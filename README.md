# agent-doc-system

基于项目的 git submodule 结构自动构建文档库，描述各模块的职责与架构。以远程 URL、仓库、分支作为文档划分依据；以文档内容与实际代码是否一致、远端 commit sha 与文档记录是否一致作为更新依据。

系统由技能、检测脚本和项目文档库组成，可在支持技能或读取 SKILL.md 的 AI 环境中使用。可选执行门限目前提供 Codex 原生适配器，在实际文件变化后运行检查并保存审阅状态；其他宿主需适配和验证原生事件。能力范围见手册 §16.2。

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

### 可选：Codex 执行门限

登记器要求 Python 3.11 或更高版本，以解析宿主 TOML 配置。

```bash
python3 ~/.agent-docs/scripts/selftest.py
python3 ~/.agent-docs/scripts/doc-lint-consistency.py ~/.agent-docs
python3 ~/.agent-docs/scripts/doc-gate-install.py --stage-disabled
```

唯一标识为 `agent-doc-system-context-update-gate`，五个事件覆盖每轮上下文、压缩恢复、写前限制、写后检查和停止时督办。登记前运行能力测试；映射保持禁用，须经宿主审阅、信任和隔离验证后启用。项目文档提案按文件哈希绑定，每块 diff 经原生用户输入精确确认后落盘；中断可恢复，冲突可撤销旧确认并重审。

观测范围限于当前项目及已初始化子模块中的 Git 跟踪文件与非忽略新文件。原生回调可能被绕过或失败放行；`Stop` 能要求继续执行，不能在答复发布前拦截。完整协议、确认方式及限制见手册 §16.2。

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

### 方式二：手动运行脚本

```bash
python3 ~/.agent-docs/installers/install-global.py --upgrade --purge
```

`--purge` 会清理目标目录中在新版本不再存在的过时文件。

## Skills

| 指令 | 用途 |
|---|---|
| `/doc-context` | 加载索引、主模块及相关模块正文；支持原生事件注入和加载记录 |
| `/doc-init` | 初始化新项目的文档库（第一阶段：扫子模块出清单） |
| `/doc-update [module]` | 更新文档。sha 漂移检测 → 内容刷新 → diff 审批 → 落盘 |
| `/doc-doctor` | 健康检查：编码/schema/命名/归档/冗余字段/章节缺失 |
| `/doc-rebuild` | 全量重建文档库，先列清单等确认 |
| `/doc-prune` | 物理删除孤儿归档文档，先列清单等确认 |
| `/doc-merge <path>` | 跨项目合并文档库，章节级验证 + 实际代码对账 |
| `/doc-tree` | 只读输出文档库结构树 |
| `/doc-sync-system` | 拉取最新 skill 包并安装，脚本失败时 agent 代理 |

## 目录结构

```
agent-doc-system/
├── README.md
├── urls.conf
├── manual/doc-system.md     # 全局操作手册（含门限协议）
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
