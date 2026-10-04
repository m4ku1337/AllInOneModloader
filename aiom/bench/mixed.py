"""Mixed-instance benchmark: sample 100 Modrinth projects, load them together.

This is the run the whole project exists to produce. Unlike the earlier
isolated benchmark, every project is installed into ONE shared instance
directory and the runtimes are booted with the full set in place, so the number
reported is a genuine coexistence figure.

A project counts as passed only when the loader both reached readiness *and*
announced that project. See aiom.core.verdict for why the second half matters:
a NeoForge instance will happily reach readiness while silently skipping every
Fabric jar it was handed.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path

from ..core import isolate, mcmeta, modrinth, placement, verdict
from ..core.launcher import launch
from .. import instance as inst_mod

MC = mcmeta.TARGET_MC
THRESHOLD = 0.89
SEED = 20262


@dataclass
class Row:
    index: int
    slug: str
    title: str
    project_type: str
    version: str
    host: str
    chosen_loader: str
    file: str
    outcome: str = "pending"
    reason: str = ""
    evidence: str = ""
    counted: bool = True
    in_sample: bool = True
    size: int = 0


@dataclass
class MixedReport:
    mc: str = MC
    seed: int = SEED
    target: int = 100
    threshold: float = THRESHOLD
    sampled: int = 0
    roots: int = 0
    closure: int = 0
    installed: dict = field(default_factory=dict)
    passed: int = 0
    failed: int = 0
    unplaceable: int = 0
    rows: list[Row] = field(default_factory=list)
    runtime_results: dict = field(default_factory=dict)
    duration_s: float = 0.0
    started_at: str = ""

    @property
    def rate(self) -> float:
        return self.passed / self.sampled if self.sampled else 0.0

    @property
    def meets(self) -> bool:
        return self.sampled > 0 and self.rate >= self.threshold

    def to_dict(self) -> dict:
        return {
            "minecraft": self.mc, "seed": self.seed, "target": self.target,
            "threshold": self.threshold,
            "sampled": self.sampled, "roots": self.roots,
            "closure_nodes": self.closure, "installed": self.installed,
            "passed": self.passed, "failed": self.failed,
            "unplaceable": self.unplaceable,
            "mixed_load_rate": round(self.rate, 4),
            "meets_threshold": self.meets,
            "runtime_results": self.runtime_results,
            "duration_s": round(self.duration_s, 1),
            "started_at": self.started_at,
            "results": [asdict(r) for r in self.rows],
        }

    def save(self, p: Path) -> Path:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                     encoding="utf-8")
        return p


def sample_roots(mc: str, n: int, seed: int) -> list[tuple]:
    """Draw the sample and enrich each project with its 26.2 files."""
    cands = modrinth.sample(mc, ["neoforge", "forge", "fabric", "paper"],
                            n=n, seed=seed)
    out = []
    for c in cands:
        out.append((c.project_id, c.slug, c.title, c.project_type))
    return out


def run(n: int = 100, seed: int = SEED, mc: str = MC,
        root: Path | None = None,
        out: Path | None = None) -> MixedReport:
    root = (root or Path(".aiom/instance")).resolve()
    out = out or Path("reports") / f"mixed-{mc}-{seed}.json"
    t0 = time.time()
    rep = MixedReport(seed=seed, target=n,
                      started_at=time.strftime("%Y-%m-%dT%H:%M:%S"))

    print("=" * 64)
    print(f"AllInOne 混合实例基准  MC {mc}  seed {seed}  n={n}")
    print("=" * 64)

    print("[1/6] 随机抽样 Modrinth ...")
    roots = sample_roots(mc, n, seed)
    rep.roots = len(roots)
    print(f"      抽到 {len(roots)} 个项目")

    print("[2/6] 解析依赖闭包与生态归位 ...")
    resolved = placement.closure(roots, mc=mc)
    rep.closure = len(resolved)
    by_id = {r.project_id: r for r in resolved}
    print(f"      闭包 {len(resolved)} 个节点（含依赖）")

    print("[3/6] 准备实例 ...")
    info = inst_mod.build(root, mc)
    print(f"      实例就绪: {info['root']}")

    print("[4/6] 下载并安装到对应运行时 ...")
    placed = inst_mod.install(resolved, root)
    rep.installed = placed
    print(f"      neoforge={placed['neoforge']} "
          f"paper={placed['paper']} failed={placed['failed']}")

    # Build the row set: every sampled project is reported, even if it never
    # made it onto disk, so the denominator stays honest.
    rows: list[Row] = []
    for i, (pid, slug, title, ptype) in enumerate(roots):
        r = by_id.get(pid)
        if r is None:
            rows.append(Row(i, slug, title, ptype, "", "", "", "",
                            "fail", "could not resolve a 26.2 build"))
        elif not r.placeable:
            rep.unplaceable += 1
            rows.append(Row(i, slug, title, ptype, r.version_number, "", "",
                            r.filename, "fail", r.reason or "not placeable"))
        else:
            rows.append(Row(i, slug, title, ptype, r.version_number, r.host,
                            r.chosen_loader, r.filename, size=r.size))
    rep.sampled = len(rows)

    print("[5/6] 启动各运行时并判定 ...")
    for rt in ("neoforge", "paper"):
        # Each runtime lives in its own subdirectory of the instance root.
        # Passing `root` here would make the launcher and the isolation
        # bisector look at a directory that holds no mods at all.
        rt_dir = root / rt
        # A single bad jar kills the whole instance, which would make every
        # project look broken. Bisect the set instead so each project's fate
        # stays attributable.
        iso = isolate.isolate(rt, rt_dir, mc, timeout=420)
        # IsolationResult.log already holds the log *text*; reading it again as
        # a path is what made every project fail with "log missing or empty".
        log = iso.log or ""
        rep.runtime_results[rt] = {
            "booted": iso.booted, "detail": iso.detail,
            "rounds": iso.rounds, "removed": iso.removed,
            "blamed": iso.blamed, "log": iso.log,
        }
        print(f"      {rt}: booted={iso.booted} rounds={iso.rounds} "
              f"removed={len(iso.removed)} blamed={','.join(iso.blamed) or '-'}")

        for row in rows:
            if row.host != rt:
                continue
            fname = Path(row.file).name
            if fname in iso.removed:
                row.outcome = "fail"
                row.reason = ("broke the shared instance and was isolated: "
                              + ",".join(iso.blamed)[:120])
                continue
            if row.outcome == "fail":
                continue
            v = verdict.judge(log, row.slug, row.file, rt)
            row.outcome = "pass" if v.passed else "fail"
            row.reason = v.reason
            row.evidence = v.evidence

    # A project that loaded as a dependency but was not sampled still counts
    # toward the closure, never toward the headline rate.
    for row in rows:
        if row.outcome == "pass":
            rep.passed += 1
        else:
            rep.failed += 1

    print("[6/6] 统计 ...")
    rep.rows = rows
    rep.duration_s = time.time() - t0
    rep.save(out)
    print(f"\n混合共存通过率: {rep.rate * 100:.1f}%  "
          f"({rep.passed}/{rep.sampled})  阈值 {THRESHOLD * 100:.0f}  "
          f"{'达标' if rep.meets else '未达标'}")
    print(f"报告: {out}")
    return rep


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="AllInOne mixed-instance bench")
    ap.add_argument("-n", type=int, default=100)
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--root", default=".aiom/instance")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()
    run(n=a.n, seed=a.seed, root=Path(a.root),
        out=Path(a.out) if a.out else None)
