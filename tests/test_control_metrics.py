"""控件尺寸契约：输入类控件必须精确落在 CONTROL_HEIGHT。

## 为什么需要这个测试

QSS 里 `height` / `min-height` **不含 padding 与 border**，三者是相加的。
原来写 `min-height: CONTROL_HEIGHT(30px)` + `padding: 4px 10px`，实测：

    QSpinBox  → 38px   (30 + 4×2 padding)
    QLineEdit → 30px
    QComboBox → 30px

同一行里 spinbox 比另两个高 8px，面板看起来"歪" —— 这是视觉廉价感主要来源之一，
而且靠肉眼很难定位（你不知道该怪哪个控件）。

本组测试直接量渲染后的像素高度，锁住"三者相加 = 30"这个等式。
以后谁再往输入控件上加 padding 而不扣 min-height，这里会红。

另外锁住"不滥用边框"：输入框默认不应有可见描边，
边框色与内部色的亮度差若小于 10，等于白占空间还添噪点。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

pytestmark = pytest.mark.integration

#: 控件高度契约值。
#:
#: 2026-10-28：改为从 `design_spec` 取，不再写死 30。
#: 改造前这里是硬编码 30，而 spec 已经收敛到三档（24/28/36），
#: 导致改了尺寸档位后测试必然失败 —— 契约值本身也应该只有一处真源。
from app.ui.design_spec import Scale  # noqa: E402

EXPECTED_CONTROL_HEIGHT = Scale.PX[Scale.MD]


@pytest.fixture(scope="module")
def panel():
    """整个模块共用一个主窗口（构造要 2~5 秒，别每个用例建一次）。

    ⚠ 必须还原 QApplication 的全局样式：QApplication 是进程级单例，
    装了主题不还原会让后续测试（例如 test_integrated_text_panel_a_v2_ui
    对色块最小高度的断言）在带主题的环境下跑，出现「单跑通过、全量失败」的假回归。
    这是本项目踩过的坑，见 tests/test_splash_contract.py 同类说明。
    """
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    from app.main_window import MainWindow

    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.dark_theme import CursorDarkTheme

    prev_qss = app.styleSheet()
    prev_palette = app.palette()
    CursorDarkTheme.apply_to_application(app)

    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    for _ in range(12):
        app.processEvents()

    yield win.properties_panel

    win.close()
    win.deleteLater()
    app.processEvents()
    # 还原全局样式，避免污染其它测试
    app.setStyleSheet(prev_qss)
    app.setPalette(prev_palette)


def _visible_controls(panel, cls):
    """取面板里可见的某类控件，排除 spinbox 内部的 lineedit。"""
    items = []
    for widget in panel.findChildren(cls):
        if not widget.isVisible():
            continue
        # QSpinBox 内部那个 QLineEdit 是 18px 的实现细节，不算契约控件
        if widget.objectName() == "qt_spinbox_lineedit":
            continue
        items.append(widget)
    return items


@pytest.mark.parametrize("class_name", ["QSpinBox", "QComboBox", "QLineEdit"])
def test_input_controls_height_matches_contract(panel, class_name):
    """输入类控件高度必须精确等于 CONTROL_HEIGHT。"""
    import PySide6.QtWidgets as qw

    cls = getattr(qw, class_name)
    items = _visible_controls(panel, cls)
    if not items:
        pytest.skip(f"面板里没有可见的 {class_name}")

    heights = sorted({w.height() for w in items})
    assert heights == [EXPECTED_CONTROL_HEIGHT], (
        f"{class_name} 高度为 {heights}，契约要求 [{EXPECTED_CONTROL_HEIGHT}]。"
        f"很可能是 QSS 里给输入控件加了 padding 却没从 min-height 里扣掉 —— "
        f"QSS 的 height 不含 padding/border，三者相加才是实际像素高。"
    )


def test_input_controls_border_is_invisible_by_default(panel):
    """输入框默认不应有可见描边（靠底色区分，不靠边框）。"""
    from PySide6.QtGui import QImage
    from PySide6.QtWidgets import QComboBox

    items = _visible_controls(panel, QComboBox)
    if not items:
        pytest.skip("面板里没有可见的 QComboBox")

    widget = items[0]
    image = widget.grab().toImage().convertToFormat(QImage.Format_RGB32)

    mid_x = widget.width() // 2
    top = image.pixelColor(mid_x, 0)
    inner = image.pixelColor(mid_x, widget.height() // 2)
    top_lum = 0.2126 * top.red() + 0.7152 * top.green() + 0.0722 * top.blue()
    inner_lum = 0.2126 * inner.red() + 0.7152 * inner.green() + 0.0722 * inner.blue()

    diff = abs(top_lum - inner_lum)
    assert diff < 4, (
        f"输入框上边缘与内部的亮度差为 {diff:.1f}（上={top_lum:.1f} 内={inner_lum:.1f}），"
        f"说明还存在一条可见描边。低对比描边（实测差 6~9）肉眼难辨却白占 2px，"
        f"设计规范要求改用底色差分层。"
    )


def test_selection_color_matches_brand_accent():
    """文本选中背景必须用品牌主色，不能残留旧主色。"""
    from app.ui.design_tokens import Tokens
    from app.ui.tokens_v2 import Color

    assert Tokens.SELECTION_BG == Color.accent, (
        f"SELECTION_BG={Tokens.SELECTION_BG!r} 与品牌主色 {Color.accent!r} 不一致。"
        f"历史上它漏在 v2 转发层之外，长期是旧 Ant 蓝 #0E76D8 —— "
        f"选中输入框文字时会突然跳出一片冷蓝。"
    )


def test_section_has_no_border(panel):
    """卡片（section）不应有描边，靠底色差分层。"""
    from app.ui.design_tokens import Tokens

    qss = Tokens.panel_qss("#P")
    marker = '#P QFrame[role="section"] {'
    start = qss.find(marker)
    assert start >= 0, "找不到 section 规则"

    body = qss[start : qss.find("}", start)]
    assert "border: none" in body, (
        f"section 规则里不是 border:none，实际内容：{body!r}。"
        f"设计规范 5.0 实测结论：一屏十几个带描边的框会像 Excel 表格。"
    )
