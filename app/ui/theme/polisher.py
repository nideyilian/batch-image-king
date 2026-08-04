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


def _polish_button_box(box):
    for button in box.buttons():
        variant = _BUTTON_BOX_VARIANTS.get(box.buttonRole(button), "secondary")
        _set_if_missing(button, "variant", variant)


def _polish_button(button):
    if not button.accessibleName() and button.text():
        button.setAccessibleName(button.text().replace("&", ""))

    if button.property("variant") is not None:
        return
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


def _polish_one(widget):
    if isinstance(widget, QDialog):
        _set_if_missing(widget, "role", "dialog")
    if isinstance(widget, QDialogButtonBox):
        _polish_button_box(widget)
    if isinstance(widget, QAbstractButton):
        _polish_button(widget)
    if isinstance(widget, QProgressBar):
        _set_if_missing(widget, "role", "progress")
    if isinstance(widget, QGroupBox):
        _set_if_missing(widget, "role", "section")
    if isinstance(widget, QTabWidget):
        _set_if_missing(widget, "role", "tabs")
    widget.setProperty("semanticPolished", True)


def polish_widget_tree(root):
    """幂等地补齐 root 及其子控件的语义，不覆盖显式属性。"""
    widgets = [root]
    if isinstance(root, QWidget):
        widgets.extend(root.findChildren(QWidget))
    for widget in widgets:
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
