---
name: doc-update
description: "Update existing documentation files for one or all submodules in the current project, including refreshing commit SHA, filling in architecture / key flows / interfaces / data contracts, and reorganizing chapters. Always outputs a unified diff and waits for user approval before writing. Use when the user asks to update, refresh, sync, or fill in module documentation."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§4（每对话流程，含 STALE 内容判定）+ §7（更新触发条件）+ §8（文档模板）+ §11（diff 提议格式）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

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
5. 汇总所有目标项（stale + 粒度候选），进入阶段 B。

### 阶段 B：逐份更新

对每个目标（stale 子模块、主模块、粒度候选）：

1. 读取当前文档。
2. **Schema版本检查与升级**：
   - 检查文档yaml frontmatter中的`schema_version`字段。
   - 对比全局手册`~/.agent-docs/manual/doc-system.md`中的当前schema版本。
   - 若文档版本低于手册版本，**必须按新模板完整升级**，不能只改版本号：
     - 更新`schema_version`字段到手册当前版本
     - 对照手册§9的schema定义，补充**所有**新增字段（必填+可选）
     - 对照`~/.agent-docs/templates/`中的模板文件，确保文档结构符合新模板要求
     - 对于schema v4+，必须提取并填充`structure`字段（deps/exports/inner）
   - 若文档缺少`schema_version`字段，添加为手册当前版本并按上述流程补全   - **冗余字段清理**：升级完成后，对照手册 §9 的允许字段表，删除 yaml frontmatter 中所有不在表中的顶层键及其子键。只保留表中列出的字段，其余一律移除，保持文档瘦身。3. 若文档状态为 `ARCHIVED_BUT_ACTIVE`：去掉 `archived` / `archived_at` / `archived_reason` 字段，将其从 `_index.md` 归档区移回活跃区。
4. **STALE 内容判定**（按手册 §4 第 6 条；仅 stale 目标走此步）：在子模块目录内执行 `git log --oneline <doc_sha>..<remote_sha>`，对照 §7 触发条件逐条审视：
   - 仅当**所有**提交均属"实现细节调整 / bug 修复 / 不影响接口/职责/数据契约/流程"时，方可只刷新 `commit` 字段。
   - 任意提交触及 §7 条件，必须对应章节同步更新；commit message 信息不足时进一步看 `git log -p <doc_sha>..<remote_sha> --stat` 或具体文件 diff。
   - **禁止仅凭 sha 不匹配就只刷 commit 字段**。
4. 扫对应源码当前状态（取必要的源文件、配置文件、入口类）。
5. 按 §8 模板对比文档与现状的差异，准备改动。
   - **粒度补充判定**（仅粒度候选走此分支；stale 目标不走）：
     - 依据是 agent 本次对话中**实际读过**的源码区域，禁止凭推测扩写。
     - 仅当文档**已存在章节**对该区域的描述粒度显著低于代码实际复杂度（例：模块在架构图中只占一行、关键流程缺失、对外接口未列出）时，准备补充改动。
     - 仅补充架构 / 职责边界 / 业务逻辑 / 关键流程 / 接口 / 数据契约层面的信息；**不写实现细节、不写行号、不写具体常数**（参见 §6）。
     - 不引入新章节，仅扩写已有章节。
     - 粒度差距不显著（文档已抓住要点）→ 跳过该目标，不出 diff。
   - **structure 字段提取**（stale 目标与粒度候选均执行；文档缺少 `structure` 字段时**必须**执行）：
     - 调用导入脚本，自动提取并写入文档：
       ```
       python3 ~/.agent-docs/scripts/doc-structure-import.py <doc_path> <module_path> <project_root>
       ```
     - 脚本内部调用 `doc-structure-extract.py`，将 deps/exports 写入文档 YAML frontmatter 的 `structure` 字段，覆盖已有值。
     - 脚本输出 `OK: <doc_path>` 表示成功；`ERROR: ...` 表示失败（需人工介入）。
   - **cross_module_contracts 回填**（stale 目标与粒度候选均执行，如正文涉及协作关系变化）：
     - 若文档 `## 协作关系` 章节描述了与其他模块的 delegate / callback / event / message 等协作关系，**必须**同步填充 `structure.cross_module_contracts`。格式参考手册 §9：每项含 `with`（目标模块）、`protocol`（`delegate` / `callback` / `event` / `message` / `rpc` / `inherit` / `ecs` / `di` / `observer-bus` / `state-machine`）、`interface`（接口名）、`direction`（`inbound` / `outbound` / `bidirectional`）、`note`。
     - **原则**：正文写了什么协作关系，structure 就要有对应条目。只回填正文已描述的内容，禁止凭空编造。
   - **业务逻辑章节**（stale 目标与粒度候选均执行）：
     - 检查文档是否有 `## 业务逻辑` 章节。若无，按手册 §8 模板新增该章节。
     - 内容：列出本模块参与/主导的业务场景，每个场景标注入口（哪个类/方法触发）、本模块负责什么、产出/下游、涉及的核心文件及职责。
     - 依据：agent 本次对话中实际读过的源码和已掌握的模块定位。不凭空编造业务场景。
6. 若该文档还是首次落地骨架（章节为空或仅占位），按当前掌握的信息补充对应章节。
7. 同步刷新元信息中的 `commit` 字段（子模块文档；粒度候选不刷 commit，因为代码未变）。
8. 新建文档时使用 `python3 ~/.agent-docs/scripts/doc-scaffold.py <module_path> <project_root>` 生成骨架。
9. 写入文档：用 `fs_write` 写入 markdown 内容后，立即调用 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <path>` 兜底（自动检测并修复 GBK / BOM / CRLF）。

### 阶段 C：输出与审批

0. **initial_bootstrap_done 翻转检查**（手册 §13）：
   - 检查 `_index.md` 的 `project_config.initial_bootstrap_done` 字段。
   - 若为 `false` 且以下条件**全部**满足，则在本次 diff 中包含将其改为 `true`：
     - `.gitmodules` 中所有子模块（经 slug 映射后）在 `_index.md` 活跃子模块表中均有对应条目。
     - 所有活跃子模块对应的文档均非骨架——至少 `## 定位` 和 `## 职责边界` 两个章节有实质内容（非 `_待生成_`、非空）。
     - 主模块文档 `main-module.md` 至少 `## 定位` 有实质内容。
   - 条件不满足则不翻，留待后续 `/doc-update` 完成后再翻。
1. 将全部改动以 unified diff 格式写入审阅文件：
   - 将修改后的文档内容用 `fs_write` 写入 `<project>/.agent-docs/.tmp/doc-new.md`。
   - 调用 diff 脚本生成 unified diff：
     ```
     python3 ~/.agent-docs/scripts/doc-diff.py --old <原始文档路径> --new <project>/.agent-docs/.tmp/doc-new.md --out <project>/.agent-docs/.tmp/pending-review.md
     ```
   - 立即用 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <project>/.agent-docs/.tmp/pending-review.md` 修复编码。
   - 清理临时文件 `<project>/.agent-docs/.tmp/doc-new.md`。
   - 若涉及多个文档，按上述流程逐个生成 diff，全部追加到同一 `pending-review.md`。
2. 告知用户：**"改动已写入 `.agent-docs/.tmp/pending-review.md`，请查看后回复 yes 落盘。"**
3. **禁止将大段 diff 逐字输出到对话框**。对话中只需一句话说明改动概要（如"3 份 sha 刷新 + 1 份内容更新"）。
4. **只有用户回复 yes 之后**才写文件。回复 no 或修改建议则按用户意见调整后重新生成审阅文件。

## 硬约束

- 永远不要静默写文件。每一份要变的文档都必须出现在 diff 中。
- 主模块文档与子模块文档同等对待，不可遗漏。
- sha 必须从 `origin/<branch>` 取（远端），不用本地 HEAD（除非远端引用不存在）。
- 单条命令收尾时同步更新 `_index.md` 的清单（如果子模块定位 / 一句话描述变了）。
- 不复制实现细节、不写行号、不写补丁式叙述（参见 §6）。
- 粒度补充须以 agent 本次对话中**实际读过**的源码为依据，禁止凭推测扩写文档。
- 粒度补充必须遵守 §6 全部硬约束；不引入新章节，仅扩写已有章节。
- 粒度候选与 stale 是两条独立分支：stale 目标走 SHA 漂移流程并刷 commit；粒度候选不刷 commit，因为代码未变。同一目标若两条都触发，分别处理后合并到同一份 diff。
- **structure 同步刷新（强不变量，对应手册 §7）**：本流程对任一文档的正文做出变动时，**必须**重跑 `python3 ~/.agent-docs/scripts/doc-structure-import.py <doc_path> <module_path> <project_root>` 覆盖 structure 字段。三种情形均适用：(a) sha 漂移内容刷新；(b) 粒度补充扩写；(c) schema 升级补字段。**正文每改一次 → structure 必须同步重提**；漏刷 = doctor 视为不一致警告。
- **触发条件扩展（对应手册 §7）**：
  - 协作关系变化（`cross_module_contracts` 候选清单变更）→ 触发对应章节更新
  - 子模块 `## 典型修改场景` **永不自动触发**——纯经验沉淀，仅用户主动要求时维护
- **正文 ↔ structure 双向一致**：正文中描述的协作关系必须回填 `cross_module_contracts`。正文写多少，structure 就回填多少。
