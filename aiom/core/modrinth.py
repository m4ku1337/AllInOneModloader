"""Modrinth API client and random sampler for RndMRBench 2.

Only public, unauthenticated endpoints are used. The sampler is intentionally
seedable so a reported pass rate can be reproduced exactly.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from pathlib import Path

from .http import fetch_bytes, fetch_json, fetch_file

API = "https://api.modrinth.com/v2"
UA = "AllInOneModloader/0.1 (RndMRBench 2)"

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
    client_side: str = "required"
    server_side: str = "required"

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "slug": self.slug,
            "title": self.title,
            "project_type": self.project_type,
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


def sampler_pool(mc: str, loaders: list[str],
                 limit: int = 400) -> list[dict]:
    """Collect a shuffled pool of loadable projects for the benchmark.

    The pool is deliberately larger than the sample so the final pick can be
    diversified across loaders instead of dominated by whichever ecosystem
    happens to have the most projects.
    """
    seen: dict[str, dict] = {}
    for loader in loaders:
        offset, fetched = 0, 0
        per_loader = max(limit // len(loaders), 40)
        while fetched < per_loader and offset < 400:
            try:
                data = _search(_facets([mc], [loader], "mod"), 50, offset)
            except Exception:
                break
            hits = data.get("hits", [])
            if not hits:
                break
            for h in hits:
                pid = h["project_id"]
                if pid in seen:
                    if loader not in seen[pid]["loaders"]:
                        seen[pid]["loaders"].append(loader)
                    continue
                seen[pid] = {
                    "project_id": pid,
                    "slug": h.get("slug", pid),
                    "title": h.get("title", pid),
                    "project_type": h.get("project_type", "mod"),
                    "loaders": [loader],
                    "game_versions": [mc],
                    "downloads": h.get("downloads", 0),
                }
                fetched += 1
            offset += 50
    return list(seen.values())


def sample(mc: str, loaders: list[str], n: int = 100,
           seed: int = 20262) -> list[Candidate]:
    """Deterministically sample `n` distinct projects."""
    pool = sampler_pool(mc, loaders, limit=max(n * 6, 300))
    pool = [p for p in pool if p["project_type"] in LOADABLE_TYPES]
    rng = random.Random(seed)
    rng.shuffle(pool)
    picked = pool[:n]
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
    cand.client_side = f.get("client_side", "required")
    cand.server_side = f.get("server_side", "required")
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