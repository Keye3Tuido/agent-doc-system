---
name: doc-doctor
description: "Check, organize, and archive the project documentation library. Runs encoding / line-ending checks, schema validation and migration, content constraint checks (line budgets, chapter order, forbidden references), naming compliance, duplicate detection, branch-merge archival, and stale SHA detection. Silently applies verified maintenance fixes and reserves documentation review for commit time. Does not delete files; only fixes, moves, or archives. Use when the user asks to check, audit, fix, organize, or tidy the documentation system."
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
4. **advisory 类检查（不阻断，仅汇总）**：

   a. **占位章节统计**：扫每份文档统计含 `_待生成_` 的章节数量，超过 5 章 → 提醒用户用 `/doc-update` 充实。

   b. **yaml 字段白名单检查**：
      - 子模块与附属文档对照手册 §9；`doc-library/main-module.md` 只允许模板定义的 `schema_version`；`_index.md` 允许模板定义的 `schema_version` 与 `project_config`。检查各自 frontmatter 是否包含对应白名单之外的顶层键，**不得把 `_index.md.project_config` 当作冗余字段删除**。
      - 若有 → 列入本 skill 步骤 5 的 schema 迁移项，**由本 skill 自行清理**（只改 yaml、不触正文，属元信息修复范畴）。不要指向 `/doc-update`。
      - 汇总清单，在改动清单中列为"冗余字段清理"类。

   c. **_index.md 派生表对账**：
      - 「活跃子模块」「归档子模块」两张表是派生视图，唯一事实源是各文档的 yaml frontmatter 与 `## 定位` 章节（手册 §0）。
      - 跑 `python3 ~/.agent-docs/scripts/doc-tree.py <project_root> --emit-index-tables`，把输出与 `_index.md` 中现有两节逐行比对。
      - 有任何差异（条目缺失 / 多余 / 列值不符 / 模板占位行残留 / 多余分隔行）→ 一律提议用脚本输出整节替换，不做逐格修补。
      - `project_config` 不是派生视图，不参与本项对账。

   d. **业务逻辑章节检查**：
      - 扫每份文档是否包含 `## 业务逻辑` 章节。
      - 若缺失，警告 `> [doc-doctor] <doc> 缺少 ## 业务逻辑 章节，请跑 /doc-update <module> 补全`。
      - 汇总缺失清单，在改动清单中列为"章节补全"类。
5. **Schema版本检查与升级**：
   - 检查每份文档 yaml frontmatter 中的 `schema_version` 字段。
   - 对比全局手册 `~/.agent-docs/manual/doc-system.md` 中的当前 schema 版本。
   - 若文档版本低于手册版本，**必须按新模板完整升级**，不能只改版本号：
     - 更新 `schema_version` 字段到手册当前版本
     - 对照对应模板与手册 §9，补充所有新增**必填**字段；可选字段仅在其语义适用时添加（例如只有归档文档才添加 `archived_*`）
     - **删除手册 §9 字段表中已不存在的字段**。v5 → v6 需移除：`agent_load`、`origin_host`、`owner`、`name`、`sub_section`。`doc-format-check.py` 会以 `DEPRECATED_FIELD(<字段名>)` 逐项标出
     - 对照 `~/.agent-docs/templates/` 中的模板文件，确保文档结构符合新模板要求
     - v6 → v7 需移除 `structure` 字段（含 `deps` / `exports` / `cross_module_contracts`）。该字段已废弃，`doc-format-check.py` 会以 `DEPRECATED_FIELD(structure)` 标出
   - 若文档缺少 `schema_version` 字段，添加为手册当前版本并按上述流程补全
   - **schema 迁移只改 yaml frontmatter、不触碰正文**（v5→v6、v6→v7 皆如此），因此属于本 skill「元信息修复」范畴，不违反下方「绝不主动重写文档主体内容」的硬约束。本 skill 检查**每一份**文档，与 sha 是否漂移无关——全量迁移走这条路径。
6. 对 `ARCHIVED_BUT_ACTIVE` 项：提议去掉 `archived` / `archived_at` / `archived_reason` 字段，刷新 `commit`，并在 `_index.md` 中从归档区移回活跃区。
7. 把所有问题聚合到一张"将要执行的改动清单"，按以下分类：
   - 编码 / 换行修复：只在 `.agent-docs/.tmp/` 的副本运行 `convert-to-utf8.sh`；默认模式修 BOM / CRLF / 孤立 CR。非法 UTF-8 必须先核实原编码，再对副本用 `--from <enc>` 转换，提案旧文用字节转义展示不可解码内容，核验后再替换正式文件。
   - Schema版本升级：按新模板完整升级（更新版本号 + 补充新增字段 + 删除已废弃字段）
   - 元信息修复：`commit` 与远端不一致、必填字段缺失
   - 归档动作：`.gitmodules` 已不含的子模块文档标记 `archived: true`（文件留在 `modules/` 不移动）
   - 恢复动作：`ARCHIVED_BUT_ACTIVE` 的文档去掉归档标记，刷新 `commit`，移回 `_index.md` 活跃区
   - 重名冲突：四元组重复的文档需要合并
   - 索引派生表再生：`_index.md` 两张表与文档实际状态不一致，按 `doc-tree.py --emit-index-tables` 输出整节替换
   - 章节补全：缺少 `## 业务逻辑` 等必选章节
   - 冗余字段清理 / schema 迁移：文档 yaml 中包含已删除字段或版本落后，由本 skill 直接清理（见步骤 5）
8. 静默应用可确定的元信息、编码、归档、命名与索引修复。命名迁移保留完整正文；已有用户改动不得覆盖。非法 UTF-8 先核实原编码，再用副本显式转换并核对内容。
9. 运行编码和格式检查，保留无法核实的问题；收尾只汇总结果。提交时按 §16.2 统一审阅文档差异。

## 硬约束

- 归档仅更新 yaml 标记；文档清理交给 `/doc-prune`。命名修复允许同批迁移旧路径到新路径，必须保留完整内容，提交时统一审阅。
- **绝不主动重写文档主体内容**。仅修复元信息、编码、换行、命名、归档关系。如需改章节内容，让用户走 `/doc-update`。
- 主模块文档与子模块文档同等对待，不可遗漏。
- 日常修复直接落盘，真实文档差异在提交前统一审阅。
