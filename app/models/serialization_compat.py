"""Centralized compatibility helpers for persisted document data."""

from __future__ import annotations

from typing import Any, Dict


def normalize_layer_data(layer_data: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize old layer payloads before dispatching to layer classes."""
    if not isinstance(layer_data, dict):
        return {}
    data = dict(layer_data)
    if "type" not in data and "layer_type" in data:
        layer_type = data.get("layer_type")
        if layer_type in {"group", "text", "shaped", "image"}:
            data["type"] = layer_type
    data.setdefault("type", "image")
    return data


def serialize_binding_groups(manager: object) -> Dict[str, Any]:
    if manager is None:
        return {}
    if hasattr(manager, "serialize") and callable(manager.serialize):
        return manager.serialize()
    if hasattr(manager, "get_all_groups_data") and callable(manager.get_all_groups_data):
        return manager.get_all_groups_data()
    return {}


def restore_binding_groups(manager: object, binding_data: Dict[str, Any], layers: list) -> None:
    if manager is None:
        return
    data = binding_data or {}
    if hasattr(manager, "restore_from_data") and callable(manager.restore_from_data):
        manager.restore_from_data(data)
    elif hasattr(manager, "deserialize") and callable(manager.deserialize):
        manager.deserialize(data, layers)


def restore_parent_group_id(layer: object, layer_data: Dict[str, Any]) -> object:
    parent_group_id = layer_data.get("parent_group_id") or layer_data.get("_parent_group_id")
    if parent_group_id:
        setattr(layer, "parent_group_id", str(parent_group_id))
        setattr(layer, "_parent_group_id", str(parent_group_id))
    return layer

