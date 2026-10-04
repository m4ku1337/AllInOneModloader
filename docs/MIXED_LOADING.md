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
3. **世界数据共享为软链接。** 两运行时不会同时持有世界锁，
   启动脚本保证互斥访问。
4. **Paper 插件的服务端语义与模组不同**（Bukkit API vs FML 事件系统），
   二者在同世界内不共享对象引用，仅共享世界存储。

## 六、防假阳性规则（不可妥协）

PureBoot 判定 PASS 必须同时满足：

1. 日志出现就绪标记 `Done (...)` / `Server ready` / `Started @`；
2. **模组名确实出现在加载器模组列表中**；
3. 日志中该模组**没有** `cannot be loaded` / `Failed to load` 记录。

条件 2、3 是本次实测新增的——证伪 2 证明缺了它们就会把
「服务端起来了但模组全被跳过」误判为通过。

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
