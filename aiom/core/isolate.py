"""Isolate the mods that break a shared instance, without giving up on it.

A single bad jar does not mean the sample failed. Loading nine mods together
and getting `Failed to start the minecraft server` tells us almost nothing about
the other eight. The honest way to report coexistence is:

1. Boot the full set. If it starts, every project present is a pass.
2. If it fails, the log names the culprit (`InjectionError ... from mod X`).
   Remove it, reboot, repeat.

This is a bisection over the installed set. It converges because each round
either boots or removes at least one jar, and it costs one boot per removal
rather than one boot per project.

The distinction that matters for the reported rate: a project removed because
it *broke* the instance is a genuine failure and stays in the denominator. What
bisection buys is that the survivors get verified instead of being swept up in
a shared crash — the failure stays attributable to the right project.
"""
from __future__ import annotations

import re
import shutil
from dataclasses import dataclass
from pathlib import Path

from . import verdict
from .launcher import Outcome, launch

# "from mod bettershulkers" / "in bettershulkers.mixins.json" / "mod X"
# Patterns are tried in order; the first one that matches supplies the culprit.
# Each must be specific enough that its capture group is a mod id, not an
# arbitrary word that happens to follow the keyword.
CULPRIT_PATTERNS = [
    # Fatal mixin failure: "in bettershulkers.mixins.json:... from mod bettershulkers"
    re.compile(r"Critical injection failure.*?in\s+([A-Za-z0-9_]+)\.mixins\.json",
               re.IGNORECASE),
    re.compile(r"from mod ([A-Za-z0-9_]+)", re.IGNORECASE),
    re.compile(r"Failed to load mod(?:ule)?\s+([A-Za-z0-9_]+)", re.IGNORECASE),
    re.compile(r"Could not load plugin ([A-Za-z0-9_]+)", re.IGNORECASE),
    re.compile(r"Error loading plugin ([A-Za-z0-9_]+)", re.IGNORECASE),
    re.compile(r"Failed to create mod instance.*?for mod\s+([A-Za-z0-9_]+)",
               re.IGNORECASE),
]


@dataclass
class Isolation:
    """Outcome of a bisection run over one runtime."""
    booted: bool = False
    log: str = ""
    detail: str = ""
    rounds: int = 0
    removed: list[str] = None      # filenames pulled to make the boot work
    blamed: list[str] = None       # mod ids named by the loader
    # Filenames removed only because a binary split had to shrink the search
    # space. These are NOT proven guilty and must not be reported as failures.
    unverified: list[str] = None

    def __post_init__(self):
        if self.removed is None:
            self.removed = []
        if self.blamed is None:
            self.blamed = []
        if self.unverified is None:
            self.unverified = []

    @property
    def guilty(self) -> list[str]:
        """Jars the loader actually named -- the only real failures."""
        return [f for f in self.removed if f not in set(self.unverified)]


def find_culprits(log_text: str) -> list[str]:
    """Mod ids the loader explicitly blamed, most-specific pattern first.

    Order is significant. A fatal mixin failure names its mod in a very
    specific way ("...in <id>.mixins.json:... from mod <id>"), while a mere
    "Skipping jar" warning names a file. Scanning every pattern and isolating
    everything it finds would evict innocent mods alongside the guilty one, so
    callers must treat only the first productive pattern as authoritative.
    """
    for pat in CULPRIT_PATTERNS:
        found: list[str] = []
        for m in pat.finditer(log_text):
            mid = m.group(1)
            if mid and mid.lower() not in {o.lower() for o in found}:
                found.append(mid)
        if found:
            return found
    return []


def _jar_for_mod_id(mods_dir: Path, mod_id: str) -> Path | None:
    """Map a blamed mod id back to its jar file.

    Matching cannot rely on separators alone: Modrinth file names are free-form
    and real ones include spaces and capitals ("000-Better Shulkers-2.0.0.jar"
    for mod id "bettershulkers"). So we normalise both sides down to
    alphanumerics and accept a prefix match either way.
    """
    def norm(s: str) -> str:
        return re.sub(r"[^a-z0-9]", "", s.lower())

    target = norm(mod_id)
    if not target:
        return None
    best: tuple[int, Path] | None = None
    for jar in mods_dir.glob("*.jar"):
        stem = re.sub(r"^\d{3}-", "", jar.stem)
        n = norm(stem)
        if not n:
            continue
        if n == target or n.startswith(target) or target.startswith(n):
            # Prefer the closest length match to avoid grabbing a jar that
            # merely shares a prefix with an unrelated mod.
            score = abs(len(n) - len(target))
            if best is None or score < best[0]:
                best = (score, jar)
    return best[1] if best else None


def _boot(rt: str, root: Path, mc: str, timeout: int) -> tuple[bool, str, str]:
    # Both runtimes mount the same world directory, and Minecraft takes an
    # exclusive lock on it. A leftover session.lock from a previous run makes
    # the next boot die with "DirectoryLock.create" long before any mod is
    # examined, which would look like a mod failure. Clearing it here keeps the
    # diagnosis honest: only real mod problems reach the culprit search.
    _clear_world_lock(root)
    res = launch(rt, root, timeout=timeout, mc=mc)
    log = verdict.read_log(Path(res.log_path))
    ok = res.outcome == Outcome.PASS
    return ok, log, res.detail


def _clear_world_lock(rt_dir: Path) -> None:
    """Remove a stale world lock left by a previous, cleanly-stopped run."""
    for lock in (rt_dir / "world" / "session.lock",
                 rt_dir / "shared-world" / "session.lock"):
        try:
            if lock.exists():
                lock.unlink()
        except OSError:
            pass


def isolate(rt: str, root: Path, mc: str, timeout: int = 420,
            max_rounds: int = 60) -> Isolation:
    """Boot the runtime, removing blamed jars until it starts.

    Two very different removal reasons are tracked separately, because only one
    of them is evidence of a broken project:

    * **Named** -- the loader pointed at a mod id in the log. That jar broke the
      instance and is reported as a failure.
    * **Split** -- nobody was named, so the search space was halved to make
      progress. Those jars are *unverified*, not guilty. At 90-jar scale a
      single unnamed crash would otherwise evict half the sample and, if those
      removals were reported as failures, manufacture a pass rate near 50% out
      of one crash. They go back on disk once the boot succeeds.

    Files that were removed are moved aside (not deleted) so a failure can
    still be explained after the fact.
    """
    mods_dir = (root / "plugins") if rt == "paper" else (root / "mods")
    quarantine = root / "quarantine"
    quarantine.mkdir(parents=True, exist_ok=True)
    res = Isolation(rounds=0)

    for _ in range(max_rounds):
        res.rounds += 1
        ok, log, detail = _boot(rt, root, mc, timeout)
        res.log, res.detail = log, detail
        if ok:
            restored = _restore_unverified(res=res, mods_dir=mods_dir,
                                           quarantine=quarantine)
            if restored:
                # The log we just captured was produced *without* those jars, so
                # it cannot speak for them. One more boot gives a log that
                # covers everything currently on disk, which is the only log the
                # per-project verdicts may be read from.
                ok2, log2, detail2 = _boot(rt, root, mc, timeout)
                res.rounds += 1
                res.log, res.detail = log2, detail2
                if not ok2:
                    # Restoring reintroduced the crash: keep the reduced set.
                    for name in restored:
                        src = mods_dir / name
                        if src.exists():
                            _evict(res, src, quarantine, named=False)
                        res.removed.remove(name)
                        res.unverified.append(name)
            res.booted = ok
            return res
        culprits = find_culprits(log)
        for c in culprits:
            if c not in res.blamed:
                res.blamed.append(c)
        # Evict exactly one jar per round. Evicting every id the log mentions
        # would take innocent mods down with the guilty one -- the loader often
        # names several ids while only one is actually fatal.
        jar = next((_jar_for_mod_id(mods_dir, c) for c in culprits
                    if _jar_for_mod_id(mods_dir, c)), None)
        if jar is not None:
            _evict(res, jar, quarantine, named=True)
            continue
        # Nobody is named: fall back to a binary split so one unnamed
        # crash cannot stall the run.
        jars = sorted(mods_dir.glob("*.jar"))
        if len(jars) < 2:
            return res
        half = len(jars) // 2
        for j in jars[half:]:
            _evict(res, j, quarantine, named=False)
        res.blamed.append(f"<binary split: removed {len(jars) - half}>")
    return res


def _evict(res: Isolation, jar: Path, quarantine: Path, *, named: bool) -> None:
    shutil.move(str(jar), str(quarantine / jar.name))
    res.removed.append(jar.name)
    if not named:
        res.unverified.append(jar.name)


def _restore_unverified(*, res: Isolation, mods_dir: Path,
                        quarantine: Path) -> list[str]:
    """Put split-removed jars back so the survivors' log is not their log.

    The successful boot happened *without* the unverified jars, so their fate is
    genuinely unknown. Leaving them out would quietly shrink the denominator in
    the project's favour; putting them back lets the next boot decide.

    Returns the names that were restored.
    """
    restored: list[str] = []
    for name in list(res.unverified):
        src = quarantine / name
        dst = mods_dir / name
        try:
            if src.exists() and not dst.exists():
                shutil.move(str(src), str(dst))
                res.removed.remove(name)
                restored.append(name)
        except OSError:
            continue
    res.unverified.clear()
    return restored


def restore(rt_dir: Path) -> int:
    """Move quarantined jars back into the runtime's mods/plugins folder.

    `rt_dir` is the runtime directory itself (e.g. `<instance>/neoforge`), the
    same value `isolate()` takes. Accepting the instance root here would create
    a nested `<root>/neoforge/mods` path and silently scatter the jars.
    """
    n = 0
    q = rt_dir / "quarantine"
    if not q.exists():
        return 0
    dest = rt_dir / ("plugins" if rt_dir.name == "paper" else "mods")
    dest.mkdir(parents=True, exist_ok=True)
    for f in q.glob("*.jar"):
        target = dest / f.name
        if target.exists():
            f.unlink()
        else:
            shutil.move(str(f), str(target))
        n += 1
    return n
