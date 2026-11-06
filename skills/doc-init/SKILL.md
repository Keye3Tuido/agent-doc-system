---
name: doc-init
description: "Initialize the documentation library when the current project has no .agent-docs/ folder. Use this skill when the user asks to set up, create, or bootstrap the project documentation system. Refuses if the documentation library already exists; in that case suggest /doc-rebuild."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§13（首次落地）+ §14（冷启动检测）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 必要前置

执行本 skill 前必须运行：

```bash
python3 ~/.agent-docs/scripts/doc-gate-install.py --require-ready
```

只有退出码为 0 且返回 `ready: true` 才能继续。适配器或映射缺失、禁用、缺少宿主信任、能力不足、包或宿主变化、原生验证未完成时，停止本 skill 及依赖它的项目流程，报告检查结果，按手册 §16.2 核实当前 AI 软件的能力、建立或修复对应适配器与 Hook，完成验证后重试；体系不绑定 Codex，不能用其他宿主的适配器代替当前宿主；不得改走手动执行或把隔离脚本测试当作宿主验证。安装、诊断和修复文档体系本身可继续，范围不延伸至业务项目操作。

## 执行步骤

1. 加载全局 `~/.agent-docs/manual/doc-system.md`，明确 §13 与 §14 流程。
2. 检查项目根 `.agent-docs/` 是否存在：
   - 若存在 `_index.md` 或 `doc-library/`，**拒绝执行**。在第一条回复正文最开头打印一行 `> [doc-init-blocked] 文档库已存在，请改用 /doc-rebuild`，结束。
   - 若不存在，继续。
3. 从全局模板准备 `_index.md` 与 `doc-library/main-module.md` 的完整内容，只写入 `.agent-docs/.tmp/`；保留模板 schema，解析主仓库 origin，填入 `project_config.repo_root_marker`。此时不创建正式文档。
4. 按手册 §16.2，用 `doc-gate.py begin` 同时指定上述两个目标；把完整内容与初始化理由写入提案 JSON，运行 `propose`。即使尚无 `_index.md`，执行器也支持建立和确认初始化提案。
5. 告知用户查看执行器生成的 `.agent-docs/.tmp/pending-review.md`，逐块发送其中的精确 `确认文档 <change_id> <摘要>`。全部确认后执行器创建文档、规范编码，并建立空的 `doc-library/modules/`。普通 yes 或清单确认不能授权正式写入。
6. 执行 §13 第一阶段：解析 `.gitmodules`，输出子模块清单（每条含路径 + origin URL + 当前 branch + 一句话定位草案）。**不生成任何子模块 .md 文件**。
7. 等用户确认清单后，引导用户用 `/doc-update` 或 `/doc-doctor` 走第二阶段填充。

## 不做什么

- 不在已有文档库的项目上工作。
- 不生成任何子模块文档主体内容（仅出清单）。
- 不修改全局 `~/.agent-docs/manual/` 下任何文件。

## 硬约束

- 正式文档必须经就绪门限提案，并收到全部精确用户确认后由执行器落盘。
- 全程 UTF-8 / 不带 BOM / LF 行尾。
- 编码规范化由执行器在批准后完成；失败时按 §16.2 保留提案并恢复，不能绕过门限直接重写。
