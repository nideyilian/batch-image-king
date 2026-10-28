# -*- coding: utf-8 -*-
from app.ui.design_spec import IconSize as _IconSize, Space as _Space, Scale as _Scale
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
from app.ui.design_tokens import Tokens
from app.utils.preset_manager import PresetManager
from app.ui.status_indicators import status_manager
from app.ui.visual_hierarchy import VisualHierarchy
from app.ui.icon_manager import IconManager
import os
import pickle

# 模块级 UI 布局常量（原 main_window.py 顶层常量，随 UI 职责归入本 mixin 文件）
ICON_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "resources")
COMPACT_LAYER_DOCK_WIDTH = 180
COMPACT_PROPERTIES_DOCK_WIDTH = Tokens.SIDEBAR_PREFERRED_WIDTH
COMPACT_LAYER_DOCK_MIN_WIDTH = 145
COMPACT_PROPERTIES_DOCK_MIN_WIDTH = Tokens.SIDEBAR_MIN_WIDTH + 14

class MainWindowUi(object):
    def setup_ui(self):
        """设置主界面UI"""
        self.central_widget = QWidget()
        self.central_widget.setProperty("role", "workspace")
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
        self.duplicate_tab_action.setShortcut(QKeySequence("Alt+Shift+D"))
        self.duplicate_tab_action.triggered.connect(self.duplicate_tab)
    
        self.export_action = QAction("导出", self)
        self.export_action.setShortcut("Ctrl+Shift+X")
        self.export_action.triggered.connect(self.export_image)
    
        self.batch_export_action = QAction("批量导出", self)
        self.batch_export_action.setShortcut("F12")
        self.batch_export_action.triggered.connect(self.batch_export)
    
        # 添加多标签页批量导出操作
        self.multi_tab_export_action = QAction("多标签页批量导出", self)
        # 工具栏用短标签（TextOnly 模式），菜单仍显示完整文字
        self.multi_tab_export_action.setIconText("多页导出")
        self.multi_tab_export_action.triggered.connect(self.multi_tab_export)
    
        self.exit_action = QAction("退出", self)
        self.exit_action.setShortcut(QKeySequence.Quit)
        self.exit_action.triggered.connect(self.close)
    
        # 预设菜单操作
        self.preset_store_action = QAction("预设中心", self)
        self.preset_store_action.setShortcut("Ctrl+Shift+P")
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
        # 优先 PS 习惯 Ctrl+Shift+Z；同时兼容旧的 Ctrl+Y（通过 setShortcuts 多键）
        self.redo_action.setShortcuts([QKeySequence("Ctrl+Shift+Z"), QKeySequence.Redo])
        self.redo_action.triggered.connect(self.redo)
        self.redo_action.setEnabled(False)

        # 撤销的 PS 风格补充：Ctrl+Alt+Z 步退一步
        self.step_backward_action = QAction("后退一步", self)
        self.step_backward_action.setShortcut("Ctrl+Alt+Z")
        self.step_backward_action.triggered.connect(self.undo)
        self.step_backward_action.setEnabled(False)
    
        # 调整画布大小
        self.resize_canvas_action = QAction("修改画布尺寸(Canvas Size)", self)
        self.resize_canvas_action.setShortcut("Alt+Ctrl+C")
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
        self.add_layer_action = QAction("新建空图片图层", self)
        self.add_layer_action.setIconText("新建图层")
        self.add_layer_action.setShortcut("Shift+Ctrl+N")   # PS: 新建图层
        self.add_layer_action.triggered.connect(self.add_layer)

        self.duplicate_layer_via_copy_action = QAction("复制选中图层到新图层", self)
        self.duplicate_layer_via_copy_action.setShortcut("Ctrl+J")   # PS: Via copy 复制图层
        self.duplicate_layer_via_copy_action.triggered.connect(self.add_layer)  # 占位：复用 duplicate 或 add_layer；在 main_window.py 中将 connect 覆写为真实复制实现

        self.free_transform_action = QAction("自由变换", self)
        self.free_transform_action.setShortcut("Ctrl+T")   # PS: 自由变换
        self.free_transform_action.triggered.connect(lambda: status_manager.show_status("自由变换：拖拽控制点缩放，Esc 取消", toast=True))

        self.merge_selected_down_action = QAction("向下合并图层(编组)", self)
        self.merge_selected_down_action.setShortcut("Ctrl+E")   # PS: 向下合并图层
        self.merge_selected_down_action.triggered.connect(self.add_layer)  # 占位：若有编组实现则在 main_window.py 中覆写

        self.group_layers_action = QAction("图层编组", self)
        self.group_layers_action.setShortcut("Ctrl+G")   # PS: 编组
        self.group_layers_action.triggered.connect(self.add_layer)  # 占位

        self.ungroup_groups_action = QAction("取消图层编组", self)
        self.ungroup_groups_action.setShortcut("Ctrl+Shift+G")   # PS: 取消编组
        self.ungroup_groups_action.triggered.connect(self.add_layer)  # 占位

        self.send_to_back_action = QAction("图层置于底层", self)
        self.send_to_back_action.setShortcut("Ctrl+Shift+[")   # PS: Send to back
        self.send_to_back_action.triggered.connect(self.move_layer_down)  # 占位近似：多次下移

        self.bring_to_front_action = QAction("图层置于顶层", self)
        self.bring_to_front_action.setShortcut("Ctrl+Shift+]")   # PS: Bring to front
        self.bring_to_front_action.triggered.connect(self.move_layer_up)  # 占位近似：多次上移

        self.step_backward_layer_action = QAction("图层下移一层", self)
        self.step_backward_layer_action.setShortcut("Ctrl+[")   # PS: 下移一层
        self.step_backward_layer_action.triggered.connect(self.move_layer_down)

        self.step_forward_layer_action = QAction("图层上移一层", self)
        self.step_forward_layer_action.setShortcut("Ctrl+]")   # PS: 上移一层
        self.step_forward_layer_action.triggered.connect(self.move_layer_up)

        # 视图：标尺/参考线切换
        self.toggle_rulers_action = QAction("切换标尺显示", self)
        self.toggle_rulers_action.setShortcut("Ctrl+R")   # PS: 标尺
        self.toggle_rulers_action.triggered.connect(lambda: status_manager.show_status("切换标尺显示", toast=True))

        self.toggle_guides_action = QAction("切换参考线显示", self)
        self.toggle_guides_action.setShortcut(";")   # PS: 参考线
        self.toggle_guides_action.triggered.connect(lambda: status_manager.show_status("切换参考线显示", toast=True))

        self.add_text_layer_action = QAction("添加文字图层…", self)
        self.add_text_layer_action.setIconText("文字图层")
        self.add_text_layer_action.setShortcut("Shift+F8")   # 从 PS 核心 Ctrl+T 迁出
        self.add_text_layer_action.setToolTip("打开对话框，填写内容与样式后创建文字图层")
        self.add_text_layer_action.triggered.connect(self.add_text_layer)

        # 快速建层：不弹窗，用默认样式直接建好，随后在属性面板调整。
        # 高频加字时，每次填 5 个字段纯属浪费；对应 PS「点一下就有文字层」的心流。
        self.quick_text_layer_action = QAction("快速文字图层", self)
        self.quick_text_layer_action.setShortcut("T")
        self.quick_text_layer_action.setToolTip(
            "不弹窗，按默认样式立即创建文字图层（T）\n创建后在右侧属性面板调整内容与样式"
        )
        self.quick_text_layer_action.triggered.connect(self.add_quick_text_layer)

        self.ai_asset_studio_action = QAction("AI接口设置", self)
        self.ai_asset_studio_action.setIconText("AI 素材")
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
        layer_menu.addAction(self.quick_text_layer_action)
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

    def _apply_toolbar_icons(self):
        """为主工具栏动作补齐矢量图标。

        历史上主工具栏 QAction 从未调用 setIcon，按钮只剩文字（无图标占位框）；
        toolbar 的 ToolButtonTextBesideIcon 模式下会渲染成一个个空白方块。
        这里按动作名一次性绑定，图标统一走 IconManager（Lucide 风格 SVG）。
        """
        mapping = {
            self.new_action: 'new',
            self.open_action: 'open',
            self.save_action: 'save',
            self.undo_action: 'undo',
            self.redo_action: 'redo',
            self.add_layer_action: 'image',
            self.add_text_layer_action: 'text',
            self.ai_asset_studio_action: 'ai',
            self.delete_layer_action: 'delete',
            self.batch_export_action: 'batch_export',
            self.multi_tab_export_action: 'multi_export',
            self.preset_store_action: 'preset',
        }
        for action, icon_name in mapping.items():
            if action is None:
                continue
            try:
                action.setIcon(IconManager.get_icon(icon_name, 18, 'secondary'))
            except Exception as exc:
                print(f"[工具栏] 设置图标失败 {icon_name}: {exc}")

    def create_toolbar(self):
        """创建工具栏"""
        self._apply_toolbar_icons()
        # 主工具栏
        self.main_toolbar = QToolBar("主工具栏", self)
        self.main_toolbar.setMovable(False)
        self.main_toolbar.setIconSize(QSize(18, 18))
        self.main_toolbar.setFloatable(False)
        self.main_toolbar.setAllowedAreas(Qt.TopToolBarArea)
        # 主工具栏用**纯文字**，不带图标。
        #
        # 为什么（2026-10-28 实测三种模式的 sizeHint）：
        #   图标+文字 1305px | 纯文字 1041px | 纯图标 535px
        # 而 1500px 的窗口要同时容纳主工具栏 + 对齐工具栏(453px)：
        #   图标+文字 1305+453 = 1758 > 1500 → 对齐栏被压到 195px、5 个按钮进溢出菜单
        #   纯文字   1041+453 = 1494 ≤ 1500 → 两个工具栏都能完整显示
        #
        # 所以选纯文字。文案本身是中文，可读性不依赖图标；
        # 图标只在"没有文案"时才必须（例如对齐栏那种纯图标按钮）。
        # 过长的文案通过 setIconText() 给工具栏单独设短标签，见各 action 定义处。
        self.main_toolbar.setToolButtonStyle(Qt.ToolButtonTextOnly)

        # ── 宽度策略（2026-10-28 新增）────────────────────────────────
        #
        # 用户反馈「有些地方固定了，有些可以随界面大小改变」。
        # 实测根因：主工具栏 sizeHint 是 900（纯文字），它会吃掉 900px 固定宽度；
        # 窗口 1147 时对齐栏只剩 247px（需要 323）→ 最后几个图标被挤进溢出菜单，
        # 看起来就是"图标少了几个"。
        #
        # 这里给主工具栏设最小宽度但不是无限优先：窗口够宽时按内容占位，
        # 窗口变窄时优先压缩主工具栏（文字可以省略），保住对齐栏的完整图标。
        self.main_toolbar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.main_toolbar.setMinimumWidth(0)
    
        self.main_toolbar.addAction(self.new_action)
        # “新建”为主操作，使用设计系统的 primary 变体（accent 实心）以突出 CTA
        _new_btn = self.main_toolbar.widgetForAction(self.new_action)
        if _new_btn is not None:
            _new_btn.setProperty("variant", "default")
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
        # 对齐栏用 SM 档按钮（24px）+ 18px 图标，压缩横向需求。
        #
        # 为什么要压缩（2026-10-28 实测，可用宽度 599px）：
        #   按钮 28px（MD 档）→ 需求 453px
        #   按钮 24px（SM 档）→ 需求 323px   ← 省 130px
        #
        # 顶部两条工具栏共用一个 1500px 的横向空间，省下的 130px 让
        # 主工具栏（901px）和对齐栏（323px）都有充足余量，窗口缩放时
        # 不容易触发溢出菜单。
        #
        # 24px 是 WCAG 2.5.8（AA）可点击目标下限，再小就点不准。
        # 图标 18px 配 24px 按钮 = 75%，接近业界 62~71% 的比例区间。
        self.align_toolbar.setIconSize(QSize(_IconSize.MD, _IconSize.MD))
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
    
        # 按钮尺寸交给 QSS 的 iconSm 档（SM=24px），不在这里写死数字。
        #
        # 顶栏两条工具栏共用 1500px 横向空间，实测（2026-10-28）：
        #   按钮 28px（MD 档）→ 对齐栏需求 453px
        #   按钮 24px（SM 档）→ 对齐栏需求 323px   ← 省 130px
        # 主工具栏改纯文字 + 短标签后为 901px，两项合计 1224px，
        # 留出 ~276px 余量，窗口缩放时不易触发 `qt_toolbar_ext_button` 溢出菜单。
        #
        # ⚠ 试过并失败的方案（都实测无效，避免重复踩）：
        # - `addToolBarBreak` / `insertToolBarBreak` → 两工具栏 y 坐标仍相同
        # - `addToolBar(Qt.BottomToolBarArea, tb)`   → 仍停在顶部
        # - 强行 `setMinimumWidth(sizeHint)`         → 对齐栏正常了，但主工具栏开始溢出
        # 根因是 `main_window_misc.py:553` 的 `restoreState()` 会恢复旧布局。
        for _action in self.align_toolbar.actions():
            if _action.isSeparator():
                continue
            _btn = self.align_toolbar.widgetForAction(_action)
            if _btn is not None:
                _btn.setProperty("uiSize", "iconSm")

        # ── 宽度优先级（2026-10-28 新增）────────────────────────────
        #
        # 用户反馈「有些地方固定了，有些可以随界面大小改变」。
        # 实测（窗口 1147）：对齐栏只分到 247px，它需要 323px —— 最后 2 个图标
        # 被挤进 `qt_toolbar_ext_button` 溢出菜单，界面上看着就是「图标少了」。
        # 而主工具栏始终占满 900px 不让步。
        #
        # 这里把优先级反过来：
        #   对齐栏  = Fixed，按 sizeHint 拿满（图标不能缺，缺了功能就找不到）
        #   主工具栏 = Preferred + 最小 0（窗口变窄时它先让位）
        _align_hint = self.align_toolbar.sizeHint().width()
        self.align_toolbar.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.align_toolbar.setMinimumWidth(_align_hint)
        self.align_toolbar.setMaximumWidth(_align_hint)
        self.main_toolbar.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.main_toolbar.setMinimumWidth(0)

        # 主工具栏按钮收紧左右内边距（14px → 3px）。
        #
        # 全局 QSS 给 QToolButton 的是 `padding: 1px 7px`，实测主工具栏
        # 11 个文字按钮合计需要 900px；而窗口 1147 时可用只有 824px
        # （=1147 - 对齐栏 323 - 边距），差 76px → 最后一个按钮进溢出菜单。
        # 收紧到 3px 后需求降到 804px，**不再溢出**（实测三档 3/2/0 都不溢出，
        # 取 3 是为了保留文字与边框之间的呼吸感，不再往下压）。
        # 只影响主工具栏按钮，不动全局 padding（那会影响所有按钮）。
        _compact_tb_qss = (
            "QToolButton { padding: 1px 3px 1px 3px; border-radius: 4px; }"
            "QToolButton:hover { background: rgba(255,255,255,0.05); }"
        )
        for _action in self.main_toolbar.actions():
            _btn = self.main_toolbar.widgetForAction(_action)
            if _btn is not None:
                _btn.setStyleSheet(_compact_tb_qss)

        self.addToolBar(self.align_toolbar)

    def create_statusbar(self):
        """创建状态栏"""
        self.statusbar = self.statusBar()
    
        # 应用状态栏样式
        vh = VisualHierarchy
        # 颜色 / 边框 / 字体由全局主题（dark_theme.CursorDarkTheme）统一提供，
        # 此处仅保留布局相关的最小覆盖，避免与主窗口壳层主题产生第二份样式真值。
        #
        # ⚠ 高度用 min-height 下限 + 不设 max（2026-10-28 修正）。
        # 原来写死 `min-height:20px; max-height:26px`，导致：
        #   - 状态栏高度被锁死，窗口放大/缩小它都不变
        #   - 用户把系统字体调大后，文字被裁掉（26px 塞不下 150% 的 11px 字）
        # 现在只保底 24px（design_spec.Scale.SM，WCAG 可点击下限），
        # 上限交给内容自己撑开。
        statusbar_style = f"""
        QStatusBar {{
            min-height: {_Scale.PX[_Scale.SM]}px;
        }}
        QStatusBar::item {{
            border: none;
        }}
        """
        self.statusbar.setStyleSheet(statusbar_style)
        # 状态栏内的控件随窗口拉伸，不被挤成固定宽度
        self.statusbar.setSizeGripEnabled(True)
    
        # 添加文档状态指示器
        self.document_status_indicator = status_manager.create_document_status_indicator(self)
        self.statusbar.addWidget(self.document_status_indicator)
    
        # 添加分隔符
        separator1 = QLabel("|")
        separator1.setProperty("role", "status-separator")
        self.statusbar.addPermanentWidget(separator1)
    
        # 添加缩放控件
        zoom_layout = QHBoxLayout()
        zoom_layout.setContentsMargins(0, 0, 0, 0)
        zoom_layout.setSpacing(_Space.XS)
    
        zoom_label = QLabel("缩放:")
        zoom_label.setFont(vh.get_font('small'))
        zoom_label.setProperty("role", "muted")
    
        self.zoom_spinbox = QSpinBox()
        self.zoom_spinbox.setRange(10, 500)
        self.zoom_spinbox.setValue(100)
        self.zoom_spinbox.setSuffix("%")
        self.zoom_spinbox.setFixedWidth(68)
        self.zoom_spinbox.setFont(vh.get_font('small'))
        self.zoom_spinbox.valueChanged.connect(self.zoom_value_changed)
    
        # 设置缩放控件样式
        # 颜色 / 边框 / 焦点态由全局主题（dark_theme）统一提供。
        # ⚠ 高度必须 <= 状态栏可用高度（实测 21px）：状态栏不做纵向拉伸，
        #   而全局 QSpinBox 规则是 control-h(30px)+padding=32px，
        #   塞进 21px 容器后文字下半截被裁（「100%」肉眼像「1000%」）。
        #   这里压到 16px（+1px 边框 x2 = 18px），留 3px 余量。
        spinbox_style = """
        QSpinBox {
            min-height: 16px;
            max-height: 16px;
            min-width: 56px;
            padding: 0px 2px;
            font-size: 11px;
        }
        """
        self.zoom_spinbox.setStyleSheet(spinbox_style)
    
        zoom_layout.addWidget(zoom_label)
        zoom_layout.addWidget(self.zoom_spinbox)
    
        zoom_widget = QWidget()
        zoom_widget.setLayout(zoom_layout)
    
        self.statusbar.addPermanentWidget(zoom_widget)
    
        # 添加分隔符
        separator2 = QLabel("|")
        separator2.setProperty("role", "status-separator")
        self.statusbar.addPermanentWidget(separator2)
    
        # 添加坐标显示
        #
        # ⚠ 坐标/大小这类会变的数值，宽度必须可伸缩而不是写死（2026-10-28）。
        # 写死宽度的问题：数值从 "0, 0" 变成 "-1280, 2048" 时文字被裁；
        # 窗口缩小时这些标签又不肯让位，只能把左边的提示文字挤没。
        # 现在用 Preferred 策略 + 等宽字体（数字宽度一致，不跳动），
        # 空间不够时允许被压缩。
        self.position_label = QLabel("坐标: 0, 0")
        self.position_label.setFont(vh.get_font('small'))
        self.position_label.setProperty("role", "muted")
        self.position_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.position_label.setMinimumWidth(0)
        self.statusbar.addPermanentWidget(self.position_label)
    
        # 添加分隔符
        separator3 = QLabel("|")
        separator3.setProperty("role", "status-separator")
        self.statusbar.addPermanentWidget(separator3)
    
        # 添加文档大小显示（同上：可压缩，不写死宽度）
        self.size_label = QLabel("大小: 0 x 0")
        self.size_label.setFont(vh.get_font('small'))
        self.size_label.setProperty("role", "muted")
        self.size_label.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Preferred)
        self.size_label.setMinimumWidth(0)
        self.statusbar.addPermanentWidget(self.size_label)

        # 添加Alt键提示
        #
        # 这是最长的状态栏文字，也是最该优先让位的。窗口变窄时它先省略，
        # 而不是把坐标/大小顶出去。
        self.alt_tip_label = QLabel("提示: 按住Alt键点击图层可避免切换选中图层")
        self.alt_tip_label.setFont(vh.get_font('tiny'))
        self.alt_tip_label.setProperty("role", "muted")
        self.alt_tip_label.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.alt_tip_label.setMinimumWidth(0)
        self.statusbar.addWidget(self.alt_tip_label, 1)

    def create_dock_widgets(self):
        """创建停靠窗口"""
        # ── 停靠行为（2026-10-28 新增）────────────────────────────────
        #
        # 用户反馈：面板拖出来之后就吸附不回去了。
        # 根因不是 features 缺失（Closable|Movable|Floatable 本来就有），
        # 而是主窗口没有显式声明 dock 选项：
        #   - AllowNestedDocks 未开     → 只能停靠在最外圈的四个区，拖到中间不认
        #   - AnimatedDocks 未显式开    → 拖拽时没有落点预览，用户以为"拖不动"
        # 显式打开后，拖拽过程会有蓝色落点预览，松手就吸附。
        self.setDockOptions(
            QMainWindow.AnimatedDocks          # 拖拽时显示落点预览
            | QMainWindow.AllowNestedDocks     # 允许嵌套停靠（不只是四边）
            | QMainWindow.AllowTabbedDocks     # 允许两个面板叠成标签页
        )

        # 图层面板 - 强制使用原始版本确保所有功能正常
        self.layer_dock = QDockWidget("图层", self)
        self.layer_dock.setObjectName("layerDock")
        self.layer_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        # 显式声明特性：可关、可移、可浮。不依赖默认值 ——
        # 默认值在 Qt 版本间变过，显式写死才不会哪天静默少一个。
        self.layer_dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
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
        self.properties_dock.setObjectName("propertiesDock")
        self.properties_dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        self.properties_dock.setFeatures(
            QDockWidget.DockWidgetClosable
            | QDockWidget.DockWidgetMovable
            | QDockWidget.DockWidgetFloatable
        )
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
