# -*- coding: utf-8 -*-
"""Main window components."""

from PySide6.QtWidgets import (
    QMainWindow, QDockWidget, QFileDialog, QVBoxLayout, QWidget, QMenu, QToolBar,
    QSplitter, QLabel, QSpinBox, QHBoxLayout, QPushButton, QMessageBox, QInputDialog,
    QTabWidget, QTabBar, QDialog, QFormLayout, QDialogButtonBox, QSizePolicy, QLineEdit,
)
from PySide6.QtCore import Qt, QSize, QPoint, QRect, QSettings, QTimer
from PySide6.QtGui import QIcon, QColor, QAction, QCloseEvent, QKeySequence, QPixmap
from app.ui.canvas import CanvasWidget
from app.main_window_ui import MainWindowUi
from app.main_window_tabs import MainWindowTabs
from app.main_window_actions import MainWindowActions
from app.main_window_presets import MainWindowPresets
from app.main_window_misc import MainWindowMisc
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

# 保留原模块级常量，兼容外部对 app.main_window.ICON_PATH 的引用
ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "resources")

class MainWindow(QMainWindow, MainWindowUi, MainWindowTabs, MainWindowActions, MainWindowPresets, MainWindowMisc):
    @property
    def document(self):
        manager = getattr(self, "document_manager", None)
        if manager is not None:
            try:
                active = manager.get_active_document()
                if active is not None:
                    return active
            except Exception:
                pass
        return getattr(self, "_document", None)

    @document.setter
    def document(self, value):
        self._document = value

    def current_document(self):
        """Canonical current-document accessor for new code."""
        return self.document

    def __init__(self):
        super().__init__()
        
        # 创建文档管理器（替代单个document）
        self.document_manager = DocumentManager()
        
        # 保留一个document引用，指向当前活动文档，保持与现有代码兼容
        self.document = None
        
        self.preset_manager = PresetManager()
        self._current_editing_preset_id = None
        self._current_editing_preset_name = ""
        self._current_editing_preset_description = ""
        
        # 初始化文档控制器
        from app.controllers.document_controller import DocumentController
        self.document_controller = DocumentController(self)
        
        # 初始化图层控制器
        from app.controllers.layer_controller import LayerController
        self.layer_controller = LayerController(self)
        
        # 图层剪贴板 - 用于复制粘贴功能 (保留兼容性，但将使用LayerController的)
        self.layer_clipboard = None
        
        # 图层样式剪贴板 - 用于复制粘贴图层样式
        self.layer_style_clipboard = None

        # 每个文档一个批量导出窗口（按文档隔离，避免全程序共享同一窗口）
        self._batch_export_dialogs_by_doc = {}
        # 每个文档一个多标签导出窗口（按发起文档隔离）
        self._multi_tab_export_dialogs_by_doc = {}
        self._ai_asset_studio_dialog = None
        # 每个文档的运行状态文本（用于标签页状态展示）
        self._document_runtime_status_by_id = {}
        
        self.setup_ui()
        self.create_actions()
        self.create_toolbar()
        self.create_menubar()
        self.create_statusbar()
        
        # 连接信号
        self.connect_signals()
        
        self.setWindowTitle("图像批量合成工具")
        
        # 创建停靠窗口
        self.create_dock_widgets()
        
        # 设置默认窗口大小和位置
        self.resize(1200, 800)
        
        # 恢复窗口状态（大小、位置、停靠窗口布局）
        self.restore_window_state()
        QTimer.singleShot(0, self.apply_compact_dock_layout)
