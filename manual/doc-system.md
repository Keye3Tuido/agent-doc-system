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

## 4. 读取前检查与写入后同步

日常文档维护静默进行；提交时才集中审阅文档变化。执行依据是项目源码、暂存内容和文档正文，体系可由任何能够读取技能并执行 Python/Git 的 AI 使用。

1. 读取项目前先加载 `.agent-docs/_index.md`，按任务范围识别主模块与相关子模块。没有文档库时提示一次并继续任务；初始化按 §14 处理。
2. 首次读取、上下文恢复、范围变化或相关文件状态变化时，运行 `doc-stale-check.py`、`doc-encoding-check.py` 和 `doc-format-check.py`，并检查相关仓库的 HEAD、暂存区、工作区差异及非忽略新增文件。每次读取前核对这些状态；仅状态未变时复用已核验内容。
3. 远端 SHA 漂移、本地提交、分支切换、工作区修改和已暂存的子模块版本都可能使文档过时。主模块同样核验，不能只比较子模块远端 SHA。无需为每次读取重复 fetch；远端检查使用本机已有引用，核验结论明确对应本机实际代码。
4. 发现过时文档时，先读变化源码并按 §7 更新相关章节，再加载文档作为上下文。此处的源码读取用于核验和修复，不以旧文档替代源码事实。仅全部变化均不影响职责、架构、接口、数据契约或关键流程时，才可只刷新提交基线。
5. 每次项目写入后核对实际结果，包括命令失败但文件已变化的情况；多文件事务视作一个批次。同步受影响正文、元信息和派生索引后，再继续依赖这些内容的操作。只读和写入相同字节不产生文档改动。
6. 文档 `commit` 表示已核验的提交基线；未提交代码变化也须写入正文，不能仅更新 SHA。同步时保留用户已有改动；更新索引表必须使用 `doc-tree.py --emit-index-tables`。
7. 可确定的问题静默修复。源码缺失、冲突或无法验证的事项保留待解决状态，不伪造同步结论；继续可核验的工作，提交前集中解决并审阅。不要逐次提示 stale 或要求日常批准。

规则由 AI 根据 AGENTS.md 自动调用 doc-context 和 doc-update 执行。每次使用技能检查规则安装情况（§16.3），不注册宿主 Hook 或 Git Hook；提交审阅见 §16.2。

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

每对话扫描时若发现两个子模块文档的四元组完全相同 → 核验正文后静默合并为一份，提交时审阅差异。四元组由 yaml 中的 `repo`（解析出 host / owner / name）与 `branch` 运行时推导，不存储于 yaml。

### 5.3 一个分支只保存一份文档

`commit` 字段记录在 yaml 元信息里，每次同步刷新。**sha 不进文件名。**

---

## 6. 写文档时的硬约束

1. **编码合规的唯一定义**：合法 UTF-8 + 无 BOM + 无 CRLF + 无孤立 CR。合法 UTF-8 内部的控制字符（换页 `\x0c`、ESC `\x1b` 等）**不视为问题**。本手册、`convert-to-utf8.sh`、`doc-encoding-check.py` 三处共用这一条定义，任何一处改动必须同步另两处。新建或修改文档前后都必须确认合规；发现不合规的文档先核实编码并修复，提交时审阅差异。
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

每份子模块文档头部必须严格匹配下表。`schema_version` 落后时按当前模板静默迁移元信息，保留正文，提交时一并审阅。

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

存量 v5 文档由 `doc-format-check.py` 报 `OUTDATED_SCHEMA_VERSION` 与 `DEPRECATED_FIELD(<字段名>)`，按本节首段规则静默迁移，提交时审阅裁剪结果。

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

## 11. 文档差异审阅

日常同步直接写入正式文档；用户原有内容和未提交改动必须保留。文档变更通过 Git 留下实际差异，提交前一次审阅，避免逐文件审批。

提交前将本次源码和相关文档按同一范围暂存，按 §16.2 审阅实际暂存的文档 diff 与相关源码 diff。对话中说明变化概要并提供可审阅的完整差异；文档无需变更时说明已核验范围和具体理由。取得用户对本次差异的明确确认后再提交，已有覆盖该差异的明确授权可复用。可选报告工具用于保存快照，日常流程不依赖报告或摘要。

报告、暂存树或 HEAD 改变后原批准失效。部分暂存时，文档描述必须对应将要提交的源码；工作区另有变化时不能直接把工作区文档当成提交快照。

---

## 12. 工作节奏与边界

- 读取前静默核验相关文档，写入后静默同步；同一状态的核验结果可复用。
- 提交前集中核对暂存源码与文档，向用户展示文档变化并确认；未完成核对或存在待解决项时不提交。
- 新增文档可参考已有文档，但内容必须匹配当前源码。
- 全局工作框架只在用户主动要求时修改。

---

## 13. 首次落地两阶段

仅当项目 `_index.md` 顶部 `project_config.initial_bootstrap_done == false` 时执行本节流程；该字段翻为 `true` 后，后续 skill 启动时跳过本节。

**谁来翻这个字段**：由 agent 在第二阶段条件满足时静默改为 `true`，与其他文档变化一同在提交时审阅。翻转的前置条件见下方第二阶段末条。

第一阶段（轻）：

- 若项目尚无 `.agent-docs/`，按 §14 核实初始化意图；用户已要求初始化时直接从模板创建索引、主模块及空模块目录。
- 解析 `.gitmodules`，输出子模块清单 + 每个的一句话定位。
- **不生成任何子模块 .md 文件**，清单作为后续填充范围。

第二阶段（重）：

- 按用户要求的范围逐个深入扫源码。
- 按源码核验结果直接写入 `.agent-docs/doc-library/modules/`，提交时按 §11 审阅。
- 同步刷新 `_index.md` 的子模块清单与 `doc-library/main-module.md`。
- 翻转 `initial_bootstrap_done`：当以下条件**全部**满足时，将 `_index.md` 的 `project_config.initial_bootstrap_done` 改为 `true`，提交时一并审阅：
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
| `/doc-context` | 业务对话中加载项目文档库作为上下文（过时文档先静默同步） | §0 §8 |
| `/doc-init` | 在不存在文档库时初始化、建立文档库 | §13 §14 |
| `/doc-update` | 更新文档（指定子模块或所有 stale 项），静默同步，提交时审阅 | §4 §7 §8 §11 |
| `/doc-rebuild` | 按用户明确要求备份并重建文档库 | §13 |
| `/doc-doctor` | 检查 + 整理 + 归档（修复编码、归档已离场子模块、合并重名等），静默修复可确定问题；不删文件 | §4 §5 §6 §10 §11 |
| `/doc-prune` | 按用户明确授权的范围删除已核实归档 | §10 |
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


| `doc-commit-review.py` | 可选的暂存差异报告、审阅记录及快照核对，不安装 Hook | `python3 ~/.agent-docs/scripts/doc-commit-review.py prepare --project <project_root>` |
| `doc-workflow.py` | 可选的源码摘要检查及核验结论记录，不注册或执行 Hook | `python3 ~/.agent-docs/scripts/doc-workflow.py inspect --project <project_root>` |
| `doc-agents.py` | 检查或幂等合并 AGENTS.md 自动调用规则 | `python3 ~/.agent-docs/scripts/doc-agents.py check --agents-file <实际规则文件>` |
| `test_doc_agents.py` | 隔离验证规则安装、用户内容保留与无 Hook 行为 | `python3 ~/.agent-docs/scripts/test_doc_agents.py -q` |

### 16.1 agent 使用规则

- §4 的全量检测**必须通过脚本完成**，禁止逐个手动执行 git 命令。
- 新建文档时**优先使用 `doc-scaffold.py`** 生成骨架，再补充语义内容。
- **所有文本写入的统一模式**：(1) 写入（`fs_write` / 脚本 `--out` / Python `open`）；(2) 立即 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <path>`。已知 bug：`fs_write` 及部分 Python 实现在中文系统将 UTF-8 误存为 GBK，仅靠 `encoding="utf-8"` 不足以防御。若该脚本以非零退出报「编码无法判定」，说明写出的**不是**合法 UTF-8：必须重写该文件，不得忽略、也不要改用 `--guess` 蒙。
- `/doc-tree` skill 直接调用 `doc-tree.py` 输出结果。
- 使用可选提交审阅报告工具时，报告写入 Git 目录，不进入项目文档库；直接审阅实际暂存 diff 同样适用。


### 16.2 Git 提交前审阅

每次提交前由 AI 按 AGENTS.md 执行 doc-update，核对实际暂存源码及相关文档。此流程是指令约束，不是 Git 强制拦截。

1. 检查实际暂存差异；存在未暂存且应随提交同步的文档时，按本次授权范围补齐，保留用户无关改动。未提交源码与文档同时核对，不能仅凭 SHA 宣称同步。
2. 展示文档变化概要及可审阅的完整差异；文档无需修改时说明实际核验范围与具体依据。
3. 取得用户对本次差异的明确确认再提交；已有明确覆盖该差异的授权可以复用。内容变化后重新核对受影响部分，不用用户抄写摘要。日常核验、写入和同步不请求这项确认。

可直接使用 `git diff --cached` 审阅，也可选用 doc-commit-review.py 的 prepare、approve、check 记录当前快照。该辅助工具要求先用 doc-workflow.py inspect 获取摘要，在真实源码核验、文档同步及校验完成后用 complete 记录结论；它不安装 Hook，正常维护不依赖该记录。脚本只能验证摘要、编码和结构，语义一致性仍由 AI 和审阅者判断。

### 16.3 AGENTS.md 自动调用规则

自动维护规则的发布原文为 `templates/AGENTS.md`，安装器将其中技能目录占位符替换为实际路径后合并。可直接读取和审阅该文件，再选择安装位置。

使用任一文档技能时，先确定当前宿主实际读取的全局或项目 AGENTS.md，检查其 `project-doc-skills` 标记区块是否完整、内容是否与当前安装一致。全局规则已覆盖当前项目时复用，避免重复安装。

```bash
python3 ~/.agent-docs/scripts/doc-agents.py check --agents-file <实际规则文件>
python3 ~/.agent-docs/scripts/doc-agents.py install --agents-file <实际规则文件>
```

技能目录与默认全局包不同，可使用 `--skills-root <实际技能目录>`。安装器同样支持显式选择 `--agents-file`；不指定时仅安装包，并提示补齐规则。不能假定所有 AI 软件均读取同一个全局位置；宿主不支持 AGENTS.md 时，使用其支持的规则入口载入同一内容，并如实说明自动加载情况。

使用技能包含检查与补齐对应规则区块的授权，仍遵守宿主权限。install 会备份已有文件，只替换标记区块，保留其他规则；重复运行不重复追加，标记残缺或重复时保留原文件并报错。check 只读且返回安装状态，不创建文件。文件已安装和宿主已加载分别核验，必要时在新会话验证加载。

区块要求每次读取前使用 doc-context 核对新鲜度，写入批次后使用 doc-update 同步，提交前审阅实际差异；上下文恢复、任务切换、局部工作结束及最终交付前重新对齐。日常检查在当前任务中静默执行，不生成用户消息或收尾重试链。文档自身写入只校验必要派生内容，不递归维护。

旧版本迁移时备份并删除本系统的宿主注册和 Git 提交检查部分；恢复原有 pre-commit，混合自定义入口只删除明确受管的检查行。保留其他系统的 Hook、用户脚本、Git 配置及历史诊断记录。修改注册配置后先重新加载宿主，确认旧回调停止，再清理旧运行时；不要先删除仍被当前进程缓存引用的脚本。旧注册、安装和回调入口均已移除；后续安装不会重新登记。

自动执行依赖宿主加载规则及 AI 遵循指令，不能当成程序硬门限。缺少源码、冲突或无法核实的内容必须保留为未知，不能为了通过检查而伪造同步成功。
