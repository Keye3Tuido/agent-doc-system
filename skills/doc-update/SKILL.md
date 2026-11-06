---
name: doc-update
description: "Update existing documentation files for one or all submodules in the current project, including refreshing commit SHA, filling in architecture / key flows / interfaces / data contracts, and reorganizing chapters. Silently synchronize affected documentation after project writes and before using outdated context; require documentation review only at Git commit time. Use when the user asks to update, refresh, sync, or fill in module documentation."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§4（每对话流程，含 STALE 内容判定）+ §7（更新触发条件）+ §8（文档模板）+ §11（diff 提议格式）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 静默钩子协作

使用前检查当前 AI 宿主是否已登记并启用 `agent-doc-system-silent-workflow` 的读取前、写后和收尾职责；当前 Codex 用 `doc-workflow.py status` 检查，缺失时按手册 §16.3 登记并在宿主审阅，其他 AI 使用等效事件。安装与维护本体系可以继续，不因门限未启用而锁死修复。钩子的条件和进度只送内部上下文，不向用户播报或索要日常批准。

收到内部同步要求时运行 `doc-workflow.py inspect --project <project_root>`，核验相关源码并同步文档后，用返回的 source 摘要运行 `complete --source <摘要> --reason <源码依据与同步结论>`。该完成记录由 agent 保存，不是用户确认。源文件再变或文档被修改后重新核验，未同步时不得正常结束；提交审阅仍按手册 §16.2 请求用户确认。

## 触发形式

- `/doc-update`：扫所有 stale 文档（含主模块 + 全部子模块）。
- `/doc-update <module-path>`：仅处理指定子模块（如 `Libraries/code_sandsort`）。
- `/doc-update main`：仅处理主模块文档（`doc-library/main-module.md`）。

## 自动调用范围

读取前发现过时内容或项目写入后，按本次实际变化路径选择主模块、相关子模块及受影响的协作章节，直接进入阶段 B。包括已暂存但未切换工作树的子模块版本、本地提交、工作区及新增文件；不能只等远端 SHA 漂移才更新。文档库已存在但相关模块缺文档时，核验后补建骨架和正文。使用本次已核验的范围，避免每次写入都全库扫描。

文档自身写入后只校验该文档和受影响的派生索引，不递归触发同一同步流程。已有源码变化不影响文档语义时保留正文，将核验依据留待提交审阅。

## 执行步骤

### 阶段 A：全量 stale 检测（无参数时执行；有参数时跳到阶段 B）

1. 运行脚本完成全量检测（**禁止逐个手动执行 git 命令**）：
   ```
   python3 ~/.agent-docs/scripts/doc-stale-check.py <project_root>
   python3 ~/.agent-docs/scripts/doc-encoding-check.py <project_root>
   python3 ~/.agent-docs/scripts/doc-format-check.py <project_root>
   ```
2. 解析脚本输出，汇总 STALE / NO_DOC / ORPHAN_DOC / ARCHIVED_BUT_ACTIVE / BRANCH_GONE / 编码问题 / schema 问题。
3. **检查主模块文档**（`doc-library/main-module.md`）：
   - 对照主仓库 `Classes/`、`CMakeLists.txt` 等顶层文件，判断文档描述的架构/依赖/接口是否与现状一致。
   - 若主仓库有结构性变化（新增/删除顶层子系统、链接依赖变化、构建系统变化），标记主模块为 stale。
4. **收集本次对话中读过源码的模块**（粒度候选）：
   - 列出对话中通过 `read_file` / `read_files` / `readCode` / `grep_search` 实际命中的子模块（按子模块根目录归并）。
   - 仅当本次对话中 agent 对该模块进行过实质性源码阅读时纳入；只读了一两个文件不算。
   - 这些模块标记为「粒度候选」，进入阶段 B 走粒度判定分支（与 stale 分支并存，互不覆盖）。
5. **收集 schema 迁移目标**（独立于 stale 判定）：
   - 从步骤 1 的 `doc-format-check.py` 输出中提取所有报 `OUTDATED_SCHEMA_VERSION` 或 `DEPRECATED_FIELD(...)` 的文档。
   - 这些文档**无论 sha 是否漂移、本次对话是否读过其源码，都必须纳入本次目标集**，否则永远等不到迁移。
   - 该分支只改 yaml frontmatter（补必填字段、删废弃字段、升版本号），**不动正文、不刷 `commit`**；若同一文档同时是 stale 目标，则合并到同一份 diff 一并处理。
6. 汇总所有目标项（stale + 粒度候选 + schema 迁移目标），进入阶段 B。

### 阶段 B：逐份更新

对每个目标（stale 子模块、主模块、粒度候选、**schema 迁移目标**）：

> **仅为 schema 迁移目标**（不同时是 stale 目标或粒度候选）的文档：只走第 1、2、3 步——这三步都只改 yaml frontmatter；**跳过第 4 步及其后全部步骤**（正文比对、源码扫描、`commit` 刷新），直接进入阶段 C。

1. 读取当前文档。
2. **Schema版本检查与升级**：
   - 检查文档yaml frontmatter中的`schema_version`字段。
   - 对比全局手册`~/.agent-docs/manual/doc-system.md`中的当前schema版本。
   - 若文档版本低于手册版本，**必须按新模板完整升级**，不能只改版本号：
     - 更新`schema_version`字段到手册当前版本
     - 对照对应模板与手册 §9，补充所有新增**必填**字段；可选字段仅在其语义适用时添加（例如只有归档文档才添加 `archived_*`）
     - **删除手册 §9 字段表中已不存在的字段**（判据以 §9 表为准，不必逐版本记忆；`doc-format-check.py` 会以 `DEPRECATED_FIELD(<字段名>)` 逐项标出）。历史移除记录：v5→v6 移除 `agent_load` / `origin_host` / `owner` / `name` / `sub_section`；v6→v7 移除 `structure`（含 `deps` / `exports` / `cross_module_contracts`），结构信息改写在正文章节里
     - 对照`~/.agent-docs/templates/`中的模板文件，确保文档结构符合新模板要求
   - 若文档缺少`schema_version`字段，添加为手册当前版本并按上述流程补全
   - **冗余字段清理**：子模块与附属文档对照手册 §9；`doc-library/main-module.md` 只保留模板定义的 `schema_version`；`_index.md` 保留模板定义的 `schema_version` 与完整 `project_config`。删除各自白名单之外的顶层键及其子键，保持文档瘦身；**不得把 `_index.md.project_config` 当作冗余字段删除**。
3. 若文档状态为 `ARCHIVED_BUT_ACTIVE`：去掉 `archived` / `archived_at` / `archived_reason` 字段，将其从 `_index.md` 归档区移回活跃区。
4. **STALE 内容判定**（按手册 §4；仅 stale 目标走此步）：先确定本次实际核验基线。本地与远端一致时取 `origin/<branch>`；本地领先、分支切换时取实际 HEAD；只暂存子模块版本时核验将提交的 gitlink 对象。比较文档基线与目标提交的日志和 diff，同时检查暂存、工作区及新增文件，按 §7 触发条件逐条审视：
   - 仅当**所有**提交均属"实现细节调整 / bug 修复 / 不影响接口/职责/数据契约/流程"时，方可只刷新 `commit` 字段。
   - 任意提交触及 §7 条件，必须对应章节同步更新；commit message 信息不足时进一步看 `git log -p <doc_sha>..<remote_sha> --stat` 或具体文件 diff。
   - **禁止仅凭 sha 不匹配就只刷 commit 字段**。
5. 扫对应源码当前状态（取必要的源文件、配置文件、入口类）。
6. 按 §8 模板对比文档与现状的差异，准备改动。
   - **粒度补充判定**（仅粒度候选走此分支；stale 目标不走）：
     - 依据是 agent 本次对话中**实际读过**的源码区域，禁止凭推测扩写。
     - 仅当文档**已存在章节**对该区域的描述粒度显著低于代码实际复杂度（例：模块在架构图中只占一行、关键流程缺失、对外接口未列出）时，准备补充改动。
     - 仅补充架构 / 职责边界 / 业务逻辑 / 关键流程 / 接口 / 数据契约层面的信息，并遵守 §6 第 5、6 条：**只描述当前状态（不写补丁式叙述）、不复制实现细节、不写行号、不写具体常数**。
     - 不引入新章节，仅扩写已有章节。
     - 粒度差距不显著（文档已抓住要点）→ 跳过该目标，不出 diff。
   - **新增缺失章节时必须插入到 §8.7 规定的位置，不得追加到文末**：
     - 取 §8.7 的规范章节序列（子模块 16 章 / 主模块 18 章），在其中定位待补章节的名次。
     - 在文档现有章节中找到「规范序列里排在它之后、且文档中确实存在」的第一个章节，插到那一章之前；若不存在这样的章节，才追加到末尾。
     - **反例**：`## 业务逻辑` 在规范序列中位列第 3（职责边界之后），若追加到文末会被 `doc-format-check.py` 报 `CHAPTER_ORDER`。已有项目中确实存在这样被追加错位的文档。
   - **业务逻辑章节**（stale 目标与粒度候选均执行）：
     - 检查文档是否有 `## 业务逻辑` 章节。若无，按手册 §8 模板新增，并按上一条定位插入点。
     - 内容：列出本模块参与/主导的业务场景，每个场景标注入口（哪个类/方法触发）、本模块负责什么、产出/下游、涉及的核心文件及职责。
     - 依据：agent 本次对话中实际读过的源码和已掌握的模块定位。不凭空编造业务场景。
7. 若该文档还是首次落地骨架（章节为空或仅占位），按当前掌握的信息补充对应章节。
8. 同步刷新元信息中的 `commit` 字段（子模块文档；粒度候选不刷 commit，因为代码未变）。
9. 新建文档时使用 `python3 ~/.agent-docs/scripts/doc-scaffold.py <module_path> <project_root>` 生成骨架。
10. 将已核验的新内容直接写入对应正式文档；复用本次任务已有写入授权，不逐份请求批准。每次写入后立即调用 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <path>` 兜底（默认模式修 BOM / CRLF / 孤立 CR；非 UTF-8 会拒绝改动并非零退出）。

### 阶段 C：静默同步与提交审阅

1. 每次项目写入后，包括命令失败但已产生文件变化时，核对受影响主模块和子模块的职责、架构、接口、数据契约、关键流程及索引；需要更新则立即同步，完成后再继续依赖这些内容的操作。多文件事务可作为一个写入批次处理。
2. `_index.md.project_config.initial_bootstrap_done` 为 `false` 且手册 §13 的三项条件满足时，同步改为 `true`。
3. 运行编码和格式检查。索引派生表变化时运行 `doc-tree.py --emit-index-tables` 再生对应两节。静默修复可确定的问题，保留无法核实的事项，不伪造已同步状态。
4. 提交前核对实际暂存源码与文档，运行手册 §16.2 的 `prepare`，向用户展示文档差异或无需更新的依据，收到本次审阅的明确确认后再 `approve` 和提交。日常写入不等待这一步。

## 硬约束

- 日常文档维护静默落盘；提交时统一审阅实际暂存差异。用户已有文档改动必须保留，冲突处先核验，不能用整份覆盖抹掉。
- 主模块文档与子模块文档同等对待，不可遗漏。
- `commit` 记录实际已核验的提交基线，本地与远端一致时取 `origin/<branch>`，本地领先或分支切换时取实际 HEAD。未提交变化也须同步正文，不能仅刷新 SHA 声称已同步。
- 收尾时若子模块清单或一句话定位有变化，**不要手工改 `_index.md` 的两张表**——跑 `python3 ~/.agent-docs/scripts/doc-tree.py <project_root> --emit-index-tables` 再生后替换对应两节，并纳入同一份 diff。
- 遵守 §6 第 5、6 条：只描述当前状态（禁止"修复了 X"、"以前是 Y"这类补丁式叙述）、不复制实现细节、不写行号、不写具体常数。这四项由 `doc-format-check.py` 的 `PATCH_NARRATIVE` / `LINE_NUMBER_REF` 部分覆盖。
- 粒度补充须以 agent 本次对话中**实际读过**的源码为依据，禁止凭推测扩写文档。
- 粒度补充必须遵守 §6 全部硬约束；不引入新章节，仅扩写已有章节。
- 粒度候选与 stale 是两条独立分支：stale 目标走 SHA 漂移流程并刷 commit；粒度候选不刷 commit，因为代码未变。同一目标若两条都触发，分别处理后合并到同一份 diff。
- **新增章节必须按 §8.7 插入到规范位置**，不得追加到文末，否则 `doc-format-check.py` 会报 `CHAPTER_ORDER`。
- **触发条件扩展（对应手册 §7）**：
  - 协作关系变化 → 触发 `## 协作关系` 与 `## 依赖` 章节更新
  - 子模块 `## 典型修改场景` **永不自动触发**——纯经验沉淀，仅用户主动要求时维护
