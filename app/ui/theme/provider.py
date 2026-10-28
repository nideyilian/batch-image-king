"""
主题提供器：由 shadcn/ui 令牌生成全局 QSS 与 QPalette

- build_global_stylesheet()：返回 shadcn 组件词汇的全局样式。所有规则均以「属性选择器 /
  角色（role）」方式作用，仅影响主动设置 variant / size / role 的控件，因此对现有界面
  零侵入、可安全叠加在既有 dark_theme 之上，使所有界面自动继承 shadcn 规范。
- get_palette() / apply_theme()：把当前主题应用到 QApplication（含暗/亮切换）。

注意：QPushButton 的基础外观不在此强制（沿用既有主题），只有设置了 variant 的按钮才会
被本样式接管，从而既统一了新组件库，又不破坏历史对话框的既有外观。
"""
from PySide6.QtGui import QPalette, QColor
from PySide6.QtWidgets import QApplication

from app.ui.theme.tokens import Theme

# P2 收敛（2026-10-27）：字族/字号/控件高/圆角直接取 tokens_v2，
# 避免 QSS 里再散落一套写死的取值。方向 01「墨黑极简」的核心特征
# （中文优先字体栈、13px 正文、30px 控件高、6px 圆角）由这里统一注入。
from app.ui.tokens_v2 import (
    Color as _C2,
    Radius as _R2,
    Size as _SZ2,
    Space as _S2,
    Typography as _TY2,
)

# 2026-10-28：控件高度改由 design_spec 统一供给（3 档 24/28/36）。
# tokens_v2.Size 保留了 26/30/34/38 四档，档位过多且不在 4px 栅格上，
# 是「37 种高度」的来源之一。这里只用 design_spec，旧档位不再参与 QSS。
from app.ui.design_spec import Scale as _SPEC


def _rep(qss: str) -> str:
    """把 %%token%% 占位符替换为当前主题下的实际取值。

    尺寸/字族类一律取 tokens_v2（方向 01 的硬指标）；颜色类仍走 Theme，
    因为 Theme 内部已指向 tokens_v2，保持单一事实来源。
    """
    C = {
        # —— 字体：中文优先栈（旧版把 Segoe UI 排前面会导致逐字回退）——
        "font": _TY2.family,
        "fs-base": _TY2.size_base,
        "fs-sm": _TY2.size_sm,
        "fs-xs": _TY2.size_caption,
        "fs-lg": _TY2.size_md,
        "fs-xl": _TY2.size_lg,
        "fs-2xl": _TY2.size_xl,
        "fs-title": _TY2.size_lg,
        "fw-regular": _TY2.weight_regular,
        "fw-medium": _TY2.weight_semibold,
        "fw-bold": _TY2.weight_bold,
        # —— 圆角 ——
        "radius": _R2.md,
        "radius-sm": _R2.sm,
        "radius-lg": _R2.lg,
        "radius-xl": _R2.xl,
        # —— 颜色（Theme 已指向 tokens_v2）——
        "background": Theme.color("background"),
        "foreground": Theme.color("foreground"),
        "card": Theme.color("card"),
        "card-foreground": Theme.color("card-foreground"),
        "popover": Theme.color("popover"),
        "primary": Theme.color("primary"),
        "primary-foreground": Theme.color("primary-foreground"),
        "primary-hover": Theme.color("primary-hover"),
        "primary-pressed": Theme.color("primary-pressed"),
        "secondary": Theme.color("secondary"),
        "secondary-foreground": Theme.color("secondary-foreground"),
        "muted": Theme.color("muted"),
        "muted-foreground": Theme.color("muted-foreground"),
        "accent": Theme.color("accent"),
        "accent-foreground": Theme.color("accent-foreground"),
        "destructive": Theme.color("destructive"),
        "destructive-foreground": Theme.color("destructive-foreground"),
        "border": Theme.color("border"),
        "input": Theme.color("input"),
        "ring": Theme.color("ring"),
        "hover": Theme.color("hover"),
        "console-panel": Theme.console_color("panel"),
        "console-raised": Theme.console_color("raised"),
        "console-control": Theme.console_color("control"),
        "console-hover": Theme.console_color("hover"),
        "console-border": Theme.console_color("border"),
        "console-border-strong": Theme.console_color("border_strong"),
        "console-text-primary": Theme.console_color("text_primary"),
        "console-text-secondary": Theme.console_color("text_secondary"),
        "console-text-muted": Theme.console_color("text_muted"),
        "console-accent": Theme.console_color("accent"),
        "console-accent-hover": Theme.console_color("accent_hover"),
        "console-accent-pressed": Theme.console_color("accent_pressed"),
        "console-accent-foreground": Theme.console_color("accent_foreground"),
        "info": Theme.color("info"),
        "success": Theme.color("success"),
        "warning": Theme.color("warning"),
        # —— 尺寸 ——
        #
        # ⚠ 这里的高度全部来自 `app/ui/design_spec.py`，**不准写别的数**。
        #
        # 2026-10-28 实测：改造前主窗口 170 个可见控件有 37 种不同高度，
        # 根因就是尺寸从多处各自取值（tokens_v2 的 30/34/38 + 各处 setFixedSize
        # 字面量 + 内联 QSS）。现在收敛到 3 档：24 / 28 / 36。
        "control-h": _SPEC.PX[_SPEC.MD],
        # 单行输入控件的 CSS 内高 = control_h - padding(2×2) - border(1×2)
        # QSS 的 height 不含 padding/border，三者相加才是实际像素高。
        # 写死 min-height:control-h 再叠 padding，实测会撑到 38px。
        "control-inner-h": _SPEC.PX[_SPEC.MD] - 2 * 2 - 2 * 1,
        "control-h-sm": _SPEC.PX[_SPEC.SM],
        "control-h-lg": _SPEC.PX[_SPEC.LG],
        # 工具栏按钮内高 = MD(28) - padding(1×2) - border(1×2)
        "toolbtn-inner-h": _SPEC.PX[_SPEC.MD] - 1 * 2 - 1 * 2,
        # shadcn 词汇层的 uiSize 档位（原本硬编码 30/40，第四套真源）
        "ui-sm": _SPEC.PX[_SPEC.SM],
        "ui-lg": _SPEC.PX[_SPEC.LG],
        "motion": 160,
        "label-w": 58,
        "indicator": 16,
        "switch-w": 52,
        "switch-h": _SPEC.PX[_SPEC.MD],
        "icon-btn": _SPEC.PX[_SPEC.MD],
        "icon-btn-sm": _SPEC.PX[_SPEC.SM],
        # 图标按钮的内高（扣掉 1px 边框 ×2）：控件内联 QSS 带了 border，
        # QSS 的 height 不含 border，两者相加才是最终高度。
        "icon-btn-inner": _SPEC.PX[_SPEC.MD] - 1 * 2,
        "icon-btn-sm-inner": _SPEC.PX[_SPEC.SM] - 1 * 2,
    }
    for k, v in C.items():
        qss = qss.replace("%%" + k + "%%", str(v))
    return qss


def build_global_stylesheet() -> str:
    """返回 shadcn/ui 组件词汇的全局 QSS（叠加在既有主题之上）。"""
    qss = r"""
/* ===================== shadcn/ui 规范层（叠加，opt-in） ===================== */

/* ---------- Button：仅作用于设置了 variant 的 QPushButton / QToolButton ----------
   注意：QPushButton 与 QToolButton 的尺寸必须分开写。
   工具栏用 QToolButton（TextBesideIcon，图标 + 文字并排），高度只有 ~25px；
   表单用 QPushButton，高度 36px。早前两者共用一条规则，导致工具栏按钮被撑到
   36px 后图标与文字重叠 —— 这是实际发生的显示缺陷，不要合并回去。 */
/* 未设置 variant 的普通按钮：01 方向下显式给无边框外观。
   不能依赖 QPalette 的 3D 角色 —— Qt 默认 Light/Mid/Dark 是一组偏亮灰，
   会在近黑底上画出一圈明显描边（实测比按钮底亮 10.8），与零边框方向冲突。

   ⚠ 刻意**不在这里写 min-height**。
   加过 `min-height: 28px` 后，所有固定尺寸的 QPushButton 全被撑大：
   - 图层面板 24x24 图标按钮 → 24x38（按钮栏凭空高 14px）
   - 属性面板 30x30 颜色块 → 30x38（破坏 COLOR_SWATCH_SIZE 尺寸契约）
   Qt 的 QSS min-height 优先级高于 setFixedSize()，一旦存在就全局生效。
   需要常规高度的地方请用 `uiSize` 属性档位（见下方 QPushButton[uiSize=...]）。 */
QPushButton {
    font-family: %%font%%;
    font-size: %%fs-base%%px;
    padding: 0 14px;
    border-radius: %%radius%%px;
    border: none;
    /* 用 input(surface_3) 而不是 secondary(surface_2)：
       零边框下按钮只能靠底色被识别，surface_2 与对话框底亮度差仅 12，
       视觉上会「陷进背景」；surface_3 差 19.7，边界清晰又不抢主按钮。 */
    background: %%input%%;
    color: %%foreground%%;
}
QPushButton:hover { background: %%hover%%; }
QPushButton:pressed { background: %%muted%%; }
QPushButton:disabled { color: %%muted-foreground%%; background: %%secondary%%; }
QPushButton:focus { border: 1px solid %%ring%%; }

QPushButton[variant] {
    font-family: %%font%%;
    font-size: %%fs-base%%px;
    font-weight: %%fw-medium%%;
    /* 默认尺寸 = LG 档（36）。原来是写死 36，与 design_spec 脱钩。
       注意：这条是 `[variant]` 属性选择器，特异性高于控件内联的
       `min-height`，所以它写的 height 会盖掉内联值 —— 这是
       「图层面板图标按钮内联写了 22 却渲染成 26」的直接原因之一。
       需要别的档位时，用 `uiSize` 属性显式声明，不要把 height 写进内联 QSS。 */
    height: %%ui-lg%%px;
    padding: 0 16px 0 16px;
    border-radius: %%radius%%px;
    border: 1px solid transparent;
}
QToolButton[variant] {
    font-family: %%font%%;
    font-size: %%fs-base%%px;
    font-weight: %%fw-medium%%;
    /* 工具栏按钮：高度锁定 MD 档（28）。
       ⚠ 三个要点，都是实测踩出来的：
       1. 必须写 `height` + `max-height`，只写 `min-height` 不够 ——
          实测 minH=28 时按钮仍渲染 31：因为 sizeHint/minimumSizeHint
          被「图标 18px + 文字行高 + padding」算成 31，
          Qt 取 max(minH, minSizeHint) = 31。加 max-height 才能压住。
       2. height 不含 padding/border，内高 = 28 - 1×2 - 1×2 = 24。
       3. padding 写全四边：写 `1px 7px` 时 Qt 与全局
          `padding: 0 14px` 合并会把左右值串到上下。 */
    height: %%toolbtn-inner-h%%px;
    min-height: %%toolbtn-inner-h%%px;
    max-height: %%toolbtn-inner-h%%px;
    padding: 1px 7px 1px 7px;
    border-radius: %%radius%%px;
    border: 1px solid transparent;
}
QPushButton[variant]:hover, QToolButton[variant]:hover { background: %%hover%%; }
/* 工具栏图标与文字之间留 4px，避免视觉粘连 */
QToolButton[variant]::menu-indicator { image: none; }
QPushButton[variant]:pressed, QToolButton[variant]:pressed { background: %%muted%%; }
QPushButton[variant]:disabled, QToolButton[variant]:disabled {
    opacity: 0.5;
}
QPushButton[variant]:focus, QToolButton[variant]:focus {
    border: 1px solid %%ring%%; outline: none;
}

/* default / primary */
QPushButton[variant="default"], QToolButton[variant="default"],
QPushButton[variant="primary"], QToolButton[variant="primary"] {
    background: %%primary%%; color: %%primary-foreground%%;
}
QPushButton[variant="default"]:hover, QToolButton[variant="default"]:hover,
QPushButton[variant="primary"]:hover, QToolButton[variant="primary"]:hover { background: %%primary-hover%%; }
QPushButton[variant="default"]:pressed, QToolButton[variant="default"]:pressed,
QPushButton[variant="primary"]:pressed, QToolButton[variant="primary"]:pressed { background: %%primary-pressed%%; }

/* secondary */
QPushButton[variant="secondary"], QToolButton[variant="secondary"] {
    background: %%secondary%%; color: %%secondary-foreground%%;
    border: 1px solid %%border%%;
}
QPushButton[variant="secondary"]:hover, QToolButton[variant="secondary"]:hover { background: %%hover%%; }

/* outline */
QPushButton[variant="outline"], QToolButton[variant="outline"] {
    background: transparent; color: %%foreground%%;
    border: 1px solid %%border%%;
}
QPushButton[variant="outline"]:hover, QToolButton[variant="outline"]:hover {
    background: %%accent%%; color: %%accent-foreground%%;
}

/* ghost */
QPushButton[variant="ghost"], QToolButton[variant="ghost"] {
    background: transparent; color: %%foreground%%;
}
QPushButton[variant="ghost"]:hover, QToolButton[variant="ghost"]:hover {
    background: %%accent%%; color: %%accent-foreground%%;
}

/* destructive */
QPushButton[variant="destructive"], QToolButton[variant="destructive"] {
    background: %%destructive%%; color: %%destructive-foreground%%;
}
QPushButton[variant="destructive"]:hover, QToolButton[variant="destructive"]:hover { background: %%destructive%%; }
QPushButton[variant="destructive"]:disabled, QToolButton[variant="destructive"]:disabled { opacity: 0.5; }

/* link */
QPushButton[variant="link"], QToolButton[variant="link"] {
    background: transparent; color: %%primary%%; padding: 0 4px; height: auto;
    border: none; text-decoration: underline;
}
QPushButton[variant="link"]:hover, QToolButton[variant="link"]:hover { color: %%primary-hover%%; }

/* 尺寸
   ⚠ 三档必须与 design_spec.Scale 一致（SM=24 / MD=28 / LG=36）。
   历史上这里是 30/40，跟 Tokens.CONTROL_HEIGHT=30 一起构成了第二、三套真源，
   导致「改了一处没效果」。现在统一由 %%ui-sm%% / %%ui-lg%% 注入。
   注意：height 不含 padding/border。这些档位用 padding:0 所以直接等于目标值。 */
QPushButton[uiSize="sm"], QToolButton[uiSize="sm"] { height: %%ui-sm%%px; min-height: %%ui-sm%%px; max-height: %%ui-sm%%px; padding: 0 12px; font-size: %%fs-sm%%px; }
QPushButton[uiSize="lg"], QToolButton[uiSize="lg"] { height: %%ui-lg%%px; min-height: %%ui-lg%%px; max-height: %%ui-lg%%px; padding: 0 22px; font-size: %%fs-lg%%px; }
/* 图标按钮：必须显式压掉上面 QPushButton 基础规则里的 min-height 与 padding。
   QSS 的 min-height 优先级高于代码里的 setFixedSize() —— 只写 height/width
   不够，实测 24x24 的图标按钮会被撑成 24x38，按钮栏凭空高出一截。

   ⚠ height 要扣掉 border：这类按钮通常在控件内联 QSS 里写了
   `border: 1px solid ...`（它们需要边框表达选中态）。而 QSS 的 height
   不含 border，两者相加才是最终像素。实测写 28 且带 1px 边框 → 渲染 30，
   写 24 带 1px 边框 → 渲染 26。都不在 24/28/36 三档内。
   扣掉 1×2 后：内高 26 + 边框 2 = 28 ✓ */
QPushButton[uiSize="icon"], QToolButton[uiSize="icon"] {
    height: %%icon-btn-inner%%px;
    width: %%icon-btn-inner%%px;
    min-height: %%icon-btn-inner%%px;
    max-height: %%icon-btn-inner%%px;
    min-width: %%icon-btn-inner%%px;
    max-width: %%icon-btn-inner%%px;
    padding: 0;
}
/* 紧凑图标按钮：目标 SM 档 24。同样扣掉 border → 内高 22 + 边框 2 = 24。
   24px 是 WCAG 2.5.8 Target Size(Minimum) 的下限，再小就点不准了。 */
QPushButton[uiSize="iconSm"], QToolButton[uiSize="iconSm"] {
    height: %%icon-btn-sm-inner%%px;
    width: %%icon-btn-sm-inner%%px;
    min-height: %%icon-btn-sm-inner%%px;
    max-height: %%icon-btn-sm-inner%%px;
    min-width: %%icon-btn-sm-inner%%px;
    max-width: %%icon-btn-sm-inner%%px;
    padding: 0;
}

/* ---------- Card / Section ---------- */
QFrame[role="card"] {
    background: %%card%%; border: 1px solid %%border%%;
    border-radius: %%radius-lg%%px;
}
QFrame[role="section"] {
    background: %%card%%; border: 1px solid %%border%%;
    border-radius: %%radius-lg%%px;
}
QLabel[role="card-title"] {
    color: %%card-foreground%%; font-weight: %%fw-bold%%; font-size: %%fs-lg%%px;
}
QLabel[role="card-desc"] {
    color: %%muted-foreground%%; font-size: %%fs-sm%%px;
}

/* ---------- Input / Label（统一输入控件外观） ----------

## 高度必须显式算清，不能只写 min-height

QSS 的 height / min-height **不含 padding 与 border**，三者是相加的。
原来只写 `min-height: control-h(30px)` + `padding: 4px 10px`，实测：
    QSpinBox  → 38px     (30 + 4×2 padding)
    QLineEdit → 30px
    QComboBox → 30px
同一行里 spinbox 比 input 高 8px，面板看起来"歪"，是视觉廉价感的主要来源之一。

现在把 padding 与 1px 边框算进 min-height，并把 max-height 锁死：
    min-height 24 + padding 2×2 + border 1×2 = 30px = control-h ✔
    QSpinBox 额外设 max-height（它有上下按钮，sizeHint 天生比另外两个高 4px）

实测三类控件均精确落在 30px（见 tests/test_control_metrics.py）。

## 边框只在必要时出现

深色界面里 `1px solid surface_4(#23252A)` 与底色的亮度差极小，
既看不清又添一层噪点。改为默认无边框、用底色区分；聚焦时给可见的 focus ring。
*/
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background: %%popover%%;
    border: 1px solid %%popover%%;
    border-radius: %%radius%%px;
    padding: 2px 10px;
    color: %%foreground%%;
    selection-background-color: %%primary%%;
    min-height: %%control-inner-h%%px;
}
/* 需要固定高度的单行控件：把 max 也锁死，避免 spinbox 被 sizeHint 顶高 */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
    max-height: %%control-inner-h%%px;
}
/* 多行控件不锁高度，由使用方决定 */
QTextEdit, QPlainTextEdit {
    padding: 6px 10px;
}
QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover,
QTextEdit:hover, QPlainTextEdit:hover {
    border-color: %%border%%;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid %%ring%%;
}
QLineEdit:disabled, QSpinBox:disabled, QTextEdit:disabled {
    color: %%muted-foreground%%; background: %%muted%%;
}
/* 状态栏内的紧凑输入控件。
   状态栏实际可用高度只有 ~21px（QMainWindow 的状态栏区不做拉伸，
   即便给它 max-height 也不会变高）。通用规则给 QSpinBox 的是
   control-h(30px) + padding，实测撑到 32px 塞进 21px 容器 →
   文字下半截被裁掉（「100%」显示成「1000%」）。
   这里压到 16px 并去掉上下 padding，让数值完整可见。 */
QStatusBar QSpinBox, QStatusBar QLineEdit, QStatusBar QComboBox {
    min-height: 16px;
    max-height: 16px;
    padding: 0px 2px;
    border-radius: 3px;
}
QStatusBar QSpinBox::up-button, QStatusBar QSpinBox::down-button {
    width: 12px;
    height: 8px;
}
QLabel[role="label"] {
    color: %%foreground%%; font-weight: %%fw-medium%%; font-size: %%fs-sm%%px;
}
QLabel[role="muted"] { color: %%muted-foreground%%; }
QLabel[role="status-value"] { color: %%info%%; font-weight: %%fw-bold%%; }
QLabel[role="status-value"][status="warning"] { color: %%warning%%; }
QLabel[role="status-value"][status="destructive"] { color: %%destructive%%; }
QLabel[role="status-value"][status="muted"] { color: %%muted-foreground%%; }
QLabel[role="success"] { color: %%success%%; }
QLabel[role="status-separator"] { color: %%border%%; padding: 0 4px; }
QLineEdit[status="warning"] { color: %%warning%%; border-color: %%warning%%; }
QLineEdit[status="destructive"] { color: %%destructive%%; border-color: %%destructive%%; }

/* ---------- Native selection controls ---------- */
QCheckBox, QRadioButton {
    color: %%foreground%%; spacing: 7px; min-height: %%control-h%%px;
}
QCheckBox:disabled, QRadioButton:disabled { color: %%muted-foreground%%; }
QCheckBox::indicator, QRadioButton::indicator {
    width: %%indicator%%px; height: %%indicator%%px;
    border: 1px solid %%input%%; background: %%popover%%;
}
QCheckBox::indicator { border-radius: 4px; }
QRadioButton::indicator { border-radius: 8px; }
QCheckBox::indicator:hover, QRadioButton::indicator:hover { border-color: %%ring%%; }
QCheckBox::indicator:checked, QRadioButton::indicator:checked {
    background: %%primary%%; border-color: %%primary%%;
}
QSlider::groove:horizontal {
    height: 4px; background: %%muted%%; border-radius: 2px;
}
QSlider::sub-page:horizontal { background: %%primary%%; border-radius: 2px; }
QSlider::handle:horizontal {
    width: 14px; height: 14px; margin: -5px 0;
    background: %%foreground%%; border: 2px solid %%primary%%; border-radius: 7px;
}
QSlider::handle:horizontal:hover { border-color: %%primary-hover%%; }
QListWidget, QTreeWidget {
    background: %%background%%; color: %%foreground%%;
    border: 1px solid %%border%%; border-radius: %%radius%%px;
    selection-background-color: %%accent%%;
}
QListWidget::item, QTreeWidget::item { min-height: %%control-h%%px; padding: 2px 7px; }

/* ---------- Badge ---------- */
QLabel[role="badge"] {
    background: %%secondary%%; color: %%secondary-foreground%%;
    border-radius: 9999px; padding: 2px 10px; font-size: %%fs-xs%%px;
    font-weight: %%fw-medium%%;
}
QLabel[role="badge"][variant="primary"] { background: %%primary%%; color: %%primary-foreground%%; }
QLabel[role="badge"][variant="destructive"] { background: %%destructive%%; color: %%destructive-foreground%%; }
QLabel[role="badge"][variant="success"] { background: %%success%%; color: #FFFFFF; }
QLabel[role="badge"][variant="warning"] { background: %%warning%%; color: #FFFFFF; }
QLabel[role="badge"][variant="outline"] { background: transparent; border: 1px solid %%border%%; }

/* ---------- Alert ---------- */
QFrame[role="alert"] {
    background: %%muted%%; border: 1px solid %%border%%;
    border-left: 3px solid %%muted-foreground%%;
    border-radius: %%radius%%px; padding: 12px 14px;
}
QFrame[role="alert"][variant="destructive"] { border-left-color: %%destructive%%; background: %%destructive%%; }
QFrame[role="alert"][variant="destructive"] QLabel { color: %%destructive-foreground%%; }
QFrame[role="alert"][variant="success"] { border-left-color: %%success%%; }
QFrame[role="alert"][variant="warning"] { border-left-color: %%warning%%; }
QFrame[role="alert"][variant="info"] { border-left-color: %%info%%; }
QLabel[role="alert-title"] { font-weight: %%fw-bold%%; color: %%foreground%%; }
QLabel[role="alert-desc"] { color: %%muted-foreground%%; font-size: %%fs-sm%%px; }

/* ---------- Separator ---------- */
QFrame[role="separator"] {
    background: %%border%%; max-height: 1px; min-height: 1px; border: none;
}
QFrame[role="separator"][orientation="vertical"] {
    max-width: 1px; min-width: 1px; max-height: none; min-height: none;
}

/* ---------- Progress ---------- */
QProgressBar[role="progress"] {
    background: %%muted%%; border: none; border-radius: 9999px;
    height: 8px; text-align: center; color: transparent;
}
QProgressBar[role="progress"]::chunk {
    background: %%primary%%; border-radius: 9999px;
}

/* ---------- Sheet / Popover 容器 ---------- */
QFrame[role="sheet"] {
    background: %%background%%; border: 1px solid %%border%%;
    border-radius: %%radius-lg%%px;
}
QFrame[role="popover-surface"] {
    background: %%popover%%; border: 1px solid %%border%%;
    border-radius: %%radius%%px;
}

/* ---------- Dialog A2（模态对话框，已由全局令牌驱动，单一真源） ---------- */
/* 该区块替代原 dialog_a2.py 内的 per-dialog setStyleSheet，避免第三套 QSS。
   仅作用于主动设置 dialogA2="true" 属性的对话框（见 app/ui/dialog_a2.py）。 */
QDialog[dialogA2="true"] {
    background-color: %%background%%;
    color: %%foreground%%;
    font-size: %%fs-base%%px;
}
QDialog[dialogA2="true"] QLabel {
    color: %%foreground%%;
    background: transparent;
}
QDialog[dialogA2="true"] QFrame[role="dialogCard"] {
    background-color: %%card%%;
    /* 01 方向：零边框。层次由 card(surface_1) 与 background(surface_base)
       的亮度差承担；加 1px 描边会在近黑底上形成一条明显亮线。 */
    border: none;
    border-radius: 6px;
}
QDialog[dialogA2="true"] QFrame[role="dialogSubPanel"] {
    background-color: %%background%%;
    border: none;
    border-radius: 6px;
}
QDialog[dialogA2="true"] QFrame[role="dialogFooter"] {
    background-color: transparent;
    border: none;
}
QDialog[dialogA2="true"] QLabel[role="dialogTitle"] {
    color: %%primary-foreground%%;
    font-size: 16px;
    font-weight: %%fw-bold%%;
}
QDialog[dialogA2="true"] QFrame[role="dialogHeader"] {
    background-color: transparent;
    border: none;
}
QDialog[dialogA2="true"] QFrame[role="dialogDivider"] {
    background-color: %%border%%;
    border: none;
    max-height: 1px;
}
QDialog[dialogA2="true"] QToolButton[role="dialogCloseButton"] {
    min-width: 30px;
    max-width: 30px;
    min-height: %%icon-btn-sm%%px;
    max-height: %%icon-btn-sm%%px;
    padding: 0;
    background-color: transparent;
    border-color: transparent;
}
QDialog[dialogA2="true"] QLabel[role="sectionTitle"] {
    color: %%primary-foreground%%;
    font-size: 13px;
    font-weight: %%fw-bold%%;
}
QDialog[dialogA2="true"] QLabel[role="fieldLabel"] {
    color: %%foreground%%;
    font-size: 12px;
    font-weight: %%fw-bold%%;
}
QDialog[dialogA2="true"] QLabel[role="hint"] {
    color: %%muted-foreground%%;
    font-size: 11px;
}
QDialog[dialogA2="true"] QLineEdit,
QDialog[dialogA2="true"] QSpinBox,
QDialog[dialogA2="true"] QComboBox,
QDialog[dialogA2="true"] QListWidget,
QDialog[dialogA2="true"] QTextEdit {
    min-height: %%control-h%%px;
    background-color: %%background%%;
    color: %%foreground%%;
    border: 1px solid %%input%%;
    border-radius: 4px;
    selection-background-color: %%primary%%;
    padding: 3px 6px;
}
QDialog[dialogA2="true"] QListWidget::item {
    min-height: %%control-h-sm%%px;
    padding: 4px 6px;
    border-radius: 3px;
}
QDialog[dialogA2="true"] QListWidget::item:selected {
    background-color: %%primary%%;
    color: %%primary-foreground%%;
}
QDialog[dialogA2="true"] QSplitter::handle {
    background-color: %%border%%;
    margin: 0 6px;
}
QDialog[dialogA2="true"] QLineEdit:focus,
QDialog[dialogA2="true"] QSpinBox:focus,
QDialog[dialogA2="true"] QComboBox:focus,
QDialog[dialogA2="true"] QTextEdit:focus {
    border-color: %%primary%%;
}
QDialog[dialogA2="true"] QPushButton,
QDialog[dialogA2="true"] QToolButton {
    min-height: %%control-h%%px;
    border: 1px solid %%input%%;
    border-radius: 4px;
    background-color: %%secondary%%;
    color: %%foreground%%;
    font-size: 12px;
    font-weight: %%fw-medium%%;
    padding: 3px 10px;
}
QDialog[dialogA2="true"] QPushButton:hover,
QDialog[dialogA2="true"] QToolButton:hover {
    background-color: %%hover%%;
    border-color: %%primary-hover%%;
}
QDialog[dialogA2="true"] QPushButton:pressed,
QDialog[dialogA2="true"] QToolButton:pressed {
    background-color: %%primary-pressed%%;
    border-color: %%primary%%;
}
QDialog[dialogA2="true"] QPushButton:disabled,
QDialog[dialogA2="true"] QToolButton:disabled {
    color: %%muted-foreground%%;
    background-color: %%secondary%%;
    border-color: %%border%%;
}
QDialog[dialogA2="true"] QPushButton[primaryButton="true"] {
    min-width: 80px;
    min-height: %%control-h-lg%%px;
    background-color: %%primary%%;
    border-color: %%primary-hover%%;
    color: %%primary-foreground%%;
    font-weight: %%fw-bold%%;
}
QDialog[dialogA2="true"] QPushButton[primaryButton="true"]:hover {
    background-color: %%primary-hover%%;
    border-color: %%primary-hover%%;
}
QDialog[dialogA2="true"] QPushButton[secondaryButton="true"] {
    min-width: 80px;
    min-height: %%control-h-lg%%px;
    background-color: %%secondary%%;
    border-color: %%input%%;
}
/* 取色器同时服务于 QWidget 与 QML 工作台，视觉令牌以当前生产控制台为准。 */
QDialog[colorPickerA2="true"] {
    background-color: %%console-panel%%;
    color: %%console-text-primary%%;
    font-family: "Microsoft YaHei UI";
}
QDialog[colorPickerA2="true"] * {
    font-family: "Microsoft YaHei UI";
}
QDialog[colorPickerA2="true"] QLabel {
    color: %%console-text-primary%%;
}
QDialog[colorPickerA2="true"] QLabel[role="dialogTitle"],
QDialog[colorPickerA2="true"] QLabel[role="sectionTitle"] {
    color: %%console-text-primary%%;
}
QDialog[colorPickerA2="true"] QFrame[role="dialogDivider"] {
    background-color: %%console-border%%;
}
QDialog[colorPickerA2="true"] QLineEdit,
QDialog[colorPickerA2="true"] QSpinBox {
    background-color: %%console-control%%;
    color: %%console-text-primary%%;
    border-color: %%console-border-strong%%;
    selection-background-color: %%console-accent-pressed%%;
}
QDialog[colorPickerA2="true"] QLineEdit:focus,
QDialog[colorPickerA2="true"] QSpinBox:focus {
    border-color: %%console-accent-hover%%;
}
QDialog[colorPickerA2="true"] QPushButton,
QDialog[colorPickerA2="true"] QToolButton {
    background-color: %%console-raised%%;
    color: %%console-text-primary%%;
    border-color: %%console-border-strong%%;
}
QDialog[colorPickerA2="true"] QPushButton:hover,
QDialog[colorPickerA2="true"] QToolButton:hover {
    background-color: %%console-hover%%;
    border-color: %%console-accent-hover%%;
}
QDialog[colorPickerA2="true"] QPushButton[primaryButton="true"] {
    background-color: %%console-accent%%;
    border-color: %%console-accent%%;
    color: %%console-accent-foreground%%;
}
QDialog[colorPickerA2="true"] QPushButton[primaryButton="true"]:hover {
    background-color: %%console-accent-hover%%;
    border-color: %%console-accent-hover%%;
}
QDialog[colorPickerA2="true"] QPushButton[secondaryButton="true"] {
    background-color: %%console-raised%%;
    border-color: %%console-border-strong%%;
}
QDialog[dialogA2="true"] QCheckBox {
    color: %%foreground%%;
    spacing: 6px;
}
QDialog[dialogA2="true"] QCheckBox::indicator {
    width: 15px;
    height: 15px;
    border-radius: 3px;
    border: 1px solid %%input%%;
    background: %%popover%%;
}
QDialog[dialogA2="true"] QCheckBox::indicator:checked {
    background: %%primary%%;
    border-color: %%primary-hover%%;
}
QDialog[dialogA2="true"] QTabWidget::pane {
    border: 1px solid %%border%%;
    border-radius: 4px;
    background-color: %%background%%;
}
QDialog[dialogA2="true"] QTabBar::tab {
    background-color: %%background%%;
    color: %%foreground%%;
    border: 1px solid %%border%%;
    padding: 6px 12px;
    margin-right: 4px;
    border-top-left-radius: 4px;
    border-top-right-radius: 4px;
}
QDialog[dialogA2="true"] QTabBar::tab:selected {
    background-color: %%primary%%;
    color: %%primary-foreground%%;
    font-weight: %%fw-bold%%;
}

/* ---------- Typography 排版组件 ---------- */
QLabel[role="heading"][level="1"] {
    font-size: %%fs-2xl%%px; font-weight: %%fw-bold%%; color: %%foreground%%;
}
QLabel[role="heading"][level="2"] {
    font-size: %%fs-xl%%px; font-weight: %%fw-bold%%; color: %%foreground%%;
}
QLabel[role="heading"][level="3"] {
    font-size: %%fs-lg%%px; font-weight: %%fw-medium%%; color: %%foreground%%;
}
QLabel[role="lead"] { font-size: %%fs-lg%%px; color: %%muted-foreground%%; }
QLabel[role="text"] { color: %%foreground%%; font-size: %%fs-base%%px; }
QLabel[role="small"] { color: %%muted-foreground%%; font-size: %%fs-xs%%px; }
QLabel[role="code"] {
    background: %%muted%%; color: %%foreground%%;
    border-radius: 4px; padding: 2px 6px;
    font-family: "Cascadia Code";
    font-size: %%fs-sm%%px;
}
QLabel[role="blockquote"] {
    border-left: 3px solid %%border%%; color: %%muted-foreground%%;
    padding: 2px 0 2px 12px; font-size: %%fs-base%%px;
}
QLabel[role="kbd"] {
    background: %%secondary%%; color: %%foreground%%;
    border: 1px solid %%border%%; border-radius: 4px; padding: 1px 7px;
    font-family: "Cascadia Code";
    font-size: %%fs-xs%%px;
}

/* ---------- Action groups / toggles ---------- */
QFrame[role="button-group"], QFrame[role="toggle-group"],
QFrame[role="segmented-control"], QFrame[role="radio-group"] {
    background: transparent; border: none;
}
QToolButton[role="toggle"] {
    min-height: %%control-h%%px; padding: 0 10px;
    border: 1px solid %%border%%; border-radius: %%radius%%px;
}
QToolButton[role="toggle"]:checked {
    background: %%accent%%; color: %%accent-foreground%%;
    border-color: %%ring%%;
}
QFrame[role="segmented-control"] {
    background: %%muted%%; border: 1px solid %%border%%;
    border-radius: %%radius%%px; padding: 2px;
}
QFrame[role="segmented-control"] QToolButton[role="toggle"] {
    border-color: transparent; background: transparent;
}
QFrame[role="segmented-control"] QToolButton[role="toggle"]:checked {
    background: %%card%%; border-color: %%border%%;
}

/* ---------- Form composition / validation ---------- */
QFrame[role="field"] { background: transparent; border: none; }
QLabel[role="field-error"] { color: %%destructive%%; font-size: %%fs-sm%%px; }
QLineEdit[invalid="true"], QSpinBox[invalid="true"],
QDoubleSpinBox[invalid="true"], QComboBox[invalid="true"],
QTextEdit[invalid="true"], QPlainTextEdit[invalid="true"] {
    border: 1px solid %%destructive%%;
}
QFrame[role="input-group"] {
    min-height: %%control-h%%px; background: %%popover%%;
    border: 1px solid %%input%%; border-radius: %%radius%%px;
}
QFrame[role="input-group"] QLineEdit,
QFrame[role="input-group"] QSpinBox,
QFrame[role="input-group"] QDoubleSpinBox {
    background: transparent; border: none; padding-left: 2px; padding-right: 2px;
}
/* 颜色块外观：**只写边框/圆角，不写任何尺寸属性**。
   尺寸链路由控件自己的内联 QSS 负责（ColorIndicator.update_color_display
   里写 min/max = size-2 以抵消 1px 边框）。见 app/ui/text_panel_widgets.py 的说明。
   这里若再写 min-height，会与内联值叠加成 32~38px，破坏 COLOR_SWATCH_SIZE 契约。 */
QPushButton[role="color-swatch"],
QDialog[dialogA2="true"] QPushButton[role="color-swatch"] {
    border: 1px solid %%border%%;
    border-radius: %%radius%%px;
    padding: 0;
}
QPushButton[role="color-swatch"]:focus { border-color: %%ring%%; }
QPushButton[role="color-swatch"]:focus { border-color: %%ring%%; }

/* ---------- Legacy semantic containers ---------- */
QGroupBox[role="section"] {
    background: %%card%%; border: 1px solid %%border%%;
    border-radius: %%radius-lg%%px; margin-top: 10px; padding: 10px;
}
QGroupBox[role="section"]::title {
    color: %%foreground%%; subcontrol-origin: margin; left: 10px; padding: 0 4px;
}

/* ---------- Layout / navigation ---------- */
QScrollArea[role="scroll-area"] { background: transparent; border: none; }
QFrame[role="sidebar"] {
    background: %%card%%; border-right: 1px solid %%border%%;
}
QSplitter[role="resizable"]::handle {
    background: %%border%%; width: 1px; height: 1px;
}
QSplitter[role="resizable"]::handle:hover { background: %%ring%%; }
QFrame[role="aspect-ratio"] { background: transparent; border: none; }
QFrame[role="accordion"], QFrame[role="accordion-item"] {
    background: transparent; border: none;
}
QFrame[role="accordion-item"] {
    border-bottom: 1px solid %%border%%;
}
QToolButton[role="accordion-trigger"] {
    min-height: 36px; padding: 0 8px; text-align: left;
    color: %%foreground%%; font-weight: %%fw-medium%%;
    background: transparent; border: none;
}
QToolButton[role="accordion-trigger"]:hover { background: %%accent%%; }
QWidget[role="accordion-content"] { background: transparent; }

/* ---------- Overlay / command ---------- */
QDialog[role="alert-dialog"], QDialog[role="command-palette"] {
    background: %%background%%; color: %%foreground%%;
}
QLabel[role="dialog-title"] {
    color: %%foreground%%; font-size: %%fs-lg%%px; font-weight: %%fw-bold%%;
}
QListWidget[role="command-list"] {
    background: %%background%%; border: none; padding: 4px;
}
QListWidget[role="command-list"]::item {
    min-height: %%control-h-lg%%px; padding: 0 10px; border-radius: %%radius%%px;
}
QListWidget[role="command-list"]::item:selected { background: %%accent%%; }

/* ---------- Feedback / data ---------- */
QFrame[role="toast"] {
    background: %%popover%%; border: 1px solid %%border%%;
    border-radius: %%radius-lg%%px;
}
QFrame[role="toast"][variant="success"] { border-left: 3px solid %%success%%; }
QFrame[role="toast"][variant="warning"] { border-left: 3px solid %%warning%%; }
QFrame[role="toast"][variant="destructive"] { border-left: 3px solid %%destructive%%; }
QFrame[role="toast"][variant="info"] { border-left: 3px solid %%info%%; }
QLabel[role="toast-message"] { color: %%foreground%%; }
QProgressBar[role="spinner"] {
    min-height: 4px; max-height: 4px; border: none; background: %%muted%%;
}
QProgressBar[role="spinner"]::chunk { background: %%primary%%; border-radius: 2px; }
QFrame[role="skeleton"] { background: %%muted%%; border-radius: %%radius%%px; }
QFrame[role="empty-state"] { background: transparent; border: none; }
QLabel[role="empty-title"] {
    color: %%foreground%%; font-size: %%fs-lg%%px; font-weight: %%fw-medium%%;
}
QTableWidget[role="table"] {
    background: %%background%%; alternate-background-color: %%card%%;
    border: 1px solid %%border%%; gridline-color: %%border%%;
    selection-background-color: %%accent%%;
}
QTableWidget[role="table"] QHeaderView::section {
    background: %%secondary%%; color: %%foreground%%;
    border: none; border-bottom: 1px solid %%border%%; padding: 7px 9px;
}
QFrame[role="file-drop-zone"] {
    background: %%card%%; border: 1px dashed %%input%%;
    border-radius: %%radius-lg%%px;
}
QFrame[role="file-drop-zone"][dragActive="true"] {
    background: %%accent%%; border-color: %%ring%%;
}

/* ---------- Icon 图标组件 ---------- */
QLabel#IconLabel { qproperty-alignment: AlignCenter; }
"""
    return _rep(qss)


def get_palette() -> QPalette:
    """由当前主题构造 QPalette。"""
    p = QPalette()
    bg = QColor(Theme.color("background"))
    fg = QColor(Theme.color("foreground"))
    surface = QColor(Theme.color("card"))
    p.setColor(QPalette.Window, bg)
    p.setColor(QPalette.WindowText, fg)
    p.setColor(QPalette.Base, QColor(Theme.color("popover")))
    p.setColor(QPalette.AlternateBase, surface)
    p.setColor(QPalette.Text, fg)
    p.setColor(QPalette.Button, QColor(Theme.color("secondary")))
    p.setColor(QPalette.ButtonText, fg)
    p.setColor(QPalette.Highlight, QColor(Theme.color("primary")))
    p.setColor(QPalette.HighlightedText, QColor(Theme.color("primary-foreground")))
    p.setColor(QPalette.ToolTipBase, surface)
    p.setColor(QPalette.ToolTipText, fg)
    p.setColor(QPalette.Link, QColor(Theme.color("primary")))
    # 3D 边框角色：Qt 默认会给 Light / Midlight / Mid / Dark / Shadow 一组偏亮的灰，
    # 未显式设置 variant 的按钮就会用它们画出一圈明显描边 ——
    # 这与 01 方向「零边框、靠底色差分层次」冲突（实测边框比按钮底亮 10.8）。
    # 这里全部压到接近背景的值，让默认按钮也呈无边框观感。
    _edge = QColor(Theme.color("secondary"))
    for _role in (QPalette.Light, QPalette.Midlight, QPalette.Mid,
                  QPalette.Dark, QPalette.Shadow):
        p.setColor(_role, _edge)
    return p


def apply_theme(app: "QApplication", mode: str = None) -> None:
    """把指定（或当前）主题应用到 QApplication。"""
    if mode is not None:
        Theme.set_mode(mode)
    app.setStyleSheet(app.styleSheet() + "\n" + build_global_stylesheet())
    app.setPalette(get_palette())
