---
name: doc-prune
description: "Permanently delete unused or orphaned documentation files in the project documentation library. Targets archived files whose four-tuple matches no known repository, and active files whose corresponding submodule no longer exists in .gitmodules. Lists all candidates and waits for user confirmation before deleting. Use when the user asks to clean up, prune, or delete unused documentation. THIS COMMAND PHYSICALLY DELETES FILES."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§10（archived 流程）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 必要前置

执行本 skill 前必须运行：

```bash
python3 ~/.agent-docs/scripts/doc-gate-install.py --require-ready
```

只有退出码为 0 且返回 `ready: true` 才能继续。适配器或映射缺失、禁用、缺少宿主信任、能力不足、包或宿主变化、原生验证未完成时，停止本 skill 及依赖它的项目流程，报告检查结果，按手册 §16.2 核实当前 AI 软件的能力、建立或修复对应适配器与 Hook，完成验证后重试；体系不绑定 Codex，不能用其他宿主的适配器代替当前宿主；不得改走手动执行或把隔离脚本测试当作宿主验证。安装、诊断和修复文档体系本身可继续，范围不延伸至业务项目操作。

## 执行步骤

1. 运行检测脚本：
   ```
   python3 ~/.agent-docs/scripts/doc-stale-check.py <project_root>
   python3 ~/.agent-docs/scripts/doc-format-check.py <project_root>
   ```
2. 从脚本输出中识别候选删除项（均在 `doc-library/modules/` 中）。信号来源：`ORPHAN_DOC` 由 `doc-stale-check.py` 给出，归档字段完整性与 `UNPARSEABLE_REPO_URL` 由 `doc-format-check.py` 给出。
   - `ORPHAN_DOC` 且 `archived: true`：四元组与任何已知仓库都对不上、且无 `merged_from` 链 → 候选"孤儿归档文档"。
   - `archived: true` 且元信息字段不全（缺 `archived_at` 或 `archived_reason`）→ 候选"残破归档文档"。
3. 非归档的 `ORPHAN_DOC`（应归档但未标记）**只列不删**，提示用户先用 `/doc-doctor` 走归档流程。
4. 核实候选与索引，按 §16.2 运行 `begin` 指定候选路径及 `_index.md`。准备提案 JSON：候选使用 `action: delete` 并说明删除依据，索引使用 `update` 提供移除条目后的完整内容；本来准确则标为 `unchanged`。
5. 运行 `propose`，向用户报告候选和 `.agent-docs/.tmp/pending-review.md`。用户逐块发送其中的精确 `确认文档 <change_id> <摘要>`；普通 yes 不执行删除。
6. 全部确认后由执行器删除目标并同步索引，核验结果。中断按 §16.2 恢复，不手动删除或补写索引。

## 硬约束

- 只接受执行器绑定当前提案的精确用户确认；删除清单和索引变更必须一起审阅。
- 拒绝在用户没有明确清单时执行批量删除。
- 非归档文档**永不在本指令删除**，强制走 `/doc-doctor` 先归档。
- **身份不可解析者禁止进入删除候选**：若 `doc-format-check.py` 对某文档报 `UNPARSEABLE_REPO_URL`，说明其 `repo` 无法解析出可比对的四元组，「与任何已知仓库都对不上」这一判断对它不成立。此类文档只列出并提示用户先修正 `repo` 字段，**不得**列为删除候选。
- 全程 UTF-8 / 不带 BOM / LF 行尾。
