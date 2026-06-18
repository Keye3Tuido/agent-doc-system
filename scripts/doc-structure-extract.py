#!/usr/bin/env python3
"""
doc-structure-extract.py — 从源码提取结构化关系数据（deps/exports）

用法: python3 doc-structure-extract.py <module_path> [project_root]

依赖（必需）: pip install tree-sitter
依赖（可选）: pip install tree-sitter-python tree-sitter-javascript tree-sitter-go tree-sitter-java tree-sitter-rust tree-sitter-cpp

输出: JSON格式的structure数据到stdout
"""

import os
import sys
import json
import glob
from pathlib import Path

# 动态加载各语言的tree-sitter支持
LANGUAGES = {}

try:
    from tree_sitter import Language, Parser
except ImportError:
    print("ERROR: tree-sitter not installed. Run: pip install tree-sitter", file=sys.stderr)
    sys.exit(1)

# Python
try:
    import tree_sitter_python
    LANGUAGES['python'] = Language(tree_sitter_python.language())
except ImportError:
    pass

# JavaScript/TypeScript
try:
    import tree_sitter_javascript
    LANGUAGES['javascript'] = Language(tree_sitter_javascript.language())
    LANGUAGES['typescript'] = LANGUAGES['javascript']
except ImportError:
    pass

# Go
try:
    import tree_sitter_go
    LANGUAGES['go'] = Language(tree_sitter_go.language())
except ImportError:
    pass

# Java
try:
    import tree_sitter_java
    LANGUAGES['java'] = Language(tree_sitter_java.language())
except ImportError:
    pass

# Rust
try:
    import tree_sitter_rust
    LANGUAGES['rust'] = Language(tree_sitter_rust.language())
except ImportError:
    pass

# C/C++
try:
    import tree_sitter_cpp
    LANGUAGES['cpp'] = Language(tree_sitter_cpp.language())
    LANGUAGES['c'] = LANGUAGES['cpp']
except ImportError:
    pass

if not LANGUAGES:
    print("ERROR: No language parsers installed. Install at least one: pip install tree-sitter-python tree-sitter-javascript", file=sys.stderr)
    sys.exit(1)


def detect_language(file_path):
    """根据文件扩展名检测语言"""
    ext = Path(file_path).suffix.lower()
    lang_map = {
        '.ts': 'typescript',
        '.tsx': 'typescript',
        '.js': 'javascript',
        '.jsx': 'javascript',
        '.py': 'python',
        '.go': 'go',
        '.java': 'java',
        '.rs': 'rust',
        '.cpp': 'cpp',
        '.cc': 'cpp',
        '.cxx': 'cpp',
        '.c': 'c',
        '.h': 'cpp',  # .h通常用于C++头文件
        '.hpp': 'cpp',
        '.hxx': 'cpp',
        '.hh': 'cpp',
    }
    return lang_map.get(ext)


def find_source_files(module_path, max_files=200, max_file_size=1024*1024):
    """查找模块中的源码文件（限制数量避免过载）。

    修 P1-7：先全量收集 → 过滤 → 末尾截断；不再按 pattern 提前 break，
    避免前面的语言把 max_files 配额抢光导致后面的语言一个不扫。
    """
    patterns = ['**/*.ts', '**/*.tsx', '**/*.js', '**/*.jsx', '**/*.py',
                '**/*.go', '**/*.java', '**/*.rs', '**/*.cpp', '**/*.cc',
                '**/*.cxx', '**/*.c', '**/*.h', '**/*.hpp']

    all_files = []
    for pattern in patterns:
        all_files.extend(glob.glob(os.path.join(module_path, pattern), recursive=True))

    # 排除常见的非源码目录（使用路径组件匹配）
    exclude_dirs = {'node_modules', 'dist', 'build', '__pycache__', '.git', 'vendor', 'target', 'out'}
    filtered = []
    for f in all_files:
        if os.path.islink(f):
            continue
        if not os.path.isfile(f):
            continue
        if os.path.getsize(f) > max_file_size:
            continue
        if any(ex in Path(f).parts for ex in exclude_dirs):
            continue
        filtered.append(f)

    # 优先头文件（C/C++ 头文件含更多 export 信息），然后 TS/.h 之外按字典序
    def sort_key(p):
        ext = Path(p).suffix.lower()
        priority = 0 if ext in ('.h', '.hpp', '.hxx', '.hh') else 1
        return (priority, p)
    filtered.sort(key=sort_key)

    return filtered[:max_files]


def extract_typescript_structure(source_code, file_path):
    """使用tree-sitter提取TypeScript/JavaScript结构"""
    if 'javascript' not in LANGUAGES:
        return [], [], []
    parser = Parser(LANGUAGES['javascript'])
    source_bytes = bytes(source_code, 'utf8')
    tree = parser.parse(source_bytes)
    root = tree.root_node

    deps = []
    exports = []
    inner = []
    seen_deps = set()
    seen_exports = set()

    def visit_node(node):
        # 提取import语句
        if node.type == 'import_statement':
            # import { x, y } from 'module'
            source_node = node.child_by_field_name('source')
            if source_node:
                module = source_bytes[source_node.start_byte:source_node.end_byte].decode('utf8').strip('"\'')
                if not module.startswith('.'):  # 只记录外部依赖
                    imports = []
                    for child in node.children:
                        if child.type == 'import_clause':
                            for spec in child.children:
                                if spec.type == 'named_imports':
                                    for imp in spec.children:
                                        if imp.type == 'import_specifier':
                                            name_node = imp.child_by_field_name('name')
                                            if name_node:
                                                imports.append(source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8'))
                    key = (module, tuple(sorted(imports)))
                    if key not in seen_deps:
                        deps.append({'m': module, 'use': imports, 'type': 'import'})
                        seen_deps.add(key)

        # 提取export声明
        elif node.type in ['export_statement', 'export_declaration']:
            for child in node.children:
                if child.type in ['class_declaration', 'function_declaration', 'lexical_declaration']:
                    name_node = child.child_by_field_name('name')
                    if name_node:
                        name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                        t = 'class' if child.type == 'class_declaration' else 'function'
                        key = (name, t)
                        if key not in seen_exports:
                            exports.append({'n': name, 't': t, 'path': file_path})
                            seen_exports.add(key)

        # 提取类的内部结构
        elif node.type == 'class_declaration':
            name_node = node.child_by_field_name('name')
            if name_node:
                class_name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                methods = []
                body = node.child_by_field_name('body')
                if body:
                    for member in body.children:
                        if member.type == 'method_definition':
                            method_name_node = member.child_by_field_name('name')
                            if method_name_node:
                                method_name = source_bytes[method_name_node.start_byte:method_name_node.end_byte].decode('utf8')
                                if method_name != 'constructor':
                                    methods.append(method_name)
                if methods:
                    inner.append({'n': class_name, 't': 'class', 'has': methods[:10]})

        for child in node.children:
            visit_node(child)

    visit_node(root)
    return deps, exports, inner


def extract_python_structure(source_code, file_path):
    """使用tree-sitter提取Python结构

    exports: 优先取 __all__ 中的符号；无 __all__ 时取顶层非下划线符号。
    """
    if 'python' not in LANGUAGES:
        return [], [], []
    parser = Parser(LANGUAGES['python'])
    source_bytes = bytes(source_code, 'utf8')
    tree = parser.parse(source_bytes)
    root = tree.root_node

    deps = []
    exports = []
    inner = []
    seen_deps = set()
    seen_exports = set()

    # 第一遍：扫 __all__
    all_whitelist = None
    for child in root.children:
        if child.type == 'expression_statement':
            for sub in child.children:
                if sub.type == 'assignment':
                    left = sub.child_by_field_name('left')
                    right = sub.child_by_field_name('right')
                    if left and right and source_bytes[left.start_byte:left.end_byte].decode('utf8') == '__all__':
                        all_whitelist = set()
                        # right 是 list 字面量
                        for c in right.children:
                            if c.type == 'string':
                                s = source_bytes[c.start_byte:c.end_byte].decode('utf8').strip('"\'')
                                all_whitelist.add(s)

    def is_exported(name):
        if all_whitelist is not None:
            return name in all_whitelist
        return not name.startswith('_')

    def visit_node(node):
        # 提取import语句
        if node.type == 'import_statement':
            # import module
            for child in node.children:
                if child.type == 'dotted_name':
                    module = source_bytes[child.start_byte:child.end_byte].decode('utf8')
                    key = (module, ())
                    if key not in seen_deps:
                        deps.append({'m': module, 'use': [], 'type': 'import'})
                        seen_deps.add(key)

        elif node.type == 'import_from_statement':
            # from module import x, y
            module = None
            module_start = None
            imports = []

            # 提取模块名（第一个dotted_name或relative_import）
            for child in node.children:
                if child.type == 'dotted_name':
                    module = source_bytes[child.start_byte:child.end_byte].decode('utf8')
                    module_start = child.start_byte
                    break
                elif child.type == 'relative_import':
                    # 相对导入，如 from . import x
                    module = source_bytes[child.start_byte:child.end_byte].decode('utf8')
                    module_start = child.start_byte
                    break

            # 提取导入的符号
            for child in node.children:
                if child.type == 'aliased_import':
                    name_node = child.child_by_field_name('name')
                    if name_node:
                        imports.append(source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8'))
                elif child.type == 'dotted_name' and child.start_byte != module_start:
                    # 简单导入（非aliased），排除模块名本身
                    imports.append(source_bytes[child.start_byte:child.end_byte].decode('utf8'))
                elif child.type == 'wildcard_import':
                    # 通配符导入
                    imports.append('*')

            if module:
                key = (module, tuple(sorted(imports)))
                if key not in seen_deps:
                    deps.append({'m': module, 'use': imports, 'type': 'import'})
                    seen_deps.add(key)

        # 提取顶层类和函数（作为exports）
        elif node.type == 'class_definition' and node.parent.type == 'module':
            name_node = node.child_by_field_name('name')
            if name_node:
                name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                if is_exported(name):  # __all__ 优先；无则顶层公开符号
                    key = (name, 'class')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'class', 'path': file_path})
                        seen_exports.add(key)

                    # 提取类的方法（inner）
                    methods = []
                    body = node.child_by_field_name('body')
                    if body:
                        for child in body.children:
                            if child.type == 'function_definition':
                                method_name_node = child.child_by_field_name('name')
                                if method_name_node:
                                    method_name = source_bytes[method_name_node.start_byte:method_name_node.end_byte].decode('utf8')
                                    if not method_name.startswith('_'):
                                        methods.append(method_name)
                    if methods:
                        inner.append({'n': name, 't': 'class', 'has': methods[:10]})

        elif node.type == 'function_definition' and node.parent.type == 'module':
            name_node = node.child_by_field_name('name')
            if name_node:
                name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                if is_exported(name):
                    key = (name, 'function')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'function', 'path': file_path})
                        seen_exports.add(key)

        for child in node.children:
            visit_node(child)

    visit_node(root)
    return deps, exports, inner


def extract_cpp_structure(source_code, file_path):
    """使用tree-sitter提取C/C++结构

    exports: 仅在头文件（.h/.hpp/.hxx/.hh）中提取，避免捕获实现文件中的内部函数。
    deps: 所有文件均提取。
    inner: 仅在头文件中提取（声明位置）。
    """
    if 'cpp' not in LANGUAGES:
        return [], [], []
    is_header = Path(file_path).suffix.lower() in ('.h', '.hpp', '.hxx', '.hh')
    parser = Parser(LANGUAGES['cpp'])
    source_bytes = bytes(source_code, 'utf8')
    tree = parser.parse(source_bytes)
    root = tree.root_node

    deps = []
    exports = []
    inner = []
    seen_deps = set()
    seen_exports = set()

    def visit_node(node):
        # 提取#include语句（所有文件）
        if node.type == 'preproc_include':
            for child in node.children:
                if child.type in ['string_literal', 'system_lib_string']:
                    path = source_bytes[child.start_byte:child.end_byte].decode('utf8').strip('"<>')
                    if path not in seen_deps:
                        deps.append({'m': path, 'use': [], 'type': 'include'})
                        seen_deps.add(path)

        # 提取函数定义（仅头文件中的声明视为 export；实现文件跳过）
        elif node.type == 'function_definition' and is_header:
            declarator = node.child_by_field_name('declarator')
            if declarator:
                name = None
                if declarator.type == 'function_declarator':
                    for child in declarator.children:
                        if child.type == 'identifier':
                            name = source_bytes[child.start_byte:child.end_byte].decode('utf8')
                            break
                elif declarator.type == 'identifier':
                    name = source_bytes[declarator.start_byte:declarator.end_byte].decode('utf8')

                if name:
                    key = (name, 'function')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'function', 'path': file_path})
                        seen_exports.add(key)

        # 提取类定义（仅头文件中的类声明）
        elif node.type == 'class_specifier' and is_header:
            name_node = node.child_by_field_name('name')
            if name_node:
                name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                key = (name, 'class')
                if key not in seen_exports:
                    exports.append({'n': name, 't': 'class', 'path': file_path})
                    seen_exports.add(key)

                methods = []
                body = node.child_by_field_name('body')
                if body:
                    is_public = False
                    for child in body.children:
                        if child.type == 'access_specifier':
                            spec_text = source_bytes[child.start_byte:child.end_byte].decode('utf8')
                            is_public = 'public' in spec_text
                        elif child.type == 'function_definition' and is_public:
                            declarator = child.child_by_field_name('declarator')
                            if declarator:
                                method_name = None
                                if declarator.type == 'function_declarator':
                                    for dc in declarator.children:
                                        if dc.type == 'field_identifier' or dc.type == 'identifier':
                                            method_name = source_bytes[dc.start_byte:dc.end_byte].decode('utf8')
                                            break
                                if method_name:
                                    methods.append(method_name)
                if methods:
                    inner.append({'n': name, 't': 'class', 'has': methods[:10]})

        # 提取struct定义（仅头文件）
        elif node.type == 'struct_specifier' and is_header:
            name_node = node.child_by_field_name('name')
            if name_node:
                name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                key = (name, 'struct')
                if key not in seen_exports:
                    exports.append({'n': name, 't': 'struct', 'path': file_path})
                    seen_exports.add(key)

        for child in node.children:
            visit_node(child)

    visit_node(root)
    return deps, exports, inner


def extract_rust_structure(source_code, file_path):
    """使用tree-sitter提取Rust结构"""
    if 'rust' not in LANGUAGES:
        return [], [], []
    parser = Parser(LANGUAGES['rust'])
    source_bytes = bytes(source_code, 'utf8')
    tree = parser.parse(source_bytes)
    root = tree.root_node

    deps = []
    exports = []
    inner = []
    seen_deps = set()
    seen_exports = set()

    def visit_node(node):
        # 提取use语句
        if node.type == 'use_declaration':
            for child in node.children:
                if child.type in ['scoped_identifier', 'identifier', 'use_wildcard']:
                    path = source_bytes[child.start_byte:child.end_byte].decode('utf8')
                    if path not in seen_deps:
                        deps.append({'m': path, 'use': [], 'type': 'use'})
                        seen_deps.add(path)

        # 提取pub函数
        elif node.type == 'function_item':
            is_pub = False
            for child in node.children:
                if child.type == 'visibility_modifier':
                    is_pub = True
                    break

            if is_pub:
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                    key = (name, 'function')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'function', 'path': file_path})
                        seen_exports.add(key)

        # 提取pub struct
        elif node.type == 'struct_item':
            is_pub = False
            for child in node.children:
                if child.type == 'visibility_modifier':
                    is_pub = True
                    break

            if is_pub:
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                    key = (name, 'struct')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'struct', 'path': file_path})
                        seen_exports.add(key)

        # 提取pub enum
        elif node.type == 'enum_item':
            is_pub = False
            for child in node.children:
                if child.type == 'visibility_modifier':
                    is_pub = True
                    break

            if is_pub:
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                    key = (name, 'enum')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'enum', 'path': file_path})
                        seen_exports.add(key)

        # 提取pub trait
        elif node.type == 'trait_item':
            is_pub = False
            for child in node.children:
                if child.type == 'visibility_modifier':
                    is_pub = True
                    break

            if is_pub:
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                    key = (name, 'trait')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'trait', 'path': file_path})
                        seen_exports.add(key)

        for child in node.children:
            visit_node(child)

    visit_node(root)
    return deps, exports, inner


def extract_java_structure(source_code, file_path):
    """使用tree-sitter提取Java结构"""
    if 'java' not in LANGUAGES:
        return [], [], []
    parser = Parser(LANGUAGES['java'])
    source_bytes = bytes(source_code, 'utf8')
    tree = parser.parse(source_bytes)
    root = tree.root_node

    deps = []
    exports = []
    inner = []
    seen_deps = set()
    seen_exports = set()

    def visit_node(node):
        # 提取import语句
        if node.type == 'import_declaration':
            for child in node.children:
                if child.type == 'scoped_identifier' or child.type == 'identifier':
                    path = source_bytes[child.start_byte:child.end_byte].decode('utf8')
                    if path not in seen_deps:
                        deps.append({'m': path, 'use': [], 'type': 'import'})
                        seen_deps.add(path)

        # 提取public类
        elif node.type == 'class_declaration':
            is_public = False
            for child in node.children:
                if child.type == 'modifiers':
                    mod_text = source_bytes[child.start_byte:child.end_byte].decode('utf8')
                    if 'public' in mod_text:
                        is_public = True
                        break

            if is_public:
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                    key = (name, 'class')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'class', 'path': file_path})
                        seen_exports.add(key)

                    # 提取public方法
                    methods = []
                    body = node.child_by_field_name('body')
                    if body:
                        for child in body.children:
                            if child.type == 'method_declaration':
                                is_public_method = False
                                for mod_child in child.children:
                                    if mod_child.type == 'modifiers':
                                        mod_text = source_bytes[mod_child.start_byte:mod_child.end_byte].decode('utf8')
                                        if 'public' in mod_text:
                                            is_public_method = True
                                            break
                                if is_public_method:
                                    method_name_node = child.child_by_field_name('name')
                                    if method_name_node:
                                        method_name = source_bytes[method_name_node.start_byte:method_name_node.end_byte].decode('utf8')
                                        methods.append(method_name)
                    if methods:
                        inner.append({'n': name, 't': 'class', 'has': methods[:10]})

        # 提取public接口
        elif node.type == 'interface_declaration':
            is_public = False
            for child in node.children:
                if child.type == 'modifiers':
                    mod_text = source_bytes[child.start_byte:child.end_byte].decode('utf8')
                    if 'public' in mod_text:
                        is_public = True
                        break

            if is_public:
                name_node = node.child_by_field_name('name')
                if name_node:
                    name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                    key = (name, 'interface')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'interface', 'path': file_path})
                        seen_exports.add(key)

        for child in node.children:
            visit_node(child)

    visit_node(root)
    return deps, exports, inner


def extract_go_structure(source_code, file_path):
    """使用tree-sitter提取Go结构"""
    if 'go' not in LANGUAGES:
        return [], [], []
    parser = Parser(LANGUAGES['go'])
    source_bytes = bytes(source_code, 'utf8')
    tree = parser.parse(source_bytes)
    root = tree.root_node

    deps = []
    exports = []
    inner = []
    seen_deps = set()
    seen_exports = set()

    def visit_node(node):
        # 提取import语句
        if node.type == 'import_declaration':
            for child in node.children:
                if child.type == 'import_spec_list':
                    for spec in child.children:
                        if spec.type == 'import_spec':
                            path_node = spec.child_by_field_name('path')
                            if path_node:
                                path = source_bytes[path_node.start_byte:path_node.end_byte].decode('utf8').strip('"')
                                if path not in seen_deps:
                                    deps.append({'m': path, 'use': [], 'type': 'import'})
                                    seen_deps.add(path)
                elif child.type == 'import_spec':
                    path_node = child.child_by_field_name('path')
                    if path_node:
                        path = source_bytes[path_node.start_byte:path_node.end_byte].decode('utf8').strip('"')
                        if path not in seen_deps:
                            deps.append({'m': path, 'use': [], 'type': 'import'})
                            seen_deps.add(path)

        # 提取导出的函数（首字母大写）
        elif node.type == 'function_declaration':
            name_node = node.child_by_field_name('name')
            if name_node:
                name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                if name and name[0].isupper():
                    key = (name, 'function')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'function', 'path': file_path})
                        seen_exports.add(key)

        # 提取导出的方法（首字母大写）
        elif node.type == 'method_declaration':
            name_node = node.child_by_field_name('name')
            if name_node:
                name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                if name and name[0].isupper():
                    key = (name, 'method')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'method', 'path': file_path})
                        seen_exports.add(key)

        # 提取导出的类型（struct, interface）
        elif node.type == 'type_declaration':
            for spec in node.children:
                if spec.type == 'type_spec':
                    name_node = spec.child_by_field_name('name')
                    type_node = spec.child_by_field_name('type')
                    if name_node:
                        name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                        if name and name[0].isupper():
                            type_kind = 'type'
                            fields = []
                            if type_node:
                                if type_node.type == 'struct_type':
                                    type_kind = 'struct'
                                    # 提取struct字段
                                    for child in type_node.children:
                                        if child.type == 'field_declaration_list':
                                            for field in child.children:
                                                if field.type == 'field_declaration':
                                                    for name_child in field.children:
                                                        if name_child.type == 'field_identifier':
                                                            field_name = source_bytes[name_child.start_byte:name_child.end_byte].decode('utf8')
                                                            if field_name and field_name[0].isupper():
                                                                fields.append(field_name)
                                elif type_node.type == 'interface_type':
                                    type_kind = 'interface'

                            key = (name, type_kind)
                            if key not in seen_exports:
                                exports.append({'n': name, 't': type_kind, 'path': file_path})
                                seen_exports.add(key)

                            if fields:
                                inner.append({'n': name, 't': type_kind, 'has': fields[:10]})

        for child in node.children:
            visit_node(child)

    visit_node(root)
    return deps, exports, inner


def extract_structure_treesitter(module_path, max_files=200, max_file_size=1024*1024):
    """使用tree-sitter提取结构"""
    structure = {
        'deps': [],
        'exports': [],
        'inner': []
    }

    # 计算总匹配数（用于截断警告）
    total_matched = 0
    patterns_for_count = ['**/*.ts', '**/*.tsx', '**/*.js', '**/*.jsx', '**/*.py',
                          '**/*.go', '**/*.java', '**/*.rs', '**/*.cpp', '**/*.cc',
                          '**/*.cxx', '**/*.c', '**/*.h', '**/*.hpp']
    exclude_dirs = {'node_modules', 'dist', 'build', '__pycache__', '.git', 'vendor', 'target', 'out'}
    for pat in patterns_for_count:
        for f in glob.glob(os.path.join(module_path, pat), recursive=True):
            if os.path.islink(f) or not os.path.isfile(f):
                continue
            if any(ex in Path(f).parts for ex in exclude_dirs):
                continue
            total_matched += 1

    files = find_source_files(module_path, max_files=max_files, max_file_size=max_file_size)
    if total_matched > len(files):
        print(f"WARNING: module truncated, scanned {len(files)}/{total_matched} files",
              file=sys.stderr)
    all_deps = []
    all_exports = []
    all_inner = []

    for file_path in files:
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                source_code = f.read()

            lang = detect_language(file_path)
            if not lang:
                continue

            # 检查语言是否已安装支持
            if lang not in LANGUAGES:
                continue

            rel_path = os.path.relpath(file_path, module_path)

            if lang in ['typescript', 'javascript']:
                deps, exports, inner = extract_typescript_structure(source_code, rel_path)
                all_deps.extend(deps)
                all_exports.extend(exports)
                all_inner.extend(inner)
            elif lang == 'python':
                deps, exports, inner = extract_python_structure(source_code, rel_path)
                all_deps.extend(deps)
                all_exports.extend(exports)
                all_inner.extend(inner)
            elif lang == 'go':
                deps, exports, inner = extract_go_structure(source_code, rel_path)
                all_deps.extend(deps)
                all_exports.extend(exports)
                all_inner.extend(inner)
            elif lang == 'java':
                deps, exports, inner = extract_java_structure(source_code, rel_path)
                all_deps.extend(deps)
                all_exports.extend(exports)
                all_inner.extend(inner)
            elif lang == 'rust':
                deps, exports, inner = extract_rust_structure(source_code, rel_path)
                all_deps.extend(deps)
                all_exports.extend(exports)
                all_inner.extend(inner)
            elif lang in ['cpp', 'c']:
                deps, exports, inner = extract_cpp_structure(source_code, rel_path)
                all_deps.extend(deps)
                all_exports.extend(exports)
                all_inner.extend(inner)

        except Exception as e:
            print(f"Warning: failed to parse {file_path}: {e}", file=sys.stderr)
            continue

    # 去重
    seen_deps = set()
    for dep in all_deps:
        key = (dep['m'], tuple(dep.get('use', [])))
        if key not in seen_deps:
            structure['deps'].append(dep)
            seen_deps.add(key)

    seen_exports = set()
    for exp in all_exports:
        key = (exp['n'], exp['t'])
        if key not in seen_exports:
            structure['exports'].append(exp)
            seen_exports.add(key)

    seen_inner = set()
    for inn in all_inner:
        key = (inn['n'], tuple(inn.get('has', [])))
        if key not in seen_inner:
            structure['inner'].append(inn)
            seen_inner.add(key)

    return structure


# ============================================================
# 后处理层：模块映射、跨模块过滤、role 判定、use 频次、模式识别、循环依赖
# ============================================================

# 已知公共包注册表前缀（命中视为 utility）
PUBLIC_PACKAGE_PREFIXES = (
    "react", "react-", "@react", "@types/", "@angular/", "@vue/",
    "lodash", "axios", "express", "vue", "next", "vite",
    "numpy", "pandas", "scipy", "torch", "tensorflow", "django", "flask", "requests",
    "serde", "tokio", "rayon", "anyhow", "thiserror", "clap",
    "google.", "javax.", "org.springframework", "com.google", "junit",
    "github.com/", "golang.org/", "google.golang.org/", "gopkg.in/",
    "boost/", "Qt", "qt/",
)

# 项目根 framework / engine 约定目录
FRAMEWORK_DIR_HINTS = ("engine", "framework", "core", "runtime", "platform")
RESOURCE_DIR_HINTS = ("Resources", "resources", "assets", "config", "configs", "Config")


def resolve_submodule_paths(project_root, mechanism="auto"):
    """收集项目子模块路径清单。返回相对项目根的路径 set。"""
    paths = set()

    def parse_gitmodules():
        f = os.path.join(project_root, ".gitmodules")
        if not os.path.isfile(f):
            return
        try:
            with open(f, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith("path"):
                        eq = line.find("=")
                        if eq > 0:
                            paths.add(line[eq + 1:].strip())
        except Exception:
            pass

    def parse_package_json():
        f = os.path.join(project_root, "package.json")
        if not os.path.isfile(f):
            return
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            ws = data.get("workspaces")
            patterns = []
            if isinstance(ws, list):
                patterns = ws
            elif isinstance(ws, dict):
                patterns = ws.get("packages", []) or []
            for pat in patterns:
                # 简化：仅展开通配 packages/* 这类
                base = pat.replace("/*", "")
                base_path = os.path.join(project_root, base)
                if os.path.isdir(base_path) and "*" in pat:
                    for sub in os.listdir(base_path):
                        sub_full = os.path.join(base_path, sub)
                        if os.path.isdir(sub_full):
                            paths.add(os.path.relpath(sub_full, project_root))
                elif os.path.isdir(base_path):
                    paths.add(base)
        except Exception:
            pass

    def parse_cargo_toml():
        f = os.path.join(project_root, "Cargo.toml")
        if not os.path.isfile(f):
            return
        try:
            with open(f, "r", encoding="utf-8") as fh:
                in_ws = False
                for line in fh:
                    s = line.strip()
                    if s.startswith("[workspace]"):
                        in_ws = True
                        continue
                    if s.startswith("["):
                        in_ws = False
                        continue
                    if in_ws and s.startswith("members"):
                        # members = ["a", "b"]
                        m = re.search(r"\[(.*?)\]", s)
                        if m:
                            for item in m.group(1).split(","):
                                v = item.strip().strip('"').strip("'")
                                if v:
                                    paths.add(v)
        except Exception:
            pass

    if mechanism in ("auto", "git-submodule"):
        parse_gitmodules()
    if mechanism in ("auto", "monorepo-workspace"):
        parse_package_json()
    if mechanism in ("auto", "cargo-workspace"):
        parse_cargo_toml()

    return paths


def is_external_package(module_str):
    """判断字符串是否为外部包（npm / pypi / 类似命名）。"""
    if not module_str:
        return False
    # 相对路径、绝对路径、./../ 起始 → 非外部
    if module_str.startswith((".", "/", "./", "../")):
        return False
    # 已知公共包前缀
    for pre in PUBLIC_PACKAGE_PREFIXES:
        if module_str.startswith(pre):
            return True
    return False


def map_dep_to_module(dep_m, current_module_rel, project_root, submodule_paths):
    """把 deps 项的 m 字段映射为目标模块标识。

    返回 (target_module, role)：
      - target_module: 跨模块时为目标子模块路径或外部包名；同模块内部 → None
      - role: framework / utility / sibling / resource / unknown

    兜底语义（修 P0-1/P0-4）：未匹配任何已知模式时，**保留 dep 字面量为 unknown**
    而非返回 None 丢弃；让下游（doctor / 用户）裁决。仅在能明确判定为模块内部
    引用时才返回 None。
    """
    if not dep_m:
        return None, "unknown"

    # 外部包 → utility
    if is_external_package(dep_m):
        return dep_m, "utility"

    # 相对路径基于当前模块
    if dep_m.startswith(("./", "../")):
        abs_target = os.path.normpath(os.path.join(project_root, current_module_rel, dep_m))
        rel = os.path.relpath(abs_target, project_root)
        # 解析后落在自身模块内 → 模块内部引用
        if rel == current_module_rel or rel.startswith(current_module_rel + os.sep):
            return None, "unknown"
        # 解析后落在某子模块内
        for sub in submodule_paths:
            if rel == sub or rel.startswith(sub + os.sep):
                return sub, "sibling"
        # 解析后落在 framework / resource hint
        first_seg = rel.split(os.sep)[0] if rel else ""
        if first_seg in FRAMEWORK_DIR_HINTS:
            return first_seg, "framework"
        if first_seg in RESOURCE_DIR_HINTS:
            return first_seg, "resource"
        # 兜底：保留为 unknown 字面量
        return rel, "unknown"

    if dep_m.startswith("/"):
        # 绝对路径，几乎不该出现；保留字面量
        return dep_m, "unknown"

    # 非路径形式（裸名 / 包名 / include 字面量）
    # 优先比对 submodule_paths：dep_m 是否前缀命中任何子模块路径
    for sub in submodule_paths:
        if dep_m == sub or dep_m.startswith(sub + "/") or dep_m.startswith(sub + os.sep):
            if sub == current_module_rel:
                return None, "unknown"  # 自指
            return sub, "sibling"

    # framework / resource hint 命中第一段
    first_seg = dep_m.split("/")[0]
    if first_seg in FRAMEWORK_DIR_HINTS:
        return first_seg, "framework"
    if first_seg in RESOURCE_DIR_HINTS:
        return first_seg, "resource"

    # 兜底：保留字面量为 unknown（修 P0-1：不再丢弃）
    return dep_m, "unknown"


def postprocess_structure(raw, rel_module, project_root, submodule_paths, candidates_out=None):
    """对原始 raw 结构做语义级 enrichment。"""
    enriched = {
        "deps": [],
        "exports": [],
        "inner": [],
        "cross_module_contracts": [],
        "data_flow_anchors": [],
    }

    # ---- deps：模块级归并 + 跨模块过滤 + role + granularity + use 聚合 ----
    # 聚合表：target_module → {role, use_freq: {sym: count}}
    #
    # 注（v1 限制 / TODO）：当前 use 频次 = "符号在 raw deps 中作为 import 出现的次数"，
    # 而非 TODO §1.1 期望的"符号在源码非声明位置的引用次数"。原因是各语言 visit_node
    # 当前只在 import 节点收集，未追加 identifier 引用扫描。
    # 后续 v2 可在每个语言提取器加 identifier-frequency pass，结果通过 raw 输出
    # 同名 sym 多条 dep 项让此聚合自然反映真实引用频次。
    agg = {}
    for d in raw.get("deps", []):
        target, role = map_dep_to_module(d.get("m", ""), rel_module, project_root, submodule_paths)
        if target is None:
            continue  # 模块内部引用丢弃
        bucket = agg.setdefault(target, {"role": role, "use_freq": {}})
        for sym in d.get("use", []) or []:
            bucket["use_freq"][sym] = bucket["use_freq"].get(sym, 0) + 1

    for target, info in agg.items():
        # top-5 频次符号
        top = sorted(info["use_freq"].items(), key=lambda kv: -kv[1])[:5]
        enriched["deps"].append({
            "m": target,
            "use": [k for k, _ in top],
            "type": "import",
            "role": info["role"],
            "granularity": "module",
        })

    # ---- exports：默认 vis=public（所有现有提取器已过滤了非公开） ----
    for e in raw.get("exports", []):
        item = dict(e)
        item.setdefault("vis", "public")
        enriched["exports"].append(item)

    # ---- inner：识别 pattern (singleton / observer)；base 字段保留空对象 ----
    for n in raw.get("inner", []):
        item = dict(n)
        has = set(item.get("has") or [])
        # singleton：has 含 getInstance / instance / getSingleton 或类名后缀 Singleton
        is_singleton = any(m in has for m in ("getInstance", "instance", "getSingleton")) \
            or item.get("n", "").endswith("Singleton")
        # observer：has 含 addObserver / subscribe / on / emit / publish 任三件
        observer_markers = sum(1 for m in ("addObserver", "subscribe", "on", "emit", "publish",
                                            "addListener", "notify") if m in has)
        is_observer = observer_markers >= 2
        if is_singleton:
            item["pattern"] = "singleton"
        elif is_observer:
            item["pattern"] = "observer"
        # base 字段：保留缺省（提取器未填）；下游手动补
        enriched["inner"].append(item)

    # ---- cross_module_contracts：高置信度自动识别 ----
    contract_candidates = []
    for n in raw.get("inner", []):
        cls_name = n.get("n", "")
        # 命名启发：*Delegate / *Listener / *Observer
        if cls_name.endswith(("Delegate", "Listener", "Observer", "Callback")):
            contract_candidates.append({
                "with": "(unknown)",
                "protocol": "delegate" if cls_name.endswith("Delegate") else "callback",
                "interface": cls_name,
                "direction": "outbound",
                "note": f"declared as {cls_name}",
                "confidence": "medium",
                "_source_path": n.get("path", ""),
            })
    # 仅高置信度（命名 + 配对存在 implements）写入 enriched
    # 当前 raw 不带 implements 信息 → 全部进候选清单，不入正式字段
    # （后续 schema base 加 implements 后可升级）

    # ---- data_flow_anchors：保留为候选（需要跨模块视角，单模块视角无法判定） ----
    flow_candidates = []  # 暂留空；由 main 模块视角脚本调用时填充

    if candidates_out:
        try:
            with open(candidates_out, "w", encoding="utf-8") as fh:
                json.dump({
                    "cross_module_contracts": contract_candidates,
                    "data_flow_anchors": flow_candidates,
                }, fh, indent=2, ensure_ascii=False)
        except Exception as ex:
            print(f"WARNING: failed to write candidates: {ex}", file=sys.stderr)

    # ---- 循环依赖检测 ----
    # 注：单模块调用看不到双向边，此处仅基于本模块 → 其他模块的单向 deps，
    # 真正循环检测须在主模块视角下聚合多个 extract 结果。
    # 这里仅对本批 deps 做 trivial 自循环检测（target == current_module）。
    for dep in enriched["deps"]:
        if dep["m"] == rel_module:
            print(f"WARNING: self-loop in deps for module {rel_module}", file=sys.stderr)

    return enriched


def main():
    import argparse
    p = argparse.ArgumentParser(description="Extract structure data from source modules")
    p.add_argument("module_path", help="模块路径（相对 project_root 或绝对路径）")
    p.add_argument("project_root", nargs="?", default=None, help="项目根目录")
    p.add_argument("--max-files", type=int, default=200, help="最多扫描文件数（默认 200）")
    p.add_argument("--max-file-size", type=int, default=1024 * 1024, help="单文件最大字节（默认 1 MiB）")
    p.add_argument("--resolve-modules", default="auto",
                   choices=["auto", "git-submodule", "monorepo-workspace", "cargo-workspace", "none"],
                   help="子模块路径解析机制（默认 auto 嗅探）")
    p.add_argument("--candidates", default=None,
                   help="将 cross_module_contracts / data_flow_anchors 候选清单 dump 到指定 JSON 文件")
    args = p.parse_args()

    project_root = os.path.abspath(args.project_root or os.getcwd())
    module_path = args.module_path
    if not os.path.isabs(module_path):
        module_path = os.path.join(project_root, module_path)
    module_path = os.path.abspath(module_path)

    if not os.path.isdir(module_path):
        print(f"ERROR: {module_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    raw = extract_structure_treesitter(
        module_path,
        max_files=args.max_files,
        max_file_size=args.max_file_size,
    )

    # 后处理 enrichment
    rel_module = os.path.relpath(module_path, project_root)
    submodule_paths = resolve_submodule_paths(project_root, args.resolve_modules)

    enriched = postprocess_structure(
        raw,
        rel_module=rel_module,
        project_root=project_root,
        submodule_paths=submodule_paths,
        candidates_out=args.candidates,
    )

    print(json.dumps(enriched, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
