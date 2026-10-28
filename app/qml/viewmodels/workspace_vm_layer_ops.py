"""WorkspaceViewModel 图层选择/命中/排列/样式复制方法组 mixin（P1-4 拆分）。

从 ``workspace_view_model.py`` 原样迁出的图层操作 setter 方法组（33 个方法），
语义不变。依赖主类实例方法（``_set_layer_attrs``、``_change_layer``、
``_selected_layers`` 等）与下列模块级名字。
"""

from __future__ import annotations

import copy
import math
import re
import uuid

from PySide6.QtCore import QPointF, Slot
from PySide6.QtGui import QPainterPath

from app.models.layer_group import LayerGroup
from app.models.layer_properties import ShapeType
from app.utils.layer_tree import (
    expand_group_indices,
    get_parent_group_id,
    group_bounds,
    is_effectively_locked,
    is_effectively_visible,
    is_layer_group,
    set_parent_group_id,
)

from .workspace_vm_shared import _COMMON_STYLE_ATTRIBUTES, _TEXT_STYLE_ATTRIBUTES


class WorkspaceLayerOpsMixin:
    @Slot(result=bool)
    def copySelectedLayerStyle(self) -> bool:
        if not self._ensure_operations_available():
            return False
        layer = self._selected_layer()
        if layer is None:
            self._set_status("请先选择要复制样式的图层", toast=True)
            return False
        layer_type = self._layer_model.layer_type_name(layer)
        values = {
            attr: copy.deepcopy(getattr(layer, attr))
            for attr in self._style_attributes_for_layer(layer)
            if hasattr(layer, attr)
        }
        if not values:
            self._set_status("当前图层没有可复制的样式", toast=True)
            return False
        self._layer_style_clipboard = {
            "layer_type": layer_type,
            "values": values,
            "summary": f"{getattr(layer, 'name', '图层')} · {layer_type}样式",
        }
        self.styleClipboardChanged.emit()
        self._set_status(f"已复制“{getattr(layer, 'name', '图层')}”的样式", toast=True)
        return True

    @Slot(result=bool)
    def pasteSelectedLayerStyle(self) -> bool:
        if not self._ensure_operations_available():
            return False
        if not self._layer_style_clipboard:
            self._set_status("尚未复制图层样式", toast=True)
            return False
        layer = self._selected_layer()
        if layer is None:
            self._set_status("请先选择要粘贴样式的图层", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定，无法粘贴样式", toast=True)
            return False

        source_type = self._layer_style_clipboard.get("layer_type", "")
        target_type = self._layer_model.layer_type_name(layer)
        allowed = set(_COMMON_STYLE_ATTRIBUTES)
        if source_type == target_type == "文字":
            allowed.update(_TEXT_STYLE_ATTRIBUTES)
        values = self._layer_style_clipboard.get("values", {})
        changes = {
            attr: copy.deepcopy(value)
            for attr, value in values.items()
            if attr in allowed and hasattr(layer, attr)
        }
        if not changes:
            self._set_status("复制的样式与当前图层不兼容", toast=True)
            return False

        index = self.selectedLayerIndex
        with self._document_lock:
            self._ensure_history_baseline()
            for attr, value in changes.items():
                setattr(layer, attr, value)
            self._document.is_modified = True
            self._document.bump_hit_test_version()
            self._document._invalidate_render_cache()
            self._document.save_state("粘贴图层样式")
        self._publish_content_change(index, f"已粘贴 {len(changes)} 项图层样式")
        return True

    @Slot(result=bool)
    def deleteSelectedLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        index = self.selectedLayerIndex
        layer = self._layer_model.layer_at(index)
        if layer is None:
            self._set_status("没有可删除的图层", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定，无法删除", toast=True)
            return False

        try:
            with self._document_lock:
                before_count = len(self._document.layers)
                self._ensure_history_baseline()
                self._document.remove_layer(index)
                if len(self._document.layers) == before_count:
                    return False
                self._document.is_modified = True
        except Exception as error:
            self._set_status(f"删除图层失败：{error}", toast=True)
            return False

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已删除图层", toast=True)
        return True

    def _duplicate_layer_name(self, original_name: str) -> str:
        original_name = str(original_name or "未命名图层")
        match = re.match(r"^(.*?)(?: 副本(?: \d+)?)?$", original_name)
        base_name = (match.group(1) if match else original_name).strip() or "未命名图层"
        existing_names = {str(getattr(layer, "name", "")) for layer in self._document.layers}
        candidate = f"{base_name} 副本"
        if candidate not in existing_names:
            return candidate
        number = 2
        while f"{base_name} 副本 {number}" in existing_names:
            number += 1
        return f"{base_name} 副本 {number}"

    @Slot(result=bool)
    def duplicateSelectedLayer(self) -> bool:
        if not self._ensure_operations_available():
            return False
        if not self.canDuplicateLayer:
            self._set_status("当前图层无法复制", toast=True)
            return False
        index = self.selectedLayerIndex
        original = self._selected_layer()

        try:
            with self._document_lock:
                self._ensure_history_baseline()
                try:
                    duplicate = original.duplicate(parent=self._document)
                except TypeError:
                    duplicate = original.duplicate()
                if duplicate is None:
                    raise RuntimeError("图层复制失败")

                if hasattr(duplicate, "_layer_id"):
                    duplicate._layer_id = str(uuid.uuid4())
                duplicate.name = self._duplicate_layer_name(getattr(original, "name", ""))

                if hasattr(duplicate, "x") and hasattr(duplicate, "width"):
                    max_x = max(0, self.canvasWidth - int(getattr(duplicate, "width", 0) or 0))
                    duplicate.x = min(max_x, max(0, int(getattr(original, "x", 0) or 0) + 12))
                if hasattr(duplicate, "y") and hasattr(duplicate, "height"):
                    max_y = max(0, self.canvasHeight - int(getattr(duplicate, "height", 0) or 0))
                    duplicate.y = min(max_y, max(0, int(getattr(original, "y", 0) or 0) + 12))

                changed_signal = getattr(duplicate, "changed", None)
                if changed_signal is not None:
                    changed_signal.connect(self._document.document_changed.emit)

                insert_index = index + 1
                self._document.layers.insert(insert_index, duplicate)
                self._document.selected_layer_index = insert_index
                self._document.selected_layer_indices = [insert_index]
                self._document.is_modified = True
                self._document._invalidate_render_cache()
                self._document.bump_hit_test_version()
                self._document.layer_changed.emit()
                self._document.layer_selected.emit(insert_index)
                self._document.layers_selection_changed.emit([insert_index])
                self._document.document_changed.emit()
                self._document.save_state("复制图层")
        except Exception as error:
            self._set_status(f"复制图层失败：{error}", toast=True)
            return False

        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"已创建 {duplicate.name}", toast=True)
        return True

    @Slot(str, result=bool)
    def moveSelectedLayer(self, direction: str) -> bool:
        if not self._ensure_operations_available():
            return False
        direction = str(direction or "").lower()
        if direction == "to_front":
            return self._move_selected_layer_to_boundary("front")
        if direction == "to_back":
            return self._move_selected_layer_to_boundary("back")
        allowed = self.canMoveLayerForward if direction == "forward" else self.canMoveLayerBackward
        if direction not in {"forward", "backward"} or not allowed:
            self._set_status("图层已在边界或相邻图层已锁定", toast=True)
            return False
        index = self.selectedLayerIndex
        selected_layer = self._selected_layer()

        with self._document_lock:
            self._ensure_history_baseline()
            if direction == "forward":
                self._document.move_layer_down(index)
                action_text = "前移一层"
            else:
                self._document.move_layer_up(index)
                action_text = "后移一层"
            try:
                new_index = self._document.layers.index(selected_layer)
            except ValueError:
                return False
            if new_index == index:
                return False
            self._document.is_modified = True
            self._document._invalidate_render_cache()
            self._document.document_changed.emit()

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"图层已{action_text}", toast=True)
        return True

    def _move_selected_layer_to_boundary(self, side: str) -> bool:
        """将选中图层移到顶层 (front) 或底层 (back)。"""
        if not self._ensure_operations_available() or self.selectedLayerIndex < 0:
            self._set_status("请先选择一个图层", toast=True)
            return False
        selected_layer = self._selected_layer()
        if selected_layer is None or self._is_effectively_locked(selected_layer):
            self._set_status("图层已锁定或不可移动", toast=True)
            return False

        n = len(self._document.layers)
        current = self.selectedLayerIndex
        target = (n - 1) if side == "front" else 0
        if target == current:
            return True

        with self._document_lock:
            self._ensure_history_baseline()
            layer = self._document.layers.pop(current)
            self._document.layers.insert(target, layer)
            action_text = "置于顶层" if side == "front" else "置于底层"
            self._document.is_modified = True
            self._document._invalidate_render_cache()
            self._document.save_state(action_text)
            self._document.document_changed.emit()

        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)
        self._set_status(f"图层已{action_text}", toast=True)
        return True

    @Slot(result=bool)
    def beginFreeTransform(self) -> bool:
        """Ctrl+T（PS 自由变换）入口：有选中层时显示提示并沿用画布现有的变换手柄。"""
        if not self._ensure_operations_available() or self.selectedLayerIndex < 0:
            self._set_status("请先选择一个图层再使用自由变换(Ctrl+T)", toast=True)
            return False
        self._set_status("自由变换：拖拽控制点缩放，Esc 取消", toast=True)
        self.documentInfoChanged.emit()
        self.selectionChanged.emit()
        return True

    @Slot(result=bool)
    def mergeSelectedDown(self) -> bool:
        """Ctrl+E（PS 向下合并图层）占位：当前实现等价于「编组为合并容器」。

        应用暂未实现像素级扁平化渲染，这里复用 groupSelectedLayers，
        但在状态栏中明确说明是 Ctrl+E 触发的向下合并动作。"""
        if not self._ensure_operations_available():
            return False
        idx = self.selectedLayerIndex
        if idx <= 0 or idx >= len(self._document.layers):
            self._set_status("请选择一个非最底层的图层以执行向下合并(Ctrl+E)", toast=True)
            return False
        upper = self._document.layers[idx]
        lower = self._document.layers[idx - 1]
        if self._is_effectively_locked(upper) or self._is_effectively_locked(lower):
            self._set_status("存在锁定图层，无法合并", toast=True)
            return False
        ok = self.groupSelectedLayers()
        if ok:
            self._set_status("已编组为合并容器（向下合并：Ctrl+E）", toast=True)
        return ok

    def _finish_arrangement(self, action: str, status: str, *, render: bool = True) -> None:
        self._document.is_modified = True
        self._document._invalidate_render_cache()
        self._document.bump_hit_test_version()
        self._document.save_state(action)
        self._document.layer_changed.emit()
        self._document.document_changed.emit()
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()
        self.viewSettingsChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        if render:
            self.requestPreview(force=True)
        self._set_status(status, toast=True)

    @Slot(int, bool, bool, result=bool)
    def selectLayerWithModifiers(self, index: int, ctrl: bool, shift: bool) -> bool:
        if self._layer_model.layer_at(index) is None:
            return False
        current = self.selectedLayerIndices
        if shift and self._selection_anchor_index >= 0:
            start = min(self._selection_anchor_index, index)
            end = max(self._selection_anchor_index, index)
            selection = list(range(start, end + 1))
            primary = index
        elif ctrl:
            selection = list(current)
            if index in selection:
                selection.remove(index)
                primary = selection[-1] if selection else -1
            else:
                selection.append(index)
                primary = index
            self._selection_anchor_index = index if primary >= 0 else -1
        else:
            selection = [index]
            primary = index
            self._selection_anchor_index = index
        self._dismiss_text_edit_overlay(primary)
        self._document.select_layers(selection, primary_index=primary)
        self._selected_vector_node_index = -1
        self.vectorEditChanged.emit()
        return True

    @Slot(float, float, float, float, bool, result=bool)
    def selectLayersInRect(self, left: float, top: float, right: float, bottom: float, additive: bool) -> bool:
        x1, x2 = sorted((float(left), float(right)))
        y1, y2 = sorted((float(top), float(bottom)))
        hits = []
        for index, layer in enumerate(self._document.layers):
            if is_layer_group(layer) or not bool(getattr(layer, "visible", True)):
                continue
            if not all(hasattr(layer, attr) for attr in ("x", "y", "width", "height")):
                continue
            layer_left = float(layer.x)
            layer_top = float(layer.y)
            layer_right = layer_left + float(layer.width)
            layer_bottom = layer_top + float(layer.height)
            if layer_right >= x1 and layer_left <= x2 and layer_bottom >= y1 and layer_top <= y2:
                hits.append(index)
        selection = list(self.selectedLayerIndices) if additive else []
        for index in hits:
            if index not in selection:
                selection.append(index)
        primary = hits[-1] if hits else (selection[-1] if selection else -1)
        self._dismiss_text_edit_overlay(primary)
        self._document.select_layers(selection, primary_index=primary)
        self._selection_anchor_index = primary
        return bool(hits)

    @Slot(float, float, result=int)
    def hitTestLayerAt(self, x: float, y: float) -> int:
        hits = []
        for index in range(len(self._document.layers) - 1, -1, -1):
            layer = self._document.layers[index]
            if is_layer_group(layer):
                continue
            if not is_effectively_visible(layer, self._document.layers):
                continue
            for position in self._layer_hit_positions(layer):
                if self._layer_contains_point(layer, x, y, position):
                    hits.append(index)
                    break
        if hits:
            return hits[0]

        selected = self._selected_layer()
        if is_layer_group(selected):
            bounds = group_bounds(self._document.layers, selected, include_hidden=False)
            if bounds and bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]:
                return self.selectedLayerIndex
        for index in range(len(self._document.layers) - 1, -1, -1):
            layer = self._document.layers[index]
            if not is_layer_group(layer) or not is_effectively_visible(layer, self._document.layers):
                continue
            bounds = group_bounds(self._document.layers, layer, include_hidden=False)
            if bounds and bounds[0] <= x <= bounds[2] and bounds[1] <= y <= bounds[3]:
                return index
        return -1

    @Slot(float, float, result="QVariantList")
    def hitTestLayersAt(self, x: float, y: float):
        hits = []
        for index in range(len(self._document.layers) - 1, -1, -1):
            layer = self._document.layers[index]
            if is_layer_group(layer) or not is_effectively_visible(layer, self._document.layers):
                continue
            if any(
                self._layer_contains_point(layer, x, y, position)
                for position in self._layer_hit_positions(layer)
            ):
                hits.append(index)
        return hits

    def _layer_hit_positions(self, layer):
        positions = [(float(getattr(layer, "x", 0)), float(getattr(layer, "y", 0)))]
        if bool(getattr(layer, "clone_enabled", False)):
            getter = getattr(layer, "get_effective_clone_positions", None)
            if not callable(getter):
                getter = getattr(layer, "get_clone_positions", None)
            if callable(getter):
                try:
                    clone_positions = list(getter() or [])
                    if clone_positions:
                        positions = [(float(px), float(py)) for px, py in clone_positions]
                except Exception:
                    pass
        mirror_mode = str(getattr(layer, "clone_mirror_mode", "none") or "none")
        if mirror_mode not in ("horizontal", "vertical") or not positions:
            return positions
        min_x = min(px for px, _py in positions)
        max_x = max(px + float(layer.width) for px, _py in positions)
        min_y = min(py for _px, py in positions)
        max_y = max(py + float(layer.height) for _px, py in positions)
        mirrored = []
        if mirror_mode == "horizontal":
            mirrored_left = self.canvasWidth - (min_x + max_x - min_x)
            mirrored = [(mirrored_left + px - min_x, py) for px, py in positions]
        else:
            mirrored_top = self.canvasHeight - (min_y + max_y - min_y)
            mirrored = [(px, mirrored_top + py - min_y) for px, py in positions]
        return positions + mirrored

    @Slot(float, float, bool, bool, result=int)
    def selectLayerAtWithModifiers(self, x: float, y: float, ctrl: bool, shift: bool) -> int:
        hits = self.hitTestLayersAt(x, y)
        index = hits[0] if hits else self.hitTestLayerAt(x, y)
        if ctrl and hits:
            current = self.selectedLayerIndex
            index = hits[(hits.index(current) + 1) % len(hits)] if current in hits else hits[0]
            self.selectLayer(index)
        elif index >= 0:
            self.selectLayerWithModifiers(index, False, shift)
        elif not ctrl and not shift:
            self.clearSelection()
        return index

    @Slot(int, int, result=bool)
    def moveSelectedLayersBy(self, delta_x: int, delta_y: int) -> bool:
        indices = self._selected_content_indices()
        movable = [
            index for index in indices
            if not is_effectively_locked(self._document.layers[index], self._document.layers)
            and all(hasattr(self._document.layers[index], attr) for attr in ("x", "y", "width", "height"))
        ]
        if not movable:
            return False
        dx = int(delta_x)
        dy = int(delta_y)
        if dx == 0 and dy == 0:
            return True
        with self._document_lock:
            self._ensure_history_baseline()
            for index in movable:
                layer = self._document.layers[index]
                layer.x = int(layer.x) + dx
                layer.y = int(layer.y) + dy
            self._finish_arrangement("移动多个图层", f"已移动 {len(movable)} 个图层")
        return True

    @Slot(result=bool)
    def groupSelectedLayers(self) -> bool:
        if not self.canGroupSelectedLayers:
            self._set_status("请选择至少两个未分组且未锁定的图层", toast=True)
            return False
        movable = sorted(
            index for index in self.selectedLayerIndices
            if not is_layer_group(self._document.layers[index])
            and not get_parent_group_id(self._document.layers[index])
            and not is_effectively_locked(self._document.layers[index], self._document.layers)
        )
        with self._document_lock:
            self._ensure_history_baseline()
            group_count = sum(is_layer_group(layer) for layer in self._document.layers)
            group = LayerGroup(name=f"图层组 {group_count + 1}", parent=self._document)
            selected_layers = [self._document.layers[index] for index in movable]
            selected_set = set(movable)
            insert_at = min(movable)
            remaining = [
                layer for index, layer in enumerate(self._document.layers)
                if index not in selected_set
            ]
            for layer in selected_layers:
                set_parent_group_id(layer, group.group_id)
            self._document.layers = remaining[:insert_at] + [group] + selected_layers + remaining[insert_at:]
            group_index = self._document.layers.index(group)
            self._document.select_layers([group_index], primary_index=group_index)
            self._selection_anchor_index = group_index
            self._finish_arrangement("建立图层组", f"已建立包含 {len(selected_layers)} 个图层的组")
        return True

    @Slot(result=bool)
    def ungroupSelectedGroups(self) -> bool:
        group_indices = [
            index for index in self.selectedLayerIndices
            if isinstance(self._document.layers[index], LayerGroup)
        ]
        if not group_indices:
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            group_ids = {
                str(self._document.layers[index].group_id)
                for index in group_indices
            }
            self._document.layers = [
                layer for index, layer in enumerate(self._document.layers)
                if index not in set(group_indices)
            ]
            child_indices = []
            for index, layer in enumerate(self._document.layers):
                if get_parent_group_id(layer) in group_ids:
                    set_parent_group_id(layer, None)
                    child_indices.append(index)
            primary = child_indices[0] if child_indices else -1
            self._document.select_layers(child_indices, primary_index=primary)
            self._selection_anchor_index = primary
            self._finish_arrangement("解散图层组", f"已解散 {len(group_indices)} 个图层组")
        return True

    @Slot(int, result=bool)
    def toggleLayerGroupExpanded(self, index: int) -> bool:
        group = self._layer_model.layer_at(index)
        if not isinstance(group, LayerGroup):
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            group.expanded = not group.expanded
            self._document.is_modified = True
            self._document.save_state("切换图层组展开")
        self._layer_model.reset_from_document()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        return True

    @Slot(bool, result=bool)
    def setSelectedLayersVisible(self, visible: bool) -> bool:
        indices = self.selectedLayerIndices
        changes = {
            index: self._document.layers[index]
            for index in indices
            if bool(getattr(self._document.layers[index], "visible", True)) != bool(visible)
        }
        if not changes:
            return True
        with self._document_lock:
            self._ensure_history_baseline()
            for layer in changes.values():
                layer.visible = bool(visible)
            action = "批量显示图层" if visible else "批量隐藏图层"
            self._finish_arrangement(action, f"已{action[2:4]} {len(changes)} 个图层")
        return True

    @Slot(bool, result=bool)
    def setSelectedLayersLocked(self, locked: bool) -> bool:
        indices = self.selectedLayerIndices
        changes = [
            self._document.layers[index]
            for index in indices
            if bool(getattr(self._document.layers[index], "locked", False)) != bool(locked)
        ]
        if not changes:
            return True
        with self._document_lock:
            self._ensure_history_baseline()
            for layer in changes:
                layer.locked = bool(locked)
            action = "批量锁定图层" if locked else "批量解锁图层"
            self._finish_arrangement(action, f"已{action[2:4]} {len(changes)} 个图层", render=False)
        return True

    @Slot(result=bool)
    def duplicateSelectedLayers(self) -> bool:
        indices = self._selected_content_indices()
        originals = [
            self._document.layers[index]
            for index in indices
            if callable(getattr(self._document.layers[index], "duplicate", None))
            and not is_effectively_locked(self._document.layers[index], self._document.layers)
        ]
        if not originals:
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            insert_at = max(indices) + 1
            duplicates = []
            for original in originals:
                try:
                    duplicate = original.duplicate(parent=self._document)
                except TypeError:
                    duplicate = original.duplicate()
                if hasattr(duplicate, "_layer_id"):
                    duplicate._layer_id = str(uuid.uuid4())
                duplicate.name = self._duplicate_layer_name(getattr(original, "name", ""))
                if hasattr(duplicate, "x"):
                    duplicate.x = min(max(0, self.canvasWidth - int(duplicate.width)), int(original.x) + 12)
                    duplicate.y = min(max(0, self.canvasHeight - int(duplicate.height)), int(original.y) + 12)
                set_parent_group_id(duplicate, get_parent_group_id(original))
                duplicates.append(duplicate)
            self._document.layers[insert_at:insert_at] = duplicates
            duplicate_indices = list(range(insert_at, insert_at + len(duplicates)))
            self._document.select_layers(duplicate_indices, primary_index=duplicate_indices[0])
            self._selection_anchor_index = duplicate_indices[0]
            self._finish_arrangement("复制多个图层", f"已复制 {len(duplicates)} 个图层")
        return True

    @Slot(result=bool)
    def deleteSelectedLayers(self) -> bool:
        indices = expand_group_indices(
            self._document.layers,
            self.selectedLayerIndices,
            include_groups=True,
        )
        deletable = sorted({
            index for index in indices
            if not is_effectively_locked(self._document.layers[index], self._document.layers)
        })
        if not deletable:
            return False
        with self._document_lock:
            self._ensure_history_baseline()
            for index in reversed(deletable):
                layer = self._document.layers[index]
                if hasattr(self._document, "binding_manager") and self._document.binding_manager:
                    self._document.binding_manager.remove_layer_from_group(layer)
                del self._document.layers[index]
            fallback = min(deletable[0], len(self._document.layers) - 1) if self._document.layers else -1
            self._document.select_layers([fallback] if fallback >= 0 else [], primary_index=fallback)
            self._selection_anchor_index = fallback
            self._finish_arrangement("删除多个图层", f"已删除 {len(deletable)} 个图层")
        return True

    @Slot(int, result=bool)
    def moveSelectedLayersTo(self, target_index: int) -> bool:
        indices = sorted(expand_group_indices(
            self._document.layers,
            self.selectedLayerIndices,
            include_groups=True,
        ))
        if not indices:
            return False
        target_index = max(0, min(int(target_index), len(self._document.layers) - 1))
        if target_index in indices:
            return True
        with self._document_lock:
            self._ensure_history_baseline()
            selected_objects = [self._document.layers[index] for index in indices]
            remaining = [
                layer for index, layer in enumerate(self._document.layers)
                if index not in set(indices)
            ]
            insert_at = target_index - sum(index < target_index for index in indices)
            if min(indices) < target_index:
                insert_at += 1
            insert_at = max(0, min(insert_at, len(remaining)))
            self._document.layers = remaining[:insert_at] + selected_objects + remaining[insert_at:]
            new_indices = [self._document.layers.index(layer) for layer in selected_objects]
            self._document.select_layers(new_indices, primary_index=new_indices[0])
            self._selection_anchor_index = new_indices[0]
            self._finish_arrangement("重新排序图层", f"已移动 {len(selected_objects)} 个图层", render=False)
        return True

    def _layer_alignment_bounds(self, layer):
        """图层（含分身 / 镜像）的整体包围盒，返回 (min_x, min_y, width, height)。

        为什么不能直接用 layer.x/width：分身和镜像会把可见范围撑到图层矩形之外，
        只按主矩形对齐会出现"看着对齐了、实际分身出界"的情况。
        旧版 app/ui/layer_panel_align.py 为此写了三层分支（分身 / 镜像 / 元素填充），
        这里复用命中测试已经在用的 `_layer_hit_positions`（同样含分身+镜像），
        保证"用户点得到的位置"和"对齐算的位置"是同一套。
        """
        positions = self._layer_hit_positions(layer) or [
            (float(getattr(layer, "x", 0)), float(getattr(layer, "y", 0)))
        ]
        width = float(getattr(layer, "width", 0) or 0)
        height = float(getattr(layer, "height", 0) or 0)
        min_x = min(px for px, _py in positions)
        min_y = min(py for _px, py in positions)
        max_x = max(px + width for px, _py in positions)
        max_y = max(py + height for _px, py in positions)
        return min_x, min_y, max_x - min_x, max_y - min_y

    @Slot(str, result=bool)
    def alignSelectedLayers(self, mode: str) -> bool:
        """多选对齐：以首选图层为基准。

        ⚠ 单选不走这里 —— 单选是「对齐到画板」，由 `alignSelected()` 负责。
        QML 侧统一入口是 `window.alignCurrentSelection(mode)`，它按选中数量分发。
        两处不要各写一份，否则工具栏和右键菜单会出现同一操作两种结果。
        """
        indices = self._selected_content_indices()
        if len(indices) < 2:
            return False
        primary = self.selectedLayerIndex if self.selectedLayerIndex in indices else indices[0]
        reference = self._document.layers[primary]
        mode = str(mode or "").lower()
        changed = []
        with self._document_lock:
            self._ensure_history_baseline()
            for index in indices:
                if index == primary:
                    continue
                layer = self._document.layers[index]
                if is_effectively_locked(layer, self._document.layers):
                    continue
                before = (layer.x, layer.y, layer.width, layer.height)
                if mode == "left":
                    layer.x = reference.x
                elif mode == "hcenter":
                    layer.x = round(reference.x + reference.width / 2 - layer.width / 2)
                elif mode == "right":
                    layer.x = reference.x + reference.width - layer.width
                elif mode == "top":
                    layer.y = reference.y
                elif mode == "vcenter":
                    layer.y = round(reference.y + reference.height / 2 - layer.height / 2)
                elif mode == "bottom":
                    layer.y = reference.y + reference.height - layer.height
                elif mode == "center":
                    layer.x = round(reference.x + reference.width / 2 - layer.width / 2)
                    layer.y = round(reference.y + reference.height / 2 - layer.height / 2)
                elif mode == "same_size":
                    layer.width = reference.width
                    layer.height = reference.height
                else:
                    return False
                if before != (layer.x, layer.y, layer.width, layer.height):
                    changed.append(layer)
            if not changed:
                return True
            self._finish_arrangement("对齐多个图层", f"已对齐 {len(changed)} 个图层")
        return True

    @Slot(str, result=bool)
    def distributeSelectedLayers(self, axis: str) -> bool:
        indices = self._selected_content_indices()
        if len(indices) < 3:
            self._set_status("等距分布至少需要三个图层", toast=True)
            return False
        horizontal = str(axis or "").lower() == "horizontal"
        if not horizontal and str(axis or "").lower() != "vertical":
            return False
        position_attr = "x" if horizontal else "y"
        size_attr = "width" if horizontal else "height"
        indices = sorted(indices, key=lambda index: getattr(self._document.layers[index], position_attr))
        layers = [self._document.layers[index] for index in indices]
        start = float(getattr(layers[0], position_attr))
        end = float(getattr(layers[-1], position_attr) + getattr(layers[-1], size_attr))
        total_size = sum(float(getattr(layer, size_attr)) for layer in layers)
        gap = (end - start - total_size) / (len(layers) - 1)
        cursor = start
        changed = []
        with self._document_lock:
            self._ensure_history_baseline()
            for offset, layer in enumerate(layers):
                target = round(cursor)
                if offset not in (0, len(layers) - 1) and not is_effectively_locked(layer, self._document.layers):
                    if int(getattr(layer, position_attr)) != target:
                        setattr(layer, position_attr, target)
                        changed.append(layer)
                cursor += float(getattr(layer, size_attr)) + gap
            if not changed:
                return True
            direction = "水平" if horizontal else "垂直"
            self._finish_arrangement(f"{direction}等距分布图层", f"已{direction}等距分布")
        return True

    @Slot(int, result=bool)
    def selectLayer(self, index: int) -> bool:
        if self._layer_model.layer_at(index) is None:
            return False
        if self._crop_edit_original is not None and index != self._crop_edit_index:
            self.cancelCropEdit()
        self._dismiss_text_edit_overlay(index)
        self._document.select_layers([int(index)], primary_index=int(index))
        self._selection_anchor_index = int(index)
        self._selected_vector_node_index = -1
        self.selectionChanged.emit()
        self.vectorEditChanged.emit()
        return True

    @Slot(result=bool)
    def clearSelection(self) -> bool:
        if self.selectedLayerIndex < 0:
            return True
        if self._crop_edit_original is not None:
            self.cancelCropEdit()
        self._dismiss_text_edit_overlay(-1)
        self._document.select_layers([], primary_index=-1)
        self._selection_anchor_index = -1
        self._selected_vector_node_index = -1
        self.selectionChanged.emit()
        self.vectorEditChanged.emit()
        return True

    @staticmethod
    def _layer_local_point(layer, x: float, y: float, position=None):
        width = float(getattr(layer, "width", 0) or 0)
        height = float(getattr(layer, "height", 0) or 0)
        if width <= 0 or height <= 0:
            return None
        left, top = position or (
            float(getattr(layer, "x", 0) or 0),
            float(getattr(layer, "y", 0) or 0),
        )
        center_x = left + width / 2.0
        center_y = top + height / 2.0
        offset_x = float(x) - center_x
        offset_y = float(y) - center_y
        angle = math.radians(float(getattr(layer, "rotation", 0.0) or 0.0))
        cosine = math.cos(angle)
        sine = math.sin(angle)
        local_x = cosine * offset_x + sine * offset_y + width / 2.0
        local_y = -sine * offset_x + cosine * offset_y + height / 2.0
        return local_x, local_y

    @staticmethod
    def _layer_alpha_image(layer):
        image = getattr(layer, "cached_image", None)
        if image is None or not hasattr(image, "getpixel"):
            getter = getattr(layer, "get_image", None)
            if callable(getter):
                try:
                    image = getter()
                except Exception:
                    image = None
        if image is None or not hasattr(image, "getpixel"):
            return None
        try:
            return image if image.mode == "RGBA" else image.convert("RGBA")
        except Exception:
            return None

    @classmethod
    def _layer_contains_point(cls, layer, x: float, y: float, position=None) -> bool:
        local = cls._layer_local_point(layer, x, y, position)
        if local is None:
            return False
        local_x, local_y = local
        width = float(getattr(layer, "width", 0) or 0)
        height = float(getattr(layer, "height", 0) or 0)
        if not (0.0 <= local_x <= width and 0.0 <= local_y <= height):
            return False

        shape = getattr(layer, "shape_type", ShapeType.RECTANGLE)
        shape_value = str(getattr(shape, "value", shape or "rectangle"))
        if shape_value != "rectangle" or bool(getattr(layer, "vector_path_enabled", False)):
            try:
                from app.utils.vector_layer_geometry import build_vector_outline_points_px

                points, _ = build_vector_outline_points_px(
                    max(1, int(width)),
                    max(1, int(height)),
                    int(getattr(layer, "corner_radius", 0)),
                    int(getattr(layer, "vector_corner_radius_tl", 0)),
                    int(getattr(layer, "vector_corner_radius_tr", 0)),
                    int(getattr(layer, "vector_corner_radius_br", 0)),
                    int(getattr(layer, "vector_corner_radius_bl", 0)),
                    bool(getattr(layer, "vector_path_enabled", False)),
                    str(getattr(layer, "vector_path_mode", "polygon")),
                    getattr(layer, "vector_path_points", []),
                    getattr(layer, "vector_bezier_nodes", []),
                    bool(getattr(layer, "vector_path_closed", True)),
                    shape_value,
                    int(getattr(layer, "trapezoid_top_width", 100)),
                    int(getattr(layer, "trapezoid_bottom_width", 80)),
                    str(getattr(layer, "trapezoid_slope_side", "right")),
                    float(getattr(layer, "polygon_rotation", 0.0)),
                    int(getattr(layer, "polygon_corner_radius", 0)),
                )
                if len(points) >= 3:
                    path = QPainterPath(QPointF(*points[0]))
                    for point in points[1:]:
                        path.lineTo(QPointF(*point))
                    path.closeSubpath()
                    if not path.contains(QPointF(local_x, local_y)):
                        return False
            except Exception:
                pass

        from app.models.text_layer import TextLayer

        if isinstance(layer, TextLayer):
            return True
        image = cls._layer_alpha_image(layer)
        if image is None or image.mode != "RGBA":
            return True
        pixel_x = min(image.width - 1, max(0, round(local_x / max(1.0, width) * (image.width - 1))))
        pixel_y = min(image.height - 1, max(0, round(local_y / max(1.0, height) * (image.height - 1))))
        try:
            return int(image.getpixel((pixel_x, pixel_y))[-1]) >= 8
        except Exception:
            return True

    @Slot(float, float, result=int)
    def selectLayerAt(self, x: float, y: float) -> int:
        for index in range(self._layer_model.rowCount() - 1, -1, -1):
            layer = self._layer_model.layer_at(index)
            if layer is None:
                continue
            if not bool(getattr(layer, "visible", True)) or bool(getattr(layer, "locked", False)):
                continue
            if self._layer_contains_point(layer, x, y):
                self.selectLayer(index)
                return index
        self.clearSelection()
        return -1
