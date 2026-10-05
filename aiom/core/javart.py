"""Java runtime discovery for Minecraft 26.2+.

MC 26.2 declares javaVersion.majorVersion = 25. A wrong runtime fails in
confusing ways (UnsupportedClassVersionError deep in bootstrap), so the
launcher verifies the version up front instead of trusting the ambient JRE.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Locations checked before falling back to PATH, in priority order.
_WINDOWS_CANDIDATES = [
    Path(r"C:\Program Files\Java"),
    Path(r"C:\Program Files\Eclipse Adoptium"),
    Path(r"C:\Program Files\Microsoft\jdk"),
    Path(r"C:\Program Files\Zulu"),
]

_VERSION_RE = re.compile(r'version "(\d+)(?:\.(\d+))?')

# Seconds allowed for `java -version`. Generous for a cold JVM start, far below
# the point where a stuck probe starts costing whole minutes on a CI runner.
PROBE_TIMEOUT = max(5, int(os.environ.get("AIOM_JAVA_PROBE_TIMEOUT", "20")))

_VERSION_CACHE: dict[str, int] = {}


def _java_bin(home: Path) -> Path:
    name = "java.exe" if platform.system() == "Windows" else "java"
    return home / "bin" / name


def probe_major(java: Path) -> int | None:
    """Major version of a java binary, or None if it will not run.

    The timeout is short on purpose. A JVM that cannot answer `-version` in a
    few seconds is not one we want to boot a server with, and on a CI runner
    with several JDKs installed each stalled probe would otherwise cost a full
    minute before the search moved on.
    """
    key = str(java)
    if key in _VERSION_CACHE:
        return _VERSION_CACHE[key]
    try:
        out = subprocess.run([str(java), "-version"], capture_output=True,
                             text=True, timeout=PROBE_TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"[aiom] java probe timed out after {PROBE_TIMEOUT}s: {java}",
              file=sys.stderr, flush=True)
        return None
    except Exception as exc:
        print(f"[aiom] java probe failed for {java}: {exc}",
              file=sys.stderr, flush=True)
        return None
    blob = (out.stderr or "") + (out.stdout or "")
    m = _VERSION_RE.search(blob)
    if not m:
        return None
    major = int(m.group(1))
    _VERSION_CACHE[key] = major
    return major


def candidates() -> list[Path]:
    """Every java home we can see, best-guess first."""
    found: list[Path] = []

    env_home = os.environ.get("AIOM_JAVA_HOME") or os.environ.get("JAVA_HOME")
    if env_home:
        p = Path(env_home)
        if (p / "bin").is_dir():
            found.append(p)

    if platform.system() == "Windows":
        for base in _WINDOWS_CANDIDATES:
            if not base.is_dir():
                continue
            for child in sorted(base.iterdir(), reverse=True):
                if child.is_dir() and (_java_bin(child)).exists():
                    found.append(child)
    else:
        for base in (Path("/usr/lib/jvm"), Path("/Library/Java/JavaVirtualMachines")):
            if base.is_dir():
                found.extend(sorted((c for c in base.iterdir() if c.is_dir()),
                                    reverse=True))

    on_path = shutil.which("java")
    if on_path:
        # .../bin/java -> parent of bin
        found.append(Path(on_path).parent.parent)

    seen, unique = set(), []
    for p in found:
        s = str(p)
        if s not in seen:
            seen.add(s)
            unique.append(p)
    return unique


def find(required_major: int) -> Path:
    """Locate a java home whose major version >= required_major.

    Raises RuntimeError with the full inventory when nothing qualifies, so the
    failure message tells the user exactly which runtimes were inspected.
    """
    inspected: list[str] = []
    for home in candidates():
        java = _java_bin(home)
        major = probe_major(java)
        if major is None:
            continue
        inspected.append(f"{home} -> {major}")
        if major >= required_major:
            return home
    raise RuntimeError(
        f"No Java >= {required_major} found for Minecraft 26.2.\n"
        f"Inspected:\n  " + "\n  ".join(inspected or ["(nothing found)"]) +
        "\nSet AIOM_JAVA_HOME to a JDK 25+ installation."
    )


def resolve(required_major: int) -> tuple[Path, int]:
    home = find(required_major)
    return home, probe_major(_java_bin(home))


if __name__ == "__main__":
    need = 25
    try:
        home, major = resolve(need)
        print(f"OK  java {major}  {home}")
    except RuntimeError as exc:
        print("FAIL", exc)