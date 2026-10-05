"""HTTP transport with a curl fallback.

The bundled CPython TLS stack is blocked in some sandboxed environments
(SSL: UNEXPECTED_EOF_WHILE_READING) while the system curl works fine. Every
network call in AllInOneModloader routes through here so the project behaves
identically on a developer machine and inside CI containers.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "AllInOneModloader/0.1 (PureBoot)"
TIMEOUT = 300


def _has_curl() -> bool:
    return shutil.which("curl") is not None


def fetch_bytes(url: str, timeout: int = TIMEOUT) -> bytes:
    """GET a URL, preferring Python urllib and falling back to curl.

    The fallback is bounded by what is left of `timeout`: if urllib already
    burned most of it, curl gets a short leash instead of a second full budget.
    Otherwise a blocked host costs the full timeout twice over, which is how a
    600s download turns into a 20-minute stall.
    """
    started = time.monotonic()
    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError):
        if not _has_curl():
            raise
        left = timeout - (time.monotonic() - started)
        if left < 5:
            # Pretending we succeeded would be worse than failing: callers
            # treat bytes as a valid payload, so re-raise the real error.
            raise
        left = int(left)
        # curl's own --max-time bounds the transfer, but not the cases where the
        # process itself never gets that far (DNS stuck in the resolver, a hung
        # spawn). Without the Python-side timeout the caller waits forever --
        # which is how a 300s download budget turned into a 25-minute job.
        proc = subprocess.run(
            ["curl", "-sSL", "--fail", "--max-time", str(left),
             "-A", UA, url],
            capture_output=True, check=True, timeout=left + 15,
        )
        return proc.stdout


def fetch_json(url: str, timeout: int = TIMEOUT):
    return json.loads(fetch_bytes(url, timeout=timeout))


def fetch_file(url: str, dest: Path, timeout: int = TIMEOUT) -> Path:
    """Download to `dest`, skipping the transfer if it already looks valid."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1024:
        return dest
    dest.write_bytes(fetch_bytes(url, timeout=timeout))
    return dest


if __name__ == "__main__":
    import sys

    print(len(fetch_bytes(sys.argv[1])), "bytes")