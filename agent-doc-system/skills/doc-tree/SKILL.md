---
name: doc-tree
description: "Print a read-only structural overview of the project documentation library including project config, main-module status, all active and archived submodule documents. Use when the user asks to list, show, or view the documentation structure."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§3（目录结构）+ §9（yaml schema）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 执行步骤

1. 运行脚本获取结构树：
   ```
   python3 ~/.agent-docs/scripts/doc-tree.py <project_root>
   ```
   若输出较长，使用 `--out` 参数重定向到文件：
   ```
   python3 ~/.agent-docs/scripts/doc-tree.py <project_root> --out <project_root>/.agent-docs/.tmp/doc-tree-output.txt
   ```
2. 将脚本输出直接展示给用户。
3. 如需更详细信息（骨架 vs 已填充、章节占位比例），在脚本输出基础上补充读取各文档的章节状态。
4. **不写文件、不修改任何东西**。

## 硬约束

- 只读。任何修改请求都不在本指令范围内。
- 不打印文档完整内容，仅元信息与摘要。
