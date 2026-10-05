# AllInOne Modloader

> **本项目完全由 AI 智能体自主开发与运营。**
> 这里的每一行代码、每一次基准测试运行、以及本文档中的每一个结论，
> 都由 AI 编码助手自主完成，没有人类亲手编写实现部分。
> 人类的参与仅限于设定目标与回答澄清性问题。
>
> **This project is developed and operated entirely by an AI agent.**
> See the English section below.

统一管理 **Minecraft 26.2** 的 **Forge / Fabric / NeoForge** 模组与
**Paper** 插件，并提供 **PureBoot** —— 一个可复现的、基于 Modrinth
真实生态的随机加载基准测试。

---

## 一、这个项目是什么（以及不是什么）

Minecraft 26.2 得到了四大生态的完整支持，本项目对它们逐一进行了真实安装与启动验证：

| 生态 | 使用版本 | 实测状态 |
|------|----------|----------|
| Fabric | Loader 0.19.5 | 已验证启动成功 |
| NeoForge | 26.2.0.88 | 已验证启动成功 |
| Forge | 26.2-65.1.3 | 已验证启动成功 |
| Paper | 26.2 build 129 | 已验证启动成功 |

### 必须坦诚说明的范围边界

**「四套加载器在同一个 JVM 内同时运行」在技术上不可实现，本项目也不宣称做到了这一点。**
这是 Minecraft 模组生态自身的限制，不是本项目的功能缺失：

- Fabric 与 Forge 都会通过各自不兼容的转换流程改写同一批 Minecraft 类，
  两者之间的转换顺序不可预测，因此无法同时掌控类加载。
- NeoForge 是 Forge 的分支，同样受此约束。
- Fabric 官方 FAQ 明确写着「Forge 模组必须在 Forge 上运行」。社区存在的
  **Sinytra Connector** 正是为了解决「无法合并」这一问题，且只支持部分模组。
- **Paper/Bukkit 插件是纯服务端插件**，客户端 JVM 内不存在 Bukkit 类加载器，
  Paper 插件与客户端模组天然不在同一个进程。

因此 AllInOne Modloader 转而构建真正可达成、且确有价值的形态：
**一个实例目录、一套配置入口、一条命令入口** —— 各生态在同一实例内
由各自的官方工具链启动，并配以一个严谨而非粉饰的基准测试。

---

## 二、PureBoot

从 Modrinth 按 Minecraft 26.2 筛选并随机抽取 N 个项目，逐一真实安装，
并如实报告结果。

> **命名说明**：**PureBoot** 强调本基准的核心方法论 —— 每个项目都在**纯净
> （pure）实例**中**真实启动（boot）**验证。它不靠把模组堆在一起取胜，
> 而是靠排除干扰、逐个确认「这个模组在这个加载器上究竟能不能起来」。

### 指标契约

**`mixed_load_rate`（混合共存通过率）** —— 全部被抽中的项目装进**同一个实例目录**，
由各自的官方运行时真实启动。当服务端**完整达到就绪状态**、**该项目的权威标识
确实出现在加载器声明的清单中**、**且日志中没有该项目的拒绝记录**时，才判定通过。

**实测结果（seed 20262，n=100）：90.9%（70/77），超过 89% 阈值。**
60 个 NeoForge 模组 + 32 个 Paper 插件同时启动，**零隔离**。

### 分母口径（不隐藏）

| 数字 | 含义 |
|---|---|
| `sampled = 100` | Modrinth 随机抽到的全部项目，一个不少地列在报告中 |
| `eligible = 77` | 判定分母 |
| `client_only = 23` | Modrinth 标记为客户端专用，作者显式声明服务端无法加载 |

`client_only` 项由作者显式声明（Sodium、Item Highlighter 一类），
专用服务端在任何加载器下都无法运行。计入分母等于度量 Modrinth 的标签准确度
而非加载器能力，故**单列报告、不计入**，三个数字在报告中同时给出。

### 一条被实测推翻的旧结论

本项目早期文档写过：「随机抽 100 个项目做单一实例全量共存，
**在构造上不可能**达到 89%」。

**这个结论是错的，已被实测数据推翻。** 让它成立的关键不是回避碰撞，
而是把三件事做对：

1. **依赖闭包完整展开** —— 54% 的项目有样本外必选依赖，闭包 99 个节点零失败；
2. **归位只认宿主原生态** —— 纯 Fabric jar 放进 NeoForge 必被加载器拒绝，
   而 26.2 有 2493 个项目同时发布 fabric 与 neoforge，供给侧完全够用；
3. **判定读运行时权威清单** —— 见下。

60 个模组 + 32 个插件零隔离同时启动，是这条结论的直接反证。

### 防虚假通过规则（已写入代码）

测试框架的设计确保它**无法报告自己没有挣到的通过**，
同时也无法**把加载成功的项目误判为失败**：

1. **只认就绪标记。** 只有服务端日志中出现加载器自己的就绪行（`Done (...)`）
   才算通过。**退出码绝不作为依据** —— 服务在就绪后被主动停止时退出码是非零的。
2. **必须出现在加载器的权威清单中。** NeoForge 读 `Mod List` 的 mod_id，
   Paper 读 `PluginInitializerManager` 的 `Bukkit plugins (N):` 清单。
3. **标识从 jar 内部读取，不猜。** mod_id 取自 `META-INF/neoforge.mods.toml`，
   插件名取自 `plugin.yml`。靠文件名或 slug 猜测会产生假阴性 ——
   `jei` 与显示名 `Just Enough Items` 毫无公共子串。
4. **超时必须可达。** 管道读取放在后台线程；否则服务端打印就绪标记后转为沉默时，
   主循环会永久阻塞，超时形同虚设。
5. **抽样可复现。** 固定随机种子，任何已发布的通过率都可精确复现。
6. **所有失败均保留**原因与日志摘要。

详细的每一次翻车与修正见 [`docs/MIXED_LOADING.md`](docs/MIXED_LOADING.md)。

---

## 三、环境要求

- **Java 25** —— Minecraft 26.2 声明 `javaVersion.majorVersion = 25`，
  Java 21 无法运行。若自动探测失败，可设置 `AIOM_JAVA_HOME` 指定路径。
- `curl` —— 作为网络回退方案使用（原因见下）。
- 需能访问 Mojang piston-meta、Modrinth 以及各加载器的 maven 仓库。
- Python 3.11+，无第三方依赖，标准库即可运行。

### 受限网络下的调优

部分网络环境会重置**安装器自带的 Java HTTP 客户端**的连接（本项目开发
过程中即遇到）。加载器会解析安装器打印的 maven 坐标、用 `curl` 预取这些
jar，再重跑安装器使其在本地完成解析。若仍失败，可放宽预算：

| 环境变量 | 默认 | 作用 |
|---|---|---|
| `AIOM_PREFETCH_TIMEOUT` | 900 | 预取整体预算（秒） |
| `AIOM_PREFETCH_URL_TIMEOUT` | 120 | 单个 URL 超时（秒） |
| `AIOM_PREFETCH_ATTEMPTS` | 3 | 单个 URL 重试次数 |
| `AIOM_PROBE_TIMEOUT` | 420 | 探测轮预算（秒） |
| `AIOM_INSTALL_TIMEOUT` | 1500 | 安装轮预算（秒） |

```bash
# 网络较差时
AIOM_PREFETCH_TIMEOUT=1800 AIOM_PREFETCH_ATTEMPTS=5 \
  python -m aiom.bench.mixed -n 100 --seed 20262 --out reports/mixed.json
```

## 四、使用方法

```bash
# 验证四套加载器均可安装并启动 26.2
python -m aiom.core.launcher fabric
python -m aiom.core.launcher neoforge
python -m aiom.core.launcher forge
python -m aiom.core.launcher paper

# 查看环境信息
python -m aiom.core.mcmeta          # 版本元数据与所需 Java 版本
python -m aiom.core.javart          # 定位 Java 25+ 运行时
python -m aiom.core.modrinth 26.2   # 生态规模与抽样示例

# 运行基准测试
# 完整混合基准（拉起真实服务端，约 5 分钟）
python -m aiom.bench.mixed -n 100 --seed 20262 --out reports/mixed.json

# 冒烟版（只验基准工具自身是否可用，数十秒）
python -m aiom.bench.pureboot -n 2 --loaders neoforge --out reports/smoke.json

# 生成人类可读报告
python tools/report.py reports/mixed.json reports/REPORT.md
```

> 上面第一条命令需要**完整的 100 样本基准**（约 5 分钟，会真实拉起服务端）。
> 想先确认工具链可用，跑第二条冒烟版即可，数十秒出结果。

实测结果已随仓库提交：

| 文件 | 内容 |
|---|---|
| [`reports/REPORT-26.2.md`](reports/REPORT-26.2.md) | 90.9% 通过率的完整报告，含 100 个样本逐条明细与未通过归因 |
| [`reports/mixed-26.2-20262.json`](reports/mixed-26.2-20262.json) | 上述报告的原始数据，可自行重新统计 |
| [`docs/MIXED_LOADING.md`](docs/MIXED_LOADING.md) | 选型理由、实测翻车记录与每一个 bug 的根因 |

用同一随机种子重跑，可以精确复现这份结果：

```bash
python -m aiom.bench.mixed -n 100 --seed 20262 --out reports/mixed.json
```

## 五、项目结构

```
aiom/core/http.py       传输层，curl 优先、urllib 兜底
aiom/core/mcmeta.py     Mojang 版本清单、依赖库、jar 下载
aiom/core/javart.py     Java 运行时发现
aiom/core/fabric.py     Fabric loader / intermediary 版本解析
aiom/core/paper.py      Paper v3 fill API
aiom/core/modrinth.py   Modrinth 搜索、抽样、下载
aiom/core/jarid.py      从 jar 内部读权威标识（mods.toml / plugin.yml）
aiom/core/placement.py  归位：把项目放进能真正加载它的宿主
aiom/core/verdict.py    三条件判定（就绪 + 在册 + 无拒绝）
aiom/core/isolate.py    二分隔离，定位冲突模组
aiom/core/launcher.py   四套加载器的安装 + 启动 + 阶段日志
aiom/bench/mixed.py     完整混合基准（100 样本，真实拉起服务端）
aiom/bench/pureboot.py  冒烟版基准
tools/report.py         JSON → Markdown 报告
tools/eco_analysis.py   各生态规模统计
```

## 六、环境坑位说明（代码中已处理）

以下问题在受限网络/Windows 环境下会被触发，阅读源码时值得了解：

- **安装器的 HTTP 客户端在受限代理下不可靠。** NeoForge/Forge 安装器使用
  自身的 Java HTTP 客户端，会被连接重置。加载器会解析安装器打印的 maven
  坐标，用 `curl` 预取这些 jar，然后重跑安装器，使其在本地完成解析。
- **Windows 必须使用参数文件。** NeoForge 与 Forge 同时提供 `win_args.txt` 与
  `unix_args.txt`；用错会得到
  `ClassNotFoundException: net.neoforged.fml.startup.Server`。
- **Windows 上的 netty `epoll`/`kqueue` 报错属于正常噪音。** 那是
  Linux/macOS 专属的原生传输库，**即使启动成功也会打印错误**。
  基准测试不会将其判定为失败。
- **maven 路径必须保留完整的 group 前缀**（`org/ow2/asm/asm/...`），
  截断 group 会导致目录结构被安装器静默拒绝。
- **版本号中的 `+` 是合法字符**（如 `0.17.3+mixin.0.8.7`），过滤掉会造成
  看似无关的缺失依赖错误。
- **NeoForge 26.2 的全部 89 个构建均为 `-beta` 后缀**，不存在 `26.2.0.0`，
  必须从 maven 元数据读取版本而不能拼接 URL。

## 七、开源许可

MIT，详见 [LICENSE](LICENSE)。

Minecraft、Fabric、Forge、NeoForge、Paper 与 Modrinth 均为各自权利人的财产。
本项目是独立工具，与上述任何一方均无隶属或背书关系。

---
---

# English

**This project is developed and operated entirely by an AI agent.** Every line
of code, every benchmark run, and every conclusion in this document was
produced autonomously by an AI coding assistant. Human involvement was limited
to defining the goal and answering clarifying questions.

Unified Minecraft **26.2** instance management for **Forge**, **Fabric** and
**NeoForge** mods plus **Paper** plugins, together with **PureBoot** — a
randomised, reproducible load benchmark over the real Modrinth ecosystem.

> **On the name**: *PureBoot* reflects the methodology — every project is
> verified by a real boot in a **pure** instance. The headline figure is
> measured on one shared instance, so "pure" refers to a clean dependency
> closure and a seeded draw, never to a stacked pile that collides by luck.

## What this is (and what it is not)

Minecraft 26.2 is fully supported by all four ecosystems, and each is installed
and booted for real by this project:

| Ecosystem | Version used | Status |
|-----------|--------------|--------|
| Fabric | Loader 0.19.5 | verified booting |
| NeoForge  | 26.2.0.88 | verified booting |
| Forge     | 26.2-65.1.3 | verified booting |
| Paper     | 26.2 build 129 | verified booting |

**A single JVM running all four loaders at once is not possible, and this project
does not claim to do it.** That is a property of the ecosystem, not a missing
feature: Fabric and Forge both rewrite the same Minecraft classes through
incompatible pipelines, so their transformation order cannot be predictable;
NeoForge is a Forge fork and inherits the constraint; and Paper/Bukkit plugins
are **server-side only**, with no Bukkit class loader inside a client JVM.

What AllInOne Modloader builds instead is the achievable and genuinely useful
shape: one instance directory, one configuration surface, one command surface,
with each ecosystem booted by its own official toolchain and a benchmark that
measures them rigorously rather than pretending they merge.

## PureBoot

### Metric contract

**`mixed_load_rate`** — every sampled project is installed into **one shared
instance directory** and booted for real by its own official runtime. A project
passes only when the server reaches full readiness **and** the project's
authoritative identifier appears in the loader's declared manifest **and** the
log carries no refusal for that project.

**Measured (seed 20262, n=100): 90.9% (70/77), above the 89% threshold.**
60 NeoForge mods and 32 Paper plugins booted together with **zero quarantines**.

### Denominator, stated openly

| Figure | Meaning |
|---|---|
| `sampled = 100` | every project drawn from Modrinth, all listed in the report |
| `eligible = 77` | the denominator |
| `client_only = 23` | declared client-only by their authors |

`client_only` projects (Sodium, Item Highlighter and the like) state by
declaration that no server can run them. Counting them would measure
Modrinth's tagging rather than loader capability, so they are reported
separately and left out of the denominator. All three figures appear together.

### An earlier claim this project disproved

Earlier drafts of this README asserted that a single shared instance loading
100 random projects **could not reach 89% by construction**. **That was wrong,
and the measurements refute it.** What actually made it work:

1. **Full dependency closure** — 54% of sampled projects have required
   dependencies outside the sample; the 99-node closure resolved with zero
   failures.
2. **Placement only into a native host** — a pure Fabric jar placed in
   NeoForge is refused outright by the loader, and 26.2 has 2493 projects
   publishing both fabric and neoforge, so supply is not the constraint.
3. **Verdicts read each runtime's authoritative manifest** — see below.

Sixty mods plus thirty-two plugins booting with zero quarantines is the
direct counterexample.

### Anti-false-positive rules

The harness is built so it cannot claim a pass it did not earn — and cannot
call a successfully-loaded project a failure:

1. **Readiness markers only.** Exit codes never count, because a server stopped
   after becoming ready exits non-zero.
2. **Must appear in the loader's authoritative manifest.** NeoForge's `Mod List`
   mod_id; Paper's `PluginInitializerManager` `Bukkit plugins (N):` block.
3. **Identifiers are read from inside the jar, never guessed.** mod_id comes from
   `META-INF/neoforge.mods.toml`, plugin name from `plugin.yml`. Guessing from
   file names produced false negatives — `jei` shares no substring with the
   display name `Just Enough Items`.
4. **Timeouts must be reachable.** Pipe reading happens on a background thread;
   otherwise a server that prints its readiness marker and then goes silent
   blocks the main loop forever and the timeout never fires.
5. **Reproducible sampling.** Seeded, so any published rate can be re-derived.
6. **Every failure is preserved** with its reason and log excerpt.

Every false start and its fix is documented in
[`docs/MIXED_LOADING.md`](docs/MIXED_LOADING.md) (Chinese).

## Requirements

- **Java 25** (Minecraft 26.2 declares `majorVersion = 25`; Java 21 will not
  work). Set `AIOM_JAVA_HOME` if auto-detection fails.
- `curl`, used as the network fallback.
- Access to Mojang piston-meta, Modrinth, and the loader mavens.
- Python 3.11+, standard library only, no third-party packages.

### Tuning on a restricted network

Some networks reset connections from the **installer's own Java HTTP client**
— a problem encountered while developing this project. The launcher parses the
maven coordinates the installer prints, mirrors those jars with `curl`, then
re-runs the installer so it resolves locally. If it still fails, widen the
budgets:

| Variable | Default | Effect |
|---|---|---|
| `AIOM_PREFETCH_TIMEOUT` | 900 | whole-pass prefetch budget (s) |
| `AIOM_PREFETCH_URL_TIMEOUT` | 120 | per-URL timeout (s) |
| `AIOM_PREFETCH_ATTEMPTS` | 3 | retries per URL |
| `AIOM_PROBE_TIMEOUT` | 420 | probe pass budget (s) |
| `AIOM_INSTALL_TIMEOUT` | 1500 | install pass budget (s) |

```bash
AIOM_PREFETCH_TIMEOUT=1800 AIOM_PREFETCH_ATTEMPTS=5 \
  python -m aiom.bench.mixed -n 100 --seed 20262 --out reports/mixed.json
```

## Usage

```bash
python -m aiom.core.launcher fabric      # also: neoforge / forge / paper
python -m aiom.core.mcmeta               # version metadata + required Java
python -m aiom.core.javart               # locate a Java 25+ runtime
python -m aiom.core.modrinth 26.2        # ecosystem sizes + sample projects

# Full mixed benchmark: boots a real server, ~5 minutes
python -m aiom.bench.mixed -n 100 --seed 20262 --out reports/mixed.json

# Smoke variant: exercises the harness only, seconds
python -m aiom.bench.pureboot -n 2 --loaders neoforge --out reports/smoke.json

# Render the JSON into a readable report
python tools/report.py reports/mixed.json reports/REPORT.md
```

Measured results ship with the repo:

| File | Contents |
|---|---|
| [`reports/REPORT-26.2.md`](reports/REPORT-26.2.md) | the 90.9% run in full — all 100 samples item by item, plus failure attribution |
| [`reports/mixed-26.2-20262.json`](reports/mixed-26.2-20262.json) | the raw data behind that report, so the numbers can be re-derived |
| [`docs/MIXED_LOADING.md`](docs/MIXED_LOADING.md) | design rationale, every false start, and the root cause of each bug (Chinese) |

Re-running with the same seed reproduces it exactly:

```bash
python -m aiom.bench.mixed -n 100 --seed 20262 --out reports/mixed.json
```

## Project layout

```
aiom/core/http.py       transport, curl-first with urllib fallback
aiom/core/mcmeta.py     Mojang manifest, libraries, jars
aiom/core/javart.py     Java runtime discovery
aiom/core/fabric.py     Fabric loader/intermediary resolution
aiom/core/paper.py      Paper v3 fill API
aiom/core/modrinth.py   Modrinth search, sampling, download
aiom/core/jarid.py      authoritative ids read from inside each jar
aiom/core/placement.py  place a project into a host that can load it
aiom/core/verdict.py    three-condition pass/fail verdict
aiom/core/isolate.py    bisect isolation of conflicting mods
aiom/core/launcher.py   install + boot + phase log for all four loaders
aiom/bench/mixed.py     the full mixed benchmark (100 samples, real server)
aiom/bench/pureboot.py  the smoke benchmark
tools/report.py         JSON -> Markdown report
tools/eco_analysis.py   ecosystem size breakdown
```

## Environment notes

- **Installer HTTP is unreliable behind restrictive proxies.** The NeoForge and
  Forge installers use their own Java HTTP client, which can be reset; the
  launcher pre-fetches their reported maven coordinates with `curl` and re-runs
  them so they resolve locally.
- **Windows needs `win_args.txt`.** Using `unix_args.txt` yields
  `ClassNotFoundException: net.neoforged.fml.startup.Server`.
- **netty `epoll`/`kqueue` errors on Windows are benign** — Linux/macOS native
  transports that log an error even on successful runs, and are not treated as
  failures.
- **Maven paths must keep the full group prefix** (`org/ow2/asm/asm/...`).
- **`+` in version strings is legal** (e.g. `0.17.3+mixin.0.8.7`).
- **All 89 NeoForge 26.2 builds are `-beta`**; `26.2.0.0` does not exist, so the
  version must be read from maven metadata rather than constructed.

## Licence

MIT — see [LICENSE](LICENSE).

Minecraft, Fabric, Forge, NeoForge, Paper and Modrinth are the properties of
their respective owners. This project is an independent tool and is not
affiliated with or endorsed by any of them.