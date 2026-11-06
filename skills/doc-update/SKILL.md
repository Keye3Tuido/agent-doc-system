---
name: doc-update
description: "Update existing documentation files for one or all submodules in the current project, including refreshing commit SHA, filling in architecture / key flows / interfaces / data contracts, and reorganizing chapters. Always outputs a unified diff and waits for user approval before writing. Use when the user asks to update, refresh, sync, or fill in module documentation."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§4（每对话流程，含 STALE 内容判定）+ §7（更新触发条件）+ §8（文档模板）+ §11（diff 提议格式）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 必要前置

执行本 skill 前必须运行：

```bash
python3 ~/.agent-docs/scripts/doc-gate-install.py --require-ready
```

只有退出码为 0 且返回 `ready: true` 才能继续。适配器或映射缺失、禁用、缺少宿主信任、能力不足、包或宿主变化、原生验证未完成时，停止本 skill 及依赖它的项目流程，报告检查结果，按手册 §16.2 核实当前 AI 软件的能力、建立或修复对应适配器与 Hook，完成验证后重试；体系不绑定 Codex，不能用其他宿主的适配器代替当前宿主；不得改走手动执行或把隔离脚本测试当作宿主验证。安装、诊断和修复文档体系本身可继续，范围不延伸至业务项目操作。

## 门限协作

就绪检查通过后，按手册 §16.2：回读 `doc-gate.py status` 中的待审、三项检查结果及文件哈希，再完成下面的源码核验。实际写入已自动触发检查；只读与无内容变化的写入不产生待审。

没有源码变更、用户主动要求更新文档时，用 `doc-gate.py begin --project <project_root> --session <宿主真实会话ID> --document <项目相对文档路径>` 建立审阅。阶段 B 只准备新内容；正式落盘由阶段 C 的门限确认执行。门限未就绪时停止；草稿、工具参数和 agent 自述都不能代替原生用户确认。

## 触发形式

- `/doc-update`：扫所有 stale 文档（含主模块 + 全部子模块）。
- `/doc-update <module-path>`：仅处理指定子模块（如 `Libraries/code_sandsort`）。
- `/doc-update main`：仅处理主模块文档（`doc-library/main-module.md`）。

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
4. **STALE 内容判定**（按手册 §4 第 6 条；仅 stale 目标走此步）：在子模块目录内执行 `git log --oneline <doc_sha>..<remote_sha>`，对照 §7 触发条件逐条审视：
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
10. 准备文档草稿：将新内容写入 `.agent-docs/.tmp/`，正式路径在阶段 C 获批后落盘。每次写草稿后立即调用 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <path>` 兜底（默认模式修 BOM / CRLF / 孤立 CR；非 UTF-8 会拒绝改动并非零退出）。

### 阶段 C：输出与审批

1. 检查 `_index.md` 的 `project_config.initial_bootstrap_done`：为 `false` 且手册 §13 的三项前置条件全部满足时，将翻为 `true` 的改动纳入同一提案；条件不满足时保持原值。
2. 按手册 §16.2 为全部受影响文档生成 JSON 决定；无需改动时使用 `review` 并说明源码依据，需要改动时使用 `propose`。新文档和相关索引也放入同一提案。
3. 告知用户查看 `.agent-docs/.tmp/pending-review.md` 并逐块发送文件中的精确确认。对话中说明改动概要，禁止逐字输出大段 diff。
4. 全部摘要经原生用户输入核验后落盘。落盘中断先 `apply`，冲突则 `recover` 撤销旧确认、保留已落盘事实并重新审阅。

## 硬约束

- 永远不要静默写文件。每一份要变的文档都必须出现在 diff 中。
- 主模块文档与子模块文档同等对待，不可遗漏。
- sha 必须从 `origin/<branch>` 取（远端），不用本地 HEAD（除非远端引用不存在）。
- 收尾时若子模块清单或一句话定位有变化，**不要手工改 `_index.md` 的两张表**——跑 `python3 ~/.agent-docs/scripts/doc-tree.py <project_root> --emit-index-tables` 再生后替换对应两节，并纳入同一份 diff。
- 遵守 §6 第 5、6 条：只描述当前状态（禁止"修复了 X"、"以前是 Y"这类补丁式叙述）、不复制实现细节、不写行号、不写具体常数。这四项由 `doc-format-check.py` 的 `PATCH_NARRATIVE` / `LINE_NUMBER_REF` 部分覆盖。
- 粒度补充须以 agent 本次对话中**实际读过**的源码为依据，禁止凭推测扩写文档。
- 粒度补充必须遵守 §6 全部硬约束；不引入新章节，仅扩写已有章节。
- 粒度候选与 stale 是两条独立分支：stale 目标走 SHA 漂移流程并刷 commit；粒度候选不刷 commit，因为代码未变。同一目标若两条都触发，分别处理后合并到同一份 diff。
- **新增章节必须按 §8.7 插入到规范位置**，不得追加到文末，否则 `doc-format-check.py` 会报 `CHAPTER_ORDER`。
- **触发条件扩展（对应手册 §7）**：
  - 协作关系变化 → 触发 `## 协作关系` 与 `## 依赖` 章节更新
  - 子模块 `## 典型修改场景` **永不自动触发**——纯经验沉淀，仅用户主动要求时维护
