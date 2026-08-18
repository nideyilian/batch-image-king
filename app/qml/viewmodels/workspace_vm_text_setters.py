"""WorkspaceViewModel 文字 setter 方法组 mixin（P1-4 拆分）。

从 ``workspace_view_model.py`` 原样迁出的文字属性设置方法组（46 个方法），
语义不变。依赖主类提供的实例方法/属性（``setTextContentForLayer``、
``_set_layer_attrs``、``_selected_layer`` 等）与下列模块级名字。
"""

from __future__ import annotations

from PySide6.QtCore import Slot

from app.utils.text_rich_format import qt_index_to_python

from .workspace_vm_shared import (
    _TEXT_ALIGNMENTS,
    _TEXT_GRADIENT_DIRECTIONS,
    _TEXT_GRADIENT_TYPES,
)


class WorkspaceTextSettersMixin:
    @Slot(str, result=bool)
    def setSelectedTextContent(self, content: str) -> bool:
        return self.setTextContentForLayer(self.selectedLayerIndex, content)

    @Slot(bool, result=bool)
    def setSelectedTextBindingEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)

        def apply(layer) -> None:
            layer.text_binding_enabled = enabled
            lines = layer.get_text_lines()
            layer.set_current_text(lines[0] if lines else "", force=True)

        mode = "按行随机" if enabled else "整段排版"
        return self._change_selected_text("切换文字内容模式", apply, f"文字模式 · {mode}")

    @Slot(int, result=bool)
    def setSelectedTextFontSize(self, value: int) -> bool:
        value = int(value)
        if not 1 <= value <= 1000:
            self._set_status("字号必须在 1 到 1000 之间", toast=True)
            return False
        return self._change_selected_text(
            "修改文字字号",
            lambda layer: setattr(layer, "font_size", value),
            f"文字字号 · {value} px",
        )

    @Slot(str, result=bool)
    def setSelectedTextFontFamily(self, family: str) -> bool:
        family = self._canonical_text_font_family(family)
        if not family:
            self._set_status("字体名称不能为空", toast=True)
            return False
        # 同值短路：避免空操作 push undo 历史
        layer = self._selected_layer() if self.selectedIsTextLayer else None
        if layer is not None:
            cur_family = str(getattr(layer, "font_family", "") or "")
            if cur_family.casefold() == family.casefold():
                self._push_recent_text_font(family, "")
                return True
        ok = self._change_selected_text(
            "修改文字字体",
            lambda layer: (setattr(layer, "font_family", family), setattr(layer, "font_face", "")),
            f"文字字体 · {family}",
        )
        if ok:
            self._push_recent_text_font(family, "")
        return ok

    @Slot(str, str, result=bool)
    def setSelectedTextFontFace(self, family: str, face: str) -> bool:
        family = self._canonical_text_font_family(family)
        face = str(face or "").strip()
        if not family or not face:
            self._set_status("字体字重不能为空", toast=True)
            return False
        if self._selected_font_face(family, face) is None:
            self._set_status("未找到所选字体字重", toast=True)
            return False

        # 同值短路：避免空操作 push undo 历史
        layer = self._selected_layer() if self.selectedIsTextLayer else None
        if layer is not None:
            cur_family = str(getattr(layer, "font_family", "") or "")
            cur_face = str(getattr(layer, "font_face", "") or "")
            if cur_family.casefold() == family.casefold() and cur_face.casefold() == face.casefold():
                self._push_recent_text_font(family, face)
                return True

        def apply(layer) -> None:
            layer.font_family = family
            layer.font_face = face
            layer.font_style = "NORMAL"

        ok = self._change_selected_text(
            "修改文字字体字重",
            apply,
            f"文字字重 · {family} · {self._font_face_label(face)}",
        )
        if ok:
            self._push_recent_text_font(family, face)
        return ok

    @Slot(int, result=bool)
    def setSelectedTextFontWeight(self, weight: int) -> bool:
        weight = int(weight)
        if not 100 <= weight <= 900:
            self._set_status("字体字重必须在 100 到 900 之间", toast=True)
            return False
        face = self._nearest_font_face_for_weight(weight, self.selectedTextItalic)
        if face is not None:
            return self.setSelectedTextFontFace(self.selectedTextFontFamily, face["face"])
        style = self._font_style_name(weight >= 600, self.selectedTextItalic)
        return self._change_selected_text(
            "修改文字字体字重",
            lambda layer: setattr(layer, "font_style", style),
            f"文字字重 · {700 if weight >= 600 else 400}",
        )

    @staticmethod
    def _font_style_name(bold: bool, italic: bool) -> str:
        if bold and italic:
            return "BOLD_ITALIC"
        if bold:
            return "BOLD"
        if italic:
            return "ITALIC"
        return "NORMAL"

    @Slot(bool, result=bool)
    def setSelectedTextBold(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        face = self._nearest_font_face(enabled, self.selectedTextItalic)
        if face is not None:
            return self.setSelectedTextFontFace(self.selectedTextFontFamily, face["face"])
        style = self._font_style_name(enabled, self.selectedTextItalic)
        return self._change_selected_text(
            "切换文字粗体",
            lambda layer: setattr(layer, "font_style", style),
            "文字粗体已开启" if enabled else "文字粗体已关闭",
        )

    @Slot(bool, result=bool)
    def setSelectedTextItalic(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        face = self._nearest_font_face(self.selectedTextBold, enabled)
        if face is not None:
            return self.setSelectedTextFontFace(self.selectedTextFontFamily, face["face"])
        style = self._font_style_name(self.selectedTextBold, enabled)
        return self._change_selected_text(
            "切换文字斜体",
            lambda layer: setattr(layer, "font_style", style),
            "文字斜体已开启" if enabled else "文字斜体已关闭",
        )

    @Slot(str, result=bool)
    def setSelectedTextAlignment(self, alignment_id: str) -> bool:
        alignment = _TEXT_ALIGNMENTS.get(str(alignment_id or "").strip().lower())
        if alignment is None:
            self._set_status("未知的文字对齐方式", toast=True)
            return False
        return self._change_selected_text(
            "修改文字对齐",
            lambda layer: setattr(layer, "text_align", alignment[0]),
            f"文字对齐 · {alignment[1]}",
        )

    @Slot(int, result=bool)
    def setSelectedTextLineSpacingPercent(self, value: int) -> bool:
        value = max(50, min(300, int(value)))
        return self._change_selected_text(
            "修改文字行距",
            lambda layer: setattr(layer, "line_spacing", value / 100.0),
            f"文字行距 · {value}%",
        )

    @Slot(int, result=bool)
    def setSelectedTextLetterSpacing(self, value: int) -> bool:
        value = max(-20, min(100, int(value)))
        return self._change_selected_text(
            "修改文字字距",
            lambda layer: setattr(layer, "letter_spacing", value),
            f"文字字距 · {value} px",
        )

    @Slot(int, result=bool)
    def setSelectedTextBoxPadding(self, value: int) -> bool:
        value = max(0, min(200, int(value)))
        return self._change_selected_text(
            "修改文字内边距",
            lambda layer: setattr(layer, "text_box_padding", value),
            f"文字内边距 · {value} px",
        )

    @Slot(bool, result=bool)
    def setSelectedTextAutoFitTextBox(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换自动文本框",
            lambda layer: setattr(layer, "auto_fit_text_box", enabled),
            "自动文本框已开启" if enabled else "自动文本框已关闭",
        )

    @Slot(bool, result=bool)
    def setSelectedTextVerticalLayout(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换文字排版方向",
            lambda layer: setattr(layer, "vertical_layout", enabled),
            "文字已切换为竖排" if enabled else "文字已切换为横排",
        )

    @Slot(str, result=bool)
    def setSelectedTextColor(self, value: str) -> bool:
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字颜色格式无效", toast=True)
            return False
        return self._change_selected_text(
            "修改文字颜色",
            lambda layer: setattr(layer, "text_color", color),
            f"文字颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(str, result=bool)
    def setSelectedTextFillMode(self, mode_id: str) -> bool:
        mode_id = str(mode_id or "").strip().lower()
        if mode_id not in ("solid", "gradient"):
            self._set_status("未知的文字填充模式", toast=True)
            return False
        enabled = mode_id == "gradient"
        return self._change_selected_text(
            "切换文字填充模式",
            lambda layer: setattr(layer, "gradient_enabled", enabled),
            "文字填充 · 渐变" if enabled else "文字填充 · 纯色",
        )

    @Slot(str, result=bool)
    def setSelectedTextGradientType(self, type_id: str) -> bool:
        gradient = _TEXT_GRADIENT_TYPES.get(str(type_id or "").strip().lower())
        if gradient is None:
            self._set_status("未知的文字渐变类型", toast=True)
            return False
        return self._change_selected_text(
            "修改文字渐变类型",
            lambda layer: setattr(layer, "gradient_type", gradient[0]),
            f"文字渐变 · {gradient[1]}",
        )

    @Slot(str, result=bool)
    def setSelectedTextGradientDirection(self, direction_id: str) -> bool:
        direction = _TEXT_GRADIENT_DIRECTIONS.get(
            str(direction_id or "").strip().lower()
        )
        if direction is None:
            self._set_status("未知的文字渐变方向", toast=True)
            return False
        return self._change_selected_text(
            "修改文字渐变方向",
            lambda layer: setattr(layer, "gradient_direction", direction[0]),
            f"文字渐变方向 · {direction[1]}",
        )

    @Slot(int, str, result=bool)
    def setSelectedTextGradientColor(self, index: int, value: str) -> bool:
        if index not in (0, 1):
            self._set_status("文字渐变颜色端点无效", toast=True)
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字渐变颜色格式无效", toast=True)
            return False
        attr = "gradient_start_color" if index == 0 else "gradient_end_color"
        return self._change_selected_text(
            "修改文字渐变颜色",
            lambda layer: setattr(layer, attr, color),
            f"文字渐变颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(int, int, result=bool)
    def setSelectedTextGradientCenter(self, x_percent: int, y_percent: int) -> bool:
        x_percent = max(0, min(100, int(x_percent)))
        y_percent = max(0, min(100, int(y_percent)))

        def apply(layer) -> None:
            layer.gradient_center_x = x_percent / 100.0
            layer.gradient_center_y = y_percent / 100.0

        return self._change_selected_text(
            "修改文字渐变中心",
            apply,
            f"文字渐变中心 · {x_percent}% / {y_percent}%",
        )

    @Slot(bool, result=bool)
    def setSelectedTextBackgroundEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换文字背景",
            lambda layer: setattr(layer, "background_enabled", enabled),
            "文字背景已开启" if enabled else "文字背景已关闭",
        )

    @Slot(str, result=bool)
    def setSelectedTextBackgroundColor(self, value: str) -> bool:
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字背景颜色格式无效", toast=True)
            return False
        return self._change_selected_text(
            "修改文字背景颜色",
            lambda layer: setattr(layer, "background_color", color),
            f"文字背景颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(int, result=bool)
    def setSelectedTextBackgroundOpacity(self, value: int) -> bool:
        value = max(0, min(100, int(value)))

        def apply(layer) -> None:
            color = tuple(getattr(layer, "background_color", (255, 255, 255, 128)))
            rgb = color[:3] if len(color) >= 3 else (255, 255, 255)
            layer.background_color = rgb + (round(value / 100.0 * 255),)

        return self._change_selected_text(
            "修改文字背景透明度",
            apply,
            f"文字背景透明度 · {value}%",
        )

    @Slot(int, result=bool)
    def setSelectedTextBackgroundPadding(self, value: int) -> bool:
        value = max(-50, min(50, int(value)))
        return self._change_selected_text(
            "修改文字背景扩展",
            lambda layer: setattr(layer, "background_padding", value),
            f"文字背景扩展 · {value:+d} px",
        )

    @Slot(bool, result=bool)
    def setSelectedTextShadowEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换文字阴影",
            lambda layer: setattr(layer, "shadow_enabled", enabled),
            "文字阴影已开启" if enabled else "文字阴影已关闭",
        )

    @Slot(int, int, result=bool)
    def setSelectedTextShadowOffset(self, x: int, y: int) -> bool:
        x = max(-50, min(50, int(x)))
        y = max(-50, min(50, int(y)))

        def apply(layer) -> None:
            layer.shadow_offset_x = x
            layer.shadow_offset_y = y

        return self._change_selected_text(
            "修改文字阴影偏移",
            apply,
            f"文字阴影偏移 · {x:+d} / {y:+d} px",
        )

    @Slot(int, result=bool)
    def setSelectedTextShadowBlur(self, value: int) -> bool:
        value = max(0, min(20, int(value)))
        return self._change_selected_text(
            "修改文字阴影模糊",
            lambda layer: setattr(layer, "shadow_blur", value),
            f"文字阴影模糊 · {value} px",
        )

    @Slot(str, result=bool)
    def setSelectedTextShadowColor(self, value: str) -> bool:
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字阴影颜色格式无效", toast=True)
            return False
        return self._change_selected_text(
            "修改文字阴影颜色",
            lambda layer: setattr(layer, "shadow_color", color),
            f"文字阴影颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(int, result=bool)
    def setSelectedTextShadowOpacity(self, value: int) -> bool:
        value = max(0, min(100, int(value)))

        def apply(layer) -> None:
            color = tuple(getattr(layer, "shadow_color", (0, 0, 0, 128)))
            rgb = color[:3] if len(color) >= 3 else (0, 0, 0)
            layer.shadow_color = rgb + (round(value / 100.0 * 255),)

        return self._change_selected_text(
            "修改文字阴影透明度",
            apply,
            f"文字阴影透明度 · {value}%",
        )

    @Slot(bool, result=bool)
    def setSelectedTextGlowEnabled(self, enabled: bool) -> bool:
        enabled = bool(enabled)
        return self._change_selected_text(
            "切换文字发光",
            lambda layer: setattr(layer, "glow_enabled", enabled),
            "文字发光已开启" if enabled else "文字发光已关闭",
        )

    @Slot(int, result=bool)
    def setSelectedTextGlowStrength(self, value: int) -> bool:
        value = max(0, min(20, int(value)))
        return self._change_selected_text(
            "修改文字发光强度",
            lambda layer: setattr(layer, "glow_strength", value),
            f"文字发光强度 · {value}",
        )

    @Slot(int, result=bool)
    def setSelectedTextGlowRadius(self, value: int) -> bool:
        value = max(1, min(50, int(value)))
        return self._change_selected_text(
            "修改文字发光半径",
            lambda layer: setattr(layer, "glow_radius", value),
            f"文字发光半径 · {value} px",
        )

    @Slot(str, result=bool)
    def setSelectedTextGlowColor(self, value: str) -> bool:
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("文字发光颜色格式无效", toast=True)
            return False
        return self._change_selected_text(
            "修改文字发光颜色",
            lambda layer: setattr(layer, "glow_color", color),
            f"文字发光颜色 · {self._rgba_to_hex(color)}",
        )

    @Slot(int, result=bool)
    def setSelectedTextGlowOpacity(self, value: int) -> bool:
        value = max(0, min(100, int(value)))

        def apply(layer) -> None:
            color = tuple(getattr(layer, "glow_color", (255, 255, 255, 255)))
            rgb = color[:3] if len(color) >= 3 else (255, 255, 255)
            layer.glow_color = rgb + (round(value / 100.0 * 255),)

        return self._change_selected_text(
            "修改文字发光透明度",
            apply,
            f"文字发光透明度 · {value}%",
        )

    def _validated_selected_text_range(self, start: int, end: int, label: str = "局部颜色"):
        if not self.selectedIsTextLayer:
            self._set_status("当前图层不是文字图层", toast=True)
            return None
        if self.selectedTextBindingEnabled:
            self._set_status(f"{label}仅支持整段排版模式", toast=True)
            return None
        text = str(getattr(self._selected_layer(), "current_text", "") or "")
        start = max(0, min(len(text), int(start)))
        end = max(0, min(len(text), int(end)))
        if start > end:
            start, end = end, start
        if start >= end:
            self._set_status(f"请先选择需要设置{label}的文字", toast=True)
            return None
        return start, end

    @Slot(int, int, str, result=bool)
    def setSelectedTextColorRange(self, start: int, end: int, value: str) -> bool:
        selected_range = self._validated_selected_text_range(start, end)
        if selected_range is None:
            return False
        color = self._parse_hex_color(value)
        if color is None:
            self._set_status("局部文字颜色格式无效", toast=True)
            return False
        start, end = selected_range
        return self._change_selected_text(
            "修改局部文字颜色",
            lambda layer: layer.set_text_color_range(start, end, color),
            f"已设置 {end - start} 个字符的局部颜色",
        )

    @Slot(int, int, result=bool)
    def clearSelectedTextColorRange(self, start: int, end: int) -> bool:
        selected_range = self._validated_selected_text_range(start, end)
        if selected_range is None:
            return False
        start, end = selected_range
        layer = self._selected_layer()
        ranges = layer.get_text_color_ranges()
        if not any(item["end"] > start and item["start"] < end for item in ranges):
            self._set_status("当前选区没有局部颜色", toast=True)
            return False
        return self._change_selected_text(
            "清除局部文字颜色",
            lambda selected: selected.clear_text_color_range(start, end),
            f"已清除 {end - start} 个字符的局部颜色",
        )

    def _qt_text_range_to_python(self, start_qt: int, end_qt: int):
        if not self.selectedIsTextLayer:
            self._set_status("当前图层不是文字图层", toast=True)
            return None
        text = str(getattr(self._selected_layer(), "current_text", "") or "")
        try:
            start_qt = int(start_qt)
            end_qt = int(end_qt)
            max_qt = len(text.encode("utf-16-le")) // 2
            if start_qt < 0 or end_qt < 0 or start_qt > max_qt or end_qt > max_qt:
                self._set_status("文字选区超出范围", toast=True)
                return None
            start = qt_index_to_python(text, start_qt)
            end = qt_index_to_python(text, end_qt)
        except (TypeError, ValueError):
            self._set_status("文字选区无效", toast=True)
            return None
        if start == end:
            self._set_status("请先选择需要设置局部样式的文字", toast=True)
            return None
        return start, end

    @Slot(int, int, str, result=bool)
    def setSelectedTextColorRangeQt(self, start_qt: int, end_qt: int, value: str) -> bool:
        selected_range = self._qt_text_range_to_python(start_qt, end_qt)
        if selected_range is None:
            return False
        return self.setSelectedTextColorRange(*selected_range, value)

    @Slot(int, int, result=bool)
    def clearSelectedTextColorRangeQt(self, start_qt: int, end_qt: int) -> bool:
        selected_range = self._qt_text_range_to_python(start_qt, end_qt)
        if selected_range is None:
            return False
        return self.clearSelectedTextColorRange(*selected_range)

    @Slot(int, int, int, result=bool)
    def setSelectedTextFontSizeRange(self, start: int, end: int, value: int) -> bool:
        selected_range = self._validated_selected_text_range(start, end, "局部字号")
        if selected_range is None:
            return False
        try:
            value = max(1, min(1000, int(value)))
        except (TypeError, ValueError):
            self._set_status("局部字号无效", toast=True)
            return False
        start, end = selected_range
        return self._change_selected_text(
            "修改局部文字字号",
            lambda layer: layer.set_font_size_range(start, end, value),
            f"已设置 {end - start} 个字符的局部字号",
        )

    @Slot(int, int, result=bool)
    def clearSelectedTextFontSizeRange(self, start: int, end: int) -> bool:
        selected_range = self._validated_selected_text_range(start, end, "局部字号")
        if selected_range is None:
            return False
        start, end = selected_range
        layer = self._selected_layer()
        ranges = layer.get_font_size_ranges()
        if not any(item["end"] > start and item["start"] < end for item in ranges):
            self._set_status("当前选区没有局部字号", toast=True)
            return False
        return self._change_selected_text(
            "清除局部文字字号",
            lambda selected: selected.clear_font_size_range(start, end),
            f"已清除 {end - start} 个字符的局部字号",
        )

    @Slot(int, int, int, result=bool)
    def setSelectedTextFontSizeRangeQt(self, start_qt: int, end_qt: int, value: int) -> bool:
        selected_range = self._qt_text_range_to_python(start_qt, end_qt)
        if selected_range is None:
            return False
        return self.setSelectedTextFontSizeRange(*selected_range, value)

    @Slot(int, int, result=bool)
    def clearSelectedTextFontSizeRangeQt(self, start_qt: int, end_qt: int) -> bool:
        selected_range = self._qt_text_range_to_python(start_qt, end_qt)
        if selected_range is None:
            return False
        return self.clearSelectedTextFontSizeRange(*selected_range)
