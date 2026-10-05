"""HTTP transport with a curl-first policy.

The bundled CPython TLS stack is blocked in some sandboxed environments
(SSL: UNEXPECTED_EOF_WHILE_READING) while the system curl works fine. Every
network call in AllInOneModloader routes through here so the project behaves
identically on a developer machine and inside CI containers.

curl is the primary path rather than the fallback: urllib's timeout is per
socket operation, so it cannot enforce a whole-transfer deadline, and a
mid-stream `IncompleteRead` is not an OSError -- it used to escape the handler
meant to reach the fallback. urllib is still tried when curl is missing or
refused, so behaviour degrades rather than breaking.
"""
from __future__ import annotations

import http.client
import json
import shutil
import subprocess
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

UA = "AllInOneModloader/0.1 (PureBoot)"
TIMEOUT = 300


def _has_curl() -> bool:
    return shutil.which("curl") is not None


def fetch_bytes(url: str, timeout: int = TIMEOUT) -> bytes:
    """GET a URL within an overall `timeout` budget.

    curl goes first, and that ordering is deliberate. urllib's `timeout` is a
    per-socket-operation timeout, not a budget for the whole transfer: a 63 MB
    Paper jar that stalls and then drops mid-stream raises `IncompleteRead`
    after far longer than the deadline the caller set -- measured at 653s
    against a 300s budget. `IncompleteRead` is an `http.client.HTTPException`,
    so it also slipped past the `(URLError, OSError)` handler that was meant to
    trigger the curl fallback, and the run simply died.

    curl's `--max-time` bounds the whole transfer and `subprocess.run(timeout=)`
    bounds the process itself. urllib stays as the fallback so nothing
    regresses where curl is missing or refused.
    """
    curl_error: Exception | None = None
    if _has_curl():
        try:
            proc = subprocess.run(
                ["curl", "-sSL", "--fail", "--max-time", str(int(timeout)),
                 "-A", UA, url],
                capture_output=True, check=True, timeout=timeout + 15,
            )
            return proc.stdout
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired,
                OSError) as exc:
            # A proxy may block curl outright while letting Python through, so
            # fall through rather than failing here.
            curl_error = exc

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()
    except (urllib.error.URLError, OSError,
            http.client.HTTPException) as exc:
        if curl_error is not None:
            raise curl_error from exc
        raise


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