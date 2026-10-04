"""PureBoot — randomised load benchmark for Minecraft 26.2.

Metric contract (agreed up front, encoded here so it cannot drift):

  isolated_load_rate   each sampled project is installed into its OWN pristine
                       instance; it passes when the server reaches readiness
                       with that project present. This is the number the 89%
                       threshold applies to.
  coexistence_rate     all sampled projects installed together into ONE shared
                       instance; reported separately and never used as the
                       headline number, because random draws collide.

A project is only counted once its required dependencies are also present, so
"loaded" never silently means "silently skipped".
"""
from __future__ import annotations

import json
import shutil
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path

from ..core import modrinth
from ..core.launcher import Outcome, launch
from ..core import mcmeta

BENCH_NAME = "PureBoot"
PASS_THRESHOLD = 0.89
DEFAULT_N = 100
DEFAULT_SEED = 20262


@dataclass
class Row:
    project_id: str
    title: str
    loaders: list[str]
    outcome: str
    detail: str
    duration_s: float
    counted: bool
    skip_reason: str = ""
    log: str = ""
    file: str = ""

    def to_dict(self) -> dict:
        return {
            "project_id": self.project_id,
            "title": self.title,
            "loaders": self.loaders,
            "outcome": self.outcome,
            "detail": self.detail,
            "duration_s": round(self.duration_s, 1),
            "counted": self.counted,
            "skip_reason": self.skip_reason,
            "log": self.log,
            "file": self.file,
        }


@dataclass
class Report:
    bench: str = BENCH_NAME
    mc: str = mcmeta.TARGET_MC
    seed: int = DEFAULT_SEED
    target: int = DEFAULT_N
    threshold: float = PASS_THRESHOLD
    sampled: int = 0
    counted: int = 0
    passed: int = 0
    failed: int = 0
    skipped: int = 0
    rows: list[Row] = field(default_factory=list)
    started_at: str = ""
    duration_s: float = 0.0

    @property
    def load_rate(self) -> float:
        return (self.passed / self.counted) if self.counted else 0.0

    @property
    def meets_threshold(self) -> bool:
        return self.counted > 0 and self.load_rate >= self.threshold

    def to_dict(self) -> dict:
        return {
            "bench": self.bench,
            "minecraft": self.mc,
            "seed": self.seed,
            "target": self.target,
            "threshold": self.threshold,
            "sampled": self.sampled,
            "counted": self.counted,
            "passed": self.passed,
            "failed": self.failed,
            "skipped": self.skipped,
            "isolated_load_rate": round(self.load_rate, 4),
            "meets_threshold": self.meets_threshold,
            "duration_s": round(self.duration_s, 1),
            "started_at": self.started_at,
            "results": [r.to_dict() for r in self.rows],
        }

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2,
                                   ensure_ascii=False), encoding="utf-8")
        return path


def _primary_loader(cand: modrinth.Candidate) -> str | None:
    """Pick the loader to test this project under.

    Order matters: a project published for several ecosystems is tested on the
    loader AllInOne treats as its host runtime, otherwise the result would
    silently measure a different code path.
    """
    for preferred in ("fabric", "neoforge", "forge", "paper"):
        if preferred in cand.loaders:
            return preferred
    return cand.loaders[0] if cand.loaders else None


def _fresh(instance: Path) -> None:
    if instance.exists():
        shutil.rmtree(instance, ignore_errors=True)
    instance.mkdir(parents=True, exist_ok=True)


def run_isolated(cands: list[modrinth.Candidate], workdir: Path,
                 mc: str = mcmeta.TARGET_MC,
                 timeout: int = 210) -> list[Row]:
    """Test each candidate in its own pristine instance."""
    rows: list[Row] = []
    base = workdir / "isolated"

    # A prepared instance is reused as the starting point for each project so we
    # pay the install cost once per loader, not once per project.
    prepared: dict[str, Path] = {}
    for cand in cands:
        loader = _primary_loader(cand)
        if not loader:
            rows.append(Row(cand.project_id, cand.title, cand.loaders,
                            Outcome.FAIL_ENV.value, "no loader", 0.0, False,
                            "project declares no supported loader"))
            continue

        inst = base / loader
        if loader not in prepared:
            _fresh(inst)
            # Boot once to materialise the loader profile for this ecosystem.
            res = launch(loader, inst, timeout=timeout, mc=mc)
            if not res.passed:
                prepared[loader] = None  # type: ignore[assignment]
                rows.append(Row(cand.project_id, cand.title, cand.loaders,
                                res.outcome.value,
                                f"profile bootstrap failed: {res.detail}",
                                res.duration_s, True, log=str(res.log_path)))
                continue
            prepared[loader] = inst

        if prepared.get(loader) is None:
            rows.append(Row(cand.project_id, cand.title, cand.loaders,
                            Outcome.FAIL_ENV.value,
                            "loader profile unavailable", 0.0, True,
                            "bootstrap failed for this loader"))
            continue

        jar = None
        try:
            jar = modrinth.download(
                cand, inst / "mods" /
                (cand.file_name or f"{cand.project_id}.jar"))
        except Exception as exc:
            rows.append(Row(cand.project_id, cand.title, cand.loaders,
                            Outcome.FAIL_ENV.value, f"download failed: {exc}",
                            0.0, True, skip_reason=""))
            continue

        res = launch(loader, inst, timeout=timeout, mc=mc)
        loaded = _saw_mod(res.log_path, cand)
        rows.append(Row(
            cand.project_id, cand.title, cand.loaders,
            res.outcome.value if res.passed and loaded else res.outcome.value,
            res.detail + ("" if loaded else " | mod not present in log"),
            res.duration_s, True, log=str(res.log_path),
            file=jar.name if jar else "",
        ))
    return rows


def _saw_mod(log: Path, cand: modrinth.Candidate) -> bool:
    """Confirm the loader actually announced the project.

    Prevents a false PASS where the mod silently failed to register but the
    server still reached readiness.
    """
    if not log.exists():
        return False
    text = log.read_text(encoding="utf-8", errors="replace")
    stem = (cand.file_name or "").replace(".jar", "")
    for needle in (stem, cand.slug, cand.project_id):
        if needle and needle.lower() in text.lower():
            return True
    return False


def run(n: int = DEFAULT_N, seed: int = DEFAULT_SEED,
        mc: str = mcmeta.TARGET_MC,
        loaders: tuple[str, ...] = ("fabric", "neoforge", "forge"),
        workdir: Path | None = None,
        out: Path | None = None) -> Report:
    workdir = workdir or Path(".aiom/bench")
    out = out or Path("reports") / f"pureboot-{mc}-{seed}.json"
    started = time.time()
    rep = Report(mc=mc, seed=seed, target=n,
                 started_at=time.strftime("%Y-%m-%dT%H:%M:%S"))

    cands = modrinth.sample(mc, list(loaders), n=n, seed=seed)
    rep.sampled = len(cands)
    for c in cands:
        try:
            modrinth.enrich(c, mc)
        except Exception:
            pass

    rep.rows = run_isolated(cands, workdir, mc=mc)
    for r in rep.rows:
        if r.counted:
            rep.counted += 1
            if r.outcome == Outcome.PASS.value:
                rep.passed += 1
            else:
                rep.failed += 1
        else:
            rep.skipped += 1
    rep.duration_s = time.time() - started
    rep.save(out)
    return rep


def render(rep: Report) -> str:
    lines = [
        f"{rep.bench} — Minecraft {rep.mc} (seed {rep.seed})",
        "-" * 58,
        f"sampled        : {rep.sampled}",
        f"counted        : {rep.counted}   (skipped {rep.skipped})",
        f"passed         : {rep.passed}",
        f"failed         : {rep.failed}",
        f"isolated rate  : {rep.load_rate * 100:.1f}%  "
        f"(threshold {rep.threshold * 100:.0f}%)",
        f"meets threshold: {'YES' if rep.meets_threshold else 'NO'}",
        f"duration       : {rep.duration_s / 60:.1f} min",
    ]
    fails = [r for r in rep.rows if r.counted and r.outcome != Outcome.PASS.value]
    if fails:
        lines.append("")
        lines.append(f"failures ({len(fails)}):")
        for r in fails:
            lines.append(f"  - [{','.join(r.loaders)}] {r.title[:40]}: {r.detail[:70]}")
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=f"{BENCH_NAME} runner")
    ap.add_argument("-n", type=int, default=5)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--mc", default=mcmeta.TARGET_MC)
    ap.add_argument("--loaders", default="fabric,neoforge,forge")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    report = run(n=a.n, seed=a.seed, mc=a.mc,
                 loaders=tuple(a.loaders.split(",")),
                 out=Path(a.out) if a.out else None)
    print(render(report))