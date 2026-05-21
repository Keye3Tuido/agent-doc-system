#!/usr/bin/env python3
"""
doc-scaffold.py — 从子模块路径自动生成文档骨架。

用法: python3 doc-scaffold.py <module_path> [project_root]

示例: python3 doc-scaffold.py Libraries/code_sandsort /path/to/project

功能:
  - 从 git remote 获取 origin URL
  - 从 git 获取当前分支和远端 sha
  - 解析 URL 生成 origin_host / owner / name
  - 生成符合 schema 的 yaml 头 + 空章节模板
  - 输出到 stdout（不直接写文件，由调用方决定写入位置）
"""

import os
import re
import subprocess
import sys


def run_git(args, cwd):
    """执行 git 命令，返回 stdout 或 None。"""
    try:
        r = subprocess.run(
            ["git"] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=10,
        )
        if r.returncode == 0:
            return r.stdout.strip()
        return None
    except Exception:
        return None


def parse_git_url(url):
    """解析 git URL，返回 (host, owner, name)。"""
    url = url.strip()
    # SSH: git@host:owner/name.git
    m = re.match(r"git@([^:]+):(.+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2), m.group(3)
    # SSH with port: git@host:port:owner/name.git
    m = re.match(r"git@([^:]+):(\d+):(.+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return f"{m.group(1)}-{m.group(2)}", m.group(3), m.group(4)
    # HTTPS: https://host/owner/name.git
    m = re.match(r"https?://([^/]+)/(.+)/([^/]+?)(?:\.git)?$", url)
    if m:
        return m.group(1), m.group(2), m.group(3)
    return "unknown", "unknown", "unknown"


def slugify(s):
    """将字符串转为 slug（保留字母数字和连字符）。"""
    s = re.sub(r"[^\w\u4e00-\u9fff\u3400-\u4dbf-]", "-", s)
    s = re.sub(r"-+", "-", s)
    return s.strip("-")


def generate_filename(host, owner, name, branch):
    """生成文档文件名。"""
    parts = [
        slugify(host),
        slugify(owner),
        slugify(name),
        slugify(branch.replace("/", "-")),
    ]
    return "__".join(parts) + ".md"


def main():
    if len(sys.argv) < 2:
        print("Usage: doc-scaffold.py <module_path> [project_root]", file=sys.stderr)
        sys.exit(1)

    module_path = sys.argv[1]
    project_root = sys.argv[2] if len(sys.argv) > 2 else os.getcwd()
    project_root = os.path.abspath(project_root)
    abs_module = os.path.join(project_root, module_path)

    if not os.path.isdir(abs_module):
        print(f"ERROR: {abs_module} is not a directory", file=sys.stderr)
        sys.exit(1)

    # 获取 git 信息
    origin_url = run_git(["-C", abs_module, "remote", "get-url", "origin"], project_root)
    if not origin_url:
        print("ERROR: cannot get origin URL", file=sys.stderr)
        sys.exit(1)

    branch = run_git(["-C", abs_module, "rev-parse", "--abbrev-ref", "HEAD"], project_root)
    if branch == "HEAD":
        # detached, 尝试从 remote 分支推断
        refs = run_git(["-C", abs_module, "branch", "-r", "--points-at", "HEAD"], project_root)
        if refs:
            # 取第一个非 HEAD 的远端分支
            for ref in refs.split("\n"):
                ref = ref.strip()
                if ref and "HEAD" not in ref and ref.startswith("origin/"):
                    branch = ref.removeprefix("origin/")
                    break
        if branch == "HEAD":
            branch = "detached"

    # 获取远端 sha
    remote_sha = run_git(["-C", abs_module, "rev-parse", f"origin/{branch}"], project_root)
    if not remote_sha:
        remote_sha = run_git(["-C", abs_module, "rev-parse", "HEAD"], project_root)

    host, owner, name = parse_git_url(origin_url)
    filename = generate_filename(host, owner, name, branch)

    # 输出骨架
    output = f"""---
schema_version: 2
agent_load: on-demand
repo: "{origin_url}"
origin_host: "{host}"
owner: "{owner}"
name: "{name}"
branch: "{branch}"
commit: "{remote_sha or '0' * 40}"
origin_path_in_main: "{module_path}"
---

# {name}

## 定位
（一句话说清模块在系统中的角色）

## 职责边界
做什么：
不做什么：

## 架构

## 生命周期

## 外部入口

## 关键流程

## 接口

## 数据契约

## 配置与资源

## 依赖

## 使用约束

## 警示

## 可观测性
"""

    # 输出文件名建议到 stderr，内容到 stdout
    print(f"FILENAME: {filename}", file=sys.stderr)
    print(output)


if __name__ == "__main__":
    main()
