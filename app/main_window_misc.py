# -*- coding: utf-8 -*-
"""Main window components."""

from PySide6.QtWidgets import (QMainWindow, QDockWidget, QFileDialog,                                QVBoxLayout, QWidget, QMenu, QToolBar, QSplitter,                               QLabel, QSpinBox, QHBoxLayout, QPushButton, QMessageBox, QInputDialog,                               QTabWidget, QTabBar, QDialog, QFormLayout, QDialogButtonBox,                               QSizePolicy, QLineEdit)
from PySide6.QtCore import Qt, QSize, QPoint, QRect, QSettings, QTimer
from PySide6.QtGui import QIcon, QColor, QAction, QCloseEvent, QKeySequence, QPixmap
from app.ui.canvas import CanvasWidget
from app.ui.layer_panel import LayerPanel
from app.models.document import Document
from app.models.document_manager import DocumentManager
from app.ui.document_tab import DocumentTab
from app.ui.new_canvas_dialog import NewCanvasDialog
from app.ui.layer_properties import LayerPropertiesPanel
from app.utils.preset_manager import PresetManager
from app.ui.status_indicators import status_manager
from app.ui.visual_hierarchy import VisualHierarchy
import os
import pickle

class MainWindowMisc(object):
    def update_position_label(self, x, y):
        """更新坐标显示"""
        self.position_label.setText(f"坐标: {x}, {y}")

    def on_canvas_layer_moved(self, layer_index, delta_x, delta_y):
        """处理画布图层移动信号"""
        # 通知图层属性面板更新
        if hasattr(self, 'properties_panel') and self.properties_panel:
            self.properties_panel.update_panel()

    def on_canvas_layer_resized(self, layer_index, handle_index, width, height, x, y):
        """处理画布图层调整大小信号"""
        # 通知图层属性面板更新
        if hasattr(self, 'properties_panel') and self.properties_panel:
            self.properties_panel.update_panel()

    def update_history_actions(self):
        """更新撤销重做动作的状态"""
        if self.document and hasattr(self.document, 'can_undo'):
            self.undo_action.setEnabled(self.document.can_undo())
            self.redo_action.setEnabled(self.document.can_redo())
        else:
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)

    def update_copy_paste_actions(self):
        """更新复制粘贴操作的状态"""
        if self.document and self.document.selected_layer_index >= 0 and \
           self.document.selected_layer_index < len(self.document.layers):
            # 有选中的图层，启用复制功能
            self.copy_layer_action.setEnabled(True)
        else:
            # 没有选中的图层，禁用复制功能
            self.copy_layer_action.setEnabled(False)
    
        # 粘贴功能根据剪贴板是否有内容决定
        if self.layer_clipboard:
            self.paste_layer_action.setEnabled(True)
        else:
            self.paste_layer_action.setEnabled(False)

    def update_document_info(self):
        """更新文档信息显示"""
        # 更新标签页名称
        current_index = self.tab_widget.currentIndex()
        self.update_tab_name(current_index)
    
        # 更新窗口标题
        self.update_window_title()
    
        # 更新状态栏尺寸信息
        if self.document and hasattr(self.document, 'canvas_width') and hasattr(self.document, 'canvas_height'):
            if self.document.canvas_width > 0 and self.document.canvas_height > 0:
                self.size_label.setText(f"大小: {self.document.canvas_width} x {self.document.canvas_height}")
        else:
            self.size_label.setText("大小: 0 x 0")

    def align_layers(self, align_type):
        """对齐图层方法"""
        if hasattr(self, 'layer_panel') and self.document:
            # 使用新的图层面板方法（如果存在）
            if hasattr(self.layer_panel, 'enhanced_panel'):
                try:
                    # 目前增强面板没有align_layers方法，先跳过
                    print(f"图层对齐功能暂未支持: {align_type}")
                    pass
                except Exception as e:
                    print(f"图层对齐失败: {e}")
            elif hasattr(self.layer_panel, 'align_layers'):
                self.layer_panel.align_layers(align_type)

    def resize_canvas(self):
        """修改画布尺寸"""
        # 检查是否有打开的文档
        if not self.document:
            QMessageBox.warning(self, "警告", "没有打开的文档，请先创建或打开一个文档。")
            return
    
        # 创建一个对话框来输入新的尺寸
        dialog = QDialog(self)
        dialog.setWindowTitle("修改画布尺寸")
        dialog.setMinimumWidth(300)
    
        layout = QVBoxLayout()
    
        # 尺寸输入
        form_layout = QFormLayout()
    
        width_spinbox = QSpinBox()
        width_spinbox.setRange(1, 10000)
        width_spinbox.setValue(self.document.canvas_width)
        width_spinbox.setSuffix("px")
    
        height_spinbox = QSpinBox()
        height_spinbox.setRange(1, 10000)
        height_spinbox.setValue(self.document.canvas_height)
        height_spinbox.setSuffix("px")
    
        form_layout.addRow("宽度:", width_spinbox)
        form_layout.addRow("高度:", height_spinbox)
    
        layout.addLayout(form_layout)
    
        # 按钮
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
    
        layout.addWidget(buttons)
        dialog.setLayout(layout)
    
        # 显示对话框
        if dialog.exec() == QDialog.Accepted:
            # 获取新的尺寸
            new_width = width_spinbox.value()
            new_height = height_spinbox.value()
        
            # 检查尺寸是否有变化
            if new_width == self.document.canvas_width and new_height == self.document.canvas_height:
                return
        
            # 保存当前状态
            self.document.save_state("修改画布尺寸前")
        
            # 记录原始尺寸
            old_width = self.document.canvas_width
            old_height = self.document.canvas_height
        
            # 更新画布尺寸
            self.document.canvas_width = new_width
            self.document.canvas_height = new_height
        
            # 计算缩放因子
            width_scale = new_width / old_width
            height_scale = new_height / old_height
        
            # 询问是否调整图层位置和大小
            adjust_layers = QMessageBox.question(
                self,
                "调整图层",
                "是否要调整图层位置和大小以适应新的画布尺寸？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes
            ) == QMessageBox.Yes
        
            if adjust_layers:
                # 调整所有图层的位置和大小
                for layer in self.document.layers:
                    # 调整位置
                    layer.x = int(layer.x * width_scale)
                    layer.y = int(layer.y * height_scale)
                
                    # 调整大小
                    layer.width = int(layer.width * width_scale)
                    layer.height = int(layer.height * height_scale)
                
                    # 清除缓存的图像，强制重新加载
                    if hasattr(self, 'layer_panel'):
                        # 清理图层缓存（如果支持）
                        if hasattr(self.layer_panel, 'enhanced_panel'):
                            try:
                                # 目前增强面板没有clear_layer_cache方法，用替代方案
                                if hasattr(layer, '_cached_image'):
                                    layer._cached_image = None
                                if hasattr(layer, 'cached_image'):
                                    layer.cached_image = None
                            except Exception:
                                pass
                        elif hasattr(self.layer_panel, 'clear_layer_cache'):
                            self.layer_panel.clear_layer_cache(layer)
                    else:
                        # 兼容原来的代码，统一处理缓存命名差异
                        if hasattr(layer, '_cached_image'):
                            layer._cached_image = None
                        if hasattr(layer, 'cached_image'):
                            layer.cached_image = None

                    # 标记文档需要缓存刷新
                    if hasattr(self.document, '_needs_cache_refresh'):
                        self.document._needs_cache_refresh = True
        
            # 保存状态并触发更新
            self.document.save_state("修改画布尺寸后")
            self.document.document_changed.emit()
        
            # 更新状态栏显示的尺寸
            self.size_label.setText(f"大小: {new_width} x {new_height}")
        
            # 刷新画布
            active_tab = self.tab_widget.currentWidget()
            if active_tab and hasattr(active_tab, 'canvas'):
                active_tab.canvas.update()

    def _create_align_icon(self, align_type):
        """创建对齐图标"""
        size = 24
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.transparent)
    
        from PySide6.QtGui import QPainter, QPen, QBrush
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing, True)
    
        # 设置画笔和画刷
        canvas_pen = QPen(QColor(80, 80, 80))
        canvas_pen.setWidth(1)
    
        layer_pen = QPen(QColor(40, 40, 40))
        layer_pen.setWidth(1)
    
        # PS风格的蓝色
        layer_brush = QBrush(QColor(38, 128, 235))
    
        # 绘制画布边框 (浅灰色描边的矩形)
        painter.setPen(canvas_pen)
        canvas_rect = QRect(2, 2, size - 4, size - 4)
        painter.drawRect(canvas_rect)
    
        # 设置图层画笔和画刷
        painter.setPen(layer_pen)
        painter.setBrush(layer_brush)
    
        # 根据对齐类型绘制不同的图层表示
        if align_type == "left":
            # 左对齐: 蓝色矩形靠左
            layer_rect = QRect(4, 6, (size - 10) // 2, size - 12)
    
        elif align_type == "hcenter":
            # 水平居中: 较窄的蓝色矩形水平居中
            layer_rect = QRect(0, 6, size - 14, size - 12)
            layer_rect.moveCenter(QPoint(canvas_rect.center().x(), layer_rect.center().y()))
    
        elif align_type == "right":
            # 右对齐: 蓝色矩形靠右
            layer_rect = QRect(size - (size - 10) // 2 - 4, 6, (size - 10) // 2, size - 12)
    
        elif align_type == "top":
            # 顶部对齐: 蓝色矩形靠顶
            layer_rect = QRect(6, 4, size - 12, (size - 10) // 2)
    
        elif align_type == "vcenter":
            # 垂直居中: 较矮的蓝色矩形垂直居中
            layer_rect = QRect(6, 0, size - 12, size - 14)
            layer_rect.moveCenter(QPoint(layer_rect.center().x(), canvas_rect.center().y()))
    
        elif align_type == "bottom":
            # 底部对齐: 蓝色矩形靠底
            layer_rect = QRect(6, size - (size - 10) // 2 - 4, size - 12, (size - 10) // 2)
    
        elif align_type == "center":
            # 完全居中: 小一些的蓝色矩形居中
            layer_rect = QRect(0, 0, size - 10, size - 10)
            layer_rect.moveCenter(canvas_rect.center())
    
        elif align_type == "same_size":
            # 匹配大小: 与画布几乎相同大小的蓝色矩形
            layer_rect = QRect(4, 4, size - 8, size - 8)

        elif align_type == "distribute_horizontal":
            layer_rect = None
            small_brush = QBrush(QColor(38, 128, 235))
            painter.setBrush(small_brush)
            for x in (5, 10, 15):
                painter.drawRect(QRect(x, 8, 4, 8))
            line_pen = QPen(QColor(220, 220, 220, 180))
            line_pen.setWidth(1)
            painter.setPen(line_pen)
            painter.drawLine(7, 18, 17, 18)

        elif align_type == "distribute_vertical":
            layer_rect = None
            small_brush = QBrush(QColor(38, 128, 235))
            painter.setBrush(small_brush)
            for y in (5, 10, 15):
                painter.drawRect(QRect(8, y, 8, 4))
            line_pen = QPen(QColor(220, 220, 220, 180))
            line_pen.setWidth(1)
            painter.setPen(line_pen)
            painter.drawLine(18, 7, 18, 17)
        else:
            layer_rect = QRect(6, 6, size - 12, size - 12)
    
        # 绘制图层
        if layer_rect is not None:
            painter.drawRect(layer_rect)
    
        # 添加指示线条（PS风格）
        if align_type == "left" or align_type == "hcenter" or align_type == "right":
            # 水平方向的对齐添加垂直参考线
            line_pen = QPen(QColor(220, 220, 220, 180))
            line_pen.setWidth(1)
            painter.setPen(line_pen)
        
            if align_type == "left":
                # 左侧垂直线
                painter.drawLine(4, 2, 4, size - 3)
            elif align_type == "hcenter":
                # 中间垂直线
                mid_x = canvas_rect.center().x()
                painter.drawLine(mid_x, 2, mid_x, size - 3)
            elif align_type == "right":
                # 右侧垂直线
                painter.drawLine(size - 5, 2, size - 5, size - 3)
            
        elif align_type == "top" or align_type == "vcenter" or align_type == "bottom":
            # 垂直方向的对齐添加水平参考线
            line_pen = QPen(QColor(220, 220, 220, 180))
            line_pen.setWidth(1)
            painter.setPen(line_pen)
        
            if align_type == "top":
                # 顶部水平线
                painter.drawLine(2, 4, size - 3, 4)
            elif align_type == "vcenter":
                # 中间水平线
                mid_y = canvas_rect.center().y()
                painter.drawLine(2, mid_y, size - 3, mid_y)
            elif align_type == "bottom":
                # 底部水平线
                painter.drawLine(2, size - 5, size - 3, size - 5)
    
        elif align_type == "center":
            # 中心对齐添加十字参考线
            line_pen = QPen(QColor(220, 220, 220, 180))
            line_pen.setWidth(1)
            painter.setPen(line_pen)
        
            mid_x = canvas_rect.center().x()
            mid_y = canvas_rect.center().y()
            painter.drawLine(mid_x, 2, mid_x, size - 3)  # 垂直线
            painter.drawLine(2, mid_y, size - 3, mid_y)  # 水平线
        
        painter.end()
    
        return QIcon(pixmap)

    def select_all_layers(self):
        """全选图层 (Ctrl+A)"""
        if not self.document or not self.document.layers:
            return
        
        # 在当前的单选模式下，全选的含义是选择最顶层的图层
        # 或者可以在UI上提供视觉反馈表示"全选"状态
        top_layer_index = len(self.document.layers) - 1
        self.document.select_layer(top_layer_index)
    
        # 提供用户反馈
        if hasattr(self, 'statusbar'):
            self.statusBar().showMessage(f"已选择顶层图层 ({len(self.document.layers)}个图层)", 2000)

    def rename_layer(self):
        """重命名图层 (F2)"""
        if not self.document or self.document.selected_layer_index < 0:
            return
        
        current_layer = self.document.layers[self.document.selected_layer_index]
    
        # 使用输入对话框获取新名称
        new_name, ok = QInputDialog.getText(
            self, 
            "重命名图层", 
            "图层名称:", 
            text=current_layer.name
        )
    
        if ok and new_name.strip() and new_name != current_layer.name:
            # 保存状态
            self.document.save_state("重命名图层前")
        
            # 更新图层名称
            current_layer.name = new_name.strip()
        
            # 触发文档更新
            self.document.document_changed.emit()
            self.document.layer_changed.emit()
        
            # 保存新状态
            self.document.save_state("重命名图层")
        
            # 提供用户反馈
            if hasattr(self, 'statusbar'):
                self.statusBar().showMessage(f"图层已重命名为 '{new_name.strip()}'", 2000)

    def edit_text_layer(self, layer_index=None):
        """打开文字图层文案编辑器。"""
        if not self.document or not getattr(self.document, 'layers', None):
            return False

        if layer_index is None:
            layer_index = getattr(self.document, 'selected_layer_index', -1)
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return False

        layer = self.document.layers[layer_index]
        from app.models.text_layer import TextLayer
        if not isinstance(layer, TextLayer):
            QMessageBox.information(self, "编辑文案", "请先选择文字图层")
            return False

        if hasattr(self.document, 'select_layers'):
            self.document.select_layers([layer_index], primary_index=layer_index)
        else:
            self.document.select_layer(layer_index)

        if hasattr(self, 'properties_dock'):
            self.properties_dock.show()
            self.properties_dock.raise_()

        panel = getattr(self, 'properties_panel', None)
        if panel:
            panel.layer_selected(layer_index)
            text_panel = getattr(panel, 'text_layer_panel', None)
            if text_panel:
                text_panel.set_text_layer(layer)
                integrated_panel = getattr(text_panel, 'integrated_panel', None)
                if integrated_panel and hasattr(integrated_panel, 'open_text_editor'):
                    integrated_panel.open_text_editor()
                    return True

        QMessageBox.warning(self, "编辑文案", "无法打开文字编辑器")
        return False

    def copy_layer_style(self):
        result = self.layer_controller.copy_layer_style()
        if hasattr(self, 'paste_layer_style_action') and result and self.layer_style_clipboard:
            self.paste_layer_style_action.setEnabled(True)
        return result

    def paste_layer_style(self):
        return self.layer_controller.paste_layer_style()

    def save_window_state(self):
        """保存窗口状态（大小、位置、停靠窗口布局等）"""
        try:
            settings = QSettings("批图王", "批图王")
        
            # 保存窗口几何信息（位置和大小）
            settings.setValue("window/geometry", self.saveGeometry())
        
            # 保存窗口状态（停靠窗口、工具栏等的布局）
            settings.setValue("window/state", self.saveState())
        
            # 保存窗口是否最大化
            settings.setValue("window/maximized", self.isMaximized())
        
            # 保存停靠窗口的可见性状态
            if hasattr(self, 'layer_dock'):
                settings.setValue("docks/layer_dock_visible", self.layer_dock.isVisible())
            if hasattr(self, 'properties_dock'):
                settings.setValue("docks/properties_dock_visible", self.properties_dock.isVisible())
            if hasattr(self, 'properties_panel') and hasattr(self.properties_panel, 'save_module_layout'):
                self.properties_panel.save_module_layout()
        
            print("[INFO] 窗口状态已保存")
        
        except Exception as e:
            print(f"[WARNING] 保存窗口状态时出错: {e}")

    def restore_window_state(self):
        """恢复窗口状态（大小、位置、停靠窗口布局等）"""
        try:
            settings = QSettings("批图王", "批图王")
        
            # 恢复窗口几何信息（位置和大小）
            geometry = settings.value("window/geometry")
            if geometry:
                self.restoreGeometry(geometry)
                print("[INFO] 窗口位置和大小已恢复")
            else:
                # 如果没有保存的状态，使用默认位置（居中显示）
                self.center_window()
                print("[INFO] 使用默认窗口位置")
        
            # 恢复窗口状态（停靠窗口、工具栏等的布局）
            window_state = settings.value("window/state")
            if window_state:
                self.restoreState(window_state)
                print("[INFO] 窗口布局已恢复")
                self.apply_compact_dock_layout()
        
            # 恢复窗口最大化状态
            is_maximized = settings.value("window/maximized", False, type=bool)
            if is_maximized:
                self.showMaximized()
                print("[INFO] 窗口最大化状态已恢复")
        
            # 恢复停靠窗口的可见性状态
            if hasattr(self, 'layer_dock'):
                layer_dock_visible = settings.value("docks/layer_dock_visible", True, type=bool)
                self.layer_dock.setVisible(layer_dock_visible)
        
            if hasattr(self, 'properties_dock'):
                properties_dock_visible = settings.value("docks/properties_dock_visible", True, type=bool)
                self.properties_dock.setVisible(properties_dock_visible)
            
        except Exception as e:
            print(f"[WARNING] 恢复窗口状态时出错: {e}")
            # 如果恢复失败，使用默认位置
            self.center_window()

    def center_window(self):
        """将窗口居中显示"""
        try:
            # 获取屏幕几何信息
            screen = self.screen()
            if screen:
                screen_geometry = screen.availableGeometry()
                window_geometry = self.frameGeometry()
            
                # 计算居中位置
                center_point = screen_geometry.center()
                window_geometry.moveCenter(center_point)
            
                # 移动窗口到居中位置
                self.move(window_geometry.topLeft())
                print("[INFO] 窗口已居中显示")
        
        except Exception as e:
            print(f"[WARNING] 居中显示窗口时出错: {e}")
