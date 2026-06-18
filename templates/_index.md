---
schema_version: 5
agent_load: always
project_config:
  repo_root_marker: "<主仓库 origin URL，例如 https://github.com/foo/Bar.git>"
  submodule_mechanism: "git-submodule"
  doc_language: "zh-CN"
  submodule_count_throttle_threshold: 30
  initial_bootstrap_done: false
---

# 文档索引

> 本文件是当前项目的文档目录。任一 doc-* skill 启动时主动 Read 本文件，据此知道有哪些子模块文档及归档了哪些已弃用模块。
>
> 顶部 `project_config` 是当前项目的耦合配置。全局 `doc-system.md` 中的 `{{字段名}}` 占位符均指向本块字段。
>
> 本文件由 agent 在每次结构性变动（新增 / 归档 / 重命名 / 合并子模块）后**提议** diff，由用户审批后落库。日常 sha 漂移不触发本文件的修改，只触发 `doc-library/modules/` 下对应文档的 commit 字段刷新。

---

## 体系入口

- 全局 `~/.agent-docs/manual/doc-system.md` — 文档体系操作手册（规则、模板、schema、命名）。所有操作都应在此手册指引下进行。
- 本文件 `_index.md` — 当前项目的索引清单与 `project_config`。
- `doc-library/main-module.md` — 当前项目主仓库（主模块）的整体架构文档。

---

## 主模块

| 文件 | 一句话定位 |
|---|---|
| `doc-library/main-module.md` | <待首次落地第二阶段填写> |

---

## 活跃子模块

> 首次落地尚未完成。第一阶段输出后由用户审批通过，第二阶段生成文档时填表。

| 文件 | repo | branch | 一句话定位 |
|---|---|---|---|
| _（pending first scan）_ | | | |

---

## 归档子模块

| 文件 | 原 repo | 原 branch | 归档原因 |
|---|---|---|---|
| _（暂无）_ | | | |

---

## 备注

- 同一仓库不同分支并存时，**每分支独立一份文档**；本表按子模块仓库分组列出，分支不同的两份文档相邻列出便于对照。
- 子模块之间**完全解耦**，文档之间不互相引用。需要跨子模块查阅时直接打开对应文件即可。
