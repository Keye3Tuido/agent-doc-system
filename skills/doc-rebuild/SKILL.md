---
name: doc-rebuild
description: "Fully rebuild the project documentation library from scratch. Clears doc-library/modules/ and doc-library/main-module.md, then re-runs the full bootstrap. Preserves _index.md project_config but resets the index table. Use when the user asks to fully rebuild, reset, or regenerate the entire documentation library. Lists all files to be cleared and waits for user confirmation before any action."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§13（首次落地两阶段）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 执行步骤

1. 加载全局 `~/.agent-docs/manual/doc-system.md`，明确 §13 全流程。
2. 列出**将被清空 / 重置的文件清单**：
   - `doc-library/main-module.md`（重置为模板骨架）
   - `doc-library/modules/` 下所有 `.md` 文件（删除，含归档标记的文档）
   - `_index.md`（保留顶部 `project_config`，主模块 / 活跃子模块 / 归档子模块三张表清空）
3. 将清单写入审阅文件：
   - 直接用 `fs_write` 把清单写入 `<project>/.agent-docs/.tmp/pending-review.md`。
   - 立即用 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <project>/.agent-docs/.tmp/pending-review.md` 修复编码。
4. 告知用户：**"重建清单已写入 `.agent-docs/.tmp/pending-review.md`，请查看后回复 yes 继续。"**
5. **必须等用户回复 yes 之后**才动手。
6. 执行清理动作。
7. 执行 §13 第一阶段：对每个子模块运行 `python3 ~/.agent-docs/scripts/doc-scaffold.py <module_path> <project_root>`，把骨架文本收集起来汇总成子模块清单（含路径、origin URL、branch、一句话定位草案）展示给用户。该脚本只输出到 stdout；**本阶段不写任何 `.md` 文件**（§13 第一阶段的硬要求）。
8. 等用户再次确认清单后，进入第二阶段：逐份填充文档内容。每份文档：
   - **使用手册当前 schema 版本**：读取 `~/.agent-docs/manual/doc-system.md` 中的当前 schema 版本，所有新建文档的 `schema_version` 字段必须使用该版本。
   - **按当前模板生成**：对照 `~/.agent-docs/templates/` 中的模板文件和手册§9的schema定义，确保文档结构和字段完整符合当前版本要求。
   - 扫描对应子模块源码，把结构信息写进正文的「架构」「接口」「数据契约」「依赖」等章节（v7 起 frontmatter 不承载结构数据）。
   - 用 `fs_write` 写入 markdown 内容到目标路径。
   - 立即调用 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <path>` 兜底（默认模式修 BOM / CRLF / 孤立 CR；若不是合法 UTF-8 则拒绝改动并非零退出，此时必须重写该文件，见手册 §6.1）。
9. 翻转 `initial_bootstrap_done`：按手册 §13 第二阶段末条的三项前置条件判定，满足则**在最后一份 diff 中提议**把 `_index.md` 顶部 `project_config.initial_bootstrap_done` 改为 `true`，与其他改动一同经用户审批落盘；不满足则不翻。**不得绕过审批直接写入。**

## 硬约束

- 不接受 "yes" 之外的批准词；不接受隐式同意。
- 拒绝在已经存在大量正在使用的文档时被误触发：清单输出后再三确认。
- 全程 UTF-8 / 不带 BOM / LF 行尾。
