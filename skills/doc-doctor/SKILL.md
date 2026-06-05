---
name: doc-doctor
description: "Check, organize, and archive the project documentation library. Runs encoding / line-ending checks, schema validation, naming compliance, duplicate detection, branch-merge archival, and stale SHA detection. Aggregates all findings into a single change list and waits for user approval before executing batch fixes. Does not delete files; only fixes, moves, or archives. Use when the user asks to check, audit, fix, organize, or tidy the documentation system."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§4（每对话流程）+ §5（命名/冲突）+ §6（写文档约束）+ §10（archived 流程）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 执行步骤

1. 运行全套检测脚本（**禁止逐个手动执行 git 命令**）：
   ```
   python3 ~/.agent-docs/scripts/doc-stale-check.py <project_root>
   python3 ~/.agent-docs/scripts/doc-encoding-check.py <project_root>
   python3 ~/.agent-docs/scripts/doc-format-check.py <project_root>
   ```
2. 解析脚本输出，汇总所有问题（含 STALE / NO_DOC / ORPHAN_DOC / ARCHIVED_BUT_ACTIVE / BRANCH_GONE / 编码 / schema）。
3. 额外检查 §10 分支合并归档（`git merge-base --is-ancestor`）和 §5 命名合规。
4. **structure 字段验证**（仅对有 `structure` 字段的文档执行）：
   - 检查 `structure.deps` 中引用的模块路径是否存在于当前项目（主仓库路径或 `.gitmodules` 中的子模块路径）。
   - 不存在的依赖标记为警告（不阻塞，因为可能是外部库或已移除的模块）。
   - 检查 `structure.exports` 和 `structure.inner` 的基本格式完整性（必填字段是否存在）。

4.5 **structure 三类 advisory（不阻断，仅汇总）**：

   a. **章节不一致**：列出 "structure 与文档章节不一致" 候选——`structure.exports` 中有但 "## 接口" 章节未提及的符号，或反之，作为人工核对清单。

   b. **structure 新鲜度（兑现 §7 强不变量）**：
      - 缓存路径：`<project>/.agent-docs/.cache/structure-fp.json`，结构 `{ "<doc_path>": { "fp": "<sha256>", "doc_mtime": <epoch>, "ts": <epoch> } }`。
      - 对每份子模块文档：
        - 计算当前 `structure` 字段的稳定 hash（按字段排序后 sha256）作为 `current_fp`。
        - 读 `doc_mtime = os.path.getmtime(doc_path)`。
        - 若缓存无该文档记录 → 写入基线，不报警。
        - 若缓存中 `fp == current_fp` 但 `doc_mtime > cache.doc_mtime` → 警告 `> [doc-doctor] 正文已改但 structure 未刷，请跑 /doc-update <module> 重提`。
        - 若 `fp != current_fp` → 更新缓存，不报警（说明 import 已跑过）。

   c. **structure 空值堆积**：模块代码非空（`find_source_files` 返回 ≥ 1）但 `structure.deps + exports + inner` 三项总条目 < 3 → 警告 `> [doc-doctor] <doc> structure 几乎为空，可能脚本提取失败或语言不支持`。

   d. **占位章节统计**：扫每份文档统计含 `_待生成_` 的章节数量，超过 5 章 → 提醒用户用 `/doc-update` 充实。
5. **Schema版本检查与升级**：
   - 检查每份文档 yaml frontmatter 中的 `schema_version` 字段。
   - 对比全局手册 `~/.agent-docs/manual/doc-system.md` 中的当前 schema 版本。
   - 若文档版本低于手册版本，**必须按新模板完整升级**，不能只改版本号：
     - 更新 `schema_version` 字段到手册当前版本
     - 对照手册§9的schema定义，补充**所有**新增字段（必填+可选）
     - 对照 `~/.agent-docs/templates/` 中的模板文件，确保文档结构符合新模板要求
     - 对于 schema v4+，必须提取并填充 `structure` 字段：
       ```
       python3 ~/.agent-docs/scripts/doc-structure-import.py <doc_path> <module_path> <project_root>
       ```
   - 若文档缺少 `schema_version` 字段，添加为手册当前版本并按上述流程补全
6. 对 `ARCHIVED_BUT_ACTIVE` 项：提议去掉 `archived` / `archived_at` / `archived_reason` 字段，刷新 `commit`，并在 `_index.md` 中从归档区移回活跃区。
7. 把所有问题聚合到一张"将要执行的改动清单"，按以下分类：
   - 编码 / 换行修复：使用 `python3 ~/.agent-docs/scripts/doc-write-utf8.py <path>` 修复（自动检测 GBK/CRLF/BOM 并转换）
   - Schema版本升级：按新模板完整升级（更新版本号 + 补充新增字段 + 提取structure字段）
   - 元信息修复：`commit` 与远端不一致、必填字段缺失
   - 归档动作：`.gitmodules` 已不含的子模块文档标记 `archived: true`（文件留在 `modules/` 不移动）
   - 恢复动作：`ARCHIVED_BUT_ACTIVE` 的文档去掉归档标记，刷新 `commit`，移回 `_index.md` 活跃区
   - 重名冲突：四元组重复的文档需要合并
6. 将改动清单写入审阅文件：
   - 先用 `fs_write` 把清单写到 `<project>/.agent-docs/.tmp/diff-staging.md`。
   - 立即用 `python3 ~/.agent-docs/scripts/doc-write-utf8.py <project>/.agent-docs/.tmp/diff-staging.md` 修复编码（兜底 fs_write 的 GBK 漏写）。
   - 再调用：
     ```
     python3 ~/.agent-docs/scripts/doc-diff-propose.py <project_root> --from <project>/.agent-docs/.tmp/diff-staging.md --title "doc-doctor: N issues"
     ```
7. 告知用户：**"诊断结果已写入 `.agent-docs/.tmp/pending-review.md`，请查看后回复 yes 执行。"** 对话中只需一句话概要（如"发现 3 项编码问题 + 2 项归档"）。
8. **必须等用户回复 yes 之后**才动手。
9. 执行批量改动：
   - 元信息 / 归档动作的 yaml 修改：用 `fs_write` 写入修改后的 markdown，再立即调用 `python3 ~/.agent-docs/scripts/doc-write-utf8.py <path>` 兜底（自动修复 GBK / BOM / CRLF）。
   - 仅编码 / 换行问题（无 yaml 改动）的文档：直接 `python3 ~/.agent-docs/scripts/doc-write-utf8.py <path>` 原地修复。

## 硬约束

- **绝不删除文件**。归档仅标记 yaml 字段 `archived: true`，物理删除留给 `/doc-prune`。
- **绝不主动重写文档主体内容**。仅修复元信息、编码、换行、命名、归档关系。如需改章节内容，让用户走 `/doc-update`。
- 主模块文档与子模块文档同等对待，不可遗漏。
- 单次改动超 300 行 diff 按"一份文档一块"拆分。
