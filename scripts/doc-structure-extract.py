#!/usr/bin/env python3
"""
doc-structure-extract.py — 从源码提取结构化关系数据（deps/exports/inner）

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


def find_source_files(module_path, max_files=50, max_file_size=1024*1024):
    """查找模块中的源码文件（限制数量避免过载）"""
    patterns = ['**/*.ts', '**/*.tsx', '**/*.js', '**/*.jsx', '**/*.py',
                '**/*.go', '**/*.java', '**/*.rs', '**/*.cpp', '**/*.cc',
                '**/*.cxx', '**/*.c', '**/*.h', '**/*.hpp']

    files = []
    for pattern in patterns:
        found = glob.glob(os.path.join(module_path, pattern), recursive=True)
        files.extend(found[:max_files - len(files)])
        if len(files) >= max_files:
            break

    # 排除常见的非源码目录（使用路径组件匹配）
    exclude_dirs = {'node_modules', 'dist', 'build', '__pycache__', '.git', 'vendor', 'target', 'out'}
    filtered = []
    for f in files:
        # 跳过符号链接
        if os.path.islink(f):
            continue
        # 跳过不存在的文件
        if not os.path.isfile(f):
            continue
        # 跳过过大的文件
        if os.path.getsize(f) > max_file_size:
            continue
        # 检查路径组件是否包含排除目录
        if any(ex in Path(f).parts for ex in exclude_dirs):
            continue
        filtered.append(f)

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
    """使用tree-sitter提取Python结构"""
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
                if not name.startswith('_'):  # 排除私有类
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
                if not name.startswith('_'):  # 排除私有函数
                    key = (name, 'function')
                    if key not in seen_exports:
                        exports.append({'n': name, 't': 'function', 'path': file_path})
                        seen_exports.add(key)

        for child in node.children:
            visit_node(child)

    visit_node(root)
    return deps, exports, inner


def extract_cpp_structure(source_code, file_path):
    """使用tree-sitter提取C/C++结构"""
    if 'cpp' not in LANGUAGES:
        return [], [], []
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
        # 提取#include语句
        if node.type == 'preproc_include':
            for child in node.children:
                if child.type in ['string_literal', 'system_lib_string']:
                    path = source_bytes[child.start_byte:child.end_byte].decode('utf8').strip('"<>')
                    if path not in seen_deps:
                        deps.append({'m': path, 'use': [], 'type': 'include'})
                        seen_deps.add(path)

        # 提取函数定义
        elif node.type == 'function_definition':
            declarator = node.child_by_field_name('declarator')
            if declarator:
                # 查找函数名
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

        # 提取类定义
        elif node.type == 'class_specifier':
            name_node = node.child_by_field_name('name')
            if name_node:
                name = source_bytes[name_node.start_byte:name_node.end_byte].decode('utf8')
                key = (name, 'class')
                if key not in seen_exports:
                    exports.append({'n': name, 't': 'class', 'path': file_path})
                    seen_exports.add(key)

                # 提取类的public方法
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

        # 提取struct定义
        elif node.type == 'struct_specifier':
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


def extract_structure_treesitter(module_path):
    """使用tree-sitter提取结构"""
    structure = {
        'deps': [],
        'exports': [],
        'inner': []
    }

    files = find_source_files(module_path)
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


def main():
    if len(sys.argv) < 2:
        print("Usage: doc-structure-extract.py <module_path> [project_root]", file=sys.stderr)
        sys.exit(1)

    module_path = sys.argv[1]
    project_root = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()

    module_path = os.path.abspath(os.path.join(project_root, module_path))

    if not os.path.isdir(module_path):
        print(f"ERROR: {module_path} is not a directory", file=sys.stderr)
        sys.exit(1)

    structure = extract_structure_treesitter(module_path)

    print(json.dumps(structure, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
