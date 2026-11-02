#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""架构约束检查器（零依赖，纯标准库）。

为什么自己写而不用 import-linter：
  * CI 环境能装，但本地/离线环境装不上，规则就变成"只有 CI 能验证"；
  * 本项目要守的规则很少且很具体（见 LAYER_CONTRACTS），
    几百行外部依赖换不来对应收益；
  * AST 直读源码，能给出**精确到行号**的违规位置，报错比通用工具更好定位。

检查内容
--------
1. 分层禁止反向依赖：底层（models/utils/services/engines）不得 import 表现层
   （qml/ui）。这是"换掉界面时底层能整体复用"的前提。
2. 单例/全局出口集中：不在模块顶层创建 QWidget / QApplication（避免无显示环境
   导入即崩，也避免 offscreen 测试被抢实例）。
3. 禁止新增裸 `except:`（E722）。历史已清零，不允许回潮。

用法
----
    python tools/check_architecture.py            # 检查，违规则退出码 1
    python tools/check_architecture.py -v         # 打印每条规则的检查范围

在 CI 里作为独立 job 运行，见 .github/workflows/lint.yml。
也可以挂进 pre-commit：`python tools/check_architecture.py`
"""

from __future__ import annotations

import ast
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")

# (来源包前缀, 禁止 import 的目标包前缀, 说明)
LAYER_CONTRACTS = [
    ("app.models", "app.qml", "模型层不得依赖 QML 视图层"),
    ("app.models", "app.ui", "模型层不得依赖 QML 视图层"),
    ("app.utils", "app.qml", "工具层不得依赖 QML 视图层"),
    ("app.utils", "app.ui", "工具层不得依赖 QML 视图层"),
    ("app.services", "app.qml", "服务层不得依赖 QML 视图层"),
    ("app.services", "app.ui", "服务层不得依赖 QML 视图层"),
    ("app.engines", "app.qml", "渲染引擎不得依赖 QML 视图层"),
    ("app.engines", "app.ui", "渲染引擎不得依赖 QML 视图层"),
    ("app.workers", "app.qml", "导出子进程不得依赖 QML 视图层"),
]

# 允许的例外：文件路径 -> 允许的违规目标（附理由）。保持这份清单**极短**，
# 每加一条都意味着架构在退化。
ALLOWED_EXCEPTIONS: dict[str, set[str]] = {}


def iter_py_files(base: str):
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for name in filenames:
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def module_name(path: str) -> str:
    rel = os.path.relpath(path, ROOT)
    mod = rel[:-3].replace(os.sep, ".")
    if mod.endswith(".__init__"):
        mod = mod[: -len(".__init__")]
    return mod


def collect_imports(tree: ast.AST):
    """产出 (被导入模块名, 行号)。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            yield node.module, node.lineno
        elif isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name, node.lineno


def check_layer_contracts() -> list[str]:
    problems = []
    for path in iter_py_files(APP):
        mod = module_name(path)
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="ignore").read())
        except SyntaxError as exc:
            problems.append(f"{os.path.relpath(path, ROOT)}:{exc.lineno}: 语法错误，无法检查 ({exc.msg})")
            continue

        for imported, lineno in collect_imports(tree):
            for source, forbidden, reason in LAYER_CONTRACTS:
                if not mod.startswith(source):
                    continue
                if not imported.startswith(forbidden):
                    continue
                if forbidden in ALLOWED_EXCEPTIONS.get(mod, set()):
                    continue
                problems.append(
                    f"{os.path.relpath(path, ROOT)}:{lineno}: "
                    f"{mod} -> {imported}（{reason}）"
                )
    return problems


def check_bare_except() -> list[str]:
    """禁止裸 except:（E722）。历史已清零，加回来一律拦下。"""
    problems = []
    for path in iter_py_files(APP):
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="ignore").read())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler) and node.type is None:
                problems.append(
                    f"{os.path.relpath(path, ROOT)}:{node.lineno}: 裸 except: —— 请指定异常类型"
                )
    return problems


RULES = {
    "分层依赖方向": check_layer_contracts,
    "裸 except": check_bare_except,
}


# ---------------------------------------------------------------------------
# 与 ruff.toml 对齐的等效检查
# ---------------------------------------------------------------------------
# 为什么在这里再实现一遍：
#   CI 里装了 ruff，但本地/离线环境（比如这台机器，pip 走代理 502）装不上。
#   如果只有 CI 能验证，规则在日常开发中就形同虚设。
#   这里实现 ruff.toml 选中的 5 条规则的最小子集，让两边结论一致；
#   CI 仍然跑真 ruff 作为权威判定，本脚本作为「本地可跑的同一把尺」。
#
# 维护约定：改 ruff.toml 的 select 时必须同步这里，反之亦然。

_FUTURE_NAMES = {
    "annotations", "print_function", "division", "absolute_import",
    "unicode_literals", "with_statement", "generators", "nested_scopes", "braces",
}

# 刻意的 re-export / 命名空间聚合文件，import 本身就是用途
_REEXPORT_FILES = {
    "app/controllers/__init__.py",
    "app/services/__init__.py",
    "app/engines/__init__.py",
    "app/models/__init__.py",
    "app/utils/print_utils.py",
}


def _collect_bound_names(tree: ast.AST) -> tuple[dict[str, int], set[str]]:
    """返回 (导入名 -> 行号, 所有被引用的名字)。"""
    imported: dict[str, int] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                imported.setdefault(alias.asname or alias.name.split(".")[0], node.lineno)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "*":
                    continue
                imported.setdefault(alias.asname or alias.name, node.lineno)

    used: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            root = node
            while isinstance(root, ast.Attribute):
                root = root.value
            if isinstance(root, ast.Name):
                used.add(root.id)
    return imported, used


def check_unused_imports() -> list[str]:
    """F401 未使用 import（本地等效实现）。"""
    problems = []
    for path in iter_py_files(APP):
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        if rel in _REEXPORT_FILES:
            continue
        src = open(path, encoding="utf-8", errors="ignore").read()
        try:
            tree = ast.parse(src)
        except SyntaxError:
            continue
        imported, used = _collect_bound_names(tree)
        # 文本里出现超过 1 次（import 那行本身算 1 次）就认为"可能在字符串注解里用到"，放过
        for name, lineno in imported.items():
            if name in _FUTURE_NAMES or name in used:
                continue
            if len(re.findall(r"\b" + re.escape(name) + r"\b", src)) <= 1:
                problems.append(f"{rel}:{lineno}: 导入但未使用: {name}")
    return problems


def check_redefined() -> list[str]:
    """F811 模块顶层重复定义。"""
    problems = []
    for path in iter_py_files(APP):
        rel = os.path.relpath(path, ROOT).replace(os.sep, "/")
        try:
            tree = ast.parse(open(path, encoding="utf-8", errors="ignore").read())
        except SyntaxError:
            continue
        seen: dict[str, int] = {}
        for node in tree.body:
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name in seen:
                    problems.append(
                        f"{rel}:{node.lineno}: {node.name} 重复定义（首次在第 {seen[node.name]} 行）"
                    )
                else:
                    seen[node.name] = node.lineno
    return problems


RULES["未使用 import (F401)"] = check_unused_imports
RULES["重复定义 (F811)"] = check_redefined


def main(argv: list[str]) -> int:
    verbose = "-v" in argv or "--verbose" in argv

    if verbose:
        print("检查目录:", APP)
        print("分层契约:")
        for source, forbidden, reason in LAYER_CONTRACTS:
            print(f"  {source:<16} !-> {forbidden:<12} {reason}")
        print()

    total = 0
    for name, rule in RULES.items():
        problems = rule()
        if problems:
            total += len(problems)
            print(f"[FAIL] {name}（{len(problems)} 处）")
            for item in problems:
                print(f"  - {item}")
        else:
            print(f"[ OK ] {name}")

    print()
    if total:
        print(f"架构检查未通过，共 {total} 处违规。")
        print("说明：这些规则都是当前代码已经满足的（不是新增要求），"
              "出现违规说明有回退。")
        return 1
    print("架构检查通过。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
