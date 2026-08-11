from __future__ import annotations

from PySide6.QtCore import QObject, Property, QUrl, Signal, Slot

from app.utils.preset_document_loader import documents_from_preset_data
from app.utils.preset_manager import PresetManager


class PresetManagerViewModel(QObject):
    presetsChanged = Signal()
    stateChanged = Signal()

    def __init__(self, workspace, sessions=None, manager=None, parent=None) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._sessions = sessions
        self._manager = manager or PresetManager()
        self._last_error = ""

    def _set_error(self, message: str) -> None:
        self._last_error = str(message or "")
        self.stateChanged.emit()

    def _manager_error(self, fallback: str) -> str:
        return str(getattr(self._manager, "last_error", "") or fallback)

    @Property(str, notify=stateChanged)
    def lastError(self) -> str:
        return self._last_error

    @Property("QVariantList", notify=presetsChanged)
    def presets(self):
        result = []
        for preset in self._manager.get_all_presets():
            summary = preset
            result.append(
                {
                    "id": str(summary.get("id") or ""),
                    "name": str(summary.get("name") or "未命名预设"),
                    "description": str(summary.get("description") or ""),
                    "type": str(summary.get("type") or "single_document"),
                    "documentCount": int(summary.get("document_count") or 1),
                    "totalLayers": int(summary.get("total_layers") or 0),
                    "canvasSizes": list(summary.get("canvas_sizes") or []),
                    "createdAt": str(summary.get("created_at") or ""),
                }
            )
        return result

    @Property(int, notify=presetsChanged)
    def count(self) -> int:
        return len(self._manager.get_all_presets())

    def _name_exists(self, name: str, *, exclude_id: str = "") -> bool:
        normalized = str(name or "").strip().casefold()
        return any(
            str(preset.get("name") or "").strip().casefold() == normalized
            and str(preset.get("id") or "") != str(exclude_id or "")
            for preset in self._manager.get_all_presets()
        )

    def _preset_exists(self, preset_id: str) -> bool:
        preset_id = str(preset_id or "")
        return bool(preset_id) and any(
            str(preset.get("id") or "") == preset_id
            for preset in self._manager.get_all_presets()
        )

    @staticmethod
    def _local_path(path_or_url: str) -> str:
        text = str(path_or_url or "")
        url = QUrl(text)
        return url.toLocalFile() if url.isLocalFile() else text

    def _session_document(self, index: int):
        if self._sessions is None or not 0 <= int(index) < self._sessions.count:
            return None
        document = self._sessions.documentAt(int(index))
        if document is None:
            return None
        title = str(
            self._sessions.data(
                self._sessions.index(int(index), 0), self._sessions.TitleRole
            )
            or f"标签页 {int(index) + 1}"
        )
        document.tab_name = title
        document.original_tab_name = title
        return document

    def _documents_for_save(self, *, include_all: bool):
        if self._sessions is not None:
            if self._sessions.count <= 0:
                return []
            indices = (
                range(self._sessions.count)
                if include_all
                else [self._sessions.activeIndex]
            )
            return [
                document
                for index in indices
                if (document := self._session_document(index)) is not None
            ]
        document = getattr(self._workspace, "document", None)
        return [document] if document is not None else []

    def _save_documents(self, name: str, description: str, documents) -> bool:
        name = str(name or "").strip()
        if not name:
            self._set_error("预设名称不能为空")
            return False
        if self._name_exists(name):
            self._set_error("已存在同名预设")
            return False
        documents = list(documents or [])
        if not documents:
            self._set_error("没有可保存的文档")
            return False
        preset_id = self._manager.save_preset_documents(
            name,
            str(description or "").strip(),
            documents,
            {},
        )
        if not isinstance(preset_id, str) or not preset_id:
            self._set_error("保存预设失败")
            return False
        self._set_error("")
        self.presetsChanged.emit()
        return True

    @Slot(str, str, result=bool)
    def saveCurrent(self, name: str, description: str = "") -> bool:
        return self._save_documents(
            name,
            description,
            self._documents_for_save(include_all=False),
        )

    @Slot(str, str, result=bool)
    def saveAll(self, name: str, description: str = "") -> bool:
        return self._save_documents(
            name,
            description,
            self._documents_for_save(include_all=True),
        )

    @Slot(str, result=int)
    def loadPreset(self, preset_id: str) -> int:
        data = self._manager.load_preset(str(preset_id or ""))
        if not data:
            self._set_error("无法读取预设")
            return 0
        documents = documents_from_preset_data(data)
        if not documents:
            self._set_error("预设中没有可用文档")
            return 0
        if self._sessions is not None:
            loaded = int(self._sessions.appendDocuments(documents, "加载预设"))
        else:
            loaded = 1 if self._workspace.activateDocument(documents[0]) else 0
        if not loaded:
            self._set_error("无法将预设加入工作区")
            return 0
        self._manager.touch_preset_used(str(preset_id or ""))
        self._set_error("")
        self.presetsChanged.emit()
        return loaded

    @Slot(str, result=str)
    def duplicatePreset(self, preset_id: str) -> str:
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return ""
        new_id = str(self._manager.duplicate_preset(preset_id) or "")
        if not new_id:
            self._set_error("复制预设失败")
            return ""
        self._set_error("")
        self.presetsChanged.emit()
        return new_id

    @Slot(str, str, result=bool)
    def exportPreset(self, preset_id: str, export_path: str) -> bool:
        preset_id = str(preset_id or "")
        export_path = self._local_path(export_path)
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return False
        if not export_path:
            self._set_error("请选择导出位置")
            return False
        success = bool(self._manager.export_preset(preset_id, export_path))
        self._set_error("" if success else self._manager_error("导出预设失败"))
        return success

    @Slot(str, result=int)
    def exportAll(self, export_path: str) -> int:
        export_path = self._local_path(export_path)
        if not export_path:
            self._set_error("请选择导出位置")
            return 0
        if self.count <= 0:
            self._set_error("没有可导出的预设")
            return 0
        exported = int(self._manager.export_all_presets(export_path) or 0)
        self._set_error(
            "" if exported > 0 else self._manager_error("导出预设合集失败")
        )
        return exported

    @Slot(str, result=int)
    def importPreset(self, import_path: str) -> int:
        import_path = self._local_path(import_path)
        if not import_path:
            self._set_error("请选择要导入的预设文件")
            return 0
        before_count = self.count
        imported_id = self._manager.import_preset(import_path)
        imported = max(0, self.count - before_count)
        if not imported_id or imported <= 0:
            self._set_error(
                self._manager_error("导入预设失败，文件可能已损坏或格式不正确")
            )
            return 0
        self._set_error("")
        self.presetsChanged.emit()
        return imported

    @Slot(str, str, str, result=bool)
    def renamePreset(self, preset_id: str, name: str, description: str = "") -> bool:
        preset_id = str(preset_id or "")
        name = str(name or "").strip()
        if not preset_id or not name:
            self._set_error("预设名称不能为空")
            return False
        if self._name_exists(name, exclude_id=preset_id):
            self._set_error("已存在同名预设")
            return False
        success = bool(self._manager.update_preset(preset_id, name=name, description=str(description or "").strip()))
        self._set_error("" if success else "更新预设失败")
        if success:
            self.presetsChanged.emit()
        return success

    @Slot(str, result=bool)
    def deletePreset(self, preset_id: str) -> bool:
        preset_id = str(preset_id or "")
        if not self._preset_exists(preset_id):
            self._set_error("预设不存在")
            return False
        success = bool(self._manager.delete_preset(preset_id))
        self._set_error("" if success else "删除预设失败")
        if success:
            self.presetsChanged.emit()
        return success
