"""启动画面契约测试：锁住"快出现"与"进度可信"这两条底线。

背景（2026-10-27 实测，见 .workbuddy/memory/2026-10-27.md）：
`MainWindow()` 冷启动要 3.5~5 秒，是 Qt 首次建原生窗口 + 676 控件首次布局
的固有成本，代码层优化不掉。启动画面的职责就是让这段等待可感知。

踩过的坑（都用测试锁住，防止被"顺手优化"回去）：
1. 在 `drawContents` 里逐帧画文字 → show() 从 1.1s 劣化到 5.1s
   （本机 2004 个字体族，每次排版都走字体解析）
2. 把文字放后台线程 → `thread.start()` 本身被阻塞 3.9s（抢字体锁）
3. hook 参数顺序写成 (text, percent) → 进度条收到字符串，彻底不动
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def _make_splash():
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    for path in (r"C:\Windows\Fonts\msyh.ttc",):
        QFontDatabase.addApplicationFont(path)
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.splash_screen import SplashScreen

    return SplashScreen()


def test_geometry_first_frame_is_cheap():
    """构造阶段不能包含文字渲染 —— 必须毫秒级完成。

    这是整个设计的命门：如果构造要 3 秒，启动画面就失去了存在意义。
    """
    import time

    t = time.time()
    splash = _make_splash()
    elapsed_ms = (time.time() - t) * 1000
    splash.close()

    assert elapsed_ms < 500, (
        f"启动画面构造耗时 {elapsed_ms:.0f}ms，超过 500ms。"
        "很可能有人把文字渲染搬回了 __init__（本机首次 drawText 要 1~4 秒）。"
    )


def test_advance_rejects_non_numeric_progress():
    """advance 收到非数字进度时必须自愈，不能让画面停住。"""
    splash = _make_splash()
    splash.advance(0.3)
    before = splash._progress

    # 模拟当初那个 bug：把文案当进度传进来
    splash.advance("正在构建状态栏…")  # type: ignore[arg-type]

    assert splash._progress == pytest.approx(before), (
        "非数字进度不应改变当前进度（应被丢弃，而不是崩溃或归零）"
    )
    splash.close()


def test_advance_never_goes_backwards():
    """进度只能前进。阶段乱序或重复调用都不能让进度条倒退。"""
    splash = _make_splash()
    splash.advance(0.6)
    splash.advance(0.2)   # 故意倒退
    assert splash._progress == pytest.approx(0.6)
    splash.close()


def test_advance_clamps_to_unit_range():
    """越界进度要被夹到 0~1，避免进度条画出画布外。"""
    splash = _make_splash()
    splash.advance(5.0)
    assert splash._progress <= 1.0

    splash2 = _make_splash()
    splash2.advance(-3.0)
    assert splash2._progress >= 0.0
    splash2.close()
    splash.close()


def test_creep_target_is_bounded():
    """蠕动上限必须紧跟真实进度，不能自己跑飞。

    蠕动是为了让长时间阻塞期看着"在动"，但绝不能跑到真实进度前面，
    否则就是骗用户。
    """
    splash = _make_splash()
    splash.advance(0.4)
    assert splash._creep_target <= 0.4 + 0.09, "蠕动上限超出真实进度太多"
    splash.close()


def test_splash_does_not_import_heavy_modules():
    """启动画面模块不能依赖主窗口/控制器等重模块（会拖慢首帧）。"""
    source = (
        __file__.rsplit("tests", 1)[0] + "app/splash_screen.py"
    )
    with open(source, encoding="utf-8") as fh:
        text = fh.read()

    forbidden = ("app.main_window", "app.controllers", "app.models.document")
    for name in forbidden:
        assert f"from {name}" not in text, (
            f"splash_screen.py 不应导入 {name} —— 会把主窗口的初始化成本搬到首帧之前"
        )


def test_splash_colors_do_not_drift_from_theme():
    """启动画面里硬编码的色值必须与主题一致（防止两边漂移）。

    为什么允许硬编码：SplashScreen 在 `main.py:342` 创建，此时主题尚未加载
    （`setup_fixed_theme` 更晚调用），所以它必须自带色值、能独立画出来。
    这不违反「禁止硬编码颜色」的初衷 —— 那条规则防的是**样式漂移**，
    而这里的风险不是"用了字面量"，是"字面量与主题不一致"。

    所以这条测试锁的是**一致性**，不是禁止硬编码。
    """
    from app import splash_screen

    #: (splash 常量名, dark_theme 里的属性名)
    PAIRS = [
        ("_BG", "BACKGROUND_PRIMARY"),
        ("_FG", "TEXT_PRIMARY"),
        ("_ACCENT", "ACCENT_PRIMARY"),
    ]

    from app.ui.dark_theme import CursorDarkTheme

    for splash_attr, theme_attr in PAIRS:
        splash_color = getattr(splash_screen, splash_attr)
        theme_value = getattr(CursorDarkTheme, theme_attr, None)
        assert theme_value is not None, (
            f"dark_theme 里找不到 {theme_attr}，契约已失效，需要同步更新本测试"
        )
        assert splash_color.name().lower() == str(theme_value).lower(), (
            f"{splash_attr} = {splash_color.name()}，"
            f"但主题 {theme_attr} = {theme_value} —— 启动画面与主题已经漂移"
        )
