---
name: doc-context
description: "Before reading project code or documentation, silently check freshness, synchronize outdated documentation from verified source, and load the relevant project context. Reuse verified content only while its source and documentation remain unchanged."
---

> 每次读取项目代码或文档前静默执行。文档过时则先按 doc-update 同步，再将正文作为上下文。日常维护直接落盘，文档差异留到提交时审阅；规则见手册 §4、§11、§16.2。

## 静默钩子协作

使用前检查当前 AI 宿主是否已登记并启用 `agent-doc-system-silent-workflow` 的读取前、写后和收尾职责；当前 Codex 用 `doc-workflow.py status` 检查，缺失时按手册 §16.3 登记并在宿主审阅，其他 AI 使用等效事件。安装与维护本体系可以继续，不因门限未启用而锁死修复。钩子的条件和进度只送内部上下文，不向用户播报或索要日常批准。

原生入口按 `agent-doc-system-silent-workflow/<宿主事件名>` 稳定唯一命名；Codex 的完整名称为 `agent-doc-system-silent-workflow/PreToolUse`、`agent-doc-system-silent-workflow/PostToolUse`、`agent-doc-system-silent-workflow/Stop`。首次使用、上下文恢复或配置变化时，逐项核对名称、事件、匹配范围、执行命令、启用及宿主信任状态；同名文件、登记成功或信任字段存在不能代替实际触发证据。重新登记原位更新，名称冲突时保留配置并先查明归属，不能追加重复入口。Codex 用 `statusMessage` 保存名称，宿主可能显示运行标签；日常检查仍只送内部上下文。

验证在隔离环境覆盖六项：三个入口实际执行、重复登记不增加入口、两个系统名称不冲突、无关策略及状态保留、失败命令已产生的写入仍触发同步、重复收尾在文档未同步时不得记为成功；同一项目、同一会话待同步期间最多自动恢复三次，第四次仍失败时按未核验终止，保留缺口及提交门限。新增读取、源码变化和宿主回合变化均不重置次数；仅真实核验完成后清除恢复记录。分别记录脚本测试、登记、启用与宿主原生回调结果；失败或未验证项不得计为通过。

项目文档工作流自动补齐 Git 提交入口；首次加载已核验文档时由 Hook 送入索引及主模块正文，提交动作自动要求 doc-update 核对实际暂存内容。已有用户文档和其他 Hook 保留。

自定义 Git Hook 路径保持不变。安装器先解析实际 pre-commit；已有入口包含受管标识、当前 Python 与脚本路径对应的检查命令，并传递非零退出码时，直接复用且不重写。未集成的自定义入口保留原状，单独记录 needs_integration；已通过源码与文档校验的同步仍可完成，提交时阻止操作并说明需接入 doc-commit-review.py check --project .。

收到内部同步要求时运行 `doc-workflow.py inspect --project <project_root>`，核验相关源码并同步文档后，用返回的 source 摘要运行 `complete --source <摘要> --reason <源码依据与同步结论>`。该完成记录由 agent 保存，不是用户确认。源文件再变或文档被修改后重新核验，未同步时不能记为成功；自动恢复达到上限则保留未核验状态并停止重复续跑；提交审阅仍按手册 §16.2 请求用户确认。

## 读取前检查

- 首次读取、上下文压缩恢复、任务范围变化，或相关代码/文档的 HEAD、暂存区、工作区内容变化时，运行 `python3 ~/.agent-docs/scripts/doc-stale-check.py <project_root>`，并核对相关主仓库与子模块的 `git diff`、`git diff --cached`、非忽略新增文件。远端 SHA 相同不能证明工作区内容未变。
- 后续每次读取前核对上述状态；仅在相关状态与已核验内容相同的情况下复用。发现漂移时先读变化源码，按 doc-update 更新相关章节，再使用文档回答；源码读取是修复过时文档所必需的核验。禁止把旧正文当成已核验事实。
- 缺少源码、子模块未初始化、远端不可达或冲突导致无法同步时，继续完成可核验部分，明确未知事实；保留待解决项，在提交审阅时报告，不逐次请求审批。
- 检查与更新静默进行，不打印日常 stale 警告，不要求专用会话绑定，宿主入口按上述规则检查。

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

- 只修改本次读取所需、已核验过时的文档；同步调用 doc-update 的内容规则。
- 文档库不存在时不阻断对话——打印提示后正常作答。
- 同一对话中复用仍适用的正文；压缩恢复、文档内容或任务涉及的模块变化后重新加载。不得把正文加载失败或被截断的预览记为已完整加载。
