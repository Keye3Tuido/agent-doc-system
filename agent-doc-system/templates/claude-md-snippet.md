## agent-doc-system

This project uses agent-doc-system for structured documentation.

Before answering any question about code structure, module boundaries, submodule functionality, cross-module calls, architecture, bug investigation, or new feature design: invoke `/doc-context` to load the project documentation library.

If `.agent-docs/` does not exist, print `> [doc-context] 当前项目无文档库，建议运行 /doc-init 初始化` and answer normally.

**Available slash commands:**

| Command | When to invoke |
|---|---|
| `/doc-context` | Any question requiring project architecture/module understanding |
| `/doc-init` | Initialize documentation for this project |
| `/doc-update` | Update or refresh documentation |
| `/doc-rebuild` | Rebuild all documentation from scratch |
| `/doc-merge` | Merge or consolidate documentation |
| `/doc-prune` | Remove or archive stale documentation |
| `/doc-doctor` | Check or validate documentation health |
| `/doc-tree` | List or view documentation structure |
| `/doc-sync-system` | Upgrade the doc system itself |
