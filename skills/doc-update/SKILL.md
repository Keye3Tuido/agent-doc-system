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
     - 对于schema v3+，必须提取并填充`structure`字段（deps/exports/inner）
   - 若文档缺少`schema_version`字段，添加为手册当前版本并按上述流程补全
3. 若文档状态为 `ARCHIVED_BUT_ACTIVE`：去掉 `archived` / `archived_at` / `archived_reason` 字段，将其从 `_index.md` 归档区移回活跃区。
4. **STALE 内容判定**（按手册 §4 第 6 条；仅 stale 目标走此步）：在子模块目录内执行 `git log --oneline <doc_sha>..<remote_sha>`，对照 §7 触发条件逐条审视：
   - 仅当**所有**提交均属"实现细节调整 / bug 修复 / 不影响接口/职责/数据契约/流程"时，方可只刷新 `commit` 字段。
   - 任意提交触及 §7 条件，必须对应章节同步更新；commit message 信息不足时进一步看 `git log -p <doc_sha>..<remote_sha> --stat` 或具体文件 diff。
   - **禁止仅凭 sha 不匹配就只刷 commit 字段**。
4. 扫对应源码当前状态（取必要的源文件、配置文件、入口类）。
5. 按 §8 模板对比文档与现状的差异，准备改动。
   - **粒度补充判定**（仅粒度候选走此分支；stale 目标不走）：
     - 依据是 agent 本次对话中**实际读过**的源码区域，禁止凭推测扩写。
     - 仅当文档**已存在章节**对该区域的描述粒度显著低于代码实际复杂度（例：模块在架构图中只占一行、关键流程缺失、对外接口未列出）时，准备补充改动。
     - 仅补充架构 / 职责边界 / 关键流程 / 接口 / 数据契约层面的信息；**不写实现细节、不写行号、不写具体常数**（参见 §6）。
     - 不引入新章节，仅扩写已有章节。
     - 粒度差距不显著（文档已抓住要点）→ 跳过该目标，不出 diff。
   - **structure 字段提取**（stale 目标与粒度候选均执行）：
     - 调用脚本提取结构化关系数据：
       ```
       python3 ~/.agent-docs/scripts/doc-structure-extract.py <module_path> <project_root>
       ```
     - 脚本输出JSON格式的structure数据（deps/exports/inner）。
     - 解析JSON并更新 yaml frontmatter 的 `structure` 字段。
     - 若当前文档已有 `structure` 字段，对比现状后增量更新；若无则新建。
6. 若该文档还是首次落地骨架（章节为空或仅占位），按当前掌握的信息补充对应章节。
7. 同步刷新元信息中的 `commit` 字段（子模块文档；粒度候选不刷 commit，因为代码未变）。
8. 新建文档时使用 `python3 ~/.agent-docs/scripts/doc-scaffold.py <module_path> <project_root>` 生成骨架。
9. 写入文档：用 `fs_write` 写入 markdown 内容后，立即调用 `python3 ~/.agent-docs/scripts/doc-write-utf8.py <path>` 兜底（自动检测并修复 GBK / BOM / CRLF）。

### 阶段 C：输出与审批

1. 将全部改动以 unified diff 格式写入审阅文件：
   - 先用 `fs_write` 把 diff 内容存到 `<project>/.agent-docs/.tmp/diff-staging.md`。
   - 立即用 `python3 ~/.agent-docs/scripts/doc-write-utf8.py <project>/.agent-docs/.tmp/diff-staging.md` 修复编码（fs_write 中文环境可能写 GBK，下一步 doc-diff-propose.py 严格读 UTF-8 会失败）。
   - 再调用：
     ```
     python3 ~/.agent-docs/scripts/doc-diff-propose.py <project_root> --from <project>/.agent-docs/.tmp/diff-staging.md --title "doc-update: N files"
     ```
   - **禁止使用 stdin 管道**（脚本不再支持 stdin）。
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
