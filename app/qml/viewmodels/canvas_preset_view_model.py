from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.utils.canvas_preset_manager import CanvasPresetManager


class CanvasPresetViewModel(QObject):
    presetsChanged = Signal()

    def __init__(self, workspace, manager=None, parent=None) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._manager = manager or CanvasPresetManager()

    @Property("QVariantList", notify=presetsChanged)
    def presets(self):
        return [dict(preset) for preset in self._manager.get_all_presets()]

    @Property(int, notify=presetsChanged)
    def count(self) -> int:
        return len(self._manager.get_all_presets())

    @Slot(str, int, int, result=bool)
    def createPreset(self, name: str, width: int, height: int) -> bool:
        name = str(name or "").strip()
        success = bool(self._manager.add_custom_preset(name, int(width), int(height)))
        if success:
            self.presetsChanged.emit()
        return success

    @Slot(str, str, int, int, result=bool)
    def renamePreset(self, old_name: str, new_name: str, width: int, height: int) -> bool:
        success = bool(
            self._manager.update_custom_preset(
                str(old_name or "").strip(),
                str(new_name or "").strip(),
                int(width),
                int(height),
            )
        )
        if success:
            self.presetsChanged.emit()
        return success

    @Slot(str, result=bool)
    def deletePreset(self, name: str) -> bool:
        success = bool(self._manager.remove_custom_preset(str(name or "").strip()))
        if success:
            self.presetsChanged.emit()
        return success

    @Slot(int, result=bool)
    def applyPreset(self, index: int) -> bool:
        presets = self._manager.get_all_presets()
        if not 0 <= int(index) < len(presets):
            return False
        preset = presets[int(index)]
        return bool(self._workspace.resizeCanvas(int(preset["width"]), int(preset["height"])))
