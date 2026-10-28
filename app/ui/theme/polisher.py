"""为历史 Qt 控件补齐设计系统语义属性。"""

from PySide6.QtCore import QEvent, QObject
from PySide6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QProgressBar,
    QPushButton,
    QTabWidget,
    QToolButton,
    QWidget,
)


_BUTTON_BOX_VARIANTS = {
    QDialogButtonBox.AcceptRole: "default",
    QDialogButtonBox.YesRole: "default",
    QDialogButtonBox.ApplyRole: "default",
    QDialogButtonBox.RejectRole: "outline",
    QDialogButtonBox.NoRole: "outline",
    QDialogButtonBox.ResetRole: "outline",
    QDialogButtonBox.DestructiveRole: "destructive",
    QDialogButtonBox.HelpRole: "ghost",
    QDialogButtonBox.ActionRole: "secondary",
}


def _set_if_missing(widget, name, value):
    if widget.property(name) is None:
        widget.setProperty(name, value)
        return True
    return False


def _polish_button_box(box):
    """按按钮在 QDialogButtonBox 中的**角色**赋 variant。

    ⚠ 必须能覆盖已有的通用 variant：控件先收到 QEvent.Polish 时，
    ``_polish_button`` 会先给它打上通用默认值 ``secondary``；
    等这里再按角色映射（AcceptRole → default 等）时，若沿用
    ``_set_if_missing`` 就会被跳过 —— 结果「应用」按钮永远不是主按钮样式。
    这是实测发现的真实缺陷：单测单独跑能过，全量跑（polisher 已装）
    才暴露，因为属性已被提前写入。

    所以这里用 force 语义：角色映射优先于通用默认值。
    """
    changed = False
    for button in box.buttons():
        variant = _BUTTON_BOX_VARIANTS.get(box.buttonRole(button), "secondary")
        if button.property("variant") != variant:
            button.setProperty("variant", variant)
            changed = True
    return changed


def _variant_from_button_box(button):
    """若按钮属于 QDialogButtonBox，返回按角色应得的 variant，否则 None。

    为什么需要：控件先收到 QEvent.Polish 时，``_polish_button`` 会抢先把
    variant 写成通用默认值 ``secondary``；而 ButtonBox 的角色映射
    （AcceptRole → default 等）此时还没跑。若不在这里拦截，
    「应用/确定」这类主按钮会永远拿不到主按钮样式 —— 实测确认的真实缺陷。
    """
    parent = button.parentWidget()
    if not isinstance(parent, QDialogButtonBox):
        return None
    return _BUTTON_BOX_VARIANTS.get(parent.buttonRole(button))


def _polish_button(button):
    if not button.accessibleName() and button.text():
        button.setAccessibleName(button.text().replace("&", ""))

    if button.property("variant") is not None:
        return False

    # 已用 `role` 做语义标记的控件，**不参与 variant 推断**。
    #
    # 这是 2026-10-28 实测出的真实缺陷：色块（ColorIndicator）设了
    # `role="color-swatch"`，尺寸由自己的内联 QSS 锁定为 30x30。
    # 但 polisher 会先给它打上 `variant="secondary"`，于是命中
    # `QPushButton[variant="secondary"] { min-height: N; padding: 0 12px }` ——
    # 实测 30x30 被撑成 30x38（minH=38 > maxH=30 的矛盾态），
    # 破坏 COLOR_SWATCH_SIZE 契约，且色块在面板里溢出父容器 22px。
    #
    # `role` 表示「这个控件已有明确的语义分类，样式由 role 规则负责」，
    # 优先级高于按位置的通用推断。
    if button.property("role") is not None:
        return False

    # 已用 `uiSize` 声明尺寸档位的控件，也不参与 variant 推断。
    #
    # 与上面 `role` 同一个病根，2026-10-28 二次实测确认：
    # 图层面板底栏的图标按钮设了 `uiSize="iconSm"` + `setFixedSize(24, 24)`，
    # 本应是 24x24。但 polisher 给它打上 `variant="secondary"`，
    # 命中 `QPushButton[variant="secondary"] { min-height: 26px }`，
    # 24 被撑成 26 —— 26 不在 design_spec 的三档里。
    #
    # `uiSize` 是「我明确声明了尺寸档位」的信号，variant 只该管配色，
    # 不该反过来改写尺寸。
    if button.property("uiSize") is not None:
        return False

    # ButtonBox 内的按钮优先按角色决定（见 _variant_from_button_box 说明）
    role_variant = _variant_from_button_box(button)
    if role_variant is not None:
        button.setProperty("variant", role_variant)
        return True

    if button.property("primaryButton") is True:
        button.setProperty("variant", "default")
    elif button.property("secondaryButton") is True:
        button.setProperty("variant", "outline")
    elif isinstance(button, QPushButton) and button.isDefault():
        button.setProperty("variant", "default")
    elif isinstance(button, QToolButton):
        button.setProperty("variant", "ghost")
    else:
        button.setProperty("variant", "secondary")
    return True


def _polish_one(widget):
    changed = False
    if isinstance(widget, QDialog):
        changed = _set_if_missing(widget, "role", "dialog") or changed
    if isinstance(widget, QDialogButtonBox):
        changed = _polish_button_box(widget) or changed
    if isinstance(widget, QAbstractButton):
        changed = _polish_button(widget) or changed
    if isinstance(widget, QProgressBar):
        changed = _set_if_missing(widget, "role", "progress") or changed
    if isinstance(widget, QGroupBox):
        changed = _set_if_missing(widget, "role", "section") or changed
    if isinstance(widget, QTabWidget):
        changed = _set_if_missing(widget, "role", "tabs") or changed
    widget.setProperty("semanticPolished", True)
    if changed:
        widget.style().unpolish(widget)
        widget.style().polish(widget)


def polish_widget_tree(root):
    """幂等地补齐 root 及其子控件的语义，不覆盖显式属性。

    ⚠ 幂等性至关重要（2026-10-28 实测）：
    本函数会对每个控件执行 `unpolish + polish`，强制重新计算 QSS。
    而 Qt 在「面板 QSS + 全局 QSS」叠加时重新计算，会把 padding 的
    两值写法（`3px 8px`）错解成四值，实测把 28px 的按钮顶成 44px。

    原来的实现没有幂等保护：每次 Show / Polish 事件都对**整棵树**重刷，
    于是一个面板 show 出来会触发 N 次全树 re-polish，把控件尺寸改坏，
    也是启动多花 3 秒的原因之一。

    现在：已带 `semanticPolished` 标记的控件直接跳过。
    """
    widgets = [root]
    if isinstance(root, QWidget):
        widgets.extend(root.findChildren(QWidget))
    for widget in widgets:
        if widget.property("semanticPolished") is True:
            continue
        _polish_one(widget)
    return root


class SemanticWidgetPolisher(QObject):
    """在历史控件首次显示时应用语义属性。"""

    def eventFilter(self, watched, event):
        if event.type() in (QEvent.Show, QEvent.Polish) and isinstance(watched, QWidget):
            polish_widget_tree(watched)
        return False


def install_semantic_polisher(app=None):
    app = app or QApplication.instance()
    if app is None:
        return None
    current = app.property("semanticWidgetPolisher")
    if current is not None:
        return current
    polisher = SemanticWidgetPolisher(app)
    app.installEventFilter(polisher)
    app.setProperty("semanticWidgetPolisher", polisher)
    for window in app.topLevelWidgets():
        polish_widget_tree(window)
    return polisher
