"""render_composition 的结构约束。

这个函数原本 734 行 / 118 分支 / 嵌套 8 层，改一处要通读全篇。
拆分后主逻辑只剩调度，各分支独立成方法。

这组测试锁住两点：
  1. 主函数不能再胖回去（行数 / 嵌套深度上限）
  2. 拆分出来的每一个方法都必须真的被调用到（不能留死代码）

行为一致性由 ``docs/audit/probe_render_baseline.py`` 负责（逐像素比对），
这里只管结构。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

SOURCE = Path(__file__).resolve().parents[1] / "app" / "models" / "document_render.py"


def _class_node() -> ast.ClassDef:
    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    return next(node for node in tree.body if isinstance(node, ast.ClassDef))


def _method(name: str) -> ast.FunctionDef:
    cls = _class_node()
    for node in cls.body:
        if isinstance(node, ast.FunctionDef) and node.name == name:
            return node
    raise AssertionError(f"找不到方法 {name}")


def _span(node: ast.AST) -> int:
    return (node.end_lineno or node.lineno) - node.lineno + 1


def _max_nesting(node: ast.AST) -> int:
    depth = [0]

    def walk(current: ast.AST, level: int) -> None:
        depth[0] = max(depth[0], level)
        for child in ast.iter_child_nodes(current):
            if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.With)):
                walk(child, level + 1)
            else:
                walk(child, level)

    walk(node, 0)
    return depth[0]


def _branches(node: ast.AST) -> int:
    return sum(1 for item in ast.walk(node) if isinstance(item, (ast.If, ast.For, ast.While, ast.Try)))


def test_render_composition_stays_small():
    """主函数只做调度，不应再膨胀回去。"""
    fn = _method("render_composition")
    assert _span(fn) <= 90, f"render_composition 已涨到 {_span(fn)} 行"
    assert _branches(fn) <= 12, f"render_composition 分支数 {_branches(fn)} 过多"
    assert _max_nesting(fn) <= 3, f"render_composition 嵌套 {_max_nesting(fn)} 层过深"


def test_extracted_methods_exist():
    """拆分出的方法都应存在（改名/误删会让这里红）。"""
    expected = [
        "_acquire_advanced_compositor",
        "_render_with_advanced_compositor",
        "_prepare_standard_render",
        "_compose_standard_layers",
        "_build_fill_clone_positions",
    ]
    cls = _class_node()
    names = {node.name for node in cls.body if isinstance(node, ast.FunctionDef)}
    for name in expected:
        assert name in names, f"缺少方法 {name}"


def test_extracted_methods_are_actually_called():
    """抽出来的方法必须被主流程调用，不能变成死代码。"""
    source = SOURCE.read_text(encoding="utf-8")
    for name in (
        "_acquire_advanced_compositor",
        "_render_with_advanced_compositor",
        "_prepare_standard_render",
        "_compose_standard_layers",
        "_build_fill_clone_positions",
    ):
        # 定义占一次，至少还要有一处调用
        assert source.count(name) >= 2, f"{name} 只有定义没有调用"


def test_no_method_is_absurdly_long():
    """任何方法都不该超过 300 行 —— 超了说明又变成不可维护的大块。"""
    cls = _class_node()
    offenders = [
        (node.name, _span(node))
        for node in cls.body
        if isinstance(node, ast.FunctionDef) and _span(node) > 300
    ]
    assert not offenders, f"以下方法过长：{offenders}"


def test_methods_do_not_reference_undefined_free_variables():
    """抽方法最容易漏传参数：引用了外层局部变量却不报错，只会静默失效。

    这里检查每个方法的自由变量是否都是模块级名字（导入/函数/内置）或参数。
    """
    import builtins

    tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
    cls = next(node for node in tree.body if isinstance(node, ast.ClassDef))

    # 模块级可见的名字：内置 + 顶层导入 + 顶层赋值
    known: set[str] = set(dir(builtins))
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                known.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    known.add(target.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            known.add(node.name)

    watched = {
        "_render_with_advanced_compositor",
        "_prepare_standard_render",
        "_compose_standard_layers",
        "_build_fill_clone_positions",
        "_acquire_advanced_compositor",
    }
    problems: list[str] = []
    for node in cls.body:
        if not isinstance(node, ast.FunctionDef) or node.name not in watched:
            continue
        assigned = {a.arg for a in node.args.args}
        loaded: set[str] = set()
        for item in ast.walk(node):
            if isinstance(item, ast.Name):
                if isinstance(item.ctx, (ast.Store, ast.Del)):
                    assigned.add(item.id)
                else:
                    loaded.add(item.id)
            elif isinstance(item, ast.arg):
                assigned.add(item.arg)
            elif isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)) and item is not node:
                assigned.add(item.name)
            elif isinstance(item, ast.ClassDef):
                assigned.add(item.name)
            elif isinstance(item, ast.ExceptHandler) and item.name:
                assigned.add(item.name)
            elif isinstance(item, ast.Import):
                for alias in item.names:
                    assigned.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(item, ast.ImportFrom):
                for alias in item.names:
                    assigned.add((alias.asname or alias.name).split(".")[0])
            elif isinstance(item, ast.comprehension) and isinstance(item.target, ast.Name):
                assigned.add(item.target.id)

        for name in sorted(loaded - assigned - known):
            problems.append(f"{node.name}: {name}")

    assert not problems, "以下自由变量未定义（可能漏传参数）：" + ", ".join(problems)


@pytest.mark.parametrize("name", ["_compose_standard_layers", "_render_with_advanced_compositor"])
def test_heavy_methods_are_documented(name):
    """两个主要分支方法至少要有 docstring 说明返回值语义。"""
    fn = _method(name)
    doc = ast.get_docstring(fn)
    assert doc, f"{name} 缺少 docstring"
    assert "返回" in doc, f"{name} 的 docstring 应说明返回值"
