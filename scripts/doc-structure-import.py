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


def run_extract(module_path, project_root):
    script = os.path.join(os.path.dirname(__file__), "doc-structure-extract.py")
    cmd = [sys.executable, script, module_path]
    if project_root:
        cmd.append(project_root)
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "doc-structure-extract.py failed")
    return json.loads(result.stdout)


def build_structure_yaml(data):
    """将 structure dict 序列化为 YAML 块（缩进2空格）。"""
    def item_to_yaml(item, indent):
        pad = " " * indent
        lines = []
        for k, v in item.items():
            if isinstance(v, list):
                if not v:
                    lines.append(f"{pad}{k}: []")
                else:
                    lines.append(f"{pad}{k}:")
                    for elem in v:
                        lines.append(f"{pad}  - {json.dumps(elem, ensure_ascii=False)}")
            else:
                lines.append(f"{pad}{k}: {json.dumps(v, ensure_ascii=False)}")
        return "\n".join(lines)

    sections = []
    for key in ("deps", "exports", "inner"):
        items = data.get(key, [])
        if not items:
            sections.append(f"  {key}: []")
        else:
            sections.append(f"  {key}:")
            for item in items:
                first_key = next(iter(item))
                first_val = item[first_key]
                rest = {k: v for k, v in item.items() if k != first_key}
                line = f"    - {first_key}: {json.dumps(first_val, ensure_ascii=False)}"
                sections.append(line)
                for k, v in rest.items():
                    if isinstance(v, list):
                        if not v:
                            sections.append(f"      {k}: []")
                        else:
                            sections.append(f"      {k}:")
                            for elem in v:
                                sections.append(f"        - {json.dumps(elem, ensure_ascii=False)}")
                    else:
                        sections.append(f"      {k}: {json.dumps(v, ensure_ascii=False)}")
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
