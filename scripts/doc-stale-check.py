#!/usr/bin/env python3
"""
doc-stale-check.py - Output stale status for all submodules in one shot.

Usage: python3 ~/.agent-docs/scripts/doc-stale-check.py [project_root] [--out <file>]

Output: table with columns PATH | ORIGIN | DOC_BRANCH | REMOTE_SHA | DOC_SHA | STATUS

Statuses:
  OK              - sha matches remote
  STALE           - sha differs from remote
  BRANCH_GONE(OK) - remote branch missing but sha matches local HEAD
  BRANCH_GONE(STALE) - remote branch missing and sha differs from local HEAD
  NO_DOC          - submodule has no documentation file
  ORPHAN_DOC      - doc exists for a path not in .gitmodules (non-archived)
  ARCHIVED_BUT_ACTIVE - doc is archived but submodule still in .gitmodules
  ERROR           - cannot determine sha
"""

import os
import re
import subprocess
import sys


def run_git(args, cwd):
    try:
        r = subprocess.run(
            ["git"] + args, cwd=cwd, capture_output=True, text=True, timeout=10
        )
        return r.stdout.strip() if r.returncode == 0 else None
    except Exception:
        return None


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


def load_all_docs(project_root, docs_dir=None):
    docs_dir = docs_dir if docs_dir else os.path.join(project_root, ".agent-docs", "doc-library", "modules")
    if not os.path.isdir(docs_dir):
        return []
    docs = []
    for fname in os.listdir(docs_dir):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(docs_dir, fname)
        meta = extract_meta(fpath)
        if meta:
            meta["_filename"] = fname
            docs.append(meta)
    return docs


def normalize_url(url):
    return url.rstrip("/").removesuffix(".git") if url else ""


def find_doc_for_module(mod_path, mod_url, docs):
    """Find the matching doc for a given submodule (active or archived)."""
    norm_url = normalize_url(mod_url)
    for d in docs:
        if normalize_url(d.get("repo", "")) == norm_url:
            return d
    for d in docs:
        if d.get("origin_path_in_main") == mod_path:
            return d
    return None


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

    modules = parse_gitmodules(project_root)
    docs = load_all_docs(project_root, args.docs_dir)
    matched_docs = set()

    fmt = "{:<40} {:<55} {:<20} {:<12} {:<12} {}"
    print(fmt.format("PATH", "ORIGIN", "DOC_BRANCH", "REMOTE_SHA", "DOC_SHA", "STATUS"))
    print("-" * 145)

    for mod in modules:
        mod_path = mod.get("path", "")
        mod_url = mod.get("url", "")
        abs_path = os.path.join(project_root, mod_path)

        doc = find_doc_for_module(mod_path, mod_url, docs)

        if not doc:
            print(fmt.format(mod_path, mod_url, "---", "---", "---", "NO_DOC"))
            continue

        matched_docs.add(doc["_filename"])

        # Check if doc is archived but submodule is still active
        if doc.get("archived") == "true":
            print(fmt.format(
                mod_path, mod_url,
                doc.get("branch", ""), "---",
                doc.get("commit", "")[:10],
                "ARCHIVED_BUT_ACTIVE"
            ))
            continue

        doc_branch = doc.get("branch", "")
        doc_commit = doc.get("commit", "")[:10]

        remote_sha = None
        branch_gone = False
        if doc_branch:
            remote_sha = run_git(["-C", abs_path, "rev-parse", "origin/" + doc_branch], project_root)
        if not remote_sha:
            remote_sha = run_git(["-C", abs_path, "rev-parse", "HEAD"], project_root)
            branch_gone = True

        rs = (remote_sha or "???")[:10]

        if not remote_sha:
            status = "ERROR"
        elif branch_gone:
            status = "BRANCH_GONE(OK)" if remote_sha[:10] == doc_commit else "BRANCH_GONE(STALE)"
        elif remote_sha[:40] == doc.get("commit", "")[:40]:
            status = "OK"
        else:
            status = "STALE"

        print(fmt.format(mod_path, mod_url, doc_branch, rs, doc_commit, status))

    # Orphan docs: non-archived docs that didn't match any submodule
    for doc in docs:
        if doc["_filename"] in matched_docs:
            continue
        if doc.get("archived") == "true":
            continue
        repo = doc.get("repo", "")
        path = doc.get("origin_path_in_main", "")
        print(fmt.format(path, repo, doc.get("branch", ""), "---", doc.get("commit", "")[:10], "ORPHAN_DOC"))


if __name__ == "__main__":
    main()
