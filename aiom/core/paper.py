"""Paper server profile resolution.

Uses the v3 fill API (https://fill.papermc.io/v3). The legacy v2 API no longer
serves 26.x, so callers must not fall back to it.
"""
from __future__ import annotations

from .http import fetch_json

FILL_V3 = "https://fill.papermc.io/v3/projects/paper"


def available_versions() -> dict[str, list[str]]:
    """Map of MC version -> ordered list of Paper builds (newest first)."""
    data = fetch_json(FILL_V3)
    return data.get("versions", {})


def latest_build(mc: str) -> int | None:
    builds = builds_for(mc)
    return builds[0] if builds else None


def builds_for(mc: str) -> list[int]:
    """Build ids for `mc`, newest first."""
    url = f"{FILL_V3}/versions/{mc}/builds"
    data = fetch_json(url)
    items = data if isinstance(data, list) else data.get("builds", [])
    ids = [b.get("id") for b in items if isinstance(b, dict) and b.get("id")]
    return sorted(ids, reverse=True)


def resolve_paper(mc: str) -> tuple[str, int]:
    """(download_url, build_id) for the newest Paper build of `mc`."""
    url = f"{FILL_V3}/versions/{mc}/builds"
    data = fetch_json(url)
    items = data if isinstance(data, list) else data.get("builds", [])
    for build in sorted((b for b in items if isinstance(b, dict)),
                        key=lambda b: b.get("id", 0), reverse=True):
        url = (build.get("downloads", {}) or {}).get(
            "server:default", {}).get("url")
        if url:
            return url, build["id"]
    raise LookupError(f"no Paper build with a server download for {mc}")


if __name__ == "__main__":
    import sys
    mc = sys.argv[1] if len(sys.argv) > 1 else "26.2"
    print("26.x groups:", {k: v for k, v in available_versions().items()
                           if k.startswith("26.")})
    print("builds:", builds_for(mc)[:5])
    print("picked:", resolve_paper(mc)[1])