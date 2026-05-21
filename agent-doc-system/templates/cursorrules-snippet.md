## agent-doc-system

This project uses agent-doc-system for structured documentation. Before answering any question about code structure, module boundaries, submodule functionality, cross-module calls, architecture, bug investigation, or new feature design, load the project documentation library first.

**To load documentation context:**
Read `<project_root>/.agent-docs/_index.md`, then `<project_root>/.agent-docs/doc-library/main-module.md` (if it exists), then selectively read relevant submodule docs from `<project_root>/.agent-docs/doc-library/modules/`.

If `.agent-docs/` does not exist, print `> [doc-context] 当前项目无文档库，建议运行 /doc-init 初始化` and answer normally.

**Available skills** (read the corresponding SKILL.md from `~/.agent-docs/skills/<name>/SKILL.md`):

| Skill | When to invoke |
|---|---|
| `doc-context` | Any question requiring project architecture/module understanding |
| `doc-init` | User asks to initialize documentation for this project |
| `doc-update` | User asks to update or refresh documentation |
| `doc-rebuild` | User asks to rebuild all documentation from scratch |
| `doc-merge` | User asks to merge or consolidate documentation |
| `doc-prune` | User asks to remove or archive stale documentation |
| `doc-doctor` | User asks to check or validate documentation health |
| `doc-tree` | User asks to list or view documentation structure |
| `doc-sync-system` | User asks to upgrade the doc system itself |
