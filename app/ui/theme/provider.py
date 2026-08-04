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


def _rep(qss: str) -> str:
    """把 %%token%% 占位符替换为当前主题下的实际取值。"""
    C = {
        "font": Theme.font("family"),
        "fs-base": Theme.font_size("base"),
        "fs-sm": Theme.font_size("sm"),
        "fs-xs": Theme.font_size("xs"),
        "fs-lg": Theme.font_size("lg"),
        "fs-xl": Theme.font_size("xl"),
        "fs-2xl": Theme.font_size("2xl"),
        "fs-title": Theme.font_size("title"),
        "fw-regular": Theme.font_weight("regular"),
        "fw-medium": Theme.font_weight("medium"),
        "fw-bold": Theme.font_weight("bold"),
        "radius": Theme.radius("md"),
        "radius-sm": Theme.radius("sm"),
        "radius-lg": Theme.radius("lg"),
        "radius-xl": Theme.radius("xl"),
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
        "info": Theme.color("info"),
        "success": Theme.color("success"),
        "warning": Theme.color("warning"),
        "control-h": Theme.layout("control_height"),
        "motion": Theme.layout("motion_ms"),
        "label-w": Theme.layout("label_width"),
        "indicator": Theme.layout("indicator"),
        "switch-w": Theme.layout("switch_w"),
        "switch-h": Theme.layout("switch_h"),
        "icon-btn": Theme.layout("icon_button"),
    }
    for k, v in C.items():
        qss = qss.replace("%%" + k + "%%", str(v))
    return qss


def build_global_stylesheet() -> str:
    """返回 shadcn/ui 组件词汇的全局 QSS（叠加在既有主题之上）。"""
    qss = r"""
/* ===================== shadcn/ui 规范层（叠加，opt-in） ===================== */

/* ---------- Button：仅作用于设置了 variant 的 QPushButton / QToolButton ---------- */
QPushButton[variant], QToolButton[variant] {
    font-family: %%font%%;
    font-size: %%fs-base%%px;
    font-weight: %%fw-medium%%;
    height: 36px;
    padding: 0 16px;
    border-radius: %%radius%%px;
    border: 1px solid transparent;
}
QPushButton[variant]:hover, QToolButton[variant]:hover { background: %%hover%%; }
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

/* 尺寸 */
QPushButton[uiSize="sm"], QToolButton[uiSize="sm"] { height: 30px; padding: 0 12px; font-size: %%fs-sm%%px; }
QPushButton[uiSize="lg"], QToolButton[uiSize="lg"] { height: 40px; padding: 0 22px; font-size: %%fs-lg%%px; }
QPushButton[uiSize="icon"], QToolButton[uiSize="icon"] {
    height: %%icon-btn%%px; width: %%icon-btn%%px; padding: 0;
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

/* ---------- Input / Label（统一输入控件外观） ---------- */
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QTextEdit, QPlainTextEdit {
    background: %%popover%%; border: 1px solid %%input%%;
    border-radius: %%radius%%px; padding: 4px 10px;
    color: %%foreground%%; selection-background-color: %%primary%%;
    min-height: %%control-h%%px;
}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {
    border: 1px solid %%ring%%;
}
QLineEdit:disabled, QSpinBox:disabled, QTextEdit:disabled {
    color: %%muted-foreground%%; background: %%muted%%;
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
QListWidget::item, QTreeWidget::item { min-height: 30px; padding: 2px 7px; }

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
    border: 1px solid %%border%%;
    border-radius: 6px;
}
QDialog[dialogA2="true"] QFrame[role="dialogSubPanel"] {
    background-color: %%background%%;
    border: 1px solid %%border%%;
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
    min-height: 32px;
    background-color: %%background%%;
    color: %%foreground%%;
    border: 1px solid %%input%%;
    border-radius: 4px;
    selection-background-color: %%primary%%;
    padding: 3px 6px;
}
QDialog[dialogA2="true"] QListWidget::item {
    min-height: 26px;
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
    min-height: 32px;
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
    min-height: 34px;
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
    min-height: 34px;
    background-color: %%secondary%%;
    border-color: %%input%%;
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
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
    font-size: %%fs-sm%%px;
}
QLabel[role="blockquote"] {
    border-left: 3px solid %%border%%; color: %%muted-foreground%%;
    padding: 2px 0 2px 12px; font-size: %%fs-base%%px;
}
QLabel[role="kbd"] {
    background: %%secondary%%; color: %%foreground%%;
    border: 1px solid %%border%%; border-radius: 4px; padding: 1px 7px;
    font-family: "Cascadia Code", "Consolas", "Courier New", monospace;
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
QPushButton[role="color-swatch"] {
    border: 1px solid %%border%%; border-radius: %%radius%%px; padding: 0;
}
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
    min-height: 34px; padding: 0 10px; border-radius: %%radius%%px;
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
    return p


def apply_theme(app: "QApplication", mode: str = None) -> None:
    """把指定（或当前）主题应用到 QApplication。"""
    if mode is not None:
        Theme.set_mode(mode)
    app.setStyleSheet(app.styleSheet() + "\n" + build_global_stylesheet())
    app.setPalette(get_palette())
