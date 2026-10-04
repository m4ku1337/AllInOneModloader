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
    environment: str = "unknown"


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
    client_only: int = 0
    rows: list[Row] = field(default_factory=list)
    runtime_results: dict = field(default_factory=dict)
    duration_s: float = 0.0
    started_at: str = ""

    @property
    def eligible(self) -> int:
        """Projects the benchmark actually judges.

        A project Modrinth tags ``client_only`` states that no server can run
        it. Counting those as failures would measure Modrinth's tagging, not
        the loader, so they are reported separately and left out of the
        denominator.
        """
        return sum(1 for r in self.rows if r.counted)

    @property
    def rate(self) -> float:
        return self.passed / self.eligible if self.eligible else 0.0

    @property
    def meets(self) -> bool:
        return self.eligible > 0 and self.rate >= self.threshold

    def to_dict(self) -> dict:
        return {
            "minecraft": self.mc, "seed": self.seed, "target": self.target,
            "threshold": self.threshold,
            "sampled": self.sampled, "eligible": self.eligible,
            "roots": self.roots,
            "closure_nodes": self.closure, "installed": self.installed,
            "passed": self.passed, "failed": self.failed,
            "unplaceable": self.unplaceable,
            "client_only": self.client_only,
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
        types = c.project_types or [c.project_type]
        out.append((c.project_id, c.slug, c.title, c.project_type, types))
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
    by_id = {r.project_id: r for r in resolved}

    # Build the row set before anything touches the disk: every sampled project
    # is reported, even ones that never make it onto a disk, so the report is a
    # faithful account of the draw.
    rows: list[Row] = []
    # Note the loop variable: `root` is already the instance path in this
    # function, and shadowing it here made `inst_mod.build(root, mc)` receive a
    # tuple instead of a Path.
    for i, entry in enumerate(roots):
        pid, slug, title, ptype = entry[0], entry[1], entry[2], entry[3]
        r = by_id.get(pid)
        if r is None:
            rows.append(Row(i, slug, title, ptype, "", "", "", "",
                            "fail", "could not resolve a 26.2 build"))
        elif r.environment == "client_only":
            # Author-declared: no server runtime can host this. Reported in
            # full, but excluded from the denominator -- counting it would
            # measure Modrinth's tagging rather than the loader.
            rows.append(Row(i, slug, title, ptype, r.version_number, "", "",
                            r.filename, "skipped",
                            "Modrinth marks this 26.2 build client_only; "
                            "no server loader can host it",
                            counted=False, environment=r.environment))
        elif not r.placeable:
            rows.append(Row(i, slug, title, ptype, r.version_number, "", "",
                            r.filename, "fail", r.reason or "not placeable",
                            environment=r.environment))
        else:
            rows.append(Row(i, slug, title, ptype, r.version_number, r.host,
                            r.chosen_loader, r.filename, size=r.size,
                            environment=r.environment))
    rep.sampled = len(rows)
    rep.client_only = sum(1 for r in rows if r.outcome == "skipped")
    rep.unplaceable = sum(1 for r in rows
                          if r.outcome == "fail" and r.environment != "client_only"
                          and not r.host)

    # Nothing client-side may reach a mods or plugins directory. Dependency
    # nodes are filtered too: a client-only library breaks its dependents just
    # as thoroughly as it breaks itself.
    resolved = [r for r in resolved if r.environment != "client_only"]
    rep.closure = len(resolved)
    print(f"      闭包 {len(resolved)} 个节点（含依赖，"
          f"已剔除 {rep.client_only} 个 client_only）")

    print("[3/6] 准备实例 ...")
    info = inst_mod.build(root, mc)
    print(f"      实例就绪: {info['root']}")

    print("[4/6] 下载并安装到对应运行时 ...")
    placed = inst_mod.install(resolved, root)
    rep.installed = placed
    print(f"      neoforge={placed['neoforge']} "
          f"paper={placed['paper']} failed={placed['failed']}")

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
            "blamed": iso.blamed, "unverified": iso.unverified,
            "log": iso.log,
        }
        print(f"      {rt}: booted={iso.booted} rounds={iso.rounds} "
              f"guilty={len(iso.guilty)} unverified={len(iso.unverified)} "
              f"blamed={','.join(iso.blamed) or '-'}")

        for row in rows:
            if row.host != rt:
                continue
            fname = Path(row.file).name
            # Only jars the loader named are failures. A jar dropped by the
            # binary split was never proven guilty, and at 90-jar scale one
            # unnamed crash would otherwise take half the sample down with it.
            if fname in set(iso.guilty):
                row.outcome = "fail"
                row.reason = ("broke the shared instance and was named by the "
                              "loader: " + ",".join(iso.blamed)[:120])
                continue
            if row.outcome == "fail":
                continue
            # The jar on disk is the only reliable source of the mod id; the
            # file name disagrees with it often enough to matter (jei).
            jar_path = rt_dir / ("plugins" if rt == "paper" else "mods") / fname
            v = verdict.judge(log, row.slug, row.file, rt,
                              str(jar_path) if jar_path.exists() else "")
            row.outcome = "pass" if v.passed else "fail"
            row.reason = v.reason
            row.evidence = v.evidence

    # A project that loaded as a dependency but was not sampled still counts
    # toward the closure, never toward the headline rate. `skipped` rows are
    # reported but excluded, so only judged projects move the counters.
    for row in rows:
        if not row.counted:
            continue
        if row.outcome == "pass":
            rep.passed += 1
        else:
            rep.failed += 1

    print("[6/6] 统计 ...")
    rep.rows = rows
    rep.duration_s = time.time() - t0
    rep.save(out)
    print(f"\n混合共存通过率: {rep.rate * 100:.1f}%  "
          f"({rep.passed}/{rep.eligible})  阈值 {THRESHOLD * 100:.0f}%  "
          f"{'达标' if rep.meets else '未达标'}")
    print(f"已报告 {rep.sampled} 个项目，其中 client_only 跳过 "
          f"{rep.client_only} 个，无法归位 {rep.unplaceable} 个")
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
