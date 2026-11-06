---
name: doc-prune
description: "Permanently delete unused or orphaned documentation files in the project documentation library. Targets archived files whose four-tuple matches no known repository, and active files whose corresponding submodule no longer exists in .gitmodules. Deletes only explicitly authorized, verified candidates; documentation changes are reviewed at commit time. Use when the user asks to clean up, prune, or delete unused documentation. THIS COMMAND PHYSICALLY DELETES FILES."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§10（archived 流程）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

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
4. 核实候选、用户授权的删除范围和索引；授权范围不明确时先保留文件，在提交审阅中列为待处理项。
5. 将拟删除文件备份至 Git 目录中的 `agent-docs-backups/`，仅删除已核实且明确获准的归档文件。
6. 用 `doc-tree.py --emit-index-tables` 再生索引两节，运行编码与格式检查；提交时按 §16.2 审阅删除差异。

## 硬约束

- 用户明确授权的删除范围是执行边界；删除清单和索引变更在提交时一起审阅。
- 拒绝在用户没有明确清单时执行批量删除。
- 非归档文档**永不在本指令删除**，强制走 `/doc-doctor` 先归档。
- **身份不可解析者禁止进入删除候选**：若 `doc-format-check.py` 对某文档报 `UNPARSEABLE_REPO_URL`，说明其 `repo` 无法解析出可比对的四元组，「与任何已知仓库都对不上」这一判断对它不成立。此类文档只列出并提示用户先修正 `repo` 字段，**不得**列为删除候选。
- 全程 UTF-8 / 不带 BOM / LF 行尾。
