# -*- coding: utf-8 -*-
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
"""Main window components."""

from PySide6.QtWidgets import (
    QMainWindow, QDockWidget, QFileDialog, QVBoxLayout, QWidget, QMenu, QToolBar,
    QSplitter, QLabel, QSpinBox, QHBoxLayout, QPushButton, QMessageBox, QInputDialog,
    QTabWidget, QTabBar, QDialog, QFormLayout, QDialogButtonBox, QSizePolicy, QLineEdit,
)
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

# 模块级 UI 布局常量（原 main_window.py 顶层常量，随 UI 职责归入本 mixin 文件）
ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "resources")
COMPACT_LAYER_DOCK_WIDTH = 180
COMPACT_PROPERTIES_DOCK_WIDTH = 220
COMPACT_LAYER_DOCK_MIN_WIDTH = 145
COMPACT_PROPERTIES_DOCK_MIN_WIDTH = 180

class MainWindowUi(object):
    def setup_ui(self):
        """设置主界面UI"""
        self.central_widget = QWidget()
        self.setCentralWidget(self.central_widget)
    
        # 创建主布局
        self.main_layout = QVBoxLayout(self.central_widget)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)
    
        # 创建标签页控件
        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)  # 标签可关闭
        self.tab_widget.tabCloseRequested.connect(self.close_tab)
        self.tab_widget.currentChanged.connect(self.tab_changed)
    
        # 设置标签栏样式，类似Photoshop
        self.tab_widget.setDocumentMode(True)  # 文档模式，标签看起来更紧凑
        self.tab_widget.tabBar().setExpanding(False)  # 标签不会扩展填满整个宽度
        self.tab_widget.tabBar().setDrawBase(True)  # 绘制标签栏底部线条
        self.tab_widget.tabBar().setUsesScrollButtons(True)
    
        # 添加标签页右键菜单
        self.tab_widget.tabBar().setContextMenuPolicy(Qt.CustomContextMenu)
        self.tab_widget.tabBar().customContextMenuRequested.connect(self.show_tab_context_menu)
    
        self.main_layout.addWidget(self.tab_widget)

    def create_actions(self):
        """创建操作"""
        # 文件菜单操作
        self.new_action = QAction("新建", self)
        self.new_action.setShortcut(QKeySequence.New)
        self.new_action.triggered.connect(self.new_document)
    
        self.open_action = QAction("打开", self)
        self.open_action.setShortcut(QKeySequence.Open)
        self.open_action.triggered.connect(self.open_document)
    
        self.save_action = QAction("保存", self)
        self.save_action.setShortcut(QKeySequence.Save)
        self.save_action.triggered.connect(self.save_document)
    
        self.save_as_action = QAction("另存为", self)
        self.save_as_action.setShortcut(QKeySequence.SaveAs)
        self.save_as_action.triggered.connect(self.save_document_as)
    
        self.close_tab_action = QAction("关闭当前标签", self)
        self.close_tab_action.setShortcut(QKeySequence("Ctrl+W"))
        self.close_tab_action.triggered.connect(lambda: self.close_tab(self.tab_widget.currentIndex()))
    
        self.duplicate_tab_action = QAction("复制当前标签", self)
        self.duplicate_tab_action.setShortcut(QKeySequence("Ctrl+D"))
        self.duplicate_tab_action.triggered.connect(self.duplicate_tab)
    
        self.export_action = QAction("导出", self)
        self.export_action.setShortcut("Ctrl+E")
        self.export_action.triggered.connect(self.export_image)
    
        self.batch_export_action = QAction("批量导出", self)
        self.batch_export_action.triggered.connect(self.batch_export)
    
        # 添加多标签页批量导出操作
        self.multi_tab_export_action = QAction("多标签页批量导出", self)
        self.multi_tab_export_action.setShortcut("Ctrl+Shift+E")
        self.multi_tab_export_action.triggered.connect(self.multi_tab_export)
    
        self.exit_action = QAction("退出", self)
        self.exit_action.setShortcut(QKeySequence.Quit)
        self.exit_action.triggered.connect(self.close)
    
        # 预设菜单操作
        self.preset_store_action = QAction("预设中心", self)
        self.preset_store_action.setShortcut("Ctrl+P")
        self.preset_store_action.triggered.connect(self.open_preset_store)

        self.save_as_preset_action = QAction("保存为预设", self)
        self.save_as_preset_action.triggered.connect(self.save_as_preset)
    
        self.load_preset_action = QAction("加载预设", self)
        self.load_preset_action.triggered.connect(self.load_preset)
    
        self.manage_presets_action = QAction("管理预设", self)
        self.manage_presets_action.triggered.connect(self.manage_presets)
    
        # 编辑菜单操作
        self.undo_action = QAction("撤销", self)
        self.undo_action.setShortcut(QKeySequence.Undo)
        self.undo_action.triggered.connect(self.undo)
        self.undo_action.setEnabled(False)
    
        self.redo_action = QAction("重做", self)
        self.redo_action.setShortcut(QKeySequence.Redo)
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)
    
        # 调整画布大小
        self.resize_canvas_action = QAction("修改画布尺寸", self)
        self.resize_canvas_action.setShortcut("Ctrl+R")
        self.resize_canvas_action.triggered.connect(self.resize_canvas)
    
        # 画布预设管理
        self.manage_canvas_presets_action = QAction("画布预设管理", self)
        self.manage_canvas_presets_action.triggered.connect(self.manage_canvas_presets)
    
        # 视图菜单操作
        self.zoom_in_action = QAction("放大", self)
        self.zoom_in_action.setShortcut("Ctrl++")
        self.zoom_in_action.triggered.connect(self.zoom_in)
    
        self.zoom_out_action = QAction("缩小", self)
        self.zoom_out_action.setShortcut("Ctrl+-")
        self.zoom_out_action.triggered.connect(self.zoom_out)
    
        self.zoom_reset_action = QAction("重置缩放", self)
        self.zoom_reset_action.setShortcut("Ctrl+0")
        self.zoom_reset_action.triggered.connect(self.zoom_reset)
    
        # 图层菜单操作
        self.add_layer_action = QAction("添加图层", self)
        self.add_layer_action.setShortcut("Ctrl+L")
        self.add_layer_action.triggered.connect(self.add_layer)
    
        self.add_text_layer_action = QAction("添加文字图层", self)
        self.add_text_layer_action.setShortcut("Ctrl+T")
        self.add_text_layer_action.triggered.connect(self.add_text_layer)

        self.ai_asset_studio_action = QAction("AI接口设置", self)
        self.ai_asset_studio_action.triggered.connect(self.open_ai_asset_studio)
    
        self.delete_layer_action = QAction("删除图层", self)
        self.delete_layer_action.setShortcut("Delete")
        self.delete_layer_action.triggered.connect(self.delete_layer)
    
        # 图层复制粘贴操作
        self.copy_layer_action = QAction("复制图层", self)
        self.copy_layer_action.setShortcut("Ctrl+C")
        self.copy_layer_action.triggered.connect(self.copy_layer)
    
        self.paste_layer_action = QAction("粘贴图层", self)
        self.paste_layer_action.setShortcut("Ctrl+V")
        self.paste_layer_action.triggered.connect(self.paste_layer)
        self.paste_layer_action.setEnabled(False)  # 初始状态禁用
    
        self.move_layer_up_action = QAction("上移图层", self)
        self.move_layer_up_action.setShortcut("Ctrl+Up")
        self.move_layer_up_action.triggered.connect(self.move_layer_up)
    
        self.move_layer_down_action = QAction("下移图层", self)
        self.move_layer_down_action.setShortcut("Ctrl+Down")
        self.move_layer_down_action.triggered.connect(self.move_layer_down)
    
        # 新增标准快捷键操作
        self.select_all_layers_action = QAction("全选图层", self)
        self.select_all_layers_action.setShortcut("Ctrl+A")
        self.select_all_layers_action.triggered.connect(self.select_all_layers)
    
        self.rename_layer_action = QAction("重命名图层", self)
        self.rename_layer_action.setShortcut("F2")
        self.rename_layer_action.triggered.connect(self.rename_layer)
    
        # 图层样式复制粘贴（扩展功能）
        self.copy_layer_style_action = QAction("复制图层样式", self)
        self.copy_layer_style_action.setShortcut("Ctrl+Shift+C")
        self.copy_layer_style_action.triggered.connect(self.copy_layer_style)
    
        self.paste_layer_style_action = QAction("粘贴图层样式", self)
        self.paste_layer_style_action.setShortcut("Ctrl+Shift+V")
        self.paste_layer_style_action.triggered.connect(self.paste_layer_style)
        self.paste_layer_style_action.setEnabled(False)  # 初始状态禁用
    
        # 图层对齐操作 - 仅用于工具栏，不在菜单中显示
        self.align_left_action = QAction("左对齐到画板", self)
        self.align_left_action.setIcon(self._create_align_icon("left"))
        self.align_left_action.triggered.connect(lambda: self.align_layers("left"))
    
        self.align_hcenter_action = QAction("水平居中于画板", self)
        self.align_hcenter_action.setIcon(self._create_align_icon("hcenter"))
        self.align_hcenter_action.triggered.connect(lambda: self.align_layers("hcenter"))
    
        self.align_right_action = QAction("右对齐到画板", self)
        self.align_right_action.setIcon(self._create_align_icon("right"))
        self.align_right_action.triggered.connect(lambda: self.align_layers("right"))
    
        self.align_top_action = QAction("顶部对齐到画板", self)
        self.align_top_action.setIcon(self._create_align_icon("top"))
        self.align_top_action.triggered.connect(lambda: self.align_layers("top"))
    
        self.align_vcenter_action = QAction("垂直居中于画板", self)
        self.align_vcenter_action.setIcon(self._create_align_icon("vcenter"))
        self.align_vcenter_action.triggered.connect(lambda: self.align_layers("vcenter"))
    
        self.align_bottom_action = QAction("底部对齐到画板", self)
        self.align_bottom_action.setIcon(self._create_align_icon("bottom"))
        self.align_bottom_action.triggered.connect(lambda: self.align_layers("bottom"))

        self.distribute_horizontal_action = QAction("水平等距分布", self)
        self.distribute_horizontal_action.setIcon(self._create_align_icon("distribute_horizontal"))
        self.distribute_horizontal_action.triggered.connect(lambda: self.align_layers("distribute_horizontal"))

        self.distribute_vertical_action = QAction("垂直等距分布", self)
        self.distribute_vertical_action.setIcon(self._create_align_icon("distribute_vertical"))
        self.distribute_vertical_action.triggered.connect(lambda: self.align_layers("distribute_vertical"))
    
        self.center_action = QAction("完全居中于画板", self)
        self.center_action.setIcon(self._create_align_icon("center"))
        self.center_action.triggered.connect(lambda: self.align_layers("center"))
    
        self.same_size_action = QAction("完全匹配画板大小", self)
        self.same_size_action.setIcon(self._create_align_icon("same_size"))
        self.same_size_action.triggered.connect(lambda: self.align_layers("same_size"))

    def create_menubar(self):
        """创建菜单栏"""
        self.menubar = self.menuBar()
    
        # 文件菜单
        file_menu = self.menubar.addMenu("文件")
        file_menu.addAction(self.new_action)
        file_menu.addAction(self.open_action)
        file_menu.addSeparator()
        file_menu.addAction(self.save_action)
        file_menu.addAction(self.save_as_action)
        file_menu.addSeparator()
        file_menu.addAction(self.close_tab_action)
        file_menu.addAction(self.duplicate_tab_action)
        file_menu.addSeparator()
        file_menu.addAction(self.export_action)
        file_menu.addAction(self.batch_export_action)
        file_menu.addAction(self.multi_tab_export_action)
        file_menu.addSeparator()
        file_menu.addAction(self.exit_action)
    
        # 预设菜单
        preset_menu = self.menubar.addMenu("预设")
        preset_menu.addAction(self.preset_store_action)
        preset_menu.addSeparator()
        preset_menu.addAction(self.save_as_preset_action)
        preset_menu.addAction(self.load_preset_action)
        preset_menu.addAction(self.manage_presets_action)
    
        # 编辑菜单
        edit_menu = self.menubar.addMenu("编辑")
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        edit_menu.addAction(self.resize_canvas_action)
    
        # 工具菜单
        tools_menu = self.menubar.addMenu("工具")
        tools_menu.addAction(self.manage_canvas_presets_action)
    
        # 视图菜单
        view_menu = self.menubar.addMenu("视图")
        view_menu.addAction(self.zoom_in_action)
        view_menu.addAction(self.zoom_out_action)
        view_menu.addAction(self.zoom_reset_action)
        view_menu.addSeparator()
    
        # 添加工具栏显示选项
        view_menu.addAction(self.main_toolbar.toggleViewAction())
        view_menu.addAction(self.align_toolbar.toggleViewAction())
    
        # 图层菜单
        layer_menu = self.menubar.addMenu("图层")
        layer_menu.addAction(self.add_layer_action)
        layer_menu.addAction(self.add_text_layer_action)
        layer_menu.addAction(self.ai_asset_studio_action)
        layer_menu.addAction(self.delete_layer_action)
        layer_menu.addSeparator()
        layer_menu.addAction(self.select_all_layers_action)
        layer_menu.addAction(self.rename_layer_action)
        layer_menu.addSeparator()
        layer_menu.addAction(self.copy_layer_action)
        layer_menu.addAction(self.paste_layer_action)
        layer_menu.addAction(self.copy_layer_style_action)
        layer_menu.addAction(self.paste_layer_style_action)
        layer_menu.addSeparator()
        layer_menu.addAction(self.move_layer_up_action)
        layer_menu.addAction(self.move_layer_down_action)

    def create_toolbar(self):
        """创建工具栏"""
        # 主工具栏
        self.main_toolbar = QToolBar("主工具栏", self)
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setIconSize(QSize(18, 18))
        self.main_toolbar.setFloatable(False)
        self.main_toolbar.setAllowedAreas(Qt.TopToolBarArea)
        self.main_toolbar.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
    
        self.main_toolbar.addAction(self.new_action)
        self.main_toolbar.addAction(self.open_action)
        self.main_toolbar.addAction(self.save_action)
        self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.undo_action)
        self.main_toolbar.addAction(self.redo_action)
        self.main_toolbar.addSeparator()
        # 移除缩放按钮 - 用户可通过快捷键或状态栏控制缩放
        # self.main_toolbar.addAction(self.zoom_in_action)
        # self.main_toolbar.addAction(self.zoom_out_action)
        # self.main_toolbar.addAction(self.zoom_reset_action)
        # self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.add_layer_action)
        self.main_toolbar.addAction(self.add_text_layer_action)
        self.main_toolbar.addAction(self.ai_asset_studio_action)
        self.main_toolbar.addAction(self.delete_layer_action)
        self.main_toolbar.addSeparator()
        # 移除复制粘贴图层按钮 - 用户可通过快捷键或右键菜单使用
        # self.main_toolbar.addAction(self.copy_layer_action)
        # self.main_toolbar.addAction(self.paste_layer_action)
        # self.main_toolbar.addSeparator()
        self.main_toolbar.addAction(self.batch_export_action)
        self.main_toolbar.addAction(self.multi_tab_export_action)
        self.main_toolbar.addAction(self.preset_store_action)
    
        self.addToolBar(self.main_toolbar)
    
        # 创建对齐工具栏
        self.align_toolbar = QToolBar("对齐工具栏", self)
        self.align_toolbar.setMovable(False)
        self.align_toolbar.setIconSize(QSize(18, 18))
        self.align_toolbar.setFloatable(False)
        self.align_toolbar.setAllowedAreas(Qt.TopToolBarArea)
        self.align_toolbar.setToolButtonStyle(Qt.ToolButtonIconOnly)
    
        self.align_toolbar.addAction(self.align_left_action)
        self.align_toolbar.addAction(self.align_hcenter_action)
        self.align_toolbar.addAction(self.align_right_action)
        self.align_toolbar.addSeparator()
        self.align_toolbar.addAction(self.align_top_action)
        self.align_toolbar.addAction(self.align_vcenter_action)
        self.align_toolbar.addAction(self.align_bottom_action)
        self.align_toolbar.addSeparator()
        self.align_toolbar.addAction(self.distribute_horizontal_action)
        self.align_toolbar.addAction(self.distribute_vertical_action)
        self.align_toolbar.addSeparator()
        self.align_toolbar.addAction(self.center_action)
        self.align_toolbar.addAction(self.same_size_action)
    
        self.addToolBar(self.align_toolbar)

    def create_statusbar(self):
        """创建状态栏"""
        self.statusbar = self.statusBar()
    
        # 应用状态栏样式
        vh = VisualHierarchy
        statusbar_style = f"""
        QStatusBar {{
            background-color: {vh.get_color('background', 'secondary')};
            border-top: 1px solid {vh.get_color('border', 'divider')};
            color: {vh.get_color('text', 'secondary')};
            font-size: {vh.FONTS['small']['size']}px;
            min-height: 20px;
        }}
        QStatusBar::item {{
            border: none;
        }}
        """
        self.statusbar.setStyleSheet(statusbar_style)
    
        # 添加文档状态指示器
        self.document_status_indicator = status_manager.create_document_status_indicator(self)
        self.statusbar.addWidget(self.document_status_indicator)
    
        # 添加分隔符
        separator1 = QLabel("|")
        separator1.setStyleSheet(f"color: {vh.get_color('border', 'divider')}; margin: 0 4px;")
        self.statusbar.addPermanentWidget(separator1)
    
        # 添加缩放控件
        zoom_layout = QHBoxLayout()
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(2)
    
        zoom_label = QLabel("缩放:")
        zoom_label.setFont(vh.get_font('small'))
        zoom_label.setStyleSheet(f"color: {vh.get_color('text', 'secondary')};")
    
        self.zoom_spinbox = QSpinBox()
        self.zoom_spinbox.setRange(10, 500)
        self.zoom_spinbox.setValue(100)
        self.zoom_spinbox.setSuffix("%")
        self.zoom_spinbox.setFixedWidth(68)
        self.zoom_spinbox.setFont(vh.get_font('small'))
        self.zoom_spinbox.valueChanged.connect(self.zoom_value_changed)
    
        # 设置缩放控件样式
        spinbox_style = f"""
        QSpinBox {{
            background-color: {vh.get_color('background', 'surface')};
            border: 1px solid {vh.get_color('border', 'secondary')};
            color: {vh.get_color('text', 'primary')};
            border-radius: {vh.get_radius('sm')}px;
            padding: 1px 4px;
        }}
        QSpinBox:focus {{
            border: 1px solid {vh.get_color('border', 'focus')};
        }}
        """
        self.zoom_spinbox.setStyleSheet(spinbox_style)
    
        zoom_layout.addWidget(zoom_label)
        zoom_layout.addWidget(self.zoom_spinbox)
    
        zoom_widget = QWidget()
        zoom_widget.setLayout(zoom_layout)
    
        self.statusbar.addPermanentWidget(zoom_widget)
    
        # 添加分隔符
        separator2 = QLabel("|")
        separator2.setStyleSheet(f"color: {vh.get_color('border', 'divider')}; margin: 0 4px;")
        self.statusbar.addPermanentWidget(separator2)
    
        # 添加坐标显示
        self.position_label = QLabel("坐标: 0, 0")
        self.position_label.setFont(vh.get_font('small'))
        self.position_label.setStyleSheet(f"color: {vh.get_color('text', 'secondary')};")
        self.statusbar.addPermanentWidget(self.position_label)
    
        # 添加分隔符
        separator3 = QLabel("|")
        separator3.setStyleSheet(f"color: {vh.get_color('border', 'divider')}; margin: 0 4px;")
        self.statusbar.addPermanentWidget(separator3)
    
        # 添加文档大小显示
        self.size_label = QLabel("大小: 0 x 0")
        self.size_label.setFont(vh.get_font('small'))
        self.size_label.setStyleSheet(f"color: {vh.get_color('text', 'secondary')};")
        self.statusbar.addPermanentWidget(self.size_label)
    
        # 添加Alt键提示
        self.alt_tip_label = QLabel("提示: 按住Alt键点击图层可避免切换选中图层")
        self.alt_tip_label.setFont(vh.get_font('tiny'))
        self.alt_tip_label.setStyleSheet(f"color: {vh.get_color('text', 'hint')}; font-style: italic; margin-left: 8px;")
        self.statusbar.addWidget(self.alt_tip_label)

    def create_dock_widgets(self):
        """创建停靠窗口"""
        # 图层面板 - 强制使用原始版本确保所有功能正常
        self.layer_dock = QDockWidget("图层", self)
        self.layer_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.layer_dock.setMinimumWidth(COMPACT_LAYER_DOCK_MIN_WIDTH)
    
        # 创建图层面板 - 修复：强制使用原始LayerPanel确保功能完整
        print("[主窗口] 强制使用原始图层面板，确保随机按钮等功能正常")
        self.layer_panel = LayerPanel(self.document)
        self.layer_panel.setMinimumWidth(COMPACT_LAYER_DOCK_MIN_WIDTH - 12)
        self.layer_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        print("[主窗口] 原始图层面板创建完成")
    
        self.layer_dock.setWidget(self.layer_panel)
        self.addDockWidget(Qt.LeftDockWidgetArea, self.layer_dock)
    
        # 图层属性面板
        self.properties_dock = QDockWidget("图层属性", self)
        self.properties_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.properties_dock.setMinimumWidth(COMPACT_PROPERTIES_DOCK_MIN_WIDTH)
        self.properties_panel = LayerPropertiesPanel(self.document)
        self.properties_panel.setMinimumWidth(COMPACT_PROPERTIES_DOCK_MIN_WIDTH - 14)
        self.properties_panel.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Expanding)
        self.properties_dock.setWidget(self.properties_panel)
        self.addDockWidget(Qt.RightDockWidgetArea, self.properties_dock)
        if hasattr(self.properties_panel, "restore_module_layout"):
            self.properties_panel.restore_module_layout()
    
        self.apply_compact_dock_layout()

    def apply_compact_dock_layout(self):
        """收紧默认停靠面板宽度，把水平空间优先留给画布。"""
        if not (hasattr(self, 'layer_dock') and hasattr(self, 'properties_dock')):
            return

        self.resizeDocks(
            [self.layer_dock, self.properties_dock],
            [COMPACT_LAYER_DOCK_WIDTH, COMPACT_PROPERTIES_DOCK_WIDTH],
            Qt.Horizontal
        )
