#!/usr/bin/env python3
"""
doc-format-check.py - Validate yaml schema compliance of doc files.

Usage: python3 ~/.agent-docs/scripts/doc-format-check.py [project_root] [--docs-dir <dir>]

Checks:
  - Required fields present (schema_version, agent_load, repo, origin_host, owner, name, branch, commit)
  - schema_version value matches current version
  - commit is 10-40 char hex
  - No duplicate (origin_host, owner, name, branch) four-tuples among active docs
  - Archived docs must have: archived_at, archived_reason, origin_path_in_main

Output: one issue per line, or "ALL_PASS" if clean.
"""

import os
import re
import sys


REQUIRED_FIELDS = ["schema_version", "agent_load", "repo", "origin_host", "owner", "name", "branch", "commit"]
ARCHIVED_REQUIRED_FIELDS = ["archived_at", "archived_reason", "origin_path_in_main"]
VALID_ARCHIVED_REASONS = [
    "removed-from-gitmodules",
    "imported-from-other-project",
]
CURRENT_SCHEMA_VERSION = "3"


def extract_meta(filepath):
    """Extract yaml front-matter fields as dict using regex (no yaml dep)."""
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
    yaml_block = content[3:end]
    meta = {}
    current_list_key = None
    for line in yaml_block.split("\n"):
        stripped = line.strip()
        if stripped.startswith("- "):
            if current_list_key:
                val = stripped[2:].strip().strip('"').strip("'")
                meta[current_list_key].append(val)
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

            # Validate archived_at is ISO date format
            archived_at = meta.get("archived_at", "")
            if archived_at and not re.match(r"^\d{4}-\d{2}-\d{2}$", archived_at):
                all_issues.append(f"{fname}: INVALID_ARCHIVED_AT({archived_at})")

            # Validate archived_reason starts with known prefix or matches pattern
            archived_reason = meta.get("archived_reason", "")
            if archived_reason:
                valid = False
                for prefix in VALID_ARCHIVED_REASONS:
                    if archived_reason.startswith(prefix):
                        valid = True
                        break
                if not valid and not archived_reason.startswith("renamed-to-") and not archived_reason.startswith("merged-into-"):
                    all_issues.append(f"{fname}: INVALID_ARCHIVED_REASON({archived_reason})")

        # structure field check (schema v3+)
        if str(sv) == CURRENT_SCHEMA_VERSION and not is_archived:
            if "structure" not in meta:
                all_issues.append(f"{fname}: MISSING_STRUCTURE")

        # Four-tuple uniqueness (only among active docs)
        if not is_archived:
            key = (
                meta.get("origin_host", ""),
                meta.get("owner", ""),
                meta.get("name", ""),
                meta.get("branch", ""),
            )
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
