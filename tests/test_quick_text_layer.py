"""快速建文字层契约测试。

背景：经典版此前只能走对话框建文字层，建一个至少要填 5 个字段
（名称 / 内容 / 字体 / 字号 / 颜色），高频加字时纯属浪费。
QML 工作台有 addConfiguredTextLayer，经典版缺对等能力。

本组测试锁住三条：
1. 不弹窗就能建（真·快速）
2. 参数校验口径与 QML 侧一致（防两侧行为分叉）
3. 新建的图层**第一眼就能看全内容**（字号自适应 + 边框自动撑开）
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def shared_win():
    """整个模块共用一个主窗口。

    为什么不用 function 级：MainWindow 构造要 2~5 秒（676 个控件），
    10 个用例各建一次就是 50 秒，跑起来像挂死。
    这里只建一次，每个用例自己在里面开新文档。
    """
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)

    win = MainWindow()
    win.resize(1000, 700)
    win.show()
    app.processEvents()

    yield win

    win.close()
    win.deleteLater()
    app.processEvents()


@pytest.fixture
def ctx(shared_win):
    """每个用例在共享窗口里开一个新文档，结束后关掉该标签。"""
    from PySide6.QtWidgets import QApplication

    from app.models.document import Document

    app = QApplication.instance()
    doc = Document(parent=shared_win)
    doc.create_new(800, 600)
    shared_win.create_new_tab(doc)
    app.processEvents()

    yield shared_win, doc, shared_win.layer_controller

    # 关掉本用例的文档，避免影响下一个
    try:
        index = shared_win.document_manager.get_document_count() - 1
        if index >= 0:
            shared_win.close_tab(index)
    except Exception:
        pass
    app.processEvents()



def test_quick_text_layer_creates_without_dialog(ctx):
    """快速建层不弹任何对话框。"""
    from PySide6.QtWidgets import QDialog

    _win, doc, controller = ctx

    original_exec = QDialog.exec
    dialogs_opened = []
    QDialog.exec = lambda self: (dialogs_opened.append(type(self).__name__), 0)[1]

    try:
        layer = controller.add_quick_text_layer()
    finally:
        QDialog.exec = original_exec

    assert layer is not None, "快速建层失败"
    assert not dialogs_opened, f"快速建层不该弹对话框，实际弹了：{dialogs_opened}"
    assert layer in doc.layers or any(x is layer for x in doc.layers)


def test_quick_text_layer_fits_canvas(ctx):
    """快速建出的图层必须在画布内，且字号与画布相称（不能小到看不清）。"""
    _win, doc, controller = ctx
    layer = controller.add_quick_text_layer()

    assert layer is not None
    # 不能超出画布
    assert layer.x + layer.width <= doc.canvas_width, "文字层右边超出画布"
    assert layer.y + layer.height <= doc.canvas_height, "文字层下边超出画布"
    # 字号要跟画布成比例（实测 48px 固定值在 1920 画布上只占宽 16%，太小）
    expected = max(24, min(160, round(doc.canvas_height / 12)))
    assert layer.font_size == expected, (
        f"字号 {layer.font_size} 不是按画布自适应算出的 {expected}"
    )


def test_quick_text_autofit_enabled(ctx):
    """自动适配边框必须开启，否则大字号文字会被裁掉。"""
    _win, _doc, controller = ctx
    layer = controller.add_quick_text_layer()
    assert layer is not None
    assert layer.auto_fit_text_box is True, (
        "auto_fit_text_box 关闭时框固定为 300x100，"
        "72px 的「限时特惠 5折」只会渲染出「限时特惠」，「5折」整段丢失"
    )


def test_configured_text_layer_applies_all_fields(ctx):
    """带配置建层时，内容 / 字号 / 颜色 / 对齐 / 绑定都要落到图层上。"""
    _win, _doc, controller = ctx
    layer = controller.add_configured_text_layer(
        {
            "content": "秋季大促",
            "font_size": 64,
            "color": "#FF3366",
            "alignment": "center",
            "binding_enabled": False,
        }
    )
    assert layer is not None
    assert layer.font_size == 64
    assert tuple(layer.text_color) == (255, 51, 102, 255)
    assert layer.text_binding_enabled is False


@pytest.mark.parametrize(
    "config, reason",
    [
        ({"content": "   "}, "空内容"),
        ({"content": "x", "font_size": 500}, "字号越界"),
        ({"content": "x", "font_size": -1}, "字号负数"),
        ({"content": "x", "color": "不是颜色"}, "非法颜色"),
        ({"content": "x", "alignment": "diagonal"}, "非法对齐"),
    ],
)
def test_configured_text_layer_rejects_invalid(ctx, config, reason):
    """非法输入必须被拒绝，且不能污染文档。"""
    _win, doc, controller = ctx
    before = len(doc.layers)
    result = controller.add_configured_text_layer(config)
    assert result is None, f"{reason} 应当被拒绝"
    assert len(doc.layers) == before, f"{reason} 被拒绝后不应新增图层"


def test_quick_text_layer_names_are_unique(ctx):
    """连按快捷键建多层时，图层名不能重复（否则面板里分不清）。"""
    _win, doc, controller = ctx
    for _ in range(3):
        controller.add_quick_text_layer()

    names = [layer.name for layer in doc.layers]
    assert len(names) == len(set(names)), f"图层名重复：{names}"


def test_configured_text_layer_renders_visible_pixels(ctx):
    """建出的文字必须真的被渲染到画布上（不是只有数据没有画面）。"""
    import numpy as np

    _win, doc, controller = ctx
    layer = controller.add_configured_text_layer(
        {"content": "限时特惠 5折", "font_size": 72, "color": "#FF2D55"}
    )
    assert layer is not None

    image = doc.render_composition()
    assert image is not None

    arr = np.array(image.convert("RGB"))
    red_pixels = (
        (arr[:, :, 0] > 200) & (arr[:, :, 1] < 120) & (arr[:, :, 2] < 140)
    ).sum()
    assert red_pixels > 500, (
        f"画布上只有 {red_pixels} 个红色像素，文字很可能没渲染出来或被裁掉"
    )
