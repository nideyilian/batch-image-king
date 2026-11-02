# -*- coding: utf-8 -*-
"""清理未使用的 import。

安全策略：
  1. 只删「全文只出现 1 次」（即 import 那一行本身）的名字，
     有任何额外出现都保守跳过。
  2. 逐文件处理，每个文件改完立即 ast.parse 校验。
  3. 只处理 app/ 下的业务代码，跳过 __init__.py（可能有 re-export 语义）。
  4. 支持 --dry-run 预览。
"""

from __future__ import annotations

import argparse
import ast
import io
import os
import re
import sys


def collect_imports(tree: ast.Module):
    """返回 [(names_in_stmt, lineno, kind)]，按语句分组便于整行删除。"""
    result = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [(a.asname or a.name).split(".")[0] for a in node.names]
            result.append((names, node.lineno, node.end_lineno, "import"))
        elif isinstance(node, ast.ImportFrom):
            names = [a.asname or a.name for a in node.names if a.name != "*"]
            if names:
                result.append((names, node.lineno, node.end_lineno, "from"))
    return result


def used_names(tree: ast.Module) -> set[str]:
    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            cur = node
            while isinstance(cur, ast.Attribute):
                cur = cur.value
            if isinstance(cur, ast.Name):
                used.add(cur.id)
        elif isinstance(node, ast.arg) and node.annotation is not None:
            for sub in ast.walk(node.annotation):
                if isinstance(sub, ast.Name):
                    used.add(sub.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.returns is not None:
                for sub in ast.walk(node.returns):
                    if isinstance(sub, ast.Name):
                        used.add(sub.id)
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None:
            for sub in ast.walk(node.annotation):
                if isinstance(sub, ast.Name):
                    used.add(sub.id)
    return used


def all_exported(src: str) -> str:
    match = re.search(r"__all__\s*=\s*[\[\(]([^\]\)]*)[\]\)]", src, re.S)
    return match.group(1) if match else ""


def is_used(name: str, used: set, src: str, exported: str) -> bool:
    if name in used:
        return True
    if name == "annotations":
        return True
    if name in exported:
        return True
    # 字符串形式引用（getattr / forward ref / noqa 等）
    if re.search(r'["\']' + re.escape(name) + r'["\']', src):
        return True
    # 全文出现次数 > 1 说明除 import 行外还有别处提到，保守保留
    if len(re.findall(r"\b" + re.escape(name) + r"\b", src)) > 1:
        return True
    return False


def clean_file(path: str, dry_run: bool) -> tuple[int, list[str]]:
    src = open(path, encoding="utf-8").read()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return 0, []

    used = used_names(tree)
    exported = all_exported(src)
    lines = src.splitlines(keepends=True)

    # 决定哪些行要整行删
    to_delete: set[int] = set()
    removed: list[str] = []
    for names, start, end, kind in collect_imports(tree):
        if kind == "from":
            # from X import a, b —— 只有全部没用时整行删
            keep = [n for n in names if is_used(n, used, src, exported)]
            if not keep:
                for ln in range(start, (end or start) + 1):
                    to_delete.add(ln)
                removed.extend(names)
            elif len(keep) < len(names) and start == (end or start):
                # 部分保留：重写该行
                dropped = [n for n in names if n not in keep]
                removed.extend(dropped)
                stmt = lines[start - 1]
                match = re.match(r"^(\s*from\s+\S+\s+import\s+)(.+?)(\s*(?:#.*)?)$", stmt.rstrip("\n"))
                if match:
                    prefix, _, suffix = match.groups()
                    newline = prefix + ", ".join(keep) + suffix + "\n"
                    lines[start - 1] = newline
        else:
            # import a, b —— 逐个判断
            keep = [n for n in names if is_used(n, used, src, exported)]
            if not keep:
                for ln in range(start, (end or start) + 1):
                    to_delete.add(ln)
                removed.extend(names)
            elif len(keep) < len(names) and start == (end or start):
                dropped = [n for n in names if n not in keep]
                removed.extend(dropped)
                stmt = lines[start - 1]
                match = re.match(r"^(\s*import\s+)(.+?)(\s*(?:#.*)?)$", stmt.rstrip("\n"))
                if match:
                    prefix, _, suffix = match.groups()
                    lines[start - 1] = prefix + ", ".join(keep) + suffix + "\n"

    if not removed:
        return 0, []

    new_src = "".join(ln for idx, ln in enumerate(lines, 1) if idx not in to_delete)

    # 语法校验：过不了就放弃这个文件
    try:
        ast.parse(new_src)
    except SyntaxError:
        return 0, []

    if not dry_run:
        with open(path, "w", encoding="utf-8", newline="") as handle:
            handle.write(new_src)
    return len(removed), removed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--root", default="app")
    args = parser.parse_args()

    total = 0
    files_changed = 0
    details: list[tuple[str, int]] = []
    for dirpath, dirnames, filenames in os.walk(args.root):
        if "__pycache__" in dirpath:
            continue
        for filename in filenames:
            if not filename.endswith(".py") or filename == "__init__.py":
                continue
            path = os.path.join(dirpath, filename)
            count, removed = clean_file(path, args.dry_run)
            if count:
                files_changed += 1
                total += count
                details.append((path, count))
                if args.dry_run:
                    print(f"{path}: 删除 {count} 个 → {', '.join(sorted(set(removed))[:6])}")

    details.sort(key=lambda item: -item[1])
    print()
    print(f"{'将' if args.dry_run else '已'}清理 {total} 个未使用 import，涉及 {files_changed} 个文件")
    print("TOP 10:")
    for path, count in details[:10]:
        print(f"  {count:3d}  {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
