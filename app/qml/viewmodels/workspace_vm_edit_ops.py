"""WorkspaceViewModel 文本编辑覆盖层/属性基线/裁剪/矢量/形状方法组 mixin（P1-4 拆分）。

从 ``workspace_view_model.py`` 原样迁出的 55 个方法，语义不变。
依赖主类实例方法（``_set_layer_attrs``、``_change_layer``、``_selected_layer`` 等）
与下列模块级名字。``textEditOverlayVisible``（@Property）留在主类。
"""

from __future__ import annotations

from PySide6.QtCore import Slot

from app.models.layer_properties import ShapeType
from app.models.shaped_layer_new import ShapedLayer
from app.utils.layer_tree import is_effectively_locked
from app.utils.text_rich_format import (
    apply_editor_style,
    inspect_editor_selection,
    parse_editor_html,
)

from .workspace_vm_shared import _CROP_DIRECTIONS, _FIT_MODES, _SHAPE_TYPES


class WorkspaceEditOpsMixin:
    @Slot(float, float, result=bool)
    def beginTextEditAt(self, x: float, y: float) -> bool:
        if self.cropEditing or self._export_running:
            return False
        hits = self.hitTestLayersAt(x, y)
        if not hits:
            return False
        index = int(hits[0])
        layer = self._document.layers[index]
        if self._layer_model.layer_type_name(layer) != "文字":
            return False
        if is_effectively_locked(layer, self._document.layers):
            self._set_status("图层已锁定，无法编辑文字", toast=True)
            return False
        self.selectLayer(index)
        return True

    @Slot(result=bool)
    def startTextEditOverlay(self) -> bool:
        """在画布上进入文字直接编辑状态。"""
        if self.cropEditing or self._export_running or not self.selectedIsTextLayer:
            return False
        layer = self._selected_layer()
        if is_effectively_locked(layer, self._document.layers):
            self._set_status("图层已锁定，无法编辑文字", toast=True)
            return False
        if bool(getattr(layer, "vertical_layout", False)):
            self._set_status("竖排文字请在右侧编辑", toast=True)
            return False
        self._text_edit_layer_index = self.selectedLayerIndex
        self._text_edit_draft_html = self._text_editor_html_for_layer(layer)
        self._text_edit_overlay_visible = True
        self.textEditingChanged.emit()
        self.requestPreview(force=True)
        return True

    def _dismiss_text_edit_overlay(self, primary_index: int = -1):
        """切换图层时提交当前草稿并关闭画布文字编辑覆盖层。"""
        if not self._text_edit_overlay_visible:
            return
        if primary_index >= 0 and primary_index == self._text_edit_layer_index:
            return
        index = self._text_edit_layer_index
        draft_html = self._text_edit_draft_html
        self._text_edit_overlay_visible = False
        self._text_edit_layer_index = -1
        self._text_edit_draft_html = None
        self.textEditingChanged.emit()
        if index >= 0 and draft_html:
            self._commit_text_edit_html(index, draft_html, "文字编辑已保存")
        else:
            self.requestPreview(force=True)

    def _selected_text_editor_style(self):
        layer = self._selected_layer()
        if layer is None or not self.selectedIsTextLayer:
            return None
        return (
            max(1, int(getattr(layer, "font_size", 24) or 24)),
            getattr(layer, "text_color", (0, 0, 0, 255)),
        )

    @Slot(str, result=bool)
    def stageTextEditOverlayDraft(self, html: str) -> bool:
        if not self._text_edit_overlay_visible or self._text_edit_layer_index < 0:
            return False
        self._text_edit_draft_html = str(html or "")
        return True

    @Slot(str, int, int, result="QVariantMap")
    def inspectTextEditorSelection(self, html: str, start: int, end: int):
        style = self._selected_text_editor_style()
        if style is None:
            return {
                "characterCount": 0,
                "fontSize": 0,
                "mixedFontSize": False,
                "color": "#000000",
                "mixedColor": False,
            }
        return inspect_editor_selection(
            html,
            int(start),
            int(end),
            base_font_size=style[0],
            base_text_color=style[1],
        )

    @Slot(str, int, int, int, result=str)
    def applyTextEditorFontSize(self, html: str, start: int, end: int, size: int) -> str:
        size = max(1, min(1000, int(size)))
        return apply_editor_style(html, int(start), int(end), font_size=size)

    @Slot(str, int, int, str, result=str)
    def applyTextEditorColor(self, html: str, start: int, end: int, value: str) -> str:
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("局部文字颜色格式无效", toast=True)
            return str(html or "")
        return apply_editor_style(html, int(start), int(end), color=color)

    @Slot(str, int, int, result=str)
    def clearTextEditorStyle(self, html: str, start: int, end: int) -> str:
        style = self._selected_text_editor_style()
        if style is None:
            return str(html or "")
        return apply_editor_style(
            html,
            int(start),
            int(end),
            font_size=style[0],
            color=style[1],
        )

    def _commit_text_edit_html(self, index: int, html: str, status: str) -> bool:
        layer = self._layer_model.layer_at(int(index))
        if layer is None or self._layer_model.layer_type_name(layer) != "文字":
            return False
        state = parse_editor_html(
            html,
            base_font_size=max(1, int(getattr(layer, "font_size", 24) or 24)),
            base_text_color=getattr(layer, "text_color", (0, 0, 0, 255)),
        )
        lines = layer.parse_text_input_to_lines(state.text)
        current_text = lines[0] if lines else ""
        color_ranges = [] if layer.text_binding_enabled else state.color_ranges
        font_size_ranges = [] if layer.text_binding_enabled else state.font_size_ranges
        unchanged = (
            layer.get_text_lines() == lines
            and str(getattr(layer, "current_text", "") or "") == current_text
            and layer.get_text_color_ranges() == color_ranges
            and layer.get_font_size_ranges() == font_size_ranges
        )
        if unchanged:
            self.requestPreview(force=True)
            return True

        def apply(selected) -> None:
            selected.set_text_lines(lines)
            selected.set_current_text(current_text, force=True)
            selected.replace_text_style_ranges(color_ranges, font_size_ranges)

        return self._change_text_layer(
            int(index),
            "编辑文字",
            apply,
            status,
        )

    @Slot(str, result=bool)
    def commitTextEditOverlayRichText(self, html: str) -> bool:
        index = self._text_edit_layer_index
        was_visible = self._text_edit_overlay_visible
        self._text_edit_overlay_visible = False
        self._text_edit_layer_index = -1
        self._text_edit_draft_html = None
        if was_visible:
            self.textEditingChanged.emit()
        if index < 0 or index != self.selectedLayerIndex:
            self.requestPreview(force=True)
            return False
        return self._commit_text_edit_html(index, str(html or ""), "文字编辑已完成")

    @Slot(str, result=bool)
    def commitTextEditOverlay(self, value: str) -> bool:
        """提交画布纯文字编辑内容并退出编辑状态。"""
        index = self._text_edit_layer_index
        was_visible = self._text_edit_overlay_visible
        self._text_edit_overlay_visible = False
        self._text_edit_layer_index = -1
        self._text_edit_draft_html = None
        if was_visible:
            self.textEditingChanged.emit()
        if index < 0 or index != self.selectedLayerIndex:
            self.requestPreview(force=True)
            return False
        return self.setTextContentForLayer(index, value)

    @Slot(result=bool)
    def cancelTextEditOverlay(self) -> bool:
        """取消画布文字编辑，不保存草稿。"""
        if not self._text_edit_overlay_visible:
            return False
        self._text_edit_overlay_visible = False
        self._text_edit_layer_index = -1
        self._text_edit_draft_html = None
        self.textEditingChanged.emit()
        self.requestPreview(force=True)
        return True

    def _ensure_history_baseline(self) -> None:
        manager = self._document._history_manager
        if manager.get_history_count() == 0:
            self._document.save_state("初始状态")

    def _set_layer_attrs(
        self,
        index: int,
        changes: dict,
        action: str,
        *,
        render: bool = True,
        save_history: bool = True,
    ) -> bool:
        if not self._ensure_operations_available():
            return False
        self._suppress_document_selection_notify += 1
        try:
            with self._document_lock:
                layer = self._layer_model.layer_at(index)
                if layer is None:
                    return False
                if any(attr not in ("visible", "locked") for attr in changes) and bool(
                    getattr(layer, "locked", False)
                ):
                    self._set_status("图层已锁定", toast=True)
                    return False
                effective_changes = {
                    attr: value
                    for attr, value in changes.items()
                    if getattr(layer, attr, None) != value
                }
                if not effective_changes:
                    return True
                if save_history:
                    self._ensure_history_baseline()
                for attr, value in effective_changes.items():
                    setattr(layer, attr, value)
                if any(
                    attr in ("fit_mode", "crop_direction", "use_original_size")
                    for attr in effective_changes
                ):
                    self._clear_image_layer_cache(layer)
                    if hasattr(layer, "_cache_valid"):
                        layer._cache_valid = False
                self._document.is_modified = True
                if any(
                    attr in ("x", "y", "width", "height", "rotation", "visible", "locked", "shape_type")
                    or attr.startswith("clone_")
                    or attr.startswith("vector_")
                    for attr in effective_changes
                ):
                    self._document.bump_hit_test_version()
                if any(attr not in ("name", "locked") for attr in effective_changes):
                    invalidate = getattr(self._document, "_invalidate_render_cache", None)
                    if callable(invalidate):
                        invalidate()
                if save_history:
                    self._document.save_state(action)
        finally:
            self._suppress_document_selection_notify -= 1
        self._layer_model.notify_row(index)
        if set(effective_changes) == {"opacity"}:
            self.layerAppearanceChanged.emit()
        else:
            self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        if save_history:
            self.historyStateChanged.emit()
        if render:
            self.requestPreview(force=True)
        return True

    def _set_layer_attr(
        self,
        index: int,
        attr: str,
        value,
        action: str,
        *,
        render: bool = True,
        save_history: bool = True,
    ) -> bool:
        return self._set_layer_attrs(
            index,
            {attr: value},
            action,
            render=render,
            save_history=save_history,
        )

    def _invalidate_direct_layer_edit(self, index: int, *, save_action: str = "") -> None:
        layer = self._layer_model.layer_at(index)
        if layer is not None:
            layer.cached_image = None
            layer._cache_valid = False
        self._document.is_modified = True
        self._document.bump_hit_test_version()
        invalidate = getattr(self._document, "_invalidate_render_cache", None)
        if callable(invalidate):
            invalidate()
        if save_action:
            self._document.save_state(save_action)
        self._layer_model.notify_row(index)
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.historyStateChanged.emit()
        self.requestPreview(force=True)

    def _run_vector_command(self, action: str, command) -> bool:
        if not self._ensure_operations_available() or not self.selectedSupportsVectorPath:
            self._set_status("当前图层不支持路径编辑", toast=True)
            return False
        layer = self._selected_layer()
        if layer is None or bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        index = self.selectedLayerIndex
        with self._document_lock:
            before = layer.serialize()
            self._ensure_history_baseline()
            command(layer)
            if layer.serialize() == before:
                return False
            self._invalidate_direct_layer_edit(index, save_action=action)
        self.vectorEditChanged.emit()
        return True

    def _refresh_random_transform_preview(self) -> bool:
        layer = self._selected_layer()
        if not self.selectedSupportsRandomTransform or layer is None:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        with self._document_lock:
            layer.generate_random_transform_params()
            layer.cached_image = None
            layer._cache_valid = False
            invalidate = getattr(self._document, "_invalidate_render_cache", None)
            if callable(invalidate):
                invalidate()
        self._layer_model.notify_row(self.selectedLayerIndex)
        self.selectionChanged.emit()
        self.requestPreview(force=True)
        return True

    @Slot(str, result=bool)
    def setSelectedFitMode(self, mode_id: str) -> bool:
        if not self.selectedSupportsImageFit:
            self._set_status("当前图层不支持图片适配", toast=True)
            return False
        mode_id = str(mode_id or "").strip().lower()
        mode = _FIT_MODES.get(mode_id)
        if mode is None:
            self._set_status("未知的图片适配模式", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "fit_mode",
            mode[0],
            "修改图片适配模式",
        )

    @Slot(bool, result=bool)
    def setSelectedUseOriginalSize(self, enabled: bool) -> bool:
        return self.setSelectedTrimTransparentBoundsEnabled(enabled)

    @Slot(bool, result=bool)
    def setSelectedTrimTransparentBoundsEnabled(self, enabled: bool) -> bool:
        layer = self._selected_layer()
        if not self.selectedHasImageSource or layer is None or not hasattr(layer, "use_original_size"):
            self._set_status("当前图层不支持去透明留白", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "use_original_size",
            bool(enabled),
            "切换去透明留白",
        )

    @Slot(str, result=bool)
    def setSelectedCropDirection(self, direction_id: str) -> bool:
        if not self.selectedSupportsImageFit:
            self._set_status("当前图层不支持裁剪方向", toast=True)
            return False
        direction_id = str(direction_id or "").strip().lower()
        direction = _CROP_DIRECTIONS.get(direction_id)
        if direction is None:
            self._set_status("未知的裁剪方向", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "crop_direction",
            direction[0],
            "修改裁剪方向",
        )

    @Slot(result=bool)
    def startCropEdit(self) -> bool:
        if not self._ensure_operations_available() or not self.selectedSupportsFreeCrop:
            self._set_status("当前图层不支持自由裁剪", toast=True)
            return False
        layer = self._selected_layer()
        if bool(getattr(layer, "locked", False)):
            self._set_status("图层已锁定", toast=True)
            return False
        if self.cropEditing:
            return True
        if self._crop_edit_original is not None:
            self.cancelCropEdit()
        with self._document_lock:
            self._ensure_history_baseline()
            self._crop_edit_index = self.selectedLayerIndex
            self._crop_edit_original = list(layer.crop_rect)
            self._crop_edit_was_modified = bool(self._document.is_modified)
        self.cropEditChanged.emit()
        self._set_status("拖动裁剪框后确认应用", toast=True)
        return True

    @Slot(float, float, float, float, result=bool)
    def updateCropRect(self, left: float, top: float, right: float, bottom: float) -> bool:
        if not self.cropEditing:
            return False
        layer = self._layer_model.layer_at(self._crop_edit_index)
        if layer is None:
            return False
        with self._document_lock:
            layer.crop_rect = [left, top, right, bottom]
            self._invalidate_direct_layer_edit(self._crop_edit_index)
        self.cropEditChanged.emit()
        return True

    @Slot(result=bool)
    def confirmCropEdit(self) -> bool:
        if not self.cropEditing:
            return False
        index = self._crop_edit_index
        layer = self._layer_model.layer_at(index)
        original = list(self._crop_edit_original)
        changed = layer is not None and list(layer.crop_rect) != original
        with self._document_lock:
            if changed:
                self._invalidate_direct_layer_edit(index, save_action="自由裁剪图片")
            else:
                self._document.is_modified = self._crop_edit_was_modified
        self._crop_edit_index = -1
        self._crop_edit_original = None
        self.cropEditChanged.emit()
        if changed:
            self._set_status("已应用自由裁剪", toast=True)
        return True

    @Slot(result=bool)
    def cancelCropEdit(self) -> bool:
        if self._crop_edit_original is None:
            return False
        index = self._crop_edit_index
        layer = self._layer_model.layer_at(index)
        with self._document_lock:
            if layer is not None:
                layer.crop_rect = list(self._crop_edit_original)
                self._invalidate_direct_layer_edit(index)
            self._document.is_modified = self._crop_edit_was_modified
        self._crop_edit_index = -1
        self._crop_edit_original = None
        self.cropEditChanged.emit()
        self.documentInfoChanged.emit()
        self._set_status("已取消自由裁剪", toast=True)
        return True

    @Slot(result=bool)
    def resetSelectedCrop(self) -> bool:
        if self.cropEditing:
            self.cancelCropEdit()
        if not self.selectedSupportsFreeCrop:
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "crop_rect",
            [0.0, 0.0, 1.0, 1.0],
            "重置自由裁剪",
        )

    @Slot(result=bool)
    def convertSelectedToVectorPath(self) -> bool:
        changed = self._run_vector_command(
            "转换为矢量路径",
            lambda layer: layer.convert_rect_to_vector_path(),
        )
        if changed:
            self._selected_vector_node_index = 0
            self.vectorEditChanged.emit()
        return changed

    @Slot(int, result=bool)
    def selectVectorNode(self, node_index: int) -> bool:
        if node_index < 0 or node_index >= len(self.selectedVectorNodes):
            return False
        self._selected_vector_node_index = int(node_index)
        self.vectorEditChanged.emit()
        return True

    @Slot(int, float, float, result=bool)
    def moveSelectedVectorNode(self, node_index: int, x: float, y: float) -> bool:
        if node_index < 0 or node_index >= len(self.selectedVectorNodes):
            return False
        self._selected_vector_node_index = int(node_index)
        return self._run_vector_command(
            "移动路径节点",
            lambda layer: layer.update_vector_bezier_anchor(node_index, float(x), float(y)),
        )

    @Slot(int, str, float, float, result=bool)
    def moveSelectedVectorHandle(self, node_index: int, handle_type: str, x: float, y: float) -> bool:
        handle_type = str(handle_type or "").lower()
        if handle_type not in {"in", "out"}:
            return False
        return self._run_vector_command(
            "移动路径控制柄",
            lambda layer: layer.update_vector_bezier_handle(
                node_index, handle_type, float(x), float(y)
            ),
        )

    @Slot(str, result=bool)
    def setSelectedVectorNodeType(self, node_type: str) -> bool:
        if self._selected_vector_node_index < 0:
            return False
        node_type = str(node_type or "").lower()
        if node_type not in {"corner", "smooth", "symmetric"}:
            return False
        return self._run_vector_command(
            "修改路径节点类型",
            lambda layer: layer.set_vector_node_type(self._selected_vector_node_index, node_type),
        )

    @Slot(result=bool)
    def cycleSelectedVectorNodeType(self) -> bool:
        if self._selected_vector_node_index < 0:
            return False
        return self._run_vector_command(
            "切换路径节点类型",
            lambda layer: layer.cycle_vector_node_type(self._selected_vector_node_index),
        )

    @Slot(int, result=bool)
    def insertVectorNodeAfter(self, segment_index: int) -> bool:
        changed = self._run_vector_command(
            "插入路径节点",
            lambda layer: layer.insert_vector_node_after(int(segment_index)),
        )
        if changed:
            self._selected_vector_node_index = int(segment_index) + 1
            self.vectorEditChanged.emit()
        return changed

    @Slot(result=bool)
    def deleteSelectedVectorNode(self) -> bool:
        index = self._selected_vector_node_index
        if index < 0:
            return False
        changed = self._run_vector_command(
            "删除路径节点",
            lambda layer: layer.delete_vector_node(index),
        )
        if changed:
            self._selected_vector_node_index = min(index, len(self.selectedVectorNodes) - 1)
            self.vectorEditChanged.emit()
        return changed

    @Slot(bool, result=bool)
    def setSelectedVectorPathClosed(self, closed: bool) -> bool:
        return self._run_vector_command(
            "切换路径闭合",
            lambda layer: setattr(layer, "vector_path_closed", bool(closed)),
        )

    @Slot(str, result=bool)
    def setSelectedVectorHandleLinkMode(self, mode: str) -> bool:
        mode = str(mode or "").lower()
        if mode not in {"mirror", "collinear", "free"}:
            return False
        return self._run_vector_command(
            "修改控制柄联动",
            lambda layer: setattr(layer, "vector_handle_link_mode", mode),
        )

    @Slot(int, result=bool)
    def setSelectedVectorCornerRadiusAll(self, value: int) -> bool:
        value = max(0, min(1000, int(value)))
        return self.setSelectedVectorCornerRadii(value, value, value, value)

    def _set_corner_attrs(self, mode: str, changes: dict, action: str) -> bool:
        """原子更新圆角属性和仅供界面使用的编辑模式。"""
        layer = self._selected_layer()
        mode_key = id(layer)
        previous_mode = self.selectedCornerMode
        had_override = mode_key in self._corner_edit_modes
        previous_override = self._corner_edit_modes.get(mode_key)
        has_layer_changes = any(
            getattr(layer, attr, None) != value for attr, value in changes.items()
        )

        # 属性变更会同步发出 selectionChanged，因此先设置模式，确保绑定读取新值。
        self._corner_edit_modes[mode_key] = mode
        changed = self._set_layer_attrs(self.selectedLayerIndex, changes, action)
        if not changed:
            if had_override:
                self._corner_edit_modes[mode_key] = previous_override
            else:
                self._corner_edit_modes.pop(mode_key, None)
            return False

        # no-op 属性更新不会发通知，但模式本身仍可能已经改变。
        if previous_mode != mode and not has_layer_changes:
            self.selectionChanged.emit()
        return True

    @Slot(str, result=bool)
    def setSelectedCornerMode(self, mode: str) -> bool:
        if not self.selectedSupportsCornerRadius:
            self._set_status("当前图层不支持矩形圆角", toast=True)
            return False
        mode = str(mode or "").strip().lower()
        if mode not in {"uniform", "independent"}:
            self._set_status("未知的圆角编辑模式", toast=True)
            return False
        layer = self._selected_layer()
        if mode == "uniform":
            value = max(
                max(0, int(getattr(layer, "corner_radius", 0))),
                *self.selectedVectorCornerRadii,
            )
            return self.setSelectedCornerRadius(value)
        if self.selectedCornerMode == "independent":
            return True
        self._corner_edit_modes[id(layer)] = "independent"
        self.selectionChanged.emit()
        return True

    @Slot(int, int, int, int, result=bool)
    def setSelectedVectorCornerRadii(self, top_left: int, top_right: int, bottom_right: int, bottom_left: int) -> bool:
        if not self.selectedSupportsVectorCorners:
            self._set_status("当前图层不支持四角圆角", toast=True)
            return False
        values = [
            max(0, min(1000, int(top_left))),
            max(0, min(1000, int(top_right))),
            max(0, min(1000, int(bottom_right))),
            max(0, min(1000, int(bottom_left))),
        ]
        changes = {
            "vector_corner_radius_tl": values[0],
            "vector_corner_radius_tr": values[1],
            "vector_corner_radius_br": values[2],
            "vector_corner_radius_bl": values[3],
            "corner_radius": max(values),
        }
        return self._set_corner_attrs("independent", changes, "修改矢量四角圆角")

    @Slot(bool, result=bool)
    def setSelectedFlipHorizontal(self, enabled: bool) -> bool:
        if not self.selectedSupportsImageFit:
            self._set_status("当前图层不支持水平翻转", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "flip_horizontal",
            bool(enabled),
            "水平翻转图层",
        )

    @Slot(bool, result=bool)
    def setSelectedFlipVertical(self, enabled: bool) -> bool:
        if not self.selectedSupportsImageFit:
            self._set_status("当前图层不支持垂直翻转", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "flip_vertical",
            bool(enabled),
            "垂直翻转图层",
        )

    def _selected_shaped_layer(self):
        layer = self._selected_layer()
        if not isinstance(layer, ShapedLayer):
            self._set_status("当前图层不是异形图层", toast=True)
            return None
        return layer

    @Slot(str, result=bool)
    def setSelectedShapeType(self, shape_id: str) -> bool:
        layer = self._selected_shaped_layer()
        if layer is None:
            return False
        shape_id = str(shape_id or "").strip().lower()
        shape_entry = _SHAPE_TYPES.get(shape_id)
        if shape_entry is None:
            self._set_status("不支持的异形类型", toast=True)
            return False
        changes = {"shape_type": shape_entry[0]}
        if shape_entry[0] == ShapeType.RIGHT_TRAPEZOID:
            width = max(1, int(layer.width))
            changes.update(
                {
                    "trapezoid_top_width": width,
                    "trapezoid_bottom_width": max(1, round(width * 0.8)),
                    "trapezoid_slope_side": "right",
                }
            )
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            changes,
            f"切换异形为{shape_entry[1]}",
        )

    @Slot(int, result=bool)
    def setSelectedTrapezoidTopWidth(self, value: int) -> bool:
        layer = self._selected_shaped_layer()
        if layer is None:
            return False
        value = max(1, min(int(layer.width), int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "trapezoid_top_width",
            value,
            "修改梯形上底",
        )

    @Slot(int, result=bool)
    def setSelectedTrapezoidBottomWidth(self, value: int) -> bool:
        layer = self._selected_shaped_layer()
        if layer is None:
            return False
        value = max(1, min(int(layer.width), int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "trapezoid_bottom_width",
            value,
            "修改梯形下底",
        )

    @Slot(str, result=bool)
    def setSelectedTrapezoidSlopeSide(self, value: str) -> bool:
        if self._selected_shaped_layer() is None:
            return False
        value = str(value or "").strip().lower()
        if value not in {"left", "right"}:
            self._set_status("梯形斜边方向无效", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "trapezoid_slope_side",
            value,
            "修改梯形斜边方向",
        )

    @Slot(float, result=bool)
    def setSelectedPolygonRotation(self, value: float) -> bool:
        if self._selected_shaped_layer() is None:
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "polygon_rotation",
            float(value) % 360.0,
            "旋转多边形内容",
        )

    @Slot(int, result=bool)
    def setSelectedPolygonCornerRadius(self, value: int) -> bool:
        if self._selected_shaped_layer() is None or not self.selectedSupportsShapeCornerRadius:
            self._set_status("当前形状不支持顶点圆角", toast=True)
            return False
        value = max(0, min(self.selectedPolygonCornerRadiusMax, int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "polygon_corner_radius",
            value,
            "修改多边形圆角",
        )

    @Slot(str, result=bool)
    def setSelectedName(self, value: str) -> bool:
        value = str(value or "").strip()
        if not value:
            self._set_status("图层名称不能为空", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "name",
            value[:120],
            "重命名图层",
            render=False,
        )

    @Slot(float, result=bool)
    def setSelectedRotation(self, value: float) -> bool:
        if not self.selectedCanRotate:
            self._set_status("当前图层不支持旋转", toast=True)
            return False
        value = float(value) % 360.0
        return self._set_layer_attr(self.selectedLayerIndex, "rotation", value, "旋转图层")

    @Slot(int, result=bool)
    def toggleLayerVisible(self, index: int) -> bool:
        layer = self._layer_model.layer_at(index)
        return bool(layer) and self._set_layer_attr(index, "visible", not bool(layer.visible), "切换图层可见性")

    @Slot(int, result=bool)
    def toggleLayerLocked(self, index: int) -> bool:
        layer = self._layer_model.layer_at(index)
        return bool(layer) and self._set_layer_attr(
            index,
            "locked",
            not bool(layer.locked),
            "切换图层锁定",
            render=False,
        )
