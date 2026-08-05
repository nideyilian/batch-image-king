from __future__ import annotations

import copy
from dataclasses import dataclass
import os
from typing import List, Optional

from PySide6.QtCore import (
    QAbstractListModel,
    QByteArray,
    QModelIndex,
    Property,
    Qt,
    QUrl,
    Signal,
    Slot,
)

from app.models.document import Document
from app.models.document_serializer import DocumentSerializer


@dataclass
class _DocumentSession:
    document: Document
    untitled_number: int
    custom_title: str = ""


class WorkspaceSessionViewModel(QAbstractListModel):
    TitleRole = Qt.UserRole + 1
    FilePathRole = Qt.UserRole + 2
    ModifiedRole = Qt.UserRole + 3
    ActiveRole = Qt.UserRole + 4
    CanvasWidthRole = Qt.UserRole + 5
    CanvasHeightRole = Qt.UserRole + 6

    countChanged = Signal()
    activeIndexChanged = Signal()
    pendingCloseIndexChanged = Signal()
    closeConfirmationRequested = Signal(int, str)
    savePathRequested = Signal(int, str)
    applicationCloseStateChanged = Signal()
    applicationCloseReady = Signal()

    MIN_CANVAS_SIZE = 16
    MAX_CANVAS_SIZE = 32768

    def __init__(self, workspace, parent=None) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._sessions: List[_DocumentSession] = []
        self._active_index = -1
        self._pending_close_index = -1
        self._next_untitled_number = 1
        self._application_close_pending = False
        self._application_close_approved = False
        self._close_others_keep_document: Optional[Document] = None

        self._append_initial_document(workspace.document)
        workspace.documentInfoChanged.connect(self._on_active_document_info_changed)

    def roleNames(self):
        return {
            self.TitleRole: QByteArray(b"title"),
            self.FilePathRole: QByteArray(b"filePath"),
            self.ModifiedRole: QByteArray(b"modified"),
            self.ActiveRole: QByteArray(b"active"),
            self.CanvasWidthRole: QByteArray(b"canvasWidth"),
            self.CanvasHeightRole: QByteArray(b"canvasHeight"),
        }

    def rowCount(self, parent=QModelIndex()) -> int:
        return 0 if parent.isValid() else len(self._sessions)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self._sessions):
            return None
        session = self._sessions[index.row()]
        document = session.document
        if role in (Qt.DisplayRole, self.TitleRole):
            return self._title_for(session)
        if role == self.FilePathRole:
            return str(getattr(document, "current_file_path", None) or "")
        if role == self.ModifiedRole:
            return bool(getattr(document, "is_modified", False))
        if role == self.ActiveRole:
            return index.row() == self._active_index
        if role == self.CanvasWidthRole:
            return int(getattr(document, "canvas_width", 0))
        if role == self.CanvasHeightRole:
            return int(getattr(document, "canvas_height", 0))
        return None

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._sessions)

    @Property(int, notify=activeIndexChanged)
    def activeIndex(self) -> int:
        return self._active_index

    @Property(int, notify=pendingCloseIndexChanged)
    def pendingCloseIndex(self) -> int:
        return self._pending_close_index

    @Property(bool, notify=applicationCloseStateChanged)
    def applicationClosePending(self) -> bool:
        return self._application_close_pending

    @Property(bool, notify=applicationCloseStateChanged)
    def applicationCloseApproved(self) -> bool:
        return self._application_close_approved

    @staticmethod
    def _local_path(path_or_url: str) -> str:
        text = str(path_or_url or "").strip()
        url = QUrl(text)
        return url.toLocalFile() if url.isLocalFile() else text

    @classmethod
    def _normalized_path(cls, path_or_url: str) -> str:
        path = cls._local_path(path_or_url)
        return os.path.normcase(os.path.realpath(os.path.abspath(path))) if path else ""

    @staticmethod
    def _prepare_history(document: Document, action: str) -> None:
        document._history_manager.clear()
        document.save_state(action)

    def _title_for(self, session: _DocumentSession) -> str:
        if session.custom_title:
            return session.custom_title
        path = getattr(session.document, "current_file_path", None)
        if path:
            return os.path.basename(path)
        return f"未命名-{session.untitled_number}.cmp"

    def _set_pending_close_index(self, index: int) -> None:
        index = int(index)
        if index != self._pending_close_index:
            self._pending_close_index = index
            self.pendingCloseIndexChanged.emit()

    def _connect_document(self, document: Document) -> None:
        document.document_changed.connect(self._on_document_changed)

    def _disconnect_document(self, document: Document) -> None:
        try:
            document.document_changed.disconnect(self._on_document_changed)
        except (RuntimeError, TypeError):
            pass

    def _append_initial_document(self, document: Document) -> None:
        session = _DocumentSession(document, self._next_untitled_number)
        self._next_untitled_number += 1
        self._sessions.append(session)
        self._active_index = 0
        self._connect_document(document)

    def _append_document(self, document: Document) -> int:
        index = len(self._sessions)
        self.beginInsertRows(QModelIndex(), index, index)
        session = _DocumentSession(document, self._next_untitled_number)
        self._next_untitled_number += 1
        self._sessions.append(session)
        self._connect_document(document)
        self.endInsertRows()
        self.countChanged.emit()
        return index

    def _insert_document(self, index: int, document: Document, custom_title: str = "") -> int:
        index = max(0, min(int(index), len(self._sessions)))
        self.beginInsertRows(QModelIndex(), index, index)
        session = _DocumentSession(document, self._next_untitled_number, str(custom_title or ""))
        self._next_untitled_number += 1
        self._sessions.insert(index, session)
        self._connect_document(document)
        self.endInsertRows()
        self.countChanged.emit()
        return index

    def _emit_row_changed(self, index: int) -> None:
        if not 0 <= index < len(self._sessions):
            return
        model_index = self.index(index, 0)
        self.dataChanged.emit(
            model_index,
            model_index,
            [
                self.TitleRole,
                self.FilePathRole,
                self.ModifiedRole,
                self.ActiveRole,
                self.CanvasWidthRole,
                self.CanvasHeightRole,
            ],
        )

    @Slot()
    def _on_document_changed(self) -> None:
        document = self.sender()
        for index, session in enumerate(self._sessions):
            if session.document is document:
                self._emit_row_changed(index)
                return

    @Slot()
    def _on_active_document_info_changed(self) -> None:
        self._emit_row_changed(self._active_index)

    @Slot(int, result=object)
    def documentAt(self, index: int):
        if 0 <= index < len(self._sessions):
            return self._sessions[index].document
        return None

    def appendDocuments(self, documents, action="加载预设") -> int:
        valid = [document for document in list(documents or []) if isinstance(document, Document)]
        if not valid or self._workspace.operationsBlocked:
            return 0
        first_index = -1
        for document in valid:
            document.current_file_path = None
            document.is_modified = False
            self._prepare_history(document, action)
            index = self._append_document(document)
            if first_index < 0:
                first_index = index
        if first_index >= 0:
            self.activateDocument(first_index)
        return len(valid)

    @Slot(int, result=int)
    def duplicateDocument(self, index: int) -> int:
        if not 0 <= int(index) < len(self._sessions) or self._workspace.operationsBlocked:
            return -1
        source_session = self._sessions[int(index)]
        try:
            data = copy.deepcopy(DocumentSerializer.prepare_document_data(source_session.document))
            duplicate = Document()
            if not DocumentSerializer.restore_document_data(duplicate, data):
                return -1
        except Exception:
            return -1
        duplicate.current_file_path = None
        duplicate.is_modified = True
        self._prepare_history(duplicate, "复制标签页")
        source_title = self._title_for(source_session)
        stem, extension = os.path.splitext(source_title)
        title = f"{stem} 副本{extension or '.cmp'}"
        new_index = self._insert_document(int(index) + 1, duplicate, title)
        if not self.activateDocument(new_index):
            self._remove_session(new_index)
            return -1
        self._workspace._set_status(f"已复制标签页：{title}", toast=True)
        return new_index

    @Slot(int, str, result=bool)
    def renameDocument(self, index: int, title: str) -> bool:
        if not 0 <= int(index) < len(self._sessions):
            return False
        title = str(title or "").strip()
        if not title:
            return False
        if not os.path.splitext(title)[1]:
            title += ".cmp"
        self._sessions[int(index)].custom_title = title
        self._emit_row_changed(int(index))
        return True

    @Slot(int, int, result=bool)
    def moveDocument(self, source_index: int, target_index: int) -> bool:
        source_index = int(source_index)
        target_index = int(target_index)
        if not 0 <= source_index < len(self._sessions):
            return False
        target_index = max(0, min(target_index, len(self._sessions) - 1))
        if source_index == target_index:
            return True
        active_document = self._sessions[self._active_index].document
        self.beginResetModel()
        session = self._sessions.pop(source_index)
        self._sessions.insert(target_index, session)
        self._active_index = next(
            index for index, item in enumerate(self._sessions) if item.document is active_document
        )
        self.endResetModel()
        self.activeIndexChanged.emit()
        return True

    @Slot(int, result=bool)
    def closeOtherDocuments(self, keep_index: int) -> bool:
        if not 0 <= int(keep_index) < len(self._sessions) or self._workspace.operationsBlocked:
            return False
        self._close_others_keep_document = self._sessions[int(keep_index)].document
        return self._advance_close_others()

    def _advance_close_others(self) -> bool:
        keep_document = self._close_others_keep_document
        if keep_document is None:
            return False
        for index, session in enumerate(self._sessions):
            if session.document is keep_document:
                continue
            if bool(getattr(session.document, "is_modified", False)):
                self.activateDocument(index)
                self._set_pending_close_index(index)
                self.closeConfirmationRequested.emit(index, self._title_for(session))
                return False
            self._close_session(index)
            return self._advance_close_others()
        keep_index = next(
            (index for index, session in enumerate(self._sessions) if session.document is keep_document),
            -1,
        )
        self._close_others_keep_document = None
        if keep_index >= 0:
            self.activateDocument(keep_index)
        return True

    @Slot(int, result=bool)
    def activateDocument(self, index: int) -> bool:
        if not 0 <= index < len(self._sessions):
            return False
        if index == self._active_index:
            return True
        if not self._workspace.activateDocument(self._sessions[index].document):
            return False

        previous = self._active_index
        self._active_index = index
        self._emit_row_changed(previous)
        self._emit_row_changed(index)
        self.activeIndexChanged.emit()
        return True

    @Slot(int, int, result=bool)
    def newDocument(self, width: int = 1080, height: int = 1350) -> bool:
        if self._workspace.operationsBlocked:
            self._workspace._set_status("批量导出期间无法新建文档", toast=True)
            return False
        width = int(width)
        height = int(height)
        if not (
            self.MIN_CANVAS_SIZE <= width <= self.MAX_CANVAS_SIZE
            and self.MIN_CANVAS_SIZE <= height <= self.MAX_CANVAS_SIZE
        ):
            self._workspace._set_status(
                f"画布尺寸必须在 {self.MIN_CANVAS_SIZE} 到 {self.MAX_CANVAS_SIZE} 像素之间",
                toast=True,
            )
            return False

        document = Document()
        document.create_new(width, height)
        self._prepare_history(document, "初始状态")
        index = self._append_document(document)
        if not self.activateDocument(index):
            self._remove_session(index)
            return False
        self._workspace._set_status(f"已新建 {width} x {height} 画布", toast=True)
        return True

    @Slot(str, result=bool)
    def openDocument(self, file_path: str) -> bool:
        if self._workspace.operationsBlocked:
            self._workspace._set_status("批量导出期间无法打开文档", toast=True)
            return False
        file_path = self._local_path(file_path)
        normalized = self._normalized_path(file_path)
        if not normalized:
            self._workspace._set_status("打开失败：文件路径为空", toast=True)
            return False

        for index, session in enumerate(self._sessions):
            current = getattr(session.document, "current_file_path", None)
            if current and self._normalized_path(current) == normalized:
                self.activateDocument(index)
                self._workspace._set_status(f"项目已打开：{self._title_for(session)}", toast=True)
                return True

        candidate = Document()
        if not candidate.load_document(file_path):
            self._workspace._set_status("打开失败：无法读取项目文件", toast=True)
            return False
        self._prepare_history(candidate, "打开文档")
        index = self._append_document(candidate)
        if not self.activateDocument(index):
            self._remove_session(index)
            return False
        self._workspace._set_status(f"已打开 {os.path.basename(file_path)}", toast=True)
        return True

    @Slot(int, result=bool)
    def requestClose(self, index: int) -> bool:
        if not 0 <= index < len(self._sessions):
            return False
        if self._workspace.operationsBlocked:
            self._workspace._set_status("批量导出期间无法关闭文档", toast=True)
            return False
        if not self.activateDocument(index):
            return False
        session = self._sessions[index]
        if bool(getattr(session.document, "is_modified", False)):
            self._set_pending_close_index(index)
            self.closeConfirmationRequested.emit(index, self._title_for(session))
            return False
        return self._close_session(index)

    @Slot(result=bool)
    def requestApplicationClose(self) -> bool:
        if self._application_close_approved:
            return True
        if self._workspace.operationsBlocked:
            self._workspace._set_status("请先结束正在运行的导出任务", toast=True)
            return False
        self._close_others_keep_document = None
        self._application_close_pending = True
        self._application_close_approved = False
        self.applicationCloseStateChanged.emit()
        return self._advance_application_close()

    def _advance_application_close(self) -> bool:
        for index, session in enumerate(self._sessions):
            if bool(getattr(session.document, "is_modified", False)):
                self.activateDocument(index)
                self._set_pending_close_index(index)
                self.closeConfirmationRequested.emit(index, self._title_for(session))
                return False
        self._set_pending_close_index(-1)
        self._application_close_pending = False
        self._application_close_approved = True
        self.applicationCloseStateChanged.emit()
        self.applicationCloseReady.emit()
        return True

    @Slot()
    def cancelClose(self) -> None:
        self._set_pending_close_index(-1)
        self._close_others_keep_document = None
        if self._application_close_pending:
            self._application_close_pending = False
            self._application_close_approved = False
            self.applicationCloseStateChanged.emit()

    @Slot(int, result=bool)
    def discardAndClose(self, index: int) -> bool:
        if not 0 <= index < len(self._sessions) or self._workspace.operationsBlocked:
            return False
        if self._application_close_pending:
            self._sessions[index].document.is_modified = False
            self._emit_row_changed(index)
            self._set_pending_close_index(-1)
            self._advance_application_close()
            return True
        if self._close_others_keep_document is not None:
            self._set_pending_close_index(-1)
            result = self._close_session(index)
            self._advance_close_others()
            return result
        self._set_pending_close_index(-1)
        return self._close_session(index)

    @Slot(int, str, result=bool)
    def saveAndClose(self, index: int, file_path: str = "") -> bool:
        if not 0 <= index < len(self._sessions) or self._workspace.operationsBlocked:
            return False
        if not self.activateDocument(index):
            return False
        session = self._sessions[index]
        target = self._local_path(file_path) or str(
            getattr(session.document, "current_file_path", None) or ""
        )
        if not target:
            self._set_pending_close_index(index)
            self.savePathRequested.emit(index, self._title_for(session))
            return False
        if not self._workspace.saveDocumentTo(target):
            return False
        if self._application_close_pending:
            self._set_pending_close_index(-1)
            self._advance_application_close()
            return True
        if self._close_others_keep_document is not None:
            self._set_pending_close_index(-1)
            result = self._close_session(index)
            self._advance_close_others()
            return result
        self._set_pending_close_index(-1)
        return self._close_session(index)

    def _remove_session(self, index: int) -> _DocumentSession:
        self.beginRemoveRows(QModelIndex(), index, index)
        session = self._sessions.pop(index)
        self._disconnect_document(session.document)
        self.endRemoveRows()
        self.countChanged.emit()
        return session

    def _close_session(self, index: int) -> bool:
        if not 0 <= index < len(self._sessions):
            return False

        if len(self._sessions) == 1:
            old_document = self._sessions[0].document
            replacement = Document()
            replacement.create_new(1080, 1350)
            self._prepare_history(replacement, "初始状态")
            self.beginResetModel()
            self._disconnect_document(old_document)
            self._sessions = [_DocumentSession(replacement, self._next_untitled_number)]
            self._next_untitled_number += 1
            self._connect_document(replacement)
            self._active_index = 0
            self.endResetModel()
            self._workspace.activateDocument(replacement)
            self._set_pending_close_index(-1)
            self.activeIndexChanged.emit()
            self._workspace._set_status("已关闭文档并新建空白画布", toast=True)
            return True

        was_active = index == self._active_index
        self._remove_session(index)
        if self._active_index > index:
            self._active_index -= 1
        elif was_active:
            self._active_index = min(index, len(self._sessions) - 1)
            if not self._workspace.activateDocument(self._sessions[self._active_index].document):
                return False
        self._set_pending_close_index(-1)
        self._emit_row_changed(self._active_index)
        self.activeIndexChanged.emit()
        self._workspace._set_status("已关闭文档", toast=True)
        return True
