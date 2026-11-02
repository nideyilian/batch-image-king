"""Alpha 合成器兜底路径回归（2026-11-02）。

这里锁定两个"降级变崩溃"的真实事故，都出在
``app/utils/unified_alpha_compositor.py``：

1. **``_basic_dark_edge_fix`` 函数体被误插入的 ``def safe_print(...)`` 从中间劈开**。
   表现为：
     - 传入 background_color 时，函数只执行到 ``img_array = ...`` 就结束，
       在 ``if background_color:`` 分支末尾返回 **None**；
     - 后半段颜色校正代码变成了 ``safe_print`` 的私有逻辑，永不执行。
   该方法恰好是「PNG 优化不可用 / 优化抛异常」时的**最后一道防线**，
   返回 None 等于把可降级的问题升级成导出崩溃。

2. **``safe_print`` 全文被调用 18 次、却零定义零导入**。
   所有降级分支（OpenCV 缺失、PNG 优化缺失、合成失败警告）一旦触发
   就抛 ``NameError`` —— 降级路径本身反而成了崩溃源。
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from app.utils.unified_alpha_compositor import (
    UnifiedAlphaCompositor,
    unified_alpha_compositor,
)

MODULE_PATH = Path(__file__).resolve().parents[1] / "app" / "utils" / "unified_alpha_compositor.py"


@pytest.fixture
def semi_transparent_rgba():
    """左边缘 12px 做透明度渐变的 40×40 图，用来触发半透明颜色校正。"""
    from PIL import Image

    image = Image.new("RGBA", (40, 40), (200, 30, 30, 255))
    for x in range(12):
        alpha = int(255 * x / 12)
        for y in range(40):
            image.putpixel((x, y), (200, 30, 30, alpha))
    return image


@pytest.mark.unit
def test_safe_print_is_defined_in_module():
    """safe_print 必须能在模块上取到（历史事故：调用 18 次但从未定义）。"""
    from app.utils import unified_alpha_compositor as module

    assert hasattr(module, "safe_print"), "safe_print 未导入/未定义，降级分支会抛 NameError"
    assert callable(module.safe_print)
    # 真正调用一次，确认不是个占位属性
    module.safe_print("[test] safe_print 可用")


@pytest.mark.unit
def test_all_degradation_paths_can_reference_safe_print():
    """静态检查：源码里每个 safe_print 调用都必须能解析到已定义的名字。"""
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    # 模块级必须存在这个名字（import 或 def 都算）
    defined = set()
    for node in tree.body:
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                defined.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                defined.add((alias.asname or alias.name).split(".")[0])
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            defined.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    defined.add(target.id)

    assert "safe_print" in defined, "模块级没有定义或导入 safe_print"

    calls = [
        node for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "safe_print"
    ]
    assert len(calls) >= 1, "预期模块内有 safe_print 调用；如果已全部移除，请同步删掉本断言"


@pytest.mark.unit
def test_basic_dark_edge_fix_without_background_returns_image(semi_transparent_rgba):
    """不给背景色：只平滑 Alpha，必须返回图片。"""
    result = unified_alpha_compositor._basic_dark_edge_fix(semi_transparent_rgba)
    assert result is not None, "兜底路径返回 None —— 调用方会崩"
    assert result.mode == "RGBA"
    assert result.size == semi_transparent_rgba.size


@pytest.mark.unit
def test_basic_dark_edge_fix_with_background_returns_image(semi_transparent_rgba):
    """给背景色：这是被劈开的那条分支，必须返回图片而不是 None。"""
    result = unified_alpha_compositor._basic_dark_edge_fix(
        semi_transparent_rgba, (250, 250, 250)
    )
    assert result is not None, (
        "带 background_color 时返回 None —— 正是历史事故的特征"
        "（函数体被 def safe_print 劈开）"
    )
    assert result.mode == "RGBA"
    assert result.size == semi_transparent_rgba.size


@pytest.mark.unit
def test_basic_dark_edge_fix_accepts_non_rgba_input():
    """输入是 RGB 时也要能处理（内部先转 RGBA）。"""
    from PIL import Image

    result = unified_alpha_compositor._basic_dark_edge_fix(
        Image.new("RGB", (10, 10), (10, 20, 30))
    )
    assert result is not None
    assert result.mode == "RGBA"


@pytest.mark.unit
def test_basic_dark_edge_fix_never_returns_none_on_bad_background(semi_transparent_rgba):
    """背景色非法（长度不对）时也必须降级返回图片，而不是让异常冒出去。"""
    result = unified_alpha_compositor._basic_dark_edge_fix(
        semi_transparent_rgba, (1, 2)
    )
    assert result is not None
    assert result.size == semi_transparent_rgba.size


@pytest.mark.unit
def test_module_has_no_function_body_truncation():
    """结构检查：模块级函数之间不允许出现"上一个是方法、下一个突然掉到 0 缩进"的诡异拼接。

    历史事故就是把 ``def safe_print`` 插进了一个**方法体内**，导致方法体提前结束。
    这里用 AST 对比：所有类的方法必须完整落在类范围内（由 ast 保证），
    真正要防的是"模块级 def 夹在类方法中间"。
    """
    source = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(source)

    class_ranges: list[tuple[int, int]] = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef):
            start = node.lineno
            end = max(
                getattr(child, "end_lineno", child.lineno)
                for child in node.body
                if hasattr(child, "lineno")
            )
            class_ranges.append((start, end))

    module_level_defs = [
        node for node in tree.body if isinstance(node, ast.FunctionDef)
    ]
    for func in module_level_defs:
        for start, end in class_ranges:
            assert not (start < func.lineno < end), (
                f"模块级函数 {func.name}（第 {func.lineno} 行）落在类范围 "
                f"{start}-{end} 内 —— 疑似又一个 def 被误插入类方法体"
            )
