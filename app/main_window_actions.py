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

class MainWindowActions(object):
    def new_document(self):
        """创建新文档 - 委托给DocumentController"""
        return self.document_controller.new_document()

    def open_document(self):
        """打开文档 - 委托给DocumentController"""
        return self.document_controller.open_document()

    def save_document(self):
        """保存当前文档 - 委托给DocumentController"""
        return self.document_controller.save_document()

    def save_document_as(self):
        """另存为 - 委托给DocumentController"""
        return self.document_controller.save_document_as()

    def export_image(self):
        """导出当前图像"""
        # 先检查文档是否存在
        if not self.document:
            QMessageBox.warning(self, "无法导出", "请先创建或打开文档")
            return
        
        if self.document.canvas_width <= 0 or self.document.canvas_height <= 0:
            QMessageBox.warning(self, "无法导出", "请先创建或打开文档")
            return
        
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出图像", "", 
            "PNG图像 (*.png);;JPEG图像 (*.jpg);;所有文件 (*.*)"
        )
    
        if file_path:
            if self.document.export_image(file_path):
                if hasattr(self, 'statusBar') and self.statusBar():
                    self.statusBar().showMessage(f"导出成功：{file_path}", 8000)
            else:
                if hasattr(self, 'statusBar') and self.statusBar():
                    self.statusBar().showMessage("导出失败：无法导出图像", 8000)

    def batch_export(self):
        """批量导出图像"""
        from app.ui.batch_export_dialog import BatchExportDialog
    
        # 先检查文档是否存在
        if not self.document:
            QMessageBox.warning(self, "无法导出", "请先创建或打开文档")
            return
    
        if self.document.canvas_width <= 0 or self.document.canvas_height <= 0:
            QMessageBox.warning(self, "无法导出", "请先创建或打开文档")
            return
        
        current_index = self.tab_widget.currentIndex()
        current_tab = self.tab_widget.widget(current_index) if current_index >= 0 else None
        tab_name = self.tab_widget.tabText(current_index) if current_index >= 0 else "未命名文档"
        if tab_name.endswith(" *"):
            tab_name = tab_name[:-2]

        doc_key = id(self.document)
        existing_dialog = self._batch_export_dialogs_by_doc.get(doc_key)
        if existing_dialog is not None and (
            existing_dialog.isVisible() or getattr(existing_dialog, "_export_running", False)
        ):
            # 文档已有导出窗口（可见或后台运行）时直接激活
            existing_dialog.show()
            existing_dialog.raise_()
            existing_dialog.activateWindow()
            return

        # 将导出窗口挂在当前标签页上，形成“文档级窗口”语义
        parent_widget = current_tab if current_tab is not None else self
        dialog = BatchExportDialog(self.document, parent_widget)
        dialog.setWindowTitle(f"批量导出图像 - {tab_name}")
        # 改为非模态：导出期间允许继续操作其他标签页/文档
        dialog.setModal(False)
        dialog.setWindowModality(Qt.NonModal)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        self._batch_export_dialogs_by_doc[doc_key] = dialog
    
        def _cleanup_dialog(*_):
            if self._batch_export_dialogs_by_doc.get(doc_key) is dialog:
                self._batch_export_dialogs_by_doc.pop(doc_key, None)
    
        dialog.destroyed.connect(_cleanup_dialog)
        dialog.show()

    def multi_tab_export(self):
        """多标签页批量导出"""
        # 检查是否有标签页打开
        if self.document_manager.get_document_count() == 0:
            QMessageBox.warning(self, "无法导出", "没有打开的标签页")
            return
        
        # 导入选择对话框
        from app.ui.multi_tab_export_dialog import MultiTabExportDialog

        current_index = self.tab_widget.currentIndex()
        current_tab = self.tab_widget.widget(current_index) if current_index >= 0 else None
        tab_name = self.tab_widget.tabText(current_index) if current_index >= 0 else "未命名文档"
        if tab_name.endswith(" *"):
            tab_name = tab_name[:-2]

        doc_key = id(self.document) if self.document is not None else current_index
        existing_dialog = self._multi_tab_export_dialogs_by_doc.get(doc_key)
        if existing_dialog is not None and (
            existing_dialog.isVisible() or getattr(existing_dialog, "_export_started", False)
        ):
            existing_dialog.show()
            existing_dialog.raise_()
            existing_dialog.activateWindow()
            return

        parent_widget = current_tab if current_tab is not None else self
        dialog = MultiTabExportDialog(self.document_manager, parent_widget)
        dialog.setWindowTitle(f"多标签页批量导出 - {tab_name}")
        dialog.setModal(False)
        dialog.setWindowModality(Qt.NonModal)
        dialog.setAttribute(Qt.WA_DeleteOnClose, True)
        self._multi_tab_export_dialogs_by_doc[doc_key] = dialog

        def _cleanup_dialog(*_):
            if self._multi_tab_export_dialogs_by_doc.get(doc_key) is dialog:
                self._multi_tab_export_dialogs_by_doc.pop(doc_key, None)

        dialog.destroyed.connect(_cleanup_dialog)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def undo(self):
        """撤销操作"""
        if self.document:
            self.document.undo()

    def redo(self):
        """重做操作"""
        if self.document:
            self.document.redo()

    def zoom_in(self):
        """放大画布"""
        active_tab = self.tab_widget.currentWidget()
        if active_tab and hasattr(active_tab, 'canvas'):
            active_tab.canvas.zoom_factor *= 1.1
            active_tab.canvas.update()
            self.zoom_spinbox.setValue(int(active_tab.canvas.zoom_factor * 100))

    def zoom_out(self):
        """缩小画布"""
        active_tab = self.tab_widget.currentWidget()
        if active_tab and hasattr(active_tab, 'canvas'):
            active_tab.canvas.zoom_factor /= 1.1
            active_tab.canvas.zoom_factor = max(0.1, min(10.0, active_tab.canvas.zoom_factor))
            active_tab.canvas.update()
            self.zoom_spinbox.setValue(int(active_tab.canvas.zoom_factor * 100))

    def zoom_reset(self):
        """重置画布缩放"""
        active_tab = self.tab_widget.currentWidget()
        if active_tab and hasattr(active_tab, 'canvas'):
            active_tab.canvas.zoom_factor = 1.0
            active_tab.canvas.offset = QPoint(0, 0)
            active_tab.canvas.update()
            self.zoom_spinbox.setValue(100)

    def zoom_value_changed(self, value):
        """缩放值改变时更新画布"""
        active_tab = self.tab_widget.currentWidget()
        if active_tab and hasattr(active_tab, 'canvas'):
            active_tab.canvas.zoom_factor = value / 100.0
            active_tab.canvas.update()

    def add_layer(self):
        """添加新图层 - 委托给LayerController"""
        return self.layer_controller.add_layer()

    def add_text_layer(self):
        """添加新文字图层（弹配置对话框） - 委托给LayerController"""
        return self.layer_controller.add_text_layer()

    def add_quick_text_layer(self):
        """快速添加文字图层（不弹窗，默认样式） - 委托给LayerController。

        对应快捷键 T / 图层菜单「快速文字图层」。
        建好后把焦点交给图层面板，方便用户接着改内容或直接拖位置。
        """
        layer = self.layer_controller.add_quick_text_layer()
        if layer is not None:
            try:
                panel = getattr(self, "layer_panel", None)
                if panel is not None and hasattr(panel, "setFocus"):
                    panel.setFocus()
            except Exception:
                pass
        return layer is not None

    def open_ai_asset_studio(self):
        """Open the AI asset generation dialog."""
        dialog = self._ai_asset_studio_dialog
        if dialog is None:
            from app.ui.ai_asset_studio_dialog import AIAssetStudioDialog

            dialog = AIAssetStudioDialog(self)
            dialog.destroyed.connect(lambda: setattr(self, "_ai_asset_studio_dialog", None))
            self._ai_asset_studio_dialog = dialog

        dialog.show()
        dialog.raise_()
        dialog.activateWindow()

    def delete_layer(self):
        """删除选中的图层 - 委托给LayerController"""
        return self.layer_controller.delete_layer()

    def move_layer_up(self):
        """上移图层 - 委托给LayerController"""
        return self.layer_controller.move_layer_up()

    def move_layer_down(self):
        """下移图层 - 委托给LayerController"""
        return self.layer_controller.move_layer_down()

    def copy_layer(self):
        """复制选中的图层 - 委托给LayerController"""
        return self.layer_controller.copy_layer()

    def paste_layer(self):
        """粘贴复制的图层 - 委托给LayerController"""
        return self.layer_controller.paste_layer()

    def closeEvent(self, event: QCloseEvent):
        """关闭窗口前的未保存确认。

        ## 修复记录（2026-10-27）

        **前置 bug（更严重）**：`MainWindow` 的继承顺序把 `QMainWindow` 排在
        mixin 前面，导致本方法被 `QWidget.closeEvent()` 完全遮蔽 ——
        **从来没执行过**。用户点 X 直接退出，未保存内容静默丢失。
        已通过调整 `MainWindow` 基类顺序修复（见 main_window.py 的说明）。

        本方法自身的三个逻辑缺陷（本次一并修掉）：
        1. 提示写"有未保存的文档"（单数），实际可能多个 → 改为列出数量与名称
        2. 点「保存」时对**所有**文档逐个保存，包括没改动、没文件路径的文档，
           会为每个都弹出「另存为」对话框（实测 3 个文档要弹 3 次）
           → 只保存真正有改动的文档
        3. 循环里逐个文档弹框，但点任何按钮后都 `return`，
           剩下的文档根本没机会被询问 → 改为一次性汇总询问
        """
        dirty = []
        for i in range(self.document_manager.get_document_count()):
            document = self.document_manager.get_document(i)
            if document is not None and getattr(document, "is_modified", False):
                dirty.append((i, self.document_manager.get_document_name(i)))

        if not dirty:
            self.save_window_state()
            event.accept()
            return

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("退出")
        msg_box.setIcon(QMessageBox.Question)

        if len(dirty) == 1:
            msg_box.setText(
                f"文档「{dirty[0][1]}」有未保存的更改，是否在退出前保存？"
            )
        else:
            names = "、".join(f"「{name}」" for _, name in dirty[:5])
            if len(dirty) > 5:
                names += f" 等 {len(dirty)} 个文档"
            msg_box.setText(f"有 {len(dirty)} 个文档未保存：{names}\n\n是否在退出前保存？")

        save_btn = msg_box.addButton("全部保存", QMessageBox.AcceptRole)
        discard_btn = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
        cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.setDefaultButton(save_btn)

        msg_box.exec()
        clicked = msg_box.clickedButton()

        if clicked is save_btn:
            if not self._save_dirty_documents(dirty):
                # 任一文档保存失败或用户取消了另存为 → 放弃退出，避免丢数据
                event.ignore()
                return
            self.save_window_state()
            event.accept()
        elif clicked is discard_btn:
            self.save_window_state()
            event.accept()
        else:
            # 包括取消以及直接关掉对话框（点右上角 X）都视为取消退出
            event.ignore()

    def _save_dirty_documents(self, dirty) -> bool:
        """保存指定的脏文档列表。任一失败则返回 False（调用方应放弃退出）。

        只处理 dirty 里的文档，不碰其它 —— 无改动的文档不需要保存，
        更不该为它们弹「另存为」。
        """
        for index, name in dirty:
            document = self.document_manager.get_document(index)
            if document is None:
                continue
            # 切到该文档再保存：save_document 依赖当前活动文档
            self.tab_widget.setCurrentIndex(index)
            try:
                if not self.save_document():
                    # 用户可能点了「另存为」的取消，或写入失败
                    return False
            except Exception as exc:
                try:
                    self.statusbar.showMessage(
                        f"保存文档「{name}」失败：{exc}", 5000
                    )
                except Exception:
                    pass
                return False
        return True
