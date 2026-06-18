---
name: doc-init
description: "Initialize the documentation library when the current project has no .agent-docs/ folder. Use this skill when the user asks to set up, create, or bootstrap the project documentation system. Refuses if the documentation library already exists; in that case suggest /doc-rebuild."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§13（首次落地）+ §14（冷启动检测）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 执行步骤

1. 加载全局 `~/.agent-docs/manual/doc-system.md`，明确 §13 与 §14 流程。
2. 检查项目根 `.agent-docs/` 是否存在：
   - 若存在 `_index.md` 或 `doc-library/`，**拒绝执行**。在第一条回复正文最开头打印一行 `> [doc-init-blocked] 文档库已存在，请改用 /doc-rebuild`，结束。
   - 若不存在，继续。
3. 在第一条回复中向用户列出**将要执行的动作清单**（不出 diff，因为这一步只是拷模板 + 改 inclusion + 填 origin，纯结构化操作）：
   - 拷贝 `~/.agent-docs/templates/_index.md` → `<project>/.agent-docs/_index.md`，把 `agent_load: manual` 改为 `agent_load: always`。模板文件已包含当前 schema 版本。
   - 拷贝 `~/.agent-docs/templates/main-module.md` → `<project>/.agent-docs/doc-library/main-module.md`，把 `agent_load: manual` 改为 `agent_load: always`。
   - 创建空目录 `doc-library/modules/`，放一个 `.gitkeep`。
   - 解析项目主仓库 origin 并填入 `_index.md` 的 `project_config.repo_root_marker`。
4. **必须等用户回复 yes 之后**才动手。
5. 执行上述动作。每写完一个文件，立即用 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <path>` 兜底（自动检测并修复 GBK / BOM / CRLF；这是因为 `fs_write` 在中文系统有把 UTF-8 误存为 GBK 的历史 bug）。
6. 执行 §13 第一阶段：解析 `.gitmodules`，输出子模块清单（每条含路径 + origin URL + 当前 branch + 一句话定位草案）。**不生成任何子模块 .md 文件**。
7. 等用户确认清单后，引导用户用 `/doc-update` 或 `/doc-doctor` 走第二阶段填充。

## 不做什么

- 不在已有文档库的项目上工作。
- 不生成任何子模块文档主体内容（仅出清单）。
- 不修改全局 `~/.agent-docs/manual/` 下任何文件。

## 硬约束

- 必须等用户 yes 之后才写文件。
- 全程 UTF-8 / 不带 BOM / LF 行尾。
- `_index.md` / `main-module.md` 写入后必须经 `convert-to-utf8.sh` 兜底（自动修复，不依赖 `--check` 模式）。
