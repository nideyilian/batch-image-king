from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QSpinBox, QDoubleSpinBox, QLineEdit, QFormLayout,
                           QFileDialog, QGroupBox, QCheckBox, QComboBox,
                           QSlider, QMessageBox, QRadioButton, QButtonGroup,
                           QScrollArea, QFrame, QSizePolicy,
                           QMenu, QMainWindow, QDockWidget, QApplication, QTextEdit,
                           QProgressBar)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QSettings, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QColor
import os
import time
from PIL import Image

try:
    from app.models.document_blend import BlendMode
    HAS_BLEND_MODE = True
except ImportError:
    HAS_BLEND_MODE = False

from app.ui.layer_transform_widget import LayerTransformWidget
from app.ui.collapsible_group import CollapsibleGroupBox
from app.ui.color_picker_dialog_a2 import get_color_a2
from app.ui.shaped_layer_panel import ShapePreviewWidget, ShapeType as PreviewShapeType
from app.ui.dark_theme import CursorDarkTheme
from app.utils.layer_tree import is_layer_group
from app.services.ai_asset_service import (
    AIAssetRequest,
    AIAssetResult,
    AIAssetService,
    localize_ai_error,
)
from app.services.ai_provider_config import AIProviderStore
from app.utils.print_utils import safe_print

# 图层面板方法已拆分到以下 mixin 模块，通过多重继承组合进主类
from app.ui.layer_properties_base import LayerPropertiesBase
from app.ui.layer_properties_layout import LayerPropertiesLayout
from app.ui.layer_properties_refresh import LayerPropertiesRefresh
from app.ui.layer_properties_attr import LayerPropertiesAttr
from app.ui.layer_properties_ai import LayerPropertiesAi
from app.ui.layer_properties_source import LayerPropertiesSource
from app.ui.layer_properties_transform import LayerPropertiesTransform
from app.ui.layer_properties_shape import LayerPropertiesShape


class _AIAssetWorkerSignals(QObject):
    finished = Signal(object)


class _AIAssetLayerTask(QRunnable):
    def __init__(self, service, request):
        super().__init__()
        self.service = service
        self.request = request
        self.signals = _AIAssetWorkerSignals()

    @Slot()
    def run(self):
        self.signals.finished.emit(self.service.generate_assets(self.request))


class LayerPropertiesPanel(QWidget, LayerPropertiesBase, LayerPropertiesLayout, LayerPropertiesRefresh, LayerPropertiesAttr, LayerPropertiesAi, LayerPropertiesSource, LayerPropertiesTransform, LayerPropertiesShape):
    """图层属性面板（方法已拆分到多个 mixin 模块，见 layer_properties_*.py）"""

    # 属性变更信号
    name_changed = Signal(str)
    opacity_changed = Signal(int)

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.current_layer = None
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.text_layer_panel = None  # 文字图层属性面板
        self._deferred_layer_changed = False
        self._deferred_action_name = None
        self._suppress_panel_refresh_until = 0.0
        self._deferred_context_fields = []
        self._deferred_context_reason = ""
        self._ui_change_timer = QTimer(self)
        self._ui_change_timer.setSingleShot(True)
        self._ui_change_timer.timeout.connect(self._flush_deferred_document_change)
        self._history_timer = QTimer(self)
        self._history_timer.setSingleShot(True)
        self._history_timer.timeout.connect(self._flush_deferred_history_save)
        # 模块拆分/组合状态
        self._module_groups = {}
        self._module_group_titles = {}
        self._module_order = []
        self._module_docks = {}
        self._restoring_module_layout = False
        self._ai_generation_task = None

        self.setup_ui()

        # 连接文档变化信号
        if self.document:
            safe_print("正在连接图层信号...")  # 调试信息
            self.document.layer_changed.connect(self.on_layer_changed)
            self.document.layer_selected.connect(self.layer_selected)
            if hasattr(self.document, 'layers_selection_changed'):
                self.document.layers_selection_changed.connect(self._on_layers_selection_changed)
            self.document.document_changed.connect(self.delayed_update_panel)

            # 如果文档有图层且已选择图层，直接触发选择
            if hasattr(self.document, 'layers') and len(self.document.layers) > 0:
                if hasattr(self.document, 'selected_layer_index') and self.document.selected_layer_index >= 0:
                    safe_print(f"文档已有选中图层: {self.document.selected_layer_index}")
                    self.layer_selected(self.document.selected_layer_index)
                else:
                    # 自动选择第一个图层
                    safe_print("自动选择第一个图层")
                    self.document.select_layer(0)
        else:
            safe_print("警告: document为空，无法连接信号")

        # 初始加载时更新一次UI
        self.update_panel()

    def mouseReleaseEvent(self, event):
        """鼠标释放事件，用于处理点击面板时自动选择图层"""
        super().mouseReleaseEvent(event)

        # 如果当前没有选中的图层，尝试选择第一个图层
        if not self.current_layer and self.document and hasattr(self.document, 'layers') and len(self.document.layers) > 0:
            safe_print("点击面板，自动选择第一个图层")
            if hasattr(self.document, 'select_layer'):
                self.document.select_layer(0)
            else:
                self.layer_selected(0)

        # 如果控件被禁用但有选中图层，确保更新面板
        if self.current_layer and not self.name_edit.isEnabled():
            safe_print("检测到控件禁用但已有选中图层，更新面板")
            self.update_panel()

# 以下方法实现位于各个 mixin 模块中，通过多重继承组合进来。
# 主类仅保留 __init__、类级信号声明与 Qt 事件重写 mouseReleaseEvent。

# 向后兼容：_AIAssetWorkerSignals / _AIAssetLayerTask 在本文件 preamble 中定义

__all__ = [
    'LayerPropertiesPanel',
    '_AIAssetWorkerSignals',
    '_AIAssetLayerTask',
]
