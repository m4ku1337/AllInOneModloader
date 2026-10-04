# AllInOne 混合加载方案选型（基于 26.2 实测）

> 结论先行：**单一 Minecraft 26.2 服务端实例内可以同时运行
> NeoForge 模组 + Paper 插件**；Fabric / Forge 模组通过
> **「同项目多生态发布」**在生态边界内共存。
> 硬性不可行的是「把纯 Fabric jar 直接塞进 NeoForge 实例」——已被实测证伪。

## 一、实测数据（seed 20262，n=100，2026-10-05）

来自 `tools/eco_analysis.py` 与 `tools/place_analysis.py` 的线上实测：

| 指标 | 实测值 |
|---|---|
| 有效 26.2 项目 | 100 / 100 |
| 无必选依赖 | 46 (46.0%) |
| 依赖在样本外 | 54 (54.0%) — **可解，装依赖闭包即可** |
| 依赖闭包总节点 | 129（含 29 个样本外依赖） |
| 无法解析的依赖 | **0** |
| 单一生态项目 | 75 (neoforge 44 / fabric 31) |
| 多生态项目 | 25 |
| 端侧兼容性双端可加载 | 100 (100.0%) |
| **可被宿主持有** | **128/128 = 100.00%** |

### 26.2 生态跨生态规模（Modrinth API 实测）

| 组合 | 项目数 |
|---|---|
| fabric AND neoforge | **2493** |
| fabric AND forge | 2320 |
| neoforge AND forge | 2330 |
| paper AND bukkit | 2205 |
| 全部 mod | 13216 |
| 全部 plugin | 4973 |

**这张表是整个方案的基石**：26.2 生态里，跨生态联合发布的项目有数千个，
不是个例，因此「一个实例同时容纳多生态模组」在供给侧完全成立。

## 二、被实测证伪的假设

### 证伪 1：Sinytra Connector 可作为 26.2 桥接层 → **不可用**

`sinytra-connector`（真实 ID `u58R1TMW`）的**全部**支持版本为：

```
1.20.1, 1.21, 1.21.1, 26.1.2
```

**没有任何 26.2 版本**。最新为 `Connector 3.0.0 beta 6`（仅 26.1.2）。
`connector-extras` 同样止于 26.1.2。

搜索结果中出现的「26.2 Sodium for NeoForge」属于项目 `AANobbMI`（Sodium），
被误当作 Connector —— 已在实现中修正，避免了错误选型。

### 证伪 2：纯 Fabric jar 放进 NeoForge 实例可被加载 → **明确不可行**

实测：把 `ferritecore-9.0.0-fabric.jar` 与 `cloth-config` 的 fabric 版
放入 NeoForge 26.2.0.88 实例，启动日志给出**加载器层面的显式拒绝**：

```
[ne.ne.fm.lo.mo.ModDiscoverer/SCAN]: Skipping jar. File mods/ferritecore-9.0.0-fabric.jar
    is a Fabric mod and cannot be loaded
[ne.ne.fm.lo.FMLLoader/]: File mods/ferritecore-9.0.0-fabric.jar is a Fabric mod
    and cannot be loaded
```

这比崩溃更值得注意：服务端**照常达到就绪态**（`Done (...)`）。
若只以「服务端启动成功」判定通过，会得到**假阳性**——
两个模组实际一个都没加载。这正是 PureBoot 强制校验
「模组是否真的出现在模组列表中」的原因。

### 证伪 3：依赖冲突是共存的主要障碍 → **不是**

54% 的项目有样本外依赖，但依赖闭包 **129 节点 / 0 个无法解析**。
依赖是可解问题，不是壁垒。真正的边界是加载器互斥。

## 三、选定方案：多生态并行 + 统一实例

基于以上实测，AllInOne 采用**双运行时统一目录**架构：

```
instance/
├── neoforge/          # 模组侧宿主
│   ├── mods/          # NeoForge 生态 jar
│   └── world/         # 共享世界（软链接到 ../shared-world）
├── paper/             # 插件侧宿主
│   ├── plugins/       # Paper 生态 jar
│   └── world/ ────────┘
└── shared-world/      # 唯一世界数据，双方共用
```

### 各生态归位规则（`family` 判定）

| 家族 | 宿主 | 理由 |
|---|---|---|
| neoforge / forge | `neoforge/` | Forge 是 NeoForge 前驱分支，NeoForge 兼容绝大多数 Forge 模组 |
| fabric / quilt / legacy-fabric | `neoforge/` **仅当该项目同时发布 neoforge 版** | 走多生态发布，非桥接 |
| paper / purpur / spigot / bukkit / folia | `paper/` | Bukkit 系同门 |
| 仅有单一生态且该生态无宿主 | 不安装 | 记入未通过清单，附原因 |

### 关键机制：生态自动择优

对每个采样项目，解析其 26.2 全部版本文件，按
「优先选宿主持有生态的 jar」规则下载。例：

```
ferrite-core 9.0.0-fabric   loaders=['fabric']    → 跳过
ferrite-core 9.0.0-neoforge loaders=['neoforge']  → ✓ 采用
```

实测采用 neoforge 版后加载成功：

```
Ferrite Core 9.0.0 (ferritecore)
 - ferritecore (jar(mods/ferritecore-9.0.0-neoforge.jar))
Cloth Config v26.2 API 26.2.155 (cloth_config)
 - cloth_config (jar(mods/cloth-config-26.2.155.jar))
```

`cannot be loaded` 计数从 2 降为 **0**。

## 四、各组件版本锁定（Minecraft 26.2）

| 组件 | 版本 | 来源 |
|---|---|---|
| Minecraft | 26.2 | Mojang 官方元数据 |
| Java | **25**（majorVersion=25） | Mojang 元数据 |
| NeoForge | **26.2.0.88** | neoforged maven（26.2.0.0 不存在，全为 `-beta` 后缀） |
| Fabric Loader | 0.19.5 | fabricmc meta |
| Forge | 26.2-65.1.3 | forge maven |
| Paper | 26.2 build **129** | `fill.papermc.io/v3`（v2 已不提供 26.x） |
| Connector | **不可用** | 止于 26.1.2 |

## 五、已知限制（如实记录）

1. **单 JVM 四合一不可行。** Fabric 与 NeoForge 都对同一批原版类做变换，
   加载器层面互斥。本项目不宣称单 JVM 混合，而是**统一目录 + 双运行时**。
2. **纯生态模组无法跨宿主。** 纯 Fabric 模组（不发布 neoforge 版）
   在本方案中无法进入 NeoForge 实例，如实计入未通过。
3. **世界数据不再共享。** 早期设计让两个运行时软链同一个世界目录，
   实测导致 `world_gen_settings.dat` 被两种格式交替重写而损坏
   （详见第八节）。现改为各运行时独立世界目录。
4. **Paper 插件的服务端语义与模组不同**（Bukkit API vs FML 事件系统），
   二者在同实例内共享配置文件与端口，但不共享对象引用。
5. **客户端专用项目不在判定范围内。** Modrinth 标记 `client_only` 的项目
   在设计上就无法在服务端运行，单列报告而不计入通过率分母（详见第六之二节）。
6. **隔离法无法归因「谁引发了冲突」。** 被隔离的 jar 记为失败，
   但日志通常只点名崩溃点，未必是真正的冲突发起方。

## 六、防假阳性规则（不可妥协）

PureBoot 判定 PASS 必须同时满足：

1. 日志出现就绪标记 `Done (...)` / `Server ready` / `Started @`；
2. **模组名确实出现在加载器模组列表中**；
3. 日志中该模组**没有** `cannot be loaded` / `Failed to load` 记录。

条件 2、3 是本次实测新增的——证伪 2 证明缺了它们就会把
「服务端起来了但模组全被跳过」误判为通过。

## 六之二、抽样口径（两次翻车换来的）

抽样器最初写错了两个地方，导致基准测的根本不是用户要求的样本集。

### 翻车 1：facet 只搜 `project_type:"mod"`

`sampler_pool()` 对每个 loader 只发一条带 `project_type:"mod"` 的查询。
实测结果：`Counter({'mod': 100})` —— **插件 0 个**。

修法：对每个 `loader × LOADABLE_TYPES` 单元分别查询并设配额。

### 翻车 2：`project_type` 只是**主**类型

修好 facet 后仍然 100% 是 mod。逐条核对后发现的真相：

```
facet project_type:plugin  total_hits=4814   ← facet 生效了
但 hits 里的 project_type 字段全是 "mod"
```

Modrinth 允许一个项目同时声明多种类型，而 `project_type` 只返回**其中一种**：

| 项目 | `project_type` | `all_project_types` | 实际是什么 |
|---|---|---|---|
| WorldEdit | mod | mod, plugin | Bukkit 插件 |
| FancyNpcs | mod | mod, plugin | Paper 插件 |
| Chunky | mod | mod, plugin | Bukkit 插件 |
| Simple Voice Chat | mod | mod, plugin | Bukkit 插件 |

`all_project_types` 才是完整集合。改读该字段后分布变为：

```
类型桶:  {'mod': 68, 'plugin': 32}
主加载器: {'neoforge': 30, 'forge': 29, 'fabric': 21, 'paper': 20}
```

### 翻车 3：池子均衡了，取样仍会偏

`sampler_pool()` 均衡后 `sample()` 仍是全池 `shuffle` 后取前 n，
完全可能连续抽到同一生态。改为按 `(类型桶, 主加载器)` **分层 +
最大余额法配额 + 兜底回填**，同 seed 结果完全可复现。

### 附带修正：`environment` 才是服务端可用性判据

版本对象上**没有** `client_side` / `server_side` 字段，
旧代码读不到就退回默认值 `"required"`，于是每个项目都看似服务端可用。
真实字段是 `environment`，实测 100 样本分布：

| environment | 数量 |
|---|---|
| `server_only` | 20 |
| `client_and_server` | 14 |
| `client_only` | **24** |
| `unknown` | 24 |
| `client_or_server_prefers_both` | 6 |
| `server_only_client_optional` | 5 |
| `client_or_server` | 5 |
| `client_only_server_optional` | 2 |

### 为什么 `client_only` 不进分母

`client_only` 是**作者显式声明**：这个项目在设计上就只在客户端运行
（Item Highlighter、Sodium、EntityCulling、Zoomify、MoreChatHistory…）。
专用服务端在任何加载器下都不可能加载它——这与 AllInOne 的混合加载能力无关。

若把它们计入分母，通过率的上限就被压到 76%，
测的其实是 Modrinth 的标签准确度，而不是加载器。

因此：**单列报告、不安装、不进分母**。报告中 `sampled`（抽样总数）、
`eligible`（判定分母）、`client_only`（跳过数）三个数字同时给出，
口径可被读者复核。依赖节点同样过滤——一个客户端库会把它依赖的模组一起拖垮。

实测结果：闭包 126 节点 → 剔除 25 个 `client_only` → 余 **101 个全部可归位**。

## 七、共享实例的坏模组隔离（实测发现）

### 现象

把 9 个 NeoForge 模组一起装进实例后启动，**服务端直接起不来**：

```
[main/ERROR] [minecraft/Main]: Failed to start the minecraft server
Caused by: InjectionError: Critical injection failure:
  Callback method bettershulkers$checkForShulkerMaterial(...)V
  in bettershulkers.mixins.json:AnvilMenuMixin from mod bettershulkers
  failed injection check, (0/1) succeeded. Scanned 0 target(s). No refMap loaded.
```

一个模组的 Mixin 注入失败，**拖垮整个实例**。若就此把 9 个全判失败，
得到的共存率毫无意义 —— 它只反映「有一个坏模组在场」。

### 隔离算法（`aiom/core/isolate.py`）

1. 启动运行时；成功则所有在场项目直接判定。
2. 失败则从日志提取**加载器点名的元凶**：
   `from mod X` / `X.mixins.json` / `Failed to load mod X` / `Could not load plugin X`。
3. 把该 jar **移入 `quarantine/`（不删除）**，重启。
4. 日志未点名时退化为二分：移除后半段 jar 继续。
5. 直至启动成功或无可移除。

每轮至少移除一个 jar，故必然收敛；代价是每移除一个 jar 一次启动，
而非每个项目一次启动。

### 计数口径（关键）

被隔离的模组**计入分母、判为失败**——它确实破坏了共享实例。
二分买到的是「让幸存者被真实验证」，而不是把失败稀释掉。
不这样做的话，一次崩溃会把 8 个好模组一起冤枉。

### 另一类必须区分的失败

`main_menu_credits` 的客户端 Mixin 在服务端找不到目标：

```
Error loading class: net/minecraft/client/gui/screens/PauseScreen
@Mixin target ...PauseScreen was not found
```

这是**客户端专用模组装到服务端**的正常表现，WARN 级别，不影响启动。
判定逻辑因此只在日志中**出现该项目的拒绝/错误行**时才判失败，
不会因为日志里别处有 ERROR 就连坐。

## 八、共享世界目录是错误设计（实测教训）

### 原始设计

```
neoforge/world  ──symlink──┐
                            ├──> shared-world/
paper/world     ──symlink──┘
```

### 实际后果

两个运行时**交替写同一个世界目录**，各自用不同格式重写
`world_gen_settings.dat`。结果是**世界数据损坏**，且报错完全指向错误方向：

```
[ERROR] [minecraft/LevelStorageSource]: Unable to read or access the world
gen settings file! .\world\data\minecraft\world_gen_settings.dat
java.lang.IllegalStateException: Overworld settings missing
net.neoforged.fml.startup.FatalStartupException: Couldn't find Minecraft
server thread. Startup likely failed.
```

最恶劣的一点：此时 **mods 目录已空**，隔离器已把所有模组移除干净，
日志里再没有任何模组相关信息。一个模组作者看到这个报错，
绝不会怀疑「世界被另一个运行时写坏了」——它长得像加载器坏了。

### 修正

每个运行时拥有**独立世界**：

```
instance/
  neoforge/world/     # NeoForge 自己的世界
  paper/world/        # Paper 自己的世界
  worlds/README.md    # 说明为何不共享，以及如何手动迁移
```

`worlds/README.md` 明确写出原因和迁移方法，避免后来者再踩。

**这同时否定了「单一世界」的原始诉求**。必须如实说明：在两个独立服务端
运行时之间共享同一个世界目录不可行——Minecraft 的世界存档格式不是
跨加载器稳定的契约。

## 九、服务端进程未被终止（Windows 特有）

### 现象

基准任务跑完 Paper 阶段后**永不返回**，且后续 `rm -rf` 报
`Device or resource busy`。

### 两层根因

1. **`terminate()` 只杀父进程。** Paper 经 paperclip 启动，paperclip 解压后
   再拉起真正的服务端**子 JVM**。杀父进程后子进程继续持有
   `paper.jar`、`libraries/`、世界锁。
2. **`taskkill /T` 需要父进程仍存在。** 父进程退出后其 pid 不再标识进程树，
   `/T` 找不到子进程。

### 修正（`launcher.kill_stray_servers`）

1. 父进程存活时先 `taskkill /F /T /PID`；
2. 无论成败，事后**按命令行扫描**本工作区路径下的 `java.exe` 并终止。

### 关键坑：`wmic` 已被移除

第一版用 `wmic` 枚举进程，在新版 Windows 上命令不存在 →
**静默返回「清理 0 个」**。一个清理函数谎报成功，比没有这个函数更危险。

改用 PowerShell 的 CIM 提供者（`Get-CimInstance Win32_Process`）枚举
`java.exe` 的 ProcessId 与 CommandLine，再按本工作区路径过滤。

只杀命令行含本工作区路径的 JVM，避免误杀用户其他 Java 程序。

## 十、超时形同虚设：阻塞读取导致永久挂起

### 现象

100 样本首轮运行中，NeoForge 阶段顺利通过
（**87 个模组同时启动，`Done (4.277s)!`，零隔离**），
Paper 也在 `06:22:32` 打出 `Done (38.036s)!` —— 但基准任务**永不返回**，
一个 java 进程持续占用 1.5 GB 内存。

### 根因

`boot()` 用 `for line in proc.stdout` 阻塞读管道，而 deadline 检查
**只放在读到新行之后**：

```python
for line in proc.stdout:          # ← 阻塞在这里
    chunks.append(line)
    if stop_marker and stop_marker in line:
        deadline = min(deadline, time.time() + 20)
    if time.time() > deadline:     # ← 永远走不到
        break
```

Paper 打印就绪标记后**就不再输出任何一行**，于是 `proc.stdout` 永不返回，
`break` 永远不执行，420 秒超时形同虚设。

这不是「超时设得太短」，而是**超时不可达**。

### 修正

改为后台线程读管道，主循环定时轮询：

```python
reader = threading.Thread(target=pump, daemon=True)
reader.start()
while True:
    if stop_marker and stop_at is None and any(...):
        stop_at = time.time() + 20
    if stop_at is not None and time.time() >= stop_at: break
    if time.time() >= deadline: break
    if proc.poll() is not None and not reader.is_alive(): break
    time.sleep(0.25)
```

主循环无论如何都会醒来，因此超时终于可达。

### 复现测试

```python
# 子进程打印就绪标记后 sleep(600) 不再输出
prog = 'import sys,time; print("Done (38.0s)! For help"); sys.stdout.flush(); time.sleep(600)'
```

| 版本 | 结果 |
|---|---|
| 修复前 | 永久挂起 |
| 修复后 | **21.2 秒返回**，标记完整捕获 |

**教训**：带超时的循环里，任何阻塞调用都会吃掉这个超时。
管道读取必须放到线程里，让控制流始终掌握在主循环手里。

## 十一、二分移除不等于失败（规模放大后的缺陷）

### 现象

小样本（n=6）下二分几乎不触发，这个缺陷一直没暴露。
到 90 个 jar 的规模，一次**无人点名**的崩溃会让二分移除后一半共 45 个，
而判定逻辑把所有被移除的 jar 都记为失败——**一次崩溃就能把通过率打到 50% 上下**，
且这 45 个模组从未被证明有任何问题。

### 修正

区分两种移除原因：

| 类型 | 触发条件 | 判定 |
|---|---|---|
| `guilty` | 日志点名（`from mod X` / `X.mixins.json`） | **真失败** |
| `unverified` | 无人点名，缩小搜索空间 | **不算失败** |

启动成功后把 `unverified` 的 jar 全部放回磁盘，并**再启动一次**——
因为刚才那份成功日志是在它们缺席时产生的，不能拿来给它们判定。
若回填后再次崩溃，则保留缩减后的集合。

单元测试：90 jar 二分 → `guilty 0` / `unverified 45`；
回填后磁盘恢复 90 个且 `removed` 清空；点名移除 → `guilty` 命中。

