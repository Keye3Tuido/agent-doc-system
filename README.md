# agent-doc-system

基于项目的 git submodule 结构自动构建文档库，描述各模块的职责与架构。以远程 URL、仓库、分支作为文档划分依据；以文档内容与实际代码是否一致、远端 commit sha 与文档记录是否一致作为更新依据。

系统由技能、检测脚本和项目文档库组成，可在能读取 SKILL.md 并执行 Python 3.11+ 和 Git 的 AI 环境中使用。读取前静默检查相关文档，写入后静默同步；只有提交时集中审阅文档变化。日常流程由三个宿主入口触发技能，提交门限使用一个 Git pre-commit；其他 AI 按等效事件接入。

## 安装

下载链接: [`agent-doc-system.zip`](https://github.com/Keye3Tuido/agent-doc-system/releases/latest/download/agent-doc-system.zip) 

### 第一步：全局安装（所有 IDE 通用）

```bash
python3 agent-doc-system/installers/install-global.py
```

将手册、脚本、技能、模板、安装器及根目录配置安装到 `~/.agent-docs/`。

Codex 可同时同步实际使用的技能目录：

```bash
python3 agent-doc-system/installers/install-global.py --upgrade --skills-target ~/.agents/skills
```

仅同步包内 doc-* 的 SKILL.md，保留其他技能及附加文件。升级后对比全局包和实际 IDE 文件，避免运行旧副本。

### 项目提交门限（每个仓库安装一次）

```bash
python3 ~/.agent-docs/scripts/doc-commit-review.py install --project <project_root>
```

该命令只安装一个 Git pre-commit，保留已有入口。静默核验与同步另需三个宿主入口，见下文。项目指令持续引用 doc-context（读取前检查）与 doc-update（写后同步）。已有自定义 hooksPath 时按提示集成到原入口。

日常文档同步直接落盘。提交前运行 `doc-commit-review.py prepare --project <project_root>`，展示报告，用户确认本次文档审阅后运行 `approve --project <project_root> --digest <摘要> --reason <结论>`，再正常提交。暂存内容、HEAD 或报告变化后须重新审阅；用户不用抄写摘要。完整步骤与能力边界见手册 §16.2。

### 第二步：为各 IDE 安装 skill

全局安装完成后，需要将 skill 注册到各 IDE。根据 IDE 是否支持软链接，有两种安装方式：

- **软链接（symlink）**：IDE 目录下的 skill 文件指向 `~/.agent-docs/skills/`，升级时只需更新全局目录即可自动生效。适用于支持软链接的 IDE。
- **复制（copy）**：将 skill 文件完整复制到 IDE 目录下。适用于不支持软链接的 IDE。升级后需额外同步 IDE 目录。

> **由 agent 执行安装时**：agent 应询问用户选择哪种方式（symlink / copy），或根据目标 IDE 的已知限制自动选择。若用户无明确偏好，按下方各 IDE 的推荐方式执行。

#### Claude Code（CLI 及 VSCode 扩展）

推荐方式：**软链接**

```bash
for skill in ~/.agent-docs/skills/*/; do
  ln -sf "$skill/SKILL.md" ~/.claude/commands/$(basename "$skill").md
done
```

安装后直接使用 `/doc-init`、`/doc-update` 等 slash command。

#### Kiro IDE

推荐方式：**软链接**（Kiro 已支持软链接形式的 skill 目录，`~/.kiro/skills/` 下的符号链接会被正常发现并加载）

```bash
for skill in ~/.agent-docs/skills/*/; do
  ln -sfn "${skill%/}" ~/.kiro/skills/$(basename "$skill")
done
```

> `-n` 不可省略：目标已是「指向目录的软链接」时，`ln -sf` 会跟随该链接、把新链接建到目标目录内部；`-n` 才会直接替换链接本身。

如需与全局目录解耦，也可改用复制（升级后须额外同步）：

```bash
for skill in ~/.agent-docs/skills/*/; do
  cp -R "$skill" ~/.kiro/skills/$(basename "$skill")
done
```

安装后直接使用 `/doc-init`、`/doc-update` 等 skill。

#### DeepSeek TUI

推荐方式：**软链接**

```bash
for skill in ~/.agent-docs/skills/*/; do
  ln -sf "$skill" ~/.deepseek/skills/$(basename "$skill")
done
```

安装后直接使用 `/doc-init`、`/doc-update` 等 skill。

#### VSCode (GitHub Copilot)

推荐方式：**软链接**

```bash
for skill in ~/.agent-docs/skills/*/; do
  ln -sf "$skill" ~/.copilot/skills/$(basename "$skill")
done
```

安装后 Copilot Agent 会自动发现并加载 skill。

#### Cursor

推荐方式：**复制**（Cursor 从 2.4 起原生支持 Agent Skills 标准，skill 目录为 `~/.cursor/skills/`）

```bash
for skill in ~/.agent-docs/skills/*/; do
  cp -R "$skill" ~/.cursor/skills/$(basename "$skill")
done
```

或使用软链接：

```bash
for skill in ~/.agent-docs/skills/*/; do
  ln -sf "$skill" ~/.cursor/skills/$(basename "$skill")
done
```

安装后 Cursor 会自动发现并加载 skill，在 Agent 对话中输入 `/` 搜索 skill 名称即可手动调用。

## 升级

### 方式一：通过 `/doc-sync-system` 指令（推荐）

在已有对话中运行 `/doc-sync-system`，agent 会自动完成全部流程：

1. 下载最新版本并更新全局 `~/.agent-docs/`（备份 → dry-run → 用户确认 → 覆写）
2. 同步当前 IDE 的 skill 目录：
   - **软链接方式**（如 Claude Code、Kiro、DeepSeek、Cursor、VSCode/Copilot）：无需额外操作，自动生效。
   - **复制方式**：检测变更并提示用户确认后覆盖更新。

升级旧版本前，从宿主移除旧文档系统的 Hook 注册；其他策略保持原样。新版使用 §16.3 的三个静默入口，登记后在宿主中审阅并启用；不要求专用会话绑定。

### 方式二：手动运行脚本

```bash
python3 ~/.agent-docs/installers/install-global.py --upgrade --purge
```

`--purge` 会清理目标目录中在新版本不再存在的过时文件。

## Skills

| 指令 | 用途 |
|---|---|
| `/doc-context` | 加载索引、主模块及相关模块正文；读取前静默检查与同步 |
| `/doc-init` | 初始化新项目的文档库（第一阶段：扫子模块出清单） |
| `/doc-update [module]` | 更新文档。源码核验 → 静默同步 → 提交时审阅 |
| `/doc-doctor` | 健康检查：编码/schema/命名/归档/冗余字段/章节缺失 |
| `/doc-rebuild` | 按用户明确要求备份并重建文档库 |
| `/doc-prune` | 按明确授权范围删除已核实归档 |
| `/doc-merge <path>` | 跨项目合并文档库，章节级验证 + 实际代码对账 |
| `/doc-tree` | 只读输出文档库结构树 |
| `/doc-sync-system` | 拉取最新 skill 包并安装，脚本失败时 agent 代理 |

## 目录结构

```
agent-doc-system/
├── README.md
├── urls.conf
├── manual/doc-system.md     # 全局操作手册（含静默维护与提交审阅流程）
├── scripts/                 # 工具脚本与行为测试
├── skills/                  # 9 个 doc-* skill
├── installers/install-global.py
└── templates/               # _index.md, main-module.md（schema v7）
```

安装后 → `~/.agent-docs/`；项目文档库 → `<project>/.agent-docs/`。

## 迁移方法

### 将文档库迁移到新项目

将已有项目的以下两项拷贝到新项目的 `.agent-docs/` 下：

- `<old-project>/.agent-docs/_index.md`
- `<old-project>/.agent-docs/doc-library/`

在新项目中运行 `/doc-update`，agent 会逐份校验并更新文档内容，使其与新项目实际代码对齐。

### 合并多个项目的文档库

运行 `/doc-merge <other-project-agent-docs-path>`，agent 会逐章节比对，以当前项目实际代码为准裁决冲突，外来仓库文档标记归档。

### 跨机器复用全局配置

将 `~/.agent-docs/` 整个目录打包拷贝到新机器即可（含 `manual/`、`scripts/`、`skills/`、`templates/`、`installers/`和`urls.conf`）。

项目文档库不在全局配置中，各项目独立维护。

## 静默核验与同步入口

当前 Codex 宿主运行 `python3 ~/.agent-docs/scripts/doc-workflow.py register`，登记读前、写后、收尾三个禁用入口，再在宿主 Hook 管理中审阅并启用。其他 AI 按手册 §16.3 映射等效事件。入口唯一标识为 `agent-doc-system-silent-workflow`，不依赖旧适配器或专用会话绑定。

正常检查、状态和进度只进入内部记录。过时文档由 agent 核验源码后同步；钩子负责触发、指纹失效及收尾检查，不能证明文档语义正确。日常维护不请求用户批准，提交时才集中审阅。登记和脚本测试不等于宿主已实际启用。
