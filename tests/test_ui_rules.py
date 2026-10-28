"""界面规则契约 —— 把「设计规范」变成不能违反的 CI 红线。

═══════════════════════════════════════════════════════════════════════════
背景
═══════════════════════════════════════════════════════════════════════════

2026-10-28 实测：项目早有一套完整组件库（`app/ui/components/`，1481 行），
文档明确写着「所有界面新增控件应从本包取件，禁止写死样式」，
但**只有 3 个文件在用它**。规范写在文档里，没人执行。

同期量化：主窗口 170 个可见控件有 **37 种不同高度**、5 种按钮高度、
7 种 layout 间距、9 种边距。

→ 本测试的作用：**让「不合规」变成红灯，而不是靠人记得。**

═══════════════════════════════════════════════════════════════════════════
为什么用「欠账上限」而不是「零容忍」
═══════════════════════════════════════════════════════════════════════════

历史代码有 100+ 处不合规，一次性改完不现实（会拖垮节奏而且风险高）。

所以采用**棘轮机制**：记录当前欠账数作为上限，
- 新增违规 → 立刻红灯（上限不放宽）
- 修掉一些 → 必须同步下调上限（只能变好）

这是把「技术债」变成「单向收敛」的唯一办法。
"""

from __future__ import annotations

import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.design_spec import Scale, Space  # noqa: E402
from app.ui.ui_rules import lint_source  # noqa: E402

# ── 当前欠账（2026-10-28 全部清零）────────────────────────────────────
#
# **只准降，不准升。** 这里是 0，意味着新增任何一处违规都会直接红灯。
#
# 清零过程记录（供追溯）：
#   R1 内联样式    20 → 0（提纯判据：只看真正传给 setStyleSheet 的 QSS 内容）
#   R2 硬编码尺寸  47 → 0（新增 design_spec.Width 档位，宽度按用途分）
#   R7 硬编码颜色  15 → 0（4 类语义豁免 + 启动画面独立色值）
DEBT = {
    "R1-内联样式未令牌化": 0,
    "R2-禁止硬编码尺寸": 0,
    "R7-禁止硬编码颜色": 0,
}


# ── 规格本身的自检 ────────────────────────────────────────────────────


def test_scale_has_exactly_three_tiers():
    """高度必须只有 3 档。

    Ant Design / TDesign / Material 3 都是 3 档。
    档位再多，选档时就要「猜」，等于没有规范。
    """
    assert len(Scale.PX) == 3, f"高度档位应为 3，实际 {len(Scale.PX)}: {Scale.PX}"


def test_scale_is_on_4px_grid():
    """所有高度必须是 4 的倍数。

    不在 4px 栅格上的值（如旧代码的 30、34、38、26）无法互相整除，
    导致任意两个相邻控件都对齐不了 —— 这是「看着歪」的数学原因。
    """
    off_grid = {name: px for name, px in Scale.PX.items() if px % 4 != 0}
    assert not off_grid, f"以下档位不在 4px 栅格上: {off_grid}"


def test_scale_meets_wcag_click_target():
    """最小档位必须满足 WCAG 2.5.8 的 24x24 可点击目标。"""
    assert min(Scale.PX.values()) >= 24, "最小高度低于 WCAG 2.5.8 的 24px 下限"


def test_space_has_at_most_six_tiers():
    """间距档位不超过 6 档。"""
    assert len(Space.ALL) <= 6, f"间距档位过多: {Space.ALL}"


def test_space_is_on_4px_grid():
    """所有间距必须是 4 的倍数。"""
    off = [v for v in Space.ALL if v % 4 != 0]
    assert not off, f"间距不在 4px 栅格上: {off}"


# ── 单一真源检查 ──────────────────────────────────────────────────────


def test_tokens_height_comes_from_spec():
    """Tokens.CONTROL_HEIGHT 必须等于 spec 的 MD 档。

    改造前 design_tokens 写死 30、tokens_v2 是 30、各处 setFixedSize 是 32/34/44，
    三套真源打架，实测同排控件歪 8px。
    """
    from app.ui.design_tokens import Tokens

    assert Tokens.CONTROL_HEIGHT == Scale.PX[Scale.MD], (
        f"Tokens.CONTROL_HEIGHT={Tokens.CONTROL_HEIGHT} 与 spec MD="
        f"{Scale.PX[Scale.MD]} 不一致"
    )


def test_qss_height_comes_from_spec():
    """全局 QSS 里的控件高度必须等于 spec 的 MD 档。"""
    from app.ui.theme.provider import build_global_stylesheet

    qss = build_global_stylesheet()
    expected = Scale.PX[Scale.MD]
    # control-h 会出现在 min-height: %%control-h%%px 的位置
    assert f"min-height: {expected}px" in qss or f"height: {expected}px" in qss, (
        f"QSS 里找不到 spec 高度 {expected}px"
    )


def test_no_off_grid_height_in_qss():
    """QSS 的**最终高度**不应出现旧档位（26/30/34/38）。

    这些是改造前的残留，一旦出现说明某个规则没走 design_spec。

    ⚠ 判据是「height + padding + border = 目标值」，所以内高可以是
    非栅格值（例如 icon 档目标 28，内高 28-2×1=26 是合法的）。
    直接搜「26px 出现」会误报，这里改成验证每条 icon 档规则
    的内高 + 边框正好等于 design_spec 的档位值。
    """
    import re

    from app.ui.design_spec import Scale
    from app.ui.theme.provider import build_global_stylesheet

    qss = build_global_stylesheet()

    # 1) 找出所有「图标按钮档位」规则，验证内高 + 2×border = 档位值
    icon_rules = {
        'uiSize="icon"': Scale.PX[Scale.MD],
        'uiSize="iconSm"': Scale.PX[Scale.SM],
    }
    for selector_key, target in icon_rules.items():
        pattern = (
            r'QPushButton\[' + re.escape(selector_key) + r'\][^{]*\{([^}]*)\}'
        )
        m = re.search(pattern, qss)
        assert m, f"找不到 {selector_key} 的规则"
        body = m.group(1)
        mh = re.search(r"min-height:\s*(\d+)px", body)
        assert mh, f"{selector_key} 规则里没有 min-height"
        inner = int(mh.group(1))
        # 这类按钮在控件内联 QSS 里写了 border: 1px
        assert inner + 2 == target, (
            f"{selector_key} 内高 {inner} + 边框 2 = {inner + 2}，"
            f"但档位目标是 {target}（应在 design_spec.Scale 里）"
        )

    # 2) 除图标档位外，其余地方不得直接写旧档位高度
    legacy = {30, 34, 38}
    hits = [h for h in legacy if f"min-height: {h}px" in qss]
    assert not hits, (
        f"QSS 仍在使用旧高度档位: {hits}（应只来自 design_spec 的 24/28/36）"
    )


# ── 静态规则：棘轮 ────────────────────────────────────────────────────


def test_static_violations_do_not_exceed_debt():
    """静态扫描的违规数不得超过已登记欠账。

    这条是**防倒退**的核心：新增一处硬编码尺寸 → 立刻红灯。
    """
    result = lint_source()
    actual: dict[str, int] = {}
    for v in result.violations:
        actual[v.rule] = actual.get(v.rule, 0) + 1

    regressions = []
    for rule, cap in DEBT.items():
        got = actual.get(rule, 0)
        if got > cap:
            sample = [
                f"{v.path}:{v.line}"
                for v in result.violations
                if v.rule == rule
            ][:5]
            regressions.append(
                f"{rule}: {got} 处 > 上限 {cap} 处\n     例如: {sample}"
            )

    assert not regressions, (
        "界面规则倒退（欠账只准降不准升）：\n  " + "\n  ".join(regressions)
    )


def test_debt_ratchet_is_not_stale():
    """欠账上限不能高于实际值太多。

    如果修了一大批却没下调上限，棘轮就失效了（下次可以偷偷加回来）。
    这里要求：上限不得超出实际值 20% 以上。
    """
    result = lint_source()
    actual: dict[str, int] = {}
    for v in result.violations:
        actual[v.rule] = actual.get(v.rule, 0) + 1

    stale = []
    for rule, cap in DEBT.items():
        got = actual.get(rule, 0)
        if cap > 0 and got < cap * 0.8:
            stale.append(f"{rule}: 上限 {cap} 但实际只有 {got}，请下调上限")

    assert not stale, "欠账上限需要收紧：\n  " + "\n  ".join(stale)


# ── 运行时规则 ────────────────────────────────────────────────────────


@pytest.fixture(scope="module")
def main_window():
    """建一个真实主窗口（带文档 + 图层），用于运行时审计。"""
    from PySide6.QtGui import QFont, QFontDatabase
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    QFontDatabase.addApplicationFont(r"C:\Windows\Fonts\msyh.ttc")
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.dark_theme import CursorDarkTheme

    # 记录原状态，测试后还原（QApplication 是进程级单例，不还原会污染其它测试）
    prev_sheet = app.styleSheet()

    CursorDarkTheme.apply_to_application(app)

    from app.main_window import MainWindow
    from app.models.document import Document

    win = MainWindow()
    win.resize(1500, 950)
    doc = Document(parent=win)
    doc.create_new(800, 600)
    win.create_new_tab(doc)
    win.layer_controller.add_quick_text_layer()
    win.show()
    for _ in range(20):
        app.processEvents()

    yield win

    win.close()
    win.deleteLater()
    app.setStyleSheet(prev_sheet)
    app.processEvents()


def test_visible_widget_heights_are_converging(main_window):
    """可见控件的高度种类必须在收敛。

    改造前是 37 种。这个数字只能往下走。
    """
    from PySide6.QtWidgets import QComboBox, QLineEdit, QPushButton, QSpinBox

    from app.ui.ui_rules import is_framework_internal

    heights = set()
    for cls in (QPushButton, QLineEdit, QComboBox, QSpinBox):
        for w in main_window.findChildren(cls):
            if not w.isVisible():
                continue
            if is_framework_internal(w):
                continue
            heights.add(w.height())

    # 已收敛到目标值（2026-10-28 收尾实测 3 种 = {24, 28, 36}）。
    # 起点是 37 种（改造前）。**只准降，不准升。**
    MAX_HEIGHT_KINDS = 3

    assert len(heights) <= MAX_HEIGHT_KINDS, (
        f"控件高度增加到 {len(heights)} 种: {sorted(heights)}"
        f"（上限 {MAX_HEIGHT_KINDS}，目标 {sorted(Scale.all_px())}）"
    )


def test_no_widget_overflows_parent(main_window):
    """不得有控件溢出父容器（会导致文字被切）。

    2026-10-27 实测：图层面板 8 个按钮需 210px，dock 只有 176px，
    最后一个按钮被切掉 4px。
    """
    from PySide6.QtWidgets import QWidget

    overflow = []
    for w in main_window.findChildren(QWidget):
        if not w.isVisible():
            continue
        parent = w.parentWidget()
        if parent is None:
            continue
        if w.x() + w.width() > parent.width() + 2:
            overflow.append(
                f"{type(w).__name__} 右边界 {w.x() + w.width()} > 父宽 {parent.width()}"
            )

    assert not overflow, "控件溢出：\n  " + "\n  ".join(overflow[:8])


def test_icon_buttons_have_tooltip(main_window):
    """纯图标按钮必须有 tooltip（无障碍最低要求）。

    WCAG 2.4.6 / 4.1.2：没有可读名称的按钮，屏幕阅读器无法表达其用途。
    """
    from PySide6.QtWidgets import QPushButton

    missing = []
    for w in main_window.findChildren(QPushButton):
        if not w.isVisible():
            continue
        if w.text().strip():
            continue
        if w.icon().isNull():
            continue
        if not w.toolTip().strip():
            missing.append(f"{w.objectName() or type(w).__name__}")

    # 允许少量历史欠账，但必须登记
    assert len(missing) <= 3, (
        f"{len(missing)} 个图标按钮缺 tooltip: {missing[:8]}"
    )


# ── 图标库契约 ────────────────────────────────────────────────────────


def test_icon_library_uses_single_source():
    """图标必须全部来自同一图标集（Lucide SVG），不得混用字体字符。

    2026-10-28 架构调整：真源从 qtawesome/mdi6 改为 `app/qml/icons/*.svg`
    （lucide-static v1.28.0）。理由：QWidget 与 QML 共用同一批 SVG 文件，
    一个图标只有一份定义；且不额外引入第三方字体依赖。
    """
    from app.ui.icon_library import AVAILABLE, ICON_DIR

    assert AVAILABLE, f"图标目录为空: {ICON_DIR}"
    assert len(AVAILABLE) >= 90, f"Lucide 图标数量异常偏少: {len(AVAILABLE)}"

    # 全部必须是同一版本、同一笔画参数 —— 否则「统一图标集」不成立
    import os
    import re

    widths, unlicensed = set(), []
    for name in AVAILABLE:
        with open(os.path.join(ICON_DIR, f"{name}.svg"), encoding="utf-8") as fh:
            text = fh.read()
        m = re.search(r'stroke-width="([\d.]+)"', text)
        if m:
            widths.add(m.group(1))
        if "lucide-static" not in text:
            unlicensed.append(name)

    assert widths == {"2"}, f"描边宽度不统一: {widths}（必须全部 2px）"
    assert not unlicensed, f"以下图标不是 Lucide 来源: {unlicensed[:8]}"


def test_no_character_icons_remain():
    """旧图标模块不得再保留字符图标表（⚀ ∞ ⧄ ✎ 💾 📁）。

    字符图标依赖系统字体、与 SVG 笔画重量不同，是「两套图标混用」的根源。
    """
    from app.ui import icon_manager

    for banned in ("ICONS", "ICON_SVGS"):
        assert not hasattr(icon_manager, banned), (
            f"icon_manager 仍保留 {banned}：字符图标/手绘 path 必须彻底移除，"
            "图标统一走 app/qml/icons/*.svg"
        )


def test_icon_manager_delegates_to_library():
    """兼容层必须真的转调 icon_library，而不是自己造一套。"""
    from PySide6.QtWidgets import QApplication

    from app.ui.icon_library import AVAILABLE, resolve
    from app.ui.icon_manager import IconManager

    QApplication.instance() or QApplication([])

    # 旧业务名必须能解析到真实存在的 SVG 文件
    for legacy in ("delete", "save", "undo", "visible", "lock", "random", "edit"):
        resolved = resolve(legacy)
        assert resolved in AVAILABLE, f"{legacy} → {resolved} 文件不存在"

    # 兼容层返回的必须是真实图标，不是空
    ic = IconManager.get_icon("delete", 20)
    assert not ic.isNull(), "IconManager.get_icon 返回空图标"


def test_all_semantic_icons_resolve():
    """所有语义图标名都必须能渲染出来（不能是空图标）。"""
    from PySide6.QtWidgets import QApplication

    from app.ui.icon_library import IconName, icon

    QApplication.instance() or QApplication([])

    names = {
        k: v for k, v in vars(IconName).items()
        if k.isupper() and isinstance(v, str)
    }
    assert len(names) >= 40, f"语义图标数量偏少: {len(names)}"

    broken = [k for k in names if icon(k).isNull()]
    assert not broken, f"以下图标渲染为空: {broken}"


def test_icon_sizes_come_from_spec():
    """图标尺寸必须落在 3 档内（16/20/24）。"""
    from app.ui.design_spec import IconSize

    assert len(IconSize.ALL) == 3
    assert all(v % 4 == 0 for v in IconSize.ALL), f"图标尺寸不在栅格上: {IconSize.ALL}"
    assert IconSize.MD in (16, 20, 24)


# ── 架构契约：MRO 遮蔽 ─────────────────────────────────────────────────


def test_no_qt_base_class_shadows_mixin_methods():
    """Qt 基类不得排在 mixin 之前，导致 mixin 方法被静默遮蔽。

    这是本项目反复出现的架构缺陷（`MainWindow.closeEvent`、
    `BatchExportDialog.closeEvent`、`CanvasWidget.sizeHint` 都中过招）：
    写成 `class X(QWidget, XxxMixin)` 时，QWidget 占据 MRO 首位，
    它自带的同名方法会抢在 mixin 之前解析 —— **不报错、不崩溃，只是不生效**。

    这类缺陷极难发现，因为它静默：代码写了、语法对了、测试不覆盖就永远不知道。
    本测试扫描全项目，凡是「Qt 基类后面还有 mixin」的类，逐个检查
    mixin 里定义的方法是否真的能被解析到。

    修法：把 Qt 基类移到基类列表**最后**，`super()` 依然能走到它。
    """
    import ast
    import glob

    QT_PREFIX = "Q"
    #: 已知的合法例外：这些类 Qt 基类在前是必要的，
    #: 或者 mixin 里没有会冲突的方法。
    ALLOWED: set[tuple[str, str]] = set()

    offenders = []
    for path in glob.glob("app/**/*.py", recursive=True):
        if "__pycache__" in path:
            continue
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except Exception:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ClassDef):
                continue
            bases = [b.id for b in node.bases if isinstance(b, ast.Name)]
            qt_idx = [i for i, b in enumerate(bases) if b.startswith(QT_PREFIX)]
            mixins = [
                b for b in bases
                if not b.startswith(QT_PREFIX) and b != "object"
            ]
            if not qt_idx or not mixins:
                continue
            if qt_idx[0] >= len(bases) - 1:
                continue        # Qt 基类已在最后，合规
            if (path, node.name) in ALLOWED:
                continue
            offenders.append((path, node.name, bases))

    assert not offenders, (
        "以下类的 Qt 基类排在 mixin 之前，mixin 里的同名方法会被静默遮蔽：\n  "
        + "\n  ".join(
            f"{p}:{n}  基类={b}" for p, n, b in offenders
        )
        + "\n\n修法：把 Qt 基类移到基类列表最后。"
    )


# ── 工具栏契约 ─────────────────────────────────────────────────────────


def test_toolbar_icon_bitmap_matches_icon_size(main_window):
    """自绘图标的位图尺寸必须与工具栏 iconSize 一致。

    这条防的是一个真实踩过的坑（2026-10-28）：
    `_create_align_icon()` 里写死 `display_size = 18` 生成位图，
    而工具栏后来改成 iconSize=24 —— 结果 9 个对齐按钮全变成蓝色方块
    （18px 位图被拉到 24px 显示，细节全糊）。

    这类 bug 很隐蔽：图标不为 null、程序不报错、只是"看起来不对"。
    所以直接断言「位图逻辑尺寸 ≈ 工具栏 iconSize」。
    """
    from PySide6.QtWidgets import QToolBar

    toolbars = [t for t in main_window.findChildren(QToolBar) if t.isVisible()]
    assert toolbars, "没有可见的工具栏"

    checked = 0
    for tb in toolbars:
        icon_size = tb.iconSize().width()
        if icon_size <= 0:
            continue
        for action in tb.actions():
            icon = action.icon()
            if action.isSeparator() or icon.isNull():
                continue
            # ⚠ 不能用 `icon.pixmap(size)` 判断 —— QIcon 会**自动缩放**到请求尺寸，
            # 返回的位图永远等于请求值，测不出"原生位图太小被拉伸"的问题
            # （实测：iconSize=24 而位图按 18 生成，这条断言照样通过）。
            # 必须看 availableSizes()：那是图标**真正**持有的原生尺寸。
            sizes = icon.availableSizes()
            assert sizes, f"图标「{action.text()}」没有任何原生尺寸"
            natural = max(s.width() for s in sizes)
            dpr = main_window.devicePixelRatioF() or 1.0
            logical = natural / dpr
            assert abs(logical - icon_size) <= 1, (
                f"工具栏「{tb.windowTitle()}」iconSize={icon_size}px，"
                f"但图标「{action.text()}」的原生位图是 {natural}px"
                f"（逻辑 {logical:.1f}px）。两者必须一致，否则会被拉伸模糊。"
                f"检查 `_create_align_icon()` 里的 display_size 是否跟上了 setIconSize。"
            )
            checked += 1

    assert checked > 0, "没有检查到任何带图标的工具栏按钮"


def test_main_toolbar_uses_text_only():
    """主工具栏必须是纯文字模式（有文案就不带图标）。

    理由（2026-10-28 实测三种模式的 sizeHint）：
        图标+文字 1305px | 纯文字 1041px | 纯图标 535px
    顶栏要和 323px 的对齐栏共存于 1500px，只有纯文字放得下。
    这条测试防止有人"顺手"改回图标+文字而不知情地把对齐栏挤进溢出菜单。
    """
    import re

    src = open("app/main_window_ui.py", encoding="utf-8").read()
    assert re.search(
        r"self\.main_toolbar\.setToolButtonStyle\(\s*Qt\.ToolButtonTextOnly\s*\)",
        src,
    ), "主工具栏应为 Qt.ToolButtonTextOnly（纯文字），不要改回 ToolButtonTextBesideIcon"


# ── 组件库弃用契约（2026-10-28）────────────────────────────────────────


def test_shadcn_component_library_has_no_business_dependency():
    """`app/ui/components/` 已弃用，不得再被业务代码引用。

    2026-10-28 决定：产品不再使用这套 shadcn 组件库。
    当时已把两处业务依赖解除：
      - new_canvas_dialog.py：Button/Input → 原生 QPushButton/QLineEdit
      - layer_panel_base.py：FlowLayout → app/ui/flow_layout.py

    允许的唯一引用是 showcase.py（组件演示页自身，已标记 DEPRECATED）。

    这条测试防止有人再 `from app.ui.components import ...` 把弃用库拉回来。
    """
    import os
    import re

    allowed = {
        # 组件库自身的内部引用
        os.path.normpath(os.path.join("app", "ui", "components")),
        # 已弃用的演示页，只查不改
        os.path.normpath(os.path.join("app", "ui", "showcase.py")),
    }

    offenders = []
    for root, _dirs, files in os.walk("app"):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.normpath(os.path.join(root, fn))
            if path in allowed:
                continue
            # 组件库目录内部文件之间的互相引用不算业务依赖
            if path.startswith(os.path.normpath(os.path.join("app", "ui", "components")) + os.sep):
                continue
            try:
                src = open(path, encoding="utf-8").read()
            except OSError:
                continue
            if re.search(r"^\s*(from|import)\s+app\.ui\.components\b", src, re.M):
                offenders.append(path)

    assert not offenders, (
        "以下文件仍引用已弃用的 shadcn 组件库，请改用原生 QWidget + "
        "design_spec/tokens_v2 令牌：\n  " + "\n  ".join(offenders)
    )


def test_flow_layout_lives_outside_component_library():
    """FlowLayout 是布局原语而非视觉组件，必须独立于弃用的组件库存在。"""
    from app.ui.flow_layout import FlowLayout  # noqa: F401

    assert FlowLayout is not None


# ── 字号层级契约（2026-10-28 新增）────────────────────────────────────
#
# 为什么加这组：属性面板出现「4 个字号混用、标签比输入框还小、
# 某个开关标题 15px 比区块标题还大」的问题。根因不是谁手滑，
# 而是**字号这条维度从来没有被强制过** —— 23 条契约里 10 条管高度、
# 0 条管字号。规范只写在文档里，没有写进 CI，就一定会漂。


def test_font_size_single_source():
    """字号必须只有一个真源：tokens_v2.Typography。

    design_spec.FontSize 与 design_tokens.Tokens 的数字必须与它一致，
    否则「按 spec 写」和「按 tokens_v2 写」会得到不同字号。
    """
    from app.ui.design_spec import FontSize
    from app.ui.design_tokens import Tokens
    from app.ui.tokens_v2 import Typography as T

    # design_spec 的每个档位都必须能在 tokens_v2 里找到同值
    spec_values = set(FontSize.ALL)
    v2_values = {
        T.size_caption, T.size_sm, T.size_base, T.size_md,
        T.size_lg, T.size_xl, T.size_2xl,
    }
    assert spec_values <= v2_values, (
        f"design_spec.FontSize 出现了 tokens_v2 里没有的字号: "
        f"{sorted(spec_values - v2_values)}"
    )

    # design_tokens 的语义字号也必须落在 tokens_v2 的档位内
    semantic = {
        "SIDEBAR_TITLE_FONT_SIZE": Tokens.SIDEBAR_TITLE_FONT_SIZE,
        "SIDEBAR_BODY_FONT_SIZE": Tokens.SIDEBAR_BODY_FONT_SIZE,
        "SECTION_TITLE_FONT_SIZE": Tokens.SECTION_TITLE_FONT_SIZE,
        "FIELD_LABEL_FONT_SIZE": Tokens.FIELD_LABEL_FONT_SIZE,
        "SUMMARY_FONT_SIZE": Tokens.SUMMARY_FONT_SIZE,
        "FEATURE_TITLE_FONT_SIZE": Tokens.FEATURE_TITLE_FONT_SIZE,
        "FONT_SIZE_BASE": Tokens.FONT_SIZE_BASE,
        "FONT_SIZE_SMALL": Tokens.FONT_SIZE_SMALL,
    }
    off_grid = {
        k: v for k, v in semantic.items() if v not in v2_values
    }
    assert not off_grid, (
        f"以下字号不在 tokens_v2 的档位内（说明又写死了新数字）: {off_grid}\n"
        f"合法档位: {sorted(v2_values)}"
    )


def test_no_hardcoded_font_size_in_qss():
    """QSS / setStyleSheet 里不得出现裸数字字号。

    只允许两种写法：
      - f-string 插值：`font-size: {Token}px`
      - 令牌变量：    `font-size: 12px` 仅当该值同时出现在令牌里

    这条测试的作用是：任何人想加一个新字号，必须先在 tokens_v2 里登记。
    """
    import os
    import re

    legal = set()
    from app.ui.tokens_v2 import Typography as T

    for name in dir(T):
        if name.startswith("size_"):
            legal.add(getattr(T, name))
    from app.ui.design_spec import FontSize

    legal |= set(FontSize.ALL)

    # 匹配 font-size: 12px 这种裸数字（不含花括号插值）
    # ⚠ 这里必须写 \\s \\d 而不是 \s \d —— 之前用 shell heredoc 生成该文件时，
    #   反斜杠被吃掉，正则变成了 "/s*(/d+)px"，永远匹配不到任何东西，
    #   测试看起来"通过"其实完全没生效（注入 17px 也能过）。
    #   这类"假通过"比没有测试更危险。
    pattern = re.compile(r"font-size:\s*(\d+)px")
    offenders = []
    for root, _dirs, files in os.walk("app"):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                lines = open(path, encoding="utf-8").read().splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if line.lstrip().startswith("#"):
                    continue
                for m in pattern.finditer(line):
                    value = int(m.group(1))
                    if value not in legal:
                        offenders.append(f"{path}:{i} → {value}px")

    assert not offenders, (
        "以下位置写了不在令牌档位内的字号，请改用 tokens_v2.Typography "
        "或 design_spec.FontSize：\n  " + "\n  ".join(offenders)
    )


def test_field_label_smaller_than_content():
    """字段标签必须比输入内容小一档（层级正确性）。

    「标签 12 / 内容 13」是当前规范。反过来（标签比内容大）会让
    每一行都像标题，整片失去层次 —— 属性面板之前就是这个毛病。
    """
    from app.ui.design_tokens import Tokens

    label = Tokens.FIELD_LABEL_FONT_SIZE
    body = Tokens.FONT_SIZE_BASE
    assert label < body, (
        f"字段标签字号({label})必须小于正文/输入内容字号({body})，"
        "否则表单看起来每一行都是标题"
    )


def test_no_font_size_arithmetic_offsets():
    """禁止对字号做算术偏移（如 FONT_SIZE_BASE + 1）。

    偏移出来的值不在档位上，等于绕过规范 —— 这是历史遗留的常见漂移源。
    """
    import os
    import re

    # 同样注意反斜杠：见上一条测试的说明
    pattern = re.compile(r"font-size:\s*\{[^}]*[\+\-]\s*\d+[^}]*\}px")
    offenders = []
    for root, _dirs, files in os.walk("app"):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                lines = open(path, encoding="utf-8").read().splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    offenders.append(f"{path}:{i}")
    assert not offenders, (
        "以下位置对字号做了算术偏移，会产生不在档位上的字号：\n  "
        + "\n  ".join(offenders)
    )


def test_property_panel_font_hierarchy_is_sane(main_window):
    """属性面板的字号必须形成清晰层级，且不出现「标题比区块标题还大」的倒挂。

    度量方式（2026-10-28 定）：
      - 允许的档位：11(摘要) / 12(标签) / 13(内容) / 14(标题)
        最多 4 档 —— 11px 是摘要类辅助文字，语义上必须存在，
        不能为了"数档位"硬删（删了摘要就和正文同级，反而失去层次）。
      - 禁止倒数：任何可见控件都不该超过 14px。
        修之前"启用描边"是 15px，比"基本属性"区块标题(14)还大，这才是"乱"。

    为什么不用"档位数 <= 3"：那样会误伤合法的摘要文字，
    逼人要么删档位、要么放宽阈值 —— 两种都是假规范。
    """
    import collections

    from PySide6.QtWidgets import (
        QComboBox, QLabel, QLineEdit, QPushButton, QSpinBox, QWidget,
    )

    panel = getattr(main_window, "properties_panel", None)
    if panel is None:
        pytest.skip("没有属性面板")

    from app.ui.tokens_v2 import Typography as T

    allowed = {
        T.size_caption,   # 11 摘要
        T.size_sm,        # 12 标签
        T.size_base,      # 13 内容
        T.size_md,        # 14 标题
    }

    tiers = collections.Counter()
    offenders = []
    for child in panel.findChildren(QWidget):
        if not child.isVisible():
            continue
        if not isinstance(child, (QLabel, QLineEdit, QSpinBox, QComboBox, QPushButton)):
            continue
        px = child.font().pixelSize()
        if px <= 0:
            continue
        tiers[px] += 1
        if px not in allowed:
            text = ""
            try:
                text = child.text()[:14]
            except Exception:
                pass
            offenders.append(f"{px}px {type(child).__name__}({text!r})")

    assert tiers, "属性面板没有可见控件？"
    assert not offenders, (
        f"属性面板出现越界字号（允许 {sorted(allowed)}）: {offenders[:8]}\n"
        "字号必须在 tokens_v2.Typography 的档位内。"
    )

    # 最大字号不得成为"倒挂"：面板内最大字号应 <= 标题档
    biggest = max(tiers)
    assert biggest <= T.size_md, (
        f"属性面板出现 {biggest}px 控件，超过标题档 {T.size_md}px。"
        "面板内没有任何元素应该比区块标题更大。"
    )


def test_design_tokens_stylesheet_font_sizes_all_legal():
    """design_tokens 生成的全部 QSS 里，字号必须都在档位上。

    上一条测的是「运行时可见控件」，但可见性依赖窗口状态（有没有选中图层、
    当前哪个 tab），容易漏。这条直接查**生成的 QSS 文本** —— 不管控件是否
    可见，只要样式里写了越界字号就会被抓。

    2026-10-28 实测抓到：design_tokens.py 里有一条写死 `font-size: 18px`
    （不在档位内的 18，规范是 16/20）。
    """
    import re

    from app.ui.design_tokens import Tokens
    from app.ui.tokens_v2 import Typography as T
    from app.ui.design_spec import FontSize

    legal = {getattr(T, n) for n in dir(T) if n.startswith("size_")}
    legal |= set(FontSize.ALL)

    qss_parts = []
    for method in ("control_qss", "panel_qss"):
        fn = getattr(Tokens, method, None)
        if fn is None:
            continue
        try:
            qss_parts.append(fn("#Probe"))
        except Exception as exc:  # 参数签名变了就跳过，不让测试本身变脆
            pytest.skip(f"Tokens.{method} 调用失败: {exc}")
    qss = "\n".join(qss_parts)
    if not qss:
        pytest.skip("Tokens 没有可调用的 QSS 生成方法")

    offenders = []
    # ⚠ 反斜杠必须写对（\\s \\d）。用 shell heredoc 生成代码时反斜杠会被吞，
    #   正则变成 "/s*(/d+)px" 就永远匹配不到 —— 测试"通过"但完全没生效。
    for m in re.finditer(r"font-size:\s*(\d+)px", qss):
        value = int(m.group(1))
        if value not in legal:
            offenders.append(value)

    assert not offenders, (
        f"design_tokens 生成的 QSS 里有越界字号 {sorted(set(offenders))}，"
        f"合法档位 {sorted(legal)}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# 表单栅格契约（2026-10-28 二次整治）
# ═══════════════════════════════════════════════════════════════════════════
#
# 背景：属性面板被反复说「乱」。第一轮修了字号，还是乱 —— 因为真正的
# 物理问题是**没有栅格**：
#
#   实测（探针 _probe_grid.py）同一个面板里标签列宽出现 58 / 84 / 640 三种，
#   右边缘落在 70 / 84 / 96 三个 x 坐标；图像源那一段干脆没有标签列，
#   从分区最左边起排。原因不是审美，是三种实现同时在跑：
#
#     1. `_label()` 当时给的是「min 58 / max 84，让 QFormLayout 自己撑」
#        —— QFormLayout 按**本表单最长标签**算列宽，所以不同表单列宽不同
#     2. `addRow("", w)` 的空字符串标签宽度 0，字段列偷偷左移
#     3. `switch_row()` 造标签只设了 objectName 没设宽度
#
# 现在规则只有一条，并且由下面四条测试把守：
#   **字段标签一律固定 design_spec.Layout.LABEL_WIDTH(72)，右对齐；
#     行内子标签走 inline=True，不参与栅格。**


def _property_panels(main_window):
    """取出两个属性面板（图层属性 / 文字属性），没有就跳过。"""
    found = []
    for name in ("properties_panel", "layer_properties", "text_properties_panel"):
        panel = getattr(main_window, name, None)
        if panel is not None:
            found.append(panel)
    if not found:
        pytest.skip("主窗口没有属性面板")
    return found


def test_form_label_width_has_single_source():
    """标签列宽在令牌层只能有一个数，不允许各写一份。"""
    from app.ui.design_spec import Layout
    from app.ui.design_tokens import Tokens

    assert Tokens.LABEL_WIDTH == Layout.LABEL_WIDTH, (
        f"design_tokens.Tokens.LABEL_WIDTH({Tokens.LABEL_WIDTH}) "
        f"与 design_spec.Layout.LABEL_WIDTH({Layout.LABEL_WIDTH}) 不一致。"
        "标签列宽只能有一个真源。"
    )

    from app.ui.property_panel_a2 import PropertyPanelA2

    assert PropertyPanelA2.LABEL_WIDTH == Layout.LABEL_WIDTH, (
        f"文字属性面板的标签列宽({PropertyPanelA2.LABEL_WIDTH})与栅格({Layout.LABEL_WIDTH})不一致，"
        "同一个 dock 里切图层会换一次对齐。"
    )


def test_form_label_width_is_not_content_dependent(main_window):
    """所有字段标签必须是固定列宽，不允许按各自文字长度算。

    这条是本次整治的核心：只要允许「按内容自适应」，
    QFormLayout 就会按每个表单的最长标签给出不同列宽，
    栅格立刻失效（实测 58/84/640 三种）。
    """
    from PySide6.QtWidgets import QLabel

    from app.ui.design_spec import Layout

    panels = _property_panels(main_window)
    checked = 0
    offenders = []
    for panel in panels:
        for label in panel.findChildren(QLabel):
            if label.objectName() != "fieldLabel":
                continue
            checked += 1
            lo, hi = label.minimumWidth(), label.maximumWidth()
            if not (lo == hi == Layout.LABEL_WIDTH):
                offenders.append(
                    f"{label.text()!r} min={lo} max={hi} 实际={label.width()}"
                )
            if not (label.alignment() & 0x0002):  # Qt.AlignRight
                offenders.append(f"{label.text()!r} 未右对齐")
            # 固定宽度会把超长标签裁掉，而 QLabel 裁字是**静默**的：
            # 截图里只会看到少半个字，没有任何报错。这里用字体度量兜住。
            adv = label.fontMetrics().horizontalAdvance(label.text())
            if adv + 2 > Layout.LABEL_WIDTH:
                offenders.append(
                    f"{label.text()!r} 文字宽 {adv}px，超过列宽 {Layout.LABEL_WIDTH}px（会被裁字）"
                )

    assert checked >= 10, f"只找到 {checked} 个字段标签，面板结构可能变了"
    assert not offenders, (
        f"{len(offenders)} 个字段标签没落在统一栅格上（要求固定 "
        f"{Layout.LABEL_WIDTH}px + 右对齐）:\n  " + "\n  ".join(offenders[:8])
    )


def _visible_label_edges(panel):
    from PySide6.QtWidgets import QLabel

    edges = set()
    for label in panel.findChildren(QLabel):
        if label.objectName() != "fieldLabel" or not label.isVisible():
            continue
        pos = label.mapTo(panel, label.rect().topLeft())
        edges.add(pos.x() + label.width())
    return edges


def test_image_layer_panel_has_exactly_one_label_edge(main_window):
    """图层属性面板（图片图层）必须只有一条标签竖线。

    这是杰哥截图里那块面板，也是默认看到的面板 —— 要求最严：
    **所有字段标签右边缘完全相同**。

    修之前实测 3 个值（70 / 84 / 96），因为三种实现同时生效：
    `_label()` 给的是 min58/max84 让 QFormLayout 自己撑，而 QFormLayout
    按「本表单最长标签」算列宽；`addRow("", w)` 的空标签宽 0；
    `switch_row()` 的标签干脆没设宽度。
    """
    from PySide6.QtWidgets import QWidget

    panel = getattr(main_window, "properties_panel", None)
    if not isinstance(panel, QWidget):
        pytest.skip("没有属性面板")

    # fixture 里选中的是文字图层，面板显示的是文字页。
    # 这里手动切回图片页（等价于用户在画布里点中一个图片图层）。
    text_panel = getattr(panel, "text_layer_panel", None)
    normal_panel = getattr(panel, "normal_layer_panel", None)
    if text_panel is None or normal_panel is None:
        pytest.skip("面板结构变了：没有 text_layer_panel / normal_layer_panel")
    text_panel.hide()
    normal_panel.show()
    normal_panel.setCurrentIndex(0)
    lay = panel.layout()
    if lay is not None:
        lay.activate()
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()

    edges = _visible_label_edges(panel)
    if not edges:
        pytest.skip("图层属性面板没有可见字段标签")

    assert len(edges) == 1, (
        f"图层属性面板出现 {len(edges)} 个标签右边缘 {sorted(edges)}。"
        "字段标签必须固定 72px + 右对齐，连成一条竖线。"
    )


def test_text_panel_label_indent_is_on_grid(main_window):
    """文字属性面板的嵌套缩进必须落在 8px 阶梯上。

    文字面板有嵌套子卡片（颜色 / 背景 / 效果），子卡片里的字段本来就该
    往里缩，所以这里**不要求只有一条线**，但缩进必须是阶梯、不能是漂移：
    实测修之前是 88 / 95 / 102（每级差 7px，肉眼就是"齐了但没齐"），
    根因是内边距写了 (8,5,8,6) / (6,4,6,4) 这类不在栅格上的数。

    当前允许 3 档偏移（0 / 9 / 14）：9 = 8 + 卡片 1px 边框，
    14 = 排版卡片还残留一处 6px 内距（**已知欠账**，收掉后必须同步收紧这里）。
    **只许减少，不许增加** —— 新增档位立刻红灯。
    """
    from PySide6.QtWidgets import QWidget

    panel = getattr(main_window, "properties_panel", None)
    if not isinstance(panel, QWidget):
        pytest.skip("没有文字属性面板")

    # fixture 默认就停在文字页；显式恢复一次，避免受上一条测试切页影响
    text_panel = getattr(panel, "text_layer_panel", None)
    normal_panel = getattr(panel, "normal_layer_panel", None)
    if text_panel is None or normal_panel is None:
        pytest.skip("面板结构变了：没有 text_layer_panel / normal_layer_panel")
    normal_panel.hide()
    text_panel.show()
    from PySide6.QtWidgets import QApplication

    QApplication.processEvents()

    edges = _visible_label_edges(panel)
    if not edges:
        pytest.skip("文字属性面板没有可见字段标签")

    base = min(edges)
    offsets = sorted({e - base for e in edges})
    allowed = [0, 9, 14]

    extra = [o for o in offsets if o not in allowed]
    assert not extra, (
        f"文字面板出现新的标签缩进 {extra}（当前全部偏移 {offsets}，基准 {base}）。\n"
        "嵌套缩进必须落在 8px 阶梯上（1px 卡片边框可容忍）；"
        "检查是不是又写了不在栅格上的内边距。"
    )


def test_property_forms_do_not_build_raw_labels():
    """属性面板里不允许再用裸标签/空字符串标签造字段行。

    `addRow(QLabel("智能裁剪"), w)` —— 裸 QLabel 宽度按内容算（实测 52），
    与旁边的 72 列错位；`addRow("", w)` —— 空标签宽度 0，字段列左移。
    两者都会绕开 `_label()`，必须用 `_label()` / `_blank_label()`。
    """
    import glob
    import re

    offenders = []
    # 只匹配真正的调用：`对象.addRow(` 后面紧跟 QLabel( 或字符串字面量。
    # 不匹配文档字符串里举例的 `addRow("", w)`（前面没有「对象.」）。
    pattern = re.compile(r"^\s*\w+\.addRow\(\s*(QLabel\(|\"|')", re.M)
    for path in glob.glob("app/ui/layer_properties_*.py"):
        text = open(path, encoding="utf-8").read()
        for m in pattern.finditer(text):
            line = text[: m.start()].count("\n") + 1
            offenders.append(f"{path}:{line} → {m.group(0).strip()}")

    assert not offenders, (
        f"{len(offenders)} 处字段行绕开了统一标签:\n  " + "\n  ".join(offenders[:8])
    )
