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

class MainWindow(
    MainWindowUi,
    MainWindowTabs,
    MainWindowActions,
    MainWindowPresets,
    MainWindowMisc,
    QMainWindow,
):
    """主窗口。

    ## ⚠ 继承顺序不能动（2026-10-27 血的教训）

    mixin **必须排在 `QMainWindow` 前面**。曾经写成
    `class MainWindow(QMainWindow, MainWindowUi, ...)`，导致
    `MainWindowActions.closeEvent()` 被 `QWidget.closeEvent()` 遮蔽 ——
    `getattr(MainWindow, 'closeEvent')` 解析到的是 Qt 的空实现。

    后果：**点窗口 X 直接退出，所有未保存文档被静默丢弃，一个提示都不弹。**
    （实测：3 个 is_modified=True 的文档，closeEvent 里 0 次弹窗）

    Qt 的虚函数走的是 C++ 侧同名方法查找，Python MRO 里谁在前面就用谁。
    `QMainWindow` 排在 mixin 之前意味着所有 mixin 里的虚函数全部失效。
    当前受影响的只有 `closeEvent` 一个（其余虚函数没在 mixin 里定义），
    但这是个陷阱：以后往 mixin 里加 `resizeEvent` / `showEvent` 之类
    会"写了不生效"，且极难排查。

    各 mixin 都没有 `__init__`，且方法间无同名冲突，所以调整顺序是安全的
    （已由 tests/test_main_window_mro.py 锁住）。
    """

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

    # 构造阶段进度回调（可选）。
    #
    # 为什么不直接在构造里调 splash：MainWindow 也被测试和工具脚本直接
    # 实例化（tests/ 与 tools/ 里有多处 `MainWindow()`），它们没有启动画面。
    # 用一个可选的类级钩子，谁需要谁注入，不影响其它调用方。
    #
    # 签名固定为 hook(progress: float, text: str)，与 SplashScreen.advance 一致，
    # 这样 main.py 可以直接 `MainWindow.stage_hook = splash.advance`。
    # ⚠ 曾经把顺序写成 (text, percent)，导致字符串被当进度传给 advance ——
    #   进度条彻底不动且 setProgress 抛类型错。参数顺序必须与 advance 对齐。
    stage_hook = None

    def _notify_stage(self, text: str, percent: float) -> None:
        """向构造阶段回调报告进度；异常一律吞掉，绝不能让启动画面拖垮启动。"""
        hook = type(self).stage_hook
        if hook is None:
            return
        try:
            hook(float(percent), str(text))
        except Exception:
            pass

    def __init__(self):
        super().__init__()

        self._notify_stage("正在初始化文档…", 0.04)

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
        
        self._notify_stage("正在准备工作区…", 0.06)
        self.setup_ui()
        self.create_actions()
        self._notify_stage("正在构建工具栏…", 0.10)
        self.create_toolbar()
        self.create_menubar()

        # 状态栏是整段构造里最贵的一步：`self.statusBar()` 首次创建原生控件
        # 实测占全部构造时间的 **79.5%（约 4.2 秒 / 总 5.3 秒）**，
        # 且耗时集中在单个调用内部，拆不出更细的中间点。
        # 所以这里用"双点"策略：进入前报 0.12，出来报 0.72 ——
        # 让进度条在耗时期间保持低值但可预测，用户看得到它在往前推，
        # 而不是卡在某个数字上 4 秒不动。
        self._notify_stage("正在构建界面框架…", 0.12)
        self.create_statusbar()
        self._notify_stage("正在连接事件…", 0.72)

        # 连接信号
        self.connect_signals()
        
        self.setWindowTitle("图像批量合成工具")
        
        # 创建停靠窗口
        self._notify_stage("正在装配面板…", 0.78)
        self.create_dock_widgets()
        self._notify_stage("正在完成初始化…", 0.94)
        
        # 设置默认窗口大小和位置
        self.resize(1200, 800)
        
        # 恢复窗口状态（大小、位置、停靠窗口布局）
        self.restore_window_state()
        QTimer.singleShot(0, self.apply_compact_dock_layout)
