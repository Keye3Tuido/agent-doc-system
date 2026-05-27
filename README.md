# agent-doc-system

基于项目的 git submodule 结构自动构建文档库，描述各模块的职责与架构。以远程 URL、仓库、分支作为文档划分依据；以文档内容与实际代码是否一致、远端 commit sha 与文档记录是否一致作为更新依据。

系统为纯 skill + 存储形态，不依赖任何 IDE 的自动加载机制。每个 doc-* skill 在执行前主动读取手册，支持 Claude Code、Cursor、Kiro IDE、VSCode (GitHub Copilot)、Deepseek TUI 作为运行环境。

## Schema v3 新特性

**结构化关系数据（structure 字段）**

从 schema v3 开始，文档 yaml frontmatter 新增可选的 `structure` 字段，用于记录模块间依赖关系和内部结构：

- **deps**：依赖列表（此模块依赖哪些模块，使用了哪些符号）
- **exports**：导出列表（此模块暴露的公共接口）
- **inner**：内部结构（文件内的类/函数包含关系）

**优势**：
- AI 可直接读取结构化数据，无需重新扫描代码
- 加速理解模块依赖和架构关系
- 保持轻量（模块级粒度，不记录实现细节）

**自动提取**：`/doc-update`、`/doc-rebuild`、`/doc-merge` 会自动从源码提取并更新 structure 字段。

**向后兼容**：structure 为可选字段，旧版文档（schema v2）可正常使用，升级时会自动补全。

## 安装

下载链接: [`agent-doc-system.zip`](https://github.com/Keye3Tuido/agent-doc-system/releases/latest/download/agent-doc-system.zip) 

### 第一步：全局安装（所有 IDE 通用）

```bash
python3 agent-doc-system/installers/install-global.py
```

将 `manual/`、`scripts/`、`skills/` 安装到 `~/.agent-docs/`。

### 第二步：为各 IDE 安装 skill

全局安装完成后，需要将 skill 注册到各 IDE。根据 IDE 是否支持软链接，有两种安装方式：

- **软链接（symlink）**：IDE 目录下的 skill 文件指向 `~/.agent-docs/skills/`，升级时只需更新全局目录即可自动生效。适用于支持软链接的 IDE。
- **复制（copy）**：将 skill 文件完整复制到 IDE 目录下。适用于不支持软链接的 IDE（如 Kiro IDE）。升级后需额外同步 IDE 目录。

> **由 agent 执行安装时**：agent 应询问用户选择哪种方式（symlink / copy），或根据目标 IDE 的已知限制自动选择。若用户无明确偏好，按下方各 IDE 的推荐方式执行。

#### Claude Code（CLI 及 VSCode 扩展）

推荐方式：**软链接**

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

推荐方式：**复制**（Kiro 不支持软链接形式的 skill 目录）

```bash
for skill in ~/.agent-docs/skills/*/; do
  cp -R "$skill" ~/.kiro/skills/$(basename "$skill")
done
```

或使用软链接（如果未来 Kiro 支持）：

```bash
for skill in ~/.agent-docs/skills/*/; do
  ln -sf "$skill" ~/.kiro/skills/$(basename "$skill")
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
   - **软链接方式**（如 Claude Code、DeepSeek、Cursor、VSCode/Copilot）：无需额外操作，自动生效。
   - **复制方式**（如 Kiro、Cursor）：检测变更并提示用户确认后覆盖更新。

### 方式二：手动运行脚本

```bash
python3 ~/.agent-docs/installers/install-global.py --upgrade
```

此命令仅更新全局 `~/.agent-docs/` 目录。完成后需自行同步 IDE 侧：

- **软链接方式**：无需额外操作。
- **复制方式**：重新执行复制命令（参见"第二步"中对应 IDE 的 `cp -R` 命令）。

## Skills

| 指令                     | 用途                                                                          |
| ------------------------ | ----------------------------------------------------------------------------- |
| `/doc-context`         | 业务对话中加载项目文档库作为上下文（只读，不阻断对话）                        |
| `/doc-init`            | 初始化文档库。仅在本地无文档库时使用。                                        |
| `/doc-update [module]` | 更新文档。比较远端 sha 与文档记录、内容是否冲突，输出 diff 等用户确认后落盘。 |
| `/doc-rebuild`         | 全量重建文档库。                                                              |
| `/doc-merge <path...>` | 合并其他项目的文档库到当前项目。                                              |
| `/doc-doctor`          | 检查文档格式是否规范（编码、命名、schema、归档状态），批量修复。              |
| `/doc-prune`           | 物理删除归档中的孤儿文档。                                                    |
| `/doc-tree`            | 输出文档库中所有文档的结构清单。                                              |
| `/doc-sync-system`     | 拉取最新版本的 skill 包并安装。                                               |

## 目录结构

```
agent-doc-system/
├── urls.conf        # 下载链接配置（统一维护）
├── manual/          # 全局手册（doc-system.md）
├── scripts/         # 工具脚本
├── skills/          # 9 个 skill（含 doc-context）
├── installers/      # install-global.py
└── templates/       # _index.md, main-module.md, claude-md-snippet.md
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

将 `~/.agent-docs/` 整个目录打包拷贝到新机器即可（含 `manual/`、`scripts/`、`skills/`、`templates/`、`installers/`和`urls.conf`）。

项目文档库不在全局配置中，各项目独立维护。
