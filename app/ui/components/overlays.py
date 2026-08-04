"""弹层组件：确认框、弹出面板、菜单和命令面板。"""

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
)

from app.ui.components.button import Button
from app.ui.components.dialog import Dialog
from app.ui.theme import Theme


class AlertDialog(Dialog):
    def __init__(self, title, description="", destructive=False, parent=None):
        super().__init__(parent, title)
        self.setProperty("role", "alert-dialog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            Theme.spacing("lg"), Theme.spacing("lg"),
            Theme.spacing("lg"), Theme.spacing("lg"))
        layout.setSpacing(Theme.spacing("md"))
        self.title_label = QLabel(title, self)
        self.title_label.setProperty("role", "dialog-title")
        self.description_label = QLabel(description, self)
        self.description_label.setProperty("role", "muted")
        self.description_label.setWordWrap(True)
        self.cancel_button = Button("取消", variant="outline", parent=self)
        self.confirm_button = Button(
            "确认", variant="destructive" if destructive else "default", parent=self)
        self.cancel_button.clicked.connect(self.reject)
        self.confirm_button.clicked.connect(self.accept)
        layout.addWidget(self.title_label)
        if description:
            layout.addWidget(self.description_label)
        layout.addWidget(self.button_row([self.cancel_button, self.confirm_button]))


class Popover(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent, Qt.Popup)
        self.setProperty("role", "popover-surface")

    def show_for(self, anchor, offset=None):
        offset = offset or anchor.rect().bottomLeft()
        self.move(anchor.mapToGlobal(offset))
        self.show()
        self.raise_()


class DropdownMenu(QMenu):
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.setProperty("role", "dropdown-menu")

    def add_item(self, text, callback=None, value=None, icon=None, checkable=False):
        action = QAction(icon, text, self) if icon is not None else QAction(text, self)
        action.setCheckable(checkable)
        action.setData(value)
        if callback is not None:
            action.triggered.connect(callback)
        self.addAction(action)
        return action


class ContextMenu(DropdownMenu):
    def __init__(self, title="", parent=None):
        super().__init__(title, parent)
        self.setProperty("role", "context-menu")


class CommandPalette(Dialog):
    def __init__(self, parent=None, placeholder="搜索命令..."):
        super().__init__(parent, "命令")
        self.setProperty("role", "command-palette")
        self.resize(520, 360)
        self.search_input = QLineEdit(self)
        self.search_input.setPlaceholderText(placeholder)
        self.command_list = QListWidget(self)
        self.command_list.setProperty("role", "command-list")
        self._commands = {}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(
            Theme.spacing("md"), Theme.spacing("md"),
            Theme.spacing("md"), Theme.spacing("md"))
        layout.setSpacing(Theme.spacing("sm"))
        layout.addWidget(self.search_input)
        layout.addWidget(self.command_list, 1)
        self.search_input.textChanged.connect(self.set_query)
        self.command_list.itemActivated.connect(
            lambda item: self.trigger_command(item.data(Qt.UserRole)))

    def add_command(self, value, label, callback=None, keywords=""):
        key = str(value)
        item = QListWidgetItem(label)
        item.setData(Qt.UserRole, key)
        item.setData(Qt.UserRole + 1, "%s %s" % (label, keywords))
        self.command_list.addItem(item)
        self._commands[key] = callback
        return item

    def set_query(self, query):
        needle = str(query).strip().casefold()
        for row in range(self.command_list.count()):
            item = self.command_list.item(row)
            haystack = str(item.data(Qt.UserRole + 1)).casefold()
            item.setHidden(bool(needle) and needle not in haystack)

    def visible_commands(self):
        return [
            self.command_list.item(row).data(Qt.UserRole)
            for row in range(self.command_list.count())
            if not self.command_list.item(row).isHidden()
        ]

    def trigger_command(self, value):
        callback = self._commands.get(str(value))
        if callback is None:
            return False
        callback()
        self.accept()
        return True
