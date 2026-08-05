from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.models.layer_group import LayerGroup


class SizeMatchViewModel(QObject):
    stateChanged = Signal()

    def __init__(self, workspace, parent=None) -> None:
        super().__init__(parent)
        self._workspace = workspace
        workspace.documentObjectChanged.connect(lambda _document: self.stateChanged.emit())

    @property
    def _manager(self):
        return self._workspace.document.layer_size_match_manager

    @Property(bool, notify=stateChanged)
    def globalEnabled(self) -> bool:
        return bool(self._manager.global_enabled)

    @Property("QVariantList", notify=stateChanged)
    def layerNames(self):
        return [
            str(getattr(layer, "name", ""))
            for layer in self._workspace.document.layers
            if not isinstance(layer, LayerGroup) and str(getattr(layer, "name", ""))
        ]

    @Property("QVariantList", notify=stateChanged)
    def relations(self):
        result = []
        for relation in self._manager.relations:
            result.append(
                {
                    "id": str(relation.get("id") or ""),
                    "sourceName": str(relation.get("source_layer_name") or ""),
                    "targetNames": list(relation.get("target_layer_names") or []),
                    "enabled": bool(relation.get("enabled", True)),
                    "padding": int(relation.get("padding", 1)),
                    "oneToMany": bool(relation.get("one_to_many", False)),
                    "autoRotate": bool(relation.get("auto_rotate", False)),
                    "autoMaskEnabled": bool(relation.get("auto_mask_enabled", False)),
                    "autoMaskThreshold": int(relation.get("auto_mask_threshold", 32)),
                    "autoMaskTolerance": int(relation.get("auto_mask_tolerance", 18)),
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
        self._workspace.requestPreview(force=True)

    @Slot(bool, result=bool)
    def setGlobalEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        if enabled == self.globalEnabled:
            return True
        self._workspace._ensure_history_baseline()
        self._manager.set_global_enabled(enabled)
        self._finish("切换尺寸匹配")
        return True

    @Slot(str, "QVariantList", int, bool, bool, bool, int, int, result=str)
    def addRelation(
        self,
        source_name: str,
        target_names,
        padding: int,
        one_to_many: bool,
        auto_rotate: bool,
        auto_mask_enabled: bool,
        threshold: int,
        tolerance: int,
    ) -> str:
        self._workspace._ensure_history_baseline()
        relation_id = self._manager.add_relation(
            str(source_name or ""),
            list(target_names or []),
            padding=max(0, int(padding)),
            one_to_many=bool(one_to_many),
            auto_rotate=bool(auto_rotate),
            auto_mask={
                "auto_mask_enabled": bool(auto_mask_enabled),
                "auto_mask_threshold": max(0, int(threshold)),
                "auto_mask_tolerance": max(0, int(tolerance)),
            },
        )
        if relation_id:
            self._finish("创建尺寸匹配")
        return str(relation_id or "")

    @Slot(str, result=bool)
    def removeRelation(self, relation_id: str) -> bool:
        if not any(str(item.get("id")) == str(relation_id or "") for item in self._manager.relations):
            return False
        self._workspace._ensure_history_baseline()
        success = bool(self._manager.remove_relation(str(relation_id or "")))
        if success:
            self._finish("删除尺寸匹配")
        return success

    @Slot(str, bool, result=bool)
    def setRelationEnabled(self, relation_id: str, enabled: bool) -> bool:
        relation = next((item for item in self._manager.relations if str(item.get("id")) == str(relation_id or "")), None)
        if relation is None:
            return False
        self._workspace._ensure_history_baseline()
        relation["enabled"] = bool(enabled)
        self._finish("切换尺寸匹配关系")
        return True
