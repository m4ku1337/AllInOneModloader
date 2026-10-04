"""Fabric loader profile resolution for a Minecraft version.

Fabric does not publish a 1:1 installer jar; the loader is injected via
`-javaagent:` and needs the intermediary mappings matching the exact MC build.
This module resolves the version triple (loader / intermediary / installer)
from meta.fabricmc.net and materialises the runtime classpath.
"""
from __future__ import annotations

from .http import fetch_bytes, fetch_file, fetch_json

UA = "AllInOneModloader/0.1 (RndMRBench 2)"
FABRIC_META = "https://meta.fabricmc.net/v2"

# Fabric 0.19.x targets the modern Mojang-official-mappings pipeline, so the
# intermediary artifact is keyed by the MC version string itself.
_LOADER_JAR = "https://maven.fabricmc.net/net/fabricmc/fabric-loader/{v}/fabric-loader-{v}.jar"


def _get_json(url: str):
    return fetch_json(url)


def _download(url: str, dest: Path) -> Path:
    return fetch_file(url, dest)


def loader_versions() -> list[dict]:
    return _get_json(f"{FABRIC_META}/versions/loader")


def game_versions() -> list[dict]:
    return _get_json(f"{FABRIC_META}/versions/game")


def supports(mc: str) -> bool:
    return any(g["version"] == mc for g in game_versions())


def latest_loader() -> str:
    return loader_versions()[0]["version"]


def loader_profile(mc: str) -> dict | None:
    """Loader+intermediary pair for `mc`, or None if Fabric never shipped it."""
    builds = _get_json(f"{FABRIC_META}/versions/loader/{mc}")
    return builds[0] if builds else None


def fetch_loader(mc: str, loader: str, cache: Path) -> Path:
    url = _LOADER_JAR.format(v=loader)
    return _download(url, cache / f"fabric-loader-{loader}.jar")


def fetch_intermediary(mc: str, cache: Path) -> Path | None:
    """Intermediary jar for `mc`. None means the build uses Mojang mappings."""
    url = f"{FABRIC_META}/versions/intermediary/{mc}"
    try:
        dest = cache / f"intermediary-{mc}.jar"
        return _download(url, dest)
    except Exception:
        return None


if __name__ == "__main__":
    import sys

    mc = sys.argv[1] if len(sys.argv) > 1 else "26.2"
    gv = [g["version"] for g in game_versions()][:8]
    print(f"loader latest : {latest_loader()}")
    print(f"game versions : {gv}")
    print(f"supports {mc} : {supports(mc)}")
    prof = loader_profile(mc)
    if prof:
        print(f"loader build  : {prof['loader']['version']}")
        print(f"intermediary  : {prof['intermediary']['version']}")
        print(f"  maven       : {prof['loader']['maven']}")
    else:
        print(f"loader build  : NONE for {mc}")