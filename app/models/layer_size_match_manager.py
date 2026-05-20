#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图层大小匹配管理器
用于配置“源图层镂空 -> 目标图层位置尺寸匹配”的关系。
"""

from PySide6.QtCore import QObject, Signal
from typing import List, Dict, Any
import uuid


class LayerSizeMatchManager(QObject):
    """管理图层大小匹配关系（可选功能）。"""

    changed = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.global_enabled = False
        self.relations: List[Dict[str, Any]] = []

    def set_global_enabled(self, enabled: bool):
        enabled = bool(enabled)
        if self.global_enabled == enabled:
            return
        self.global_enabled = enabled
        self.changed.emit()

    def _normalize_targets(self, source_name: str, target_layer_names) -> List[str]:
        if isinstance(target_layer_names, str):
            candidates = [target_layer_names]
        elif isinstance(target_layer_names, (list, tuple)):
            candidates = list(target_layer_names)
        else:
            candidates = []

        normalized = []
        for name in candidates:
            n = str(name or "").strip()
            if not n or n == source_name:
                continue
            if n not in normalized:
                normalized.append(n)
        return normalized

    def add_relation(
        self,
        source_layer_name: str,
        target_layer_names,
        enabled: bool = True,
        padding: int = 1,
        one_to_many: bool = False,
        auto_rotate: bool = False,
    ) -> str:
        source_name = str(source_layer_name or "").strip()
        targets = self._normalize_targets(source_name, target_layer_names)
        if not source_name or not targets:
            return ""

        for relation in self.relations:
            old_targets = relation.get("target_layer_names", [])
            if relation.get("source_layer_name") == source_name and old_targets == targets:
                relation["enabled"] = bool(enabled)
                relation["padding"] = max(0, int(padding))
                relation["one_to_many"] = bool(one_to_many)
                relation["auto_rotate"] = bool(auto_rotate)
                relation["target_layer_name"] = targets[0]
                self.changed.emit()
                return str(relation.get("id", ""))

        relation_id = str(uuid.uuid4())
        self.relations.append({
            "id": relation_id,
            "source_layer_name": source_name,
            "target_layer_name": targets[0],  # 向后兼容
            "target_layer_names": targets,
            "enabled": bool(enabled),
            "padding": max(0, int(padding)),
            "one_to_many": bool(one_to_many),
            "auto_rotate": bool(auto_rotate),
        })
        self.changed.emit()
        return relation_id

    def remove_relation(self, relation_id: str) -> bool:
        rid = str(relation_id or "")
        if not rid:
            return False
        old_len = len(self.relations)
        self.relations = [r for r in self.relations if str(r.get("id", "")) != rid]
        if len(self.relations) != old_len:
            self.changed.emit()
            return True
        return False

    def update_relation(
        self,
        relation_id: str,
        source_layer_name: str,
        target_layer_names,
        enabled: bool,
        padding: int,
        one_to_many: bool = False,
        auto_rotate: bool = False,
    ):
        rid = str(relation_id or "")
        source_name = str(source_layer_name or "").strip()
        targets = self._normalize_targets(source_name, target_layer_names)
        if not source_name or not targets:
            return False
        for relation in self.relations:
            if str(relation.get("id", "")) == rid:
                relation["source_layer_name"] = source_name
                relation["target_layer_name"] = targets[0]
                relation["target_layer_names"] = targets
                relation["enabled"] = bool(enabled)
                relation["padding"] = max(0, int(padding))
                relation["one_to_many"] = bool(one_to_many)
                relation["auto_rotate"] = bool(auto_rotate)
                self.changed.emit()
                return True
        return False

    def get_active_relations(self) -> List[Dict[str, Any]]:
        if not self.global_enabled:
            return []
        active = []
        for relation in self.relations:
            if not bool(relation.get("enabled", True)):
                continue
            source_name = str(relation.get("source_layer_name", "")).strip()
            targets = relation.get("target_layer_names")
            if not isinstance(targets, list) or not targets:
                legacy_target = str(relation.get("target_layer_name", "")).strip()
                targets = [legacy_target] if legacy_target else []
            targets = self._normalize_targets(source_name, targets)
            if not source_name or not targets:
                continue
            active.append({
                "id": str(relation.get("id", "")),
                "source_layer_name": source_name,
                "target_layer_name": targets[0],  # 兼容字段
                "target_layer_names": targets,
                "enabled": True,
                "padding": max(0, int(relation.get("padding", 1))),
                "one_to_many": bool(relation.get("one_to_many", False)),
                "auto_rotate": bool(relation.get("auto_rotate", False)),
            })
        return active

    def serialize(self) -> Dict[str, Any]:
        return {
            "global_enabled": bool(self.global_enabled),
            "relations": [
                {
                    "id": str(r.get("id", "")),
                    "source_layer_name": str(r.get("source_layer_name", "")),
                    "target_layer_name": str(r.get("target_layer_name", "")),
                    "target_layer_names": list(r.get("target_layer_names", [])),
                    "enabled": bool(r.get("enabled", True)),
                    "padding": max(0, int(r.get("padding", 1))),
                    "one_to_many": bool(r.get("one_to_many", False)),
                    "auto_rotate": bool(r.get("auto_rotate", False)),
                }
                for r in self.relations
            ],
        }

    def deserialize(self, data: Dict[str, Any]):
        payload = data if isinstance(data, dict) else {}
        self.global_enabled = bool(payload.get("global_enabled", False))
        raw_relations = payload.get("relations", [])
        self.relations = []
        if isinstance(raw_relations, list):
            for item in raw_relations:
                if not isinstance(item, dict):
                    continue
                source_name = str(item.get("source_layer_name", "")).strip()
                raw_targets = item.get("target_layer_names", None)
                if not isinstance(raw_targets, list) or not raw_targets:
                    legacy_target = str(item.get("target_layer_name", "")).strip()
                    raw_targets = [legacy_target] if legacy_target else []
                targets = self._normalize_targets(source_name, raw_targets)
                if not source_name or not targets:
                    continue
                self.relations.append({
                    "id": str(item.get("id", "")) or str(uuid.uuid4()),
                    "source_layer_name": source_name,
                    "target_layer_name": targets[0],
                    "target_layer_names": targets,
                    "enabled": bool(item.get("enabled", True)),
                    "padding": max(0, int(item.get("padding", 1))),
                    "one_to_many": bool(item.get("one_to_many", False)),
                    "auto_rotate": bool(item.get("auto_rotate", False)),
                })
        self.changed.emit()
