#!/usr/bin/env python3
"""
selftest.py - Regression self-test for the doc-system scripts.

Usage: python3 ~/.agent-docs/scripts/selftest.py [--verbose]

Covers the failure modes that have actually bitten this project:
  - encoding normalisation (GBK / Big5 / EUC-KR / Shift_JIS / EUC-JP / latin-1 /
    UTF-8 / BOM / CRLF / lone CR / control chars / binary / empty)
  - the "default mode must never guess" contract of convert-to-utf8.sh
  - git URL parsing, including forms that must NOT collapse into a shared identity
  - schema validation: deprecated fields, outdated version, _index.md coverage
  - _index.md derived tables staying isomorphic to templates/_index.md
  - sync-system removal of explicitly retired package files

Exit code: 0 = all pass, 1 = at least one failure.
Uses only the standard library. Creates nothing outside a temp directory.
"""

import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
CONVERT = os.path.join(HERE, "convert-to-utf8.sh")

PASS = []
FAIL = []
VERBOSE = False


def check(name, ok, detail=""):
    (PASS if ok else FAIL).append(name)
    if not ok:
        print(f"FAIL {name}" + (f"\n     {detail}" if detail else ""))
    elif VERBOSE:
        print(f"PASS {name}" + (f"  ({detail})" if detail else ""))


def load(script):
    spec = importlib.util.spec_from_file_location(
        script.replace("-", "_").replace(".py", ""), os.path.join(HERE, script))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------------------
# convert-to-utf8.sh
# --------------------------------------------------------------------------

def run_convert(path, *extra):
    r = subprocess.run(
        ["bash", CONVERT, *extra, path],
        capture_output=True, text=True, timeout=60,
    )
    return r.returncode, r.stdout + r.stderr


def test_encoding(tmp):
    d = os.path.join(tmp, "enc")
    os.makedirs(d)

    def write(name, text, enc):
        p = os.path.join(d, name)
        with open(p, "wb") as f:
            f.write(text.encode(enc))
        return p

    # --- default mode: only deterministic fixes, never guess -----------------
    zh = "# \u4e2d\u6587\u6ce8\u91ca\nprint(1)\n"
    gbk = write("gbk.py", zh, "gbk")
    rc, out = run_convert(gbk)
    with open(gbk, "rb") as f:
        after = f.read()
    check("default 模式对 GBK 拒绝改动",
          rc != 0 and after == zh.encode("gbk"),
          f"rc={rc} 文件是否被改={after != zh.encode('gbk')}")
    check("default 模式拒绝时给出可操作提示",
          "--from" in out or "--guess" in out, out.strip()[-200:])

    # --- CLI validation must fail fast ---------------------------------------
    r = subprocess.run(["bash", CONVERT, "--from"], capture_output=True,
                       text=True, timeout=5)
    check("--from 缺少编码时立即报错", r.returncode == 2 and "需要" in r.stderr,
          (r.stdout + r.stderr)[-200:])
    r = subprocess.run(["bash", CONVERT, "--unknown"], capture_output=True,
                       text=True, timeout=5)
    check("未知参数被拒绝", r.returncode == 2 and "未知参数" in r.stderr,
          (r.stdout + r.stderr)[-200:])
    r = subprocess.run(["bash", CONVERT, "--help"], capture_output=True,
                       text=True, timeout=5)
    check("帮助输出不泄漏脚本代码",
          r.returncode == 0 and "set -uo pipefail" not in r.stdout, r.stdout[-200:])

    # --- --from: deterministic conversion ------------------------------------
    rc, out = run_convert(gbk, "--from", "gb18030")
    with open(gbk, encoding="utf-8") as f:
        got = f.read()
    check("--from gb18030 正确转换", rc == 0 and got == zh, repr(got[:40]))

    # --- --guess: script-exclusive evidence wins -----------------------------
    evidence_cases = [
        ("kr.txt", "\ud55c\uad6d\uc5b4 \ud14c\uc2a4\ud1a0\n", "euc_kr", "EUC-KR 韩文"),
        ("jp.txt", "\u3053\u3093\u306b\u3061\u306f\u30c6\u30b9\u30c8\n", "shift_jis", "Shift_JIS 日文"),
        ("jp2.txt", "\u3053\u3093\u306b\u3061\u306f\u30c6\u30b9\u30c8\n", "euc_jp", "EUC-JP 日文"),
    ]
    for name, text, enc, label in evidence_cases:
        p = write(name, text, enc)
        rc, out = run_convert(p, "--guess")
        with open(p, "rb") as f:
            raw = f.read()
        try:
            got = raw.decode("utf-8")
        except UnicodeDecodeError:
            got = None
        check(f"--guess 正确还原 {label}", rc == 0 and got == text,
              f"rc={rc} got={got!r}")

    # Chinese legacy encodings decode to several different plausible strings.
    # --guess must reject them; callers can use --from once the source is known.
    ambiguous_cases = [
        ("tw.txt", "\u7e41\u9ad4\u4e2d\u6587\u6e2c\u8a66\n", "big5", "Big5 繁体"),
        ("cn.txt", zh, "gb18030", "GBK 简体"),
    ]
    for name, text, enc, label in ambiguous_cases:
        p = write(name, text, "gbk" if enc == "gb18030" else enc)
        before = open(p, "rb").read()
        rc, out = run_convert(p, "--guess")
        check(f"--guess 拒绝歧义的 {label}",
              rc != 0 and open(p, "rb").read() == before and "歧义" in out,
              f"rc={rc} out={out[-200:]!r}")
        rc, out = run_convert(p, "--from", enc)
        with open(p, encoding="utf-8") as f:
            got = f.read()
        check(f"--from 正确还原 {label}", rc == 0 and got == text,
              f"rc={rc} got={got!r}")

    # --- latin-1 must not be read as CJK ------------------------------------
    p = write("latin.txt", "caf\u00e9 na\u00efve r\u00e9sum\u00e9\n", "latin-1")
    rc, _ = run_convert(p, "--guess")
    with open(p, encoding="utf-8") as f:
        got = f.read()
    check("--guess 不把 latin-1 误判为 CJK",
          rc == 0 and got == "caf\u00e9 na\u00efve r\u00e9sum\u00e9\n", repr(got))

    p = write("utf16.txt", "UTF-16 文本\n", "utf-16")
    rc, _ = run_convert(p, "--from", "utf-16")
    with open(p, encoding="utf-8") as f:
        got = f.read()
    check("--from 可转换含 NUL 的 UTF-16 文本", rc == 0 and got == "UTF-16 文本\n",
          repr(got))

    # --- valid UTF-8 containing control chars must be accepted ---------------
    p = os.path.join(d, "ctrl.md")
    with open(p, "wb") as f:
        f.write("# \u6807\u9898\n\x0cpage break\n\x1b[31mred\x1b[0m\n".encode("utf-8"))
    before = open(p, "rb").read()
    rc, out = run_convert(p)
    check("含换页/ESC 的合法 UTF-8 判为合规",
          rc == 0 and open(p, "rb").read() == before, out.strip()[-160:])

    # --- BOM + CRLF + lone CR ------------------------------------------------
    p = os.path.join(d, "bom.md")
    with open(p, "wb") as f:
        f.write(b"\xef\xbb\xbf" + "# a\r\n\r\nb\rc\n".encode("utf-8"))
    rc, out = run_convert(p)
    got = open(p, "rb").read()
    check("BOM / CRLF / 孤立 CR 一并修复",
          rc == 0 and got == "# a\n\nb\nc\n".encode("utf-8"), repr(got))

    # --- idempotency ---------------------------------------------------------
    rc, out = run_convert(p)
    check("修复后再跑为幂等", rc == 0 and "[跳过]" in out, out.strip()[-120:])

    # --- binary untouched ----------------------------------------------------
    p = os.path.join(d, "blob.bin")
    payload = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    with open(p, "wb") as f:
        f.write(payload)
    rc, out = run_convert(p)
    check("二进制文件不被改动",
          open(p, "rb").read() == payload and "[二进制]" in out, out.strip()[-120:])

    # --- empty file ----------------------------------------------------------
    p = os.path.join(d, "empty.md")
    open(p, "wb").close()
    rc, _ = run_convert(p)
    check("空文件不报错", rc == 0)

    # --- script must not rewrite itself --------------------------------------
    rc, out = run_convert(CONVERT)
    check("不改写脚本自身", "[跳过]" in out and rc == 0, out.strip()[-120:])


# --------------------------------------------------------------------------
# parse_git_url
# --------------------------------------------------------------------------

def test_url_parsing():
    fc = load("doc-format-check.py")
    sc = load("doc-scaffold.py")

    ok_cases = [
        ("https://gitee.com/red_base/red_core.git", "gitee.com", "red_base", "red_core"),
        ("https://gitee.com/match3-team/res_personal", "gitee.com", "match3-team", "res_personal"),
        ("git@github.com:foo/Bar.git", "github.com", "foo", "Bar"),
        ("http://10.10.10.253:3000/zhuge/bulldog_sdk", "10.10.10.253:3000", "zhuge", "bulldog_sdk"),
        ("ssh://git@example.com:2222/team/proj.git", "example.com:2222", "team", "proj"),
        ("git://example.com/team/proj.git", "example.com", "team", "proj"),
        ("https://host.tld/a/b/c/deep.git", "host.tld", "a/b/c", "deep"),
        ("/srv/git/myrepo.git", "local", "srv/git", "myrepo"),
    ]
    for url, host, owner, name in ok_cases:
        for label, mod in (("format-check", fc), ("scaffold", sc)):
            h, o, n, good = mod.parse_git_url(url)
            check(f"URL 解析[{label}] {url}",
                  good and (h, o, n) == (host, owner, name),
                  f"got={(h, o, n, good)} want={(host, owner, name, True)}")

    # 不可解析的 URL 之间不得共享身份
    weird = ["not a url at all", "???", "mailto:someone@example.com"]
    ids = []
    for u in weird:
        h, o, n, good = fc.parse_git_url(u)
        check(f"不可解析被标记: {u!r}", not good, f"got={(h, o, n, good)}")
        ids.append((h, o, n))
    check("不同的不可解析 URL 身份互不相同",
          len(set(ids)) == len(ids), f"ids={ids}")

    scp_port = fc.parse_git_url("git@example.com:2222:team/proj.git")
    ssh_port = fc.parse_git_url("ssh://git@example.com:2222/team/proj.git")
    check("同一带端口仓库的两种 SSH 写法身份一致", scp_port == ssh_port,
          f"scp={scp_port} ssh={ssh_port}")

    local_a = fc.parse_git_url("/srv/git/myrepo.git")
    local_b = fc.parse_git_url("/home/git/myrepo.git")
    check("不同绝对路径的同名本地仓库身份不碰撞", local_a != local_b,
          f"a={local_a} b={local_b}")

    h, o, n, good = fc.parse_git_url("")
    check("空 URL 被标记为不可解析", not good, f"got={(h, o, n, good)}")

    # 两个脚本的实现必须一致
    same = all(fc.parse_git_url(u) == sc.parse_git_url(u)
               for u, *_ in ok_cases + [(w,) for w in weird])
    check("两份 parse_git_url 实现一致", same)


# --------------------------------------------------------------------------
# doc-format-check.py
# --------------------------------------------------------------------------

DOC_V7 = """---
schema_version: 7
repo: "git@github.com:foo/Bar.git"
branch: "release/2026-q2"
commit: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
origin_path_in_main: "Libraries/Bar"
---

# Bar

## 定位
负责关卡数据的加载与校验。
"""

DOC_V5 = """---
schema_version: 5
agent_load: on-demand
repo: "https://gitee.com/a/b.git"
origin_host: "gitee.com"
owner: "a"
name: "b"
branch: "main"
commit: "0123456789abcdef0123456789abcdef01234567"
sub_section: "flow"
---

# b
"""


def make_project(tmp, docs, index_sv=7, main_sv=7, index_extra=""):
    root = os.path.join(tmp, f"proj{len(os.listdir(tmp))}")
    mods = os.path.join(root, ".agent-docs", "doc-library", "modules")
    os.makedirs(mods)
    for name, body in docs.items():
        with open(os.path.join(mods, name), "w", encoding="utf-8") as f:
            f.write(body)
    with open(os.path.join(root, ".agent-docs", "_index.md"), "w", encoding="utf-8") as f:
        f.write(f"---\nschema_version: {index_sv}\n{index_extra}---\n\n# idx\n")
    with open(os.path.join(root, ".agent-docs", "doc-library", "main-module.md"),
              "w", encoding="utf-8") as f:
        f.write(f"---\nschema_version: {main_sv}\n---\n\n# main\n")
    return root


def run_fc(root):
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "doc-format-check.py"), root],
        capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout


def test_format_check(tmp):
    root = make_project(tmp, {"github-com__foo__Bar__release-2026-q2.md": DOC_V7})
    rc, out = run_fc(root)
    check("干净的 v7 项目 ALL_PASS", rc == 0 and "ALL_PASS" in out, out.strip()[:300])

    root = make_project(tmp, {"gitee-com__a__b__main.md": DOC_V5})
    rc, out = run_fc(root)
    for f in ("agent_load", "origin_host", "owner", "name", "sub_section"):
        check(f"v5 文档报 DEPRECATED_FIELD({f})", f"DEPRECATED_FIELD({f})" in out)
    check("已删除的两个 structure 脚本不再存在",
          not os.path.exists(os.path.join(HERE, "doc-structure-extract.py"))
          and not os.path.exists(os.path.join(HERE, "doc-structure-import.py")))
    check("v5 文档报 OUTDATED_SCHEMA_VERSION",
          "OUTDATED_SCHEMA_VERSION(5, expected 7)" in out)

    # _index.md / main-module.md 必须被覆盖（历史上漏扫，导致永久停在旧版本）
    root = make_project(tmp, {"github-com__foo__Bar__release-2026-q2.md": DOC_V7},
                        index_sv=4, main_sv=4, index_extra="agent_load: always\n")
    rc, out = run_fc(root)
    check("_index.md 的旧 schema 被检出",
          "_index.md: OUTDATED_SCHEMA_VERSION(4, expected 7)" in out, out)
    check("_index.md 的废弃字段被检出",
          "_index.md: DEPRECATED_FIELD(agent_load)" in out, out)
    check("main-module.md 的旧 schema 被检出",
          "main-module.md: OUTDATED_SCHEMA_VERSION(4, expected 7)" in out, out)

    # 不可解析的 repo 不得参与四元组比较（否则会被提议合并 / 列入删除候选）
    bad = DOC_V7.replace('repo: "git@github.com:foo/Bar.git"', 'repo: "garbage"')
    root = make_project(tmp, {"a__b__c__main.md": bad,
                              "d__e__f__main.md": bad.replace("Bar", "Baz")})
    rc, out = run_fc(root)
    check("不可解析 repo 报 UNPARSEABLE_REPO_URL", "UNPARSEABLE_REPO_URL" in out, out)
    check("不可解析 repo 不产生 DUPLICATE_FOUR_TUPLE",
          "DUPLICATE_FOUR_TUPLE" not in out, out)

    # 真正的重复仍要抓到
    root = make_project(tmp, {"x__1.md": DOC_V7, "x__2.md": DOC_V7})
    rc, out = run_fc(root)
    check("同 repo 同 branch 仍报 DUPLICATE_FOUR_TUPLE",
          "DUPLICATE_FOUR_TUPLE" in out, out)

    # v7 起 structure 是废弃字段，出现即报
    with_struct = DOC_V7.replace(
        'origin_path_in_main: "Libraries/Bar"',
        'origin_path_in_main: "Libraries/Bar"\nstructure:\n  deps: []\n  exports: []')
    root = make_project(tmp, {"github-com__foo__Bar__release-2026-q2.md": with_struct})
    rc, out = run_fc(root)
    check("structure 字段被判为废弃",
          rc == 1 and "DEPRECATED_FIELD(structure)" in out, out)

    with_unknown = DOC_V7.replace(
        'origin_path_in_main: "Libraries/Bar"',
        'origin_path_in_main: "Libraries/Bar"\nunexpected_field: "x"')
    root = make_project(tmp, {"github-com__foo__Bar__release-2026-q2.md": with_unknown})
    rc, out = run_fc(root)
    check("schema 白名单拒绝任意未知顶层字段",
          rc == 1 and "DEPRECATED_FIELD(unexpected_field)" in out, out)

    root = make_project(tmp, {"github-com__foo__Bar__release-2026-q2.md": DOC_V7},
                        index_extra="project_config:\n  initial_bootstrap_done: false\n")
    rc, out = run_fc(root)
    check("_index.md 保留 project_config 特例",
          rc == 0 and "DEPRECATED_FIELD(project_config)" not in out, out)

    index_path = os.path.join(root, ".agent-docs", "_index.md")
    with open(index_path, "r+", encoding="utf-8") as f:
        body = f.read().replace("project_config:", "unexpected_index_key:\n  x: y\nproject_config:")
        f.seek(0)
        f.write(body)
        f.truncate()
    rc, out = run_fc(root)
    check("_index.md 拒绝 project_config 之外的未知字段",
          rc == 1 and "DEPRECATED_FIELD(unexpected_index_key)" in out, out)


# --------------------------------------------------------------------------
# doc-tree.py --emit-index-tables
# --------------------------------------------------------------------------

def test_emit_index_tables(tmp):
    root = make_project(tmp, {"github-com__foo__Bar__release-2026-q2.md": DOC_V7})
    mods = os.path.join(root, ".agent-docs", "doc-library", "modules")
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "doc-tree.py"), root, "--emit-index-tables"],
        capture_output=True, text=True, timeout=60)
    out = r.stdout
    check("派生表提取到一句话定位",
          "\u8d1f\u8d23\u5173\u5361\u6570\u636e\u7684\u52a0\u8f7d\u4e0e\u6821\u9a8c\u3002" in out, out)

    # 与模板同构：说明行 / 分隔线 / 空态占位符都必须一致，
    # 否则 doc-doctor 的"整节替换"会删掉模板里的手写内容。
    tpl = open(os.path.join(ROOT, "templates", "_index.md"), encoding="utf-8").read()
    note = "> \u6d3e\u751f\u89c6\u56fe\uff0c\u7531 `doc-tree.py --emit-index-tables` " \
           "\u518d\u751f\uff0c\u52ff\u624b\u5de5\u7ef4\u62a4\u3002"
    check("派生表含与模板一致的说明行", out.count(note) == 2, f"count={out.count(note)}")
    check("模板含同一说明行", tpl.count(note) == 2, f"count={tpl.count(note)}")
    check("派生表含 --- 分隔线", "\n---\n" in out)

    empty = os.path.join(tmp, "emptyproj")
    os.makedirs(os.path.join(empty, ".agent-docs", "doc-library", "modules"))
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "doc-tree.py"), empty, "--emit-index-tables"],
        capture_output=True, text=True, timeout=60)
    placeholder = "| _\uff08\u6682\u65e0\uff09_ | | | |"
    check("空项目派生表用与模板一致的占位行",
          r.stdout.count(placeholder) == 2, r.stdout)
    check("模板用同一占位行", tpl.count(placeholder) == 2,
          f"count={tpl.count(placeholder)}")

    # 骨架占位的定位不应被当成正文
    doc = DOC_V7.replace("\u8d1f\u8d23\u5173\u5361\u6570\u636e\u7684\u52a0\u8f7d\u4e0e\u6821\u9a8c\u3002",
                         "\uff08\u4e00\u53e5\u8bdd\u8bf4\u6e05\u6a21\u5757\u89d2\u8272\uff09")
    root2 = make_project(tmp, {"github-com__foo__Bar__release-2026-q2.md": doc})
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "doc-tree.py"), root2, "--emit-index-tables"],
        capture_output=True, text=True, timeout=60)
    check("骨架占位定位留空",
          "\uff08\u4e00\u53e5\u8bdd\u8bf4\u6e05" not in r.stdout, r.stdout)


# --------------------------------------------------------------------------
# doc-encoding-check.py alignment
# --------------------------------------------------------------------------

def test_encoding_check_alignment(tmp):
    root = os.path.join(tmp, "encproj")
    d = os.path.join(root, ".agent-docs")
    os.makedirs(d)
    with open(os.path.join(d, "ctrl.md"), "wb") as f:
        f.write("# a\n\x0c\x1b[0m\n".encode("utf-8"))
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "doc-encoding-check.py"), root],
        capture_output=True, text=True, timeout=60)
    check("encoding-check 不把控制字符判为问题",
          "ALL_PASS" in r.stdout, r.stdout)

    with open(os.path.join(d, "cr.md"), "wb") as f:
        f.write(b"a\rb\n")
    r = subprocess.run(
        [sys.executable, os.path.join(HERE, "doc-encoding-check.py"), root],
        capture_output=True, text=True, timeout=60)
    check("encoding-check 检出孤立 CR", "LONE_CR_DETECTED" in r.stdout, r.stdout)


def test_sync_obsolete(tmp):
    sync = load("doc-sync-system.py")
    original_home = sync.AGENT_DOCS_HOME
    home = os.path.join(tmp, "sync-home")
    src = os.path.join(tmp, "sync-package")
    os.makedirs(os.path.join(home, "scripts"))
    os.makedirs(os.path.join(src, "scripts"))
    obsolete = [
        "doc-structure-extract.py",
        "doc-structure-import.py",
    ]
    for name in obsolete + ["custom.py"]:
        with open(os.path.join(home, "scripts", name), "w", encoding="utf-8") as f:
            f.write(name)
    try:
        sync.AGENT_DOCS_HOME = home
        removed = sync.collect_obsolete(src)
        check("sync 只识别显式淘汰的 structure 脚本",
              {os.path.basename(p) for p in removed} == set(obsolete), repr(removed))
        backup = sync.make_backup()
        sync.apply_removals(removed)
        check("sync 删除显式淘汰脚本",
              all(not os.path.exists(os.path.join(home, "scripts", n)) for n in obsolete))
        check("sync 保留未列入淘汰清单的自定义脚本",
              os.path.isfile(os.path.join(home, "scripts", "custom.py")))
        check("sync 删除前备份淘汰脚本",
              all(os.path.isfile(os.path.join(backup, "scripts", n)) for n in obsolete))
    finally:
        sync.AGENT_DOCS_HOME = original_home


# --------------------------------------------------------------------------

def main():
    global VERBOSE
    ap = argparse.ArgumentParser()
    ap.add_argument("--verbose", action="store_true")
    VERBOSE = ap.parse_args().verbose

    tmp = tempfile.mkdtemp(prefix="doc-selftest-")
    try:
        test_encoding(tmp)
        test_url_parsing()
        test_format_check(tmp)
        test_emit_index_tables(tmp)
        test_encoding_check_alignment(tmp)
        test_sync_obsolete(tmp)
        test_lint(tmp)
        test_content_constraints(tmp)
        for script in ("test_doc_gate.py", "test_doc_gate_install.py"):
            result = subprocess.run([sys.executable, os.path.join(HERE, script), "-q"],
                                    capture_output=True, text=True, timeout=120)
            check(script + " behavioral tests", result.returncode == 0, result.stdout + result.stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(PASS) + len(FAIL)
    print(f"\n{len(PASS)}/{total} passed")
    if FAIL:
        print("FAILED:")
        for name in FAIL:
            print(f"  - {name}")
        sys.exit(1)
    print("ALL_PASS")
    sys.exit(0)


# --------------------------------------------------------------------------
# doc-lint-consistency.py
#
# The lint exists because prose restatements drift. It must itself be tested
# against synthetic packages with deliberate defects -- running it on the real
# repo only tells us what the repo looks like today, not whether the lint works.
# --------------------------------------------------------------------------

LINT = os.path.join(HERE, "doc-lint-consistency.py")

LINT_MANUAL = """---
schema_version: 7
---

# demo manual

\u4e0d\u5f97\u628a\u672c\u811a\u672c\u63cf\u8ff0\u4e3a\u300c\u81ea\u52a8\u68c0\u6d4b\u5e76\u4fee\u590d GBK\u300d\u3002

## 9. yaml \u5143\u4fe1\u606f schema

| \u5b57\u6bb5 | \u5fc5\u586b | \u8bf4\u660e |
|---|---|---|
| `schema_version` | \u662f | x |
| `repo` | \u662f | x |
| `archived` | \u5426 | x |

| \u79fb\u9664\u5b57\u6bb5 | \u4f9d\u636e | \u66ff\u4ee3\u6765\u6e90 |
|---|---|---|
| `old_field` | x | y |

## 15. \u5173\u8054\u7684 skill

| \u89e6\u53d1\u8bcd | \u7528\u9014 | \u5bf9\u5e94\u7ae0\u8282 |
|---|---|---|
| `/doc-demo` | x | \u00a79 |

## 16. \u5de5\u5177\u811a\u672c

\u8c03\u7528 `python3 doc-format-check.py <root> --docs-dir <d>`\uff0c\u6a21\u677f\u89c1 templates/_index.md\u3002

| \u811a\u672c | \u7528\u9014 |
|---|---|
| `doc-format-check.py` | x |
| `doc-other.py` | y |
| `selftest.py` | z |
"""

LINT_SKILL = """---
name: doc-demo
description: "demo"
---

> \u5bf9\u5e94\u7ae0\u8282\uff1a\u00a79

## \u6267\u884c\u6b65\u9aa4

1. \u7b2c\u4e00\u6b65
2. \u7b2c\u4e8c\u6b65
"""

LINT_FC = '''#!/usr/bin/env python3
"""fake doc-format-check for lint fixtures."""
import argparse

REQUIRED_FIELDS = ["schema_version", "repo"]
ALLOWED_FIELDS = ["schema_version", "repo", "archived"]
DEPRECATED_FIELDS = ["old_field"]


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--docs-dir", default=None)
    p.parse_args()
    print("STALE ORPHAN_DOC")
'''

LINT_OTHER = '''#!/usr/bin/env python3
"""fake second script, declares a flag doc-format-check does not have."""
import argparse

p = argparse.ArgumentParser()
p.add_argument("--other", default=None)
'''

LINT_SELFTEST = '''#!/usr/bin/env python3
"""Fixture that mentions GHOST_STATUS only as an expected test value."""
'''


def make_lint_pkg(tmp, tag, mutations=()):
    """Build a minimal doc-system package; each mutation is (relpath, old, new)."""
    root = os.path.join(tmp, "lintpkg-" + tag)
    files = {
        os.path.join("manual", "doc-system.md"): LINT_MANUAL,
        os.path.join("scripts", "doc-format-check.py"): LINT_FC,
        os.path.join("scripts", "doc-other.py"): LINT_OTHER,
        os.path.join("scripts", "selftest.py"): LINT_SELFTEST,
        os.path.join("skills", "doc-demo", "SKILL.md"): LINT_SKILL,
        os.path.join("templates", "_index.md"): "---\nschema_version: 7\n---\n",
    }
    for rel, old, new in mutations:
        assert old in files[rel], f"fixture mutation not applicable: {old!r}"
        files[rel] = files[rel].replace(old, new)
    for rel, body in files.items():
        p = os.path.join(root, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            f.write(body)
    return root


def run_lint(root):
    r = subprocess.run([sys.executable, LINT, root],
                       capture_output=True, text=True, timeout=60)
    return r.returncode, r.stdout


MANUAL_REL = os.path.join("manual", "doc-system.md")
SKILL_REL = os.path.join("skills", "doc-demo", "SKILL.md")


def test_lint(tmp):
    root = make_lint_pkg(tmp, "clean")
    rc, out = run_lint(root)
    check("lint 对无瑕疵包报 ALL_PASS", rc == 0 and "ALL_PASS" in out, out)

    quoted = make_lint_pkg(tmp, "single-quotes", [
        (os.path.join("scripts", "doc-format-check.py"),
         'add_argument("--docs-dir",', "add_argument('--docs-dir',")])
    rc, out = run_lint(quoted)
    check("lint recognizes single-quoted CLI flags", rc == 0 and "ALL_PASS" in out, out)

    cases = [
        ("MANUAL_SECTION_REF", "\u5f15\u7528\u4e0d\u5b58\u5728\u7684\u7ae0\u8282",
         [(SKILL_REL, "\u00a79\n", "\u00a799\n")]),
        ("SCRIPT_REF", "\u5f15\u7528\u4e0d\u5b58\u5728\u7684\u811a\u672c",
         [(MANUAL_REL, "doc-format-check.py <root>", "doc-ghost.py <root>")]),
        ("UNKNOWN_FLAG", "\u5f15\u7528\u65e0\u4eba\u58f0\u660e\u7684 flag",
         [(SKILL_REL, "1. \u7b2c\u4e00\u6b65", "1. \u7b2c\u4e00\u6b65 `--nope`")]),
        ("SCRIPT_FLAG_REF", "\u628a\u522b\u7684\u811a\u672c\u7684 flag \u7ed9\u9519\u4e86\u5bf9\u8c61",
         [(MANUAL_REL, "--docs-dir <d>", "--other <d>")]),
        ("STATUS_CODE_REF", "\u5f15\u7528\u4e0d\u5b58\u5728\u7684\u72b6\u6001\u7801",
         [(SKILL_REL, "1. \u7b2c\u4e00\u6b65", "1. \u7b2c\u4e00\u6b65 `MISSING_THING`")]),
        ("SCHEMA_FIELD_SYNC", "\u624b\u518c\u5fc5\u586b\u8868\u4e0e\u811a\u672c\u4e0d\u7b26",
         [(MANUAL_REL, "| `archived` | \u5426 |", "| `archived` | \u662f |")]),
        ("SCHEMA_FIELD_SYNC", "\u624b\u518c\u5141\u8bb8\u5b57\u6bb5\u4e0e\u811a\u672c\u767d\u540d\u5355\u4e0d\u7b26",
         [(os.path.join("scripts", "doc-format-check.py"),
           ', "archived"]', "]")]),
        ("HOME_PATH_REF", "\u5f15\u7528\u5b89\u88c5\u5668\u4e0d\u521b\u5efa\u7684 ~ \u8def\u5f84",
         [(MANUAL_REL, "\u6a21\u677f\u89c1 templates/_index.md",
           "\u89c1 ~/.nonexistent-venv/bin/python3")]),
        # \u8fb9\u754c\u9677\u9631\uff1a~/.agent-docs-venv \u4e0d\u5c5e\u4e8e ~/.agent-docs
        ("HOME_PATH_REF", "\u540c\u524d\u7f00\u4f46\u4e0d\u540c\u76ee\u5f55\u7684 ~ \u8def\u5f84",
         [(MANUAL_REL, "\u6a21\u677f\u89c1 templates/_index.md",
           "\u89c1 ~/.agent-docs-venv/bin/python3")]),
        ("SKILL_REGISTRY_SYNC", "\u624b\u518c\u767b\u8bb0\u4e86\u4e0d\u5b58\u5728\u7684 skill",
         [(MANUAL_REL, "| `/doc-demo` | x | \u00a79 |",
           "| `/doc-demo` | x | \u00a79 |\n| `/doc-ghost` | x | \u00a79 |")]),
        ("SKILL_NUMBERING", "\u6b65\u9aa4\u7f16\u53f7\u91cd\u590d",
         [(SKILL_REL, "2. \u7b2c\u4e8c\u6b65", "1. \u7b2c\u4e8c\u6b65")]),
        ("SCRIPT_REGISTRY_SYNC", "\u811a\u672c\u5b58\u5728\u4f46 \u00a716 \u672a\u767b\u8bb0",
         [(MANUAL_REL, "| `doc-other.py` | y |\n", "")]),
        ("SCHEMA_VERSION_SYNC", "\u6a21\u677f\u7684 schema \u7248\u672c\u843d\u540e\u4e8e\u624b\u518c",
         [(os.path.join("templates", "_index.md"),
           "schema_version: 7", "schema_version: 6")]),
        ("FORBIDDEN_PHRASE", "skill \u58f0\u79f0\u811a\u672c\u4f1a\u81ea\u52a8\u4fee\u590d GBK",
         [(SKILL_REL, "1. \u7b2c\u4e00\u6b65",
           "1. \u7b2c\u4e00\u6b65\uff08\u81ea\u52a8\u68c0\u6d4b\u5e76\u4fee\u590d GBK\uff09")]),
        ("FORBIDDEN_PHRASE", "\u624b\u518c\u5176\u4ed6\u4f4d\u7f6e\u4ecd\u4f7f\u7528\u7981\u7528\u8bf4\u6cd5",
         [(MANUAL_REL, "# demo manual",
           "# demo manual\n\n\u8be5\u811a\u672c\u4f1a\u81ea\u52a8\u68c0\u6d4b\u5e76\u4fee\u590d GBK\u3002")]),
        ("TEMPLATE_REF", "\u5f15\u7528\u4e0d\u5b58\u5728\u7684\u6a21\u677f",
         [(MANUAL_REL, "templates/_index.md", "templates/missing.md")]),
    ]
    for code, desc, mutations in cases:
        root = make_lint_pkg(tmp, code.lower(), mutations)
        rc, out = run_lint(root)
        check(f"lint 抓到 {code}（{desc}）",
              rc == 1 and code in out, out.strip()[:300])

    root = make_lint_pkg(tmp, "status-fixture", [
        (MANUAL_REL, "# demo manual", "# demo manual\n\n\u8fd0\u884c\u53ef\u80fd\u8fd4\u56de `GHOST_STATUS`\u3002"),
    ])
    rc, out = run_lint(root)
    check("lint \u4e0d\u628a selftest fixture \u5f53\u6210\u72b6\u6001\u7801\u5b9e\u73b0",
          rc == 1 and "STATUS_CODE_REF" in out, out)

    # 误报防御：手册泛指"脚本 --out 输出"时不得归咎于同行出现的脚本
    root = make_lint_pkg(tmp, "noprose", [
        (MANUAL_REL, "\u6a21\u677f\u89c1 templates/_index.md",
         "\u811a\u672c `--docs-dir` \u8f93\u51fa\uff1b\u6a21\u677f\u89c1 templates/_index.md"),
    ])
    rc, out = run_lint(root)
    check("lint 不因散文中的 flag 误报", rc == 0 and "ALL_PASS" in out, out)

    # 误报防御：编号按小节重置，阶段 A/B 各自从 1 开始是合法的
    root = make_lint_pkg(tmp, "sections", [
        (SKILL_REL, "1. \u7b2c\u4e00\u6b65\n2. \u7b2c\u4e8c\u6b65",
         "### \u9636\u6bb5 A\n\n1. a\n2. b\n\n### \u9636\u6bb5 B\n\n1. c\n2. d"),
    ])
    rc, out = run_lint(root)
    check("lint 允许编号按小节重置", rc == 0 and "ALL_PASS" in out, out)


# --------------------------------------------------------------------------
# doc-format-check.py content constraints (manual sections 6 and 8)
#
# These rules lived only in prose until now. Real project data does not exercise
# them (the prose bodies there are ~40 lines each), so fixtures are the only way
# to know the checks work at all.
# --------------------------------------------------------------------------

CONTENT_HEAD = """---
schema_version: 7
repo: "git@github.com:foo/Bar.git"
branch: "main"
commit: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"
---

# Bar
"""


def content_doc(*chapters):
    """Build a v7 module doc whose body contains the given (name, text) chapters."""
    out = CONTENT_HEAD
    for name, text in chapters:
        out += f"\n## {name}\n{text}\n"
    return out


def test_content_constraints(tmp):
    ok = content_doc(
        ("\u5b9a\u4f4d", "\u8d1f\u8d23\u5173\u5361\u6570\u636e\u52a0\u8f7d\u3002"),
        ("\u804c\u8d23\u8fb9\u754c", "\u505a\u4ec0\u4e48 / \u4e0d\u505a\u4ec0\u4e48\u3002"),
        ("\u63a5\u53e3", "\u5bf9\u5916\u63a5\u53e3\u3002"),
    )
    root = make_project(tmp, {"github-com__foo__Bar__main.md": ok})
    rc, out = run_fc(root)
    check("\u5408\u89c4\u6b63\u6587 ALL_PASS", rc == 0 and "ALL_PASS" in out, out[:300])

    cases = [
        ("DOC_TOO_LONG", "\u6b63\u6587\u8d85 500 \u884c",
         content_doc(("\u5b9a\u4f4d", "x\n" * 600))),
        ("CHAPTER_TOO_LONG", "\u5355\u7ae0\u8d85 80 \u884c",
         content_doc(("\u5b9a\u4f4d", "x"), ("\u67b6\u6784", "y\n" * 100))),
        ("PATCH_NARRATIVE", "\u8865\u4e01\u5f0f\u53d9\u8ff0",
         content_doc(("\u5b9a\u4f4d", "\u8fd9\u91cc\u4fee\u590d\u4e86\u4e00\u4e2a\u5d29\u6e83\u3002"))),
        ("LINE_NUMBER_REF", "\u5199\u4e86\u884c\u53f7",
         content_doc(("\u63a5\u53e3", "\u53c2\u89c1 Foo.cpp:120\u3002"))),
        ("LINE_NUMBER_REF", "\u5199\u4e86\u4e2d\u6587\u884c\u53f7",
         content_doc(("\u63a5\u53e3", "\u89c1\u7b2c 42 \u884c\u3002"))),
        ("CROSS_DOC_REF", "\u5f15\u7528\u5176\u4ed6\u5b50\u6a21\u5757\u6587\u6863",
         content_doc(("\u4f9d\u8d56", "\u89c1 gitee-com__x__y__main.md\u3002"))),
        ("CHAPTER_ORDER", "\u7ae0\u8282\u987a\u5e8f\u9519\u4e71",
         content_doc(("\u63a5\u53e3", "a"), ("\u5b9a\u4f4d", "b"))),
    ]
    for code, desc, body in cases:
        root = make_project(tmp, {"github-com__foo__Bar__main.md": body})
        rc, out = run_fc(root)
        check(f"\u5185\u5bb9\u7ea6\u675f\u6293\u5230 {code}\uff08{desc}\uff09",
              rc == 1 and code in out, out.strip()[:300])

    # \u8bef\u62a5\u9632\u5fa1\uff1a\u5f15\u7528\u81ea\u8eab\u7684\u9644\u5c5e\u6587\u6863\u662f\u5408\u6cd5\u7684
    root = make_project(tmp, {"github-com__foo__Bar__main.md": content_doc(
        ("\u67b6\u6784", "\u62c6\u5206\u89c1 github-com__foo__Bar__main__flow.md\u3002"))})
    rc, out = run_fc(root)
    check("\u5f15\u7528\u81ea\u8eab\u9644\u5c5e\u6587\u6863\u4e0d\u62a5 CROSS_DOC_REF",
          "CROSS_DOC_REF" not in out, out.strip()[:300])

    # \u8bef\u62a5\u9632\u5fa1\uff1a\u5f52\u6863\u6587\u6863\u4e0d\u53d7\u5185\u5bb9\u7ea6\u675f\u7ea6\u675f
    archived = content_doc(("\u5b9a\u4f4d", "x\n" * 600)).replace(
        'commit: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"',
        'commit: "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0"\n'
        'archived: true\narchived_at: "2026-05-01"\n'
        'archived_reason: "removed-from-gitmodules"\n'
        'origin_path_in_main: "Libraries/Bar"')
    root = make_project(tmp, {"github-com__foo__Bar__main.md": archived})
    rc, out = run_fc(root)
    check("\u5f52\u6863\u6587\u6863\u8df3\u8fc7\u5185\u5bb9\u7ea6\u675f",
          "DOC_TOO_LONG" not in out, out.strip()[:300])


if __name__ == "__main__":
    main()
