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

### 指标契约（两个指标严格分离，绝不混淆）

- **`isolated_load_rate`（隔离加载率）** —— 每个被抽中的项目都在**独立的纯净实例**中安装。
  当服务端**完整达到就绪状态**、**且日志中确实出现该项目**时，才判定为通过。
  **89% 阈值作用于这个指标。**
- **`coexistence_rate`（共存率）** —— 所有被抽中的项目装进**同一个共享实例**。
  该指标**单独报告**，不作为头条数字。

### 为什么必须分成两个指标

随机抽 100 个项目，碰撞是**必然**发生的：重复模组、缺失依赖、
互斥的 mixin、客户端专属模组装进服务端等。因此「单一实例全量共存」
在构造上**不可能**达到 89%。任何声称能做到的项目，测量的都不是它所声称的东西。

隔离每个项目后，测量的恰好是一件事：**这个模组在这个加载器、
这个 Minecraft 版本上能否加载** —— 既有意义，也可达成。

### 防虚假通过规则（已写入代码）

测试框架的设计确保它**无法报告自己没有挣到的通过**：

1. **只认就绪标记。** 只有服务端日志中出现加载器自己的就绪行（`Done (...)`）
   才算通过。**退出码绝不作为依据** —— 因为服务在就绪后被主动停止时，
   退出码是非零的。
2. **模组必须出现在日志中。** 达到就绪后，框架会在日志中检索项目名；
   静默注册失败的模组会被记为**失败**，而非通过。
3. **抽样可复现。** 抽样使用固定随机种子，任何已发布的通过率都可精确复现。
4. **所有失败均保留**日志路径与末尾片段。

---

## 三、环境要求

- **Java 25** —— Minecraft 26.2 声明 `javaVersion.majorVersion = 25`，
  Java 21 无法运行。若自动探测失败，可设置 `AIOM_JAVA_HOME` 指定路径。
- `curl` —— 作为网络回退方案使用（原因见下）。
- 需能访问 Mojang piston-meta、Modrinth 以及各加载器的 maven 仓库。

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
python -m aiom.bench.pureboot -n 100 --seed 20262
```

报告输出至 `reports/pureboot-<mc>-<seed>.json`。

实测结果见 [`docs/BENCHMARK.md`](docs/BENCHMARK.md)。

## 五、项目结构

```
aiom/core/http.py       带curl 回退的 HTTP 传输层
aiom/core/mcmeta.py     Mojang 版本清单、依赖库、jar 下载
aiom/core/javart.py     Java 运行时发现
aiom/core/fabric.py     Fabric loader / intermediary 版本解析
aiom/core/paper.py      Paper v3 fill API
aiom/core/modrinth.py   Modrinth 搜索、抽样、下载
aiom/core/launcher.py   四套加载器的安装 + 启动 + 结果分级
aiom/bench/pureboot.py  基准测试主体
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

Two metrics are reported and never conflated:

- **`isolated_load_rate`** — each sampled project is installed into its own
  pristine instance. A project passes only when the server reaches full
  readiness **and** the project is confirmed present in the loader's log. This
  is the number the **89% threshold** applies to.
- **`coexistence_rate`** — all projects in one shared instance, reported
  separately.

They are separated because sampling 100 projects at random guarantees
collisions (duplicate mods, unmet dependencies, mutually exclusive mixins,
client-only mods on a server), so a single combined instance **cannot** reach
89% by construction.

### Anti-false-positive rules

1. **Readiness markers only.** A run passes only when the log contains the
   loader's own `Done (...)` line. Exit codes never count, because a server
   stopped after becoming ready exits non-zero.
2. **The mod must appear in the log.** A mod that silently fails to register is
   recorded as a failure.
3. **Reproducible sampling.** Seeded, so any published rate can be re-derived.
4. **Every failure is preserved** with its log path and tail.

## Requirements

- **Java 25** (Minecraft 26.2 declares `majorVersion = 25`; Java 21 will not
  work). Set `AIOM_JAVA_HOME` if auto-detection fails.
- `curl`, used as the network fallback.
- Access to Mojang piston-meta, Modrinth, and the loader mavens.

## Usage

```bash
python -m aiom.core.launcher fabric      # also: neoforge / forge / paper
python -m aiom.core.mcmeta               # version metadata + required Java
python -m aiom.core.javart               # locate a Java 25+ runtime
python -m aiom.core.modrinth 26.2        # ecosystem sizes + sample projects
python -m aiom.bench.pureboot -n 100 --seed 20262
```

Measured results: [`docs/BENCHMARK.md`](docs/BENCHMARK.md).

## Project layout

```
aiom/core/http.py       transport with curl fallback
aiom/core/mcmeta.py     Mojang manifest, libraries, jars
aiom/core/javart.py     Java runtime discovery
aiom/core/fabric.py     Fabric loader/intermediary resolution
aiom/core/paper.py      Paper v3 fill API
aiom/core/modrinth.py   Modrinth search, sampling, download
aiom/core/launcher.py   install + boot + classify for all four loaders
aiom/bench/pureboot.py  the benchmark
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