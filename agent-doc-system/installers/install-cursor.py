#!/usr/bin/env python3
"""
install-cursor.py - Append agent-doc-system snippet to .cursorrules.

Usage: python3 install-cursor.py [project_root] [--remove] [--dry-run]

Appends the contents of templates/cursorrules-snippet.md between
BEGIN/END markers so the block can be upgraded or removed cleanly.

Exit codes: 0 success, 1 error
"""

import argparse
import os
import sys

MARKER_BEGIN = "# BEGIN agent-doc-system"
MARKER_END = "# END agent-doc-system"


def snippet_text(repo_root):
    snippet_path = os.path.join(repo_root, "templates", "cursorrules-snippet.md")
    if not os.path.isfile(snippet_path):
        print(f"ERROR: snippet not found: {snippet_path}", file=sys.stderr)
        sys.exit(1)
    with open(snippet_path, "r", encoding="utf-8") as f:
        return f.read().strip()


def remove_block(content):
    lines = content.splitlines(keepends=True)
    out, inside = [], False
    for line in lines:
        if line.strip() == MARKER_BEGIN:
            inside = True
        elif line.strip() == MARKER_END:
            inside = False
        elif not inside:
            out.append(line)
    return "".join(out)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("project_root", nargs="?", default=None)
    p.add_argument("--remove", action="store_true", help="Remove the snippet block")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    project_root = os.path.abspath(args.project_root or os.getcwd())
    cursorrules = os.path.join(project_root, ".cursorrules")
    repo_root = os.path.abspath(os.path.dirname(os.path.dirname(__file__)))

    existing = ""
    if os.path.isfile(cursorrules):
        with open(cursorrules, "r", encoding="utf-8") as f:
            existing = f.read()

    if args.remove:
        new_content = remove_block(existing)
        action = "REMOVE"
    else:
        cleaned = remove_block(existing)
        snippet = snippet_text(repo_root)
        sep = "\n" if cleaned and not cleaned.endswith("\n") else ""
        new_content = f"{cleaned}{sep}\n{MARKER_BEGIN}\n{snippet}\n{MARKER_END}\n"
        action = "APPEND"

    if args.dry_run:
        print(f"[dry-run] {action} snippet in {cursorrules}")
        return 0

    with open(cursorrules, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)

    print(f"{action}: {cursorrules}")

    # Warn if .gitignore might exclude .agent-docs
    gitignore = os.path.join(project_root, ".gitignore")
    if os.path.isfile(gitignore):
        with open(gitignore, "r", encoding="utf-8") as f:
            gi = f.read()
        if ".agent-docs" in gi:
            print("WARNING: .gitignore may exclude .agent-docs/ — ensure it is committed.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
