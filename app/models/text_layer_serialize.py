# -*- coding: utf-8 -*-
"""TextLayer 方法 mixin：本文件由拆分脚本生成，方法原属于 TextLayer。"""
import logging
from PySide6.QtCore import QObject, Signal, Property
from PIL import Image, ImageDraw, ImageFont
import os
import random
import platform
import math
import threading
from typing import List, Tuple, Dict, Set, Optional
from enum import Enum, auto
import json
from pathlib import Path
from app.models.text_layer_enums import (
    TextAlign, FontStyle, GradientType, GradientDirection, safe_print
)

logger = logging.getLogger(__name__)


class TextLayerSerializeMixin:

    def set_current_text(self, value, emit_signals: bool = True, force: bool = False):
        """设置当前显示文字。

        批量导出会频繁切换文字内容，调用方可用 emit_signals=False 避免触发 UI 刷新；
        force=True 用于单候选文案等场景，即使文字未变化也清理缓存并通知。
        """
        value = "" if value is None else str(value)
        if not force and self._current_text == value:
            return False

        self._current_text = value
        self._clip_text_color_ranges_to_current_text()
        self._clip_font_size_ranges_to_current_text()
        self._cached_image = None
        self._update_text_box_size_if_needed()

        should_emit_signals = bool(emit_signals)
        if should_emit_signals:
            parent_doc = None
            if hasattr(self, '_parent') and self._parent:
                parent_doc = self._parent
            elif hasattr(self, 'parent') and self.parent():
                parent_doc = self.parent()

            if parent_doc and hasattr(parent_doc, '_is_batch_export_running'):
                should_emit_signals = not parent_doc._is_batch_export_running

        if should_emit_signals:
            self.text_changed.emit()
            self.changed.emit()

        return True

    def set_current_text_silent(self, value):
        """批量/后台任务专用：更新文字并清缓存，但不发射 UI 信号。"""
        return self.set_current_text(value, emit_signals=False)

    def _normalize_color_tuple(self, color):
        if not isinstance(color, (tuple, list)) or len(color) < 3:
            return self._text_color
        r = max(0, min(255, int(color[0])))
        g = max(0, min(255, int(color[1])))
        b = max(0, min(255, int(color[2])))
        a = max(0, min(255, int(color[3]))) if len(color) > 3 else 255
        return (r, g, b, a)

    def _clamp_text_range(self, start, end):
        text_len = len(self._current_text or "")
        start = max(0, min(text_len, int(start)))
        end = max(0, min(text_len, int(end)))
        if end < start:
            start, end = end, start
        return start, end

    def _subtract_color_range(self, ranges, start, end):
        next_ranges = []
        for item in ranges:
            item_start = int(item.get("start", 0))
            item_end = int(item.get("end", 0))
            color = self._normalize_color_tuple(item.get("color", self._text_color))
            if item_end <= start or item_start >= end:
                next_ranges.append({"start": item_start, "end": item_end, "color": color})
                continue
            if item_start < start:
                next_ranges.append({"start": item_start, "end": start, "color": color})
            if item_end > end:
                next_ranges.append({"start": end, "end": item_end, "color": color})
        return self._merge_text_color_ranges(next_ranges)

    def _merge_text_color_ranges(self, ranges):
        valid_ranges = []
        text_len = len(self._current_text or "")
        for item in ranges:
            try:
                start = max(0, min(text_len, int(item.get("start", 0))))
                end = max(0, min(text_len, int(item.get("end", 0))))
            except (TypeError, ValueError):
                logger.warning("静默异常已忽略: except (TypeError, ValueError): in text_layer_serialize.py", exc_info=True)
                continue
            if end <= start:
                continue
            valid_ranges.append({
                "start": start,
                "end": end,
                "color": self._normalize_color_tuple(item.get("color", self._text_color)),
            })

        valid_ranges.sort(key=lambda item: (item["start"], item["end"]))
        merged = []
        for item in valid_ranges:
            if merged and merged[-1]["color"] == item["color"] and item["start"] <= merged[-1]["end"]:
                merged[-1]["end"] = max(merged[-1]["end"], item["end"])
            else:
                merged.append(dict(item))
        return merged

    def _set_text_color_ranges(self, ranges):
        if not isinstance(ranges, list):
            ranges = []
        self._text_color_ranges = self._merge_text_color_ranges(ranges)

    def _clip_text_color_ranges_to_current_text(self):
        clipped = self._merge_text_color_ranges(self._text_color_ranges)
        if clipped != self._text_color_ranges:
            self._text_color_ranges = clipped
            return True
        return False

    def get_text_color_ranges(self):
        return [
            {"start": item["start"], "end": item["end"], "color": tuple(item["color"])}
            for item in self._text_color_ranges
        ]

    def set_text_color_range(self, start, end, color):
        start, end = self._clamp_text_range(start, end)
        if start >= end:
            return False
        ranges = self._subtract_color_range(self._text_color_ranges, start, end)
        ranges.append({"start": start, "end": end, "color": self._normalize_color_tuple(color)})
        self._text_color_ranges = self._merge_text_color_ranges(ranges)
        self._cached_image = None
        self.changed.emit()
        return True

    def clear_text_color_range(self, start, end):
        start, end = self._clamp_text_range(start, end)
        if start >= end:
            return False
        next_ranges = self._subtract_color_range(self._text_color_ranges, start, end)
        if next_ranges == self._text_color_ranges:
            return False
        self._text_color_ranges = next_ranges
        self._cached_image = None
        self.changed.emit()
        return True

    # ------------------------------------------------------------------
    # 局部字号区间（混合字号）
    # ------------------------------------------------------------------

    def _merge_font_size_ranges(self, ranges):
        valid_ranges = []
        text_len = len(self._current_text or "")
        for item in ranges or []:
            try:
                start = max(0, min(text_len, int(item.get("start", 0))))
                end = max(0, min(text_len, int(item.get("end", 0))))
                size = max(1, int(item.get("size", self._font_size)))
            except (TypeError, ValueError):
                logger.warning("静默异常已忽略: except (TypeError, ValueError): in text_layer_serialize.py", exc_info=True)
                continue
            if end <= start:
                continue
            valid_ranges.append({"start": start, "end": end, "size": size})

        valid_ranges.sort(key=lambda item: (item["start"], item["end"]))
        merged = []
        for item in valid_ranges:
            if merged and merged[-1]["size"] == item["size"] and item["start"] <= merged[-1]["end"]:
                merged[-1]["end"] = max(merged[-1]["end"], item["end"])
            else:
                merged.append(dict(item))
        return merged

    def _subtract_font_size_range(self, ranges, start, end):
        next_ranges = []
        for item in ranges or []:
            item_start = int(item.get("start", 0))
            item_end = int(item.get("end", 0))
            size = max(1, int(item.get("size", self._font_size)))
            if item_end <= start or item_start >= end:
                next_ranges.append({"start": item_start, "end": item_end, "size": size})
                continue
            if item_start < start:
                next_ranges.append({"start": item_start, "end": start, "size": size})
            if item_end > end:
                next_ranges.append({"start": end, "end": item_end, "size": size})
        return self._merge_font_size_ranges(next_ranges)

    def _clip_font_size_ranges_to_current_text(self):
        clipped = self._merge_font_size_ranges(self._font_size_ranges)
        if clipped != self._font_size_ranges:
            self._font_size_ranges = clipped
            return True
        return False

    def get_font_size_ranges(self):
        return [
            {"start": item["start"], "end": item["end"], "size": int(item["size"])}
            for item in self._font_size_ranges
        ]

    def has_font_size_ranges(self):
        return bool(self._font_size_ranges)

    def font_size_for_text_index(self, index):
        """返回字符索引处的字号；未设置局部字号时返回全局字号。"""
        for item in self._font_size_ranges:
            if item["start"] <= index < item["end"]:
                return int(item["size"])
        return self._font_size

    def set_font_size_range(self, start, end, size):
        """为指定字符区间设置独立字号。返回是否发生变更。"""
        start, end = self._clamp_text_range(start, end)
        if start >= end:
            return False
        size = max(1, int(size))
        if size == self._font_size:
            return self.clear_font_size_range(start, end)
        ranges = self._subtract_font_size_range(self._font_size_ranges, start, end)
        ranges.append({"start": start, "end": end, "size": size})
        self._font_size_ranges = self._merge_font_size_ranges(ranges)
        self._cached_image = None
        self._update_text_box_size_if_needed()
        self.changed.emit()
        return True

    def clear_font_size_range(self, start, end):
        """清除指定字符区间的独立字号（恢复全局字号）。返回是否发生变更。"""
        start, end = self._clamp_text_range(start, end)
        if start >= end:
            return False
        next_ranges = self._subtract_font_size_range(self._font_size_ranges, start, end)
        if next_ranges == self._font_size_ranges:
            return False
        self._font_size_ranges = next_ranges
        self._cached_image = None
        self._update_text_box_size_if_needed()
        self.changed.emit()
        return True

    def get_text_lines(self) -> List[str]:
        """获取文字行列表"""
        return self._text_lines.copy()

    def set_text_lines(self, lines: List[str]):
        """设置文字行列表"""
        self._text_lines = lines.copy()
        if self._text_lines and (self._current_text is None or str(self._current_text).strip() == ""):
            self._current_text = self._text_lines[0]
        self._clip_text_color_ranges_to_current_text()
        self._clip_font_size_ranges_to_current_text()
        self._cached_image = None
        self._update_text_box_size_if_needed()
        self.text_changed.emit()
        self.changed.emit()

    def parse_text_input_to_lines(self, text: str) -> List[str]:
        """根据当前绑定模式解析编辑器输入"""
        raw_text = "" if text is None else str(text)
        if self._text_binding_enabled:
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            return lines

        # 非绑定模式：整个文本作为一条文案，保留真实换行
        if raw_text.strip() == "":
            return []
        return [raw_text]

    def add_text_line(self, text: str):
        """添加新的文字行 - 确保绑定管理器能正确响应"""
        if text and text not in self._text_lines:
            self._text_lines.append(text)
            self._cached_image = None
            safe_print(f"[文字图层] 添加新文案: '{text}'")
            self.text_changed.emit()
            self.changed.emit()
            return True
        return False

    def insert_text_line(self, index: int, text: str):
        """在指定位置插入文字行"""
        if text and 0 <= index <= len(self._text_lines):
            if text not in self._text_lines:
                self._text_lines.insert(index, text)
                self._cached_image = None
                safe_print(f"[文字图层] 在位置 {index} 插入新文案: '{text}'")
                self.text_changed.emit()
                self.changed.emit()
                return True
        return False

    def remove_text_line(self, text: str):
        """移除指定的文字行"""
        if text in self._text_lines:
            self._text_lines.remove(text)
            # 如果移除的是当前显示的文字，切换到第一个可用的
            if self._current_text == text and self._text_lines:
                self._current_text = self._text_lines[0]
            elif not self._text_lines:
                self._current_text = ""
            self._cached_image = None
            safe_print(f"[文字图层] 移除文案: '{text}'")
            self.text_changed.emit()
            self.changed.emit()
            return True
        return False

    def serialize(self) -> dict:
        """序列化图层数据"""
        return {
            'type': 'text',
            'name': self._name,
            'x': self._x,
            'y': self._y,
            'width': self._width,
            'height': self._height,
            'visible': self._visible,
            'opacity': self._opacity,
            'locked': self._locked,
            'use_original_size': self._use_original_size,
            'text_lines': self._text_lines,
            'current_text': self._current_text,
            'random_mode': self._random_mode,
            'text_binding_enabled': self._text_binding_enabled,
            'font_family': self._font_family,
            'font_face': self._font_face,
            'font_size': self._font_size,
            'font_style': self._font_style.name,
            'text_color': self._text_color,
            'text_color_ranges': self.get_text_color_ranges(),
            'font_size_ranges': self.get_font_size_ranges(),
            'text_align': self._text_align.name,
            'line_spacing': self._line_spacing,
            'letter_spacing': self._letter_spacing,
            'text_box_padding': self._text_box_padding,
            'auto_fit_text_box': self._auto_fit_text_box,
            'vertical_layout': self._vertical_layout,
            'stroke_enabled': self._stroke_enabled,
            'stroke_width': self._stroke_width,
            'stroke_color': self._stroke_color,
            'background_enabled': self._background_enabled,
            'background_color': self._background_color,
            'background_padding': self._background_padding,
            'gradient_enabled': self._gradient_enabled,
            'gradient_type': self._gradient_type.name,
            'gradient_direction': self._gradient_direction.name,
            'gradient_angle': self._gradient_angle,
            'gradient_start_color': self._gradient_start_color,
            'gradient_end_color': self._gradient_end_color,
            'gradient_center_x': self._gradient_center_x,
            'gradient_center_y': self._gradient_center_y,
            'supersample_enabled': self._supersample_enabled,
            'supersample_scale': self._supersample_scale,
            'shadow_enabled': self._shadow_enabled,
            'shadow_offset_x': self._shadow_offset_x,
            'shadow_offset_y': self._shadow_offset_y,
            'shadow_blur': self._shadow_blur,
            'shadow_color': self._shadow_color,
            'glow_enabled': self._glow_enabled,
            'glow_strength': self._glow_strength,
            'glow_radius': self._glow_radius
        }

    @classmethod
    def deserialize(cls, data: dict, parent=None):
        """反序列化图层数据"""
        layer = cls(
            name=data.get('name', '文字图层'),
            x=data.get('x', 0),
            y=data.get('y', 0),
            width=data.get('width', 200),
            height=data.get('height', 100),
            parent=parent
        )

        layer._visible = data.get('visible', True)
        layer._opacity = data.get('opacity', 1.0)
        layer._locked = data.get('locked', False)
        layer._use_original_size = data.get('use_original_size', False)
        layer._text_lines = data.get('text_lines', ['示例文字'])
        layer._current_text = data.get('current_text', '示例文字')
        layer._random_mode = data.get('random_mode', False)
        layer._text_binding_enabled = data.get('text_binding_enabled', True)
        layer._font_family = data.get('font_family', layer._get_default_font())
        layer._font_face = str(data.get('font_face', '') or '')
        layer._font_size = data.get('font_size', 24)
        layer._font_style = FontStyle[data.get('font_style', 'NORMAL')]
        layer._text_color = tuple(data.get('text_color', (0, 0, 0, 255)))
        layer._set_text_color_ranges(data.get('text_color_ranges', []))
        layer._font_size_ranges = layer._merge_font_size_ranges(data.get('font_size_ranges', []))
        layer._text_align = TextAlign[data.get('text_align', 'LEFT')]
        layer._line_spacing = data.get('line_spacing', 1.2)
        layer._letter_spacing = data.get('letter_spacing', 0)
        layer._text_box_padding = max(0, int(data.get('text_box_padding', 5)))
        layer._auto_fit_text_box = bool(data.get('auto_fit_text_box', True))
        layer._vertical_layout = bool(data.get('vertical_layout', False))
        layer._stroke_enabled = data.get('stroke_enabled', False)
        layer._stroke_width = data.get('stroke_width', 2)
        layer._stroke_color = tuple(data.get('stroke_color', (255, 255, 255, 255)))
        layer._background_enabled = data.get('background_enabled', False)
        layer._background_color = tuple(data.get('background_color', (255, 255, 255, 128)))
        layer._background_padding = data.get('background_padding', 5)
        layer._gradient_enabled = data.get('gradient_enabled', False)
        layer._gradient_type = GradientType[data.get('gradient_type', 'LINEAR')]
        layer._gradient_direction = GradientDirection[data.get('gradient_direction', 'HORIZONTAL')]
        layer._gradient_angle = data.get('gradient_angle', 0)
        layer._gradient_start_color = tuple(data.get('gradient_start_color', (255, 0, 0, 255)))
        layer._gradient_end_color = tuple(data.get('gradient_end_color', (0, 0, 255, 255)))
        layer._gradient_center_x = data.get('gradient_center_x', 0.5)
        layer._gradient_center_y = data.get('gradient_center_y', 0.5)
        layer._supersample_enabled = bool(data.get('supersample_enabled', True))
        layer._supersample_scale = max(1, int(data.get('supersample_scale', 2)))
        layer.shadow_enabled = bool(data.get('shadow_enabled', False))
        layer.shadow_offset_x = int(data.get('shadow_offset_x', 2))
        layer.shadow_offset_y = int(data.get('shadow_offset_y', 2))
        layer.shadow_blur = int(data.get('shadow_blur', 4))
        layer.shadow_color = tuple(data.get('shadow_color', (0, 0, 0, 128)))
        layer.glow_enabled = bool(data.get('glow_enabled', False))
        layer.glow_strength = int(data.get('glow_strength', 5))
        layer.glow_radius = int(data.get('glow_radius', 10))
        layer._update_text_box_size_if_needed()

        return layer

    def apply_effects(self, image):
        """应用图层特效（简化版本，适用于文字图层）"""
        if image is None:
            return None

        # 文字图层暂时不支持复杂特效，直接返回渲染的图像
        # 这是为了保持与普通图层接口的兼容性
        return image

    def generate_random_transform_params(self):
        """生成随机变换参数（空实现，保持接口兼容性）"""
        # 文字图层暂时不支持随机变换
        # 这个方法主要是为了保持与普通图层接口的兼容性
        pass

    def get_effective_position(self):
        """获取有效位置（简单返回当前位置）"""
        return (self._x, self._y)

    def get_effective_clone_positions(self):
        """获取分身位置（简单返回当前位置）"""
        return [self.get_effective_position()]

    def duplicate(self, parent=None):
        """创建文字图层的副本"""
        # 在方法内 lazy import 以避开 text_layer 模块加载时的循环依赖
        from app.models.text_layer import TextLayer

        # 创建新的图层实例
        new_layer = TextLayer(
            name=self._name,
            x=self._x,
            y=self._y,
            width=self._width,
            height=self._height,
            parent=parent
        )

        # 复制所有属性
        new_layer._visible = self._visible
        new_layer._opacity = self._opacity
        new_layer._locked = self._locked
        new_layer._use_original_size = self._use_original_size

        # 复制文字内容
        new_layer._text_lines = self._text_lines.copy()
        new_layer._current_text = self._current_text
        new_layer._random_mode = self._random_mode
        new_layer._text_binding_enabled = self._text_binding_enabled

        # 复制字体属性
        new_layer._font_family = self._font_family
        new_layer._font_face = self._font_face
        new_layer._font_size = self._font_size
        new_layer._font_style = self._font_style

        # 复制文字样式
        new_layer._text_color = self._text_color
        new_layer._text_color_ranges = self.get_text_color_ranges()
        new_layer._font_size_ranges = self.get_font_size_ranges()
        new_layer._text_align = self._text_align
        new_layer._line_spacing = self._line_spacing
        new_layer._letter_spacing = self._letter_spacing
        new_layer._text_box_padding = self._text_box_padding
        new_layer._auto_fit_text_box = self._auto_fit_text_box
        new_layer._vertical_layout = self._vertical_layout

        # 复制渐变设置
        new_layer._gradient_enabled = self._gradient_enabled
        new_layer._gradient_type = self._gradient_type
        new_layer._gradient_direction = self._gradient_direction
        new_layer._gradient_start_color = self._gradient_start_color
        new_layer._gradient_end_color = self._gradient_end_color
        new_layer._gradient_angle = self._gradient_angle
        new_layer._gradient_center_x = self._gradient_center_x
        new_layer._gradient_center_y = self._gradient_center_y

        # 复制描边设置
        new_layer._stroke_enabled = self._stroke_enabled
        new_layer._stroke_width = self._stroke_width
        new_layer._stroke_color = self._stroke_color

        # 复制背景设置
        new_layer._background_enabled = self._background_enabled
        new_layer._background_color = self._background_color
        new_layer._background_padding = self._background_padding

        # 清空缓存（新图层需要重新生成）
        new_layer._cached_image = None
        new_layer._font_cache = {}

        return new_layer
