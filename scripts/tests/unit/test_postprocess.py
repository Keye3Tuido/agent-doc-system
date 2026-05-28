#!/usr/bin/env python3
"""测试 doc-structure-extract 的后处理层（不依赖 tree-sitter）。"""

import importlib.util
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
SCRIPT = os.path.join(ROOT, "scripts", "doc-structure-extract.py")


def load_module():
    """加载 extract 脚本作为 module。tree-sitter 缺失时仍然能 import 后处理函数。"""
    spec = importlib.util.spec_from_file_location("extract", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except SystemExit:
        # tree-sitter 未装时模块顶层会 sys.exit；后处理函数无法访问
        # 此时跳过测试
        print("SKIP: tree-sitter not installed; skipping postprocess tests")
        sys.exit(0)
    return mod


def test_role_classification(m):
    raw = {
        "deps": [
            {"m": "react", "use": ["useState"], "type": "import"},
            {"m": "lodash", "use": [], "type": "import"},
            {"m": "core/utils", "use": ["Logger"], "type": "import"},
            {"m": "Resources/config.json", "use": [], "type": "import"},
            {"m": "./internal", "use": [], "type": "import"},
        ],
        "exports": [],
        "inner": [],
    }
    out = m.postprocess_structure(raw, rel_module="src/myapp", project_root="/tmp", submodule_paths=set())
    by_m = {d["m"]: d["role"] for d in out["deps"]}
    assert by_m.get("react") == "utility", f"react should be utility, got {by_m.get('react')}"
    assert by_m.get("lodash") == "utility"
    assert by_m.get("core") == "framework", f"core should be framework, got {by_m.get('core')}"
    assert by_m.get("Resources") == "resource"
    assert "./internal" not in by_m, "relative ./internal should be dropped"
    print("PASS: test_role_classification")


def test_pattern_recognition(m):
    raw = {
        "deps": [],
        "exports": [],
        "inner": [
            {"n": "GameSingleton", "t": "class", "has": ["getInstance", "reset"]},
            {"n": "EventBus", "t": "class", "has": ["subscribe", "emit", "on"]},
            {"n": "Plain", "t": "class", "has": ["doStuff"]},
        ],
    }
    out = m.postprocess_structure(raw, rel_module="x", project_root="/tmp", submodule_paths=set())
    by_n = {n["n"]: n.get("pattern") for n in out["inner"]}
    assert by_n["GameSingleton"] == "singleton"
    assert by_n["EventBus"] == "observer"
    assert by_n["Plain"] is None
    print("PASS: test_pattern_recognition")


def test_module_aggregation(m):
    """同一目标模块的多次 import → 单条 dep + use 频次聚合。"""
    raw = {
        "deps": [
            {"m": "react", "use": ["useState"], "type": "import"},
            {"m": "react", "use": ["useEffect", "useState"], "type": "import"},
            {"m": "react", "use": ["useState"], "type": "import"},
        ],
        "exports": [],
        "inner": [],
    }
    out = m.postprocess_structure(raw, rel_module="x", project_root="/tmp", submodule_paths=set())
    react_deps = [d for d in out["deps"] if d["m"] == "react"]
    assert len(react_deps) == 1, f"expected 1 react entry, got {len(react_deps)}"
    use = react_deps[0]["use"]
    # useState 应在 useEffect 前（频次更高）
    assert use[0] == "useState", f"useState should rank first by freq, got {use}"
    print("PASS: test_module_aggregation")


def test_default_vis(m):
    raw = {
        "deps": [],
        "exports": [{"n": "Foo", "t": "class", "path": "src/foo.ts"}],
        "inner": [],
    }
    out = m.postprocess_structure(raw, rel_module="x", project_root="/tmp", submodule_paths=set())
    assert out["exports"][0].get("vis") == "public"
    print("PASS: test_default_vis")


def test_granularity_marker(m):
    raw = {"deps": [{"m": "react", "use": [], "type": "import"}], "exports": [], "inner": []}
    out = m.postprocess_structure(raw, rel_module="x", project_root="/tmp", submodule_paths=set())
    assert out["deps"][0]["granularity"] == "module"
    print("PASS: test_granularity_marker")


def test_unknown_dep_preserved(m):
    """P0-1/P0-4 修复：未匹配任何 hint/submodule/外部包前缀的 dep 应保留为 unknown 而非丢弃。"""
    raw = {
        "deps": [
            {"m": "Libraries/Bar", "use": ["BarApi"], "type": "include"},
            {"m": "commander", "use": ["program"], "type": "import"},  # 未在外部前缀白名单
            {"m": "Foo/Bar.h", "use": [], "type": "include"},
        ],
        "exports": [],
        "inner": [],
    }
    out = m.postprocess_structure(raw, rel_module="src/myapp", project_root="/tmp", submodule_paths=set())
    targets = {d["m"] for d in out["deps"]}
    # 全部应保留
    assert "Libraries/Bar" in targets, f"Libraries/Bar dropped, got {targets}"
    assert "commander" in targets, f"commander dropped, got {targets}"
    assert "Foo/Bar.h" in targets, f"Foo/Bar.h dropped, got {targets}"
    # role 全部为 unknown（无 hint 命中）
    by_m = {d["m"]: d["role"] for d in out["deps"]}
    assert by_m["Libraries/Bar"] == "unknown"
    assert by_m["commander"] == "unknown"
    assert by_m["Foo/Bar.h"] == "unknown"
    print("PASS: test_unknown_dep_preserved")


def test_submodule_match_for_bare_path(m):
    """裸路径形式（include 字面量）应能命中 submodule_paths → sibling。"""
    raw = {
        "deps": [
            {"m": "Libraries/Bar/Foo.h", "use": [], "type": "include"},
        ],
        "exports": [],
        "inner": [],
    }
    out = m.postprocess_structure(
        raw, rel_module="Libraries/myself", project_root="/tmp",
        submodule_paths={"Libraries/Bar", "Libraries/myself"},
    )
    by_m = {d["m"]: d["role"] for d in out["deps"]}
    assert by_m.get("Libraries/Bar") == "sibling", f"expected sibling, got {by_m}"
    print("PASS: test_submodule_match_for_bare_path")


def test_self_module_dropped(m):
    """裸路径或相对路径解析到自身模块应丢弃。"""
    raw = {
        "deps": [
            {"m": "Libraries/me/inner.h", "use": [], "type": "include"},
            {"m": "./inner", "use": [], "type": "import"},
        ],
        "exports": [],
        "inner": [],
    }
    out = m.postprocess_structure(
        raw, rel_module="Libraries/me", project_root="/tmp",
        submodule_paths={"Libraries/me"},
    )
    targets = {d["m"] for d in out["deps"]}
    assert "Libraries/me/inner.h" not in targets
    assert "./inner" not in targets
    print("PASS: test_self_module_dropped")


def main():
    m = load_module()
    test_role_classification(m)
    test_pattern_recognition(m)
    test_module_aggregation(m)
    test_default_vis(m)
    test_granularity_marker(m)
    test_unknown_dep_preserved(m)
    test_submodule_match_for_bare_path(m)
    test_self_module_dropped(m)
    print("\nALL POSTPROCESS TESTS PASSED")


if __name__ == "__main__":
    main()
