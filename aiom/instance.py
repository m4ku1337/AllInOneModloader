"""Build the reproducible AllInOne instance and launch it with one command.

Layout:

    <root>/
      run.bat / run.sh        single entry point
      config/loader.env       pinned component versions
      neoforge/               mod-side runtime  (NeoForge)
        mods/                 neoforge-lineage jars
        world -> ../shared-world
      paper/                  plugin-side runtime (Paper)
        plugins/              bukkit-lineage jars
        world -> ../shared-world
      shared-world/           the one world both runtimes use
      logs/

The two runtimes never hold the world lock at the same time; `run` starts one,
and the launcher script refuses to start the other while a pid file is live.
That is the honest form of "one instance": one directory, one world, two
runtimes that cannot corrupt each other.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from .core import jarid, mcmeta
from .core.http import fetch_file
from .core.launcher import Outcome, launch, prepare_neoforge, prepare_paper

# Pinned by measurement, not guesswork. See docs/MIXED_LOADING.md.
PINNED = {
    "minecraft": mcmeta.TARGET_MC,
    "java_major": 25,
    "neoforge": "26.2.0.88",
    "paper_build": "129",
    "loader": "fabric-0.19.5",
}


def _link_world(instance: Path) -> None:
    """Give each runtime its own world directory.

    An earlier design symlinked both runtimes onto one shared `shared-world/`.
    That does not work, and the failure is worth recording: NeoForge and Paper
    each rewrite `world_gen_settings.dat` in their own format, and taking turns
    on one directory corrupts it. The symptom appears only on the *next* boot
    and looks nothing like its cause:

        [ERROR] [minecraft/LevelStorageSource]: Unable to read or access the
        world gen settings file!
        java.lang.IllegalStateException: Overworld settings missing

    A mod author debugging that would never suspect world sharing. Each runtime
    therefore keeps its own world under `worlds/<runtime>`, and the instance
    exposes a `worlds/` root so the operator can point them at a common save
    deliberately rather than by accident.
    """
    worlds = instance / "worlds"
    for rt in ("neoforge", "paper"):
        w = instance / rt / "world"
        if w.is_symlink():
            w.unlink()
        (worlds / rt).mkdir(parents=True, exist_ok=True)
        (instance / rt / "world").mkdir(parents=True, exist_ok=True)
    (worlds / "README.md").write_text(
        "# Worlds\n\n"
        "Each runtime owns its world directory:\n\n"
        "- `neoforge/` — world used by the NeoForge runtime\n"
        "- `paper/`   — world used by the Paper runtime\n\n"
        "They are **not** shared. NeoForge and Paper serialise\n"
        "`world_gen_settings.dat` differently, so alternating on one directory\n"
        "corrupts the world and the next boot dies with\n"
        "`IllegalStateException: Overworld settings missing`.\n"
        "To migrate a save between runtimes, stop both servers and copy the\n"
        "directory while they are stopped.\n",
        encoding="utf-8")


def build(root: Path, mc: str = mcmeta.TARGET_MC) -> dict:
    """Create both runtimes and the shared world. Idempotent."""
    root = root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    (root / "logs").mkdir(exist_ok=True)
    (root / "config").mkdir(exist_ok=True)
    (root / "neoforge" / "mods").mkdir(parents=True, exist_ok=True)
    (root / "paper" / "plugins").mkdir(parents=True, exist_ok=True)

    print(f"[1/4] 准备 NeoForge 运行时 ({PINNED['neoforge']}) ...")
    if not (root / "neoforge" / "libraries").exists():
        prepare_neoforge(root / "neoforge", mc)

    print("[2/4] 准备 Paper 运行时 (build 129) ...")
    if not (root / "paper" / "eula.txt").exists():
        prepare_paper(root / "paper", mc)
    # Both runtimes are dedicated servers; accept the EULA once, here,
    # explicitly, so the instance starts unattended.
    for rt in ("neoforge", "paper"):
        e = root / rt / "eula.txt"
        if e.exists() and "eula=true" not in e.read_text(errors="replace"):
            e.write_text("eula=true\n", encoding="utf-8")
    # Paper's own server.properties is irrelevant here but its world must exist.
    sp = root / "paper" / "server.properties"
    if not sp.exists():
        sp.write_text("level-name=world\nonline-mode=false\n"
                      "max-players=20\n", encoding="utf-8")

    print("[3/4] 准备各运行时独立世界 ...")
    _link_world(root)

    print("[4/4] 写入版本清单与启动脚本 ...")
    (root / "config" / "loader.env").write_text(
        "\n".join(f"{k}={v}" for k, v in PINNED.items()) + "\n",
        encoding="utf-8")
    _write_launchers(root)

    return {"root": str(root), **PINNED}


def _write_launchers(root: Path) -> None:
    bat = f"""@echo off
REM AllInOne single-entry launcher. Usage: run.bat [neoforge^|paper]
setlocal
set RUNTIME=%1
if "%RUNTIME%"=="" set RUNTIME=neoforge
if exist "%~dp0.pid" (
  echo [AllInOne] a runtime is already running ^(pid file exists^).
  echo            stop it first, or delete %~dp0.pid if it is stale.
  exit /b 1
)
echo [AllInOne] starting %%RUNTIME%% on Minecraft {PINNED['minecraft']}
echo [AllInOne] pid file: %~dp0.pid
start "" /b cmd /c "echo %%^" > "%~dp0.pid"
python -m aiom.launcher --instance "%~dp0" --runtime %%RUNTIME%%
del "%~dp0.pid" 2>nul
endlocal
"""
    (root / "run.bat").write_text(bat, encoding="utf-8")

    sh = f"""#!/usr/bin/env bash
# AllInOne single-entry launcher. Usage: ./run.sh [neoforge|paper]
set -euo pipefail
RUNTIME="${{1:-neoforge}}"
DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)"
if [ -f "$DIR/.pid" ]; then
  echo "[AllInOne] a runtime is already running (pid file exists)."
  exit 1
fi
echo "[AllInOne] starting $RUNTIME on Minecraft {PINNED['minecraft']}"
echo $$ > "$DIR/.pid"
trap 'rm -f "$DIR/.pid"' EXIT
python -m aiom.launcher --instance "$DIR" --runtime "$RUNTIME"
"""
    p = root / "run.sh"
    p.write_text(sh, encoding="utf-8")
    try:
        p.chmod(0o755)
    except OSError:
        pass


def install(mods: list, root: Path) -> dict:
    """Place resolved jars into the right runtime directory.

    `mods` are aiom.core.placement.Resolved items. Filenames are prefixed with
    an index so two ecosystems publishing the same filename cannot collide.

    Returns counts plus `landed`: project_id -> the file name actually written.
    That mapping is not a convenience. Every jar on disk carries an `NNN-`
    prefix, so the name a project published under no longer exists anywhere,
    and any later step that needs to open the jar -- reading its mod id, for
    instance -- has to ask here rather than guess. Guessing produced a verdict
    layer that silently fell back to fuzzy matching because `exists()` was False.
    """
    root = root.resolve()
    placed = {"neoforge": 0, "paper": 0, "failed": 0, "landed": {},
              "misrouted": {}}
    for i, r in enumerate(mods):
        if not r.placeable:
            placed["failed"] += 1
            continue
        dest_dir = root / r.host / ("plugins" if r.host == "paper" else "mods")
        dest_dir.mkdir(parents=True, exist_ok=True)
        safe = r.filename or f"{r.slug}.jar"
        # `<idx>-` keeps sort order stable and avoids cross-ecosystem clashes.
        dest = dest_dir / f"{i:03d}-{safe}"
        try:
            fetch_file(r.url, dest, timeout=300)
            # A jar routed to Paper must carry a Bukkit plugin descriptor.
            # `stringandsand-1.2.0.jar` does not, and Paper rejects it with
            # "does not contain a paper-plugin.yml or plugin.yml!" -- which
            # reads like the project's fault and is not. Pull it back out and
            # record it, so the row can report the real reason.
            if r.host == "paper" and not jarid.has_plugin_descriptor(dest):
                dest.unlink(missing_ok=True)
                placed["failed"] += 1
                placed["misrouted"][r.project_id] = (
                    "routed to Paper but the jar carries no plugin.yml / "
                    "paper-plugin.yml, so it is not a Bukkit plugin")
                continue
            placed[r.host] += 1
            placed["landed"][r.project_id] = dest.name
        except Exception:
            placed["failed"] += 1
    return placed


def smoke(root: Path, mc: str = mcmeta.TARGET_MC) -> dict:
    """Boot each runtime once and report readiness. Proves the instance works."""
    out = {}
    for rt in ("neoforge", "paper"):
        print(f"冒烟测试 {rt} ...")
        res = launch(rt, root / rt, timeout=300, mc=mc)
        out[rt] = {"outcome": res.outcome.value, "detail": res.detail,
                   "log": str(res.log_path)}
        print(f"  {rt}: {res.outcome.value} — {res.detail}")
    return out


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="build the AllInOne instance")
    ap.add_argument("--root", default=".aiom/instance")
    ap.add_argument("--mc", default=mcmeta.TARGET_MC)
    ap.add_argument("--smoke", action="store_true")
    a = ap.parse_args()
    info = build(Path(a.root), a.mc)
    print(json.dumps(info, indent=2, ensure_ascii=False))
    if a.smoke:
        print(json.dumps(smoke(Path(a.root), a.mc), indent=2,
                         ensure_ascii=False))
