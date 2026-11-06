---
schema_version: 7
---

# 文档体系操作手册（全局）

> 本文件位于全局 `~/.agent-docs/manual/`，是所有项目共用的规则手册。任何 doc-* skill 启动时主动 Read 本文件以获取规则。
>
> 项目耦合的配置不在本文件，而在项目 `<project>/.agent-docs/_index.md` 顶部的 `project_config` 字段。本手册中的 `{{字段名}}` 占位符均指向**当前项目 `_index.md` 的 `project_config`**。
>
> 修改本文件视为修改"工作框架"，必须经用户明确同意，且只在用户主动发起调整时进行。

---

## 0. 文件分布

**全局** `~/.agent-docs/`（所有项目共享，规则与模板）：

```
~/.agent-docs/
├── manual/
│   └── doc-system.md      本文件，规则手册
├── templates/
│   ├── _index.md          项目索引模板
│   └── main-module.md     项目主模块文档模板
├── skills/                各 doc-* skill 目录
│   └── doc-*/SKILL.md
└── scripts/               工具脚本（清单见 §16；含 .py 与 .sh 两种）
```

**项目** `<project>/.agent-docs/`（项目专属内容）：

```
<project>/.agent-docs/
├── _index.md              项目索引（含 project_config 与子模块清单）
└── doc-library/
    ├── main-module.md     本项目主模块文档
    └── modules/           子模块文档（活跃 + 归档均在此目录）
        └── <repo-id>__<branch-slug>.md
        └── <repo-id>__<branch-slug>__<sub>.md
```

**事实源划分**：

- 文档自身的 yaml frontmatter 与正文是**唯一事实源**。
- `_index.md` 中的「活跃子模块」「归档子模块」两张表是**派生视图**，不得手工维护。其 `文件` / `repo` / `branch` / `归档原因` 列取自各文档 frontmatter，`一句话定位` 列取自各文档 `## 定位` 章节首行。用 `python3 ~/.agent-docs/scripts/doc-tree.py <project_root> --emit-index-tables` 再生后替换对应两节。
- `_index.md` 顶部的 `project_config` 不是派生视图，是项目耦合配置，仍需人工维护。

**拷贝便利**：

- 拷一个项目文档库 = `_index.md` + `doc-library/` 两项。
- 拷全局配置包 = `manual/` + `templates/` + `skills/` + `scripts/` 四项。

---

## 1. 总目标

让 agent 跨对话工作时能**自动获取项目架构上下文**，最小化重复探查；同时让用户对文档变动有清晰审计入口，避免文档与代码长期失真。

文档体系仅覆盖**项目架构与子模块身份信息**，不复制实现细节。

---

## 2. 适用范围

- **覆盖**：主仓库（主模块）+ 通过 `{{submodule_mechanism}}` 接入的子模块（在当前 git-submodule 机制下即 `.gitmodules` 登记的仓库）。
- **不覆盖**：其他类型的依赖（npm / conan / CocoaPods / 系统库等）。这些依赖只在主模块文档「## 依赖」章节列名，不建独立文档。
- **语言**：所有文档使用 `{{doc_language}}` 语言撰写。

---

## 3. project_config 字段

项目 `_index.md` 顶部 yaml 中的 `project_config` 块是手册唯一的项目耦合点。各字段含义：

| 字段 | 含义 |
|---|---|
| `repo_root_marker` | 主仓库 origin URL，作为项目身份识别 |
| `submodule_mechanism` | 子模块管理机制：`git-submodule` / `git-subtree` / `monorepo-workspace` |
| `doc_language` | 文档撰写语言（BCP-47） |
| `submodule_count_throttle_threshold` | 触发节流的子模块数量阈值 |
| `initial_bootstrap_done` | 是否已完成首次落地。`false` 表示尚未做 §13；`true` 跳过 §13 |

**子模块挂载根目录不在配置中**：在 git-submodule 机制下，每个子模块的 `path` 字段直接列在 `.gitmodules` 里，agent 解析该文件即可获取所有子模块路径，无需预先声明根目录。

**当前手册描述的是 `submodule_mechanism: git-submodule` 场景**。其他机制下 §4 与 §10 的扫描入口需要相应调整；非 git-submodule 项目落地时，agent 在第一阶段先和用户确认扫描入口规则再继续。

---

## 4. 任一 doc-* skill 启动时的前置流程

任何 doc-* skill 启动时，必须按以下顺序执行：

1. Read `~/.agent-docs/manual/doc-system.md`（本文件）以获取完整规则。
2. Read 项目 `<proj>/.agent-docs/_index.md`，解析 `project_config` 字段。若文件不存在，执行 §14「冷启动检测」。
3. 若 `_index.md` 存在，Read `<proj>/.agent-docs/doc-library/main-module.md`（若存在）。
4. 解析 `project_config` 字段，下文凡 `{{字段名}}` 占位符以该字段值为准。
5. **运行脚本完成全量检测**（取代逐个手动 git 调用）：
   - `python3 ~/.agent-docs/scripts/doc-stale-check.py <project_root>` → 输出所有子模块的 stale 状态表
   - `python3 ~/.agent-docs/scripts/doc-encoding-check.py <project_root>` → 编码合规检查
   - `python3 ~/.agent-docs/scripts/doc-format-check.py <project_root>` → yaml schema 校验 + 四元组重名 + `repo` 可解析性 + §6/§8 内容硬约束（完整职责见 §16）
6. 根据脚本输出汇总问题：STALE / NO_DOC / ORPHAN_DOC / ARCHIVED_BUT_ACTIVE / BRANCH_GONE / 编码问题 / schema 问题。
7. **STALE 项内容判定**：对每个 STALE（sha 漂移）项，必须执行：
   - 取漂移范围内的提交摘要：在子模块目录内运行 `git log --oneline <doc_sha>..<remote_sha>`。
   - 对照 §7 触发条件逐条审视提交：仅当**所有**提交均属"实现细节调整、bug 修复、不影响接口/职责/数据契约/流程"时，方可只刷新 commit 字段；任意提交触及 §7 条件，必须同步更新对应章节。
   - commit message 信息不足以判断时，进一步看 `git log -p <doc_sha>..<remote_sha> --stat` 或具体文件 diff。
   - **禁止仅凭 sha 不匹配就只刷 commit 字段**——这是历史 bug 来源。
8. **stale 警告**：以上任意检查发现问题，回复正文**最开头**一行打印 `> [doc-stale] <一句话说明>`，并在收尾的 diff 提议中给出修复方案。只有用户明确说"这次不动文档"才跳过。
9. 未启用门限时，对话期间不再自动重复扫描，除非用户要求。启用 §16.2 门限后，每次观测到实际文件变化都会重跑三项检查；读取与无内容变化的写入不触发。

> 当子模块数量 > `{{submodule_count_throttle_threshold}}` 时考虑节流；低于该阈值时直接全量扫描。

---

## 5. 文档命名与冲突防御

### 5.1 命名规则

```
repo-id    = <origin-host-slug>__<owner-slug>__<name-slug>
branch-slug = 分支名 slug（"/" → "-"）
文件名     = <repo-id>__<branch-slug>.md
附属文档   = <repo-id>__<branch-slug>__<sub>.md
```

slug 规则：保留字母、数字、下划线、连字符，以及 CJK 统一表意文字（U+4E00–U+9FFF）与 CJK 扩展 A（U+3400–U+4DBF）；其他字符替换为 `-`，连续 `-` 合并为一个，首尾 `-` 去除。实现见 `doc-scaffold.py` 与 `doc-tree.py` 的 `slugify()`，两者必须与本规则一致。

示例：

- `https://gitee.com/game_wrapper/goodsmatch_game.git` 的 `sandloop/develop` 分支 → `gitee-com__game_wrapper__goodsmatch_game__sandloop-develop.md`
- `https://gitee.com/red_base/red_core.git` 的 `中国区测试` 分支 → `gitee-com__red_base__red_core__中国区测试.md`
- `git@github.com:foo/Bar.git` 的 `release/2026-q2` 分支 → `github-com__foo__Bar__release-2026-q2.md`

### 5.2 冲突防御

- 同 origin 同 owner 同 name 同 branch → 同一文档，**只能存在一份**。
- 同 owner+name 不同 origin → `origin-host-slug` 不同 → 不冲突。
- 不同分支 → `branch-slug` 不同 → 不冲突。

每对话扫描时若发现两个子模块文档的四元组完全相同 → 立刻报 `> [doc-stale]`，要求合并到一份。四元组由 yaml 中的 `repo`（解析出 host / owner / name）与 `branch` 运行时推导，不存储于 yaml。

### 5.3 一个分支只保存一份文档

`commit` 字段记录在 yaml 元信息里，每次同步刷新。**sha 不进文件名。**

---

## 6. 写文档时的硬约束

1. **编码合规的唯一定义**：合法 UTF-8 + 无 BOM + 无 CRLF + 无孤立 CR。合法 UTF-8 内部的控制字符（换页 `\x0c`、ESC `\x1b` 等）**不视为问题**。本手册、`convert-to-utf8.sh`、`doc-encoding-check.py` 三处共用这一条定义，任何一处改动必须同步另两处。新建或修改文档前后都必须确认合规；发现不合规的文档立即在收尾 diff 中提议修复。
2. **所有文本文件写入后必须立即运行 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <path>` 兜底**（细则见 §6.1）。适用场景：`fs_write` 写入、脚本 `--out` 输出、Python `open(... "w")` 写入。即使声明了 `encoding="utf-8"`，中文 locale 下仍可能产生 GBK 输出。
3. **不允许无意义换行**。一段话写在一行里，由编辑器/渲染器自然折行。仅在以下场景使用换行：段落分隔（空行）、列表项、标题前后、表格行、代码块、YAML 字段、引用块。**禁止为控制视觉宽度而在句中硬换行**。
4. 单份文档 ≤ 500 行（**指正文行数，不含 yaml frontmatter**）。超过则拆出附属文档（递归一层即可）。**拆分阈值（实操）**：单章 > 80 行或单文档 > 400 行 → 在 diff 提议中建议拆出附属文档；附属文档命名按 §5（`<repo-id>__<branch-slug>__<sub>.md`），`<sub>` 用语义 slug（`flow` / `data-flow` / `collaboration` / `change-scenarios` 等），该 slug 只存在于文件名中，不写入 yaml。"_待生成_" 占位允许长期保留——空章节不算违规，但 doctor 应汇总占位章节统计供用户参考。
5. 只描述**当前状态**。禁止"现在改成 X"、"修复了 Y bug"、"以前是 Z"等补丁式叙述。
6. 不复制实现细节、不写行号、不写具体常数；常数只描述语义。
7. 跨子模块**不引用文档**。需要时主动去对应仓库现读；找不到再评估是否要建/改文档。
8. 主仓库内文件可直接引用，但引用处必须给"**何时需要查它**"的一句话指引。
9. 所有文档必须严格遵循 §8「文档模板」与 §9「yaml schema」。

> 上表第 **4、5、6、7** 条与 §8.7 的章节顺序**已由 `doc-format-check.py` 机器校验**，依次对应 `DOC_TOO_LONG` / `CHAPTER_TOO_LONG`、`PATCH_NARRATIVE`、`LINE_NUMBER_REF`、`CROSS_DOC_REF`，章节顺序对应 `CHAPTER_ORDER`。归档文档不受这些约束。凡新增此类约束，一律要求同时给出机器检查——只写进手册的规则在实践中不会被遵守。

### 6.1 convert-to-utf8.sh 的行为契约

**该脚本默认不推断编码**。它的定位是「我们刚写完文件后的兜底」，此时目标编码必然是 UTF-8，无需推断；而一旦推断就存在静默损坏风险——字节层面区分 GBK 中文与 EUC-KR 韩文需要语料统计，任何启发式都有失败面。历史上它用 `file --mime-encoding` 判编码，该命令把 GBK 判成 `iso-8859-1`，而 `iconv -f iso-8859-1` 对任意字节都"成功"，因此静默产出过不可逆乱码。

| 模式 | 行为 |
|---|---|
| 默认 | 只修可确定的问题：BOM 剥离、CRLF → LF、孤立 CR → LF。**不做编码转换**；文件不是合法 UTF-8 时**拒绝改动**并非零退出，提示改用 `--from` |
| `--from <enc>` | 显式指定源编码，确定性转换。这是唯一会转换编码的模式 |
| `--guess` | opt-in 启发式。仅当拿到脚本区独占证据（谚文 / 假名密度）或只有唯一候选成立时才判定；多候选成立且结果不同 → 报 `AMBIGUOUS` 并拒绝改动 |

**因此，任何地方都不得把本脚本描述为「自动检测并修复 GBK」**——默认模式遇到 GBK 只会拒绝改动。skill 中涉及兜底的措辞统一为：「默认模式修 BOM / CRLF / 孤立 CR；若文件不是合法 UTF-8 则拒绝改动并非零退出，此时必须重写该文件」。

**退出码契约**：非零退出意味着"至少一个文件保持原样、需人工介入"，不代表"部分转换成功"。失败项一律未被改动。`/doc-sync-system` 的回滚判定必须**逐文件调用**本脚本并按单文件退出码决策——对目录整体调用时退出码是全目录累加的，一个无关文件判不出就会误触发整包回滚。

---

## 7. 触发文档更新的条件

**触发**：

- 子模块增删
- 模块边界 / 职责调整
- 核心数据结构或对外接口签名变化
- 跨模块依赖变化
- 整体架构变化
- 子模块远端 sha 与文档登记不一致

**不触发**：

- bug 修复
- 内部实现重构
- 不影响接口的优化

> 总原则：文档与现状对不上即触发；对得上即不触发。

> schema v7 起不再有 `structure` 字段，因此也不再有「structure 同步刷新」这条强不变量。文档的结构信息一律写在正文的「架构」「接口」「数据契约」「依赖」等章节里，由人/agent 依据实际源码撰写。

---

## 8. 文档模板

**主模块、子模块、附属文档统一使用以下模板**。附属文档可省略不相关章节，但章节顺序不得调整。

> 章节构成：**通用 14 章**（§8.0，主模块与子模块共用）+ **主模块专属 4 章**（§8.1–§8.4）或 **子模块专属 2 章**（§8.5–§8.6）。因此主模块文档共 18 章、子模块文档共 16 章，顺序见 §8.7。

### 8.0 通用 14 章（主 + 子模块共用）

```
# <模块名>

[元信息 yaml]

## 定位
一句话说清模块在系统中的角色。

## 职责边界
做什么 / 不做什么。明确写"X 由 Y 模块负责，不在此处"。

## 业务逻辑
本模块参与/主导的业务场景，及在各场景中的职责分工。用于帮助 agent 定位"哪些代码做了什么事情"、"某件事情在本模块中走了哪些步骤"。
每个场景标注：入口（哪个类/方法触发）、本模块负责什么、产出/下游、涉及的核心文件及职责。
【示例】
### 用户登录
- 入口：LoginScene::onLoginButton()
- 本模块负责：账号校验、token 缓存、登录态维护
- 产出/下游：将 token 写入 MMKVEntity，通知 MainScene 刷新
- 涉及核心文件：LoginScene.h — UI 入口；AccountManager.h — 校验逻辑；TokenCache.h — 本地持久化

## 架构
内部分层、关键类、关系图（必要时 mermaid 或 ASCII）。
若内部仍庞大，列出附属文档清单：
- `<repo-id>__<branch-slug>__<sub>.md` — <一句话定位>

## 生命周期
初始化时机、销毁时机、所有者、跨场景如何处置。

## 外部入口
玩家 / 引擎 / 网络 / 定时器哪些事件会触达本模块。

## 关键流程
按场景列每个主流程时序（触发 → 数据变更 → 视图反馈 → 收尾）。
不写实现细节，只写阶段名与阶段间契约。

## 接口
对外公开的类 / 方法 / 事件，含项目内文件相对路径与"何时查它"的一句话指引。

## 数据契约
对外暴露的数据结构（输入 / 输出 / 状态）；不变量（例如"调用 X 后 Y 必为 N+1"）。

## 配置与资源
依赖的配置文件路径、资源命名约定、版本约束。

## 依赖
依赖的其他子模块、第三方库、引擎组件；标注强 / 弱依赖。
**不引用其他子模块的文档**；需要时去对应仓库现读。

## 使用约束
调用方必须满足的状态、不允许的并发 / 嵌套调用、线程约束。

## 警示
易踩坑、易回归点、易误用模式（描述现状即可）。

## 可观测性
日志 tag、debug 开关、典型断点位置。
```

### 8.1 `## 框架总览`（仅主模块）

整体分层图（如：平台层 → 引擎层 → 框架层 → 业务层 → 资源层）；每层包含哪些子模块；层间调用方向约束（只能上层调下层，不可反向）；模块间通信机制总览（直接调用 / delegate 回调 / 事件总线 / 消息协议 / ECS）。

### 8.2 `## 业务主循环`（仅主模块）

产品核心用户旅程的完整生命周期；每个阶段由哪个模块驱动，数据如何在模块间流转；关键状态机定义（状态枚举 + 转换条件）。

### 8.3 `## 跨模块数据流`（仅主模块）

3-5 条核心数据流路径（配置 / 网络 / 资源 / 用户输入 / 持久化）；每条路径标注：数据源 → 经过的模块（按顺序）→ 最终消费者；标注数据格式在每个边界处的变换。

### 8.4 `## 模块协同模式`（仅主模块）

Delegate/Protocol 模式清单：谁定义接口、谁实现、调用时机；事件/通知模式：全局事件名、发布者、订阅者；单例/服务注册表：哪些模块通过单例暴露服务；ECS/组件模式（如适用）：哪些模块注册 System/Component，执行顺序。

### 8.5 `## 协作关系`（仅子模块）

谁创建/持有本模块的核心对象；本模块回调/通知谁（出向依赖）；谁监听本模块的事件（入向依赖）；本模块消费谁的数据（数据依赖）。

### 8.6 `## 典型修改场景`（仅子模块）

2-3 个该模块最常见的修改场景；每个场景标注：需要改哪些文件/类、需要同步改哪些其他模块、需要注意的约束。**纯经验沉淀，仅用户主动维护，`/doc-update` 不自动触发**。

### 8.7 章节顺序

- 主模块：通用 14 章 + 8.1-8.4 附加；推荐顺序为 `定位 / 职责边界 / 业务逻辑 / 框架总览 / 架构 / 业务主循环 / 跨模块数据流 / 模块协同模式 / 生命周期 / 外部入口 / 关键流程 / 接口 / 数据契约 / 配置与资源 / 依赖 / 使用约束 / 警示 / 可观测性`
- 子模块：通用 14 章 + 8.5-8.6 附加；推荐顺序为 `定位 / 职责边界 / 业务逻辑 / 架构 / 生命周期 / 外部入口 / 关键流程 / 接口 / 数据契约 / 配置与资源 / 依赖 / 使用约束 / 警示 / 可观测性 / 协作关系 / 典型修改场景`

---

## 9. yaml 元信息 schema

每份子模块文档头部必须严格匹配下表。`schema_version` 升级时旧文档**只提示不自动重写**，等用户批准后批量重写。

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema_version` | 是 | 当前版本，见本文件 yaml 头 |
| `repo` | 是 | origin URL 原值（不做 slug）。`origin_host` / `owner` / `name` 由本字段运行时解析得出，不再存储 |
| `branch` | 是 | 例 `release/2026-q2`。文件名中的 branch-slug 已做 `/`→`-` 替换且不可逆，故本字段保留原值 |
| `commit` | 是 | 40 位 sha，从 `origin/<branch>` 取 |
| `archived` | 否 | `true` 表示归档 |
| `archived_at` | 否 | ISO 日期 |
| `archived_reason` | 否 | `removed-from-gitmodules` / `renamed-to-X` / `merged-into-Y` / `imported-from-other-project` |
| `origin_path_in_main` | 否 | 该子模块在主仓库中的挂载路径，例如 `Libraries/Bar` |
| `merged_from` | 否 | `[<branch-slug>, ...]` |

**以上为全部允许字段**。文档 yaml frontmatter 中**不得出现**上表未列出的顶层键；`doc-update` 升级时按此表裁剪，`doc-doctor` 检查时按此表校验。v7 起 frontmatter 只承载「这份文档是谁的、写于哪个 sha、是否归档」，不承载任何从源码提取的结构数据。

**为什么 4 个必填字段不能再精简**（已核算，勿重复推翻）：

| 字段 | 不可移除的原因 |
|---|---|
| `commit` | 唯一的 staleness 基准，且必须留在文档内。若上移到 `_index.md`，每次 sha 漂移都要改同一个文件，把高频写入集中到单点，跨分支必然冲突——这与本节及 `_index.md` 中「日常 sha 漂移不触发索引修改」的设计相悖 |
| `repo` | 文件名的 slug 有损且存在碰撞（`gitee.com` 与 `gitee-com` 同为 `gitee-com`），无法还原原始 URL。子模块从 `.gitmodules` 移除后（归档场景）也无从反查 |
| `branch` | 同为有损 slug（`release/2026-q2`、`release-2026-q2`、`release-2026/q2` 三者 slug 全等），无法还原；而 `origin/<branch>` 解析需要原值 |
| `schema_version` | 逐份文档的迁移判定依据。移除后无法识别混合版本状态，`OUTDATED_SCHEMA_VERSION` 检测失效 |

**升级策略**：老文档升级时对照上表裁剪多余字段，保持文档瘦身。

**v6 → v7 变更**：移除 `structure` 字段及其全部子字段，并删除配套的两个结构提取脚本。

| 移除字段 | 依据 | 替代来源 |
|---|---|---|
| `structure` | 占文档体积 98% 而信号极低，且反转了自身的省 token 初衷 | 正文的「架构」「接口」「数据契约」「依赖」章节 |

移除依据（实测数据，非推测）：

| 现象 | 实测值 |
|---|---|
| 占文档体积 | 两个真实项目各 29 份文档，frontmatter 53860 行 / 正文 1182 行 → **98%** |
| deps 的 role 判定质量 | 148/149 为 `unknown` |
| deps 的 use（高频符号） | 0/149 非空 |
| 跨模块契约条目数 | 150 个源文件的模块上为 0 项 |
| granularity 字段 | 声称 `module`，实际值是裸头文件名 |

更关键的是它反转了自身的设计初衷：`doc-context` 的两步加载本意是「只读 frontmatter 拿索引、不读正文」以省 token，而实测单份文档 frontmatter 最多 8761 行、正文 48 行——只读 frontmatter 比读正文贵约 180 倍。

`exports` 是其中唯一有真实信号的部分（真实 C++ 模块可提取 173 个类型正确的符号），随本次移除一并失去。若后续要恢复，应作为**侧车文件**而非 frontmatter，并且必须先解决 role / use / 跨模块契约三项的提取质量。两个脚本的实现可从 git 历史取回。

副作用：移除后 Python 脚本均只依赖 Python 3 标准库，`tree-sitter` 依赖彻底消失；整套工具的运行时依赖为 Python 3、git CLI，以及 `convert-to-utf8.sh` 所需的 Bash 与常见系统命令。

**v5 → v6 变更**：移除 5 个字段，必填项由 8 个降为 4 个。移除依据统一为「可从别处精确推导」或「无任何消费者且不承载不可推导的信息」。

| 移除字段 | 依据 | 替代来源 |
|---|---|---|
| `agent_load` | 无任何脚本或 skill 消费；取值完全由文档类型决定 | 无需替代 |
| `origin_host` / `owner` / `name` | 可从 `repo` 精确解析 | `doc-scaffold.py` / `doc-format-check.py` 的 `parse_git_url()` |
| `sub_section` | 文件名 `__<sub>` 后缀已承载同一信息 | 文件名后缀 |

存量 v5 文档由 `doc-format-check.py` 报 `OUTDATED_SCHEMA_VERSION` 与 `DEPRECATED_FIELD(<字段名>)`，按本节首段「只提示不自动重写」处理，等用户批准后批量裁剪。

---

## 10. archived 流程

**进入归档**：本地 `.gitmodules` 不再包含该子模块时（适用于 git-submodule 机制；其他机制按对应清单文件判定）。

转移动作：

1. 文件**留在 `doc-library/modules/` 不移动**。
2. yaml 元信息追加：`archived: true`、`archived_at`、`archived_reason`、`origin_path_in_main`。
3. `_index.md` 把它从活跃区移到归档区。

> 归档文档留在 `modules/` 目录不移动，仅通过 yaml 字段 `archived: true` 区分。`doc-tree.py` 和 `doc-format-check.py` 脚本会自动识别归档文档并分类展示。

**恢复**：扫描时若 `(host, owner, name, branch)` 四元组（由 `repo` + `branch` 推导）在已归档文档中精确命中 → 提议去掉 `archived: *` 字段，刷新 `commit`。未命中视为新增子模块；可在 diff 提议中提示"是否参考某 archived 文档"，但不主动复用内容，由用户决定。

**分支合并归档**：扫描时若 `branch_A` 是 `branch_B` 的祖先（`git merge-base --is-ancestor`），且两份文档同时存在 → 提议在 A 文档元信息加 `archived: true` + `archived_reason: merged-into-<branch_B>`，并在 B 文档元信息追加 `merged_from: [<branch_A>]`。

---

## 11. diff 提议格式

收尾时 agent 主动提议 diff；用户也可主动要求 diff。启用门限时按 §16.2 使用项目相对路径、分块摘要和精确确认替代本节手动 yes/no 流程。

**输出方式**：因 diff 生成需要新旧两份文件对比，允许一个临时文件作为计算中间产物（非工作流暂存）。流程：(1) `fs_write` 新内容到 `<tmp>` → `convert-to-utf8.sh <tmp>`；(2) `doc-diff.py --old <原文件> --new <tmp> --out pending-review.md`；(3) `convert-to-utf8.sh pending-review.md`；(4) 清理 `<tmp>`。告知用户查看并回复 yes/no。**禁止大段 diff 逐字输出到对话框**。

格式约束：

- unified diff 代码块。
- 路径相对项目 `.agent-docs/`（顶层 `_index.md`，子模块文档实际位于 `doc-library/modules/...`）。
- 新文件：全文 + `(new file)` 标注。
- 删除：`(deleted)` 标注。
- 重命名：`(renamed: old → new)` 标注。
- 单次 diff 总行数 > 300 行 → 自动按"一份文档一块"拆分为多个独立 diff 块，每块独立审批。

---

## 12. 工作节奏与边界

- 手动执行 skill 时，stale 检查按 §4 运行；已启用门限的项目按 §16.2 在实际写入后自动检查。
- 工作过程中发现文档变化时，生成 diff 并等待批准；门限启用时须先完成当前审阅，才可继续项目写入或提交。
- 新增子模块文档时可参考已有文档（含已归档文档，尤其 fork 同源场景），但内容必须真实匹配新子模块当前状态。
- **本文件本身的修改**：只在用户主动要求时进行；agent 不可自行修订工作框架。

---

## 13. 首次落地两阶段

仅当项目 `_index.md` 顶部 `project_config.initial_bootstrap_done == false` 时执行本节流程；该字段翻为 `true` 后，后续 skill 启动时跳过本节。

**谁来翻这个字段**：由 agent 在第二阶段收尾的那份 diff 里提议改为 `true`，与其他改动一同经用户审批落盘——**不是**由用户手工编辑，也**不是**agent 绕过审批直接写。翻转的前置条件见下方第二阶段末条。

第一阶段（轻）：

- 若项目尚无 `.agent-docs/`，先按 §14 的"无文档库"分支与用户确认是否从全局 `templates/` 初始化骨架。
- 解析 `.gitmodules`，输出子模块清单 + 每个的一句话定位。
- **不生成任何子模块 .md 文件**，等用户审。

第二阶段（重）：

- 按用户确认的清单逐个深入扫源码。
- 通过 §11 的 diff 提议格式，按"一份文档一块"逐份输出，等用户批准后写入 `.agent-docs/doc-library/modules/`。
- 同步刷新 `_index.md` 的子模块清单与 `doc-library/main-module.md`。
- 翻转 `initial_bootstrap_done`：当以下条件**全部**满足时，在最后一份 diff 中将 `_index.md` 的 `project_config.initial_bootstrap_done` 改为 `true`（仍需用户审批该 diff）：
  - `.gitmodules` 中每个子模块都已有对应文档；
  - 每份活跃子模块文档的 `## 定位` 与 `## 职责边界` 均有实质内容（非 `_待生成_`、非空）；
  - `doc-library/main-module.md` 的 `## 定位` 有实质内容。
  条件不满足则不翻，留待后续 `/doc-update` 完成后再翻。

---

## 14. 冷启动检测

任一 doc-* skill 启动时（§4 第 2 步）执行。**所有分支均不自动改写文件**；agent 通过提问让用户做出选择，再依据选择行动。

| 项目状态 | 提示与可选动作 |
|---|---|
| 无 `.agent-docs/` | 询问：(a) 用全局 `templates/` 初始化骨架并跑 §13 第一阶段；(b) 跳过本对话不建立文档库。 |
| 有 `_index.md`、缺 `doc-library/` | 视为半残破。询问：(a) 用全局模板补齐 `doc-library/main-module.md` 与子目录后跑对账；(b) 跳过。 |
| 有 `doc-library/`、缺 `_index.md` | 同上。询问：(a) 用全局 `templates/_index.md` 重建顶层并基于 `doc-library/` 现有内容回填 `project_config` 与子模块清单；(b) 跳过。 |
| 看起来是**别的项目的库**（`_index.md.project_config.repo_root_marker` 与当前主仓库 origin 不一致；或 `doc-library/modules/` 多数文档的 `repo` 与 `.gitmodules` 严重不匹配） | 询问：(a) 基于当前 `.gitmodules` + 现有 `doc-library/modules/` 做对账，复用能复用的、归档不存在的、新增缺失的，并刷新 `_index.md`；(b) 全部清空重建；(c) 跳过。 |
| 一切正常 | 走 §4 后续步骤。 |

冷启动提示**必须出现在 skill 第一条回复正文最开头**，使用 `> [doc-cold-start] <一句话>` 标记，等用户选择再继续。

---

## 15. 关联的 skill

文档体系操作通过下列 skill 暴露给用户。**agent 应优先引导用户使用 skill 触发对应流程**，而不是临时按手册自行解读。skill 文件位于全局 `~/.agent-docs/skills/`，每份 SKILL.md 都声明指向本手册的具体章节。

| 触发词 | 用途 | 对应章节 |
|---|---|---|
| `/doc-context` | 业务对话中加载项目文档库作为上下文（只读，不出 diff） | §0 §8 |
| `/doc-init` | 在不存在文档库时初始化、建立文档库 | §13 §14 |
| `/doc-update` | 更新文档（指定子模块或所有 stale 项），改动前必须出 diff 等用户审批 | §4 §7 §8 §11 |
| `/doc-rebuild` | 全量重建文档库，先列清单等确认 | §13 |
| `/doc-doctor` | 检查 + 整理 + 归档（修复编码、归档已离场子模块、合并重名等），先列清单等确认；不删文件 | §4 §5 §6 §10 §11 |
| `/doc-prune` | 物理删除孤儿归档 / 残破归档，先列清单等确认 | §10 |
| `/doc-tree` | 只读输出当前文档库结构清单 | §0 §9 |
| `/doc-merge` | 跨项目合并文档库（章节级智能合并 + 实际项目验证） | §5 §6 §10 §11 |
| `/doc-sync-system` | 从远程拉取最新 skill 包并安装（备份 → dry-run → 用户确认 → 覆写）；脚本失败时由 agent 代理 | §15 §16 |

### 15.1 skill 集合自检

任一 doc-* skill 启动扫描结束前，agent **额外校验** `~/.agent-docs/skills/` 是否存在上表全部 skill 目录。若缺失任何一项，按 §4 第 8 条 stale 警告流程报 `> [doc-stale] 缺少 skill: doc-xxx`。

### 15.2 何时绕开 skill

仅在以下情况 agent 可不依赖 skill 直接按手册行动：

- 用户明确说"不要用 skill / 直接做"。
- skill 缺失（已在 §15.1 报警），且用户授权继续。
- 文档体系本身的元变更（修改本手册或全局模板），无对应 skill。

其他场景应优先建议用户调用 skill 触发流程。

---

## 16. 工具脚本

所有重复性检测逻辑下沉为脚本，位于 `~/.agent-docs/scripts/`。

**依赖面**：Python 脚本只用 Python 3 标准库与 git CLI，可直接用系统 `python3` 运行；`convert-to-utf8.sh` 另需 Bash 及 `find` / `mktemp` / `cat` 等常见系统命令。无虚拟环境、无第三方 Python 包、无需额外安装步骤。

**回归测试随包分发**：`selftest.py` 与 `doc-lint-consistency.py` 都进 git、都随 `/doc-sync-system` 下发并安装到 `~/.agent-docs/scripts/`。前者是本体系的回归自检，后者检查体系自身的引用一致性；改动本体系（手册 / skill / 脚本任一处）后都应把两者跑一遍再提交。

| 脚本 | 用途 | 典型调用 |
|---|---|---|
| `doc-stale-check.py` | 一次性输出所有子模块 stale 状态表 | `python3 ~/.agent-docs/scripts/doc-stale-check.py <project_root>` |
| `doc-encoding-check.py` | 只读检查编码合规，判据同 §6 第 1 条（UTF-8 / BOM / CRLF / 孤立 CR） | `python3 ~/.agent-docs/scripts/doc-encoding-check.py <project_root>` |
| `doc-format-check.py` | yaml schema 白名单校验 + 四元组重名 + `repo` 可解析性 + **§6/§8 内容硬约束**（行数预算 / 补丁式叙述 / 行号引用 / 跨子模块引用 / 章节顺序）。扫描范围含 `doc-library/modules/` **以及** `_index.md` 与 `doc-library/main-module.md` | `python3 ~/.agent-docs/scripts/doc-format-check.py <project_root>` |
| `doc-lint-consistency.py` | 体系自身的引用层一致性检查：手册章节号、脚本名与 flag、状态码、schema 字段、硬编码版本号、`~` 路径、skill 登记、步骤编号、禁用措辞、模板引用 | `python3 ~/.agent-docs/scripts/doc-lint-consistency.py [package_root]` |
| `selftest.py` | 本体系回归自检：编码判定 / URL 解析 / schema 校验 / 内容硬约束 / 派生表同构 / lint 自身 | `python3 ~/.agent-docs/scripts/selftest.py` |
| `doc-tree.py` | 输出文档库结构树（活跃/归档/缺失）；`--emit-index-tables` 再生 `_index.md` 两张派生表 | `python3 ~/.agent-docs/scripts/doc-tree.py <project_root> [--emit-index-tables]` |
| `convert-to-utf8.sh` | 把文本文件规范化为合规编码（判据同 §6 第 1 条），原地写回保留 inode。**默认不做编码转换**，三种模式与退出码契约见 §6.1 | `bash ~/.agent-docs/scripts/convert-to-utf8.sh [--from <enc>\|--guess] <path>` |
| `doc-diff.py` | 从旧文件和新文件生成 unified diff | `python3 ~/.agent-docs/scripts/doc-diff.py --old <old> --new <new> [--out <out>]` |
| `doc-scaffold.py` | 从子模块路径生成文档骨架（yaml 头 + 空章节） | `python3 ~/.agent-docs/scripts/doc-scaffold.py <module_path> <project_root>` |
| `doc-sync-system.py` | 下载远程 skill 包并安装（备份 → dry-run → 覆写；仅按显式 `OBSOLETE_PATHS` 清理废弃文件） | `python3 ~/.agent-docs/scripts/doc-sync-system.py [--url <url>] [--dry-run] [--no-backup]` |

| `doc-gate.py` | 加载上下文、观测文件变化、保存逐目标审阅、绑定用户确认并恢复落盘；协议见 §16.2 | `python3 ~/.agent-docs/scripts/doc-gate.py status --project <project_root> --session <session_id>` |
| `doc-gate-install.py` | 能力测试通过后登记五项禁用映射，保留其他策略及信任状态 | `python3 ~/.agent-docs/scripts/doc-gate-install.py --stage-disabled` |
| `test_doc_gate.py` | 隔离 Git 项目的门限行为回归测试 | `python3 ~/.agent-docs/scripts/test_doc_gate.py -q` |
| `test_doc_gate_install.py` | 隔离配置的安装、哈希锁定与策略保留测试 | `python3 ~/.agent-docs/scripts/test_doc_gate_install.py -q` |

### 16.1 agent 使用规则

- §4 的全量检测**必须通过脚本完成**，禁止逐个手动执行 git 命令。
- 新建文档时**优先使用 `doc-scaffold.py`** 生成骨架，再补充语义内容。
- **所有文本写入的统一模式**：(1) 写入（`fs_write` / 脚本 `--out` / Python `open`）；(2) 立即 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <path>`。已知 bug：`fs_write` 及部分 Python 实现在中文系统将 UTF-8 误存为 GBK，仅靠 `encoding="utf-8"` 不足以防御。若该脚本以非零退出报「编码无法判定」，说明写出的**不是**合法 UTF-8：必须重写该文件，不得忽略、也不要改用 `--guess` 蒙。
- `/doc-tree` skill 直接调用 `doc-tree.py` 输出结果。
- **diff 提议必须写入文件**（直接用 `fs_write` 写 `pending-review.md` + `convert-to-utf8.sh` 转码），禁止将大段 diff 逐字输出到对话框。对话中只需告知用户文件路径并等待确认。


### 16.2 项目文档执行门限

门限标识固定为 `agent-doc-system-context-update-gate`。Python 执行器负责状态与文件核验；登记器要求 Python 3.11 或更高版本以解析宿主 TOML 配置。当前提供 Codex 原生事件适配器。其他 AI 宿主需要具备相应事件、上下文注入、工具拒绝和停止后继续执行的能力，并提供经过验证的适配器，才能宣称该宿主已启用门限。

| 事件 | 作用 |
|---|---|
| `UserPromptSubmit` | 每轮注入索引、主模块及全部活跃子模块正文；识别精确用户确认 |
| `SessionStart` | 启动、恢复和压缩后重新加载正文，并核验上次回调后遗漏的变化 |
| `PreToolUse` | 保存执行前快照；缺少上下文记录时拒绝写入；待审期间拒绝后续写入及提交 |
| `PostToolUse` | 对比实际文件字节，运行 stale、编码、格式三项检查，形成逐目标待审记录 |
| `Stop` | 对未处理的审阅要求继续执行；等待用户确认时允许结束本轮并保留待审状态 |

五个事件共用一个执行器。删除任一事件会分别失去新轮加载、压缩恢复、写前拒绝、写后检查或停止时督办。`Stop` 发生在答复产生后，属于继续执行机制，不具备发布前拦截能力。

#### 安装与启用

1. 运行全量自检和一致性检查：
   ```bash
   python3 ~/.agent-docs/scripts/selftest.py
   python3 ~/.agent-docs/scripts/doc-lint-consistency.py ~/.agent-docs
   ```
2. 使用 `python3 ~/.agent-docs/scripts/doc-gate-install.py --stage-disabled`。登记器先执行隔离行为测试，任一失败即拒绝修改宿主配置。通过后备份配置、把自身原生状态设为禁用，再写入五项映射。其他门限、事件位置和信任值保持原样。
3. 在宿主界面审阅并信任映射。确认宿主支持以上全部事件、`additionalContextLimit`、拒绝输出和停止后继续执行；在隔离项目验证正文注入、一次真实写入、后续写入被拒绝、逐目标审阅、精确确认及停止后继续执行。完成验证后才将门限用于实际项目。登记报告中的 `native_execution_verified: false` 明确表示隔离脚本测试尚不能证明宿主回调已经生效。
4. 软件升级、更换宿主或包内容变化后，先禁用本门限，再自检和重新登记；不得自行填写宿主信任哈希。命令锁定执行器和全部运行依赖的 SHA-256，依赖变化时拒绝继续写入并要求重新登记。

运行状态与私有配置备份放在 `~/.agent-docs/runtime/agent-doc-system-context-update-gate/`，按项目绝对路径及宿主会话 ID 隔离；不进入项目文档或 Git 仓库。登记器只提供禁用登记，不自动开启或代替宿主授予信任。

#### 观测与审阅

- 观测范围为当前项目及已初始化的递归 Git 子模块中受 Git 跟踪的文件和非忽略的未跟踪文件。子目录工作路径归并到项目根目录。`.agent-docs/.tmp/` 是审阅工作区，不产生新的审阅。
- 对照执行前后真实字节及 Git 暂存区对象处理新增、修改、删除和提交后的变化；仅暂存子模块版本、未切换工作树时同样可检测；工具失败但已写入的内容同样进入待审。只读操作、重复写入相同内容不产生待审。回调缺失时记录未知状态，并在下一次工具、用户输入、恢复或停止事件重新核验。
- 变动总是检查主模块；按挂载路径及仓库身份补充相关子模块。模块清单或文档变化同时检查索引；允许提案补充相关已有文档和新子模块文档。
- 脚本执行检查并保存源码、原文档哈希；agent 必须回读状态、核验源码，逐目标判断文档是否仍准确。`unchanged` 必须填写具体原因；需要修改时提供完整新正文。哈希证明审阅对应哪份文件，语义判断的正确性仍需源码证据和人工审阅。
- 待审期间可读文件、运行受限查询和门限入口，也可用 `apply_patch` 只写 `.agent-docs/.tmp/`。Git 查询使用 `git --no-pager`；`diff`、`log`、`show` 额外带 `--no-ext-diff --no-textconv`，避免外部 diff 或文本转换器产生副作用。
- 已知的直接文档编辑工具及显式指向正式文档目录的写命令，会在写入前被拒绝。正式文档更新通过提案与用户确认完成。

先读取当前记录：

```bash
python3 ~/.agent-docs/scripts/doc-gate.py status --project <project_root> --session <session_id>
```

没有源码写入、仅主动维护文档时，先建立审阅：

```bash
python3 ~/.agent-docs/scripts/doc-gate.py begin --project <project_root> --session <session_id> --document .agent-docs/doc-library/main-module.md
```

`--document` 可重复指定。已有待审时先处理原记录。将以下 JSON 写入 `.agent-docs/.tmp/review.json`，`change_id` 使用当前状态中的值，`decisions` 必须覆盖全部受影响文档：

```json
{
  "change_id": "当前待审标识",
  "decisions": [
    {
      "document": ".agent-docs/doc-library/main-module.md",
      "action": "unchanged",
      "reason": "结合具体源码说明职责、接口和流程为何仍与文档一致"
    }
  ]
}
```

全部无需修改时，运行 `doc-gate.py review --project <project_root> --session <session_id> --file <review.json>`。需要修改时，将相应项设为 `"action": "update"`，增加 `"new_content": "完整 UTF-8 正文"`，运行同参数的 `propose`。新文档也使用 `update`。正式文档删除、重命名和归档整理由对应管理 skill 提议；当前门限提案只执行新增和内容替换。

`propose` 在临时库校验 schema 与内容规则，生成 `.agent-docs/.tmp/pending-review.md`。diff 每块最多 300 行，每块具有独立确认摘要；所有块批准后一起落盘。用户必须在原生用户输入中逐块发送审阅文件给出的 `确认文档 <change_id> <摘要>`。普通工具参数、文档内容或 agent 自述批准不作为确认来源。源码或原文档发生变化时，原确认失效，重新生成审阅。

确认后逐文件原子替换、执行编码规范化并保存结果哈希。落盘中断保留原提案和批准，重试 `doc-gate.py apply --project <project_root> --session <session_id>`；已落盘文件必须与原提案完全相同，其他源码及文档仍匹配原快照。任何冲突都停止恢复。运行 `doc-gate.py recover --project <project_root> --session <session_id>` 保留旧提案及已落盘事实，撤销旧确认，按当前文件重新建立待审；不得跳过重新核验和批准。

#### 能力边界

上下文按活跃文档保守全量加载，输出上限 256000 字节，并在支持的宿主中关闭该事件的自动预览截断。超过上限时清空本轮加载记录并报告失败；运行 `doc-gate.py context --project <project_root> --session <session_id> --document <相关文档路径>` 按任务范围读取并记录清单，`--document` 可重复指定，始终包含索引与主模块；不得声称全部正文已加载。文档库缺失时提示 `/doc-init`，按既有约定继续任务。

原生 hook 不能覆盖宿主绕过回调的专用路径、当前项目之外的写入、Git 忽略文件，以及任意命令动态构造的写入目的地。任意 shell、MCP、Git 配置和本地可变状态不构成对抗性安全边界。宿主回调报错、超时或不符合协议也可能放行工具。因此应区分“执行器与隔离测试已具备能力”“原生映射已登记”“宿主已验证生效”，不能把登记成功写成所有 AI、所有写入及所有答复都受硬拦截。
