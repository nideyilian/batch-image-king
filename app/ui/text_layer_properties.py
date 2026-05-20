#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
文字图层属性面板 - 使用整合的专业UI设计
将所有参数整合到一个紧凑、专业的界面中
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QSizePolicy)
from PySide6.QtCore import Qt, Signal

from app.models.text_layer import TextLayer
from app.ui.integrated_text_panel import IntegratedTextPanel


class TextLayerPropertiesPanel(QWidget):
    """文字图层属性面板 - 使用整合UI设计"""

    # 信号定义
    layer_changed = Signal()  # 图层属性变更信号
    create_text_layer_requested = Signal(str)  # 创建新文字图层信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_layer = None
        self.document = None  # 文档引用
        self.setup_ui()

    def setup_ui(self):
        """设置UI界面"""
        # 保持与其他属性模块一致宽度，不因内部内容自动撑宽
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.setMinimumWidth(0)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 创建整合的文字图层参数面板
        self.integrated_panel = IntegratedTextPanel()
        self.integrated_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.integrated_panel.setMinimumWidth(0)
        layout.addWidget(self.integrated_panel)

        # 连接整合面板的信号
        self.integrated_panel.property_changed.connect(self.on_property_changed)
        self.integrated_panel.create_text_requested.connect(self.on_create_text_requested)

    def set_text_layer(self, text_layer: TextLayer):
        """设置要编辑的文字图层"""
        if self.text_layer:
            # 断开旧图层的信号连接
            try:
                self.text_layer.changed.disconnect()
                self.text_layer.text_changed.disconnect()
            except:
                pass

        self.text_layer = text_layer

        if text_layer:
            # 连接新图层的信号
            text_layer.changed.connect(self.update_properties)
            text_layer.text_changed.connect(self.update_text_display)

            # 使用整合面板设置图层
            self.integrated_panel.set_text_layer(text_layer)
        else:
            # 清空整合面板
            self.integrated_panel.set_text_layer(None)

    def set_document(self, document):
        """设置文档引用"""
        self.document = document

    def _selected_text_layers(self):
        """返回当前多选中的文字图层。"""
        if not self.document or not hasattr(self.document, 'layers'):
            return []

        indices = list(getattr(self.document, 'selected_layer_indices', []) or [])
        if not indices and getattr(self.document, 'selected_layer_index', -1) >= 0:
            indices = [self.document.selected_layer_index]

        layers = []
        for index in indices:
            if 0 <= index < len(self.document.layers):
                layer = self.document.layers[index]
                if isinstance(layer, TextLayer):
                    layers.append(layer)
        return layers

    def _apply_change_to_selected_text_layers(self, property_name):
        """文字图层多选时，把主选图层的本次修改同步到其它文字图层。"""
        if not self.text_layer:
            return 0

        selected_layers = self._selected_text_layers()
        if len(selected_layers) <= 1:
            return 0

        direct_attrs = {
            "font_family", "font_size", "font_style", "text_align", "text_color",
            "stroke_width", "stroke_enabled", "stroke_color", "opacity",
            "line_spacing", "letter_spacing", "auto_fit_text_box",
            "text_box_padding", "vertical_layout", "current_text",
            "text_binding_enabled", "shadow_enabled", "shadow_color",
            "glow_enabled", "background_enabled", "background_color",
            "background_padding", "gradient_enabled", "gradient_type",
            "gradient_start_color", "gradient_end_color",
        }
        compound_attrs = {
            "position": ("x", "y"),
            "size": ("width", "height"),
            "shadow_params": ("shadow_offset_x", "shadow_offset_y", "shadow_blur"),
            "glow_params": ("glow_strength", "glow_radius"),
            "text_lines": ("text_content", "current_text"),
            "core_params_reset": (
                "font_family", "font_size", "font_style", "text_align",
                "text_color", "stroke_enabled", "stroke_width", "stroke_color",
                "opacity", "line_spacing", "letter_spacing", "text_box_padding",
                "auto_fit_text_box", "vertical_layout",
            ),
        }

        if property_name in direct_attrs:
            attrs = (property_name,)
        else:
            attrs = compound_attrs.get(property_name, ())
        if not attrs:
            return 0

        changed_count = 0
        for layer in selected_layers:
            if layer is self.text_layer or getattr(layer, 'locked', False):
                continue
            changed = False
            for attr in attrs:
                if hasattr(self.text_layer, attr) and hasattr(layer, attr):
                    value = getattr(self.text_layer, attr)
                    if getattr(layer, attr) != value:
                        setattr(layer, attr, value)
                        changed = True
            if changed:
                changed_count += 1
                if hasattr(layer, '_cached_image'):
                    layer._cached_image = None
                if hasattr(layer, 'cached_image'):
                    layer.cached_image = None

        return changed_count

    def update_properties(self):
        """更新属性显示"""
        if self.text_layer:
            self.integrated_panel.update_ui()

    def update_text_display(self):
        """更新文字显示"""
        if self.text_layer:
            self.integrated_panel.update_preview()

    def on_property_changed(self, property_name, value):
        """处理属性变更"""
        if self.text_layer:
            self._apply_change_to_selected_text_layers(property_name)
            # 通知主界面属性已变更
            self.layer_changed.emit()
            # 更新文档状态
            if self.document:
                # 兼容不同Document实现：优先调用方法，否则直接设置属性
                if hasattr(self.document, "set_modified") and callable(getattr(self.document, "set_modified")):
                    self.document.set_modified(True)
                else:
                    setattr(self.document, "is_modified", True)
                # 文字属性变更需要触发图层级刷新（例如竖排开关）
                try:
                    self.document.layer_changed.emit()
                    self.document.document_changed.emit()
                except Exception:
                    pass

    def on_create_text_requested(self, text_content):
        """处理创建新文字图层的请求"""
        self.create_text_layer_requested.emit(text_content)


# 测试代码
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication, QMainWindow

    app = QApplication(sys.argv)

    # 创建测试窗口
    window = QMainWindow()
    window.setWindowTitle("文字图层属性面板 - 整合版")
    window.resize(420, 800)

    # 创建面板
    panel = TextLayerPropertiesPanel()

    # 创建测试文字图层
    from app.models.text_layer import TextLayer
    text_layer = TextLayer()
    text_layer.name = "测试文字图层"
    text_layer.current_text = "专业UI整合设计"
    text_layer.font_family = "Microsoft YaHei"
    text_layer.font_size = 32
    text_layer.text_color = (255, 100, 100, 255)
    text_layer.opacity = 0.85

    panel.set_text_layer(text_layer)

    window.setCentralWidget(panel)
    window.show()

    print("✅ 整合版文字图层属性面板创建成功")
    print("🎯 设计优势:")
    print("   • 单一代码文件，维护简单")
    print("   • 专业卡片式布局")
    print("   • 核心参数优先展示")
    print("   • 紧凑布局，无冗余空间")
    print("   • 现代扁平化设计风格")
    print("   • 防抖机制，界面稳定")

    sys.exit(app.exec())
