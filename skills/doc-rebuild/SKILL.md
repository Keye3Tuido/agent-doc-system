---
name: doc-rebuild
description: "Fully rebuild the project documentation library from scratch. Clears doc-library/modules/ and doc-library/main-module.md, then re-runs the full bootstrap. Preserves _index.md project_config but resets the index table. Use when the user asks to fully rebuild, reset, or regenerate the entire documentation library. Lists all files to be cleared and waits for user confirmation before any action."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§13（首次落地两阶段）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 必要前置

执行本 skill 前必须运行：

```bash
python3 ~/.agent-docs/scripts/doc-gate-install.py --require-ready
```

只有退出码为 0 且返回 `ready: true` 才能继续。适配器或映射缺失、禁用、缺少宿主信任、能力不足、包或宿主变化、原生验证未完成时，停止本 skill 及依赖它的项目流程，报告检查结果，按手册 §16.2 核实当前 AI 软件的能力、建立或修复对应适配器与 Hook，完成验证后重试；体系不绑定 Codex，不能用其他宿主的适配器代替当前宿主；不得改走手动执行或把隔离脚本测试当作宿主验证。安装、诊断和修复文档体系本身可继续，范围不延伸至业务项目操作。

## 执行步骤

1. 加载全局 `~/.agent-docs/manual/doc-system.md`，明确 §13 全流程。
2. 读取现有库并列出重建范围：主模块、全部子模块（含归档）和索引。保留 `_index.md.project_config`，仅在 §13 条件满足时提议翻转 `initial_bootstrap_done`。准备完成与确认前保留原库。
3. 执行 §13 第一阶段：对每个子模块运行 `doc-scaffold.py <module_path> <project_root>`，收集 stdout 并展示清单（路径、origin、branch、一句话定位）；此阶段不创建正式子模块文档，等待用户确认模块范围。
4. 按确认范围核验源码，依当前 schema、模板和 §9 准备完整主模块、子模块及索引内容，暂存在 `.agent-docs/.tmp/`。结构信息写入正文，不写入已废弃的 frontmatter 字段。
5. 按 §16.2 建立覆盖全部目标的 `begin` 审阅，运行 `propose`：保留或新建的路径用 `update`，不再保留的模块文档用 `delete`。同一路径仅有一个最终决策，不先删除再重建；索引派生表反映最终库。
6. 用户审阅 `.agent-docs/.tmp/pending-review.md` 并逐块发送精确确认；模块清单确认或普通 yes 不授权正式写入。全部块确认后由执行器落盘，随后核验完整库。
7. 中断时保留实际状态，按 §16.2 重试 `apply` 或 `recover`。不能先清空原库再准备内容，也不能直接覆盖、删除正式文档。

## 硬约束

- 正式写入与删除必须绑定完整最终提案及全部精确用户确认。
- 明确展示所有替换和删除目标，保留配置与源码核验依据。
- 全程 UTF-8 / 不带 BOM / LF 行尾。
