#!/usr/bin/env python3
"""
doc-structure-import.py — 调用 doc-structure-extract.py 并将结果写入文档的 structure 字段

用法: python3 doc-structure-import.py <doc_path> <module_path> [project_root]

- doc_path:    目标文档文件路径（.md，含 YAML frontmatter）
- module_path: 源码模块目录路径（传给 doc-structure-extract.py）
- project_root: 可选，项目根目录（传给 doc-structure-extract.py）

输出: 成功时打印 "OK: <doc_path>"，失败时打印 "ERROR: ..." 并以非零退出
"""

import json
import os
import re
import subprocess
import sys


# 允许的 structure 一级键白名单（schema v4 扩展）
ALLOWED_STRUCTURE_KEYS = {
    "deps",
    "exports",
    "cross_module_contracts",
}


def run_extract(module_path, project_root, extra_args=None):
    script = os.path.join(os.path.dirname(__file__), "doc-structure-extract.py")
    cmd = [sys.executable, script, module_path]
    if project_root:
        cmd.append(project_root)
    if extra_args:
        cmd.extend(extra_args)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "doc-structure-extract.py failed")
    # stderr 可能含 truncation/cycle 警告，转发到当前 stderr
    if result.stderr.strip():
        print(result.stderr.strip(), file=sys.stderr)
    return json.loads(result.stdout)


def _yaml_scalar(v):
    """序列化标量为 JSON（兼容 yaml 字面量）。"""
    return json.dumps(v, ensure_ascii=False)


def _serialize_value(v, indent):
    """递归序列化值，indent 是该值所在层的缩进空格数。"""
    pad = " " * indent
    lines = []
    if isinstance(v, dict):
        if not v:
            return [f"{pad}{{}}"]
        for k, vv in v.items():
            if isinstance(vv, (dict, list)):
                if isinstance(vv, list) and not vv:
                    lines.append(f"{pad}{k}: []")
                elif isinstance(vv, dict) and not vv:
                    lines.append(f"{pad}{k}: {{}}")
                else:
                    lines.append(f"{pad}{k}:")
                    lines.extend(_serialize_value(vv, indent + 2))
            else:
                lines.append(f"{pad}{k}: {_yaml_scalar(vv)}")
    elif isinstance(v, list):
        if not v:
            return [f"{pad}[]"]
        for elem in v:
            if isinstance(elem, dict):
                # list-of-dict：第一项 inline，其余字段缩进
                if not elem:
                    lines.append(f"{pad}- {{}}")
                    continue
                items = list(elem.items())
                first_k, first_v = items[0]
                if isinstance(first_v, (dict, list)):
                    lines.append(f"{pad}- {first_k}:")
                    lines.extend(_serialize_value(first_v, indent + 4))
                else:
                    lines.append(f"{pad}- {first_k}: {_yaml_scalar(first_v)}")
                for k, vv in items[1:]:
                    if isinstance(vv, list):
                        if not vv:
                            lines.append(f"{pad}  {k}: []")
                        else:
                            lines.append(f"{pad}  {k}:")
                            lines.extend(_serialize_value(vv, indent + 4))
                    elif isinstance(vv, dict):
                        if not vv:
                            lines.append(f"{pad}  {k}: {{}}")
                        else:
                            lines.append(f"{pad}  {k}:")
                            lines.extend(_serialize_value(vv, indent + 4))
                    else:
                        lines.append(f"{pad}  {k}: {_yaml_scalar(vv)}")
            else:
                lines.append(f"{pad}- {_yaml_scalar(elem)}")
    else:
        lines.append(f"{pad}{_yaml_scalar(v)}")
    return lines


def build_structure_yaml(data):
    """将 structure dict 序列化为 YAML 块（缩进2空格）。

    泛化处理：遍历输入 dict 全部一级键，对未在白名单内的键发出 stderr 警告。
    """
    # 检查未知键
    unknown = [k for k in data.keys() if k not in ALLOWED_STRUCTURE_KEYS]
    if unknown:
        print(f"WARNING: unknown structure keys: {unknown}", file=sys.stderr)

    sections = []
    # 按白名单顺序输出（保证稳定 diff），未知键追加在末尾
    ordered_keys = [k for k in (
        "deps", "exports", "cross_module_contracts",
    ) if k in data]
    ordered_keys += [k for k in data.keys() if k not in ALLOWED_STRUCTURE_KEYS]

    for key in ordered_keys:
        value = data[key]
        if isinstance(value, list):
            if not value:
                sections.append(f"  {key}: []")
            else:
                sections.append(f"  {key}:")
                sections.extend(_serialize_value(value, 4))
        elif isinstance(value, dict):
            if not value:
                sections.append(f"  {key}: {{}}")
            else:
                sections.append(f"  {key}:")
                sections.extend(_serialize_value(value, 4))
        else:
            sections.append(f"  {key}: {_yaml_scalar(value)}")
    return "structure:\n" + "\n".join(sections)


def update_doc(doc_path, structure_yaml):
    with open(doc_path, "r", encoding="utf-8") as f:
        content = f.read()

    if not content.startswith("---"):
        raise ValueError("文档缺少 YAML frontmatter")

    end = content.find("---", 3)
    if end == -1:
        raise ValueError("YAML frontmatter 未闭合")

    yaml_block = content[3:end]

    # 移除已有的 structure 块（多行）
    yaml_block = re.sub(
        r"\nstructure:(?:\n(?:[ \t]+[^\n]*))*",
        "",
        yaml_block,
    )

    # 追加新的 structure 块（在 frontmatter 末尾）
    yaml_block = yaml_block.rstrip("\n") + "\n" + structure_yaml + "\n"

    new_content = "---" + yaml_block + "---" + content[end + 3:]

    with open(doc_path, "w", encoding="utf-8", newline="\n") as f:
        f.write(new_content)


def main():
    if len(sys.argv) < 3:
        print("用法: doc-structure-import.py <doc_path> <module_path> [project_root]", file=sys.stderr)
        sys.exit(1)

    doc_path = sys.argv[1]
    module_path = sys.argv[2]
    project_root = sys.argv[3] if len(sys.argv) > 3 else None

    if not os.path.isfile(doc_path):
        print(f"ERROR: 文档不存在: {doc_path}", file=sys.stderr)
        sys.exit(1)

    try:
        data = run_extract(module_path, project_root)
        structure_yaml = build_structure_yaml(data)
        update_doc(doc_path, structure_yaml)
        print(f"OK: {doc_path}")
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
