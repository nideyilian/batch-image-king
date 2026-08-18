#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
状态指示器管理器
提供各种状态的可视化指示，包括文档修改状态、图层状态、选择状态等
"""

import logging

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (QWidget, QLabel, QHBoxLayout, QVBoxLayout,
                           QPushButton, QProgressBar, QFrame)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont, QColor, QPainter, QBrush, QPen

from app.ui.visual_hierarchy import VisualHierarchy
from app.ui.icon_manager import IconManager


class StatusBadge(QLabel):
    """状态徽章组件"""

    def __init__(self, text="", color_type="primary", parent=None):
        super().__init__(text, parent)
        self.color_type = color_type
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        vh = VisualHierarchy

        # 设置字体
        self.setFont(vh.get_font('tiny'))

        # 设置样式
        self.update_style()

        # 设置固定高度
        self.setFixedHeight(18)
        self.setAlignment(Qt.AlignCenter)

    def update_style(self):
        """更新样式"""
        vh = VisualHierarchy

        if self.color_type == "primary":
            bg_color = vh.get_color('primary', 'main')
            text_color = vh.get_color('primary', 'contrast')
        elif self.color_type == "success":
            bg_color = vh.get_color('state', 'success')
            text_color = vh.get_color('primary', 'contrast')
        elif self.color_type == "warning":
            bg_color = vh.get_color('state', 'warning')
            text_color = vh.get_color('primary', 'contrast')
        elif self.color_type == "error":
            bg_color = vh.get_color('state', 'error')
            text_color = vh.get_color('primary', 'contrast')
        else:  # secondary
            bg_color = vh.get_color('background', 'surface')
            text_color = vh.get_color('text', 'secondary')

        style = f"""
        QLabel {{
            background-color: {bg_color};
            color: {text_color};
            border-radius: {vh.get_radius('xl')}px;
            padding: {vh.get_spacing('xs')}px {vh.get_spacing('sm')}px;
            font-weight: bold;
            border: none;
        }}
        """

        self.setStyleSheet(style)

    def set_color_type(self, color_type):
        """设置颜色类型"""
        self.color_type = color_type
        self.update_style()


class StatusIndicator(QWidget):
    """状态指示器组件"""

    def __init__(self, icon="", text="", color_type="secondary", parent=None):
        super().__init__(parent)
        self.icon_text = icon
        self.status_text = text
        self.color_type = color_type
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(VisualHierarchy.get_spacing('xs'))

        # 图标标签
        if self.icon_text:
            self.icon_label = QLabel(self.icon_text)
            self.icon_label.setFont(VisualHierarchy.get_font('small'))
            layout.addWidget(self.icon_label)

        # 文本标签
        self.text_label = QLabel(self.status_text)
        self.text_label.setFont(VisualHierarchy.get_font('small'))
        layout.addWidget(self.text_label)

        # 应用样式
        self.update_style()

    def update_style(self):
        """更新样式"""
        vh = VisualHierarchy

        if self.color_type == "primary":
            text_color = vh.get_color('primary', 'main')
        elif self.color_type == "success":
            text_color = vh.get_color('state', 'success')
        elif self.color_type == "warning":
            text_color = vh.get_color('state', 'warning')
        elif self.color_type == "error":
            text_color = vh.get_color('state', 'error')
        else:  # secondary
            text_color = vh.get_color('text', 'secondary')

        style = f"""
        QLabel {{
            color: {text_color};
            background: transparent;
            border: none;
        }}
        """

        if hasattr(self, 'icon_label'):
            self.icon_label.setStyleSheet(style)
        self.text_label.setStyleSheet(style)

    def set_text(self, text):
        """设置文本"""
        self.status_text = text
        self.text_label.setText(text)

    def set_color_type(self, color_type):
        """设置颜色类型"""
        self.color_type = color_type
        self.update_style()


class DocumentStatusIndicator(QWidget):
    """文档状态指示器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.document = None
        self.is_modified = False
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(VisualHierarchy.get_spacing('sm'))

        # 修改状态指示器
        self.modified_indicator = StatusIndicator(
            IconManager.get_icon_text('edit'),
            "未修改",
            "secondary"
        )
        layout.addWidget(self.modified_indicator)

        # 分隔符
        separator = QFrame()
        separator.setFrameShape(QFrame.VLine)
        separator.setStyleSheet(f"""
            QFrame {{
                color: {VisualHierarchy.get_color('border', 'divider')};
                max-width: 1px;
            }}
        """)
        layout.addWidget(separator)

        # 图层数量指示器
        self.layer_count_indicator = StatusIndicator(
            "📋",
            "0 图层",
            "secondary"
        )
        layout.addWidget(self.layer_count_indicator)

        # 选中状态指示器
        self.selection_indicator = StatusIndicator(
            "👆",
            "未选中",
            "secondary"
        )
        layout.addWidget(self.selection_indicator)

    def set_document(self, document):
        """设置文档引用"""
        # 断开之前的连接
        if self.document:
            try:
                self.document.document_changed.disconnect(self.on_document_changed)
                self.document.layer_selected.disconnect(self.on_layer_selected)
            except Exception:
                logger.warning("静默异常已忽略: except in ui/status_indicators.py", exc_info=True)
                pass

        self.document = document

        # 连接新的信号
        if self.document:
            self.document.document_changed.connect(self.on_document_changed)
            self.document.layer_selected.connect(self.on_layer_selected)

            # 初始化状态
            self.update_all_status()

    def on_document_changed(self):
        """文档变化处理"""
        self.is_modified = True
        self.update_modification_status()
        self.update_layer_count()

    def on_layer_selected(self, layer_index):
        """图层选择变化处理"""
        self.update_selection_status()

    def update_modification_status(self):
        """更新修改状态"""
        if self.is_modified:
            self.modified_indicator.set_text("已修改")
            self.modified_indicator.set_color_type("warning")
        else:
            self.modified_indicator.set_text("未修改")
            self.modified_indicator.set_color_type("secondary")

    def update_layer_count(self):
        """更新图层数量"""
        if self.document and self.document.layers:
            count = len(self.document.layers)
            self.layer_count_indicator.set_text(f"{count} 图层")
            if count > 0:
                self.layer_count_indicator.set_color_type("primary")
            else:
                self.layer_count_indicator.set_color_type("secondary")
        else:
            self.layer_count_indicator.set_text("0 图层")
            self.layer_count_indicator.set_color_type("secondary")

    def update_selection_status(self):
        """更新选择状态"""
        if self.document and self.document.selected_layer_index >= 0:
            layer = self.document.layers[self.document.selected_layer_index]
            self.selection_indicator.set_text(f"已选中: {layer.name}")
            self.selection_indicator.set_color_type("success")
        else:
            self.selection_indicator.set_text("未选中")
            self.selection_indicator.set_color_type("secondary")

    def update_all_status(self):
        """更新所有状态"""
        self.update_modification_status()
        self.update_layer_count()
        self.update_selection_status()

    def mark_saved(self):
        """标记文档已保存"""
        self.is_modified = False
        self.update_modification_status()


class LayerStatusPanel(QWidget):
    """图层状态面板"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.layer = None
        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(VisualHierarchy.get_spacing('sm'),
                                 VisualHierarchy.get_spacing('sm'),
                                 VisualHierarchy.get_spacing('sm'),
                                 VisualHierarchy.get_spacing('sm'))
        layout.setSpacing(VisualHierarchy.get_spacing('sm'))

        # 标题
        title_label = QLabel("图层状态")
        title_label.setFont(VisualHierarchy.get_font('subtitle'))
        title_label.setStyleSheet(f"""
            QLabel {{
                color: {VisualHierarchy.get_color('text', 'primary')};
                font-weight: bold;
                margin-bottom: {VisualHierarchy.get_spacing('xs')}px;
            }}
        """)
        layout.addWidget(title_label)

        # 状态指示器容器
        status_layout = QVBoxLayout()
        status_layout.setSpacing(VisualHierarchy.get_spacing('xs'))

        # 可见性状态
        self.visibility_status = StatusIndicator(
            IconManager.get_icon_text('visible'),
            "可见",
            "success"
        )
        status_layout.addWidget(self.visibility_status)

        # 锁定状态
        self.lock_status = StatusIndicator(
            IconManager.get_icon_text('unlock'),
            "未锁定",
            "secondary"
        )
        status_layout.addWidget(self.lock_status)

        # 混合模式状态
        self.blend_status = StatusIndicator(
            IconManager.get_icon_text('blend'),
            "正常",
            "secondary"
        )
        status_layout.addWidget(self.blend_status)

        # 不透明度状态
        self.opacity_status = StatusIndicator(
            IconManager.get_icon_text('opacity'),
            "100%",
            "secondary"
        )
        status_layout.addWidget(self.opacity_status)

        layout.addLayout(status_layout)
        layout.addStretch()

        # 应用面板样式
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {VisualHierarchy.get_color('background', 'surface')};
                border: 1px solid {VisualHierarchy.get_color('border', 'secondary')};
                border-radius: {VisualHierarchy.get_radius('lg')}px;
            }}
        """)

    def set_layer(self, layer):
        """设置图层"""
        self.layer = layer
        self.update_all_status()

    def update_all_status(self):
        """更新所有状态"""
        if not self.layer:
            return

        # 更新可见性状态
        if self.layer.visible:
            self.visibility_status.set_text("可见")
            self.visibility_status.set_color_type("success")
        else:
            self.visibility_status.set_text("隐藏")
            self.visibility_status.set_color_type("warning")

        # 更新锁定状态
        if self.layer.locked:
            self.lock_status.set_text("已锁定")
            self.lock_status.set_color_type("error")
        else:
            self.lock_status.set_text("未锁定")
            self.lock_status.set_color_type("secondary")

        # 更新混合模式状态
        blend_mode = getattr(self.layer, 'blend_mode', 'normal')
        self.blend_status.set_text(f"混合: {blend_mode}")
        if blend_mode != 'normal':
            self.blend_status.set_color_type("primary")
        else:
            self.blend_status.set_color_type("secondary")

        # 更新不透明度状态
        opacity = getattr(self.layer, 'opacity', 1.0)
        opacity_percent = int(opacity * 100)
        self.opacity_status.set_text(f"{opacity_percent}%")
        if opacity_percent < 100:
            self.opacity_status.set_color_type("warning")
        else:
            self.opacity_status.set_color_type("secondary")


class ProgressIndicator(QWidget):
    """进度指示器"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setup_ui()
        self.hide()  # 默认隐藏

    def setup_ui(self):
        """设置UI"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(VisualHierarchy.get_spacing('md'),
                                 VisualHierarchy.get_spacing('sm'),
                                 VisualHierarchy.get_spacing('md'),
                                 VisualHierarchy.get_spacing('sm'))

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)

        # 设置进度条样式
        vh = VisualHierarchy
        progress_style = f"""
        QProgressBar {{
            background-color: {vh.get_color('background', 'surface')};
            border: 1px solid {vh.get_color('border', 'secondary')};
            border-radius: {vh.get_radius('sm')}px;
            text-align: center;
            color: {vh.get_color('text', 'primary')};
            font-size: {vh.FONTS['small']['size']}px;
        }}

        QProgressBar::chunk {{
            background-color: {vh.get_color('primary', 'main')};
            border-radius: {vh.get_radius('sm')}px;
        }}
        """

        self.progress_bar.setStyleSheet(progress_style)
        layout.addWidget(self.progress_bar)

        # 状态文本
        self.status_label = QLabel("准备中...")
        self.status_label.setFont(vh.get_font('small'))
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {vh.get_color('text', 'secondary')};
                background: transparent;
                border: none;
            }}
        """)
        layout.addWidget(self.status_label)

        # 应用容器样式
        self.setStyleSheet(f"""
            QWidget {{
                background-color: {vh.get_color('background', 'primary')};
                border: 1px solid {vh.get_color('border', 'secondary')};
                border-radius: {vh.get_radius('md')}px;
            }}
        """)

    def show_progress(self, message="处理中..."):
        """显示进度指示器"""
        self.status_label.setText(message)
        self.progress_bar.setValue(0)
        self.show()

    def update_progress(self, value, message=None):
        """更新进度"""
        self.progress_bar.setValue(value)
        if message:
            self.status_label.setText(message)

    def hide_progress(self):
        """隐藏进度指示器"""
        self.hide()


class ToastMessage(QLabel):
    """吐司消息组件"""

    def __init__(self, message="", message_type="info", parent=None):
        super().__init__(message, parent)
        self.message_type = message_type
        self.setup_ui()
        self.setup_animation()

    def setup_ui(self):
        """设置UI"""
        vh = VisualHierarchy

        # 设置字体
        self.setFont(vh.get_font('body'))

        # 根据消息类型设置样式
        if self.message_type == "success":
            bg_color = vh.get_color('state', 'success')
            text_color = vh.get_color('primary', 'contrast')
            icon = IconManager.get_icon_text('success')
        elif self.message_type == "warning":
            bg_color = vh.get_color('state', 'warning')
            text_color = vh.get_color('primary', 'contrast')
            icon = IconManager.get_icon_text('warning')
        elif self.message_type == "error":
            bg_color = vh.get_color('state', 'error')
            text_color = vh.get_color('primary', 'contrast')
            icon = IconManager.get_icon_text('remove')
        else:  # info
            bg_color = vh.get_color('primary', 'main')
            text_color = vh.get_color('primary', 'contrast')
            icon = IconManager.get_icon_text('info')

        # 添加图标到文本前
        current_text = self.text()
        self.setText(f"{icon} {current_text}")

        # 应用样式
        self.setStyleSheet(f"""
            QLabel {{
                background-color: {bg_color};
                color: {text_color};
                border: none;
                border-radius: {vh.get_radius('md')}px;
                padding: {vh.get_spacing('md')}px {vh.get_spacing('lg')}px;
                font-weight: bold;
            }}
        """)

        # 设置窗口属性
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAlignment(Qt.AlignCenter)

    def setup_animation(self):
        """设置动画"""
        self.opacity_effect = None

        # 自动隐藏定时器
        self.hide_timer = QTimer()
        self.hide_timer.setSingleShot(True)
        self.hide_timer.timeout.connect(self.fade_out)

    def show_message(self, duration=3000):
        """显示消息"""
        self.show()
        self.raise_()

        # 设置定时器
        if duration > 0:
            self.hide_timer.start(duration)

    def fade_out(self):
        """淡出动画"""
        self.hide()


class StatusIndicatorManager:
    """状态指示器管理器"""

    def __init__(self):
        self.document_status = None
        self.layer_status_panel = None
        self.progress_indicator = None
        self.active_toasts = []

    def create_document_status_indicator(self, parent=None):
        """创建文档状态指示器"""
        self.document_status = DocumentStatusIndicator(parent)
        return self.document_status

    def create_layer_status_panel(self, parent=None):
        """创建图层状态面板"""
        self.layer_status_panel = LayerStatusPanel(parent)
        return self.layer_status_panel

    def create_progress_indicator(self, parent=None):
        """创建进度指示器"""
        self.progress_indicator = ProgressIndicator(parent)
        return self.progress_indicator

    def show_toast(self, message, message_type="info", duration=3000, parent=None):
        """显示吐司消息"""
        toast = ToastMessage(message, message_type, parent)

        # 定位到父窗口中央
        if parent:
            parent_rect = parent.geometry()
            toast_rect = toast.sizeHint()
            x = parent_rect.x() + (parent_rect.width() - toast_rect.width()) // 2
            y = parent_rect.y() + parent_rect.height() // 3
            toast.move(x, y)

        # 显示消息
        toast.show_message(duration)

        # 添加到活动列表
        self.active_toasts.append(toast)

        # 清理过期的toast
        def cleanup():
            if toast in self.active_toasts:
                self.active_toasts.remove(toast)
                toast.deleteLater()

        QTimer.singleShot(duration + 500, cleanup)

        return toast

    def set_document(self, document):
        """设置文档引用"""
        if self.document_status:
            self.document_status.set_document(document)

    def set_selected_layer(self, layer):
        """设置选中的图层"""
        if self.layer_status_panel:
            self.layer_status_panel.set_layer(layer)

    def mark_document_saved(self):
        """标记文档已保存"""
        if self.document_status:
            self.document_status.mark_saved()


# 全局状态指示器管理器实例
status_manager = StatusIndicatorManager() 