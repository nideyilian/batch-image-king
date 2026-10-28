"""主题性能契约：QSS 字体栈必须只有一个字体名。

背景（2026-10-27 实测）：
应用 QSS 里的 ``font-family`` 只要并列第二个字体名（含 sans-serif 这类通用族），
Qt 就会对**每个新建控件**遍历系统全部字体族做匹配。本机装了 2004 个字体族，
单个控件首次入布局从 0ms 变成 ~420ms，主窗口冷启动因此多花 3 秒以上。

实测曲线是断崖不是线性：
    1 个字体名        →     0 ms
    2 个字体名        →  2124 ms
    3 个字体名        →  2270 ms
    4 个字体名        →  2178 ms
    sans-serif 通用族 →  2157 ms

回退需求由 ``CursorDarkTheme._install_font_fallbacks()`` 用
``QFont.insertSubstitutions`` 在程序层解决，实测 2ms 且回退效果不变。

这个测试就是防止有人「顺手」把字体栈写回多名字。
"""

import re

import pytest

pytestmark = pytest.mark.unit


def _app_qss() -> str:
    """取真实生效的全局 QSS（dark_theme 拼接 provider 后的结果）。"""
    from app.ui.dark_theme import CursorDarkTheme

    return CursorDarkTheme.get_complete_style()


def _font_families(qss: str):
    return [v.strip() for v in re.findall(r"font-family:\s*([^;]+);", qss)]


def test_qss_font_family_has_single_name():
    """每条 font-family 只能有一个字体名。"""
    families = _font_families(_app_qss())
    assert families, "全局 QSS 里找不到 font-family，测试前提被破坏"

    offenders = [f for f in families if "," in f]
    assert not offenders, (
        "QSS font-family 出现多字体并列，会让 Qt 逐控件遍历全量字体表（启动 +3s）。"
        f"违规取值：{offenders}。"
        "回退请用 QFont.insertSubstitutions，见 CursorDarkTheme._install_font_fallbacks()。"
    )


def test_qss_has_no_generic_font_family():
    """禁止 QSS 里出现 sans-serif / serif / monospace 这类通用族。"""
    generic = ("sans-serif", "serif", "monospace", "cursive", "fantasy")
    offenders = []
    for fam in _font_families(_app_qss()):
        low = fam.lower()
        for g in generic:
            if g in low:
                offenders.append(fam)
                break
    assert not offenders, f"QSS 使用了通用字体族（实测单个 +2.1s）：{offenders}"


def test_font_fallbacks_registered_at_program_level():
    """多字体回退能力必须仍然存在，只是换到了程序层。"""
    from app.ui.tokens_v2 import Typography

    assert Typography.family_fallbacks, "回退链为空 —— 主字体缺失时界面会退化成方框"
    # 回退链里不能有通用族（QFont.insertSubstitutions 里通用族同样有风险）
    for name in Typography.family_fallbacks:
        assert name.lower() not in ("sans-serif", "serif", "monospace")


def test_applied_font_on_widget_is_the_token_font():
    """QSS 生效后，控件实际字体应当就是令牌里的主字体。

    ⚠ 必须还原 QApplication 的全局样式：QApplication 是进程级单例，
    改了 styleSheet 不清回去会让后续测试在带主题的环境下运行
    （实测会造成「单跑通过、全量跑失败」的假回归）。
    """
    from PySide6.QtWidgets import QApplication, QLabel

    from app.ui.dark_theme import CursorDarkTheme
    from app.ui.tokens_v2 import Typography

    app = QApplication.instance() or QApplication([])
    prev_qss = app.styleSheet()
    prev_palette = app.palette()
    try:
        CursorDarkTheme.apply_to_application(app)

        label = QLabel("中文 Test 123")
        label.ensurePolished()

        expected = Typography.family.strip('"')
        assert label.font().family() == expected, (
            f"控件字体 {label.font().family()!r} 与令牌 {expected!r} 不一致"
        )
    finally:
        app.setStyleSheet(prev_qss)
        app.setPalette(prev_palette)


def test_typography_exposes_readable_stack():
    """font_stack() 供非 QSS 场景（QFont / 文档）使用，必须是完整可读栈。"""
    from app.ui.tokens_v2 import Typography

    stack = Typography.font_stack()
    assert "Microsoft YaHei UI" in stack
    assert stack.count(",") >= 1, "完整字体栈至少应包含主字体 + 回退"
