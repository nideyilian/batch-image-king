import logging

logger = logging.getLogger(__name__)
import copy
from typing import Dict, Iterable, List, Optional, Tuple

from app.models.layer_group import LayerGroup


def is_layer_group(node) -> bool:
    return isinstance(node, LayerGroup) or getattr(node, "is_layer_group", False) or getattr(node, "type", None) == "group"


def get_parent_group_id(layer) -> Optional[str]:
    value = getattr(layer, "parent_group_id", None)
    if value is None:
        value = getattr(layer, "_parent_group_id", None)
    return str(value) if value else None


def set_parent_group_id(layer, group_id: Optional[str]):
    value = str(group_id) if group_id else None
    try:
        setattr(layer, "parent_group_id", value)
    except Exception:
        logger.debug("静默异常已忽略: except in utils/layer_tree.py")
        pass
    try:
        setattr(layer, "_parent_group_id", value)
    except Exception:
        logger.debug("静默异常已忽略: except in utils/layer_tree.py")
        pass


def group_map(nodes: Iterable) -> Dict[str, LayerGroup]:
    return {
        str(node.group_id): node
        for node in nodes or []
        if is_layer_group(node) and getattr(node, "group_id", None)
    }


def is_effectively_visible(layer, nodes: Iterable) -> bool:
    if not getattr(layer, "visible", True):
        return False
    gid = get_parent_group_id(layer)
    if not gid:
        return True
    group = group_map(nodes).get(gid)
    return bool(getattr(group, "visible", True)) if group else True


def is_effectively_locked(layer, nodes: Iterable) -> bool:
    if getattr(layer, "locked", False):
        return True
    gid = get_parent_group_id(layer)
    if not gid:
        return False
    group = group_map(nodes).get(gid)
    return bool(getattr(group, "locked", False)) if group else False


def render_layers(nodes: Iterable) -> List:
    return [
        node for node in nodes or []
        if not is_layer_group(node) and is_effectively_visible(node, nodes)
    ]


def real_layers(nodes: Iterable, include_hidden: bool = True) -> List:
    layers = [node for node in nodes or [] if not is_layer_group(node)]
    if include_hidden:
        return layers
    return [node for node in layers if is_effectively_visible(node, nodes)]


def child_indices_for_group(nodes: Iterable, group_id: str, include_hidden: bool = True) -> List[int]:
    """Return direct child layer indices for a group in document order."""
    node_list = list(nodes or [])
    gid = str(group_id) if group_id else ""
    if not gid:
        return []
    result = []
    for idx, node in enumerate(node_list):
        if is_layer_group(node):
            continue
        if get_parent_group_id(node) != gid:
            continue
        if include_hidden or is_effectively_visible(node, node_list):
            result.append(idx)
    return result


def child_layers_for_group(nodes: Iterable, group_id: str, include_hidden: bool = True) -> List:
    node_list = list(nodes or [])
    return [node_list[idx] for idx in child_indices_for_group(node_list, group_id, include_hidden=include_hidden)]


def group_bounds(nodes: Iterable, group_or_id, include_hidden: bool = False) -> Optional[Tuple[int, int, int, int]]:
    """Return logical (left, top, right, bottom) bounds for a group's children."""
    node_list = list(nodes or [])
    group_id = getattr(group_or_id, "group_id", group_or_id)
    child_indices = child_indices_for_group(node_list, str(group_id), include_hidden=include_hidden)
    bounds = []
    for idx in child_indices:
        layer = node_list[idx]
        try:
            x = int(getattr(layer, "x", 0))
            y = int(getattr(layer, "y", 0))
            w = max(0, int(getattr(layer, "width", 0)))
            h = max(0, int(getattr(layer, "height", 0)))
        except Exception:
            logger.debug("静默异常已忽略: except in utils/layer_tree.py")
            continue
        bounds.append((x, y, x + w, y + h))
    if not bounds:
        return None
    return (
        min(item[0] for item in bounds),
        min(item[1] for item in bounds),
        max(item[2] for item in bounds),
        max(item[3] for item in bounds),
    )


def expand_group_indices(nodes: Iterable, indices: Iterable[int], include_groups: bool = False) -> List[int]:
    """Expand selected group headers to their child layer indices."""
    node_list = list(nodes or [])
    result = []
    for idx in indices or []:
        if not (0 <= idx < len(node_list)):
            continue
        node = node_list[idx]
        if is_layer_group(node):
            if include_groups and idx not in result:
                result.append(idx)
            for child_idx in child_indices_for_group(node_list, getattr(node, "group_id", ""), include_hidden=True):
                if child_idx not in result:
                    result.append(child_idx)
        elif idx not in result:
            result.append(idx)
    return result


def display_entries(nodes: Iterable) -> List[Tuple[int, object, int]]:
    """Return (document index, node, depth) in panel top-to-bottom order."""
    node_list = list(nodes or [])
    entries: List[Tuple[int, object, int]] = []
    groups = group_map(node_list)
    children_by_group: Dict[str, List[Tuple[int, object]]] = {}
    for idx, node in enumerate(node_list):
        gid = get_parent_group_id(node)
        if gid and gid in groups:
            children_by_group.setdefault(gid, []).append((idx, node))

    for idx in range(len(node_list) - 1, -1, -1):
        node = node_list[idx]
        gid = get_parent_group_id(node)
        if gid and gid in groups:
            # Grouped children are emitted directly under their group header.
            continue
        entries.append((idx, node, 0))
        if is_layer_group(node) and getattr(node, "expanded", True):
            group_id = str(getattr(node, "group_id", "") or "")
            for child_idx, child in reversed(children_by_group.get(group_id, [])):
                entries.append((child_idx, child, 1))
    return entries


def serialize_layer_tree(nodes: Iterable, serialize_layer_func) -> List[dict]:
    """Serialize the linear runtime list into recursive group data."""
    node_list = list(nodes or [])
    grouped_children: Dict[str, List[dict]] = {}
    top_level: List[dict] = []

    for node in node_list:
        if is_layer_group(node):
            continue
        data = serialize_layer_func(node)
        data.pop("parent_group_id", None)
        data.pop("_parent_group_id", None)
        gid = get_parent_group_id(node)
        if gid:
            grouped_children.setdefault(gid, []).append(data)
        else:
            top_level.append(data)

    result: List[dict] = []
    emitted_groups = set()
    for node in node_list:
        if is_layer_group(node):
            data = node.serialize() if hasattr(node, "serialize") else {}
            gid = str(getattr(node, "group_id", "") or "")
            data["children"] = grouped_children.get(gid, [])
            result.append(data)
            emitted_groups.add(gid)
            continue
        gid = get_parent_group_id(node)
        if not gid:
            result.append(serialize_layer_func(node))
        elif gid not in emitted_groups and gid not in group_map(node_list):
            # Orphaned child: preserve it as a normal layer instead of dropping data.
            data = serialize_layer_func(node)
            data.pop("parent_group_id", None)
            data.pop("_parent_group_id", None)
            result.append(data)
    return result


def deserialize_layer_tree(layers_data: Iterable[dict], deserialize_layer_func, parent=None) -> List:
    """Flatten recursive group data into the runtime linear list."""
    result: List = []
    for item in layers_data or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "group":
            group = LayerGroup.deserialize(item, parent=parent)
            result.append(group)
            for child_data in item.get("children", []) or []:
                if not isinstance(child_data, dict):
                    continue
                child = deserialize_layer_func(copy.deepcopy(child_data), parent=parent)
                set_parent_group_id(child, group.group_id)
                result.append(child)
        else:
            result.append(deserialize_layer_func(copy.deepcopy(item), parent=parent))
    return result
