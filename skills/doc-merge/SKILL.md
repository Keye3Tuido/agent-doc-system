---
name: doc-merge
description: "Merge documentation libraries from one or more other projects into the current project's library. Compares same-named docs section by section, verifies each conflicting claim against the current project's actual source code, keeps only what matches reality, and marks foreign-only docs as archived. Always backs up first, lists all proposed actions, and requires user approval before writing. Use when the user asks to merge, combine, import, or sync documentation libraries across projects."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§5（命名/冲突）+ §6（写文档约束）+ §9（yaml schema）+ §10（archived 流程）+ §11（diff 提议格式）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 触发形式

`/doc-merge <other-project-steering-path1> [<other-project-steering-path2> ...]`

每个参数必须是另一个项目的 `.agent-docs/` 目录绝对路径。

## 执行步骤

### 阶段 0：备份

1. 在 `<project>/.agent-docs/.tmp/merge-backup-<YYYYMMDD-HHMMSS>/` 整库拷贝当前 `.agent-docs/` 全部内容。**不放在 steering 树内**，避免 Kiro 误加载。
2. 第一条回复仅声明已备份与备份路径，**不打印改动数量**（数量在阶段 3 才确定）。例如：
   `> [doc-merge-pending] 已备份至 .agent-docs/.tmp/merge-backup-<timestamp>/，开始扫描外部副本…`

### 阶段 1：扫描 + 候选分类

**主键定义**：以 yaml 头部 `(origin_host, owner, name, branch)` 四元组作为唯一主键。文件名当作衍生（按 §5.1 推算）。同一四元组在不同项目中文件名可能不一致，以当前项目的标准命名为准。

**附属文档**：`<repo-id>__<branch-slug>__<sub>.md` 与主文档同主键 + `sub_section` 字段，合并规则与主文档一致。

对每个外部路径，扫 `doc-library/modules/`（包括所有 `.md`，不区分 archived），按主键与当前项目对比，得到四类候选：

- **A. 外部独有 + 当前 .gitmodules 含该仓库**：当前项目缺该文档，但仓库在挂载列表里 → 作为活跃文档引入。
  - 仓库在但分支不同：分支文档可共存（每分支一份），按新文档处理。
- **B. 外部独有 + 当前 .gitmodules 不含该仓库**：仓库不在挂载列表 → **询问用户**：(1) 标记 `archived: true` + `archived_reason: imported-from-other-project` + `archived_at: <ISO 日期>` 引入；(2) 跳过；(3) 自定义处理。**不自动引入**。这是你"当前项目没这个模块也没这个文档时让用户选择"的场景。
- **C. 同主键重叠（当前项目有该文档）**：按"章节级实际项目验证合并"处理（见阶段 2）。所有外部副本统一参与比对，不再多源裁决。
- **D. 多源外部独有**：多个外部路径都有同主键文档但当前项目没有 → 与 B 类合并询问，让用户选择保留哪个外部副本（或全部跳过）。

### 阶段 2：章节级实际项目验证合并（核心，仅适用于 C 类）

对每份"同主键重叠"文档，**当前项目存在该文档**：

1. 按 §8 文档模板的 13 个章节切分当前文档与所有外部副本。
2. 对每个章节，从"当前文档 + 所有外部副本"中收集所有候选段落/列表项/接口列表/路径等差异点。
3. 对每个差异点，**去当前项目源码实际查证**（验证策略见下方）：
   - 与当前项目代码/配置/.gitmodules/资源文件**一致** → 写入合并版本。
   - 与现状**不一致** → 丢弃（无论来自哪一方）。
   - 多个候选都对、表述不同（同义） → 取信息密度更高的一方。
   - 都错或都无法验证 → 保留当前项目原说法，加内联注释 `<!-- doc-merge: 该段未能验证，保留原值 -->` 供后续 `/doc-update` 处理。
4. 章节级特例：
   - 当前文档章节为空（`_待生成_` 或仅空白）+ 外部至少一份非空 → 选信息密度最高且经过验证的外部内容直接采纳。
   - 所有副本该章节都为空 → 保留 `_待生成_` 占位。

**验证策略指引**：

- 「定位 / 职责边界 / 警示」类描述性章节：grep 关键类名、模块说明文档、README 是否一致。
- 「架构」：读子模块顶层 `.hpp` / `CMakeLists.txt` / `Android.mk` 等，对比是否符合描述的分层、关键类。
- 「接口 / 数据契约」：grep 描述提到的类名、方法名、字段名，确认存在于当前代码中。
- 「依赖」：对照 `.gitmodules`、`CMakeLists.txt` 的 `target_link_libraries`、第三方库引用语句。
- 「配置与资源」：对照实际 `Resources/`、`config/` 路径或资源命名约定。
- 「外部入口 / 关键流程 / 生命周期」：找入口类的 `init` / `update` / 析构调用链是否匹配。
- 「使用约束 / 可观测性」：grep 日志 tag、断言、并发原语。

**yaml 头部处理**：

- 保留当前项目原有 yaml 字段。
- `commit` 字段**重读当前项目对应子模块的远端 sha**（`git -C <module> rev-parse origin/<branch>`），不沿用旧值。
- 外部 yaml 头部一律忽略。

### 阶段 3：清单确认

把阶段 1 + 2 的产物聚合为一份审阅文件：

- 先用 `fs_write` 把合并清单写到 `<project>/.agent-docs/.tmp/diff-staging.md`。
- 立即用 `python3 ~/.agent-docs/scripts/doc-write-utf8.py <project>/.agent-docs/.tmp/diff-staging.md` 修复编码（兜底 fs_write 的 GBK 漏写）。
- 再调用：
  ```
  python3 ~/.agent-docs/scripts/doc-diff-propose.py <project_root> --from <project>/.agent-docs/.tmp/diff-staging.md --title "doc-merge: N actions"
  ```

清单分类：

- **A 类（活跃引入）**：N 份，列文件名 + 来源外部路径。
- **B 类（待用户决定）**：N 项，每项标注 `(1)/(2)/(3)`，等用户在 yes 回复中嵌入选择，例如 `yes B1=1, B2=2, B3=3`。
- **C 类（章节级合并）**：N 份，每份列出"采纳的章节数 / 保留原值并加注释的章节数"，并在审阅文件中给出**完整 unified diff**。
- **D 类（多源独有）**：N 项，列各副本来源 + 让用户选 `keep=<source>` 或 `skip`。
- **备份位置**：`.agent-docs/.tmp/merge-backup-<timestamp>/`。

**对话中只输出概要**（如"3 份引入 + 5 项待裁决 + 7 份章节合并"），告知用户：
> 改动已写入 `.agent-docs/.tmp/pending-review.md`，请查看后回复 yes（含 B/D 类裁决，例如 `yes B1=1 B2=2 D1=keep=path-a`）落盘。

### 阶段 4：执行 + 同步

用户回复合法 yes 后：

1. 解析 yes 中嵌入的 B/D 类裁决参数。无裁决项默认按"跳过"处理。
2. 写入所有合并 / 新增文档：用 `fs_write` 写入后立即调用 `python3 ~/.agent-docs/scripts/doc-write-utf8.py <path>` 兜底（自动修复 GBK / BOM / CRLF）。
3. 同步更新 `_index.md` 的活跃子模块表 / 归档子模块表。**不修改 `project_config`**。
4. 调用 §10 归档规则做兜底校验（确保 archived 标记字段齐全）。
5. 输出最终 unified diff 到审阅文件并告知用户成功。

### 阶段 5：副本处理

合并成功 → 询问"是否删除备份 `.agent-docs/.tmp/merge-backup-<timestamp>/`？回复 yes 删除。"用户回复 yes 才物理删除；其他回答保留备份。

合并失败（任何阶段抛异常或用户中途取消）→ 询问"是否从备份恢复并删除已写入的失败产物？回复 yes 恢复。"用户回复 yes 才执行恢复。

## 硬约束

- **不接受 "yes" 之外的批准词**；不接受隐式同意。
- **绝不动外部项目的 `.agent-docs/`**。本 skill 对外部路径只读。
- **绝不修改当前项目 `_index.md.project_config`**。这是身份信息。
- **绝不修改 `doc-library/main-module.md`**。主模块不参与跨项目合并。
- **B 类、D 类必须经用户裁决**，agent 不得擅自决定。
- 章节级合并时，每个差异点必须有明确的"实际项目验证"动作（读源码、读配置、读 .gitmodules），不能凭推测。
- 写文件强制 UTF-8 / 无 BOM / LF / 无句中硬换行。
- diff 必须通过 `doc-diff-propose.py` 写入审阅文件，**禁止逐字输出到对话**。
- 单次 diff 总行数 > 300 行 → 自动按"一份文档一块"拆分（§11）。

## 失败回滚

阶段 4 写入过程中出错 → 立即停止，保留已写入的部分文件，输出错误位置 + 当前状态，进入阶段 5 的失败分支等用户决定恢复或保留。
