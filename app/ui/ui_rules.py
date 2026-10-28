"""界面规则执行器 —— 把「设计规范」变成「代码必须遵守的约束」。

═══════════════════════════════════════════════════════════════════════════
为什么需要这个（而不是只写文档）
═══════════════════════════════════════════════════════════════════════════

2026-10-28 实测：项目早有一套完整组件库（`app/ui/components/`，1481 行，
文档明确写着「所有界面新增控件应从本包取件，禁止写死样式」），
但**只有 3 个文件在用它**，其余全部手写控件 + 内联 QSS。

→ 光有规范没用，必须能被**自动检查、自动报错**。

本模块提供三层防线：

1. **静态检查**（`lint_source`）：扫描源码，禁止内联样式、硬编码尺寸
2. **运行时检查**（`audit_widget_tree`）：遍历真实窗口，找出不合规的控件
3. **契约测试**（`tests/test_ui_rules.py`）：把上面两个变成 CI 红线

═══════════════════════════════════════════════════════════════════════════
规则清单
═══════════════════════════════════════════════════════════════════════════

R1  业务文件禁止 `setStyleSheet`（应走 variant / 全局 QSS）
R2  禁止 `setFixedHeight` / `setFixedWidth` / `setFixedSize` 写字面量
    （应从 design_spec.Scale / IconSize 取）
R3  可见控件的 height 必须落在 Scale 档位内
R4  可见控件的 width 不得溢出父容器
R5  layout spacing 必须落在 Space 档位内
R6  纯图标按钮必须有 tooltip（无障碍最低要求）
R7  禁止在业务文件写死十六进制颜色
"""

from __future__ import annotations

import ast
import os
import re
from dataclasses import dataclass, field

from app.ui.design_spec import Scale, Space


# ── 规则定义 ──────────────────────────────────────────────────────────


@dataclass
class Violation:
    """一条违规记录。"""

    rule: str
    path: str
    line: int
    detail: str

    def __str__(self) -> str:
        return f"[{self.rule}] {self.path}:{self.line}  {self.detail}"


#: 豁免文件：这些文件**就是**样式的定义处，允许写内联 QSS / 硬编码色值。
STYLE_OWNER_FILES = {
    "design_spec.py",
    "tokens_v2.py",
    "design_tokens.py",
    "dark_theme.py",
    "provider.py",
    "tokens.py",
    "visual_hierarchy.py",
    "theme_helpers.py",
    # 组件库自身的 QSS 兜底（它负责把 variant 翻译成 QSS）
    "button.py",
    "card.py",
    "input.py",
    "theme.py",
}

#: 色板数据：用户可选的颜色，不是样式
PALETTE_FILES = {"color_picker_dialog_a2.py"}

#: 工具自身不纳入扫描：本文件里到处是「反例代码」字符串
#: （文档、注释、测试样例），扫自己只会自产自销一堆假违规。
SELF_EXEMPT = {"ui_rules.py"}

#: 语义不同、**不应**令牌化的颜色：值看起来像主题色，但语义完全是别的。
#:
#: 逐个说明（都实测确认过用途，不是"懒得改"）：
#:
#: - `add_text_layer_dialog_simple`：画在**用户任意选色**的色块上的文字，
#:   必须恒定纯白才能保证对比度。换成 `text_primary`(#F7F8F8) 在这个语境
#:   下不是"主色文字"，而是"任何底色上的文字" —— 语义不同。
#: - `icon_manager`：SVG 着色函数的**缺省参数值**，与主题无关。
#:   调用方不传色时用它兜底。
#: - `layer_properties_shape`：在任意底色上选深字/浅字的**亮度阈值配对**
#:   (#111214 / #F4F4F5)。这对值是算法常量，换成令牌会让配对漂移
#:   （text_primary 是 #F7F8F8 不是纯白，阈值就变了）。
#: - `components/forms.py`：`ColorSwatch` 构造函数的默认参数，不是样式。
SEMANTIC_COLOR_EXEMPT = {
    "add_text_layer_dialog_simple.py",
    "icon_manager.py",
    "layer_properties_shape.py",
    "forms.py",
}

#: 启动画面：色值**必须**硬编码。
#:
#: 技术约束不是偷懒：SplashScreen 在 `main.py:342` 创建，而主题在
#: `setup_fixed_theme()`（210 行定义，更晚调用）里才加载 ——
#: 启动画面必须能在主题模块可用之前就把自己画出来。
#: 色值在同文件顶部从 dark_theme 拷贝了一份并标注了来源，
#: `tests/test_splash_contract.py` 负责保证两边不会漂移。
BOOTSTRAP_COLOR_FILES = {"splash_screen.py"}

#: 已确认 0 引用的死代码（不改，但登记出来让范围可见）
DEAD_FILES = {
    "add_shaped_layer_dialog.py",
    "export_progress_dialog.py",
    "integrated_text_editor_dialog.py",
    "simple_text_editor_dialog.py",
    "preset_panel.py",
    "showcase.py",
}

#: 十六进制颜色
HEX_COLOR = re.compile(r"#[0-9A-Fa-f]{3,8}\b")

#: setFixedSize / setFixedHeight 里的裸数字
FIXED_SIZE_LITERAL = re.compile(
    r"setFixed(?:Height|Width|Size)\s*\(\s*(\d+)"
)

#: 判断一段内联 QSS 是否「已令牌化」：
#: 只要取值来自 Color / Tokens / VisualHierarchy / design_spec，就算合规。
_TOKENIZED_HINTS = (
    "Color.",
    "Tokens.",
    "VisualHierarchy",
    "vh.get_",
    "design_spec",
    "Scale.",
    "Space.",
    "Radius.",
    "FontSize.",
    "PropertyPanelA2.",
    "DialogA2.",
)


@dataclass
class LintResult:
    violations: list[Violation] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.violations

    def by_rule(self) -> dict[str, list[Violation]]:
        out: dict[str, list[Violation]] = {}
        for v in self.violations:
            out.setdefault(v.rule, []).append(v)
        return out

    def report(self, limit_per_rule: int = 8) -> str:
        if self.ok:
            return "界面规则检查通过，无违规。"
        lines = [f"发现 {len(self.violations)} 条违规："]
        for rule, items in sorted(self.by_rule().items()):
            lines.append(f"\n  {rule}（{len(items)} 条）")
            for v in items[:limit_per_rule]:
                lines.append(f"    {v.path}:{v.line}  {v.detail}")
            if len(items) > limit_per_rule:
                lines.append(f"    ...还有 {len(items) - limit_per_rule} 条")
        return "\n".join(lines)


# ── R1/R2/R7：静态检查 ────────────────────────────────────────────────


def _iter_ui_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d != "__pycache__"]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            if (fn in STYLE_OWNER_FILES or fn in PALETTE_FILES
                    or fn in DEAD_FILES or fn in BOOTSTRAP_COLOR_FILES
                    or fn in SELF_EXEMPT):
                continue
            yield os.path.join(dirpath, fn)


def _extract_qss_argument(lines: list[str], call_idx: int) -> str | None:
    """取出 `setStyleSheet(...)` 括号里的字符串字面量内容。

    只处理**直接传字面量**的情况（含 f-string）；参数是变量名时返回 None，
    由调用方回溯变量定义。这样判据就锚定在「这段 QSS 到底写了什么」，
    不会被邻近代码里的无关 token 误救。
    """
    import re as _re

    joined = "\n".join(lines[call_idx: call_idx + 24])
    m = _re.search(r"setStyleSheet\s*\(", joined)
    if not m:
        return None

    pos = m.end()
    # 跳过空白
    while pos < len(joined) and joined[pos] in " \t\n":
        pos += 1
    if pos >= len(joined):
        return None

    # 参数是裸变量名 → 交给调用方回溯
    ident = _re.match(r"[A-Za-z_][A-Za-z0-9_]*\s*\)", joined[pos:])
    if ident and not joined[pos] in "f\"'":
        return None

    # 取第一个字符串字面量（支持 f"..." / "..." / f"""...""" 等）
    quote_m = _re.match(r'f?(["\']{1,3})', joined[pos:])
    if not quote_m:
        return None
    q = quote_m.group(1)
    start = pos + quote_m.end()
    end = joined.find(q, start)
    if end < 0:
        return None
    return joined[start:end]


def _var_definition_is_tokenized(lines: list[str], call_idx: int) -> bool:
    """`setStyleSheet(变量)` 形式：回溯该变量的赋值块，判断是否用了令牌。

    典型写法：
        style = f\"\"\"
        QPushButton {{ background: {vh.get_color(...)}; }}
        \"\"\"
        button.setStyleSheet(style)

    令牌在变量定义处（在前面），而扫描窗口是往后取 12 行 —— 完全看不到。
    这不是"没令牌"，是判据的盲区。这里向前找 `变量名 = ` 或 `变量名 += `，
    取其所在的多行语句判断是否含令牌。
    """
    import re as _re

    line = lines[call_idx]
    m = _re.search(r"setStyleSheet\(\s*([A-Za-z_][A-Za-z0-9_]*)\s*\)", line)
    if not m:
        return False
    var = m.group(1)

    # 向前最多找 80 行（够覆盖任何构建 QSS 的方法）
    start = max(0, call_idx - 80)
    for idx in range(call_idx - 1, start - 1, -1):
        if _re.match(rf"\s*{_re.escape(var)}\s*(?:\+?=)", lines[idx]):
            # 取从赋值处到调用处之间的内容
            block = "\n".join(lines[idx: call_idx + 1])
            return any(hint in block for hint in _TOKENIZED_HINTS)
    return False


def _has_visual_literal(qss_window: str) -> bool:
    """内联 QSS 里是否写了**颜色**或**像素尺寸**字面量。

    这是 R1 从「不准用 setStyleSheet」放宽到「不准在内联里写死取值」的关键判据。

    出现以下任一，说明内联样式与主题脱钩，必须改：
    - 十六进制颜色 / rgb() / rgba()
    - 以 px 结尾的尺寸

    不算的（纯结构声明，无需令牌）：
    - `font-weight: bold`、`font-style: italic`
    - `background: transparent`、`border: none`
    - `text-align: center`
    """
    low = qss_window.lower()
    if HEX_COLOR.search(qss_window):
        return True
    if "rgb(" in low or "rgba(" in low:
        return True
    # 尺寸字面量：数字 + px（排除 % / em / 变量插值处）
    if re.search(r"\b\d+px\b", low):
        return True
    return False


def _docstring_lines(lines: list[str]) -> set[int]:
    """返回位于三引号字符串内部的行号集合（1-based）。

    用途：文档里经常出现 `setStyleSheet`、`#FFFFFF` 这类**说明性文字**，
    它们不是活代码。只靠"行首是 #" 判断会漏掉 docstring，造成误报
    （实测 `dialog_a2.py` 的模块文档就因此被当成违规）。

    实现用最朴素的配对计数：不解析语法树（那要引入 ast 全文解析、
    且注释里的三引号会让它困惑），只按出现次数累计开/闭。
    """
    inside: set[int] = set()
    open_triple = False
    for idx, line in enumerate(lines, 1):
        # 统计这一行里三引号的出现次数（包含 """ 和 ''' 两种）
        count = line.count('"""') + line.count("'''")
        if open_triple:
            inside.add(idx)
            if count % 2 == 1:
                open_triple = False
            continue
        if count % 2 == 1:
            inside.add(idx)
            open_triple = True
    return inside


def lint_source(root: str | None = None) -> LintResult:
    """静态扫描：禁止内联样式与硬编码尺寸。

    只对 `app/ui` 下的业务文件生效；样式定义文件与死代码豁免。
    """
    root = root or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "ui"
    )
    result = LintResult()

    for path in _iter_ui_files(root):
        rel = os.path.relpath(path, os.path.dirname(root))
        fname = os.path.basename(path)
        try:
            source = open(path, encoding="utf-8").read()
        except Exception:
            continue

        lines = source.splitlines()
        # 先算出哪些行位于多行字符串（docstring）内部。
        # 只看"行首是 #" 会漏掉文档字符串里提到 setStyleSheet 的说明性文字，
        # 那是纯注释，不是活代码 —— 实测 dialog_a2.py 的模块文档就因此误报。
        in_docstring = _docstring_lines(lines)

        for lineno, line in enumerate(lines, 1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if lineno in in_docstring:
                continue

            # R1：业务文件的内联样式必须已经令牌化。
            #
            # 注意判据不是「有没有 setStyleSheet」—— 有些场景（自绘控件、
            # 动态颜色）确实需要内联 QSS。真正的问题是**在内联里写死色值/尺寸**，
            # 那才是「第二套真源」。所以这里检查的是「有没有用令牌」。
            if "setStyleSheet" in line:
                # 只分析**真正传给 setStyleSheet 的那段 QSS**，不用"往后取 N 行"的
                # 大窗口 —— 那个做法有致命缺陷：窗口里只要碰巧出现 `Scale.` 这类
                # 子串（例如紧邻一行的 `setFixedSize(_Scale.PX[...])`），
                # 整段就被判为"已令牌化"，真违规被放过。
                #
                # 实测教训：注入 `setStyleSheet("color: #FF0000")` 后，
                # 因为后面跟着 `_Scale.PX` 的行，R1 报 0 —— 规则失效。
                qss_text = _extract_qss_argument(lines, lineno - 1)
                if qss_text is None:
                    # 传的是变量名，回溯其定义块
                    if _var_definition_is_tokenized(lines, lineno - 1):
                        continue
                    # 拿不到内容时退回整体判断（宁可不报，不误报）
                    qss_text = "\n".join(lines[lineno - 1: lineno + 12])

                if not any(hint in qss_text for hint in _TOKENIZED_HINTS):
                    # 文件级语义豁免（详见 SEMANTIC_COLOR_EXEMPT 的说明）。
                    # 这类文件里的颜色是「画在用户任意选色上的文字」或
                    # 「亮度阈值配对」，换了令牌语义就错了。
                    if fname in SEMANTIC_COLOR_EXEMPT:
                        # 但仍要检查尺寸字面量 —— 颜色可豁免，尺寸不行
                        if not re.search(r"\b\d+px\b", qss_text.lower()):
                            continue
                    # 「不涉及色值与尺寸」的内联样式不构成第二套真源。
                    #
                    # 例如 `font-weight: bold` / `background: transparent` /
                    # `border: none` —— 它们表达的是**结构意图**，不是设计取值，
                    # 没有对应的令牌可换（也没有必要为 bold 造一个令牌）。
                    #
                    # 真正危险的是内联里**写死了颜色或像素**：那会与主题脱钩，
                    # 换主题时不跟随。这类必须拦下。
                    if not _has_visual_literal(qss_text):
                        continue
                    result.violations.append(
                        Violation(
                            "R1-内联样式未令牌化",
                            rel,
                            lineno,
                            "内联 QSS 里的取值必须来自 Color/Tokens/design_spec，"
                            "不能写字面量",
                        )
                    )

            # R2：setFixedSize 等写字面量
            if FIXED_SIZE_LITERAL.search(line) and "Scale" not in line:
                result.violations.append(
                    Violation(
                        "R2-禁止硬编码尺寸",
                        rel,
                        lineno,
                        "改从 design_spec.Scale / IconSize 取档位",
                    )
                )

            # R7：硬编码颜色（只看 QSS 语境，避免误伤文档字符串）
            if fname in SEMANTIC_COLOR_EXEMPT:
                continue
            if HEX_COLOR.search(line) and (
                "color" in line.lower() or "background" in line.lower()
            ):
                result.violations.append(
                    Violation(
                        "R7-禁止硬编码颜色",
                        rel,
                        lineno,
                        "改从 tokens_v2.Color 取令牌",
                    )
                )

    return result


# ── R3/R4/R5/R6：运行时检查 ──────────────────────────────────────────


#: 框架自动生成的内部子控件 —— 高度由父控件决定，**不是**我们写的样式。
#:
#: 这些不纳入高度契约，否则统计口径失真、永远修不完：
#: - `qt_spinbox_lineedit`：QSpinBox 内部的输入行，高度 = SpinBox - 按钮区
#: - `qt_toolbar_ext_button`：QToolBar 的溢出按钮，Qt 自己创建
#: - 任何 QComboBox 内部的 QLineEdit：高度跟随 ComboBox
#:
#: 判断依据放在函数里而不是单个规则里，让审计和测试共用同一口径。
def is_framework_internal(widget) -> bool:
    """判断控件是否不参与尺寸契约。

    两类：
    1. **框架自动生成的内部子控件** —— 高度由父控件算法决定：
       - `qt_spinbox_lineedit`：QSpinBox 内部的输入行
       - `qt_toolbar_ext_button`：QToolBar 的溢出按钮
       - QComboBox / QSpinBox 内部的 QLineEdit
    2. **受限容器内的控件** —— 容器本身只有那么高，子控件必然被压缩：
       - QStatusBar 里的控件（状态栏 ~21px，放不下 28px 的控件）
    这两类改子控件没有意义，该改的是容器，而容器的尺寸另有语义。
    """
    name = widget.objectName()
    if name.startswith("qt_"):
        return True

    # 语义化方形控件：尺寸是**语义的一部分**，不是「控件高度档位」。
    # 典型：ColorIndicator（role=color-swatch）是 30×30 的颜料展示位，
    # 它必须是正方形，且边长由色块本身决定。压到 24/28 会破坏方形观感，
    # 也会和 COLOR_SWATCH_SIZE 契约冲突。
    if widget.property("role") == "color-swatch":
        return True

    parent = widget.parentWidget()
    # 往上找两层：状态栏里的控件通常被包一层容器 QWidget
    # （实测 QSpinBox ← QWidget ← QStatusBar），只看一层会漏。
    for _ in range(2):
        if parent is None:
            break
        ptype = type(parent).__name__
        # 输入型容器内部的编辑框：高度被容器钳制
        if ptype in ("QComboBox", "QSpinBox", "QDoubleSpinBox", "QDateEdit", "QTimeEdit"):
            return True
        # 状态栏：本身只有 ~21px 高，内部控件不可能达到 24/28/36
        if ptype == "QStatusBar":
            return True
        parent = parent.parentWidget()
    return False


def audit_widget_tree(window) -> LintResult:
    """遍历真实窗口，检查尺寸/间距/无障碍是否合规。

    这是**唯一能抓住「改了 QSS 但内联样式没跟进」这类问题**的手段，
    因为静态扫描看不到 QSS 与实际渲染的叠加结果。
    """
    from PySide6.QtWidgets import QPushButton, QWidget

    result = LintResult()
    allowed_heights = Scale.all_px()

    #: 允许的高度例外：这些控件的高度由内容或布局决定，不是「控件」
    #: - 容器（高度=内容撑开）
    #: - 分隔线、滚动条、进度条等细长件
    SKIP_TYPES = (
        "QFrame", "QScrollArea", "QSplitter", "QStackedWidget", "QTabWidget",
        "QScrollBar", "QSlider", "QProgressBar", "QMenuBar", "QStatusBar",
        "QToolBar", "QMenu", "QDockWidget", "QGroupBox",
    )

    widgets = [w for w in window.findChildren(QWidget) if w.isVisible()]

    for w in widgets:
        type_name = type(w).__name__
        if type_name in SKIP_TYPES:
            continue
        # 框架内部控件（spinbox 内部行编辑、toolbar 溢出按钮等）不参与契约
        if is_framework_internal(w):
            continue
        # 只检查「有交互语义」的控件
        if not isinstance(w, QPushButton) and type_name not in (
            "QLineEdit", "QComboBox", "QSpinBox", "QDoubleSpinBox", "QLabel"
        ):
            continue

        h = w.height()
        # QLabel 高度由文字行数决定，不参与尺寸契约
        if type_name == "QLabel":
            continue

        if h not in allowed_heights:
            result.violations.append(
                Violation(
                    "R3-高度不在档位内",
                    type_name,
                    h,
                    f"高度 {h}px 不在 {sorted(allowed_heights)} 内"
                    f"（文本={getattr(w, 'text', lambda: '')()[:16]!r}）",
                )
            )

        # R4：溢出
        parent = w.parentWidget()
        if parent is not None and w.x() + w.width() > parent.width() + 2:
            result.violations.append(
                Violation(
                    "R4-控件溢出父容器",
                    type_name,
                    w.x() + w.width(),
                    f"右边界 {w.x() + w.width()} > 父宽 {parent.width()}",
                )
            )

        # R6：纯图标按钮必须有 tooltip
        if isinstance(w, QPushButton) and not w.text().strip():
            if w.icon().isNull():
                continue
            if not w.toolTip().strip():
                result.violations.append(
                    Violation(
                        "R6-图标按钮缺提示",
                        type_name,
                        w.height(),
                        "纯图标按钮必须 setToolTip（无障碍最低要求）",
                    )
                )

    # R5：检查 layout spacing
    allowed_space = set(Space.ALL)
    #: 间距豁免：这些容器的 layout 由 Qt 内部创建，我们改不了也不该改
    #: - QStackedWidget 的 qt_tabwidget_stackedwidget：QTabWidget 内部栈
    #: - QStatusBar / QDockWidget：主窗口框架容器，spacing 由 Qt 主题决定
    SPACE_SKIP = ("QStatusBar", "QDockWidget")
    for w in widgets:
        lay = w.layout()
        if lay is None:
            continue
        tname = type(w).__name__
        if tname in SPACE_SKIP or w.objectName().startswith("qt_"):
            continue
        # 自定义 layout（如 FlowLayout）不覆写 spacing()，
        # 调用基类方法会返回 QLayout 默认值 6 —— 那是假数据，不是真实间距。
        # 这类布局用 h_spacing / v_spacing 两个独立参数表达间距。
        if not type(lay).__module__.startswith("PySide6"):
            sp = getattr(lay, "_h_spacing", None)
            if sp is None:
                continue
        else:
            sp = lay.spacing()
        if sp < 0:      # -1 表示用 style 默认值，合规
            continue
        if sp not in allowed_space:
            result.violations.append(
                Violation(
                    "R5-间距不在档位内",
                    type(w).__name__,
                    sp,
                    f"spacing={sp} 不在 {sorted(allowed_space)} 内",
                )
            )

    return result


def format_audit(result: LintResult) -> str:
    """把运行时审计结果整理成可读报告。"""
    if result.ok:
        return "运行时审计通过。"
    lines = [f"运行时发现 {len(result.violations)} 处不合规："]
    for rule, items in sorted(result.by_rule().items()):
        lines.append(f"\n  {rule}（{len(items)} 处）")
        for v in items[:10]:
            lines.append(f"    {v.detail}")
        if len(items) > 10:
            lines.append(f"    ...还有 {len(items) - 10} 处")
    return "\n".join(lines)


__all__ = [
    "Violation", "LintResult", "lint_source", "audit_widget_tree",
    "format_audit", "STYLE_OWNER_FILES", "DEAD_FILES", "BOOTSTRAP_COLOR_FILES",
]
