"""Modrinth API client and random sampler for PureBoot.

Only public, unauthenticated endpoints are used. The sampler is intentionally
seedable so a reported pass rate can be reproduced exactly.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from .http import fetch_bytes, fetch_json, fetch_file

API = "https://api.modrinth.com/v2"
UA = "AllInOneModloader/0.1 (PureBoot)"

# Project types that can actually be loaded into a game instance. Resource and
# shader packs are not code and must not enter a load benchmark.
LOADABLE_TYPES = {"mod", "plugin"}
# Client-only mods cannot load on a dedicated server, so a server-side
# benchmark either skips them or runs a dedicated-server-capable profile.
CLIENT_ONLY_CATEGORIES = {"cosmetic", "decoration", "optimization"}


@dataclass
class Candidate:
    project_id: str
    slug: str
    title: str
    project_type: str
    loaders: list[str]
    game_versions: list[str]
    downloads: int
    file_url: str | None = None
    file_name: str | None = None
    file_hash: str | None = None
    dependencies: list[dict] = field(default_factory=list)
    # Modrinth's per-version environment tag. `client_only` is the value that
    # matters: a dedicated server cannot host such a project under any loader.
    environment: str = "unknown"
    # Every loadable type Modrinth declares for this project. A project tagged
    # both `mod` and `plugin` is one sample that may be exercised by more than
    # one runtime, so it must not be counted twice.
    project_types: list[str] = field(default_factory=list)

    @property
    def server_loadable(self) -> bool:
        """Whether this project can run on a dedicated server at all.

        Of the eight values Modrinth uses, only the exact string `client_only`
        rules the project out of every server. `client_only_server_optional`
        and `client_or_server*` all still declare a usable server side, and
        `unknown` is an untagged project that must be given the benefit of the
        doubt and actually attempted.
        """
        return self.environment != "client_only"

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "slug": self.slug,
            "title": self.title,
            "project_type": self.project_type,
            "project_types": self.project_types or [self.project_type],
            "loaders": self.loaders,
            "downloads": self.downloads,
            "file": self.file_name,
        }


def _facets(versions: list[str], loaders: list[str],
            project_type: str | None) -> list[list[str]]:
    f: list[list[str]] = [
        [f"versions:{v}" for v in versions],
        [f"categories:{l}" for l in loaders],
    ]
    if project_type:
        f.append([f"project_type:{project_type}"])
    return f


def _search(facets: list[list[str]], limit: int, offset: int = 0) -> dict:
    import json as _json
    import urllib.parse
    url = (f"{API}/search?limit={limit}&offset={offset}&facets="
           + urllib.parse.quote(_json.dumps(facets)))
    return fetch_json(url)


def count(mc: str, loader: str) -> int:
    """Total projects matching a version+loader facet."""
    return _search(_facets([mc], [loader], None), 1).get("total_hits", 0)


def _declared_types(hit: dict, fallback: str) -> list[str]:
    """Loadable project types of a search hit.

    ``project_type`` on a search hit is only the *primary* type. Modrinth lets a
    project declare several at once, and a large share of server plugins
    (WorldEdit, FancyNpcs, Chunky, ...) come back as ``project_type: "mod"``
    while ``all_project_types`` still lists ``plugin``. Classifying on the
    primary field alone therefore produced a benchmark with zero plugins even
    though the plugin facet matched ~4.8k projects.
    """
    raw = hit.get("all_project_types") or [hit.get("project_type", fallback)]
    return sorted(t for t in set(raw) & LOADABLE_TYPES)


def sampler_pool(mc: str, loaders: list[str],
                 limit: int = 400) -> list[dict]:
    """Collect a shuffled pool of loadable projects for the benchmark.

    The pool is deliberately larger than the sample so the final pick can be
    diversified across loaders instead of dominated by whichever ecosystem
    happens to have the most projects.

    Every (loader, project_type) cell is searched separately. Searching only
    ``project_type=mod`` would silently yield a mod-only benchmark, because
    plugins are never returned by a mod-restricted query no matter how many
    hits it has.
    """
    seen: dict[str, dict] = {}
    types = sorted(LOADABLE_TYPES)
    # Aim for an even split across loader x type cells so no single cell can
    # swamp the sample; the pool is later shuffled deterministically.
    cell_quota = max(limit // max(len(loaders) * len(types), 1), 40)
    for loader in loaders:
        for ptype in types:
            offset, fetched = 0, 0
            while fetched < cell_quota and offset < 400:
                try:
                    data = _search(_facets([mc], [loader], ptype), 50, offset)
                except Exception:
                    break
                hits = data.get("hits", [])
                if not hits:
                    break
                for h in hits:
                    pid = h["project_id"]
                    declared = _declared_types(h, ptype)
                    # Resource packs, shader packs and anything else that is
                    # not loadable code must never enter the benchmark.
                    if not declared:
                        continue
                    if pid in seen:
                        if loader not in seen[pid]["loaders"]:
                            seen[pid]["loaders"].append(loader)
                        for t in declared:
                            if t not in seen[pid]["project_types"]:
                                seen[pid]["project_types"].append(t)
                        continue
                    seen[pid] = {
                        "project_id": pid,
                        "slug": h.get("slug", pid),
                        "title": h.get("title", pid),
                        "project_type": declared[0],
                        "project_types": declared,
                        "loaders": [loader],
                        "game_versions": [mc],
                        "downloads": h.get("downloads", 0),
                    }
                    fetched += 1
                offset += 50
    return list(seen.values())


def sample(mc: str, loaders: list[str], n: int = 100,
           seed: int = 20262) -> list[Candidate]:
    """Deterministically sample `n` distinct projects, stratified.

    A plain shuffle over the pool would return whichever ecosystem happens to
    be largest and could easily return zero plugins even from a perfectly
    balanced pool. The benchmark is required to cover every loader *and* both
    project types, so the draw is done per (project_type, primary loader)
    stratum with a largest-remainder quota, and only then shuffled inside each
    stratum. Same seed -> same sample, always.
    """
    pool = sampler_pool(mc, loaders, limit=max(n * 6, 300))
    pool = [p for p in pool
            if set(p.get("project_types") or [p["project_type"]]) & LOADABLE_TYPES]
    if not pool:
        return []

    # Primary loader = the first one in the caller's preference order that this
    # project actually supports, so a dual-published project is attributed the
    # same way every run. Type bucket uses the full type set: a project that is
    # both a mod and a plugin must land in the plugin stratum, otherwise the
    # plugin runtime keeps ending up empty.
    strata: dict[tuple[str, str], list[dict]] = {}
    for p in pool:
        primary = next((l for l in loaders if l in p["loaders"]),
                       p["loaders"][0] if p["loaders"] else "unknown")
        types = set(p.get("project_types") or [p["project_type"]])
        bucket = "plugin" if "plugin" in types else "mod"
        strata.setdefault((bucket, primary), []).append(p)

    keys = sorted(strata)
    rng = random.Random(seed)
    for k in keys:
        rng.shuffle(strata[k])

    # Largest-remainder quota: floor everyone, then hand out the leftovers to
    # the strata with the biggest fractional parts.
    exact = {k: n * len(strata[k]) / len(pool) for k in keys}
    quota = {k: int(exact[k]) for k in keys}
    short = n - sum(quota.values())
    for k in sorted(keys, key=lambda k: (-(exact[k] - quota[k]), k))[:short]:
        quota[k] += 1

    picked: list[dict] = []
    for k in keys:
        picked.extend(strata[k][:quota[k]])

    # Any stratum that ran dry (small ecosystem) is backfilled from the
    # largest remaining strata so the sample size is exactly n when possible.
    if len(picked) < n:
        chosen = {p["project_id"] for p in picked}
        leftovers = [p for p in pool if p["project_id"] not in chosen]
        rng.shuffle(leftovers)
        picked.extend(leftovers[: n - len(picked)])

    # Final deterministic shuffle of the ordered sample so index order in the
    # report does not leak the stratum structure.
    rng.shuffle(picked)
    return [Candidate(**p) for p in picked]


def best_file(project_id: str, mc: str, loaders: list[str]) -> dict | None:
    """Pick the file to test: newest that supports mc and any wanted loader."""
    files = fetch_json(f"{API}/project/{project_id}/version")
    best = None
    for f in files:
        if mc not in f.get("game_versions", []):
            continue
        if loaders and not (set(f.get("loaders", [])) & set(loaders)):
            continue
        if best is None or f.get("date_published", "") > best.get("date_published", ""):
            best = f
    return best


def enrich(cand: Candidate, mc: str) -> Candidate:
    """Attach the concrete download URL and declared dependencies."""
    f = best_file(cand.project_id, mc, cand.loaders)
    if not f:
        return cand
    prim = None
    for d in f.get("dependencies", []):
        if d.get("dependency_type") == "required":
            prim = d.get("project_id") or d.get("slug")
    primary = [p for p in f.get("files", []) if p.get("primary")]

    cand.file_url = (primary[0]["url"] if primary
                     else (f.get("files") or [{}])[0].get("url"))
    cand.file_name = (primary[0]["filename"] if primary
                      else (f.get("files") or [{}])[0].get("filename"))
    cand.file_hash = (primary[0]["hashes"]["sha1"] if primary
                      else (f.get("files") or [{}])[0].get("hashes", {}).get("sha1"))
    cand.dependencies = [d for d in f.get("dependencies", [])
                         if d.get("dependency_type") == "required"
                         and (d.get("project_id") or d.get("slug")) != prim]
    # The version object exposes `environment`, not the older client_side /
    # server_side pair; reading the latter silently yields "required" for every
    # project and makes a client-only mod look server-ready.
    cand.environment = f.get("environment", "unknown")
    return cand


def download(cand: Candidate, dest: Path) -> Path | None:
    if not cand.file_url or not cand.file_name:
        return None
    return fetch_file(cand.file_url, dest, timeout=300)


if __name__ == "__main__":
    import sys
    mc = sys.argv[1] if len(sys.argv) > 1 else "26.2"
    lds = (sys.argv[2].split(",") if len(sys.argv) > 2
           else ["fabric", "forge", "neoforge"])
    print("pool counts:")
    for ld in lds:
        print(f"  {ld}: {count(mc, ld)}")
    picks = sample(mc, lds, n=10)
    print(f"\nsampled {len(picks)}:")
    for p in picks:
        print(f"  [{','.join(p.loaders)}] {p.title[:42]}")