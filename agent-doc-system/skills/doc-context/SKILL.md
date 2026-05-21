---
name: doc-context
description: "Load project documentation library as context before answering questions about code structure, module boundaries, submodule functionality, cross-module calls, architecture, bug investigation, or new feature design. Call this skill whenever the user's request requires understanding the project's documented structure."
---

> 本 skill 是轻量上下文加载器，不做文档管理，无需读取全局手册。

## 执行步骤

1. 读取项目索引（若不存在，打印一行提示后正常作答，不阻断对话）：
   ```
   Read <project_root>/.agent-docs/_index.md
   ```
   若文件不存在：输出 `> [doc-context] 当前项目无文档库，建议运行 /doc-init 初始化` 然后直接回答用户问题。

2. 读取主模块文档（若存在）：
   ```
   Read <project_root>/.agent-docs/doc-library/main-module.md
   ```

3. 根据用户问题中提到的路径、模块名或子模块 slug，匹配 `_index.md` 中的记录，选择性读取相关子模块文档：
   ```
   Read <project_root>/.agent-docs/doc-library/modules/<matched-slug>.md
   ```

4. 将加载的文档内容融入对用户问题的回答。

## 硬约束

- 只读，不写文件，不生成 diff。
- 文档库不存在时不阻断对话——打印提示后正常作答。
- 同一对话中若已加载过文档库内容，跳过 Read 直接复用上下文，不重复加载。
