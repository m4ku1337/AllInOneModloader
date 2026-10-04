"""Launch a Minecraft 26.2 instance under a chosen loader.

Design rule: a result is PASS only if the JVM produced a positive readiness
marker in its own log ("Done (" for servers). Process exit code alone is
never sufficient, because a benchmark that reports pass on a stub would be
worse than no benchmark at all.

Each loader is prepared by its own official installer, then booted with the
exact argument file that installer produced. Readiness markers differ per
loader and are matched case-insensitively.
"""
from __future__ import annotations

import os
import re
import shutil
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from . import fabric, javart, mcmeta
from .http import fetch_bytes, fetch_file

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".aiom" / "cache"

FABRIC_INSTALLER = ("https://maven.fabricmc.net/net/fabricmc/fabric-installer/"
                    "1.1.2/fabric-installer-1.1.2.jar")
NEOFORGE_VERSIONS = ("https://maven.neoforged.net/api/maven/versions/releases/"
                     "net/neoforged/neoforge")
FORGE_VERSIONS = ("https://maven.minecraftforge.net/net/minecraftforge/forge/"
                  "maven-metadata.xml")

# Log lines that prove the server finished initialising.
READY = re.compile(r"Done \([\d.,]+s\)!|Server ready|Started @|For help, type \"help\"",
                   re.IGNORECASE)


class Outcome(str, Enum):
    PASS = "pass"
    FAIL_NOT_READY = "fail_not_ready"
    FAIL_CRASH = "fail_crash"
    FAIL_TIMEOUT = "fail_timeout"
    FAIL_ENV = "fail_env"
    FAIL_PREPARE = "fail_prepare"


@dataclass
class LaunchResult:
    outcome: Outcome
    duration_s: float
    exit_code: int | None
    log_path: Path
    detail: str = ""
    log_tail: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return self.outcome is Outcome.PASS

    def to_dict(self) -> dict:
        return {
            "outcome": self.outcome.value,
            "duration_s": round(self.duration_s, 2),
            "exit_code": self.exit_code,
            "detail": self.detail,
            "log": str(self.log_path),
        }


def classify(text: str, code: int | None) -> tuple[Outcome, str]:
    low = text.lower()
    if READY.search(text):
        return Outcome.PASS, "readiness marker found"
    if "unsupportedclassversion" in low:
        return Outcome.FAIL_ENV, "wrong Java version"
    if "could not find or load main class" in low:
        return Outcome.FAIL_ENV, "entrypoint missing"
    if "mixin apply failed" in low or "mixin failed" in low:
        return Outcome.FAIL_CRASH, "mixin transform failed"
    if "outofmemory" in low:
        return Outcome.FAIL_ENV, "heap exhausted"
    return Outcome.FAIL_NOT_READY, f"no readiness marker (exit {code})"


def tail(text: str, n: int = 25) -> list[str]:
    return [ln for ln in text.splitlines() if ln.strip()][-n:]


def boot(cmd: list[str], log: Path, timeout: int,
         cwd: Path, stop_marker: str | None = None) -> tuple[str, int | None]:
    """Run a server JVM, terminate it once `stop_marker` appears (or on timeout).

    Returns (output, exit_code). A server that reaches readiness is stopped on
    purpose, so a non-zero exit afterwards is expected and never a failure on
    its own; readiness is decided from the log text instead.
    """
    log.parent.mkdir(parents=True, exist_ok=True)
    proc = subprocess.Popen(
        cmd, cwd=str(Path(cwd).resolve()), stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        errors="replace", bufsize=1,
    )
    chunks: list[str] = []
    deadline = time.time() + timeout
    ready = False
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            chunks.append(line)
            if stop_marker and stop_marker in line:
                ready = True
                # Give the server a moment to finish flushing, then stop it.
                deadline = min(deadline, time.time() + 20)
            if time.time() > deadline:
                break
    finally:
        if proc.poll() is None:
            _stop_tree(proc, cwd)
    out = "".join(chunks)
    log.write_text(out, encoding="utf-8")
    return out, proc.returncode


def _stop_tree(proc: subprocess.Popen, cwd: Path) -> None:
    """Terminate the server and every JVM it spawned.

    Plain `terminate()` is not enough here. Paper starts through paperclip,
    which unpacks and then launches the real server as a *child* JVM; killing
    the parent leaves that child holding `paper.jar`, `libraries/` and the world
    lock. The next run then fails with "Device or resource busy" while deleting,
    or `DirectoryLock.create` while booting, and neither error points at a
    surviving process.

    `taskkill /T` is tried first while we still know the pid, then a
    command-line sweep runs unconditionally: by the time the parent has exited,
    its pid no longer identifies the tree, so the only reliable handle left is
    the instance path baked into the child's command line.
    """
    if os.name == "nt":
        subprocess.run(["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                       capture_output=True, check=False)
    else:
        try:
            import signal
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            proc.kill()
    try:
        proc.wait(timeout=25)
    except subprocess.TimeoutExpired:
        proc.kill()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            pass
    kill_stray_servers(str(Path(cwd).resolve()))


def kill_stray_servers(instance_hint: str = "") -> int:
    """Terminate leftover Minecraft server JVMs belonging to this workspace.

    A run that was interrupted, or whose parent exited before its children, can
    leave a server holding the world lock. Every later boot would then fail for
    a reason unrelated to the mods under test. Only JVMs whose command line
    points inside this workspace are touched, so unrelated Java work is safe.

    Implementation notes live in `winproc`; the short version is that no
    external tool is used, because every shell-based option failed silently
    (`wmic` is gone; `taskkill /T` needs a parent that has already exited).
    """
    if os.name != "nt":
        return 0
    marker = instance_hint or str(Path(__file__).resolve().parents[2])
    try:
        from . import winproc
        return len(winproc.kill_servers_under(marker))
    except (ImportError, OSError):
        return 0


def _has_ready(text: str) -> bool:
    return bool(READY.search(text))


def _java_cmd(java_home: Path) -> str:
    return str(java_home / "bin" / ("java.exe" if os.name == "nt" else "java"))


def prepare_fabric(instance: Path, mc: str = mcmeta.TARGET_MC) -> tuple[list[str], str]:
    """Install a Fabric server profile. Returns (cmd_args, detail)."""
    instance.mkdir(parents=True, exist_ok=True)
    (instance / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    installer = fetch_file(FABRIC_INSTALLER, CACHE / "fabric-installer-1.1.2.jar")
    java_home, _ = javart.resolve(mcmeta.java_major(mc))
    subprocess.run(
        [_java_cmd(java_home), "-jar", str(installer), "server",
         "-mcversion", mc, "-loader", fabric.latest_loader(),
         "-dir", str(instance.resolve())],
        capture_output=True, text=True, cwd=str(instance.resolve()),
        encoding="utf-8", errors="replace", timeout=900,
    )
    launcher = instance / "fabric-server-launch.jar"
    if not launcher.exists():
        raise RuntimeError("fabric installer produced no launcher jar")
    return ["-jar", str(launcher.resolve()), "nogui"], f"fabric {fabric.latest_loader()}"


def prepare_neoforge(instance: Path, mc: str = mcmeta.TARGET_MC) -> tuple[list[str], str]:
    """Install NeoForge. Sandbox-safe: libraries are pre-fetched with curl
    because the NeoForge installer's own HTTP client is frequently blocked."""
    raw = fetch_bytes(NEOFORGE_VERSIONS).decode()
    vs = [v for v in re.findall(r'"(26\.\d[^"]*)"', raw) if v.startswith(mc + ".")]
    if not vs:
        raise RuntimeError(f"no NeoForge build for {mc}")
    ver = sorted(vs, key=lambda v: int(re.match(r"26\.\d+\.0\.(\d+)", v).group(1)))[-1]

    instance.mkdir(parents=True, exist_ok=True)
    (instance / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    installer = fetch_file(
        f"https://maven.neoforged.net/releases/net/neoforged/neoforge/{ver}/"
        f"neoforge-{ver}-installer.jar",
        instance / "nf-installer.jar")

    java_home, _ = javart.resolve(mcmeta.java_major(mc))
    _run_installer(instance, installer)

    args = instance / "libraries" / "net" / "neoforged" / "neoforge" / ver / "win_args.txt"
    if not args.exists():
        args = instance / "libraries" / "net" / "neoforged" / "neoforge" / ver / "unix_args.txt"
    if not args.exists():
        raise RuntimeError(f"NeoForge {ver} install incomplete")
    return ([f"@{instance.resolve() / 'user_jvm_args.txt'}", f"@{args.resolve()}", "nogui"],
            f"neoforge {ver}")


def _coords_to_urls(blob: str) -> set[str]:
    """Recover maven URLs from the installer's stdout.

    The installer prints one `group:artifact:version[:classifier]` per line
    before it starts downloading. Its own HTTP client is unreliable in
    sandboxed environments, so we resolve those coordinates ourselves via curl.
    """
    urls: set[str] = set()
    for line in blob.splitlines():
        line = line.strip()
        if not re.fullmatch(r"[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+:[A-Za-z0-9_.\-]+(:[A-Za-z0-9_.\-]+)?", line):
            continue
        parts = line.split(":")
        group, artifact, version = parts[0], parts[1], parts[2]
        ext = "jar"
        if len(parts) > 3:
            continue  # classified artifacts are not required for the server
        path = f"{group.replace('.', '/')}/{artifact}/{version}/{artifact}-{version}.{ext}"
        urls.add(f"https://maven.neoforged.net/releases/{path}")
        urls.add(f"https://libraries.minecraft.net/{path}")
        urls.add(f"https://maven.minecraftforge.net/{path}")
    return urls


def _run_installer(instance: Path, installer: Path, attempts: int = 3) -> str:
    """Run an installer, prefetching the libraries it could not download.

    Returns the combined log blob. Retries because the first pass usually
    fails on blocked network while populating installer.log; after a prefetch
    the second pass has everything it needs locally.
    """
    java_home, _ = javart.resolve(mcmeta.java_major(mcmeta.TARGET_MC))
    # cwd is the instance, so every path handed to the JVM must be absolute or
    # the installer jar itself becomes unresolvable.
    jar = str(installer.resolve())
    blob = ""
    for attempt in range(attempts):
        proc = subprocess.run(
            [_java_cmd(java_home), "-jar", jar, "--installServer"],
            capture_output=True, text=True, cwd=str(instance.resolve()),
            encoding="utf-8", errors="replace", timeout=1800,
        )
        blob = (proc.stdout or "") + (proc.stderr or "")
        log = instance / "installer.log"
        if log.exists():
            blob += log.read_text(encoding="utf-8", errors="replace")
        urls = set(re.findall(r"https?://[^\s,\"]+\.jar", blob))
        urls |= _coords_to_urls(blob)
        _prefetch(instance, " ".join(urls))
        if _installer_done(instance):
            return blob
    return blob


def _installer_done(instance: Path) -> bool:
    """True once an installer has produced a runnable args file."""
    return any(instance.glob("libraries/**/win_args.txt")) or \
        any(instance.glob("libraries/**/unix_args.txt"))


def _prefetch(instance: Path, url_blob: str) -> int:
    """Mirror the given jar URLs into libraries/ using curl.

    The installers' own HTTP clients are unreliable behind restrictive proxies,
    but curl succeeds, so we satisfy their dependency list out-of-band and let
    the installer run fully offline on the retry.
    """
    urls = {u for u in re.findall(r"https?://[^\s,\"]+\.jar", url_blob) if u}
    if not urls or shutil.which("curl") is None:
        return 0
    n = 0
    for u in urls:
        rel = _maven_relpath(u)
        if not rel:
            continue
        dest = instance / "libraries" / rel
        if dest.exists() and dest.stat().st_size > 0:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["curl", "-sSL", "--fail", "--max-time", "120",
                            "-o", str(dest), u], capture_output=True)
        if r.returncode != 0:
            dest.unlink(missing_ok=True)
        else:
            n += 1
    return n


def _maven_relpath(url: str) -> str | None:
    """`group/as/paths/art-ver.jar` for a maven URL, or None if not maven-shaped.

    The full group path must be preserved: maven resolves
    `org.ow2.asm:asm` to `org/ow2/asm/asm/...`, and writing it to
    `asm/asm/...` yields a directory layout the installer will not accept.
    """
    without_scheme = url.split("://", 1)[-1]
    if "/" not in without_scheme:
        return None
    path = without_scheme.split("/", 1)[1]
    for marker in ("releases/", "libraries.minecraft.net/",
                   "maven.minecraftforge.net/", "maven.neoforged.net/"):
        if path.startswith(marker):
            path = path[len(marker):]
            break
        if marker.strip("/") + "/" in path:
            path = path.split(marker.strip("/") + "/", 1)[1]
            break
    else:
        # Unknown host: trust the path as-is if it is maven-shaped, i.e. it
        # ends in group/artifact/version/artifact-version.jar.
        segs = [s for s in path.split("/") if s]
        if len(segs) < 4:
            return None
        path = "/".join(segs)
    # "+" is legal in maven versions (e.g. sponge-mixin 0.17.3+mixin.0.8.7)
    # and must be allowed, otherwise such artifacts are silently skipped.
    if not re.fullmatch(r"[A-Za-z0-9_./+\-]+\.jar", path):
        return None
    return path


def prepare_forge(instance: Path, mc: str = mcmeta.TARGET_MC) -> tuple[list[str], str]:
    """Install a Forge server profile (latest stable build for `mc`)."""
    raw = fetch_bytes(FORGE_VERSIONS).decode("utf-8", "replace")
    vs = [v for v in re.findall(r"<version>([^<]+)</version>", raw)
          if v.startswith(mc + "-")]
    if not vs:
        raise RuntimeError(f"no Forge build for {mc}")
    # Forge versions look like "26.2-65.1.3"; sort on the numeric tail.
    ver = sorted(vs, key=lambda v: [int(x) for x in
                                     re.findall(r"\d+", v)])[-1]

    instance.mkdir(parents=True, exist_ok=True)
    (instance / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    installer = fetch_file(
        f"https://maven.minecraftforge.net/net/minecraftforge/forge/{ver}/"
        f"forge-{ver}-installer.jar",
        instance / "forge-installer.jar")

    java_home, _ = javart.resolve(mcmeta.java_major(mc))
    _run_installer(instance, installer)

    base = instance / "libraries" / "net" / "minecraftforge" / "forge" / ver
    args = base / "win_args.txt"
    if not args.exists():
        args = base / "unix_args.txt"
    if not args.exists():
        raise RuntimeError(f"Forge {ver} install incomplete")
    return ([f"@{instance.resolve() / 'user_jvm_args.txt'}", f"@{args.resolve()}", "nogui"],
            f"forge {ver}")


def prepare_paper(instance: Path, mc: str = mcmeta.TARGET_MC) -> tuple[list[str], str]:
    """Install a Paper server profile (latest build for `mc`)."""
    from .paper import resolve_paper

    instance.mkdir(parents=True, exist_ok=True)
    (instance / "eula.txt").write_text("eula=true\n", encoding="utf-8")
    url, build = resolve_paper(mc)
    jar = fetch_file(url, instance / "paper.jar", timeout=600)
    return ["-jar", str(jar.resolve()), "nogui"], f"paper {mc} build {build}"


def launch(loader: str, instance: Path, timeout: int = 210,
           mc: str = mcmeta.TARGET_MC, extra_jvm: list[str] | None = None,
           ) -> LaunchResult:
    """Install + boot `loader` in `instance` and classify the result."""
    instance.mkdir(parents=True, exist_ok=True)
    log = instance / "logs" / f"{loader}-boot.log"
    started = time.time()
    try:
        if loader == "fabric":
            args, detail = prepare_fabric(instance, mc)
        elif loader == "neoforge":
            args, detail = prepare_neoforge(instance, mc)
        elif loader == "forge":
            args, detail = prepare_forge(instance, mc)
        elif loader == "paper":
            args, detail = prepare_paper(instance, mc)
        else:
            raise ValueError(f"unsupported loader {loader}")
    except Exception as exc:
        return LaunchResult(Outcome.FAIL_PREPARE, time.time() - started, None,
                            log, detail=f"{type(exc).__name__}: {exc}"[:300])

    java_home, major = javart.resolve(mcmeta.java_major(mc))
    cmd = [_java_cmd(java_home), "-Xmx3G", *(extra_jvm or []), *args]
    # "Done (" is emitted only after full initialisation on every loader.
    out, code = boot(cmd, log, timeout, instance, stop_marker="Done (")
    outcome, why = classify(out, code)
    return LaunchResult(outcome, time.time() - started, code, log,
                        detail=f"{detail}; {why}; java {major}",
                        log_tail=tail(out))


if __name__ == "__main__":
    import sys
    ld = sys.argv[1] if len(sys.argv) > 1 else "fabric"
    res = launch(ld, ROOT / ".aiom" / "verify" / ld)
    print(f"{res.outcome.value}: {res.detail}")
    for line in res.log_tail[-8:]:
        print("   ", line[:160])