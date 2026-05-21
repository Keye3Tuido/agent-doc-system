---
name: doc-prune
description: "Permanently delete unused or orphaned documentation files in the project documentation library. Targets archived files whose four-tuple matches no known repository, and active files whose corresponding submodule no longer exists in .gitmodules. Lists all candidates and waits for user confirmation before deleting. Use when the user asks to clean up, prune, or delete unused documentation. THIS COMMAND PHYSICALLY DELETES FILES."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§10（archived 流程）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 执行步骤

1. 运行检测脚本：
   ```
   python3 ~/.agent-docs/scripts/doc-stale-check.py <project_root>
   python3 ~/.agent-docs/scripts/doc-format-check.py <project_root>
   ```
2. 从脚本输出中识别候选删除项（均在 `doc-library/modules/` 中）：
   - `ORPHAN_DOC` 且 `archived: true`：四元组与任何已知仓库都对不上、且无 `merged_from` 链 → 候选"孤儿归档文档"。
   - `archived: true` 且元信息字段不全（缺 `archived_at` 或 `archived_reason`）→ 候选"残破归档文档"。
3. 非归档的 `ORPHAN_DOC`（应归档但未标记）**只列不删**，提示用户先用 `/doc-doctor` 走归档流程。
4. 将候选清单写入审阅文件：
   - 先用 `fs_write` 把清单写到 `<project>/.agent-docs/.tmp/diff-staging.md`。
   - 立即用 `python3 ~/.agent-docs/scripts/doc-write-utf8.py <project>/.agent-docs/.tmp/diff-staging.md` 修复编码（兜底 fs_write 的 GBK 漏写）。
   - 再调用：
     ```
     python3 ~/.agent-docs/scripts/doc-diff-propose.py <project_root> --from <project>/.agent-docs/.tmp/diff-staging.md --title "doc-prune: N files to delete"
     ```
5. 告知用户：**"删除候选已写入 `.agent-docs/.tmp/pending-review.md`，请查看后回复 yes 执行物理删除。"**
6. **必须等用户回复 yes 之后**才动手。
7. 执行删除。删除完成后同步更新 `_index.md` 的归档区。

## 硬约束

- 不接受 "yes" 之外的批准词。
- 拒绝在用户没有明确清单时执行批量删除。
- 非归档文档**永不在本指令删除**，强制走 `/doc-doctor` 先归档。
- 全程 UTF-8 / 不带 BOM / LF 行尾。
