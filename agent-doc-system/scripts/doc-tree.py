#!/usr/bin/env python3
"""
doc-tree.py - Output documentation library structure tree.

Usage: python3 ~/.agent-docs/scripts/doc-tree.py [project_root] [--out <file>]

Sections: [MAIN MODULE], [ACTIVE], [ARCHIVED], [MISSING]

MISSING only lists submodules that have neither an active doc nor an archived doc.
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


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("project_root", nargs="?", default=None)
    p.add_argument("--docs-dir", default=None)
    p.add_argument("--out", default=None)
    args = p.parse_args()

    project_root = os.path.abspath(args.project_root or os.getcwd())
    out_file = args.out

    if out_file:
        sys.stdout = open(out_file, "w", encoding="utf-8")

    base = args.docs_dir if args.docs_dir else os.path.join(project_root, ".agent-docs")
    docs_dir = os.path.join(base, "doc-library", "modules")
    main_doc = os.path.join(base, "doc-library", "main-module.md")

    print("=" * 60)
    print("[MAIN MODULE]")
    print("=" * 60)
    if os.path.isfile(main_doc):
        print("  main-module.md")
    else:
        print("  (missing)")

    active = []
    archived = []
    if os.path.isdir(docs_dir):
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
                "commit": meta.get("commit", "")[:10],
            }
            if entry["archived"]:
                archived.append(entry)
            else:
                active.append(entry)

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
