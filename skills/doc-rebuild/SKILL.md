---
name: doc-rebuild
description: "Fully rebuild the project documentation library from scratch. Clears doc-library/modules/ and doc-library/main-module.md, then re-runs the full bootstrap. Preserves _index.md project_config but resets the index table. Use when the user asks to fully rebuild, reset, or regenerate the entire documentation library. Backs up the existing library before rebuilding; reviews documentation changes at commit time."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§13（首次落地两阶段）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## AGENTS.md 自动调用

使用前检查当前宿主实际加载的全局或项目 AGENTS.md 是否包含 `project-doc-skills` 标记区块。运行 `python3 ~/.agent-docs/scripts/doc-agents.py check --agents-file <实际规则文件>`；缺失或过期时，备份后用同样参数的 `install` 合并。使用本技能包含补齐该规则区块的授权；保留区块外规则，标记异常时先查明。已有全局区块适用于当前项目时复用，技能安装在其他目录时加 `--skills-root <技能目录>`。路径不明确时先核实宿主设置，不猜测所有 AI 都读取同一全局位置。宿主未自动读取 AGENTS.md 时，将规则放入其支持的指令入口；不能把写入文件当作已加载的证明。

读取前按 doc-context 核验并加载，项目写入后按 doc-update 同步，提交前审阅实际文档变化。检查在当前任务中静默完成；不登记宿主 Hook 或 Git Hook，不创建反馈续跑消息。当前会话直接执行本技能，自动触发规则以宿主实际加载为准。


## 执行步骤

1. 加载手册 §13、§6、§8、§9，列出主模块、全部子模块（含归档）及索引的重建范围。用户明确要求重建后才执行。
2. 在 Git 目录中的 `agent-docs-backups/` 创建带时间戳的库备份，保留 `_index.md.project_config`。核验新内容完成前保留原库，不先清空再生成。
3. 解析 `.gitmodules`，核验当前主模块和子模块源码；按当前 schema、模板准备完整文档，结构信息写入正文。
4. 替换已核验的文档，再生索引派生表。移除明确属于本次重建范围且已被替代的旧文档；不删除用户附加文件。
5. 运行编码和格式检查；仅在手册 §13 条件满足时将 `initial_bootstrap_done` 改为 `true`。提交前按 §16.2 审阅全部替换与删除。

## 硬约束

- 保留完整备份和项目配置；失败时核对实际落盘状态，按文件恢复，不覆盖并发或用户改动。
- 全程 UTF-8、无 BOM、LF；源码核验未完成的部分不得声称已重建。
