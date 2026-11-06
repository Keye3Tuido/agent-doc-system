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
3. 从全局模板创建 `_index.md`、`doc-library/main-module.md` 和空的 `doc-library/modules/`，保留 schema，核对主仓库 origin 并填写 `project_config`。用户调用初始化即授权此范围内的创建，不逐文件确认。
4. 解析 `.gitmodules`，输出子模块清单（路径、origin、当前分支、一句话定位）。本技能只完成第一阶段，不生成子模块正文。
5. 按手册 §6 规范编码，运行编码和格式检查。后续用 doc-update 完成第二阶段；提交时按 §16.2 审阅实际文档变化。

## 硬约束

- 已有正式文档库时停止初始化，引导使用 doc-update 或用户明确要求的 doc-rebuild。
- 只修改目标项目，不修改全局工作框架。
- 全程 UTF-8、无 BOM、LF。
