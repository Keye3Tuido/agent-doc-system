---
name: doc-merge
description: "Merge documentation libraries from one or more other projects into the current project's library. Compares same-named docs section by section, verifies each conflicting claim against the current project's actual source code, keeps only what matches reality, and marks foreign-only docs as archived. Always backs up first, lists all proposed actions, and requires user approval before writing. Use when the user asks to merge, combine, import, or sync documentation libraries across projects."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§5（命名/冲突）+ §6（写文档约束）+ §9（yaml schema）+ §10（archived 流程）+ §11（diff 提议格式）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 必要前置

执行本 skill 前必须运行：

```bash
python3 ~/.agent-docs/scripts/doc-gate-install.py --require-ready
```

只有退出码为 0 且返回 `ready: true` 才能继续。适配器或映射缺失、禁用、缺少宿主信任、能力不足、包或宿主变化、原生验证未完成时，停止本 skill 及依赖它的项目流程，报告检查结果，按手册 §16.2 核实当前 AI 软件的能力、建立或修复对应适配器与 Hook，完成验证后重试；体系不绑定 Codex，不能用其他宿主的适配器代替当前宿主；不得改走手动执行或把隔离脚本测试当作宿主验证。安装、诊断和修复文档体系本身可继续，范围不延伸至业务项目操作。

## 触发形式

`/doc-merge <other-project-steering-path1> [<other-project-steering-path2> ...]`

每个参数必须是另一个项目的 `.agent-docs/` 目录绝对路径。

## 执行步骤

### 阶段 0：备份

1. 在 `<project>/.agent-docs/.tmp/merge-backup-<YYYYMMDD-HHMMSS>/` 整库拷贝当前 `.agent-docs/` 全部内容。**不放在 steering 树内**，避免 Kiro 误加载。
2. 第一条回复仅声明已备份与备份路径，**不打印改动数量**（数量在阶段 3 才确定）。例如：
   `> [doc-merge-pending] 已备份至 .agent-docs/.tmp/merge-backup-<timestamp>/，开始扫描外部副本…`

### 阶段 1：扫描 + 候选分类

**主键定义**：以 `(host, owner, name, branch)` 四元组作为唯一主键，其中 host / owner / name 由 yaml 的 `repo` 字段运行时解析得出（不单独存储，见 §9），branch 取 yaml 的 `branch` 字段。文件名当作衍生（按 §5.1 推算）。同一四元组在不同项目中文件名可能不一致，以当前项目的标准命名为准。若某副本被 `doc-format-check.py` 报 `UNPARSEABLE_REPO_URL`，其四元组不可比对，**不得参与主键匹配**，只列出并提示用户先修 `repo`。

**附属文档**：`<repo-id>__<branch-slug>__<sub>.md` 与主文档同主键，靠文件名的 `__<sub>` 后缀区分（`<sub>` 只存在于文件名中，不写入 yaml，见 §6 第 4 条），合并规则与主文档一致。

对每个外部路径，扫 `doc-library/modules/`（包括所有 `.md`，不区分 archived），按主键与当前项目对比，得到四类候选：

- **A. 外部独有 + 当前 .gitmodules 含该仓库**：当前项目缺该文档，但仓库在挂载列表里 → 作为活跃文档引入。
  - 仓库在但分支不同：分支文档可共存（每分支一份），按新文档处理。
- **B. 外部独有 + 当前 .gitmodules 不含该仓库**：仓库不在挂载列表 → **询问用户**：(1) 标记 `archived: true` + `archived_reason: imported-from-other-project` + `archived_at: <ISO 日期>` 引入；(2) 跳过；(3) 自定义处理。**不自动引入**。这是你"当前项目没这个模块也没这个文档时让用户选择"的场景。
- **C. 同主键重叠（当前项目有该文档）**：按"章节级实际项目验证合并"处理（见阶段 2）。所有外部副本统一参与比对，不再多源裁决。
- **D. 多源外部独有**：多个外部路径都有同主键文档但当前项目没有 → 与 B 类合并询问，让用户选择保留哪个外部副本（或全部跳过）。

### 阶段 2：章节级实际项目验证合并（核心，仅适用于 C 类）

对每份"同主键重叠"文档，**当前项目存在该文档**：

1. 按 §8 文档模板切分章节。**章节清单从硬编码改为读取手册 §8 当前定义**：
   - 主模块：通用 14 章 + §8.1-§8.4 附加（`框架总览` / `业务主循环` / `跨模块数据流` / `模块协同模式`），共 18 章
   - 子模块：通用 14 章 + §8.5-§8.6 附加（`协作关系` / `典型修改场景`），共 16 章
   - 切分前先读 `~/.agent-docs/manual/doc-system.md` §8 确认当前章节集合
2. 对每个章节，从"当前文档 + 所有外部副本"中收集所有候选段落/列表项/接口列表/路径等差异点。
3. 对每个差异点，**去当前项目源码实际查证**（验证策略见下方）：
   - 与当前项目代码/配置/.gitmodules/资源文件**一致** → 写入合并版本。
   - 与现状**不一致** → 丢弃（无论来自哪一方）。
   - 多个候选都对、表述不同（同义） → 取信息密度更高的一方。
   - 都错或都无法验证 → 保留当前项目原说法，加内联注释 `<!-- doc-merge: 该段未能验证，保留原值 -->` 供后续 `/doc-update` 处理。
4. 章节级特例：
   - 当前文档章节为空（`_待生成_` 或仅空白）+ 外部至少一份非空 → 选信息密度最高且经过验证的外部内容直接采纳。
   - 所有副本该章节都为空 → 保留 `_待生成_` 占位。

**验证策略指引（含新章节）**：

- 「定位 / 职责边界 / 业务逻辑 / 警示」类描述性章节：grep 关键类名、模块说明文档、README 是否一致。
- 「业务逻辑」：验依据 = 实际入口类调用链 + 业务流程中涉及的核心文件
- 「架构」：读子模块顶层 `.hpp` / `CMakeLists.txt` / `Android.mk` 等，对比是否符合描述的分层、关键类。
- 「接口 / 数据契约」：grep 描述提到的类名、方法名、字段名，确认存在于当前代码中。
- 「依赖」：对照 `.gitmodules`、`CMakeLists.txt` 的 `target_link_libraries`、第三方库引用语句。
- 「配置与资源」：对照实际 `Resources/`、`config/` 路径或资源命名约定。
- 「外部入口 / 关键流程 / 生命周期」：找入口类的 `init` / `update` / 析构调用链是否匹配。
- 「使用约束 / 可观测性」：grep 日志 tag、断言、并发原语。
- 「框架总览」（主模块）：验依据 = 分层目录 + `.gitmodules` 实际结构；不一致丢弃
- 「业务主循环」（主模块）：验依据 = 入口类的初始化 / 主循环代码
- 「跨模块数据流」（主模块）：验依据 = 实际跨模块数据持有者（代码中跨子模块共享的数据结构）
- 「模块协同模式」（主模块）：验依据 = 当前项目源码中实际存在的 delegate / callback / event / 消息协议调用点
- 「协作关系」（子模块）：验依据 = 当前项目源码中实际的出入向调用；对不上则丢弃
- 「典型修改场景」（子模块）：**经验类章节，不做实际项目验证**，按"信息密度更高且不与现状矛盾"取舍；都为空保留 `_待生成_`

**yaml 头部处理**：

- 保留当前项目原有 yaml 字段。
- `commit` 字段**重读当前项目对应子模块的远端 sha**（`git -C <module> rev-parse origin/<branch>`），不沿用旧值。
- 外部副本若带 v7 之前的 `structure` 字段，**一律删除**，不沿用也不重新提取——该字段已废弃。
- 外部 yaml 头部一律忽略。

### 阶段 3：清单确认

把阶段 1 + 2 的候选与来源写入 `.agent-docs/.tmp/merge-candidates.md`，列出 A 类引入、B 类选择、C 类章节合并依据、D 类多源选择及备份位置。请用户明确 B/D 类裁决（如 `B1=1 D1=keep=path-a`）；未裁决项保持待选，不擅自默认处理。此阶段是内容选择，不授权正式写入。

### 阶段 4：提案 + 同步

1. 根据裁决在 `.agent-docs/.tmp/` 准备全部合并和新增文档，并再生索引表。保留 `project_config`，不修改主模块；检查归档字段齐全。
2. 按 §16.2 运行 `begin` 指定受影响目标；用完整 `decisions` 和 `new_content` 运行 `propose`，让执行器生成最终 `.agent-docs/.tmp/pending-review.md`。不覆盖执行器生成的审阅文件。
3. 告知用户概要与审阅路径，要求逐块发送精确 `确认文档 <change_id> <摘要>`。B/D 裁决和普通 yes 不能替代确认。
4. 全部确认后由执行器写入并规范编码，核验最终结果与索引。

### 阶段 5：副本处理

合并成功 → 询问"是否删除备份 `.agent-docs/.tmp/merge-backup-<timestamp>/`？回复 yes 删除。"用户回复 yes 才物理删除；其他回答保留备份。

合并失败或取消时保留备份和已落盘事实。未完成的提案按 §16.2 使用 `apply` 或 `recover`；需要从备份恢复正式文档时，重新核验并生成恢复提案（含需删除的新增模块），经全部精确确认后执行，不能直接拷回。

## 硬约束

- 正式文档操作只接受执行器绑定当前提案的精确用户确认。备份位于临时目录，其清理可按阶段 5 单独确认。
- **绝不动外部项目的 `.agent-docs/`**。本 skill 对外部路径只读。
- **绝不修改当前项目 `_index.md.project_config`**。这是身份信息。
- **绝不修改 `doc-library/main-module.md`**。主模块不参与跨项目合并。
- **B 类、D 类必须经用户裁决**，agent 不得擅自决定。
- 章节级合并时，每个差异点必须有明确的"实际项目验证"动作（读源码、读配置、读 .gitmodules），不能凭推测。
- 写文件强制 UTF-8 / 无 BOM / LF / 无句中硬换行。
- 最终 diff 必须由 `propose` 生成，禁止把大段 diff 逐字输出到对话。
- diff 每块最多 300 行，由执行器拆分并逐块绑定确认。

## 失败回滚

阶段 4 落盘出错时停止，保留提案、已批准记录与部分文件，报告错误位置及当前状态，按 §16.2 核验后恢复。
