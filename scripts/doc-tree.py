#!/usr/bin/env python3
"""
doc-tree.py - Output documentation library structure tree.

Usage: python3 ~/.agent-docs/scripts/doc-tree.py [project_root] [--out <file>]
       python3 ~/.agent-docs/scripts/doc-tree.py [project_root] --emit-index-tables

Sections: [MAIN MODULE], [ACTIVE], [ARCHIVED], [MISSING]

MISSING only lists submodules that have neither an active doc nor an archived doc.

--emit-index-tables regenerates the two submodule tables of _index.md (active /
archived). Those tables are a derived view: the single source of truth is each
document's own yaml frontmatter plus its positioning chapter. Do not hand-maintain.
"""

import os
import re
import sys


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


def parse_gitmodules(project_root):
    gm_path = os.path.join(project_root, ".gitmodules")
    if not os.path.isfile(gm_path):
        return []
    modules = []
    current = {}
    with open(gm_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("[submodule"):
                if current.get("path"):
                    modules.append(current)
                current = {}
            elif "=" in line:
                key, val = line.split("=", 1)
                current[key.strip()] = val.strip()
    if current.get("path"):
        modules.append(current)
    return modules


def normalize_url(url):
    return url.rstrip("/").removesuffix(".git") if url else ""


# Heading of the positioning chapter, and placeholder prefixes to skip.
POSITIONING_HEADING = "\u5b9a\u4f4d"
PLACEHOLDER_PREFIXES = ("_", "\uff08", "<")


def extract_positioning(filepath):
    """Extract the one-line positioning from the document's positioning chapter.

    Returns the first non-empty, non-placeholder line after the heading, with
    pipe characters escaped so it is safe inside a markdown table cell.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return ""
    m = re.search(r"^##\s+" + POSITIONING_HEADING + r"\s*$", content, re.M)
    if not m:
        return ""
    for line in content[m.end():].split("\n"):
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            break
        if s.startswith(PLACEHOLDER_PREFIXES):
            break
        return s.replace("|", "\\|")
    return ""


def scan_docs(docs_dir):
    """Scan modules/ and return (active, archived) entry lists."""
    active, archived = [], []
    if not os.path.isdir(docs_dir):
        return active, archived
    for fname in sorted(os.listdir(docs_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(docs_dir, fname)
        meta = extract_meta(fpath)
        if not meta:
            continue
        entry = {
            "filename": fname,
            "repo": meta.get("repo", ""),
            "branch": meta.get("branch", ""),
            "origin_path": meta.get("origin_path_in_main", ""),
            "archived": meta.get("archived", "") == "true",
            "archived_reason": meta.get("archived_reason", ""),
            "commit": meta.get("commit", "")[:10],
            "positioning": extract_positioning(fpath),
        }
        (archived if entry["archived"] else active).append(entry)
    return active, archived


def emit_index_tables(docs_dir):
    """Regenerate the active / archived submodule tables of _index.md.

    The output is byte-for-byte isomorphic to the corresponding sections of
    templates/_index.md (same note line, same separator, same empty-state
    placeholder), so that doc-doctor can replace whole sections with this
    output without dropping any hand-authored content.
    """
    active, archived = scan_docs(docs_dir)
    # _(none)_
    empty_cell = "_\uff08\u6682\u65e0\uff09_"
    # > Derived view, regenerate via doc-tree.py --emit-index-tables, do not hand-maintain.
    note = ("> \u6d3e\u751f\u89c6\u56fe\uff0c\u7531 `doc-tree.py --emit-index-tables` "
            "\u518d\u751f\uff0c\u52ff\u624b\u5de5\u7ef4\u62a4\u3002")

    def table(heading, header, rows):
        print(heading)
        print()
        print(note)
        print()
        print(header)
        print("|---|---|---|---|")
        if rows:
            for r in rows:
                print(r)
        else:
            print(f"| {empty_cell} | | | |")

    table(
        "## \u6d3b\u8dc3\u5b50\u6a21\u5757",  # Active submodules
        "| \u6587\u4ef6 | repo | branch | \u4e00\u53e5\u8bdd\u5b9a\u4f4d |",
        [f"| `{e['filename']}` | {e['repo']} | {e['branch']} | {e['positioning']} |"
         for e in active],
    )
    print()
    print("---")
    print()
    table(
        "## \u5f52\u6863\u5b50\u6a21\u5757",  # Archived submodules
        "| \u6587\u4ef6 | \u539f repo | \u539f branch | \u5f52\u6863\u539f\u56e0 |",
        [f"| `{e['filename']}` | {e['repo']} | {e['branch']} | {e['archived_reason']} |"
         for e in archived],
    )


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("project_root", nargs="?", default=None)
    p.add_argument("--docs-dir", default=None)
    p.add_argument("--out", default=None)
    p.add_argument(
        "--emit-index-tables",
        action="store_true",
        help="regenerate the two derived submodule tables of _index.md",
    )
    args = p.parse_args()

    project_root = os.path.abspath(args.project_root or os.getcwd())
    out_file = args.out

    if out_file:
        sys.stdout = open(out_file, "w", encoding="utf-8")

    base = args.docs_dir if args.docs_dir else os.path.join(project_root, ".agent-docs")
    docs_dir = os.path.join(base, "doc-library", "modules")
    main_doc = os.path.join(base, "doc-library", "main-module.md")

    if args.emit_index_tables:
        emit_index_tables(docs_dir)
        return

    print("=" * 60)
    print("[MAIN MODULE]")
    print("=" * 60)
    if os.path.isfile(main_doc):
        print("  main-module.md")
    else:
        print("  (missing)")

    active, archived = scan_docs(docs_dir)

    print()
    print("=" * 60)
    print(f"[ACTIVE] ({len(active)} docs)")
    print("=" * 60)
    for e in active:
        print(f"  {e['filename']}")
        print(f"    repo: {e['repo']}  branch: {e['branch']}  sha: {e['commit']}")

    print()
    print("=" * 60)
    print(f"[ARCHIVED] ({len(archived)} docs)")
    print("=" * 60)
    for e in archived:
        print(f"  {e['filename']}")
        print(f"    repo: {e['repo']}  branch: {e['branch']}")

    # MISSING: submodules that have neither active nor archived docs
    modules = parse_gitmodules(project_root)
    all_docs = active + archived
    all_urls = {normalize_url(e["repo"]) for e in all_docs}
    all_paths = {e["origin_path"] for e in all_docs}

    missing = []
    for mod in modules:
        mod_url = normalize_url(mod.get("url", ""))
        mod_path = mod.get("path", "")
        if mod_url not in all_urls and mod_path not in all_paths:
            missing.append(mod)

    print()
    print("=" * 60)
    print(f"[MISSING] ({len(missing)} submodules without docs)")
    print("=" * 60)
    for m in missing:
        print(f"  {m.get('path', '')}  ({m.get('url', '')})")


if __name__ == "__main__":
    main()
