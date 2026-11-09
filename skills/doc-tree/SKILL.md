---
name: doc-tree
description: "Print a read-only structural overview of the project documentation library including project config, main-module status, all active and archived submodule documents. Use when the user asks to list, show, or view the documentation structure."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§0（文件分布）+ §9（yaml schema）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## AGENTS.md 自动调用

使用前检查当前宿主实际加载的全局或项目 AGENTS.md 是否包含 `project-doc-skills` 标记区块。运行 `python3 ~/.agent-docs/scripts/doc-agents.py check --agents-file <实际规则文件>`；缺失或过期时，备份后用同样参数的 `install` 合并。使用本技能包含补齐该规则区块的授权；保留区块外规则，标记异常时先查明。已有全局区块适用于当前项目时复用，技能安装在其他目录时加 `--skills-root <技能目录>`。路径不明确时先核实宿主设置，不猜测所有 AI 都读取同一全局位置。宿主未自动读取 AGENTS.md 时，将规则放入其支持的指令入口；不能把写入文件当作已加载的证明。

读取前按 doc-context 核验并加载，项目写入后按 doc-update 同步，提交前审阅实际文档变化。检查在当前任务中静默完成；不登记宿主 Hook 或 Git Hook，不创建反馈续跑消息。当前会话直接执行本技能，自动触发规则以宿主实际加载为准。


## 执行步骤

1. 运行脚本获取结构树：
   ```
   python3 ~/.agent-docs/scripts/doc-tree.py <project_root>
   ```
   若输出较长，可用 `--out` 把结果落到 `.tmp/` 下的临时文件再读回：
   ```
   python3 ~/.agent-docs/scripts/doc-tree.py <project_root> --out <project_root>/.agent-docs/.tmp/doc-tree-output.txt
   ```
   这是本 skill 唯一允许的写入，且**只允许写 `.agent-docs/.tmp/` 下的临时文件**（属计算中间产物，用完即删），不得写文档库内任何文件。
   若用户要的是 `_index.md` 的活跃 / 归档两张派生表（用于替换索引中对应两节）：
   ```
   python3 ~/.agent-docs/scripts/doc-tree.py <project_root> --emit-index-tables
   ```
   本 skill 只输出表格文本给用户，**不代为写入 `_index.md`**——落盘走 `/doc-update` 或 `/doc-doctor` 的静默同步流程。
2. 将脚本输出直接展示给用户。
3. 如需更详细信息（骨架 vs 已填充、章节占位比例），在脚本输出基础上补充读取各文档的章节状态。
4. 用完删除步骤 1 可能产生的 `.tmp/doc-tree-output.txt`。

## 硬约束

- **不修改文档库**：`_index.md`、`doc-library/` 下任何文件都不得写入。
- 唯一允许的写入是 `.agent-docs/.tmp/` 下的临时输出文件（`--out`），用完即删。
- 任何修改文档内容的请求都不在本指令范围内，引导用户走 `/doc-update` 或 `/doc-doctor`。
- 不打印文档完整内容，仅元信息与摘要。
