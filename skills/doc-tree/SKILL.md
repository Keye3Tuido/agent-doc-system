---
name: doc-tree
description: "Print a read-only structural overview of the project documentation library including project config, main-module status, all active and archived submodule documents. Use when the user asks to list, show, or view the documentation structure."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§0（文件分布）+ §9（yaml schema）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 必要前置

执行本 skill 前必须运行：

```bash
python3 ~/.agent-docs/scripts/doc-gate-install.py --require-ready
```

只有退出码为 0 且返回 `ready: true` 才能继续。适配器或映射缺失、禁用、缺少宿主信任、能力不足、包或宿主变化、原生验证未完成时，停止本 skill 及依赖它的项目流程，报告检查结果，按手册 §16.2 核实当前 AI 软件的能力、建立或修复对应适配器与 Hook，完成验证后重试；体系不绑定 Codex，不能用其他宿主的适配器代替当前宿主；不得改走手动执行或把隔离脚本测试当作宿主验证。安装、诊断和修复文档体系本身可继续，范围不延伸至业务项目操作。

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
   本 skill 只输出表格文本给用户，**不代为写入 `_index.md`**——落盘走 `/doc-update` 或 `/doc-doctor` 的 diff 审批流程。
2. 将脚本输出直接展示给用户。
3. 如需更详细信息（骨架 vs 已填充、章节占位比例），在脚本输出基础上补充读取各文档的章节状态。
4. 用完删除步骤 1 可能产生的 `.tmp/doc-tree-output.txt`。

## 硬约束

- **不修改文档库**：`_index.md`、`doc-library/` 下任何文件都不得写入。
- 唯一允许的写入是 `.agent-docs/.tmp/` 下的临时输出文件（`--out`），用完即删。
- 任何修改文档内容的请求都不在本指令范围内，引导用户走 `/doc-update` 或 `/doc-doctor`。
- 不打印文档完整内容，仅元信息与摘要。
