#!/usr/bin/env python3
"""
install-global.py - Install agent-doc-system into ~/.agent-docs/.

Usage: python3 install-global.py [--source <dir>] [--upgrade] [--dry-run]

--source  Path to the agent-doc-system repo root (default: parent of this script).
--upgrade Overwrite existing files (default: skip unchanged).
--dry-run Print plan without writing.

Installs: manual/, scripts/, skills/, templates/, installers/ → ~/.agent-docs/

Exit codes: 0 success, 1 error
"""

import argparse
import os
import shutil
import sys

AGENT_DOCS_HOME = os.path.expanduser("~/.agent-docs")
TARGETS = ("manual", "scripts", "skills", "templates", "installers")
ROOT_FILES = ("urls.conf",)  # 根目录下需要安装的单文件


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", default=None)
    p.add_argument("--upgrade", action="store_true")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    src_root = os.path.abspath(args.source or os.path.dirname(os.path.dirname(__file__)))

    added, replaced, skipped = [], [], []

    # Install root-level files (e.g. urls.conf)
    for fname in ROOT_FILES:
        sp = os.path.join(src_root, fname)
        if not os.path.isfile(sp):
            continue
        dp = os.path.join(AGENT_DOCS_HOME, fname)
        if not os.path.exists(dp):
            added.append((sp, dp))
        else:
            with open(sp, "rb") as a, open(dp, "rb") as b:
                same = a.read() == b.read()
            if same:
                skipped.append(dp)
            elif args.upgrade:
                replaced.append((sp, dp))
            else:
                skipped.append(dp)

    # Install target directories
    for target in TARGETS:
        src_t = os.path.join(src_root, target)
        if not os.path.isdir(src_t):
            continue
        dst_t = os.path.join(AGENT_DOCS_HOME, target)
        for dirpath, _, files in os.walk(src_t):
            for f in files:
                sp = os.path.join(dirpath, f)
                rel = os.path.relpath(sp, src_t)
                dp = os.path.join(dst_t, rel)
                if not os.path.exists(dp):
                    added.append((sp, dp))
                else:
                    with open(sp, "rb") as a, open(dp, "rb") as b:
                        same = a.read() == b.read()
                    if same:
                        skipped.append(dp)
                    elif args.upgrade:
                        replaced.append((sp, dp))
                    else:
                        skipped.append(dp)

    for label, items in [("ADD", added), ("REPLACE", replaced), ("SKIP", skipped)]:
        for item in items:
            path = item if isinstance(item, str) else item[1]
            print(f"  {label}  {os.path.relpath(path, AGENT_DOCS_HOME)}")

    if args.dry_run:
        print("[dry-run] no files written")
        return 0

    for sp, dp in added + replaced:
        os.makedirs(os.path.dirname(dp), exist_ok=True)
        shutil.copy2(sp, dp)

    print(f"\nInstalled to {AGENT_DOCS_HOME}: {len(added)} added, {len(replaced)} replaced, {len(skipped)} skipped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
