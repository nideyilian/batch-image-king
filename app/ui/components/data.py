"""数据与文件组件：结构化表格和文件拖放区。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QLabel,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)


class Table(QTableWidget):
    def __init__(self, parent=None, headers=None):
        super().__init__(parent)
        self.setProperty("role", "table")
        self.setAlternatingRowColors(True)
        self.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.setEditTriggers(QAbstractItemView.NoEditTriggers)
        if headers:
            self.setColumnCount(len(headers))
            self.setHorizontalHeaderLabels(headers)

    def set_rows(self, rows):
        self.setRowCount(len(rows))
        if rows and self.columnCount() == 0:
            self.setColumnCount(len(rows[0]))
        for row_index, row in enumerate(rows):
            for column_index, value in enumerate(row):
                self.setItem(row_index, column_index, QTableWidgetItem(str(value)))


class FileDropZone(QFrame):
    filesDropped = Signal(list)

    def __init__(self, parent=None, extensions=None, text="拖放文件到这里"):
        super().__init__(parent)
        self.setProperty("role", "file-drop-zone")
        self.setAcceptDrops(True)
        self._extensions = {
            extension.lower() if str(extension).startswith(".") else "." + str(extension).lower()
            for extension in (extensions or [])
        }
        self.label = QLabel(text, self)
        self.label.setProperty("role", "muted")
        self.label.setAlignment(Qt.AlignCenter)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.addWidget(self.label)

    def _is_allowed(self, path):
        if not self._extensions:
            return True
        lowered = str(path).lower()
        return any(lowered.endswith(extension) for extension in self._extensions)

    def accept_paths(self, paths):
        accepted = [str(path) for path in paths if self._is_allowed(path)]
        if accepted:
            self.filesDropped.emit(accepted)
        return accepted

    def dragEnterEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if any(self._is_allowed(path) for path in paths):
            self.setProperty("dragActive", True)
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragLeaveEvent(self, event):
        self.setProperty("dragActive", False)
        event.accept()

    def dropEvent(self, event):
        self.setProperty("dragActive", False)
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if self.accept_paths(paths):
            event.acceptProposedAction()
        else:
            event.ignore()
