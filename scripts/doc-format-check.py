#!/usr/bin/env python3
"""
doc-format-check.py - Validate yaml schema compliance of doc files.

Usage: python3 ~/.agent-docs/scripts/doc-format-check.py [project_root] [--docs-dir <dir>]

Checks:
  - Required fields present (schema_version, repo, branch, commit)
  - schema_version value matches current version
  - commit is 10-40 char hex
  - No fields outside the schema allowlist (known removals are listed in
    DEPRECATED_FIELDS; unknown top-level keys are rejected by the same rule)
  - No duplicate (host, owner, name, branch) four-tuples among active docs;
    host/owner/name are derived from `repo` at runtime, not stored
  - Archived docs must have: archived_at, archived_reason, origin_path_in_main
  - repo URL must be parseable (UNPARSEABLE_REPO_URL); unparseable identities are
    excluded from four-tuple comparison so they can never be merged or pruned
  - _index.md and doc-library/main-module.md are also checked for schema_version
    and deprecated fields (they live outside modules/ but still carry a schema)

Content constraints from manual sections 6 and 8, which used to live only in prose
and were therefore widely violated in practice:
  - DOC_TOO_LONG / CHAPTER_TOO_LONG   line budgets (section 6, rule 4)
  - PATCH_NARRATIVE                   describe current state only (section 6, rule 5)
  - LINE_NUMBER_REF                   no line numbers (section 6, rule 6)
  - CROSS_DOC_REF                     no cross-submodule doc references (section 6, rule 7)
  - CHAPTER_ORDER                     chapter order (section 8.7)

Output: one issue per line, or "ALL_PASS" if clean.

Note: 本脚本只用标准库，不依赖 PyYAML；采用启发式 parser 解析 yaml frontmatter，
仅校验关键值约束，复杂嵌套用宽松规则。
"""

import hashlib
import os
import re
import sys


REQUIRED_FIELDS = ["schema_version", "repo", "branch", "commit"]
ALLOWED_FIELDS = [
    "schema_version", "repo", "branch", "commit", "archived", "archived_at",
    "archived_reason", "origin_path_in_main", "merged_from",
]
INDEX_ALLOWED_FIELDS = ["schema_version", "project_config"]
MAIN_ALLOWED_FIELDS = ["schema_version"]
ARCHIVED_REQUIRED_FIELDS = ["archived_at", "archived_reason", "origin_path_in_main"]
# 已移除的字段。存量文档中出现这些键时报 DEPRECATED_FIELD。
#   v6：agent_load 无消费者；origin_host / owner / name 可由 repo 推导；
#        sub_section 可由文件名后缀推导。
#   v7：structure 块在实际使用中占文档 98% 体积，而 role 几乎全为
#        unknown、use 从不填充、cross_module_contracts 恒为空，信号极低；
#        它还反转了 doc-context 两步加载的初衷——只读 frontmatter 反而比读正文贵约 180 倍。
DEPRECATED_FIELDS = [
    "agent_load", "origin_host", "owner", "name", "sub_section",
    "structure",
]
VALID_ARCHIVED_REASONS = [
    "removed-from-gitmodules",
    "imported-from-other-project",
]
CURRENT_SCHEMA_VERSION = "7"

# 手册 §6 / §8 的内容硬约束（此前只以散文存在，无工具执行）
MAX_DOC_LINES = 500          # §6 第 4 条：单份文档上限
MAX_CHAPTER_LINES = 80       # §6 第 4 条：单章超此值应拆附属文档
PATCH_NARRATIVE_PATTERNS = [  # §6 第 5 条：只描述当前状态
    "现在改成", "现在改为", "已改为", "改成了",
    "修复了", "修正了", "以前是", "原来是", "之前是",
]
# §8.7 章节顺序
SUB_CHAPTERS = [
    "定位", "职责边界", "业务逻辑", "架构", "生命周期", "外部入口", "关键流程",
    "接口", "数据契约", "配置与资源", "依赖", "使用约束", "警示", "可观测性",
    "协作关系", "典型修改场景",
]
MAIN_CHAPTERS = [
    "定位", "职责边界", "业务逻辑", "框架总览", "架构", "业务主循环",
    "跨模块数据流", "模块协同模式", "生命周期", "外部入口", "关键流程",
    "接口", "数据契约", "配置与资源", "依赖", "使用约束", "警示", "可观测性",
]



def parse_git_url(url):
    """解析 git URL，返回 (host, owner, name, ok)。与 doc-scaffold.py 保持一致。

    ok=False 表示无法按已知形式解析。此时 name 由 URL 摘要派生，**保证不同 URL
    不共享同一身份**——历史实现统一回落常量 unknown/unknown/unknown，会让两份
    互不相关的文档被判为同一四元组，进而被提议合并（doc-doctor）或列入物理
    删除候选（doc-prune）。
    """
    raw = (url or "").strip()
    if not raw:
        return "unparsed", "unparsed", "empty", False

    # scp-style: user@host[:port]:owner/name[.git]
    m = re.match(r"^[\w.+-]+@([^:/]+):(?:(\d+):)?(.+?)/([^/]+?)(?:\.git)?/?$", raw)
    if m:
        host = m.group(1) if not m.group(2) else f"{m.group(1)}:{m.group(2)}"
        return host, m.group(3), m.group(4), True

    # scheme://[user@]host[:port]/path
    m = re.match(r"^(?:https?|ssh|git|ftps?)://(?:[^@/]+@)?([^/:]+)(?::(\d+))?/(.*)$", raw)
    if m:
        host = m.group(1) if not m.group(2) else f"{m.group(1)}:{m.group(2)}"
        path = re.sub(r"\.git$", "", m.group(3).rstrip("/"))
        parts = [p for p in path.split("/") if p]
        if len(parts) >= 2:
            return host, "/".join(parts[:-1]), parts[-1], True
        if len(parts) == 1:
            return host, "-", parts[0], True
        return host, "-", "root", True

    # file:// 或本地路径
    m = re.match(r"^(?:file://)?(/.*|\.{1,2}/.*)$", raw)
    if m:
        path = re.sub(r"\.git$", "", m.group(1).rstrip("/"))
        parts = [p for p in os.path.normpath(path).split("/") if p]
        if parts:
            owner = "/".join(parts[:-1]) if len(parts) >= 2 else "-"
            return "local", owner, parts[-1], True

    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]
    return "unparsed", "unparsed", digest, False


def extract_body(filepath):
    """返回 frontmatter 之后的正文。无 frontmatter 时返回全文。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return ""
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            return content[end + 3:]
    return content


def split_chapters(body):
    """把正文切成 [(章节名, 行数), ...]，按 `## ` 标题划分。"""
    chapters = []
    name, count = None, 0
    for line in body.split("\n"):
        m = re.match(r"^##\s+(.+?)\s*$", line)
        if m:
            if name is not None:
                chapters.append((name, count))
            name, count = m.group(1), 0
        elif name is not None:
            count += 1
    if name is not None:
        chapters.append((name, count))
    return chapters


def validate_content(fname, filepath, is_main, issues):
    """校验手册 §6 / §8 中此前只以散文存在的硬约束。

    行数只统计 frontmatter 之后的正文。历史上曾把大体积 frontmatter 计入正文并
    误报超限，因此这里必须通过 extract_body() 后再计算。
    """
    body = extract_body(filepath)
    lines = body.split("\n")

    # §6 第 4 条：单份文档 ≤ 500 行；单章 > 80 行应拆附属文档
    if len(lines) > MAX_DOC_LINES:
        issues.append(f"{fname}: DOC_TOO_LONG({len(lines)} > {MAX_DOC_LINES})")
    for chapter, count in split_chapters(body):
        if count > MAX_CHAPTER_LINES:
            issues.append(
                f"{fname}: CHAPTER_TOO_LONG({chapter}, {count} > {MAX_CHAPTER_LINES})")

    # §6 第 5 条：只描述当前状态，禁止补丁式叙述
    for pat in PATCH_NARRATIVE_PATTERNS:
        if pat in body:
            issues.append(f"{fname}: PATCH_NARRATIVE({pat})")

    # §6 第 6 条：不写行号
    for m in re.finditer(r"第\s*\d+\s*行|\.(?:h|hpp|hxx|cpp|cc|c|py|js|ts|go|java|rs|lua|m|mm):\d+",
                         body):
        issues.append(f"{fname}: LINE_NUMBER_REF({m.group(0).strip()})")
        break

    # §6 第 7 条：跨子模块不引用文档。引用自身的附属文档是允许的。
    self_prefix = fname[:-3] if fname.endswith(".md") else fname
    for m in re.finditer(r"[A-Za-z0-9._-]+__[^\s`|)]*?__[^\s`|)]*?\.md", body):
        ref = m.group(0)
        if ref == fname or ref.startswith(self_prefix + "__"):
            continue
        issues.append(f"{fname}: CROSS_DOC_REF({ref})")

    # §8.7 章节顺序（存在的章节必须是规范顺序的子序列；缺章不在此校验）
    canonical = MAIN_CHAPTERS if is_main else SUB_CHAPTERS
    present = [c for c, _ in split_chapters(body) if c in canonical]
    idx = [canonical.index(c) for c in present]
    if idx != sorted(idx):
        out_of_order = [present[i] for i in range(1, len(idx)) if idx[i] < idx[i - 1]]
        issues.append(f"{fname}: CHAPTER_ORDER({','.join(out_of_order)})")


def extract_meta_raw(filepath):
    """读取 yaml frontmatter 原始文本块。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    return content[3:end]


def extract_meta(filepath):
    """启发式提取 yaml 顶层标量字段。复杂嵌套结构不在此解析。"""
    raw = extract_meta_raw(filepath)
    if raw is None:
        return None
    meta = {}
    current_list_key = None
    for line in raw.split("\n"):
        # 顶层字段必须无前导空格
        if line.startswith(" ") or line.startswith("\t"):
            current_list_key = None
            continue
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^([\w_]+):\s*(.*)$", stripped)
        if m:
            key = m.group(1)
            val = m.group(2).strip().strip('"').strip("'")
            if val == "":
                meta[key] = []
                current_list_key = key
            else:
                meta[key] = val
                current_list_key = None
    return meta


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("project_root", nargs="?", default=None)
    p.add_argument("--docs-dir", default=None)
    args = p.parse_args()

    project_root = os.path.abspath(args.project_root or os.getcwd())
    docs_dir = args.docs_dir if args.docs_dir else os.path.join(project_root, ".agent-docs", "doc-library", "modules")

    if not os.path.isdir(docs_dir):
        print(f"ERROR: {docs_dir} not found")
        sys.exit(1)

    all_issues = []
    four_tuples = {}

    # 索引与主模块文档：不在 modules/ 内，字段集也不同（无 repo/branch/commit），
    # 但同样受 schema_version 与废弃字段约束。漏掉它们会让这两份文件永久停在旧版本。
    if not args.docs_dir:
        for rel in ("_index.md", os.path.join("doc-library", "main-module.md")):
            fpath = os.path.join(project_root, ".agent-docs", rel)
            if not os.path.isfile(fpath):
                continue
            meta = extract_meta(fpath)
            if meta is None:
                all_issues.append(f"{rel}: NO_YAML_FRONTMATTER")
                continue
            if "schema_version" not in meta or not meta["schema_version"]:
                all_issues.append(f"{rel}: MISSING_FIELD(schema_version)")
            else:
                sv0 = str(meta["schema_version"])
                if sv0 != CURRENT_SCHEMA_VERSION:
                    all_issues.append(
                        f"{rel}: OUTDATED_SCHEMA_VERSION({sv0}, expected {CURRENT_SCHEMA_VERSION})")
            allowed = (INDEX_ALLOWED_FIELDS if rel == "_index.md"
                       else MAIN_ALLOWED_FIELDS)
            for field in meta:
                if field not in allowed:
                    all_issues.append(f"{rel}: DEPRECATED_FIELD({field})")
            if rel.endswith("main-module.md"):
                validate_content(rel, fpath, True, all_issues)

    for fname in sorted(os.listdir(docs_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(docs_dir, fname)
        meta = extract_meta(fpath)

        if meta is None:
            all_issues.append(f"{fname}: NO_YAML_FRONTMATTER")
            continue

        is_archived = meta.get("archived") == "true"

        # Required fields (common to all docs)
        for field in REQUIRED_FIELDS:
            if field not in meta or meta[field] is None or meta[field] == "":
                all_issues.append(f"{fname}: MISSING_FIELD({field})")

        # Schema allowlist. Known removals and arbitrary unknown top-level keys
        # share the same migration signal so doc-update/doc-doctor will remove them.
        for field in meta:
            if field not in ALLOWED_FIELDS:
                all_issues.append(f"{fname}: DEPRECATED_FIELD({field})")

        # schema_version value check
        sv = meta.get("schema_version", "")
        if sv and str(sv) != CURRENT_SCHEMA_VERSION:
            all_issues.append(f"{fname}: OUTDATED_SCHEMA_VERSION({sv}, expected {CURRENT_SCHEMA_VERSION})")

        # Commit format
        commit = meta.get("commit", "")
        if commit and not re.match(r"^[0-9a-f]{10,40}$", str(commit)):
            all_issues.append(f"{fname}: INVALID_COMMIT({commit[:20]}...)")

        # Archived-specific checks
        if is_archived:
            for field in ARCHIVED_REQUIRED_FIELDS:
                if field not in meta or meta[field] is None or meta[field] == "":
                    all_issues.append(f"{fname}: ARCHIVED_MISSING_FIELD({field})")

            archived_at = meta.get("archived_at", "")
            if archived_at and not re.match(r"^\d{4}-\d{2}-\d{2}$", archived_at):
                all_issues.append(f"{fname}: INVALID_ARCHIVED_AT({archived_at})")

            archived_reason = meta.get("archived_reason", "")
            if archived_reason:
                valid = False
                for prefix in VALID_ARCHIVED_REASONS:
                    if archived_reason.startswith(prefix):
                        valid = True
                        break
                if not valid and not archived_reason.startswith("renamed-to-") and not archived_reason.startswith("merged-into-"):
                    all_issues.append(f"{fname}: INVALID_ARCHIVED_REASON({archived_reason})")

        # 内容硬约束（手册 §6 / §8）。归档文档描述的是已离场模块，不再要求。
        if not is_archived:
            validate_content(fname, fpath, False, all_issues)


        # repo URL 可解析性：不可解析的身份不得参与合并 / 删除判定
        host, owner, name, url_ok = parse_git_url(meta.get("repo", ""))
        if not url_ok:
            all_issues.append(f"{fname}: UNPARSEABLE_REPO_URL({meta.get('repo', '')})")

        # Four-tuple uniqueness (only among active docs).
        # host/owner/name 由 repo 运行时推导，不再存储于 yaml。
        if not is_archived and url_ok:
            key = (host, owner, name, meta.get("branch", ""))
            if key in four_tuples:
                all_issues.append(f"{fname}: DUPLICATE_FOUR_TUPLE (conflicts with {four_tuples[key]})")
            else:
                four_tuples[key] = fname

    if all_issues:
        for issue in all_issues:
            print(issue)
        sys.exit(1)
    else:
        print("ALL_PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
