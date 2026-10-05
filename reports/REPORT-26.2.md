# PureBoot 混合实例基准报告

> 本报告由 AI 全自主运行生成，Minecraft **26.2**，seed `20262`，抽样 100 个项目。

## 一、结论

| 指标 | 值 |
|---|---|
| **混合共存通过率** | **90.9%** （70/77） |
| 目标阈值 | 89.0% |
| 是否**达标** | 是 |
| Modrinth 抽样总数 | 100 |
| 判定分母（eligible） | 77 |
| 客户端专用跳过 | 23 |
| 无法归位 | 4 |
| 依赖闭包节点 | 99 |
| 耗时 | 4.7 分钟 |

### 分母口径

- `sampled = 100`：Modrinth 随机抽到的全部项目，一个不少地列在下表。
- `eligible = 77`：**判定分母**。其中 23 个被 Modrinth 标记为
  `client_only`——作者显式声明该构建只在客户端运行，专用服务端在任何
  加载器下都无法加载。计入分母等于度量 Modrinth 的标签准确度而非加载器
  能力，故单列报告、不计入。

## 二、运行时实测

安装：NeoForge 模组 **60** 个、Paper 插件 **32** 个、下载失败 7 个。

| 运行时 | 启动成功 | 隔离轮次 | 加载器点名移除 | 二分移除 |
|---|---|---|---|---|
| neoforge | 是 | 1 | 0 | 0 |
| paper | 是 | 1 | 0 | 0 |

## 三、样本构成

| 维度 | 分布 |
|---|---|
| 生态（宿主） | neoforge 42, paper 29, 未归位 6 |
| 选用构建的加载器 | neoforge 42, paper 29, — 6 |
| 判定类型 | 插件 12, 模组 68, 模组+插件 20 |
| Modrinth environment | client_and_server 16, client_only 23, client_only_server_optional 2, client_or_server 5, client_or_server_prefers_both 5, server_only 20, server_only_client_optional 6, unknown 23 |

## 四、100 个样本测试明细

| # | 项目 | 类型 | 宿主 | 构建加载器 | 版本 | 结果 | 原因摘要 |
|---|---|---|---|---|---|---|---|
| 0 | item-highlighter | 模组 | — | — | 1.2.2 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 1 | macaws-holidays | 模组 | neoforge | neoforge | 1.1.2 | ✅ 通过 | loaded and announced |
| 2 | particle-rain | 模组 | — | — | — | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 3 | cut-through | 模组 | — | — | 26.2.0 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 4 | smartbrainlib | 模组 | neoforge | neoforge | 2.0.3 | ✅ 通过 | loaded and announced |
| 5 | veinminer-enchantment | 模组+插件 | paper | paper | 2.11.2 | ✅ 通过 | loaded and announced |
| 6 | drippy-loading-screen | 模组 | — | — | 3.1.5-26.2-neoforge | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 7 | geophilic | 模组 | neoforge | neoforge | 3.7 | ✅ 通过 | loaded and announced |
| 8 | axolotl-buckets | 模组 | — | — | 2.0.0+26.2-neoforge | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 9 | infinite-villager-trading | 插件 | paper | paper | 2.6.5 | ✅ 通过 | loaded and announced |
| 10 | orebfuscator | 插件 | paper | paper | 5.6.2 | ✅ 通过 | loaded and announced |
| 11 | tslatentitystatus | 模组 | neoforge | neoforge | 1.10.2 | ✅ 通过 | loaded and announced |
| 12 | skbee | 插件 | paper | paper | 3.26.0 | ✅ 通过 | loaded and announced |
| 13 | scalablelux | 模组 | neoforge | neoforge | 0.3.0-alpha.0.16+26.2 | ✅ 通过 | loaded and announced |
| 14 | bluemap | 模组+插件 | paper | paper | 5.28-paper | ✅ 通过 | loaded and announced |
| 15 | cardinal-components-api | 模组 | — | — | — | ❌ 失败 | no build for a runtime we host: publishes only fabric (loaders: fabric,quilt) |
| 16 | towns-and-towers | 模组 | neoforge | neoforge | 1.13.11 | ✅ 通过 | loaded and announced |
| 17 | configapi | 模组+插件 | paper | paper | 1.1 | ✅ 通过 | loaded and announced |
| 18 | worldguard | 插件 | paper | paper | 7.0.19 | ✅ 通过 | loaded and announced |
| 19 | bclib | 模组 | — | — | — | ❌ 失败 | no build for a runtime we host: publishes only fabric (loaders: fabric) |
| 20 | moogs-structure-lib | 模组 | neoforge | neoforge | 3.4.2-neoforge-26.2 | ✅ 通过 | loaded and announced |
| 21 | malilib | 模组 | — | — | — | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 22 | villager-in-a-bucket | 模组+插件 | paper | paper | 1.6.2 | ✅ 通过 | loaded and announced |
| 23 | viaaprilfools | 模组+插件 | paper | paper | 4.2.3 | ✅ 通过 | loaded and announced |
| 24 | underground-worlds | 模组 | neoforge | neoforge | 3.2.1-26.1 | ✅ 通过 | loaded and announced |
| 25 | entityculling | 模组 | — | — | 1.11.2 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 26 | dynamic-fps | 模组 | — | — | 3.11.9 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 27 | servercore | 模组 | neoforge | neoforge | 1.5.19+26.2 | ✅ 通过 | loaded and announced |
| 28 | inventoryrollbackplus | 插件 | paper | paper | 1.8.5 | ✅ 通过 | loaded and announced |
| 29 | leafrtp | 模组+插件 | paper | paper | 3.2.1 | ✅ 通过 | loaded and announced |
| 30 | stringandsand | 模组+插件 | — | — | 1.2.0+mod | ❌ 失败 | routed to Paper but the jar carries no plugin.yml / paper-plugin.yml, so it is not a Bukki |
| 31 | biomes-o-plenty | 模组 | neoforge | neoforge | 26.2.0.0.28 | ✅ 通过 | loaded and announced |
| 32 | tectonic | 模组 | neoforge | neoforge | 3.0.28-neoforge-26.2 | ✅ 通过 | loaded and announced |
| 33 | incendium | 模组 | neoforge | neoforge | 5.5.1 | ✅ 通过 | loaded and announced |
| 34 | enhancedvisuals | 模组 | neoforge | neoforge | 1.8.31 | ✅ 通过 | loaded and announced |
| 35 | netherportalfix | 模组 | neoforge | neoforge | 26.2.0.1+neoforge-26.2 | ✅ 通过 | loaded and announced |
| 36 | c2me-fabric | 模组 | — | — | — | ❌ 失败 | no build for a runtime we host: publishes only fabric (loaders: fabric) |
| 37 | discordsrv | 插件 | paper | paper | 1.30.5 | ✅ 通过 | loaded and announced |
| 38 | inventoryhudplus | 模组 | — | — | 3.4.34 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 39 | vnc | 模组+插件 | paper | paper | 1.2.1 | ❌ 失败 | server ready but project absent from mod list |
| 40 | provanish | 插件 | paper | paper | 4.0 | ✅ 通过 | loaded and announced |
| 41 | puzzle | 模组 | — | — | 2.3.1.1+26.2-neoforge | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 42 | betterf3 | 模组 | — | — | 19.0.1 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 43 | item-borders | 模组 | — | — | 1.3.2 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 44 | simple-voice-chat-discord-bridge | 模组+插件 | paper | paper | paper-3.2.1 | ✅ 通过 | loaded and announced |
| 45 | moreculling | 模组 | neoforge | neoforge | 1.8.1 | ✅ 通过 | loaded and announced |
| 46 | zoomify | 模组 | — | — | — | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 47 | crash-assistant | 模组 | — | — | 1.11.14 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 48 | main-menu-credits | 模组 | — | — | 1.4.0+26.2 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 49 | mcwifipnp | 模组 | neoforge | neoforge | 2.1.3 | ✅ 通过 | loaded and announced |
| 50 | neospeedzero | 模组+插件 | paper | paper | 6.4.1+26.2-universal | ✅ 通过 | loaded and announced |
| 51 | crazyauctions | 插件 | paper | paper | 26.1.2-f6e007a | ✅ 通过 | loaded and announced |
| 52 | leashable-players | 模组+插件 | paper | paper | 1.3.0-bukkit | ✅ 通过 | loaded and announced |
| 53 | macaws-trapdoors | 模组 | neoforge | neoforge | 1.1.5 | ✅ 通过 | loaded and announced |
| 54 | ksyxis | 模组 | neoforge | neoforge | 1.4.5 | ✅ 通过 | loaded and announced |
| 55 | dungeons-and-taverns-pillager-outpost-overhaul | 模组 | neoforge | neoforge | v3.3+mod | ✅ 通过 | loaded and announced |
| 56 | tps-hud | 模组+插件 | paper | paper | 2.0.0+26.2 | ✅ 通过 | loaded and announced |
| 57 | entitytexturefeatures | 模组 | — | — | 7.2.5-neoforge-26.2 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 58 | worldedit | 模组+插件 | paper | paper | 7.4.6-beta-02 | ✅ 通过 | loaded and announced |
| 59 | bedsalwaysexplode | 模组+插件 | neoforge | neoforge | 3.1a | ✅ 通过 | loaded and announced |
| 60 | daycounter | 模组 | neoforge | neoforge | 4+mod | ✅ 通过 | loaded and announced |
| 61 | morechathistory | 模组 | — | — | — | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 62 | fusion-connected-textures | 模组 | — | — | 1.3.15b-neoforge-mc26.2 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 63 | prickle | 模组 | neoforge | neoforge | 26.2.0.3 | ✅ 通过 | loaded and announced |
| 64 | yacl | 模组 | neoforge | neoforge | 3.9.7+26.2-neoforge | ✅ 通过 | loaded and announced |
| 65 | placeholder-api | 模组 | — | — | — | ❌ 失败 | no build for a runtime we host: publishes only fabric (loaders: fabric) |
| 66 | libipn | 模组 | — | — | neoforge-26.2-6.9.0 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 67 | optigui | 模组 | — | — | — | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 68 | hopo-better-mineshaft | 模组 | neoforge | neoforge | 1.3.7 | ✅ 通过 | loaded and announced |
| 69 | glitchcore | 模组 | neoforge | neoforge | 26.2.0.0.0 | ✅ 通过 | loaded and announced |
| 70 | civilization-smp | 模组+插件 | — | — | release | ❌ 失败 | routed to Paper but the jar carries no plugin.yml / paper-plugin.yml, so it is not a Bukki |
| 71 | huskhomes | 模组+插件 | paper | paper | 4.11-9ed80cc | ✅ 通过 | loaded and announced |
| 72 | toms-storage | 模组 | neoforge | neoforge | 26.2-2.11.2 | ✅ 通过 | loaded and announced |
| 73 | pv-addon-groups | 模组+插件 | paper | paper | 1.1.1 | ✅ 通过 | loaded and announced |
| 74 | macaws-bridges | 模组 | neoforge | neoforge | 3.1.2 | ✅ 通过 | loaded and announced |
| 75 | axgraves | 插件 | paper | paper | 1.32.1 | ✅ 通过 | loaded and announced |
| 76 | edf-remastered | 模组 | neoforge | neoforge | 5.0.2+mod | ✅ 通过 | loaded and announced |
| 77 | geyser | 模组+插件 | paper | paper | 2.11.3-b1248 | ✅ 通过 | loaded and announced |
| 78 | nbtapi | 插件 | paper | paper | 2.16.1 | ✅ 通过 | loaded and announced |
| 79 | first-person-model | 模组 | — | — | 2.7.3 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 80 | luckperms | 模组+插件 | paper | paper | v5.5.71-bukkit | ✅ 通过 | loaded and announced |
| 81 | supermartijn642s-config-lib | 模组 | neoforge | neoforge | 1.1.8a-neoforge-mc26.2 | ✅ 通过 | loaded and announced |
| 82 | distanthorizons | 模组 | neoforge | neoforge | 3.3.3-26.2 | ✅ 通过 | loaded and announced |
| 83 | flashback | 模组 | — | — | — | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 84 | jei | 模组 | neoforge | neoforge | 30.39.0.232 | ✅ 通过 | loaded and announced |
| 85 | almanac | 模组 | neoforge | neoforge | 1.26.9.1 | ✅ 通过 | loaded and announced |
| 86 | multiverse-core | 插件 | paper | paper | 5.8.1 | ✅ 通过 | loaded and announced |
| 87 | simple-snowy-fix-(forge-fabric) | 模组 | neoforge | neoforge | 2.2.1 | ✅ 通过 | loaded and announced |
| 88 | healing-campfire | 模组 | neoforge | neoforge | 26.2.0-6.4-fabric+forge+neo | ✅ 通过 | loaded and announced |
| 89 | rrls | 模组 | — | — | 5.2.8+mc26.2 | ⏭ 跳过 | Modrinth marks this 26.2 build client_only; no server loader can host it |
| 90 | terrablender | 模组 | neoforge | neoforge | 26.2.0.0.2 | ✅ 通过 | loaded and announced |
| 91 | tcdcommons | 模组 | neoforge | neoforge | 5.5.6+fn-26.2 | ✅ 通过 | loaded and announced |
| 92 | infinite-trading | 模组 | neoforge | neoforge | 26.2.0-5.1-fabric+forge+neo | ✅ 通过 | loaded and announced |
| 93 | quickshop-hikari | 插件 | paper | paper | 6.3.0.3 | ✅ 通过 | loaded and announced |
| 94 | trek | 模组 | neoforge | neoforge | B0.6.2+mod | ✅ 通过 | loaded and announced |
| 95 | macaws-fences-and-walls | 模组 | neoforge | neoforge | 1.2.1 | ✅ 通过 | loaded and announced |
| 96 | superflat-world-no-slimes | 模组 | neoforge | neoforge | 26.2.0-3.7-fabric+forge+neo | ✅ 通过 | loaded and announced |
| 97 | simple-login | 模组+插件 | paper | paper | 1.16.7 | ✅ 通过 | loaded and announced |
| 98 | fzzy-config | 模组 | neoforge | neoforge | 0.7.7+26.2+neoforge | ✅ 通过 | loaded and announced |
| 99 | macaws-biomes-o-plenty | 模组 | neoforge | neoforge | 26.2-1.6 | ✅ 通过 | loaded and announced |

## 五、未通过清单

共 7 项未通过，按根因分组：

### 架构限制：无可用生态构建（4 项）

> 这些项目在 26.2 只发布 fabric（或 fabric + quilt），既无 neoforge/forge 版也无 Bukkit 版。NeoForge 会显式拒绝纯 Fabric jar，而 Sinytra Connector 尚不支持 26.2，因此它们**在本架构下无法进入实例**。这是已知限制而非缺陷 —— 26.2 有 2493 个项目同时发布 fabric 与 neoforge，多生态供给充足，纯 Fabric 独占只是少数。

- **cardinal-components-api**（模组，宿主 未归位，构建 —）
  - 原因：no build for a runtime we host: publishes only fabric (loaders: fabric,quilt)
- **bclib**（模组，宿主 未归位，构建 —）
  - 原因：no build for a runtime we host: publishes only fabric (loaders: fabric)
- **c2me-fabric**（模组，宿主 未归位，构建 —）
  - 原因：no build for a runtime we host: publishes only fabric (loaders: fabric)
- **placeholder-api**（模组，宿主 未归位，构建 —）
  - 原因：no build for a runtime we host: publishes only fabric (loaders: fabric)

### 归位错误：jar 不是 Bukkit 插件（2 项）

> 项目页在 Modrinth 上标注了 paper 加载器，但下载到的 jar 内**不含 `plugin.yml` / `paper-plugin.yml`**，因此不是 Bukkit 插件。这是项目侧信息与产物不一致，不是 AllInOne 的兼容性问题；框架已将其撤档并如实归因，而非让它冒充项目质量缺陷。

- **stringandsand**（模组+插件，宿主 未归位，构建 —）
  - 原因：routed to Paper but the jar carries no plugin.yml / paper-plugin.yml, so it is not a Bukkit plugin
- **civilization-smp**（模组+插件，宿主 未归位，构建 —）
  - 原因：routed to Paper but the jar carries no plugin.yml / paper-plugin.yml, so it is not a Bukkit plugin

### 未出现在加载器清单（1 项）

> 服务端正常就绪，但该 jar 未出现在 Paper 的初始化清单中。典型原因是 Modrinth 上的文件本身是占位符 —— 例如 `vnc` 的 `plugin.yml` 只有一行 `# Placeholder file to upload it into Modrinth`，项目从未发布真正的插件文件。

- **vnc**（模组+插件，宿主 paper，构建 paper）
  - 原因：server ready but project absent from mod list

## 六、跳过清单（Modrinth 标记 client_only）

共 23 项。这些项目由作者显式声明只在客户端运行，专用服务端无法加载，故不计入分母。

- item-highlighter（模组）
- particle-rain（模组）
- cut-through（模组）
- drippy-loading-screen（模组）
- axolotl-buckets（模组）
- malilib（模组）
- entityculling（模组）
- dynamic-fps（模组）
- inventoryhudplus（模组）
- puzzle（模组）
- betterf3（模组）
- item-borders（模组）
- zoomify（模组）
- crash-assistant（模组）
- main-menu-credits（模组）
- entitytexturefeatures（模组）
- morechathistory（模组）
- fusion-connected-textures（模组）
- libipn（模组）
- optigui（模组）
- first-person-model（模组）
- flashback（模组）
- rrls（模组）

## 七、后续建议

### 1. 唯一可行的扩展方向是等桥接层支持 26.2

Sinytra Connector 的全部支持版本止于 `1.20.1 / 1.21 / 1.21.1 / 26.1.2`，
没有 26.2。26.2 生态里 fabric AND neoforge 联合发布的项目有 2493 个，
供给侧足够，因此本项目的多生态路线短期内不会失效；但纯 Fabric 独占项目
（本轮 4 个）在架构上永远无法进入实例，这是限制而非缺陷。
Connector 一旦发布 26.2 版本，把 fabric 族改为由 Connector 承载即可，
无需改动归位与判定逻辑。

### 2. 判定层应从 jar 元数据扩展到运行时自述

本轮已从 `META-INF/neoforge.mods.toml` 读 mod_id、从 `plugin.yml` 读插件名，
解决了 `jei` / `Orebfuscator` 这类 slug 与运行时名不一致的假阴性。
剩余可改进项：Paper 未提供稳定的插件清单 API，目前依赖解析启动日志文本。
若将来改用 Paper API 查询插件列表，可消除对日志格式的依赖。

### 3. 依赖闭包目前只展开 required

本轮闭包 99 个节点。`optional` 与 `incompatible` 依赖未处理。
26.2 生态中 optional 依赖常见于前置库（如 Cloth Config），若目标模组把关键
库声明为 optional，闭包会缺项。下一版应把 optional 中被多方共同引用的库
纳入闭包，并对 incompatible 依赖做冲突检测与报告。

### 4. 无法归位与失败应分开统计

本轮 4 个「无可用生态构建」与 3 个「项目侧问题」性质不同：前者是架构限制，
后者是项目自身缺陷（VNC 的 plugin.yml 只是 Modrinth 上传占位文件）。
建议后续在报告中持续保持这两类的区分，避免把架构限制误读为兼容性问题。

