from PySide6.QtWidgets import (QMainWindow, QDockWidget, QFileDialog, 
                               QVBoxLayout, QWidget, QMenu, QToolBar, QSplitter,
                               QLabel, QSpinBox, QHBoxLayout, QPushButton, QMessageBox, QInputDialog,
                               QTabWidget, QTabBar, QDialog, QFormLayout, QDialogButtonBox,
                               QSizePolicy, QLineEdit)
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

# 设置图标路径
ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "resources")

COMPACT_LAYER_DOCK_WIDTH = 180
COMPACT_PROPERTIES_DOCK_WIDTH = 220
COMPACT_LAYER_DOCK_MIN_WIDTH = 145
COMPACT_PROPERTIES_DOCK_MIN_WIDTH = 180

class MainWindow(QMainWindow):
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
    
    def connect_signals(self):
        """连接信号与槽"""
        # 连接文档管理器信号
        self.document_manager.active_document_changed.connect(self.active_document_changed)
        self.document_manager.document_name_changed.connect(self.update_tab_name)
        
        # 连接文档控制器信号
        self.document_controller.status_message.connect(self._on_controller_status_message)
        self.document_controller.document_operation_completed.connect(self._on_document_operation_completed)
        
        # 连接图层控制器信号
        self.layer_controller.status_message.connect(self._on_controller_status_message)
        self.layer_controller.layer_operation_completed.connect(self._on_layer_operation_completed)
        self.layer_controller.layer_selection_changed.connect(self._on_layer_selection_changed)
    
    def active_document_changed(self, document):
        """当活动文档变更时"""
        # 先断开旧文档的信号连接
        if hasattr(self, 'document') and self.document:
            try:
                # 断开信号连接
                self.document.history_changed.disconnect(self.update_history_actions)
                self.document.document_changed.disconnect(self.update_document_info)
                # 断开图层选择信号
                if hasattr(self.document, 'layer_selected'):
                    self.document.layer_selected.disconnect(self.update_copy_paste_actions)
            except Exception:
                # 如果信号未连接，会抛出异常，这里忽略
                pass
        
        # 更新document引用
        self.document = document
        
        # 更新面板
        if self.document and hasattr(self, 'layer_panel') and hasattr(self, 'properties_panel'):
            print(f"[主窗口] 开始更新面板，文档有效，图层数量: {len(self.document.layers)}")
            
            # 更新图层面板的文档引用 - 修复：使用set_document方法确保界面更新
            if hasattr(self.layer_panel, 'set_document'):
                print(f"[主窗口] 调用图层面板的set_document方法")
                self.layer_panel.set_document(self.document)
            else:
                print(f"[主窗口] 图层面板没有set_document方法，直接设置document属性")
                self.layer_panel.document = self.document
                # 手动触发更新
                if hasattr(self.layer_panel, 'update_layers'):
                    self.layer_panel.update_layers()
            
            # 更新属性面板
            if hasattr(self.properties_panel, 'set_document'):
                self.properties_panel.set_document(self.document)
            elif hasattr(self.properties_panel, 'document'):
                self.properties_panel.document = self.document
            
            # 更新状态指示器
            if hasattr(self, 'document_status_indicator'):
                status_manager.set_document(self.document)
            
            # 更新窗口标题
            self.update_window_title()
            
            # 更新状态栏
            if hasattr(self.document, 'canvas_width') and hasattr(self.document, 'canvas_height'):
                self.size_label.setText(f"大小: {self.document.canvas_width} x {self.document.canvas_height}")
            else:
                self.size_label.setText("大小: 0 x 0")
            
            # 连接当前文档的信号
            self.document.history_changed.connect(self.update_history_actions)
            self.document.document_changed.connect(self.update_document_info)
            # 连接图层选择信号，用于更新复制粘贴按钮状态
            if hasattr(self.document, 'layer_selected'):
                self.document.layer_selected.connect(self.update_copy_paste_actions)
            
            # 立即更新撤销/重做按钮状态
            self.update_history_actions()
            
            # 更新复制粘贴按钮状态
            self.update_copy_paste_actions()
        elif hasattr(self, 'layer_panel') and hasattr(self, 'properties_panel'):
            print(f"[主窗口] 没有活动文档，清空面板")
            
            # 没有活动文档 - 修复：使用set_document方法清空面板
            if hasattr(self.layer_panel, 'set_document'):
                print(f"[主窗口] 调用图层面板的set_document(None)")
                self.layer_panel.set_document(None)
            else:
                print(f"[主窗口] 直接设置图层面板document为None")
                self.layer_panel.document = None
                # 手动清空列表
                if hasattr(self.layer_panel, 'layer_list'):
                    self.layer_panel.layer_list.clear()
            
            if hasattr(self.properties_panel, 'set_document'):
                self.properties_panel.set_document(None)
            elif hasattr(self.properties_panel, 'document'):
                self.properties_panel.document = None
            self.setWindowTitle("图像批量合成工具")
            self.size_label.setText("大小: 0 x 0")
            
            # 禁用撤销/重做按钮
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)
            
            # 禁用复制粘贴按钮
            self.copy_layer_action.setEnabled(False)
            self.paste_layer_action.setEnabled(False)
    
    def update_window_title(self):
        """更新窗口标题"""
        title = "图像批量合成工具"
        
        if self.document:
            if self.document.current_file_path:
                title += f" - {os.path.basename(self.document.current_file_path)}"
            else:
                # 获取当前标签索引
                current_index = self.tab_widget.currentIndex()
                if current_index >= 0:
                    title += f" - {self.document_manager.get_document_name(current_index)}"
                
            if hasattr(self.document, 'is_modified') and self.document.is_modified:
                title += " *"
                
        self.setWindowTitle(title)
    
    def update_tab_name(self, index):
        """更新标签名称"""
        if index < 0 or index >= self.tab_widget.count():
            return
        
        name = self.document_manager.get_document_name(index)
        if self.document_manager.is_document_modified(index):
            name += " *"

        doc = self.document_manager.get_document(index)
        status = self._document_runtime_status_by_id.get(id(doc), "") if doc else ""
        if status:
            name += f" [{status}]"
            
        self.tab_widget.setTabText(index, name)

    def set_document_runtime_status(self, document, status_text=""):
        """设置文档运行状态并刷新对应标签名称"""
        if document is None:
            return
        doc_id = id(document)
        status_text = (status_text or "").strip()
        if status_text:
            self._document_runtime_status_by_id[doc_id] = status_text
        else:
            self._document_runtime_status_by_id.pop(doc_id, None)

        for i in range(self.document_manager.get_document_count()):
            doc = self.document_manager.get_document(i)
            if doc is document:
                self.update_tab_name(i)
                break
    
    def create_new_tab(self, document=None):
        """创建新标签页"""
        if document is None:
            # 创建新文档
            document = Document(parent=self)
            document.create_new(800, 600)
        
        # 创建标签页内容
        tab = DocumentTab(document)
        
        # 生成标签名
        doc_index = self.document_manager.add_document(document)
        tab_name = self.document_manager.get_document_name(doc_index)
        
        # 添加到标签页控件
        tab_index = self.tab_widget.addTab(tab, tab_name)
        
        # 激活新标签页
        self.tab_widget.setCurrentIndex(tab_index)
        
        # 连接画布信号
        tab.canvas.position_changed.connect(self.update_position_label)
        
        # 连接图层操作信号到属性面板更新
        if hasattr(tab.canvas, 'layer_moved'):
            tab.canvas.layer_moved.connect(self.on_canvas_layer_moved)
        if hasattr(tab.canvas, 'layer_resized'):
            tab.canvas.layer_resized.connect(self.on_canvas_layer_resized)
        
        return tab_index

    def _sync_document_view_settings_from_tab(self, tab_index):
        """将指定标签页画布视图设置同步到文档对象"""
        if tab_index < 0 or tab_index >= self.tab_widget.count():
            return
        tab = self.tab_widget.widget(tab_index)
        doc = self.document_manager.get_document(tab_index)
        if not tab or not doc or not hasattr(tab, 'canvas'):
            return
        canvas = tab.canvas
        if hasattr(doc, 'set_view_settings'):
            doc.set_view_settings({
                'show_rulers': bool(getattr(canvas, 'show_rulers', True)),
                'show_guides': bool(getattr(canvas, 'show_guides', True)),
                'snap_to_guides': bool(getattr(canvas, 'snap_to_guides', True)),
                'ruler_size': int(getattr(canvas, '_ruler_size', 20)),
                'horizontal_guides': list(getattr(canvas, 'horizontal_guides', [])),
                'vertical_guides': list(getattr(canvas, 'vertical_guides', [])),
                'zoom_factor': float(getattr(canvas, 'zoom_factor', 1.0)),
                'offset_x': int(getattr(canvas, 'offset', QPoint(0, 0)).x()),
                'offset_y': int(getattr(canvas, 'offset', QPoint(0, 0)).y()),
            })
    
    def close_tab(self, index):
        """关闭标签页"""
        if index < 0 or index >= self.tab_widget.count():
            return
        
        document = self.document_manager.get_document(index)
        if not document:
            return
        
        # 检查是否有未保存的更改
        if hasattr(document, 'is_modified') and document.is_modified:
            # 弹出确认对话框
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("关闭文档")
            msg_box.setText(f"文档 '{self.document_manager.get_document_name(index)}' 有未保存的更改，是否保存？")
            msg_box.setIcon(QMessageBox.Question)
            
            save_btn = msg_box.addButton("保存", QMessageBox.AcceptRole)
            discard_btn = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
            
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
            
            if clicked_button == save_btn:
                # 先激活要关闭的标签
                self.tab_widget.setCurrentIndex(index)
                # 保存文档
                if not self.save_document():
                    # 保存失败，取消关闭
                    return
            elif clicked_button == cancel_btn:
                # 取消关闭
                return
        
        # 移除标签页
        self.tab_widget.removeTab(index)
        
        # 从文档管理器中移除文档
        self._document_runtime_status_by_id.pop(id(document), None)
        self.document_manager.remove_document(index)
    
    def duplicate_tab(self):
        """复制当前标签页"""
        # 获取当前标签页索引
        current_index = self.tab_widget.currentIndex()
        if current_index < 0:
            return
        
        # 获取当前文档
        current_document = self.document_manager.get_document(current_index)
        if not current_document:
            return
        
        # 创建文档副本
        new_document = Document(parent=self)
        new_document.canvas_width = current_document.canvas_width
        new_document.canvas_height = current_document.canvas_height
        
        # 复制所有图层
        for layer in current_document.layers:
            if layer is None:
                continue
            # 创建图层副本
            try:
                new_layer = layer.duplicate(parent=new_document)
            except TypeError:
                # 兼容旧实现：部分图层duplicate不接收parent参数
                new_layer = layer.duplicate()
            except Exception as e:
                print(f"复制图层失败，已跳过: {e}")
                continue
            if new_layer is not None:
                new_document.layers.append(new_layer)
        
        # 设置相同的选中图层
        new_document.selected_layer_index = current_document.selected_layer_index
        
        # 复制导出设置
        new_document.export_settings = current_document.export_settings.copy()
        
        # 标记为已修改
        new_document.is_modified = True
        
        # 创建新标签页，放在当前标签页后面
        new_tab_index = self.create_new_tab(new_document)
        
        return new_tab_index
    
    def show_tab_context_menu(self, position):
        """显示标签页右键菜单"""
        # 获取点击位置所在的标签页索引
        index = self.tab_widget.tabBar().tabAt(position)
        if index < 0:
            return
        
        # 创建右键菜单
        menu = QMenu()
        document = self.document_manager.get_document(index)
        export_dialog = self._get_running_export_dialog_for_document(document)
        
        # 添加菜单项
        close_action = menu.addAction("关闭标签页")
        close_other_action = menu.addAction("关闭其他标签页")
        menu.addSeparator()
        duplicate_action = menu.addAction("复制标签页")
        restore_export_action = None
        if export_dialog is not None:
            restore_export_action = menu.addAction("恢复导出窗口")
        menu.addSeparator()
        rename_action = menu.addAction("重命名标签页")
        
        # 显示菜单并获取用户选择的操作
        action = menu.exec_(self.tab_widget.tabBar().mapToGlobal(position))
        
        # 处理用户选择的操作
        if action == close_action:
            self.close_tab(index)
        elif action == close_other_action:
            self.close_other_tabs(index)
        elif action == duplicate_action:
            # 先切换到要复制的标签页
            self.tab_widget.setCurrentIndex(index)
            # 然后执行复制
            self.duplicate_tab()
        elif restore_export_action and action == restore_export_action:
            self.restore_export_dialog(index)
        elif action == rename_action:
            self.rename_tab(index)

    def _get_running_export_dialog_for_document(self, document):
        """获取文档正在后台运行的导出窗口（若存在）"""
        if document is None:
            return None
        doc_key = id(document)
        dialog = self._batch_export_dialogs_by_doc.get(doc_key)
        if dialog is not None and getattr(dialog, "_export_running", False):
            return dialog
        dialog = self._multi_tab_export_dialogs_by_doc.get(doc_key)
        if dialog is not None and getattr(dialog, "_export_started", False):
            return dialog
        return None

    def restore_export_dialog(self, index):
        """恢复指定标签页的导出窗口"""
        if index < 0 or index >= self.tab_widget.count():
            return
        document = self.document_manager.get_document(index)
        dialog = self._get_running_export_dialog_for_document(document)
        if dialog is None:
            return
        self.tab_widget.setCurrentIndex(index)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
    
    def close_other_tabs(self, keep_index):
        """关闭除了指定索引外的所有标签页"""
        if keep_index < 0 or keep_index >= self.tab_widget.count():
            return
        
        # 从后向前关闭标签页，避免索引变化问题
        for i in range(self.tab_widget.count() - 1, -1, -1):
            if i != keep_index:
                self.close_tab(i)
    
    def rename_tab(self, index):
        """重命名标签页"""
        if index < 0 or index >= self.tab_widget.count():
            return
        
        document = self.document_manager.get_document(index)
        if not document:
            return
        
        # 获取当前名称
        current_name = self.tab_widget.tabText(index)
        if current_name.endswith(" *"):  # 移除修改标记
            current_name = current_name[:-2]
        
        # 弹出输入对话框
        from PySide6.QtWidgets import QInputDialog
        new_name, ok = QInputDialog.getText(
            self, "重命名标签页", "输入新名称:", 
            text=current_name
        )
        
        if ok and new_name:
            # 如果文档模型中有name属性，也要同步更新
            if hasattr(document, 'name'):
                document.name = new_name
            document.tab_name = new_name
            document.original_tab_name = new_name
            
            # 更新标签页文本
            self.tab_widget.setTabText(index, new_name)
            
            # 如果是已修改状态，添加修改标记
            if self.document_manager.is_document_modified(index):
                self.tab_widget.setTabText(index, new_name + " *")
    
    def tab_changed(self, index):
        """切换标签页时触发"""
        # the current tab has changed, update the current document
        if 0 <= index < self.tab_widget.count():
            self.document_manager.set_active_document(index)
            
            # 主动更新撤销/重做按钮状态，确保与当前文档同步
            self.update_history_actions()
        else:
            # 没有标签页了
            self.document_manager.active_document_index = -1
            self.document_manager.active_document_changed.emit(None)
    
    def _on_controller_status_message(self, message, timeout):
        """处理控制器状态消息"""
        self.statusbar.showMessage(message, timeout)
    
    def _on_document_operation_completed(self, operation, success):
        """处理文档操作完成信号"""
        # 可以在这里添加额外的处理逻辑，比如更新UI状态
        if operation == "new_document" and success:
            print(f"[INFO] 新文档创建成功")
        elif operation == "open_document" and success:
            print(f"[INFO] 文档打开成功")
        elif operation.startswith("save") and success:
            print(f"[INFO] 文档保存成功")
    
    def _on_layer_operation_completed(self, operation, success):
        """处理图层操作完成信号"""
        # 可以在这里添加额外的处理逻辑，比如更新UI状态
        if success:
            print(f"[INFO] 图层操作成功: {operation}")
        else:
            print(f"[WARNING] 图层操作失败: {operation}")
    
    def _on_layer_selection_changed(self):
        """处理图层选择改变信号"""
        # 可以在这里更新UI状态，如工具栏按钮的启用状态
        # 目前只是记录日志
        pass
    
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
        """添加新文字图层 - 委托给LayerController"""
        return self.layer_controller.add_text_layer()
    
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
        """关闭窗口前检查是否有未保存的文档并保存窗口状态"""
        for i in range(self.document_manager.get_document_count()):
            document = self.document_manager.get_document(i)
            if hasattr(document, 'is_modified') and document.is_modified:
                # 有未保存的文档，弹出确认对话框
                msg_box = QMessageBox(self)
                msg_box.setWindowTitle("退出")
                msg_box.setText("有未保存的文档，是否在退出前保存？")
                msg_box.setIcon(QMessageBox.Question)
                
                save_btn = msg_box.addButton("保存", QMessageBox.AcceptRole)
                discard_btn = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
                cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
                
                reply = msg_box.exec()
                clicked_button = msg_box.clickedButton()
                
                if clicked_button == save_btn:
                    # 保存所有文档
                    for j in range(self.document_manager.get_document_count()):
                        self.tab_widget.setCurrentIndex(j)
                        if not self.save_document():
                            # 如果有任何文档保存失败，取消关闭
                            event.ignore()
                            return
                    # 所有文档已保存，保存窗口状态并接受关闭事件
                    self.save_window_state()
                    event.accept()
                elif clicked_button == discard_btn:
                    # 不保存文档，但保存窗口状态，接受关闭事件
                    self.save_window_state()
                    event.accept()
                else:
                    # 取消关闭
                    event.ignore()
                return
        
        # 没有未保存的文档，保存窗口状态并直接关闭
        self.save_window_state()
        event.accept()
    
    def save_as_preset(self):
        """将所有打开的标签页保存为预设"""
        # 检查是否有打开的标签页
        if self.tab_widget.count() == 0:
            QMessageBox.warning(self, "保存预设", "没有打开的标签页")
            return
            
        # 询问预设名称
        default_name = self._current_editing_preset_name or ""
        preset_name, ok = QInputDialog.getText(
            self,
            "保存预设",
            "输入预设名称:",
            QLineEdit.Normal,
            default_name
        )
        if not ok or not preset_name:
            return
        
        # 收集所有打开的标签页文档
        documents = []
        print(f"准备保存预设 '{preset_name}'，包含 {self.tab_widget.count()} 个标签页")
        
        for i in range(self.tab_widget.count()):
            self._sync_document_view_settings_from_tab(i)
            # 获取对应的文档
            doc = self.document_manager.get_document(i)
            
            # 获取标签页实际显示的文本
            tab_text = self.tab_widget.tabText(i)
            # 如果标签页文本以 " *" 结尾 (表示未保存)，移除它
            if tab_text.endswith(" *"):
                tab_text = tab_text[:-2]
                
            # 设置tab_name属性和original_tab_name属性
            doc.tab_name = tab_text
            doc.original_tab_name = tab_text
            
            print(f"标签页 {i}: '{tab_text}'")
            documents.append(doc)
        
        # 获取全局设置（如果有的话）
        global_settings = {}
        if hasattr(self, 'get_global_settings'):
            global_settings = self.get_global_settings()
            
        # 使用预设管理器的save_preset_documents方法保存多标签页预设
        result = self.preset_manager.save_preset_documents(
            preset_name,
            "",  # 空描述
            documents,
            global_settings
        )
        
        # 检查结果
        if isinstance(result, dict) and result.get("duplicate"):
            # 提示用户是否要更新已有预设
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("预设名称已存在")
            msg_box.setText(f"已存在名为 '{result['name']}' 的预设，是否要更新它？")
            msg_box.setIcon(QMessageBox.Question)
            
            yes_btn = msg_box.addButton("是", QMessageBox.AcceptRole)
            no_btn = msg_box.addButton("否", QMessageBox.RejectRole)
            
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
            
            if clicked_button == yes_btn:
                # 更新已有预设
                existing_id = result["existing_id"]
                success = self.preset_manager.delete_preset(existing_id)
                
                if success:
                    # 然后用相同名称保存新预设
                    preset_id = self.preset_manager.save_preset_documents(
                        preset_name,
                        "",  # 空描述
                        documents,
                        global_settings
                    )
                    
                    if preset_id:
                        self._set_current_editing_preset(preset_id, preset_name)
                        QMessageBox.information(self, "保存预设", f"预设 '{preset_name}' 已更新 (包含 {len(documents)} 个标签页)")
                    else:
                        QMessageBox.warning(self, "保存预设", "更新预设失败")
                else:
                    QMessageBox.warning(self, "保存预设", "删除旧预设失败，无法完成更新")
        elif result:  # 保存成功
            self._set_current_editing_preset(result, preset_name)
            QMessageBox.information(self, "保存预设", f"预设 '{preset_name}' 已保存 (包含 {len(documents)} 个标签页)")
        else:  # 保存失败
            QMessageBox.warning(self, "保存预设", "保存预设失败")
    
    def load_preset(self):
        """打开预设中心。"""
        self.open_preset_store()

    def manage_presets(self):
        """打开预设中心。"""
        self.open_preset_store()

    def open_preset_store(self):
        """打开应用商店式预设中心。"""
        from app.ui.preset_store_dialog import PresetStoreDialog

        dialog = PresetStoreDialog(self, self)
        dialog.preset_edit_requested.connect(
            lambda preset_id: dialog.accept() if self._edit_preset_from_store(preset_id) else None
        )
        dialog.exec()

    def _edit_preset_from_store(self, preset_id):
        """从预设中心进入编辑。"""
        if not self._confirm_unsaved_before_loading_preset():
            return False

        close_existing = False
        if self.document_manager.get_document_count() > 0:
            msg_box = QMessageBox(self)
            msg_box.setWindowTitle("进入编辑")
            msg_box.setText("是否要关闭现有标签页并加载预设？\n选择“否”会把预设添加到当前标签页之后。")
            msg_box.setIcon(QMessageBox.Question)
            yes_btn = msg_box.addButton("关闭现有", QMessageBox.AcceptRole)
            no_btn = msg_box.addButton("追加加载", QMessageBox.DestructiveRole)
            cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
            msg_box.exec()
            clicked_button = msg_box.clickedButton()
            if clicked_button == cancel_btn:
                return False
            close_existing = clicked_button == yes_btn

        return self.apply_preset_to_tabs(preset_id, close_existing=close_existing)

    def _confirm_unsaved_before_loading_preset(self):
        """加载预设前处理未保存文档。"""
        any_modified = False
        for i in range(self.document_manager.get_document_count()):
            doc = self.document_manager.get_document(i)
            if hasattr(doc, 'is_modified') and doc.is_modified:
                any_modified = True
                break

        if not any_modified:
            return True

        msg_box = QMessageBox(self)
        msg_box.setWindowTitle("加载预设")
        msg_box.setText("当前有未保存的文档。继续加载预设前是否保存？")
        msg_box.setIcon(QMessageBox.Question)
        save_btn = msg_box.addButton("保存", QMessageBox.AcceptRole)
        discard_btn = msg_box.addButton("不保存", QMessageBox.DestructiveRole)
        cancel_btn = msg_box.addButton("取消", QMessageBox.RejectRole)
        msg_box.exec()
        clicked_button = msg_box.clickedButton()

        if clicked_button == cancel_btn:
            return False
        if clicked_button == save_btn:
            for i in range(self.document_manager.get_document_count()):
                if self.document_manager.is_document_modified(i):
                    self.tab_widget.setCurrentIndex(i)
                    if not self.save_document():
                        return False
        return True

    def apply_preset_to_tabs(self, preset_id, close_existing=False):
        """将预设加载到编辑标签页。"""
        preset_data = self.preset_manager.load_preset(preset_id)
        summary = self.preset_manager.get_preset_summary(preset_id) or {}
        preset_name = summary.get('name', '预设')
        if not preset_data:
            QMessageBox.warning(self, "加载预设", "无法加载预设数据")
            return False

        if close_existing:
            while self.tab_widget.count() > 0:
                self.close_tab(0)

        try:
            from app.utils.preset_document_loader import documents_from_preset_data
            documents = documents_from_preset_data(preset_data, parent=self)
            if documents:
                created_tabs = 0
                for document in documents:
                    tab_index = self.create_new_tab(document)
                    tab_name = getattr(document, 'original_tab_name', None) or getattr(document, 'tab_name', None) or f"标签页 {tab_index + 1}"
                    self.tab_widget.setTabText(tab_index, tab_name)
                    created_tabs += 1
                self._set_current_editing_preset(
                    preset_id,
                    preset_name,
                    summary.get('description', '')
                )
                QMessageBox.information(self, "加载预设", f"已成功加载预设 '{preset_name}'，包含 {created_tabs} 个标签页")
                return True

            QMessageBox.warning(self, "加载预设", f"无法加载预设 '{preset_name}'")
            return False
        except Exception as e:
            import traceback
            error_details = traceback.format_exc()
            print(f"加载预设时出错: {e}\n{error_details}")
            QMessageBox.warning(self, "加载预设", f"无法加载预设 '{preset_name}':\n{str(e)}")
            return False

    def _set_current_editing_preset(self, preset_id, name, description=None):
        """记录当前从预设进入编辑的上下文，用于下次保存时默认回填名称。"""
        summary = self.preset_manager.get_preset_summary(preset_id) or {}
        self._current_editing_preset_id = preset_id
        self._current_editing_preset_name = name or summary.get('name', '')
        if description is None:
            description = summary.get('description', '')
        self._current_editing_preset_description = description or ""
    
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
    
    def manage_canvas_presets(self):
        """打开画布预设管理对话框"""
        from app.ui.canvas_preset_dialog import CanvasPresetManagerDialog
        dialog = CanvasPresetManagerDialog(self)
        dialog.exec()
    
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
