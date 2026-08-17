#!/usr/bin/env python3
"""
doc-encoding-check.py - Check encoding compliance of all .md files.

Usage: python3 ~/.agent-docs/scripts/doc-encoding-check.py [project_root]

Checks: UTF-8, no BOM, LF line endings (no CRLF, no lone CR).

"Compliant" here is exactly what convert-to-utf8.sh enforces, and the manual
(section 6, rule 1) states the same definition. Control characters inside
otherwise-valid UTF-8 (form feed, ESC, ...) are NOT treated as issues.
Output: one issue per line, or "ALL_PASS" if clean.
"""

import os
import sys


def check_file(filepath, relpath):
    issues = []
    with open(filepath, "rb") as f:
        data = f.read()

    if data.startswith(b"\xef\xbb\xbf"):
        issues.append(f"{relpath}: BOM_DETECTED")

    try:
        data.decode("utf-8")
    except UnicodeDecodeError as e:
        issues.append(f"{relpath}: NOT_UTF8 (byte 0x{data[e.start]:02x} at pos {e.start})")
        return issues

    if b"\r\n" in data:
        crlf_count = data.count(b"\r\n")
        issues.append(f"{relpath}: CRLF_DETECTED (count={crlf_count})")

    # A lone CR (not part of a CRLF pair) also violates the LF-only requirement.
    lone_cr = data.replace(b"\r\n", b"").count(b"\r")
    if lone_cr:
        issues.append(f"{relpath}: LONE_CR_DETECTED (count={lone_cr})")

    return issues


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("project_root", nargs="?", default=None)
    p.add_argument("--docs-dir", default=None)
    args = p.parse_args()

    project_root = os.path.abspath(args.project_root or os.getcwd())
    steering_dir = args.docs_dir if args.docs_dir else os.path.join(project_root, ".agent-docs")

    if not os.path.isdir(steering_dir):
        print(f"ERROR: {steering_dir} not found")
        sys.exit(1)

    all_issues = []
    for root, dirs, files in os.walk(steering_dir):
        for fname in sorted(files):
            if not fname.endswith(".md"):
                continue
            fpath = os.path.join(root, fname)
            relpath = os.path.relpath(fpath, project_root)
            all_issues.extend(check_file(fpath, relpath))

    if all_issues:
        for issue in all_issues:
            print(issue)
        sys.exit(1)
    else:
        print("ALL_PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
