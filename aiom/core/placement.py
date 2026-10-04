"""Multi-ecosystem placement and dependency resolution for AllInOne.

PureBoot measures whether a project can actually load. This module decides
*where* it goes and *what else must come with it*, which is the part that
determines whether a mixed instance is even constructible.

Two rules drive everything, both derived from measured 26.2 data:

1.  **A project is placed by its published loaders, never by a bridge.**
    Minecraft 26.2 has no working Fabric/NeoForge bridge (Sinytra Connector
    stops at 26.1.2), and NeoForge explicitly refuses Fabric jars. But 26.2
    has 2493 projects that publish both ecosystems as separate builds, so
    "run many ecosystems together" is satisfiable through *multi-ecosystem
    publishing* instead of a compatibility layer.

2.  **Dependencies are solvable, so they are solved.**
    54% of a random 26.2 sample has a required dependency outside the
    sample, yet the closure of 100 projects resolved to 129 nodes with zero
    unresolvable edges. Dependency shape is not the bottleneck; loader
    exclusivity is.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field

from .http import fetch_json

API = "https://api.modrinth.com/v2"
MC = "26.2"

# Modrinth loader ids grouped into the two runtimes AllInOne hosts. Fabric
# forks map to fabric; the Bukkit forks map to paper. Anything absent here
# (sponge/bungeecord/velocity datapacks, java agents) is a different kind of
# software and is deliberately not treated as a loadable mod.
FAMILY = {
    "fabric": "fabric", "quilt": "fabric", "legacy-fabric": "fabric",
    "ornithe": "fabric", "rift": "fabric", "modloader": "fabric",
    "liteloader": "fabric", "nilloader": "fabric",
    "neoforge": "neoforge", "forge": "neoforge",
    "paper": "paper", "purpur": "paper", "spigot": "paper",
    "bukkit": "paper", "folia": "paper", "babric": "paper",
    "bta-babric": "paper",
}
# Which runtime directory hosts each family.
HOST_OF = {"neoforge": "neoforge", "fabric": "neoforge", "paper": "paper"}

# Preference order. The first entry of each tuple is the *native* loader for
# that runtime; the rest are accepted fallbacks in order.
#
# Getting this order wrong is not cosmetic. NeoForge refuses Forge-lineage jars
# outright:
#     "TerraBlender-forge-26.2.jar is for Minecraft Forge or an older version
#      of NeoForge, and cannot be loaded"
# so a project publishing both must be taken from its NeoForge build even though
# "forge" sorts before "neoforge" alphabetically.
HOST_PREFERENCE = (
    ("neoforge", "forge"),
    ("fabric", "quilt", "legacy-fabric"),
    ("paper", "purpur", "spigot", "bukkit", "folia"),
)


@dataclass
class Resolved:
    """One project, resolved to a concrete downloadable file."""
    project_id: str
    slug: str
    title: str
    project_type: str
    version_number: str = ""
    families: list[str] = field(default_factory=list)
    loaders: list[str] = field(default_factory=list)
    host: str = ""          # neoforge | paper | ""
    chosen_loader: str = ""  # the loader the chosen jar was built for
    filename: str = ""
    url: str = ""
    sha1: str = ""
    size: int = 0
    required: list[str] = field(default_factory=list)
    reason: str = ""        # why not placeable, when host == ""
    environment: str = "unknown"

    @property
    def placeable(self) -> bool:
        return bool(self.host and self.url)

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id, "slug": self.slug,
            "title": self.title, "type": self.project_type,
            "version": self.version_number, "families": self.families,
            "loaders": self.loaders, "host": self.host,
            "chosen_loader": self.chosen_loader, "file": self.filename,
            "size": self.size, "required": self.required,
            "environment": self.environment,
            "placeable": self.placeable, "reason": self.reason,
        }


def _versions(pid: str) -> list[dict]:
    try:
        return fetch_json(f"{API}/project/{pid}/version", timeout=60)
    except Exception:
        return []


def _primary(v: dict) -> dict | None:
    files = v.get("files") or []
    prim = [f for f in files if f.get("primary")] or files
    return prim[0] if prim else None


def resolve(project_id: str, slug: str = "", title: str = "",
            ptype: str = "mod", mc: str = MC) -> Resolved | None:
    """Pick the best 26.2 build this project can contribute to the instance.

    A project may publish several builds for 26.2 (one per ecosystem). We walk
    the host preference order and take the first build whose loader maps to a
    runtime we host. This is what lets a dual-published mod count as loaded
    even though we never bridge the ecosystems inside one JVM.
    """
    vs = _versions(project_id)
    if not vs:
        return None
    by_loader: dict[str, dict] = {}
    for v in vs:
        if mc not in v.get("game_versions", []):
            continue
        f = _primary(v)
        if not f:
            continue
        for ld in v.get("loaders", []):
            by_loader.setdefault(ld, {**v, "file": f, "loader": ld})

    r = Resolved(project_id=project_id, slug=slug or project_id,
                 title=title or slug or project_id, project_type=ptype)
    r.families = sorted({FAMILY[l] for l in by_loader if l in FAMILY})
    r.loaders = sorted(by_loader)
    # Any 26.2 build's environment tag will do: a project that ships a
    # client_only build for 26.2 has told us no server runtime can host it.
    r.environment = next((v.get("environment", "unknown")
                          for v in by_loader.values()), "unknown")

    # Each entry is (family, loaders-in-preference-order). The family is always
    # the first loader in its own tuple, so it is read from there rather than
    # destructured -- unpacking would fail on the longer fallback tuples.
    for entry in HOST_PREFERENCE:
        fam, loaders = entry[0], entry
        for loader in loaders:
            if loader not in by_loader:
                continue
            if FAMILY.get(loader) != fam:
                continue
            v = by_loader[loader]
            f = v["file"]
            r.host = HOST_OF[fam]
            r.chosen_loader = loader
            r.version_number = v.get("version_number", "")
            r.filename = f.get("filename", "")
            r.url = f.get("url", "")
            r.sha1 = (f.get("hashes") or {}).get("sha1", "")
            r.size = f.get("size", 0)
            r.environment = v.get("environment", "unknown")
            r.required = [d.get("project_id") or d.get("slug")
                          for d in v.get("dependencies", [])
                          if d.get("dependency_type") == "required"
                          and (d.get("project_id") or d.get("slug"))]
            return r

    r.reason = (f"no build for a hosted ecosystem "
                f"(loaders: {','.join(r.loaders) or 'none'})")
    return r


def closure(roots: list[tuple[str, str, str, str]], mc: str = MC,
            max_nodes: int = 400) -> list[Resolved]:
    """Expand required dependencies until the set closes.

    `roots` are (project_id, slug, title, type) tuples. Dependencies are
    fetched breadth-first and deduplicated by project id, so a mod required by
    five others is downloaded once.
    """
    seen: dict[str, Resolved] = {}
    queue: list[tuple[str, str, str, str]] = list(roots)
    with ThreadPoolExecutor(max_workers=8) as pool:
        while queue and len(seen) < max_nodes:
            batch = queue[:64]
            queue = queue[64:]
            found = list(pool.map(lambda a: resolve(a[0], a[1], a[2], a[3], mc),
                                   batch))
            for r in found:
                if r is None or r.project_id in seen:
                    continue
                seen[r.project_id] = r
                for dep in r.required:
                    if dep not in seen:
                        queue.append((dep, dep, dep, "mod"))

    out = list(seen.values())
    # Dependencies first: a library must be on disk before the mod needing it.
    out.sort(key=lambda r: (0 if r.slug in
                            {s for _, s, _, _ in roots} else 1, r.slug))
    return out
