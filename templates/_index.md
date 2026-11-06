---
schema_version: 7
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
> 本文件由 agent 在结构性变动后静默同步；两张子模块表通过 doc-tree.py --emit-index-tables 再生。提交时统一审阅文档差异。日常 SHA 漂移只更新对应模块文档，未影响清单或定位时不改索引。
>
> 下方「活跃子模块」与「归档子模块」两张表是**派生视图**，唯一事实源是各文档自身的 yaml frontmatter 与 `## 定位` 章节。**不要手工维护这两张表**，用脚本再生：`python3 ~/.agent-docs/scripts/doc-tree.py <project_root> --emit-index-tables`。

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

> 派生视图，由 `doc-tree.py --emit-index-tables` 再生，勿手工维护。

| 文件 | repo | branch | 一句话定位 |
|---|---|---|---|
| _（暂无）_ | | | |

---

## 归档子模块

> 派生视图，由 `doc-tree.py --emit-index-tables` 再生，勿手工维护。

| 文件 | 原 repo | 原 branch | 归档原因 |
|---|---|---|---|
| _（暂无）_ | | | |

---

## 备注

- 同一仓库不同分支并存时，**每分支独立一份文档**；本表按子模块仓库分组列出，分支不同的两份文档相邻列出便于对照。
- 子模块之间**完全解耦**，文档之间不互相引用。需要跨子模块查阅时直接打开对应文件即可。
