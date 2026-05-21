#!/usr/bin/env python3
"""
doc-write-utf8.py - Convert a file to strict UTF-8 (no BOM, LF line endings).

Usage:
  python3 doc-write-utf8.py <path>                       # fix in place
  python3 doc-write-utf8.py <output> --from <input>      # convert + copy
  python3 doc-write-utf8.py <path> --check               # exit 0 if already UTF-8/LF/no-BOM, exit 1 otherwise

Behavior:
  - Auto-detects source encoding: utf-8 -> gbk -> gb18030 -> gb2312 -> cp936 -> latin-1
  - Strips UTF-8 BOM (EF BB BF)
  - Normalizes line endings: CRLF / CR -> LF
  - Writes target as strict UTF-8 (no BOM)
  - Creates parent directory if missing

Exit codes:
  0  success (or --check pass)
  1  --check failed (file is not strict UTF-8/LF/no-BOM)
  2  IO / decode error

Note: This tool intentionally does NOT read from stdin. Pass a file path.
"""

import argparse
import os
import sys


ENCODING_FALLBACKS = ("utf-8", "gbk", "gb18030", "gb2312", "cp936", "latin-1")


def detect_and_decode(data):
    """Try common encodings; return (text, detected_encoding).

    UTF-8 is tried first. latin-1 never fails so it serves as the catch-all.
    """
    # Strip UTF-8 BOM if present (it's always UTF-8)
    had_bom = data.startswith(b"\xef\xbb\xbf")
    if had_bom:
        data = data[3:]

    for enc in ENCODING_FALLBACKS:
        try:
            return data.decode(enc), enc, had_bom
        except UnicodeDecodeError:
            continue
    # Should never reach here because latin-1 is in the list
    raise RuntimeError("decode failed")


def normalize_line_endings(text):
    """Normalize CRLF and lone CR to LF."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def is_strict_utf8_lf_no_bom(data):
    """Return True if data is valid UTF-8, has no BOM, and uses LF only."""
    if data.startswith(b"\xef\xbb\xbf"):
        return False
    if b"\r" in data:
        return False
    try:
        data.decode("utf-8", errors="strict")
        return True
    except UnicodeDecodeError:
        return False


def cmd_check(path):
    try:
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"ERROR reading {path}: {e}", file=sys.stderr)
        return 2

    if is_strict_utf8_lf_no_bom(data):
        print(f"OK: {path} (utf-8, no BOM, LF only)")
        return 0
    # Diagnose
    issues = []
    if data.startswith(b"\xef\xbb\xbf"):
        issues.append("has BOM")
    if b"\r\n" in data:
        issues.append("has CRLF")
    elif b"\r" in data:
        issues.append("has lone CR")
    try:
        data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        issues.append("not UTF-8")
    print(f"FAIL: {path} ({', '.join(issues)})")
    return 1


def cmd_convert(output_path, input_path):
    src = input_path if input_path else output_path

    try:
        with open(src, "rb") as f:
            data = f.read()
    except OSError as e:
        print(f"ERROR reading {src}: {e}", file=sys.stderr)
        return 2

    try:
        text, encoding, had_bom = detect_and_decode(data)
    except Exception as e:
        print(f"ERROR decoding {src}: {e}", file=sys.stderr)
        return 2

    text = normalize_line_endings(text)

    parent = os.path.dirname(output_path)
    if parent:
        os.makedirs(parent, exist_ok=True)

    try:
        with open(output_path, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    except OSError as e:
        print(f"ERROR writing {output_path}: {e}", file=sys.stderr)
        return 2

    notes = []
    if encoding != "utf-8":
        notes.append(f"encoding {encoding} -> utf-8")
    if had_bom:
        notes.append("stripped BOM")
    if "\r" in data.decode("latin-1") and "\r" not in text:  # cheap CRLF detection
        notes.append("normalized line endings to LF")

    if notes:
        print(f"CONVERTED: {output_path} ({'; '.join(notes)})")
    elif input_path:
        print(f"COPIED: {input_path} -> {output_path} (already utf-8)")
    else:
        print(f"OK: {output_path} (already utf-8, no changes)")
    return 0


def main():
    p = argparse.ArgumentParser(
        description="Convert a file to strict UTF-8 (no BOM, LF line endings).",
        epilog="This tool does not read from stdin. Pass a file path.",
    )
    p.add_argument("path", help="Output path (or path to fix in place if --from is omitted)")
    p.add_argument("--from", dest="src", default=None,
                   help="Read from this file instead of the output path (copy + convert)")
    p.add_argument("--check", action="store_true",
                   help="Only verify; exit 0 if already strict UTF-8/LF/no-BOM, exit 1 otherwise")
    args = p.parse_args()

    if args.check:
        if args.src:
            print("ERROR: --check is incompatible with --from", file=sys.stderr)
            return 2
        return cmd_check(args.path)

    return cmd_convert(args.path, args.src)


if __name__ == "__main__":
    sys.exit(main())
