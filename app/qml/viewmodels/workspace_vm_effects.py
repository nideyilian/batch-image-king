"""WorkspaceViewModel 变换/随机/克隆/效果 setter 方法组 mixin（P1-4 拆分）。

从 ``workspace_view_model.py`` 原样迁出的效果类属性设置方法组（54 个方法），
语义不变。依赖主类提供的实例方法/属性（``_set_layer_attrs``、
``_selected_layer``、``_change_layer`` 等）与下列模块级名字。
"""

from __future__ import annotations

from PySide6.QtCore import Slot

from app.utils.layer_tree import is_effectively_locked

from .workspace_vm_shared import _BLEND_MODES


class WorkspaceEffectsMixin:
    @Slot(int, int, int, int, result=bool)
    def applySelectedGeometry(self, x: int, y: int, width: int, height: int) -> bool:
        if width <= 0 or height <= 0:
            self._set_status("图层尺寸必须大于零", toast=True)
            return False
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            {
                "x": int(x),
                "y": int(y),
                "width": int(width),
                "height": int(height),
            },
            "画布变换图层",
        )

    @Slot(int, int, int, int, result=bool)
    def transformSelectedLayers(self, x: int, y: int, width: int, height: int) -> bool:
        indices = self._selected_content_indices()
        if not indices or width < 1 or height < 1:
            return False
        old_x, old_y, old_width, old_height = self._selection_bounds()
        if old_width <= 0 or old_height <= 0:
            return False
        scale_x = float(width) / old_width
        scale_y = float(height) / old_height
        with self._document_lock:
            self._ensure_history_baseline()
            changed = 0
            for index in indices:
                layer = self._document.layers[index]
                if is_effectively_locked(layer, self._document.layers):
                    continue
                layer.x = round(int(x) + (float(layer.x) - old_x) * scale_x)
                layer.y = round(int(y) + (float(layer.y) - old_y) * scale_y)
                layer.width = max(1, round(float(layer.width) * scale_x))
                layer.height = max(1, round(float(layer.height) * scale_y))
                changed += 1
            if not changed:
                return False
            self._finish_arrangement("缩放多个图层", f"已缩放 {changed} 个图层")
        return True

    @Slot(str, result=bool)
    def alignSelected(self, mode: str) -> bool:
        layer = self._selected_layer()
        if layer is None:
            return False
        mode = str(mode or "").lower()
        width = int(getattr(layer, "width", 0))
        height = int(getattr(layer, "height", 0))
        if mode == "same_size" and bool(getattr(layer, "use_original_size", False)):
            self._set_status("原始尺寸模式下无法匹配画板大小", toast=True)
            return False
        alignments = {
            "left": {"x": 0},
            "hcenter": {"x": (self.canvasWidth - width) // 2},
            "right": {"x": self.canvasWidth - width},
            "top": {"y": 0},
            "vcenter": {"y": (self.canvasHeight - height) // 2},
            "bottom": {"y": self.canvasHeight - height},
            "center": {
                "x": (self.canvasWidth - width) // 2,
                "y": (self.canvasHeight - height) // 2,
            },
            "same_size": {
                "x": 0,
                "y": 0,
                "width": self.canvasWidth,
                "height": self.canvasHeight,
            },
        }
        changes = alignments.get(mode)
        if changes is None:
            return False
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "对齐图层")

    @Slot(result=bool)
    def randomizeAllLayers(self) -> bool:
        if not self._ensure_operations_available():
            return False
        if not self._document.layers:
            self._set_status("没有可随机化的图层", toast=True)
            return False
        try:
            with self._document_lock:
                self._document.randomize_all_layers()
        except Exception as error:
            self._set_status(f"随机化图层失败：{error}", toast=True)
            return False
        self._layer_model.reset_from_document()
        self.selectionChanged.emit()
        self.documentInfoChanged.emit()
        self.requestPreview(force=True)
        self._set_status("已随机化所有图层", toast=True)
        return True

    @Slot(int, result=bool)
    def setSelectedX(self, value: int) -> bool:
        return self._set_layer_attr(self.selectedLayerIndex, "x", int(value), "修改 X 坐标")

    @Slot(int, result=bool)
    def setSelectedY(self, value: int) -> bool:
        return self._set_layer_attr(self.selectedLayerIndex, "y", int(value), "修改 Y 坐标")

    @Slot(bool, result=bool)
    def setSelectedAspectRatioLocked(self, enabled: bool) -> bool:
        if not self.selectedSupportsAspectRatioLock:
            self._set_status("当前图层不支持比例锁定", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "aspect_ratio_locked",
            bool(enabled),
            "切换比例锁定",
        )

    @Slot(int, result=bool)
    def setSelectedWidth(self, value: int) -> bool:
        if value <= 0:
            return False
        layer = self._selected_layer()
        if self.selectedAspectRatioLocked and layer is not None:
            current_width = max(1, int(getattr(layer, "width", 1)))
            current_height = max(1, int(getattr(layer, "height", 1)))
            return self._set_layer_attrs(
                self.selectedLayerIndex,
                {
                    "width": int(value),
                    "height": max(1, round(int(value) * current_height / current_width)),
                },
                "等比修改图层宽度",
            )
        return self._set_layer_attr(self.selectedLayerIndex, "width", int(value), "修改图层宽度")

    @Slot(int, result=bool)
    def setSelectedHeight(self, value: int) -> bool:
        if value <= 0:
            return False
        layer = self._selected_layer()
        if self.selectedAspectRatioLocked and layer is not None:
            current_width = max(1, int(getattr(layer, "width", 1)))
            current_height = max(1, int(getattr(layer, "height", 1)))
            return self._set_layer_attrs(
                self.selectedLayerIndex,
                {
                    "width": max(1, round(int(value) * current_width / current_height)),
                    "height": int(value),
                },
                "等比修改图层高度",
            )
        return self._set_layer_attr(self.selectedLayerIndex, "height", int(value), "修改图层高度")

    @Slot(bool, result=bool)
    def setSelectedRandomPositionEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        changed = self._set_layer_attr(
            self.selectedLayerIndex,
            "random_position_enabled",
            bool(enabled),
            "切换随机位置",
            render=False,
        )
        return changed and self._refresh_random_transform_preview()

    @Slot(int, result=bool)
    def setSelectedRandomPositionRange(self, value: int) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "random_position_range",
            max(0, min(10000, int(value))),
            "修改随机位置范围",
        )

    @Slot(bool, result=bool)
    def setSelectedRandomScaleEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        changed = self._set_layer_attr(
            self.selectedLayerIndex,
            "random_scale_enabled",
            bool(enabled),
            "切换随机缩放",
            render=False,
        )
        return changed and self._refresh_random_transform_preview()

    @Slot(int, result=bool)
    def setSelectedRandomScaleMinPercent(self, value: int) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        value = max(1, min(1000, int(value))) / 100.0
        layer = self._selected_layer()
        changes = {"random_scale_min": value}
        if float(getattr(layer, "random_scale_max", 1.0)) < value:
            changes["random_scale_max"] = value
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            changes,
            "修改随机缩放下限",
        )

    @Slot(int, result=bool)
    def setSelectedRandomScaleMaxPercent(self, value: int) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        value = max(1, min(1000, int(value))) / 100.0
        layer = self._selected_layer()
        changes = {"random_scale_max": value}
        if float(getattr(layer, "random_scale_min", 1.0)) > value:
            changes["random_scale_min"] = value
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            changes,
            "修改随机缩放上限",
        )

    @Slot(bool, result=bool)
    def setSelectedRandomRotationEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        changed = self._set_layer_attr(
            self.selectedLayerIndex,
            "random_rotation_enabled",
            bool(enabled),
            "切换随机旋转",
            render=False,
        )
        return changed and self._refresh_random_transform_preview()

    @Slot(float, result=bool)
    def setSelectedRandomRotationRange(self, value: float) -> bool:
        if not self.selectedSupportsRandomTransform:
            self._set_status("当前图层不支持随机变换", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "random_rotation_range",
            max(0.0, min(180.0, float(value))),
            "修改随机旋转范围",
        )

    @Slot(result=bool)
    def regenerateSelectedRandomTransform(self) -> bool:
        return self._refresh_random_transform_preview()

    def _set_selected_clone_attr(self, attr: str, value, action: str) -> bool:
        if not self.selectedSupportsClone:
            self._set_status("当前图层不支持分身", toast=True)
            return False
        return self._set_layer_attr(self.selectedLayerIndex, attr, value, action)

    @Slot(bool, result=bool)
    def setSelectedCloneEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsClone:
            self._set_status("当前图层不支持分身", toast=True)
            return False
        layer = self._selected_layer()
        changes = {"clone_enabled": bool(enabled)}
        if enabled and int(layer.clone_rows) == 1 and int(layer.clone_columns) == 1:
            changes.update({"clone_rows": 2, "clone_columns": 2})
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "切换图层分身")

    @Slot(int, result=bool)
    def setSelectedCloneRows(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_rows", max(1, min(100, int(value))), "修改分身行数"
        )

    @Slot(int, result=bool)
    def setSelectedCloneColumns(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_columns", max(1, min(100, int(value))), "修改分身列数"
        )

    @Slot(int, result=bool)
    def setSelectedCloneRowSpacing(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_row_spacing", max(0, min(10000, int(value))), "修改分身行距"
        )

    @Slot(int, result=bool)
    def setSelectedCloneColumnSpacing(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_column_spacing", max(0, min(10000, int(value))), "修改分身列距"
        )

    @Slot(str, result=bool)
    def setSelectedCloneMirrorMode(self, value: str) -> bool:
        value = str(value or "none")
        if value not in {"none", "horizontal", "vertical"}:
            self._set_status("未知的分身镜像模式", toast=True)
            return False
        return self._set_selected_clone_attr("clone_mirror_mode", value, "修改分身镜像")

    @Slot(bool, result=bool)
    def setSelectedCloneCustomSizeEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsClone:
            self._set_status("当前图层不支持分身", toast=True)
            return False
        layer = self._selected_layer()
        changes = {"clone_custom_size_enabled": bool(enabled)}
        if enabled:
            changes.update(
                {
                    "clone_custom_width": max(1, int(getattr(layer, "width", 1))),
                    "clone_custom_height": max(1, int(getattr(layer, "height", 1))),
                }
            )
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "切换分身自定义尺寸")

    @Slot(int, result=bool)
    def setSelectedCloneCustomWidth(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_custom_width", max(1, min(10000, int(value))), "修改分身宽度"
        )

    @Slot(int, result=bool)
    def setSelectedCloneCustomHeight(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_custom_height", max(1, min(10000, int(value))), "修改分身高度"
        )

    @Slot(bool, result=bool)
    def setSelectedCloneFillEnabled(self, enabled: bool) -> bool:
        return self.setSelectedCloneLayoutMode("fill" if enabled else "fixed")

    @Slot(str, result=bool)
    def setSelectedCloneLayoutMode(self, mode: str) -> bool:
        mode = str(mode or "").strip().lower()
        if mode not in {"fixed", "fill"}:
            self._set_status("未知的分身布局模式", toast=True)
            return False
        return self._set_selected_clone_attr(
            "clone_fill_enabled",
            mode == "fill",
            "切换分身布局模式",
        )

    @Slot(str, result=bool)
    def setSelectedCloneFillMode(self, value: str) -> bool:
        value = str(value or "grid")
        if value not in {"grid", "staggered", "border"}:
            self._set_status("未知的元素铺排模式", toast=True)
            return False
        return self._set_selected_clone_attr("clone_fill_mode", value, "修改元素铺排模式")

    @Slot(int, result=bool)
    def setSelectedCloneFillSpacing(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_fill_spacing", max(0, min(10000, int(value))), "修改元素间距"
        )

    @Slot(int, result=bool)
    def setSelectedCloneFillMargin(self, value: int) -> bool:
        return self._set_selected_clone_attr(
            "clone_fill_margin", max(0, min(1000, int(value))), "修改铺排边距"
        )

    @Slot(float, result=bool)
    def setSelectedCloneFillAngle(self, value: float) -> bool:
        return self._set_selected_clone_attr(
            "clone_fill_angle", float(value) % 360.0, "修改铺排角度"
        )

    @Slot(int, result=bool)
    def setSelectedOpacity(self, value: int) -> bool:
        value = max(0, min(100, int(value)))
        return self._set_layer_attr(self.selectedLayerIndex, "opacity", value / 100.0, "修改不透明度")

    @Slot(result=bool)
    def beginSelectedOpacityEdit(self) -> bool:
        """开始连续不透明度编辑，拖动期间不反复序列化历史。"""
        if not self._ensure_operations_available():
            return False
        layer = self._selected_layer()
        if layer is None or bool(getattr(layer, "locked", False)):
            return False
        if self._opacity_edit_context is not None:
            self.endSelectedOpacityEdit()
        self._opacity_edit_context = {
            "document": self._document,
            "layer": layer,
            "index": self.selectedLayerIndex,
            "initial": float(getattr(layer, "opacity", 1.0)),
            "initial_modified": bool(getattr(self._document, "is_modified", False)),
            "changed": False,
            "baseline_ready": False,
        }
        return True

    @Slot(int, result=bool)
    def updateSelectedOpacityEdit(self, value: int) -> bool:
        context = self._opacity_edit_context
        if context is None:
            return self.setSelectedOpacity(value)
        if (
            context["document"] is not self._document
            or context["layer"] is not self._selected_layer()
        ):
            self._opacity_edit_context = None
            return False
        value = max(0, min(100, int(value))) / 100.0
        if float(getattr(context["layer"], "opacity", 1.0)) == value:
            return True
        if not context["baseline_ready"]:
            with self._document_lock:
                self._ensure_history_baseline()
            context["baseline_ready"] = True
        changed = self._set_layer_attr(
            context["index"],
            "opacity",
            value,
            "修改不透明度",
            save_history=False,
        )
        context["changed"] = context["changed"] or bool(changed)
        return changed

    @Slot(result=bool)
    def endSelectedOpacityEdit(self) -> bool:
        context = self._opacity_edit_context
        self._opacity_edit_context = None
        if context is None:
            return True
        if context["document"] is not self._document:
            return False
        if not context["changed"]:
            return True
        if float(getattr(context["layer"], "opacity", 1.0)) == context["initial"]:
            self._document.is_modified = context["initial_modified"]
            self.documentInfoChanged.emit()
            return True
        with self._document_lock:
            self._document.save_state("修改不透明度")
        self.historyStateChanged.emit()
        return True

    @Slot(str, result=bool)
    def setSelectedBlendMode(self, mode_id: str) -> bool:
        mode_id = str(mode_id or "").strip().lower()
        if not self.selectedSupportsBlendMode:
            self._set_status("当前图层不支持混合模式", toast=True)
            return False
        if mode_id not in _BLEND_MODES:
            self._set_status("未知的混合模式", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "blend_mode",
            _BLEND_MODES[mode_id][0],
            "修改混合模式",
        )

    @Slot(bool, result=bool)
    def setSelectedStrokeEnabled(self, enabled: bool) -> bool:
        if not self.selectedSupportsStroke:
            self._set_status("当前图层不支持描边", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "stroke_enabled",
            bool(enabled),
            "切换描边",
        )

    @Slot(int, result=bool)
    def setSelectedStrokeWidth(self, value: int) -> bool:
        if not self.selectedSupportsStroke:
            self._set_status("当前图层不支持描边", toast=True)
            return False
        value = max(1, min(128, int(value)))
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_width", value, "修改描边宽度")

    @Slot(str, result=bool)
    def setSelectedStrokeColor(self, value: str) -> bool:
        if not self.selectedSupportsStroke:
            self._set_status("当前图层不支持描边", toast=True)
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("描边颜色格式无效", toast=True)
            return False
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_color", color, "修改描边颜色")

    @Slot(int, result=bool)
    def setSelectedStrokeType(self, value: int) -> bool:
        if not self.selectedSupportsAdvancedStroke:
            self._set_status("当前图层不支持高级描边", toast=True)
            return False
        value = max(0, min(2, int(value)))
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_type", value, "修改描边对齐")

    @Slot(str, result=bool)
    def setSelectedStrokeJoin(self, value: str) -> bool:
        value = str(value or "miter")
        if not self.selectedSupportsAdvancedStroke or value not in {"miter", "round", "bevel"}:
            self._set_status("未知的描边连接类型", toast=True)
            return False
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_join", value, "修改描边连接")

    @Slot(str, result=bool)
    def setSelectedStrokeCap(self, value: str) -> bool:
        value = str(value or "butt")
        if not self.selectedSupportsAdvancedStroke or value not in {"butt", "round", "square"}:
            self._set_status("未知的描边端点类型", toast=True)
            return False
        return self._set_layer_attr(self.selectedLayerIndex, "stroke_cap", value, "修改描边端点")

    @Slot(int, int, result=bool)
    def setSelectedStrokeDash(self, length: int, gap: int) -> bool:
        if not self.selectedSupportsAdvancedStroke:
            self._set_status("当前图层不支持高级描边", toast=True)
            return False
        changes = {
            "stroke_dash_length": max(0, min(1000, int(length))),
            "stroke_dash_gap": max(0, min(1000, int(gap))),
        }
        return self._set_layer_attrs(self.selectedLayerIndex, changes, "修改描边虚线")

    @Slot(int, result=bool)
    def setSelectedCornerRadius(self, value: int) -> bool:
        if not self.selectedSupportsCornerRadius:
            self._set_status("当前图层不支持圆角", toast=True)
            return False
        value = max(0, min(self.selectedCornerRadiusMax, int(value)))
        changes = {
            "corner_radius": value,
            "vector_corner_radius_tl": 0,
            "vector_corner_radius_tr": 0,
            "vector_corner_radius_br": 0,
            "vector_corner_radius_bl": 0,
        }
        return self._set_corner_attrs("uniform", changes, "修改统一圆角")

    @Slot(str, result=bool)
    def setSelectedOverlayMode(self, mode: str) -> bool:
        mode = str(mode or "").strip().lower()
        if mode not in {"none", "color", "gradient"}:
            self._set_status("未知的颜色叠加模式", toast=True)
            return False
        if mode == "color" and not self.selectedSupportsColorOverlay:
            self._set_status("当前图层不支持颜色叠加", toast=True)
            return False
        if mode == "gradient" and not self.selectedSupportsGradientOverlay:
            self._set_status("当前图层不支持渐变叠加", toast=True)
            return False
        if mode == "none" and not (
            self.selectedSupportsColorOverlay or self.selectedSupportsGradientOverlay
        ):
            self._set_status("当前图层不支持颜色叠加", toast=True)
            return False
        changes = {}
        if self.selectedSupportsColorOverlay:
            changes["color_overlay_enabled"] = mode == "color"
        if self.selectedSupportsGradientOverlay:
            changes["gradient_overlay_enabled"] = mode == "gradient"
        return self._set_layer_attrs(
            self.selectedLayerIndex,
            changes,
            "切换颜色叠加模式",
        )

    @Slot(bool, result=bool)
    def setSelectedColorOverlayEnabled(self, enabled: bool) -> bool:
        if enabled:
            return self.setSelectedOverlayMode("color")
        if self.selectedOverlayMode == "color":
            return self.setSelectedOverlayMode("none")
        return True

    @Slot(str, result=bool)
    def setSelectedColorOverlayColor(self, value: str) -> bool:
        if not self.selectedSupportsColorOverlay:
            self._set_status("当前图层不支持颜色叠加", toast=True)
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("叠加颜色格式无效", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "color_overlay_color",
            color,
            "修改叠加颜色",
        )

    @Slot(int, result=bool)
    def setSelectedColorOverlayOpacity(self, value: int) -> bool:
        if not self.selectedSupportsColorOverlay:
            self._set_status("当前图层不支持颜色叠加", toast=True)
            return False
        value = max(0, min(100, int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "color_overlay_opacity",
            value / 100.0,
            "修改颜色叠加强度",
        )

    @Slot(bool, result=bool)
    def setSelectedGradientOverlayEnabled(self, enabled: bool) -> bool:
        if enabled:
            return self.setSelectedOverlayMode("gradient")
        if self.selectedOverlayMode == "gradient":
            return self.setSelectedOverlayMode("none")
        return True

    @Slot(int, str, result=bool)
    def setSelectedGradientOverlayColor(self, index: int, value: str) -> bool:
        if not self.selectedSupportsGradientOverlay:
            self._set_status("当前图层不支持渐变叠加", toast=True)
            return False
        if index not in (0, 1):
            self._set_status("渐变颜色端点无效", toast=True)
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("渐变颜色格式无效", toast=True)
            return False
        colors = self._selected_gradient_colors()
        colors[index] = color
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "gradient_overlay_colors",
            colors,
            "修改渐变颜色",
        )

    @Slot(int, result=bool)
    def setSelectedGradientOverlayOpacity(self, value: int) -> bool:
        if not self.selectedSupportsGradientOverlay:
            self._set_status("当前图层不支持渐变叠加", toast=True)
            return False
        value = max(0, min(100, int(value)))
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "gradient_overlay_opacity",
            value / 100.0,
            "修改渐变叠加强度",
        )

    @Slot(float, result=bool)
    def setSelectedGradientOverlayAngle(self, value: float) -> bool:
        if not self.selectedSupportsGradientOverlay:
            self._set_status("当前图层不支持渐变叠加", toast=True)
            return False
        return self._set_layer_attr(
            self.selectedLayerIndex,
            "gradient_overlay_angle",
            float(value) % 360.0,
            "修改渐变角度",
        )

