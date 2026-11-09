---
name: doc-sync-system
description: "Download and install the latest doc-system package (skills + scripts + manual + templates + installers + urls.conf + README.md + VERSION) from a remote URL. Backs up the existing ~/.agent-docs/ content before overwriting; falls back to agent-driven install if the helper script fails. Use when the user asks to update, refresh, fetch, sync, or reinstall the doc-system."
---

> 本 skill 是全局 `~/.agent-docs/manual/doc-system.md` 的执行入口，对应章节：§15（关联 skill）+ §16（工具脚本）。完整规则以手册为准，本文件只列执行步骤，不复述规则。

## 触发形式

- `/doc-sync-system`：从默认 URL 拉取并安装。
- `/doc-sync-system <url>`：从指定 URL 拉取（覆盖默认值）。

默认 URL：从 `~/.agent-docs/urls.conf` 中的 `DOWNLOAD_URL` 字段读取。

## 执行步骤

### 维护范围

安装手册、脚本与技能副本。安装完成后检查并合并当前宿主实际加载的 AGENTS.md 规则（手册 §16.3）；使用本技能包含这项规则维护的授权。保留用户原有规则和其他系统配置，不注册宿主 Hook 或 Git Hook。

升级旧版时移除本系统旧注册及 Git 提交检查入口：先备份，仅去除明确属于文档系统的部分，已有自定义入口恢复或保留。不能整份删除混合 Hook。路径或归属不明时保留并报告具体位置，禁止更新后重新注册旧入口。

### 阶段 A：脚本驱动（首选）

1. 先 dry-run 让用户确认改动范围：
   ```
   python3 ~/.agent-docs/scripts/doc-sync-system.py --dry-run [--url <url>]
   ```
2. 把 dry-run 输出（ADDED / REPLACED / REMOVED / UNCHANGED 文件清单）原样转给用户，等用户回复 yes 再继续。`REMOVED` 只允许来自脚本内的显式 `OBSOLETE_PATHS` 迁移清单。
3. 用户确认后正式执行：
   ```
   python3 ~/.agent-docs/scripts/doc-sync-system.py [--url <url>]
   ```
4. 脚本会自动备份当前 `~/.agent-docs/` 的所有内容（skills、scripts、manual、templates、installers、urls.conf、README.md、VERSION）到 `~/.agent-docs/.backup/<时间戳>/`，然后逐文件覆写，并删除 `OBSOLETE_PATHS` 明确列出的已废弃文件。
5. 把脚本的安装摘要（含 backup 路径）转给用户。
6. 安装结束后，**重新加载手册** `~/.agent-docs/manual/doc-system.md`，当前对话立即按新版规则继续。

### 阶段 B：脚本失败时 agent 代理安装

仅在脚本退出码非 0、或脚本本身缺失/损坏时进入此阶段。

1. 用 `web_fetch`（或 `urllib.request`/`curl` 单行命令）下载 zip 到临时目录（如 `<project>/.agent-docs/.tmp/fetch-skills-<时间戳>.zip`）。
2. 解压到临时目录（如 `<project>/.agent-docs/.tmp/fetch-skills-extract-<时间戳>/`）。
3. 检查 zip 顶层是否包含 `skills/`、`scripts/`、`manual/`、`templates/`、`installers/`、`urls.conf`、`README.md` 之一（也可能多一层 wrapper 目录）；若结构异常立即停止并报告。
4. 比对 zip 内文件与 `~/.agent-docs` 现有同路径文件：
   - 不存在 → ADDED
   - 内容相同（字节级） → UNCHANGED
   - 内容不同 → REPLACED
   - 读取 zip 内 `scripts/doc-sync-system.py` 的 `OBSOLETE_PATHS`；清单内路径若已安装且 zip 不再包含 → REMOVED。不得自行推断或扩大删除范围
5. 在第一条回复正文最开头打印 `> [doc-fetch-pending] 阶段 B 代理安装，N 文件待覆盖，备份路径 ~/.agent-docs/.backup/<时间戳>/`。
6. 把完整变更清单转给用户，等用户 yes 才继续。
7. 用户确认后：
   - 复制 `~/.agent-docs/` 的所有内容（skills、scripts、manual、templates、installers、urls.conf、README.md、VERSION）到 `~/.agent-docs/.backup/<时间戳>/`（用 `shutil.copytree` 或 `cp -a`，不要用 `fs_write`）。
   - 用 `shutil.copy2(src, dst)` 或 `cp <src> <dst>` 把解压后的文件逐个搬到目标位置（zip 抽出内容用 `cp` 而非 `fs_write`，避免编码转换风险）。
   - 删除 dry-run 已列出的 REMOVED 文件；只允许删除 `OBSOLETE_PATHS` 中的精确路径。
   - 拷贝完成后，对每个新写入的文件**逐个**跑 `bash ~/.agent-docs/scripts/convert-to-utf8.sh <path>` 兜底，并按**单文件**退出码决策。任意一个失败就回滚到 `.backup/<时间戳>/`。**不要对目录整体调用**——那样退出码是全目录累加的，一个无关文件判不出就会误触发整包回滚。
   - 输出最终摘要（与脚本 INSTALLED 段一致）。
   - 清理 `<project>/.agent-docs/.tmp/` 下的临时 zip 与解压目录。

### 阶段 C：同步 IDE skill 目录

全局 `~/.agent-docs/` 更新完成后（无论经由阶段 A 还是阶段 B），执行以下步骤将变更同步到各 IDE 的 skill 目录。

1. **检测当前 IDE 的安装方式**。agent 根据自身运行环境确定当前 IDE 的 skill 安装目录（Codex 使用实际解析到的 `~/.agents/skills/` 或 `~/.codex/skills/`；如 Kiro 对应 `~/.kiro/skills/`，Claude Code 对应 `~/.claude/commands/`，DeepSeek 对应 `~/.deepseek/skills/`，Cursor 对应 `~/.cursor/skills/`，VSCode/GitHub Copilot 对应 `~/.copilot/skills/`），然后检查该目录中与 `~/.agent-docs/skills/` 同名的条目类型：
   - 若为**软链接**（`os.path.islink()` 为 True）→ 标记为 `symlink`
   - 若为**普通文件/目录**（非软链接） → 标记为 `copy`
   - 若目录不存在或为空 → 标记为 `not_installed`，跳过

2. **软链接方式**：无需额外操作。全局目录已更新，软链接自动指向新内容。仅输出确认信息。

3. **复制方式**：需要将更新后的文件同步到 IDE 目录。
   - 列出本次更新中 ADDED 或 REPLACED 的 skill 文件。
   - 将变更清单展示给用户，格式如：
     ```
     检测到以下 IDE 使用复制方式安装，需要同步更新：
     - ~/.cursor/skills/  (copy 模式，N 个文件需更新)
       REPLACED: doc-update/SKILL.md
       ADDED:    doc-new/SKILL.md
     是否同步？(yes/no)
     ```
   - 结合会话已有授权执行同步。目录式 IDE 可运行 `python3 ~/.agent-docs/installers/install-global.py --source ~/.agent-docs --upgrade --skills-target <IDE技能目录>`，只同步 doc-* 的 `SKILL.md`，不覆盖其他技能或用户附加文件。
   - **不删除 IDE 目录中用户自行添加的、不在 `~/.agent-docs/skills/` 中的条目**。
   - 输出同步摘要。

4. **异常处理**：
   - 若 IDE 目录中同一 skill 既有软链接又有普通文件（混合状态），警告用户并跳过该条目，建议手动清理。
   - 若复制失败，报告错误但不回滚全局安装（全局安装已完成且有备份）。

### 阶段 D：检查自动调用规则

按手册 §16.3 检查实际生效的 AGENTS.md；缺失或过期时运行 doc-agents.py 的 install 幂等合并。复用已有全局规则；安装器测试与宿主加载事实分别核验。

## 硬约束

- **永远先备份再覆写**。无论阶段 A 还是 B，备份目录必须时间戳化、不覆盖既有备份。
- **永远先 dry-run 再写入**。dry-run 输出必须给用户审阅，不得静默执行。
- **只覆盖 zip 内列出的文件**。唯一删除例外是 zip 内同步脚本 `OBSOLETE_PATHS` 明确列出的精确路径；其他包外文件（用户自定义 skill / 脚本）不动。
- **只动 `~/.agent-docs/` 的同步目标内容**（skills、scripts、manual、templates、installers、urls.conf、README.md、VERSION）。保留 specs、自定义文件和已有备份。AGENTS.md 标记区块维护及旧版受管 Hook 的迁移清理按本技能的维护范围执行。
- 安装完成后必须告知用户备份路径，便于回滚。
- 阶段 B 必须显式告知用户进入了"agent 代理安装"模式，不得伪装成脚本结果。
