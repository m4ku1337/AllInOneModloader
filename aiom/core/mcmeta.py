"""Minecraft version manifest / asset resolution helpers.

Source of truth: Mojang's official piston-meta manifest. No key, no auth,
no premium account required. Only the public version JSON is downloaded.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from .http import fetch_bytes, fetch_file, fetch_json

MAVEN_MOJANG = "https://piston-meta.mojang.com"
MANIFEST_URL = f"{MAVEN_MOJANG}/mc/game/version_manifest_v2.json"
UA = "AllInOneModloader/0.1 (PureBoot)"

# Pinned to the versions confirmed present on Mojang piston-meta during the
# PureBoot feasibility pass. Kept explicit rather than floating on
# "latest" so benchmark runs stay reproducible.
TARGET_MC = "26.2"
FABRIC_LOADER = "0.19.5"
NEOFORGE = "26.2.0.0"
FORGE = "26.2-65.1.3"
PAPER_BUILD = "129"


def _get(url: str, timeout: int = 60) -> bytes:
    return fetch_bytes(url, timeout=timeout)


@lru_cache(maxsize=1)
def manifest() -> dict:
    return json.loads(_get(MANIFEST_URL))


def version_meta(mc: str = TARGET_MC) -> dict:
    """Full version JSON for a Minecraft release (libraries, downloads, javaVersion)."""
    for entry in manifest()["versions"]:
        if entry["id"] == mc and entry["type"] == "release":
            return json.loads(_get(entry["url"]))
    raise LookupError(f"Minecraft release {mc} not found in Mojang manifest")


def java_major(mc: str = TARGET_MC) -> int:
    return version_meta(mc)["javaVersion"]["majorVersion"]


def client_jar(mc: str = TARGET_MC, dest: Path | None = None) -> Path:
    meta = version_meta(mc)
    url = meta["downloads"]["client"]["url"]
    dest = dest or Path(f"vanilla-{mc}.jar")
    return fetch_file(url, dest, timeout=600)


def server_jar(mc: str = TARGET_MC, dest: Path | None = None) -> Path:
    meta = version_meta(mc)
    url = meta["downloads"]["server"]["url"]
    dest = dest or Path(f"server-{mc}.jar")
    return fetch_file(url, dest, timeout=600)


@lru_cache(maxsize=1)
def libraries(mc: str = TARGET_MC) -> list[dict]:
    return version_meta(mc)["libraries"]


def _artifact_coords(lib: dict) -> tuple[str, str] | None:
    name = lib.get("name", "")
    dl = lib.get("downloads", {}).get("artifact")
    if not dl or not name:
        return None
    path = dl.get("path", "")
    if not path.endswith(".jar"):
        return None
    return name, dl["url"]


def fetch_libraries(
    mc: str = TARGET_MC,
    cache: Path | None = None,
    rules_filter=None,
) -> list[Path]:
    """Download every vanilla library for `mc` that passes `rules_filter`.

    `rules_filter` receives the raw library dict so callers can add loader
    specific constraints (NeoForge/Fabric gate some artifacts by OS).
    """
    cache = cache or Path(".aiom/cache/libraries")
    out: list[Path] = []
    for lib in libraries(mc):
        if rules_filter and not rules_filter(lib):
            continue
        coords = _artifact_coords(lib)
        if not coords:
            continue
        name, url = coords
        rel = lib["downloads"]["artifact"]["path"]
        try:
            out.append(fetch_file(url, cache / rel))
        except Exception:
            # A single unreachable optional library must not abort the whole
            # classpath; the launch probe reports it as a missing class.
            continue
    return out


def asset_index(mc: str = TARGET_MC) -> dict:
    return version_meta(mc)["assetIndex"]


if __name__ == "__main__":
    m = version_meta()
    print(f"Minecraft {TARGET_MC}")
    print(f"  java major : {m['javaVersion']['majorVersion']}")
    print(f"  mainClass  : {m['mainClass']}")
    print(f"  libraries  : {len(m['libraries'])}")
    print(f"  assetIndex : {m['assetIndex']['id']}")