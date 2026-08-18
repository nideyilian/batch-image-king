from __future__ import annotations

import os

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.models.layer_group import LayerGroup


class BindingManagerViewModel(QObject):
    stateChanged = Signal()

    def __init__(self, workspace, parent=None) -> None:
        super().__init__(parent)
        self._workspace = workspace
        workspace.documentObjectChanged.connect(lambda _document: self.stateChanged.emit())

    @property
    def _manager(self):
        return self._workspace.document.binding_manager

    @Property(bool, notify=stateChanged)
    def globalEnabled(self) -> bool:
        return bool(self._manager.global_enabled)

    @Property("QVariantList", notify=stateChanged)
    def groups(self):
        statistics = self._manager.get_global_combination_statistics()
        return [
            {
                "id": str(info.get("group_id") or ""),
                "name": str(info.get("name") or "未命名组"),
                "layerNames": list(info.get("layers") or []),
                "layerCount": int(info.get("layer_count") or 0),
                "categoryCount": len(info.get("categories") or []),
                "selectedCategory": str(
                    getattr(
                        self._manager.binding_groups.get(str(info.get("group_id") or "")),
                        "last_selected_category",
                        "",
                    )
                    or ""
                ),
                "usedCombinations": int(
                    statistics.get(str(info.get("group_id") or ""), {}).get("total_used_combinations") or 0
                ),
            }
            for info in self._manager.get_binding_groups_info()
        ]

    @Property("QVariantList", notify=stateChanged)
    def layerOptions(self):
        result = []
        for index, layer in enumerate(self._workspace.document.layers):
            if isinstance(layer, LayerGroup):
                continue
            is_text = hasattr(layer, "get_text_lines")
            if is_text:
                try:
                    candidate_count = len(layer.get_text_lines())
                except Exception:
                    candidate_count = 0
                source_type = "文字"
            else:
                files = getattr(layer, "image_files", None) or getattr(layer, "files", None) or []
                candidate_count = len(files) if isinstance(files, (list, tuple)) else 0
                if not candidate_count and bool(getattr(layer, "is_folder", False)):
                    source = str(getattr(layer, "image_source", "") or "")
                    try:
                        candidate_count = sum(1 for name in os.listdir(source) if os.path.isfile(os.path.join(source, name)))
                    except OSError:
                        candidate_count = 0
                source_type = "图片"
            result.append(
                {
                    "index": index,
                    "name": str(getattr(layer, "name", f"图层 {index + 1}")),
                    "type": source_type,
                    "candidateCount": candidate_count,
                }
            )
        return result

    def _finish(self, action: str) -> None:
        document = self._workspace.document
        document.is_modified = True
        document.save_state(action)
        document.document_changed.emit()
        self.stateChanged.emit()
        self._workspace.documentInfoChanged.emit()
        self._workspace.historyStateChanged.emit()

    @Slot(bool, result=bool)
    def setGlobalEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        if enabled == self.globalEnabled:
            return True
        self._workspace._ensure_history_baseline()
        self._manager.set_global_enabled(enabled)
        self._finish("切换绑定功能")
        return True

    @Slot(str, "QVariantList", result=str)
    def createGroup(self, name: str, layer_indices) -> str:
        name = str(name or "").strip()
        indices = sorted({int(index) for index in list(layer_indices or [])})
        layers = [
            self._workspace.document.layers[index]
            for index in indices
            if 0 <= index < len(self._workspace.document.layers)
            and not isinstance(self._workspace.document.layers[index], LayerGroup)
        ]
        if not name or len(layers) < 2:
            return ""
        if any(group.name == name for group in self._manager.binding_groups.values()):
            return ""
        self._workspace._ensure_history_baseline()
        group_id = str(self._manager.create_binding_group(name, layers) or "")
        if group_id:
            self._finish("创建绑定组")
        return group_id

    @Slot(str, str, result=bool)
    def renameGroup(self, group_id: str, name: str) -> bool:
        group = self._manager.binding_groups.get(str(group_id or ""))
        name = str(name or "").strip()
        if group is None or not name:
            return False
        if any(item is not group and item.name == name for item in self._manager.binding_groups.values()):
            return False
        self._workspace._ensure_history_baseline()
        group.name = name
        self._finish("重命名绑定组")
        return True

    @Slot(str, result=bool)
    def deleteGroup(self, group_id: str) -> bool:
        group_id = str(group_id or "")
        if group_id not in self._manager.binding_groups:
            return False
        self._workspace._ensure_history_baseline()
        self._manager.delete_binding_group(group_id)
        self._finish("删除绑定组")
        return True

    @Slot(str, result=bool)
    def resetCombinationHistory(self, group_id: str = "") -> bool:
        self._manager.reset_global_combination_history(str(group_id or "") or None)
        self.stateChanged.emit()
        return True

    @Slot(result=int)
    def previewNextCombination(self) -> int:
        if not self.globalEnabled or not self._manager.binding_groups:
            return 0
        document = self._workspace.document
        with self._workspace._document_lock:
            mapping = self._manager.randomize_bound_layers(document.layers)
            if not mapping:
                self.stateChanged.emit()
                return 0
            invalidate = getattr(document, "_invalidate_render_cache", None)
            if callable(invalidate):
                invalidate()
        document.layer_changed.emit()
        document.document_changed.emit()
        self._workspace._layer_model.reset_from_document()
        self._workspace.selectionChanged.emit()
        self._workspace.requestPreview(force=True)
        self.stateChanged.emit()
        return len(mapping)
