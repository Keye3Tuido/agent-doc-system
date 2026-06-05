---
schema_version: 4
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
└── scripts/               工具脚本
    └── doc-*.py
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
   - `python3 ~/.agent-docs/scripts/doc-format-check.py <project_root>` → yaml schema 与四元组重名检查
6. 根据脚本输出汇总问题：STALE / NO_DOC / ORPHAN_DOC / ARCHIVED_BUT_ACTIVE / BRANCH_GONE / 编码问题 / schema 问题。
7. **STALE 项内容判定**：对每个 STALE（sha 漂移）项，必须执行：
   - 取漂移范围内的提交摘要：在子模块目录内运行 `git log --oneline <doc_sha>..<remote_sha>`。
   - 对照 §7 触发条件逐条审视提交：仅当**所有**提交均属"实现细节调整、bug 修复、不影响接口/职责/数据契约/流程"时，方可只刷新 commit 字段；任意提交触及 §7 条件，必须同步更新对应章节。
   - commit message 信息不足以判断时，进一步看 `git log -p <doc_sha>..<remote_sha> --stat` 或具体文件 diff。
   - **禁止仅凭 sha 不匹配就只刷 commit 字段**——这是历史 bug 来源。
8. **stale 警告**：以上任意检查发现问题，回复正文**最开头**一行打印 `> [doc-stale] <一句话说明>`，并在收尾的 diff 提议中给出修复方案。只有用户明确说"这次不动文档"才跳过。
9. **整个对话期间不再自动重复扫描**，除非用户显式要求"再扫一遍文档对位"。

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

slug 规则：保留字母、数字、CJK 字符（U+4E00-U+9FFF）、下划线和连字符，其他字符替换为 `-`，连续 `-` 合并为一个，首尾 `-` 去除。

示例：

- `https://gitee.com/game_wrapper/goodsmatch_game.git` 的 `sandloop/develop` 分支 → `gitee-com__game_wrapper__goodsmatch_game__sandloop-develop.md`
- `https://gitee.com/red_base/red_core.git` 的 `中国区测试` 分支 → `gitee-com__red_base__red_core__中国区测试.md`
- `git@github.com:foo/Bar.git` 的 `release/2026-q2` 分支 → `github-com__foo__Bar__release-2026-q2.md`

### 5.2 冲突防御

- 同 origin 同 owner 同 name 同 branch → 同一文档，**只能存在一份**。
- 同 owner+name 不同 origin → `origin-host-slug` 不同 → 不冲突。
- 不同分支 → `branch-slug` 不同 → 不冲突。

每对话扫描时若发现两个子模块文档元信息中四元组完全相同 → 立刻报 `> [doc-stale]`，要求合并到一份。

### 5.3 一个分支只保存一份文档

`commit` 字段记录在 yaml 元信息里，每次同步刷新。**sha 不进文件名。**

---

## 6. 写文档时的硬约束

1. **所有文档强制使用 UTF-8 编码**，**不带 BOM**，行尾使用 `\n`（LF）。新建或修改文档前后都必须确认编码合规；发现非 UTF-8 / 含 BOM / 非 LF 行尾的文档立即在收尾 diff 中提议修复。
2. **不允许无意义换行**。一段话写在一行里，由编辑器/渲染器自然折行。仅在以下场景使用换行：段落分隔（空行）、列表项、标题前后、表格行、代码块、YAML 字段、引用块。**禁止为控制视觉宽度而在句中硬换行**。
3. 单份文档 ≤ 500 行。超过则拆出附属文档（递归一层即可）。**拆分阈值（实操）**：单章 > 80 行或单文档 > 400 行 → 在 diff 提议中建议拆出附属文档；附属文档命名按 §5（`<repo-id>__<branch-slug>__<sub>.md`），`sub_section` 用语义 slug（`flow` / `data-flow` / `collaboration` / `change-scenarios` 等）。"_待生成_" 占位允许长期保留——空章节不算违规，但 doctor 应汇总占位章节统计供用户参考。
4. 只描述**当前状态**。禁止"现在改成 X"、"修复了 Y bug"、"以前是 Z"等补丁式叙述。
5. 不复制实现细节、不写行号、不写具体常数；常数只描述语义。
6. 跨子模块**不引用文档**。需要时主动去对应仓库现读；找不到再评估是否要建/改文档。
7. 主仓库内文件可直接引用，但引用处必须给"**何时需要查它**"的一句话指引。
8. 所有文档必须严格遵循 §8「文档模板」与 §9「yaml schema」。

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

**强不变量（structure 同步刷新）**：任何 `/doc-update` 流程涉及该模块文档变动时（无论 sha 漂移内容刷新、粒度补充扩写、还是 schema 升级补字段），必须重跑 `python3 ~/.agent-docs/scripts/doc-structure-import.py <doc> <module> <root>` 覆盖 `structure` 字段。**正文改 + structure 未刷 = doctor 视为不一致警告**。

---

## 8. 文档模板

**主模块、子模块、附属文档统一使用以下模板**。附属文档可省略不相关章节，但章节顺序不得调整。

> 本节定义了**主模块的 4 个新章节**（§8.1-§8.4，仅主模块文档使用）和**子模块的 2 个新章节**（§8.5-§8.6，仅子模块文档使用）。

### 8.0 通用 13 章（主 + 子模块共用）

```
# <模块名>

[元信息 yaml]

## 定位
一句话说清模块在系统中的角色。

## 职责边界
做什么 / 不做什么。明确写"X 由 Y 模块负责，不在此处"。

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

- 主模块：通用 13 章 + 8.1-8.4 附加；推荐顺序为 `定位 / 职责边界 / 框架总览 / 架构 / 业务主循环 / 跨模块数据流 / 模块协同模式 / 生命周期 / 外部入口 / 关键流程 / 接口 / 数据契约 / 配置与资源 / 依赖 / 使用约束 / 警示 / 可观测性`
- 子模块：通用 13 章 + 8.5-8.6 附加；推荐顺序为 `定位 / 职责边界 / 架构 / 生命周期 / 外部入口 / 关键流程 / 接口 / 数据契约 / 配置与资源 / 依赖 / 使用约束 / 警示 / 可观测性 / 协作关系 / 典型修改场景`

---

## 9. yaml 元信息 schema

每份子模块文档头部必须严格匹配下表。`schema_version` 升级时旧文档**只提示不自动重写**，等用户批准后批量重写。

| 字段 | 必填 | 说明 |
|---|---|---|
| `schema_version` | 是 | 当前为 `4` |
| `agent_load` | 是 | `always`（主模块、_index）/ `on-demand`（子模块）/ `manual`（模板） |
| `repo` | 是 | origin URL 原值（不做 slug） |
| `origin_host` | 是 | 例 `github.com` |
| `owner` | 是 | 例 `foo` |
| `name` | 是 | 例 `Bar` |
| `branch` | 是 | 例 `release/2026-q2` |
| `commit` | 是 | 40 位 sha，从 `origin/<branch>` 取 |
| `archived` | 否 | `true` 表示归档 |
| `archived_at` | 否 | ISO 日期 |
| `archived_reason` | 否 | `removed-from-gitmodules` / `renamed-to-X` / `merged-into-Y` / `imported-from-other-project` |
| `origin_path_in_main` | 否 | 该子模块在主仓库中的挂载路径，例如 `Libraries/Bar` |
| `merged_from` | 否 | `[<branch-slug>, ...]` |
| `sub_section` | 否 | 仅附属文档使用，纯语义 slug |
| `structure.deps` | 否 | 依赖列表，每项：`m`（模块路径或包名）、`use`（top-N 高频使用符号）、`type`（import/include/use）、`role`（`framework`/`utility`/`sibling`/`resource`/`unknown`）、`granularity`（`file` 兼容老数据；新提取产出 `module`） |
| `structure.exports` | 否 | 导出列表，每项：`n`（符号名）、`t`（class/function/interface/type/const/struct/enum/trait）、`path`（文件路径）、`vis`（`public`/`protected`/`internal`，默认 `public`）、`base`（直接基类，可选） |
| `structure.inner` | 否 | 内部结构，每项：`n`（容器名）、`t`（class/namespace/module/struct）、`has`（成员列表）、`base`（`{extends: [...], implements: [...]}` 跨语言统一对象，可选）、`pattern`（v1 仅 `singleton`/`observer`，可选） |
| `structure.cross_module_contracts` | 否 | 跨模块协作契约，每项：`with`（目标模块）、`protocol`（`delegate`/`callback`/`event`/`message`/`rpc`/`inherit`/`ecs`/`di`/`observer-bus`/`state-machine`）、`interface`（接口名）、`direction`（`inbound`/`outbound`/`bidirectional`）、`note` |
| `structure.data_flow_anchors` | 否 | 跨模块共享数据锚点，每项：`name`（数据结构名）、`holders`（持有该数据的模块列表，至少 2 项）、`note` |
| `module_classification.language` | 是 | 主要语言，如 `python`、`typescript`、`rust` |
| `module_classification.framework` | 是 | 主要框架，如 `django`、`react`、`tokio` |
| `module_classification.role` | 是 | 模块角色：`application`/`library`/`service`/`utility`/`bridge` |
| `module_classification.layer` | 是 | 架构层次：`presentation`/`business`/`data`/`infrastructure`/`cross-cutting` |
| `module_classification.lifecycle_stage` | 是 | 生命周期：`active`/`maintenance`/`deprecated`/`experimental` |
| `key_abstractions.classes` | 是 | 核心类列表，每项：`name`、`purpose`（用途简述） |
| `key_abstractions.interfaces` | 是 | 核心接口列表，每项：`name`、`purpose` |
| `key_abstractions.functions` | 是 | 核心函数列表，每项：`name`、`purpose` |
| `key_abstractions.data_structures` | 是 | 核心数据结构列表，每项：`name`、`purpose` |
| `dependency_graph.direct_deps` | 是 | 直接依赖列表，每项：`module`（模块路径）、`purpose`（依赖目的） |
| `dependency_graph.provides_to` | 是 | 被依赖列表，每项：`module`（依赖方模块）、`interface`（提供的接口） |
| `dependency_graph.optional_deps` | 是 | 可选依赖列表，每项：`module`、`condition`（激活条件） |
| `dependency_graph.dev_deps` | 是 | 开发依赖列表，每项：`module`、`scope`（测试/构建/文档等） |
| `communication_pattern.interaction_model` | 是 | 交互模式：`sync`/`async`/`event-driven`/`stream`/`hybrid` |
| `communication_pattern.protocols` | 是 | 通信协议列表，如 `http`、`grpc`、`websocket`、`message-queue` |
| `communication_pattern.events` | 是 | 事件列表，每项：`name`（事件名）、`trigger`（触发条件）、`payload`（数据结构） |
| `data_flow_summary.inputs` | 是 | 输入数据列表，每项：`name`（数据名）、`source`（来源）、`format`（格式） |
| `data_flow_summary.outputs` | 是 | 输出数据列表，每项：`name`、`destination`（目的地）、`format` |
| `data_flow_summary.state` | 是 | 状态管理描述，每项：`type`（状态类型）、`scope`（作用域）、`persistence`（持久化方式） |
| `data_flow_summary.side_effects` | 是 | 副作用列表，每项：`action`（操作）、`target`（目标）、`condition`（触发条件） |
| `interface_exposure.public` | 是 | 公开接口列表，每项：`name`、`type`（class/function/API等）、`stability`（stable/beta/alpha） |
| `interface_exposure.internal` | 是 | 内部接口列表，每项：`name`、`type`、`consumers`（消费者模块列表） |
| `interface_exposure.deprecated` | 是 | 已废弃接口列表，每项：`name`、`since`（废弃版本）、`alternative`（替代方案） |
| `extensibility_points.hooks` | 是 | 扩展钩子列表，每项：`name`、`trigger`（触发时机）、`signature`（函数签名） |
| `extensibility_points.plugins` | 是 | 插件机制列表，每项：`type`（插件类型）、`interface`（接口定义）、`discovery`（发现机制） |
| `extensibility_points.configuration` | 是 | 配置扩展点列表，每项：`key`（配置键）、`type`（数据类型）、`scope`（作用范围） |

**升级策略（schema v4 内扩展）**：

- 字段扩展（`vis` / `base` / `pattern` / `cross_module_contracts` / `data_flow_anchors`）→ optional，老文档零成本兼容
- `deps` 语义从"文件路径"改为"模块路径"通过 `granularity: file|module` 字段判别；脚本读取按字段分流，**不强制全量重跑**
- 老文档在自然 `/doc-update` 时按需补全；唯一全量重跑场景 = 用户主动 `/doc-rebuild`

---

## 10. archived 流程

**进入归档**：本地 `.gitmodules` 不再包含该子模块时（适用于 git-submodule 机制；其他机制按对应清单文件判定）。

转移动作：

1. 文件**留在 `doc-library/modules/` 不移动**。
2. yaml 元信息追加：`archived: true`、`archived_at`、`archived_reason`、`origin_path_in_main`。
3. `_index.md` 把它从活跃区移到归档区。

> 归档文档留在 `modules/` 目录不移动，仅通过 yaml 字段 `archived: true` 区分。`doc-tree.py` 和 `doc-format-check.py` 脚本会自动识别归档文档并分类展示。

**恢复**：扫描时若 `(origin_host, owner, name, branch)` 四元组在已归档文档中精确命中 → 提议去掉 `archived: *` 字段，刷新 `commit`。未命中视为新增子模块；可在 diff 提议中提示"是否参考某 archived 文档"，但不主动复用内容，由用户决定。

**分支合并归档**：扫描时若 `branch_A` 是 `branch_B` 的祖先（`git merge-base --is-ancestor`），且两份文档同时存在 → 提议在 A 文档元信息加 `archived: true` + `archived_reason: merged-into-<branch_B>`，并在 B 文档元信息追加 `merged_from: [<branch_A>]`。

---

## 11. diff 提议格式

收尾时 agent 主动提议 diff；用户也可主动要求 diff。

**输出方式**：agent 将 diff 内容通过 `doc-diff-propose.py` 写入 `<project>/.agent-docs/.tmp/pending-review.md`，然后告知用户查看该文件并回复 yes/no。**禁止将大段 diff 逐字输出到对话框**。

格式约束：

- unified diff 代码块。
- 路径相对项目 `.agent-docs/`（顶层 `_index.md`，子模块文档实际位于 `doc-library/modules/...`）。
- 新文件：全文 + `(new file)` 标注。
- 删除：`(deleted)` 标注。
- 重命名：`(renamed: old → new)` 标注。
- 单次 diff 总行数 > 300 行 → 自动按"一份文档一块"拆分为多个独立 diff 块，每块独立审批。

---

## 12. 工作节奏与边界

- **stale 检查**只在每次 skill 启动时跑一次（§4）。
- 工作过程中发现要改 / 新增文档 → 专心做主任务，收尾时一次性提议 diff，等批准。
- 新增子模块文档时可参考已有文档（含已归档文档，尤其 fork 同源场景），但内容必须真实匹配新子模块当前状态。
- **本文件本身的修改**：只在用户主动要求时进行；agent 不可自行修订工作框架。

---

## 13. 首次落地两阶段

仅当项目 `_index.md` 顶部 `project_config.initial_bootstrap_done == false` 时执行本节流程；落地完成后由用户把该字段改为 `true`，后续 skill 启动时跳过本节。

第一阶段（轻）：

- 若项目尚无 `.agent-docs/`，先按 §14 的"无文档库"分支与用户确认是否从全局 `templates/` 初始化骨架。
- 解析 `.gitmodules`，输出子模块清单 + 每个的一句话定位 + `fileMatchPattern` 草案（含主仓库粘合点）。
- **不生成任何子模块 .md 文件**，等用户审。

第二阶段（重）：

- 按用户确认的清单逐个深入扫源码。
- 通过 §11 的 diff 提议格式，按"一份文档一块"逐份输出，等用户批准后写入 `.agent-docs/doc-library/modules/`。
- 同步刷新 `_index.md` 的子模块清单与 `doc-library/main-module.md`。
- 全部完成且文档对齐项目现状后，agent 自动在最后一份 diff 中将 `_index.md` 的 `project_config.initial_bootstrap_done` 改为 `true`。

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
| `/doc-context` | 业务对话中加载项目文档库作为上下文（只读，不出 diff） | §3 §9 |
| `/doc-init` | 在不存在文档库时初始化、建立文档库 | §13 §14 |
| `/doc-update` | 更新文档（指定子模块或所有 stale 项），改动前必须出 diff 等用户审批 | §4 §7 §8 §11 |
| `/doc-rebuild` | 全量重建文档库，先列清单等确认 | §13 |
| `/doc-doctor` | 检查 + 整理 + 归档（修复编码、归档已离场子模块、合并重名等），先列清单等确认；不删文件 | §4 §5 §6 §10 §11 |
| `/doc-prune` | 物理删除孤儿归档 / 残破归档，先列清单等确认 | §10 |
| `/doc-tree` | 只读输出当前文档库结构清单 | §3 §9 |
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

所有重复性检测逻辑下沉为脚本，位于 `~/.agent-docs/scripts/`。大部分脚本无第三方依赖（仅 Python 3 标准库 + git CLI），`doc-structure-extract.py` 需要 tree-sitter（见虚拟环境 `~/.agent-docs-venv`）。

| 脚本 | 用途 | 典型调用 |
|---|---|---|
| `doc-stale-check.py` | 一次性输出所有子模块 stale 状态表 | `python3 ~/.agent-docs/scripts/doc-stale-check.py <project_root>` |
| `doc-encoding-check.py` | 编码合规检查（UTF-8/BOM/CRLF） | `python3 ~/.agent-docs/scripts/doc-encoding-check.py <project_root>` |
| `doc-format-check.py` | yaml schema 校验 + 四元组重名 + 路径存在性 | `python3 ~/.agent-docs/scripts/doc-format-check.py <project_root>` |
| `doc-structure-extract.py` | 从源码提取结构化关系数据（deps/exports/inner），支持 Python/JS/TS/Go/Java/Rust/C/C++ | `~/.agent-docs-venv/bin/python3 ~/.agent-docs/scripts/doc-structure-extract.py <module_path> <project_root>` |
| `doc-structure-import.py` | 调用 `doc-structure-extract.py` 并将结果直接写入文档的 `structure` 字段 | `python3 ~/.agent-docs/scripts/doc-structure-import.py <doc_path> <module_path> <project_root>` |
| `doc-tree.py` | 输出文档库结构树（活跃/归档/缺失） | `python3 ~/.agent-docs/scripts/doc-tree.py <project_root>` |
| `doc-write-utf8.py` | 把文件转换为严格 UTF-8（无 BOM / LF）；不读 stdin | `python3 ~/.agent-docs/scripts/doc-write-utf8.py <path>` 原地修复；`--from <src>` 拷贝转换；`--check` 只校验 |
| `doc-scaffold.py` | 从子模块路径生成文档骨架（yaml 头 + 空章节） | `python3 ~/.agent-docs/scripts/doc-scaffold.py <module_path> <project_root>` |
| `doc-diff-propose.py` | 将 diff 提议写入 `.agent-docs/.tmp/pending-review.md` 供用户审阅；不读 stdin | 先用 `fs_write` 把 diff 写到 `<project>/.agent-docs/.tmp/diff-staging.md`，再 `python3 ~/.agent-docs/scripts/doc-diff-propose.py <project_root> --from <project>/.agent-docs/.tmp/diff-staging.md --title "desc"` |
| `doc-sync-system.py` | 下载远程 skill 包并安装（备份 → dry-run → 写入） | `python3 ~/.agent-docs/scripts/doc-sync-system.py [--url <url>] [--dry-run] [--no-backup]` |

### 16.1 agent 使用规则

- §4 的全量检测**必须通过脚本完成**，禁止逐个手动执行 git 命令。
- 新建文档时**优先使用 `doc-scaffold.py`** 生成骨架，再补充语义内容。
- 写入文档时若环境存在编码问题，使用 `doc-write-utf8.py` 确保 UTF-8 合规。
- `/doc-tree` skill 直接调用 `doc-tree.py` 输出结果。
- **diff 提议必须写入文件**（通过 `doc-diff-propose.py`），禁止将大段 diff 逐字输出到对话框。对话中只需告知用户文件路径并等待确认。
- **任何脚本都不得通过 stdin 传入内容**（历史上常因 agent 没接管道导致脚本永久阻塞）。需要传内容时先用 `fs_write` 写到临时文件（如 `<project>/.agent-docs/.tmp/<name>.md`），再用 `--from <file>` 或 `--content <inline>` 让脚本读取。
- **`fs_write` + 中文内容必须立即跟一次 `doc-write-utf8.py` 兜底修复**。已知 bug：`fs_write` 在中文系统会把 UTF-8 误存为 GBK；`doc-diff-propose.py` 等脚本严格按 UTF-8 读取，遇到 GBK 会硬失败。三步标准模式：(1) `fs_write <staging>`；(2) `doc-write-utf8.py <staging>`；(3) 调用消费脚本（如 `doc-diff-propose.py --from <staging>`）。
- 脚本支持 `--out <file>` 参数将输出重定向到文件，当输出内容较长时应使用此参数。
