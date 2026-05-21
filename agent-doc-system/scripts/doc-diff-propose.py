#!/usr/bin/env python3
"""
doc-diff-propose.py - Write a diff proposal to a review file for user approval.

Usage:
  python3 ~/.agent-docs/scripts/doc-diff-propose.py <project_root> --from <diff_file> [--title "description"]
  python3 ~/.agent-docs/scripts/doc-diff-propose.py <project_root> --content "<inline diff>" [--title "description"]

The script creates/overwrites:
  <project_root>/.agent-docs/.tmp/pending-review.md

Agent workflow:
  1. Agent writes diff content to a temp file (e.g. .agent-docs/.tmp/diff-staging.md) using fs_write.
  2. Agent calls this script with --from <that_file>.
  3. Script writes formatted review to .agent-docs/.tmp/pending-review.md.
  4. Agent tells user: "Review .agent-docs/.tmp/pending-review.md, reply yes to apply".
  5. On approval, agent applies changes and the review file can be discarded.

Note: This tool intentionally does NOT read from stdin. Pass content via --from or --content.

Exit codes:
  0  success
  2  argument / IO error
"""

import argparse
import os
import sys
from datetime import datetime


def main():
    p = argparse.ArgumentParser(
        description="Write a diff proposal to .agent-docs/.tmp/pending-review.md.",
        epilog="This tool does not read from stdin. Use --from <file> or --content <string>.",
    )
    p.add_argument("project_root", help="Project root directory")
    p.add_argument("--from", dest="src", default=None,
                   help="Read diff content from this file")
    p.add_argument("--content", default=None,
                   help="Inline diff content (use sparingly; prefer --from for large diffs)")
    p.add_argument("--title", default="Documentation Update Proposal",
                   help="Title shown at the top of the review file")
    args = p.parse_args()

    if not args.src and args.content is None:
        print("ERROR: must provide either --from <file> or --content <string>", file=sys.stderr)
        return 2
    if args.src and args.content is not None:
        print("ERROR: --from and --content are mutually exclusive", file=sys.stderr)
        return 2

    project_root = os.path.abspath(args.project_root)
    if not os.path.isdir(project_root):
        print(f"ERROR: project root does not exist: {project_root}", file=sys.stderr)
        return 2

    if args.src:
        try:
            with open(args.src, "r", encoding="utf-8") as f:
                content = f.read()
        except OSError as e:
            print(f"ERROR reading {args.src}: {e}", file=sys.stderr)
            return 2
        except UnicodeDecodeError as e:
            print(f"ERROR: {args.src} is not UTF-8: {e}", file=sys.stderr)
            return 2
    else:
        content = args.content

    review_dir = os.path.join(project_root, ".agent-docs", ".tmp")
    os.makedirs(review_dir, exist_ok=True)
    review_path = os.path.join(review_dir, "pending-review.md")

    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    try:
        with open(review_path, "w", encoding="utf-8", newline="") as f:
            f.write(f"# {args.title}\n\n")
            f.write(f"> Generated: {timestamp}\n")
            f.write(f"> Reply 'yes' in chat to apply all changes below.\n\n")
            f.write("---\n\n")
            f.write(content)
            if not content.endswith("\n"):
                f.write("\n")
    except OSError as e:
        print(f"ERROR writing {review_path}: {e}", file=sys.stderr)
        return 2

    print(f"WRITTEN: {os.path.relpath(review_path, project_root)}")
    print(f"SIZE: {len(content)} chars")
    return 0


if __name__ == "__main__":
    sys.exit(main())
