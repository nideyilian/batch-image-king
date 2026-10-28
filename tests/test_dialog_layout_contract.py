"""对话框布局契约测试：防止文字被挤压截断。

背景（2026-10-27 视觉走查发现）：
批量导出对话框把「导出数量 + 导出格式 + 最大文件大小 + 质量策略」塞进一行，
实测最低需求约 743px，而对话框内部可用宽度仅 ~730px，导致：
  - 「导出数量」被切成「数量」
  - 「最大文件大小(KB)」被切成「最大文件」
  - 数字输入框窄到只显示一位数
  - 「遍历导出（导出所有可能组合）」被切掉尾巴
  - 长文件名预览直接溢出面板边界

这些是功能性缺陷（用户看不到要导出多少张），必须锁住。
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture
def themed_app():
    """给 QApplication 装上主题，**测试结束还原**。

    为什么必须还原：QApplication 是进程级单例，`apply_to_application` 改的是
    全局 styleSheet / palette。若不清回去，后续测试（例如
    test_integrated_text_panel_a_v2_ui 里对控件最小高度的断言）会在
    带主题的环境下运行，得到与单独跑不同的结果 —— 实测表现为
    「单跑通过、全量跑失败」的假回归。
    """
    from PySide6.QtWidgets import QApplication

    from app.ui.dark_theme import CursorDarkTheme

    app = QApplication.instance() or QApplication([])
    prev_qss = app.styleSheet()
    prev_palette = app.palette()
    CursorDarkTheme.apply_to_application(app)
    try:
        yield app
    finally:
        app.setStyleSheet(prev_qss)
        app.setPalette(prev_palette)

REPO_ROOT = Path(__file__).resolve().parents[1]
UI_SRC = (REPO_ROOT / "app" / "ui" / "batch_export_dialog_ui.py").read_text(encoding="utf-8")


@pytest.mark.unit
def test_quality_profile_is_on_its_own_row():
    """质量策略必须独立成行。

    它原本和导出数量/格式/文件大小挤在同一行。质量策略的选项文案较长
    （「压缩体积」「质量优先」），挤在一起时会被压到只剩一个汉字。
    """
    assert "quality_layout" in UI_SRC, "质量策略应使用独立布局"
    assert 'basic_export_layout.addWidget(self.quality_profile_combo)' not in UI_SRC, (
        "质量策略不应再被加入基础参数行（会把行挤爆）"
    )


@pytest.mark.unit
def test_numeric_inputs_have_minimum_width():
    """数字输入框必须有最小宽度，否则 5/6 位数显示不全。"""
    assert "self.count_spin.setMinimumWidth(" in UI_SRC, "导出数量输入框需要最小宽度"
    assert "self.max_file_size_spin.setMinimumWidth(" in UI_SRC, "文件大小输入框需要最小宽度"


@pytest.mark.unit
def test_mode_checkboxes_are_stacked_vertically():
    """导出模式的两个复选框必须竖排。

    横排时「遍历导出（导出所有可能组合）」在窄面板里会被截断。
    """
    assert "mode_options_layout = QVBoxLayout()" in UI_SRC, (
        "导出模式复选框应竖排，横排会截断长文案"
    )


@pytest.mark.unit
def test_filename_preview_is_elided():
    """文件名预览必须按宽度省略，不能溢出容器。

    QLabel 默认不裁剪超长文本，长文件名会画到父容器边界之外。
    这里使用 ElidedLabel 在 resizeEvent 中按真实宽度重算。
    """
    assert "class ElidedLabel" in UI_SRC, "应提供 ElidedLabel 处理超长文本"
    assert "self.filename_preview = ElidedLabel()" in UI_SRC
    assert "ElideMiddle" in UI_SRC
    # 完整值要能在 tooltip 里看到
    assert "setToolTip(preview)" in UI_SRC


@pytest.mark.unit
def test_elided_label_recomputes_on_resize():
    """ElidedLabel 必须在 resizeEvent 重算，而不是只在构造时算一次。

    构造期 width() 尚未确定，只算一次会导致裁断失效 —— 这正是第一版的 bug。
    """
    src = UI_SRC[UI_SRC.index("class ElidedLabel"):]
    src = src[: src.index("class BatchExportDialogUiMixin")]
    assert "def resizeEvent" in src
    assert "_apply_elide" in src


@pytest.mark.unit
def test_elided_label_actually_elides():
    """真实行为验证：长文本在窄宽度下必须出现省略号。"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase, QFont

    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.batch_export_dialog_ui import ElidedLabel

    label = ElidedLabel()
    label.resize(120, 24)
    long_text = "20261027-百万医疗险-闪屏-AI策略-图标-3D拟物V1-陈泽杰-1.jpg"
    label.setText(long_text)

    shown = label.text()
    assert shown != long_text, "超长文本必须被裁断"
    assert "…" in shown, f"裁断后应包含省略号，实际: {shown}"
    # 完整内容仍在
    assert label.fullText() == long_text
    # 渲染宽度不能超过控件宽度
    assert label.fontMetrics().horizontalAdvance(shown) <= label.width()


# --- 状态栏：可交互控件必须放得进状态栏 ---------------------------------

def test_statusbar_spinbox_fits_inside_statusbar(themed_app):
    """状态栏里的数字框不能高于状态栏本身。

    背景（2026-10-27 实测）：全局 `QSpinBox { min-height: control-h(30px) }`
    + padding 把缩放框撑到 32px，而 QMainWindow 的状态栏区固定只有 21px
    （不做纵向拉伸，给 QStatusBar 设 max-height 也无效）。
    结果「100%」的下半截被裁掉，看起来像「1000%」。
    """
    from PySide6.QtWidgets import QApplication

    from app.main_window import MainWindow

    win = MainWindow()
    win.resize(1400, 900)
    win.show()
    for _ in range(12):
        QApplication.processEvents()

    statusbar = win.statusbar
    spinbox = win.zoom_spinbox

    assert spinbox.height() <= statusbar.height(), (
        f"状态栏高 {statusbar.height()}px，但缩放框高 {spinbox.height()}px —— 会被裁切"
    )
    win.close()


def test_zoombox_declares_explicit_compact_height():
    """缩放框必须显式声明紧凑高度，不能依赖全局 QSpinBox 规则。"""
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[1] / "app" / "main_window_ui.py"
    ).read_text(encoding="utf-8")

    assert "spinbox_style" in source
    # 必须明确写 min-height 且不超过状态栏可用高度
    import re

    block = re.search(r"spinbox_style\s*=\s*\"\"\"(.*?)\"\"\"", source, re.S)
    assert block, "找不到 spinbox_style 定义"
    body = block.group(1)
    heights = [int(x) for x in re.findall(r"min-height:\s*(\d+)px", body)]
    assert heights, f"spinbox_style 未声明 min-height，实际内容：{body!r}"
    assert max(heights) <= 20, f"缩放框 min-height {max(heights)}px 超过状态栏可用高度"
