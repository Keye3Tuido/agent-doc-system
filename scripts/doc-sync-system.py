#!/usr/bin/env python3
"""
doc-sync-system.py - Download and install the latest agent-doc-system package.

Usage: python3 ~/.agent-docs/scripts/doc-sync-system.py [--url <url>] [--no-backup] [--dry-run]

Default URL is read from urls.conf (fallback: https://k3t.site/ds/agent-doc-system.zip)

Behavior:
1. Downloads zip via HTTPS into memory.
2. Detects the directory layout inside the zip (root may directly contain
   skills/scripts/manual, or be wrapped one level deeper).
3. Backs up current ~/.agent-docs/{skills,scripts,manual} to
   ~/.agent-docs/.backup/<timestamp>/ unless --no-backup.
4. Copies new files into the corresponding ~/.agent-docs subdirectories
   (file-level overwrite; existing files NOT in the package are left alone).
5. Prints a summary: ADDED / REPLACED / UNCHANGED counts and file lists.

Safety:
- Aborts before writing if the zip structure does not contain at least one
  of skills/, scripts/, manual/.
- --dry-run prints the plan without writing or backing up.
- Backup directory is timestamped; never overwrites previous backups.

Exit codes:
  0  success (or dry-run completed)
  2  download / network error
  3  zip structure invalid
  4  filesystem error during install
"""

import argparse
import datetime
import io
import os
import shutil
import sys
import tempfile
import urllib.request
import zipfile

AGENT_DOCS_HOME = os.path.expanduser("~/.agent-docs")
TARGETS = ("manual", "scripts", "skills", "templates", "installers", "urls.conf", "README.md")
DOWNLOAD_TIMEOUT_SEC = 60


def load_default_url():
    """Read DOWNLOAD_URL from urls.conf."""
    candidates = [
        os.path.join(AGENT_DOCS_HOME, "urls.conf"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "urls.conf"),
    ]
    for conf_path in candidates:
        if os.path.isfile(conf_path):
            with open(conf_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("#") or "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    if key.strip() == "DOWNLOAD_URL":
                        return value.strip()
    print("[error] urls.conf not found or DOWNLOAD_URL not defined", file=sys.stderr)
    sys.exit(2)


def download(url):
    print(f"[fetch] downloading {url}", file=sys.stderr)
    req = urllib.request.Request(url, headers={"User-Agent": "agent-doc-sync/1.0"})
    with urllib.request.urlopen(req, timeout=DOWNLOAD_TIMEOUT_SEC) as resp:
        data = resp.read()
    print(f"[fetch] received {len(data)} bytes", file=sys.stderr)
    return data


def find_root_prefix(zip_obj):
    """Return the in-zip prefix (with trailing /) that contains the TARGETS dirs.

    Returns "" if TARGETS appear at zip root, or "<wrapper>/" if one level deep.
    Returns None if no recognizable layout is found.
    """
    names = zip_obj.namelist()
    if any(n.startswith(t + "/") for n in names for t in TARGETS):
        return ""
    top_dirs = set()
    for n in names:
        first = n.split("/", 1)[0]
        if first:
            top_dirs.add(first)
    for d in top_dirs:
        prefix = d + "/"
        if any(n.startswith(prefix + t + "/") for n in names for t in TARGETS):
            return prefix
    return None


def collect_changes(src_root):
    """Walk the package source root and classify each file vs the live tree.

    Returns (added, replaced, unchanged) tuples of (target_dir, rel_path, src_abs, dst_abs).
    """
    added, replaced, unchanged = [], [], []
    for target in TARGETS:
        src_t = os.path.join(src_root, target)
        if not os.path.exists(src_t):
            continue

        # Handle single files (urls.conf, README.md)
        if os.path.isfile(src_t):
            dst_t = os.path.join(AGENT_DOCS_HOME, target)
            entry = (target, "", src_t, dst_t)
            if not os.path.exists(dst_t):
                added.append(entry)
            else:
                try:
                    with open(src_t, "rb") as a, open(dst_t, "rb") as b:
                        same = a.read() == b.read()
                except Exception:
                    same = False
                (unchanged if same else replaced).append(entry)
            continue

        # Handle directories (manual, scripts, skills, templates, installers)
        if not os.path.isdir(src_t):
            continue
        dst_t = os.path.join(AGENT_DOCS_HOME, target)
        for dirpath, _, files in os.walk(src_t):
            for f in files:
                sp = os.path.join(dirpath, f)
                rel = os.path.relpath(sp, src_t)
                dp = os.path.join(dst_t, rel)
                entry = (target, rel, sp, dp)
                if not os.path.exists(dp):
                    added.append(entry)
                else:
                    try:
                        with open(sp, "rb") as a, open(dp, "rb") as b:
                            same = a.read() == b.read()
                    except Exception:
                        same = False
                    (unchanged if same else replaced).append(entry)
    return added, replaced, unchanged


def make_backup():
    ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_root = os.path.join(AGENT_DOCS_HOME, ".backup", ts)
    os.makedirs(backup_root, exist_ok=True)
    for t in TARGETS:
        src = os.path.join(AGENT_DOCS_HOME, t)
        if os.path.isdir(src):
            shutil.copytree(src, os.path.join(backup_root, t))
        elif os.path.isfile(src):
            shutil.copy2(src, os.path.join(backup_root, t))
    return backup_root


def apply_changes(changes):
    for _target, _rel, sp, dp in changes:
        os.makedirs(os.path.dirname(dp), exist_ok=True)
        shutil.copy2(sp, dp)


def _format_path(target, rel):
    """Render path entry: single-file target (rel is empty) → just target name; else target/rel."""
    return target if not rel else f"{target}/{rel}"


def print_summary(label, added, replaced, unchanged):
    print(f"\n=== {label} ===")
    print(f"ADDED:     {len(added)}")
    for t, rel, _, _ in sorted(added):
        print(f"  + {_format_path(t, rel)}")
    print(f"REPLACED:  {len(replaced)}")
    for t, rel, _, _ in sorted(replaced):
        print(f"  ~ {_format_path(t, rel)}")
    print(f"UNCHANGED: {len(unchanged)}")


def main():
    default_url = load_default_url()
    p = argparse.ArgumentParser()
    p.add_argument("--url", default=default_url,
                   help=f"Package URL (default: {default_url})")
    p.add_argument("--no-backup", action="store_true",
                   help="Skip backup (not recommended)")
    p.add_argument("--dry-run", action="store_true",
                   help="Show changes without writing")
    args = p.parse_args()

    try:
        data = download(args.url)
    except Exception as e:
        print(f"[error] download failed: {e}", file=sys.stderr)
        return 2

    try:
        zip_obj = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile as e:
        print(f"[error] not a valid zip: {e}", file=sys.stderr)
        return 3

    prefix = find_root_prefix(zip_obj)
    if prefix is None:
        print("[error] zip does not contain skills/, scripts/, or manual/ at root or one level down",
              file=sys.stderr)
        return 3

    with tempfile.TemporaryDirectory() as tmp:
        zip_obj.extractall(tmp)
        zip_obj.close()
        src_root = os.path.join(tmp, prefix.rstrip("/")) if prefix else tmp

        added, replaced, unchanged = collect_changes(src_root)

        if args.dry_run:
            print_summary("DRY RUN (no changes written)", added, replaced, unchanged)
            return 0

        if not added and not replaced:
            print_summary("NO CHANGES NEEDED", added, replaced, unchanged)
            return 0

        backup_root = None
        if not args.no_backup:
            try:
                backup_root = make_backup()
                print(f"[backup] {backup_root}", file=sys.stderr)
            except Exception as e:
                print(f"[error] backup failed: {e}", file=sys.stderr)
                return 4

        try:
            apply_changes(added)
            apply_changes(replaced)
        except Exception as e:
            print(f"[error] install failed: {e}", file=sys.stderr)
            if backup_root:
                print(f"[error] partial install; restore from {backup_root} if needed",
                      file=sys.stderr)
            return 4

        print_summary("INSTALLED", added, replaced, unchanged)
        if backup_root:
            print(f"\nBackup: {backup_root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
