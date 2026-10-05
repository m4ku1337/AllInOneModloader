"""Read a mod's authoritative id straight out of its own jar.

Guessing the mod id from the file name does not work. Real 26.2 mods
disagree with their own names often enough to break any verdict:

    jar  028-jei-26.2-neoforge-30.39.0.232.jar
    log  Just Enough Items 30.39.0.232 (jei)      <- id is "jei", not "jei-26.2..."

and the id is the only part of that log line guaranteed to be a handle rather
than prose. Reading `META-INF/neoforge.mods.toml` out of the jar removes the
guesswork entirely.

Fabric uses `fabric.mod.json` instead, with `"id": "..."`.
"""
from __future__ import annotations

import json
import re
import zipfile
from pathlib import Path

# NeoForge/Forge: modId="jei" inside META-INF/neoforge.mods.toml or mods.toml.
_TOML_ID = re.compile(r'^\s*modId\s*=\s*"([^"]+)"', re.MULTILINE)
# Fabric/Quilt: "id": "c2me_fabric"
_JSON_ID = re.compile(r'"id"\s*:\s*"([^"]+)"')

# Order matters: a NeoForge mod can ship a stale fabric.mod.json alongside the
# authoritative one, so the loader-specific file is read first.
META_FILES = (
    "META-INF/neoforge.mods.toml",
    "META-INF/mods.toml",
    "fabric.mod.json",
    "META-INF/quilt.mod.json",
    "quilt.mod.json",
)

_MAX_SCAN = 64  # jars are small, but a pathological one should not be read whole


def _scan(zf: zipfile.ZipFile, name: str) -> str | None:
    try:
        if zf.getinfo(name).file_size > 512 * 1024:
            return None
        blob = zf.read(name).decode("utf-8", "replace")
    except (KeyError, OSError, zipfile.BadZipFile):
        return None
    pat = _TOML_ID if name.endswith(".toml") else _JSON_ID
    m = pat.search(blob)
    return m.group(1) if m else None


def mod_id(jar: str | Path) -> str | None:
    """Return the mod id declared inside `jar`, or None if it cannot be read."""
    try:
        with zipfile.ZipFile(str(jar)) as zf:
            for name in META_FILES:
                found = _scan(zf, name)
                if found:
                    return found
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def mod_ids(jars: list[str | Path]) -> dict[str, str]:
    """Map jar file name -> mod id for every jar that declares one."""
    out: dict[str, str] = {}
    for j in jars:
        mid = mod_id(j)
        if mid:
            out[Path(str(j)).name] = mid
    return out


# Bukkit/Paper plugins name themselves in plugin.yml or paper-plugin.yml, and
# that name is what Paper prints at startup. It is frequently unrelated to both
# the Modrinth slug and the jar file name:
#     jar  046-orebfuscator-bukkit-5.6.2.jar -> Paper prints "Orebfuscator"
#     jar  050-pv-addon-groups-1.1.1.jar    -> Paper prints "pv-addon-groups"
_PLUGIN_YML = ("plugin.yml", "paper-plugin.yml")
_YML_NAME = re.compile(r"^\s*name\s*:\s*(\S+)\s*$", re.MULTILINE)


def plugin_name(jar: str | Path) -> str | None:
    """Return the plugin name declared in plugin.yml / paper-plugin.yml."""
    try:
        with zipfile.ZipFile(str(jar)) as zf:
            for entry in _PLUGIN_YML:
                for name in zf.namelist():
                    if name.lower() != entry:
                        continue
                    if zf.getinfo(name).file_size > 128 * 1024:
                        continue
                    blob = zf.read(name).decode("utf-8", "replace")
                    m = _YML_NAME.search(blob)
                    if m:
                        return m.group(1).strip("'\"")
    except (OSError, zipfile.BadZipFile):
        return None
    return None


def has_plugin_descriptor(jar: str | Path) -> bool:
    """True when the jar actually carries a Bukkit plugin descriptor.

    A jar without plugin.yml cannot be a plugin at all, no matter which loader
    the project page lists. Placing one in plugins/ produces
    "does not contain a paper-plugin.yml or plugin.yml!" -- a self-inflicted
    failure that has nothing to do with the project's own quality.
    """
    try:
        with zipfile.ZipFile(str(jar)) as zf:
            lowered = {n.lower() for n in zf.namelist()}
            return any(p in lowered for p in _PLUGIN_YML)
    except (OSError, zipfile.BadZipFile):
        return False


if __name__ == "__main__":
    import sys
    for arg in sys.argv[1:]:
        print(f"{Path(arg).name:52s} -> {mod_id(arg)}")
