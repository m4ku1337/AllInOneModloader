"""Report which installer dependencies are absent from libraries/.

Used to diagnose installer failures caused by a blocked Java HTTP client: the
installer names every URL it wanted, and this compares that list against what
is actually on disk.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


def relpaths(libroot: Path) -> set[str]:
    return {
        p.relative_to(libroot).as_posix()
        for p in libroot.rglob("*.jar")
        if p.is_file()
    }


def wanted(blob: str) -> set[str]:
    urls = set(re.findall(r'https?://[^\s,"]+\.jar', blob))
    out = set()
    for u in urls:
        path = u.split("/releases/", 1)[-1]
        path = path.split("libraries.minecraft.net/", 1)[-1]
        path = path.split("maven.minecraftforge.net/", 1)[-1]
        if "/" in path:
            out.add(path)
    return out


def main(instance: str) -> int:
    inst = Path(instance)
    libroot = inst / "libraries"
    log = inst / "installer.log"
    if not log.exists():
        print("no installer.log")
        return 1
    blob = log.read_text(encoding="utf-8", errors="replace")
    have = relpaths(libroot)
    need = wanted(blob)
    missing = sorted(need - have)
    print(f"have {len(have)} jars, installer wanted {len(need)}, "
          f"missing {len(missing)}")
    for m in missing:
        print("  MISSING", m)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "."))