"""Publish the current tree to GitHub via the REST API.

Needed because this machine's git cannot complete a TLS handshake
(CRYPT_E_NO_REVOCATION_CHECK from schannel), while `gh` itself reaches the API
fine. Uploads each tracked file to the repository's default branch.

Safe by construction:
  * only files already tracked by git are sent, so .gitignore rules
    (which exclude jars, instances and local agent memory) are honoured
  * refuses to send anything matching a secret-looking pattern
"""
from __future__ import annotations

import base64
import json
import subprocess
import sys
from pathlib import Path

import urllib.error
import urllib.request

REPO = "m4ku1337/AllInOneModloader"
API = f"https://api.github.com/repos/{REPO}"
TOKEN = subprocess.run(
    ["gh", "auth", "token"], capture_output=True, text=True, check=True
).stdout.strip()

# Anything matching these must never leave the machine.
FORBIDDEN = ("@qq.com", "@gmail.com", "github_pat_", "ghp_", "BEGIN RSA",
             "BEGIN PRIVATE", "api_key", "apiKey")


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         check=True).stdout
    return [p for p in out.splitlines() if p.strip()]


def guard(path: str, data: bytes) -> None:
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError:
        return
    for needle in FORBIDDEN:
        if needle in text:
            raise SystemExit(f"ABORT: {path} contains {needle!r}")


def request(method: str, url: str, payload: dict | None = None):
    req = urllib.request.Request(
        url, method=method,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AllInOneModloader-publisher",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload).encode() if payload else None,
    )
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:
            return json.load(resp)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        raise SystemExit(f"{method} {url} -> HTTP {exc.code}\n{detail}") from None


def main() -> int:
    files = tracked_files()
    if not files:
        print("no tracked files")
        return 1
    print(f"uploading {len(files)} files to {REPO}")

    for rel in files:
        p = Path(rel)
        if not p.is_file():
            print(f"  skip (missing) {rel}")
            continue
        data = p.read_bytes()
        guard(rel, data)
        payload = {
            "message": f"Add {rel}",
            "content": base64.b64encode(data).decode(),
            "branch": "main",
        }
        resp = request("PUT", f"{API}/contents/{rel}", payload)
        print(f"  ok {rel} ({resp.get('commit', {}).get('sha', '')[:8]})")

    print("done")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())