---
name: doc-context
description: "Load project documentation library as context before answering questions about code structure, module boundaries, submodule functionality, cross-module calls, architecture, bug investigation, or new feature design. Call this skill whenever the user's request requires understanding the project's documented structure."
---

> 本 skill 是轻量上下文加载器，只读不写、不做文档管理，因此**不需要加载全局手册**。下文出现的 `§n` 仅作为「规则出处」备注，供人工追溯，执行时无需为此去读手册。

## 门限协作

开始前检查宿主中唯一标识 `agent-doc-system-context-update-gate` 的状态。已验证启用时，复用当前轮 `UserPromptSubmit` 或压缩后 `SessionStart` 注入的真实正文；没有本轮加载记录时运行：

```bash
python3 ~/.agent-docs/scripts/doc-gate.py context --project <project_root> --session <宿主真实会话ID>
```

命令返回实际正文，并保存对应文件哈希。全量正文超限时，根据索引选择相关模块，追加可重复的 `--document <项目相对文档路径>`；索引与主模块始终加载，记录只代表所选范围。宿主没有已验证门限时，按下列只读步骤加载；不得把技能口头要求描述为已生效的原生硬拦截。门限安装、能力检查和范围见手册 §16.2，仅在处理这些事项时加载该节。

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

3. 自动识别当前会话关联的子模块并加载对应文档：
   - 从 IDE 环境上下文中获取当前打开的文件列表（active editor file、open editor files）。
   - 把每个打开文件的项目内相对路径，与各子模块文档 frontmatter 的 `origin_path_in_main`（该子模块在主仓库中的挂载路径，如 `Libraries/Bar`）做前缀匹配，确定其所属子模块。**不要用活跃表的 `repo` 列做匹配** —— 那一列是 origin URL，不是文件路径。若某文档缺 `origin_path_in_main`，回退到用 `.gitmodules` 的 `path` 字段配对。
   - 对所有匹配到的子模块，自动读取对应文档：
     ```
     Read <project_root>/.agent-docs/doc-library/modules/<matched-slug>.md
     ```
   - 无需用户显式指定模块名；即使用户未提及任何路径，只要打开的文件落在某个子模块目录内，就主动加载该子模块文档。

4. 根据用户问题中**额外**提到的路径、模块名或子模块 slug（步骤 3 未覆盖的），补充读取相关子模块文档。

5. **按需加载**：

   - schema v7 起 frontmatter 只有 `repo` / `branch` / `commit` 等身份字段，**不再有结构化索引**，因此不存在「只读 frontmatter 就能回答结构问题」的快捷路径——要答内容就得读正文。
   - 大型项目（≥ 30 子模块）控制读取量的办法是**收窄文档范围**而非收窄单份文档的读取深度：先用 `_index.md` 的活跃子模块表按「一句话定位」筛出相关模块，只读这几份的正文。
   - 跨模块查询（如"改 A 影响谁"）：读 A 文档的 `## 依赖`、`## 协作关系`、以及主模块文档的 `## 跨模块数据流` / `## 模块协同模式` 章节，据此反向定位下游模块，再按需加载。
   - 单份文档正文上限 500 行（出处：手册 §6 第 4 条），因此全量读取单份文档的代价可控。

6. 将加载的文档内容融入对用户问题的回答。

## 硬约束

- 项目文档只读，不生成 diff；门限入口仅保存本机运行记录。
- 文档库不存在时不阻断对话——打印提示后正常作答。
- 同一对话中复用仍适用的正文；压缩恢复、文档内容或任务涉及的模块变化后重新加载。不得把正文加载失败或被截断的预览记为已完整加载。
