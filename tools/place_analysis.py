"""Decisive measurement: can every sampled project be *placed* somewhere?

The first analysis showed 54% of the 100 sampled projects declare a required
dependency outside the sample -- but that is a solvable problem, not a wall: a
dependency resolver simply installs the closure. So dependency closure was
never the real ceiling.

The decisive question is different, and it is a *placement* problem rather than
a *conflict* problem: a project published for several ecosystems can be loaded
under any of them. So the only projects that can be structurally homeless are
**single-ecosystem** ones whose sole ecosystem cannot share a runtime with the
others.

This script measures exactly that, plus the real dependency-closure size.
"""
from __future__ import annotations

import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from aiom.core.http import fetch_json  # noqa: E402
from aiom.core.modrinth import API, sample  # noqa: E402

MC = "26.2"
SEED = 20262
N = 100

# AllInOne runtime families. Quilt/Legacy-Fabric/Ornithe are Fabric-API-compatible
# or Fabric forks; Purpur/Folia/Spigot/Bukkit are Paper-API-compatible.
FAMILY = {
    "fabric": "fabric", "quilt": "fabric", "legacy-fabric": "fabric",
    "ornithe": "fabric", "rift": "fabric", "modloader": "fabric",
    "liteloader": "fabric", "nilloader": "fabric",
    "neoforge": "neoforge", "forge": "neoforge",
    "paper": "paper", "purpur": "paper", "spigot": "paper",
    "bukkit": "paper", "folia": "paper", "babric": "paper", "bta-babric": "paper",
    "sponge": "sponge", "waterfall": "sponge", "velocity": "sponge",
    "bungeecord": "sponge",
}
# Families whose runtime is genuinely separate from the mod-loader families.
RUNTIME_FAMILY = {"fabric": "mod", "neoforge": "mod", "paper": "server",
                  "sponge": "proxy"}


def families_of(loaders: set[str]) -> set[str]:
    return {FAMILY[l] for l in loaders if l in FAMILY}


def fetch(pid: str) -> list[dict]:
    try:
        return fetch_json(f"{API}/project/{pid}/version", timeout=60)
    except Exception:
        return []


def detail(c) -> dict | None:
    vs = [v for v in fetch(c.project_id) if MC in v.get("game_versions", [])]
    if not vs:
        return None
    v = vs[0]
    loaders = set(v.get("loaders", [])) or set(c.loaders)
    req = [d.get("project_id") or d.get("slug")
           for d in v.get("dependencies", [])
           if d.get("dependency_type") == "required"]
    return {
        "slug": c.slug,
        "id": c.project_id,
        "title": c.title,
        "type": c.project_type,
        "loaders": sorted(loaders),
        "families": sorted(families_of(loaders)),
        "client_side": v.get("client_side"),
        "server_side": v.get("server_side"),
        "required": req,
    }


def main() -> int:
    print(f"可放置性分析  MC {MC}  seed {SEED}  n={N}\n" + "=" * 62)
    picked = sample(MC, ["fabric", "neoforge", "forge", "paper"],
                    n=N, seed=SEED)
    with ThreadPoolExecutor(max_workers=8) as pool:
        rows = [r for r in pool.map(detail, picked) if r]
    print(f"有效项目: {len(rows)}\n")

    # --- 1. single vs multi ecosystem -------------------------------------
    print("[1] 生态归属（能否自由选择运行时）")
    single = [r for r in rows if len(r["families"]) == 1]
    multi = [r for r in rows if len(r["families"]) > 1]
    print(f"    单一生态   : {len(single):3d}  ({len(single)/len(rows):.1%})")
    print(f"    多生态可选 : {len(multi):3d}  ({len(multi)/len(rows):.1%})")
    print("    单一生态明细:")
    for k, v in Counter(r["families"][0] for r in single).most_common():
        print(f"      {k:10s}: {v}")

    # --- 2. runtime family spread -----------------------------------------
    print("\n[2] 运行时家族分布")
    fam = Counter()
    for r in rows:
        for f in r["families"]:
            fam[f] += 1
    for k, v in fam.most_common():
        print(f"    {k:10s}: {v:3d}  ({v/len(rows):.1%})")

    # --- 3. true dependency closure size -----------------------------------
    print("\n[3] 依赖闭包真实规模")
    known = {r["id"] for r in rows} | {r["slug"] for r in rows}
    ids = {r["id"]: r for r in rows}
    need_more: dict[str, str] = {}
    for r in rows:
        for d in r["required"]:
            if d not in known:
                need_more[d] = r["slug"]

    fetched_deps = 0
    if need_more:
        with ThreadPoolExecutor(max_workers=8) as pool:
            extra = list(pool.map(lambda d: (d, fetch(d)), list(need_more)))
        for d, vs in extra:
            fetched_deps += 1
            hit = [v for v in vs if MC in v.get("game_versions", [])]
            ids[d] = {
                "slug": d, "id": d, "title": d, "type": "mod",
                "families": sorted(families_of(set(hit[0].get("loaders", [])))) if hit else [],
                "required": [x.get("project_id") or x.get("slug")
                             for x in (hit[0].get("dependencies", []) if hit else [])
                             if x.get("dependency_type") == "required"],
            }
    all_nodes = list(ids.values())
    total_req = sum(len(r["required"]) for r in all_nodes)
    print(f"    样本内项目       : {len(rows)}")
    print(f"    需额外拉取的依赖 : {len(need_more)}  (26.2 可用 {fetched_deps})")
    print(f"    闭包总节点       : {len(all_nodes)}")
    print(f"    闭包总边数       : {total_req}")
    unresolved = [r["slug"] for r in all_nodes
                  if any(d not in ids for d in r["required"])]
    print(f"    无法解析的依赖   : {len(unresolved)}")

    # --- 4. the decisive number -------------------------------------------
    print("\n[4] 决定性指标：可被某个运行时收容的比例")
    # A project is placeable if its family set intersects at least one runtime
    # we can host. Projects with an empty family set (datapack/java-agent/...)
    # are not code and are excluded from the code-load denominator.
    code = [r for r in all_nodes if r["families"]]
    placeable = [r for r in code if set(r["families"]) & {"fabric", "neoforge", "paper"}]
    unplaceable = [r for r in code if not set(r["families"]) & {"fabric", "neoforge", "paper"}]
    print(f"    代码类节点       : {len(code)}")
    print(f"    可被宿主持有     : {len(placeable)}  ({len(placeable)/len(code):.2%})")
    print(f"    无可用宿主       : {len(unplaceable)}")
    for r in unplaceable[:10]:
        print(f"      - {r['slug']}: {r['families']}")

    out = {
        "mc": MC, "seed": SEED, "n": len(rows),
        "single_family": len(single), "multi_family": len(multi),
        "family_hist": dict(fam),
        "closure_nodes": len(all_nodes), "closure_edges": total_req,
        "extra_deps_pulled": len(need_more),
        "unresolved_dep_nodes": len(unresolved),
        "code_nodes": len(code), "placeable": len(placeable),
        "placeable_rate": round(len(placeable) / max(len(code), 1), 4),
        "unplaceable": [r["slug"] for r in unplaceable],
    }
    dest = Path(__file__).resolve().parents[1] / "reports" / f"place-{MC}-{SEED}.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {dest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
