#!/usr/bin/env python3
"""
doc-diff.py - Generate unified diff from old file and new content.

Usage:
  python3 doc-diff.py --old <old_file> --new <new_file> [--out <out_file>]

Reads old_file, new_file, produces unified diff to stdout or --out.
Exit 0 if no differences, 1 if differences found, 2 on error.
"""
import argparse
import difflib
import os
import sys


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--old", required=True, help="path to original file")
    p.add_argument("--new", required=True, help="path to new file")
    p.add_argument("--out", default=None, help="output file (default: stdout)")
    p.add_argument("--label", default=None, help="label for diff header")
    args = p.parse_args()

    try:
        with open(args.old, "r", encoding="utf-8") as f:
            old_lines = f.readlines()
    except FileNotFoundError:
        old_lines = []
    except Exception as e:
        print(f"ERROR: cannot read --old: {e}", file=sys.stderr)
        sys.exit(2)

    try:
        with open(args.new, "r", encoding="utf-8") as f:
            new_lines = f.readlines()
    except Exception as e:
        print(f"ERROR: cannot read --new: {e}", file=sys.stderr)
        sys.exit(2)

    old_label = args.label or os.path.basename(args.old)
    new_label = os.path.basename(args.new)

    diff = list(difflib.unified_diff(
        old_lines, new_lines,
        fromfile=f"a/{old_label}",
        tofile=f"b/{new_label}",
    ))

    out = open(args.out, "w", encoding="utf-8") if args.out else sys.stdout
    try:
        if diff:
            out.writelines(diff)
            out.flush()
            sys.exit(1)
        else:
            sys.exit(0)
    finally:
        if args.out:
            out.close()


if __name__ == "__main__":
    main()
