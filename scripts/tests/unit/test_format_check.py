#!/usr/bin/env python3
"""测试 doc-format-check 的 schema 校验扩展。"""

import importlib.util
import os
import tempfile
import shutil

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "doc-format-check.py")


def load_module():
    spec = importlib.util.spec_from_file_location("fc", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VALID_DOC = """---
schema_version: 3
agent_load: on-demand
repo: "https://github.com/foo/bar.git"
origin_host: "github.com"
owner: "foo"
name: "bar"
branch: "main"
commit: "abcdef0123456789abcdef0123456789abcdef01"
structure:
  deps:
    - m: "react"
      role: "utility"
      granularity: "module"
  exports:
    - n: "Foo"
      t: "class"
      vis: "public"
  inner: []
  cross_module_contracts:
    - with: "modules/bar"
      protocol: "delegate"
      direction: "outbound"
  data_flow_anchors:
    - name: "GameState"
      holders:
        - "core/state"
        - "modules/ui"
---

# Bar
"""

INVALID_ROLE_DOC = VALID_DOC.replace('role: "utility"', 'role: "bogus"')
INVALID_PROTOCOL_DOC = VALID_DOC.replace('protocol: "delegate"', 'protocol: "BOGUS"')
INVALID_ANCHOR_HOLDERS = VALID_DOC.replace(
    'holders:\n        - "core/state"\n        - "modules/ui"',
    'holders:\n        - "core/state"',
)


def write_doc(tmpdir, filename, content):
    path = os.path.join(tmpdir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return path


def test_valid(m):
    with tempfile.TemporaryDirectory() as tmp:
        modules_dir = os.path.join(tmp, ".agent-docs", "doc-library", "modules")
        os.makedirs(modules_dir)
        write_doc(modules_dir, "valid.md", VALID_DOC)
        # 通过运行 main 间接校验：使用 sys.argv 模拟
        import sys
        argv_save = sys.argv
        sys.argv = ["doc-format-check.py", tmp]
        try:
            m.main()
        except SystemExit as e:
            assert e.code == 0, "valid doc should pass"
        finally:
            sys.argv = argv_save
    print("PASS: test_valid")


def _expect_issue(m, content, marker, label):
    with tempfile.TemporaryDirectory() as tmp:
        modules_dir = os.path.join(tmp, ".agent-docs", "doc-library", "modules")
        os.makedirs(modules_dir)
        write_doc(modules_dir, "doc.md", content)
        import sys, io
        out = io.StringIO()
        saved_out = sys.stdout
        sys.stdout = out
        argv_save = sys.argv
        sys.argv = ["doc-format-check.py", tmp]
        exit_code = None
        try:
            m.main()
        except SystemExit as e:
            exit_code = e.code
        finally:
            sys.stdout = saved_out
            sys.argv = argv_save
        text = out.getvalue()
        assert marker in text, f"expected '{marker}' in output, got:\n{text}"
        assert exit_code == 1, f"expected non-zero exit, got {exit_code}"
        print(f"PASS: test_invalid_{label}")


def test_invalid_role(m):
    _expect_issue(m, INVALID_ROLE_DOC, "INVALID_ROLE", "role")


def test_invalid_protocol(m):
    _expect_issue(m, INVALID_PROTOCOL_DOC, "INVALID_PROTOCOL", "protocol")


def test_anchor_holders_lt_2(m):
    _expect_issue(m, INVALID_ANCHOR_HOLDERS, "HOLDERS_LT_2", "anchor_holders")


# P0-3 修复：inner.base 嵌套 dict 不应污染同级字段
DOC_WITH_BASE_NESTED = """---
schema_version: 3
agent_load: on-demand
repo: "https://github.com/foo/bar.git"
origin_host: "github.com"
owner: "foo"
name: "bar"
branch: "main"
commit: "abcdef0123456789abcdef0123456789abcdef01"
structure:
  deps: []
  exports: []
  inner:
    - n: "Bus"
      t: "class"
      has:
        - "subscribe"
        - "emit"
      base:
        extends:
          - "BaseBus"
        implements:
          - "IBus"
      pattern: "observer"
  cross_module_contracts: []
  data_flow_anchors: []
---

# Bar
"""


def test_inner_base_nested_dict_no_pollution(m):
    """P0-3 修复：base: { extends, implements } 嵌套 dict 不应污染 has 列表或其他字段。"""
    with tempfile.TemporaryDirectory() as tmp:
        modules_dir = os.path.join(tmp, ".agent-docs", "doc-library", "modules")
        os.makedirs(modules_dir)
        write_doc(modules_dir, "doc.md", DOC_WITH_BASE_NESTED)
        # 直接调 parse_structure_block 验证 has 不被污染
        raw = m.extract_meta_raw(os.path.join(modules_dir, "doc.md"))
        struct = m.parse_structure_block(raw)
        inner = struct.get("inner", [])
        assert len(inner) == 1, f"expected 1 inner, got {inner}"
        bus = inner[0]
        assert bus.get("n") == "Bus"
        assert bus.get("has") == ["subscribe", "emit"], \
            f"has list polluted by base nested dict: {bus.get('has')}"
        assert bus.get("pattern") == "observer", \
            f"pattern field lost or polluted: {bus.get('pattern')}"
        # 校验流程应通过（base 内部不强校验）
        import sys
        argv_save = sys.argv
        sys.argv = ["doc-format-check.py", tmp]
        try:
            m.main()
        except SystemExit as e:
            assert e.code == 0, "valid doc with nested base should pass"
        finally:
            sys.argv = argv_save
    print("PASS: test_inner_base_nested_dict_no_pollution")


def main():
    m = load_module()
    test_valid(m)
    test_invalid_role(m)
    test_invalid_protocol(m)
    test_anchor_holders_lt_2(m)
    test_inner_base_nested_dict_no_pollution(m)
    print("\nALL FORMAT-CHECK TESTS PASSED")


if __name__ == "__main__":
    main()
