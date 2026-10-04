"""Measure the real coexistence constraints of the Minecraft 26.2 ecosystem.

The question this answers: if PureBoot draws 100 random Modrinth projects
for MC 26.2 and tries to load every one of them *together*, what share can
physically succeed?

Three measurable factors decide the ceiling:

1. **Dependency closure** -- a project with a required dependency outside the
   sample cannot load. The question is how deep the closure runs.
2. **Side compatibility** -- a client-only mod has nothing to attach to on a
   dedicated server, and a server-only plugin has no loader on the client.
3. **Loader exclusivity** -- Fabric and Forge/NeoForge rewrite the same vanilla
   classes through incompatible transformations.

Everything here is measured from live Modrinth data, not assumed.
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiom.core.http import fetch_json  # noqa: E402
from aiom.core.modrinth import API, sample  # noqa: E402

MC = "26.2"
SEED = 20262
N = 100


def loader_of(c) -> str:
    """The single loader a project is tested under (first declared)."""
    for l in ("fabric", "neoforge", "forge", "paper"):
        if l in c.loaders:
            return l
    return c.loaders[0] if c.loaders else "unknown"


def fetch_versions(pid: str) -> list[dict]:
    try:
        return fetch_json(f"{API}/project/{pid}/version", timeout=60)
    except Exception:
        return []


def analyse(c) -> dict:
    """Enrich one candidate with the fields that decide loadability."""
    versions = fetch_versions(c.project_id)
    target = [v for v in versions if MC in v.get("game_versions", [])]
    if not target:
        return {"slug": c.slug, "ok": False, "why": "no 26.2 file"}

    files = target[0]
    required = [d for d in files.get("dependencies", [])
                if d.get("dependency_type") == "required"]
    optional = [d for d in files.get("dependencies", [])
                if d.get("dependency_type") == "optional"]
    incompatible = [d for d in files.get("dependencies", [])
                    if d.get("dependency_type") == "incompatible"]

    loaders = set(files.get("loaders", [])) or set(c.loaders)
    return {
        "slug": c.slug,
        "ok": True,
        "type": c.project_type,
        "loaders": sorted(loaders),
        "client_side": files.get("client_side", "required"),
        "server_side": files.get("server_side", "required"),
        "n_required": len(required),
        "n_optional": len(optional),
        "n_incompatible": len(incompatible),
        "required_ids": [d.get("project_id") or d.get("slug")
                         for d in required],
        "downloads": c.downloads,
    }


def main() -> int:
    print(f"生态共存约束分析  MC {MC}  seed {SEED}  n={N}\n" + "=" * 60)

    print("[1/4] 抽样 Modrinth ...")
    picked = sample(MC, ["fabric", "neoforge", "forge", "paper"], n=N, seed=SEED)
    print(f"      抽到 {len(picked)} 个项目")

    print("[2/4] 拉取版本与依赖元数据（并发）...")
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = list(pool.map(analyse, picked))
    rows = [r for r in rows if r["ok"]]
    print(f"      {len(rows)} 个有 26.2 构建")

    # --- factor 1: dependency closure -------------------------------------
    print("\n[3/4] 依赖闭包")
    ids = {r["slug"] for r in rows}
    dep_free = [r for r in rows if r["n_required"] == 0]
    in_sample = [r for r in rows
                 if r["n_required"] and all(d in ids for d in r["required_ids"])]
    ext_dep = [r for r in rows
               if r["n_required"] and not all(d in ids for d in r["required_ids"])]
    print(f"      无必选依赖      : {len(dep_free):3d}  ({len(dep_free)/len(rows):.1%})")
    print(f"      依赖全在样本内  : {len(in_sample):3d}  ({len(in_sample)/len(rows):.1%})")
    print(f"      依赖在样本外    : {len(ext_dep):3d}  ({len(ext_dep)/len(rows):.1%})")
    total_deps = sum(r["n_required"] for r in rows)
    print(f"      必选依赖总边数  : {total_deps}")

    # --- factor 2: side compatibility -------------------------------------
    print("\n[4/4] 端侧兼容性")
    cs = Counter(r["client_side"] for r in rows)
    ss = Counter(r["server_side"] for r in rows)
    print(f"      client_side: {dict(cs)}")
    print(f"      server_side: {dict(ss)}")
    client_only = [r for r in rows if r["server_side"] == "unsupported"]
    both = [r for r in rows
            if r["client_side"] != "unsupported" and r["server_side"] != "unsupported"]
    print(f"      纯客户端(服务端不支持): {len(client_only)}")
    print(f"      双端可加载            : {len(both)}  ({len(both)/len(rows):.1%})")

    # --- factor 3: loader mix ---------------------------------------------
    print("\n加载器分布（单项目声明）")
    ld = Counter()
    for r in rows:
        for l in r["loaders"]:
            ld[l] += 1
    for k, v in ld.most_common():
        print(f"      {k:10s}: {v}")

    out = {
        "mc": MC, "seed": SEED, "n": len(rows),
        "dep_free": len(dep_free),
        "deps_inside": len(in_sample),
        "deps_outside": len(ext_dep),
        "total_required_edges": total_deps,
        "both_sides": len(both),
        "client_only": len(client_only),
        "loader_hist": dict(ld),
        "rows": rows,
    }
    dest = Path(__file__).resolve().parents[1] / "reports" / f"eco-{MC}-{SEED}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
