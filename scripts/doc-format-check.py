#!/usr/bin/env python3
"""
doc-format-check.py - Validate yaml schema compliance of doc files.

Usage: python3 ~/.agent-docs/scripts/doc-format-check.py [project_root] [--docs-dir <dir>]

Checks:
  - Required fields present (schema_version, agent_load, repo, origin_host, owner, name, branch, commit)
  - schema_version value matches current version
  - commit is 10-40 char hex
  - No duplicate (origin_host, owner, name, branch) four-tuples among active docs
  - Archived docs must have: archived_at, archived_reason, origin_path_in_main
  - structure field schema (deps / exports / inner / cross_module_contracts / data_flow_anchors)

Output: one issue per line, or "ALL_PASS" if clean.

Note: 由于不依赖 PyYAML，本脚本采用启发式 parser 解析 yaml frontmatter；
仅校验关键值约束，复杂嵌套用宽松规则。
"""

import os
import re
import sys


REQUIRED_FIELDS = ["schema_version", "agent_load", "repo", "origin_host", "owner", "name", "branch", "commit"]
ARCHIVED_REQUIRED_FIELDS = ["archived_at", "archived_reason", "origin_path_in_main"]
VALID_ARCHIVED_REASONS = [
    "removed-from-gitmodules",
    "imported-from-other-project",
]
CURRENT_SCHEMA_VERSION = "3"

# structure 字段允许的取值
VALID_DEPS_ROLES = {"framework", "utility", "sibling", "resource", "unknown"}
VALID_DEPS_GRANULARITY = {"file", "module"}
VALID_EXPORTS_VIS = {"public", "protected", "internal"}
VALID_INNER_PATTERN_V1 = {"singleton", "observer"}  # v1 严格枚举；其他值警告但不拒绝
VALID_CONTRACT_PROTOCOLS = {
    "delegate", "callback", "event", "message", "rpc", "inherit",
    "ecs", "di", "observer-bus", "state-machine",
}
VALID_CONTRACT_DIRECTIONS = {"inbound", "outbound", "bidirectional"}


def extract_meta_raw(filepath):
    """读取 yaml frontmatter 原始文本块。"""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return None
    if not content.startswith("---"):
        return None
    end = content.find("---", 3)
    if end == -1:
        return None
    return content[3:end]


def extract_meta(filepath):
    """启发式提取 yaml 顶层标量字段。复杂嵌套（structure 等）单独读 raw 文本。"""
    raw = extract_meta_raw(filepath)
    if raw is None:
        return None
    meta = {}
    current_list_key = None
    for line in raw.split("\n"):
        # 顶层字段必须无前导空格
        if line.startswith(" ") or line.startswith("\t"):
            current_list_key = None
            continue
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^([\w_]+):\s*(.*)$", stripped)
        if m:
            key = m.group(1)
            val = m.group(2).strip().strip('"').strip("'")
            if val == "":
                meta[key] = []
                current_list_key = key
            else:
                meta[key] = val
                current_list_key = None
    return meta


def parse_structure_block(raw_yaml):
    """解析 structure 块，返回 dict（未知键也保留）。

    极简解析器：识别 list-of-dict 模式，足以支撑校验。不构造完整 yaml。

    修 P0-3：对 list-item 内的嵌套 dict（如 `inner[].base: { extends: [...] }`），
    整段跳过，避免把嵌套 dict 的子键和子 list 元素污染到同级字段。
    本解析器不需要校验 `base` 内部，"宽松通过"由手册明确。
    """
    if raw_yaml is None:
        return None
    lines = raw_yaml.split("\n")
    # 找到 structure: 起始行
    start = None
    for i, ln in enumerate(lines):
        if ln.startswith("structure:"):
            start = i
            break
    if start is None:
        return None

    # 提取 structure 块（直到下一行非缩进且非空）
    block = []
    for ln in lines[start + 1:]:
        if ln.startswith(" ") or ln.startswith("\t") or ln.strip() == "":
            block.append(ln)
        else:
            break

    # 解析子键
    result = {}
    current_key = None
    current_items = None
    current_item = None  # 当前正在拼的 dict item
    skipping_nested_dict = False  # P0-3: 跳过 list-item 内嵌套 dict 直至缩进恢复
    nested_dict_indent = -1  # 嵌套 dict 起始的缩进列数（空格数）

    def indent_of(s):
        return len(s) - len(s.lstrip(" "))

    for ln in block:
        if not ln.strip():
            # 空行不影响 skip 状态
            continue

        # 跳过模式：检测缩进是否回到了 nested_dict_indent 或更浅
        if skipping_nested_dict:
            if indent_of(ln) <= nested_dict_indent:
                skipping_nested_dict = False
                # 不 continue，下面继续按正常分支处理本行
            else:
                # 仍在嵌套 dict 内，跳过
                continue

        stripped = ln.rstrip()
        # 二级键: "  key:" 或 "  key: []" 或 "  key: value"
        m_key = re.match(r"^  ([\w_]+):\s*(.*)$", stripped)
        if m_key:
            current_key = m_key.group(1)
            tail = m_key.group(2).strip()
            if tail == "[]":
                result[current_key] = []
                current_items = None
                current_item = None
            elif tail == "":
                result[current_key] = []
                current_items = result[current_key]
                current_item = None
            else:
                # 标量值（罕见，schema 不期待）
                result[current_key] = tail.strip('"').strip("'")
                current_items = None
                current_item = None
            continue

        # list 项起始: "    - key: value"
        m_item_start = re.match(r"^    - ([\w_]+):\s*(.*)$", stripped)
        if m_item_start and current_items is not None:
            k = m_item_start.group(1)
            v = m_item_start.group(2).strip()
            current_item = {}
            if v == "[]":
                current_item[k] = []
            elif v == "":
                current_item[k] = []  # 待 nested list 填
            else:
                current_item[k] = v.strip('"').strip("'")
            current_items.append(current_item)
            continue

        # list 项后续字段: "      key: value"
        m_item_field = re.match(r"^      ([\w_]+):\s*(.*)$", stripped)
        if m_item_field and current_item is not None:
            k = m_item_field.group(1)
            v = m_item_field.group(2).strip()
            if v == "":
                # P0-3: key 后无值 → 可能是嵌套 list（下行 "- value"）或嵌套 dict（下行 "key:"）
                # 探测后一行；当前简化：先记录为空 list，nested 元素塞入逻辑会接收
                # 若实际是嵌套 dict（如 base: { extends, implements }），下面遇到
                # 非"- ..." 形式的更深缩进 key 行 → 触发 skip 模式
                current_item[k] = []
            elif v == "[]":
                current_item[k] = []
            else:
                current_item[k] = v.strip('"').strip("'")
            continue

        # nested list 元素 "        - value"
        m_nested = re.match(r"^( {6,})- (.*)$", stripped)
        if m_nested and current_item is not None:
            v = m_nested.group(2).strip().strip('"').strip("'")
            # 找到当前 item 中最后一个空 list 字段塞入
            for kk in reversed(list(current_item.keys())):
                if isinstance(current_item[kk], list):
                    current_item[kk].append(v)
                    break
            continue

        # P0-3: 更深缩进的非 "- " key 行（如 "        extends:"）→ 嵌套 dict
        # 进入 skip 模式直到缩进恢复到 ≤ 当前缩进
        m_nested_dict_key = re.match(r"^( {8,})([\w_]+):\s*", stripped)
        if m_nested_dict_key and current_item is not None:
            skipping_nested_dict = True
            nested_dict_indent = len(m_nested_dict_key.group(1)) - 2
            # 同时要把 current_item 中刚刚被错误初始化的空 list（base 字段）从 list 改为不存在
            # 因为下游 validate 不需要 base 内部，整体丢弃即可
            # 通过追踪上一次 m_item_field 的 key 来定位
            # 简化：保留为空 list，validate 跳过
            continue

    return result


def validate_structure(struct, fname, issues):
    """校验 structure 字段的子结构。"""
    if struct is None:
        return

    deps = struct.get("deps", [])
    if isinstance(deps, list):
        for i, d in enumerate(deps):
            if not isinstance(d, dict):
                continue
            role = d.get("role")
            if role and role not in VALID_DEPS_ROLES:
                issues.append(f"{fname}: STRUCTURE_DEPS[{i}]_INVALID_ROLE({role})")
            gran = d.get("granularity")
            if gran and gran not in VALID_DEPS_GRANULARITY:
                issues.append(f"{fname}: STRUCTURE_DEPS[{i}]_INVALID_GRANULARITY({gran})")

    exports = struct.get("exports", [])
    if isinstance(exports, list):
        for i, e in enumerate(exports):
            if not isinstance(e, dict):
                continue
            vis = e.get("vis")
            if vis and vis not in VALID_EXPORTS_VIS:
                issues.append(f"{fname}: STRUCTURE_EXPORTS[{i}]_INVALID_VIS({vis})")
            base = e.get("base")
            if base is not None and not isinstance(base, str):
                issues.append(f"{fname}: STRUCTURE_EXPORTS[{i}]_INVALID_BASE_TYPE")

    inner = struct.get("inner", [])
    if isinstance(inner, list):
        for i, n in enumerate(inner):
            if not isinstance(n, dict):
                continue
            pattern = n.get("pattern")
            if pattern and pattern not in VALID_INNER_PATTERN_V1:
                issues.append(f"{fname}: STRUCTURE_INNER[{i}]_UNKNOWN_PATTERN({pattern})  (warn-only)")
            # base 应为 dict {extends, implements} 或缺省。极简 parser 不解析嵌套 dict，
            # 这里宽松通过；嵌套结构由 import 脚本写入时保证形状。

    contracts = struct.get("cross_module_contracts", [])
    if isinstance(contracts, list):
        for i, c in enumerate(contracts):
            if not isinstance(c, dict):
                continue
            with_ = c.get("with")
            if not with_ or not isinstance(with_, str):
                issues.append(f"{fname}: STRUCTURE_CONTRACTS[{i}]_MISSING_WITH")
            proto = c.get("protocol")
            if proto and proto not in VALID_CONTRACT_PROTOCOLS:
                issues.append(f"{fname}: STRUCTURE_CONTRACTS[{i}]_INVALID_PROTOCOL({proto})")
            direction = c.get("direction")
            if direction and direction not in VALID_CONTRACT_DIRECTIONS:
                issues.append(f"{fname}: STRUCTURE_CONTRACTS[{i}]_INVALID_DIRECTION({direction})")

    anchors = struct.get("data_flow_anchors", [])
    if isinstance(anchors, list):
        for i, a in enumerate(anchors):
            if not isinstance(a, dict):
                continue
            name = a.get("name")
            if not name or not isinstance(name, str):
                issues.append(f"{fname}: STRUCTURE_ANCHORS[{i}]_MISSING_NAME")
            holders = a.get("holders")
            if not isinstance(holders, list) or len(holders) < 2:
                issues.append(f"{fname}: STRUCTURE_ANCHORS[{i}]_HOLDERS_LT_2")


def main():
    import argparse
    p = argparse.ArgumentParser()
    p.add_argument("project_root", nargs="?", default=None)
    p.add_argument("--docs-dir", default=None)
    args = p.parse_args()

    project_root = os.path.abspath(args.project_root or os.getcwd())
    docs_dir = args.docs_dir if args.docs_dir else os.path.join(project_root, ".agent-docs", "doc-library", "modules")

    if not os.path.isdir(docs_dir):
        print(f"ERROR: {docs_dir} not found")
        sys.exit(1)

    all_issues = []
    four_tuples = {}

    for fname in sorted(os.listdir(docs_dir)):
        if not fname.endswith(".md"):
            continue
        fpath = os.path.join(docs_dir, fname)
        meta = extract_meta(fpath)

        if meta is None:
            all_issues.append(f"{fname}: NO_YAML_FRONTMATTER")
            continue

        is_archived = meta.get("archived") == "true"

        # Required fields (common to all docs)
        for field in REQUIRED_FIELDS:
            if field not in meta or meta[field] is None or meta[field] == "":
                all_issues.append(f"{fname}: MISSING_FIELD({field})")

        # schema_version value check
        sv = meta.get("schema_version", "")
        if sv and str(sv) != CURRENT_SCHEMA_VERSION:
            all_issues.append(f"{fname}: OUTDATED_SCHEMA_VERSION({sv}, expected {CURRENT_SCHEMA_VERSION})")

        # Commit format
        commit = meta.get("commit", "")
        if commit and not re.match(r"^[0-9a-f]{10,40}$", str(commit)):
            all_issues.append(f"{fname}: INVALID_COMMIT({commit[:20]}...)")

        # Archived-specific checks
        if is_archived:
            for field in ARCHIVED_REQUIRED_FIELDS:
                if field not in meta or meta[field] is None or meta[field] == "":
                    all_issues.append(f"{fname}: ARCHIVED_MISSING_FIELD({field})")

            archived_at = meta.get("archived_at", "")
            if archived_at and not re.match(r"^\d{4}-\d{2}-\d{2}$", archived_at):
                all_issues.append(f"{fname}: INVALID_ARCHIVED_AT({archived_at})")

            archived_reason = meta.get("archived_reason", "")
            if archived_reason:
                valid = False
                for prefix in VALID_ARCHIVED_REASONS:
                    if archived_reason.startswith(prefix):
                        valid = True
                        break
                if not valid and not archived_reason.startswith("renamed-to-") and not archived_reason.startswith("merged-into-"):
                    all_issues.append(f"{fname}: INVALID_ARCHIVED_REASON({archived_reason})")

        # structure field check (schema v3+, only active docs)
        if str(sv) == CURRENT_SCHEMA_VERSION and not is_archived:
            raw = extract_meta_raw(fpath)
            struct = parse_structure_block(raw)
            if struct is None:
                all_issues.append(f"{fname}: MISSING_STRUCTURE")
            else:
                validate_structure(struct, fname, all_issues)

        # Four-tuple uniqueness (only among active docs)
        if not is_archived:
            key = (
                meta.get("origin_host", ""),
                meta.get("owner", ""),
                meta.get("name", ""),
                meta.get("branch", ""),
            )
            if key in four_tuples:
                all_issues.append(f"{fname}: DUPLICATE_FOUR_TUPLE (conflicts with {four_tuples[key]})")
            else:
                four_tuples[key] = fname

    if all_issues:
        for issue in all_issues:
            print(issue)
        sys.exit(1)
    else:
        print("ALL_PASS")
        sys.exit(0)


if __name__ == "__main__":
    main()
