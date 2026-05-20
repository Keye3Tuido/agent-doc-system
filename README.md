# agent-doc-system

基于项目的 git submodule 结构自动构建文档库，描述各模块的职责与架构。以远程 URL、仓库、分支作为文档划分依据；以文档内容与实际代码是否一致、远端 commit sha 与文档记录是否一致作为更新依据。

系统为纯 skill + 存储形态，不依赖任何 IDE 的自动加载机制。每个 doc-* skill 在执行前主动读取手册，支持 Claude Code、Cursor、Kiro IDE 作为运行环境。

## 安装

链接：<https://k3t.site/ds/agent-doc-system>

### 第一步：全局安装（所有 IDE 通用）

```bash
python3 agent-doc-system/installers/install-global.py
```

将 `manual/`、`scripts/`、`skills/` 安装到 `~/.agent-docs/`。

### 第二步：为各 IDE 创建 skill 软链接

#### Claude Code（CLI 及 VSCode 扩展）

```bash
for skill in ~/.agent-docs/skills/*/; do
  ln -sf "$skill/SKILL.md" ~/.claude/commands/$(basename "$skill").md
done
```

安装后直接使用 `/doc-init`、`/doc-update` 等 slash command。

可选：在项目 `CLAUDE.md` 中追加触发片段，让 agent 自动调用 `/doc-context`：

```bash
cat agent-doc-system/templates/claude-md-snippet.md >> CLAUDE.md
```

#### Kiro IDE

```bash
for skill in ~/.agent-docs/skills/*/; do
  ln -sf "$skill" ~/.kiro/skills/$(basename "$skill")
done
```

安装后直接使用 `/doc-init`、`/doc-update` 等 skill。

#### DeepSeek TUI

```bash
for skill in ~/.agent-docs/skills/*/; do
  ln -sf "$skill" ~/.deepseek/skills/$(basename "$skill")
done
```

安装后直接使用 `/doc-init`、`/doc-update` 等 skill。

#### Cursor

```bash
# 将 snippet 追加到项目 .cursorrules（带 BEGIN/END 标记，可升级/卸载）
python3 agent-doc-system/installers/install-cursor.py [project_root]
```

Cursor 无 slash command，通过 `.cursorrules` 中的 snippet 引导 agent 读取 `~/.agent-docs/skills/<name>/SKILL.md` 执行等价操作。

卸载：`python3 installers/install-cursor.py [project_root] --remove`

## 升级

```bash
python3 agent-doc-system/installers/install-global.py --upgrade
```

或在已有对话中运行 `/doc-sync-system`（自动备份 → dry-run → 用户确认 → 覆写）。

## Skills

| 指令 | 用途 |
|---|---|
| `/doc-context` | 业务对话中加载项目文档库作为上下文（只读，不阻断对话） |
| `/doc-init` | 初始化文档库。仅在本地无文档库时使用。 |
| `/doc-update [module]` | 更新文档。比较远端 sha 与文档记录、内容是否冲突，输出 diff 等用户确认后落盘。 |
| `/doc-rebuild` | 全量重建文档库。 |
| `/doc-merge <path...>` | 合并其他项目的文档库到当前项目。 |
| `/doc-doctor` | 检查文档格式是否规范（编码、命名、schema、归档状态），批量修复。 |
| `/doc-prune` | 物理删除归档中的孤儿文档。 |
| `/doc-tree` | 输出文档库中所有文档的结构清单。 |
| `/doc-sync-system` | 拉取最新版本的 skill 包并安装。 |

## 目录结构

```
agent-doc-system/
├── manual/          # 全局手册（doc-system.md）
├── scripts/         # 工具脚本
├── skills/          # 9 个 skill（含 doc-context）
├── installers/      # install-global.py, install-cursor.py
└── templates/       # _index.md, main-module.md, cursorrules-snippet.md, claude-md-snippet.md
```

安装后对应 `~/.agent-docs/` 下的同名子目录；项目文档库存放在 `<project>/.agent-docs/`。

## 迁移方法

### 将文档库迁移到新项目

将已有项目的以下两项拷贝到新项目的 `.agent-docs/` 下：

- `<old-project>/.agent-docs/_index.md`
- `<old-project>/.agent-docs/doc-library/`

在新项目中运行 `/doc-update`，agent 会逐份校验并更新文档内容，使其与新项目实际代码对齐。

### 合并多个项目的文档库

运行 `/doc-merge <other-project-agent-docs-path>`，agent 会逐章节比对，以当前项目实际代码为准裁决冲突，外来仓库文档标记归档。

### 跨机器复用全局配置

将 `~/.agent-docs/` 整个目录打包拷贝到新机器即可（含 `manual/`、`scripts/`、`skills/`、`templates/`、`installers/`）。

项目文档库不在全局配置中，各项目独立维护。
