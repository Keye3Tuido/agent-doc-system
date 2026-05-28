#!/usr/bin/env python3
"""测试 doc-structure-import 的 yaml 序列化。"""

import importlib.util
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "doc-structure-import.py")


def load_module():
    spec = importlib.util.spec_from_file_location("imp", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_full_5_keys(m):
    data = {
        "deps": [{"m": "react", "use": ["useState"], "type": "import",
                   "role": "utility", "granularity": "module"}],
        "exports": [{"n": "Foo", "t": "class", "path": "src/foo.ts", "vis": "public"}],
        "inner": [{"n": "Bus", "t": "class", "has": ["sub", "emit"],
                    "base": {"extends": ["Base"], "implements": ["IBus"]},
                    "pattern": "observer"}],
        "cross_module_contracts": [{"with": "modules/bar", "protocol": "delegate",
                                     "interface": "IBarDelegate", "direction": "outbound"}],
        "data_flow_anchors": [{"name": "GameState",
                                "holders": ["core/state", "modules/ui"]}],
    }
    out = m.build_structure_yaml(data)
    assert "structure:\n" in out
    assert "deps:" in out and "exports:" in out and "inner:" in out
    assert "cross_module_contracts:" in out and "data_flow_anchors:" in out
    assert '"useState"' in out
    assert "extends:" in out and "implements:" in out
    print("PASS: test_full_5_keys")


def test_unknown_keys_warning(m, capsys=None):
    """传入未知键时 stderr 应出 WARNING（人工确认或抑制 stderr）。"""
    import sys, io
    err = io.StringIO()
    saved = sys.stderr
    sys.stderr = err
    try:
        data = {"deps": [], "exports": [], "inner": [], "weird_key": []}
        m.build_structure_yaml(data)
    finally:
        sys.stderr = saved
    assert "WARNING" in err.getvalue() and "weird_key" in err.getvalue()
    print("PASS: test_unknown_keys_warning")


def test_empty_lists(m):
    data = {"deps": [], "exports": [], "inner": [],
            "cross_module_contracts": [], "data_flow_anchors": []}
    out = m.build_structure_yaml(data)
    assert "deps: []" in out
    assert "data_flow_anchors: []" in out
    print("PASS: test_empty_lists")


def main():
    m = load_module()
    test_full_5_keys(m)
    test_unknown_keys_warning(m)
    test_empty_lists(m)
    print("\nALL SERIALIZER TESTS PASSED")


if __name__ == "__main__":
    main()
