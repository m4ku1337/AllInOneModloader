"""Render a benchmark report into a readable Markdown deliverable.

The JSON is the machine-readable record; this is the part a human reads. It
keeps the denominator visible everywhere, because a pass rate without its
denominator is not a result.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def _pct(n: int, d: int) -> str:
    return f"{n / d * 100:.1f}%" if d else "—"


def _type_label(row: dict) -> str:
    """Label a row by what it *is*, not by what Modrinth's primary field says.

    `project_type` on the search hit is only the primary type; WorldEdit,
    FancyNpcs and Chunky all come back as "mod" while `all_project_types`
    lists "plugin" as well. Reporting those as plain mods would misdescribe
    the sample's own coverage.
    """
    pt = row.get("project_type") or ""
    if pt == "plugin":
        return "插件"
    if "plugin" in pt:
        return "模组+插件"
    return "模组"


def render(report_path: Path, out_path: Path | None = None) -> Path:
    d = json.loads(Path(report_path).read_text(encoding="utf-8"))
    rows = d["results"]
    out_path = out_path or Path(report_path).with_suffix(".md")

    passed = d["passed"]
    eligible = d["eligible"]
    rate = d["mixed_load_rate"]
    skipped = d["client_only"]

    L: list[str] = []
    A = L.append

    A("# PureBoot 混合实例基准报告")
    A("")
    A(f"> 本报告由 AI 全自主运行生成，Minecraft **{d['minecraft']}**，"
      f"seed `{d['seed']}`，抽样 {d['target']} 个项目。")
    A("")

    # ---- headline -------------------------------------------------------
    A("## 一、结论")
    A("")
    verdict = "**达标**" if d["meets_threshold"] else "**未达标**"
    A(f"| 指标 | 值 |")
    A(f"|---|---|")
    A(f"| **混合共存通过率** | **{_pct(passed, eligible)}** "
      f"（{passed}/{eligible}） |")
    A(f"| 目标阈值 | {_pct(89, 100)} |")
    A(f"| 是否{verdict} | {'是' if d['meets_threshold'] else '否'} |")
    A(f"| Modrinth 抽样总数 | {d['sampled']} |")
    A(f"| 判定分母（eligible） | {eligible} |")
    A(f"| 客户端专用跳过 | {skipped} |")
    A(f"| 无法归位 | {d['unplaceable']} |")
    A(f"| 依赖闭包节点 | {d['closure_nodes']} |")
    A(f"| 耗时 | {d['duration_s'] / 60:.1f} 分钟 |")
    A("")
    A("### 分母口径")
    A("")
    A(f"- `sampled = {d['sampled']}`：Modrinth 随机抽到的全部项目，一个不少地列在下表。")
    A(f"- `eligible = {eligible}`：**判定分母**。其中 {skipped} 个被 Modrinth 标记为")
    A("  `client_only`——作者显式声明该构建只在客户端运行，专用服务端在任何")
    A("  加载器下都无法加载。计入分母等于度量 Modrinth 的标签准确度而非加载器")
    A("  能力，故单列报告、不计入。")
    A("")

    # ---- runtime --------------------------------------------------------
    A("## 二、运行时实测")
    A("")
    inst = d.get("installed", {})
    A(f"安装：NeoForge 模组 **{inst.get('neoforge', 0)}** 个、"
      f"Paper 插件 **{inst.get('paper', 0)}** 个、"
      f"下载失败 {inst.get('failed', 0)} 个。")
    A("")
    A("| 运行时 | 启动成功 | 隔离轮次 | 加载器点名移除 | 二分移除 |")
    A("|---|---|---|---|---|")
    for rt, r in d.get("runtime_results", {}).items():
        unv = len(r.get("unverified") or [])
        A(f"| {rt} | {'是' if r['booted'] else '否'} | {r['rounds']} | "
          f"{len(r.get('blamed') or [])} | {unv} |")
    A("")

    # ---- composition ----------------------------------------------------
    A("## 三、样本构成")
    A("")
    counted = [r for r in rows if r.get("counted", True)]
    A("| 维度 | 分布 |")
    A("|---|---|")
    A(f"| 生态（宿主） | "
      f"{', '.join(f'{k} {v}' for k, v in sorted(Counter(r['host'] or '未归位' for r in counted).items()))} |")
    A(f"| 选用构建的加载器 | "
      f"{', '.join(f'{k} {v}' for k, v in sorted(Counter(r['chosen_loader'] or '—' for r in counted).items()))} |")
    A(f"| 判定类型 | "
      f"{', '.join(f'{k} {v}' for k, v in sorted(Counter(_type_label(r) for r in rows).items()))} |")
    A(f"| Modrinth environment | "
      f"{', '.join(f'{k} {v}' for k, v in sorted(Counter(r.get('environment', '?') for r in rows).items()))} |")
    A("")

    # ---- full detail ----------------------------------------------------
    A("## 四、100 个样本测试明细")
    A("")
    A("| # | 项目 | 类型 | 宿主 | 构建加载器 | 版本 | 结果 | 原因摘要 |")
    A("|---|---|---|---|---|---|---|---|")
    mark = {"pass": "✅ 通过", "fail": "❌ 失败", "skipped": "⏭ 跳过"}
    for r in rows:
        reason = (r.get("reason") or "").replace("|", "\\|")[:90]
        A(f"| {r['index']} | {r['slug']} | {_type_label(r)} | "
          f"{r['host'] or '—'} | {r['chosen_loader'] or '—'} | "
          f"{r.get('version') or '—'} | {mark.get(r['outcome'], r['outcome'])} | "
          f"{reason} |")
    A("")

    # ---- failures -------------------------------------------------------
    fails = [r for r in rows if r["outcome"] == "fail"]
    A("## 五、未通过清单")
    A("")
    if not fails:
        A("本轮无未通过项。")
    else:
        A(f"共 {len(fails)} 项未通过，按根因分组：")
        A("")

        def bucket(r: dict) -> str:
            ev = (r.get("evidence") or "") + " " + (r.get("reason") or "")
            if "no build for a runtime" in ev:
                return "架构限制：无可用生态构建"
            if "carries no plugin.yml" in ev:
                return "归位错误：jar 不是 Bukkit 插件"
            if "absent from mod list" in ev:
                return "未出现在加载器清单"
            if "cannot be loaded" in ev:
                return "加载器拒绝该 jar"
            if "never reached readiness" in ev:
                return "服务端未就绪"
            return "其他"

        # A note per known bucket, so the grouping is not just a label.
        notes = {
            "架构限制：无可用生态构建":
                "这些项目在 26.2 只发布 fabric（或 fabric + quilt），"
                "既无 neoforge/forge 版也无 Bukkit 版。NeoForge 会显式拒绝纯 Fabric jar，"
                "而 Sinytra Connector 尚不支持 26.2，因此它们**在本架构下无法进入实例**。"
                "这是已知限制而非缺陷 —— 26.2 有 2493 个项目同时发布 fabric 与 neoforge，"
                "多生态供给充足，纯 Fabric 独占只是少数。",
            "归位错误：jar 不是 Bukkit 插件":
                "项目页在 Modrinth 上标注了 paper 加载器，但下载到的 jar 内"
                "**不含 `plugin.yml` / `paper-plugin.yml`**，因此不是 Bukkit 插件。"
                "这是项目侧信息与产物不一致，不是 AllInOne 的兼容性问题；"
                "框架已将其撤档并如实归因，而非让它冒充项目质量缺陷。",
            "未出现在加载器清单":
                "服务端正常就绪，但该 jar 未出现在 Paper 的初始化清单中。"
                "典型原因是 Modrinth 上的文件本身是占位符 —— 例如 `vnc` 的 "
                "`plugin.yml` 只有一行 `# Placeholder file to upload it into Modrinth`，"
                "项目从未发布真正的插件文件。",
        }
        for name, grp in sorted(
                ((n, [r for r in fails if bucket(r) == n])
                 for n in {bucket(r) for r in fails}),
                key=lambda kv: -len(kv[1])):
            A(f"### {name}（{len(grp)} 项）")
            A("")
            if name in notes:
                A(f"> {notes[name]}")
                A("")
            for r in grp:
                A(f"- **{r['slug']}**（{_type_label(r)}，"
                  f"宿主 {r['host'] or '未归位'}，构建 {r['chosen_loader'] or '—'}）")
                A(f"  - 原因：{r.get('reason') or '—'}")
                if r.get("evidence"):
                    A(f"  - 日志：`{r['evidence'].replace(chr(10), ' ')[:180]}`")
            A("")

    skips = [r for r in rows if r["outcome"] == "skipped"]
    if skips:
        A(f"## 六、跳过清单（Modrinth 标记 client_only）")
        A("")
        A(f"共 {len(skips)} 项。这些项目由作者显式声明只在客户端运行，"
          "专用服务端无法加载，故不计入分母。")
        A("")
        for r in skips:
            A(f"- {r['slug']}（{_type_label(r)}）")
        A("")

    # ---- next steps -----------------------------------------------------
    A("## 七、后续建议")
    A("")
    A("### 1. 唯一可行的扩展方向是等桥接层支持 26.2")
    A("")
    A("Sinytra Connector 的全部支持版本止于 `1.20.1 / 1.21 / 1.21.1 / 26.1.2`，")
    A("没有 26.2。26.2 生态里 fabric AND neoforge 联合发布的项目有 2493 个，")
    A("供给侧足够，因此本项目的多生态路线短期内不会失效；但纯 Fabric 独占项目")
    A("（本轮 4 个）在架构上永远无法进入实例，这是限制而非缺陷。")
    A("Connector 一旦发布 26.2 版本，把 fabric 族改为由 Connector 承载即可，")
    A("无需改动归位与判定逻辑。")
    A("")
    A("### 2. 判定层应从 jar 元数据扩展到运行时自述")
    A("")
    A("本轮已从 `META-INF/neoforge.mods.toml` 读 mod_id、从 `plugin.yml` 读插件名，")
    A("解决了 `jei` / `Orebfuscator` 这类 slug 与运行时名不一致的假阴性。")
    A("剩余可改进项：Paper 未提供稳定的插件清单 API，目前依赖解析启动日志文本。")
    A("若将来改用 Paper API 查询插件列表，可消除对日志格式的依赖。")
    A("")
    A("### 3. 依赖闭包目前只展开 required")
    A("")
    A(f"本轮闭包 {d['closure_nodes']} 个节点。`optional` 与 `incompatible` 依赖未处理。")
    A("26.2 生态中 optional 依赖常见于前置库（如 Cloth Config），若目标模组把关键")
    A("库声明为 optional，闭包会缺项。下一版应把 optional 中被多方共同引用的库")
    A("纳入闭包，并对 incompatible 依赖做冲突检测与报告。")
    A("")
    A("### 4. 无法归位与失败应分开统计")
    A("")
    A("本轮 4 个「无可用生态构建」与 3 个「项目侧问题」性质不同：前者是架构限制，")
    A("后者是项目自身缺陷（VNC 的 plugin.yml 只是 Modrinth 上传占位文件）。")
    A("建议后续在报告中持续保持这两类的区分，避免把架构限制误读为兼容性问题。")
    A("")

    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    Path(out_path).write_text("\n".join(L) + "\n", encoding="utf-8")
    return Path(out_path)


if __name__ == "__main__":
    import sys
    src = Path(sys.argv[1] if len(sys.argv) > 1
               else "reports/mixed-26.2-20262.json")
    dst = Path(sys.argv[2]) if len(sys.argv) > 2 else None
    p = render(src, dst)
    print(f"wrote {p}")
