from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

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

    @Slot(str, str, result=bool)
    def saveCurrent(self, name: str, description: str = "") -> bool:
        name = str(name or "").strip()
        if not name:
            self._set_error("预设名称不能为空")
            return False
        if self._name_exists(name):
            self._set_error("已存在同名预设")
            return False
        preset_id = self._manager.save_preset_from_document(name, self._workspace.document, str(description or "").strip())
        if not preset_id:
            self._set_error("保存预设失败")
            return False
        self._set_error("")
        self.presetsChanged.emit()
        return True

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
        if not preset_id or not any(str(preset.get("id")) == preset_id for preset in self._manager.get_all_presets()):
            self._set_error("预设不存在")
            return False
        success = bool(self._manager.delete_preset(preset_id))
        self._set_error("" if success else "删除预设失败")
        if success:
            self.presetsChanged.emit()
        return success
