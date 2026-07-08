from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QListWidget, QListWidgetItem, QCheckBox,
                           QAbstractItemView, QInputDialog, QMenu, QApplication,
                           QDialog, QDialogButtonBox, QTextEdit, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QTimer, QRect, QPoint
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QDropEvent, QPen, QBrush
import sys
import os
import builtins

_LAYER_PANEL_DEBUG = (
    os.environ.get("BTPW_LAYER_PANEL_DEBUG", "0") == "1"
    or os.environ.get("BTPW_UI_DEBUG", "0") == "1"
)
_LAYER_PANEL_ALWAYS_LOG_KEYWORDS = (
    "出错", "错误", "失败", "警告", "异常",
    "error", "failed", "warning", "exception", "Traceback",
)


def print(*args, **kwargs):
    if _LAYER_PANEL_DEBUG:
        builtins.print(*args, **kwargs)
        return
    try:
        message = " ".join(str(arg) for arg in args)
    except Exception:
        message = ""
    if any(keyword in message for keyword in _LAYER_PANEL_ALWAYS_LOG_KEYWORDS):
        builtins.print(*args, **kwargs)

# 注释掉冲突的导入，使用本文件中定义的类
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from app.views.layer_panel import LayerPanel, LayerItem
try:
    from app.models.shaped_layer_new import ShapedLayer
except ImportError:
    from app.models.shaped_layer_new import ShapedLayer

from app.ui.icon_manager import IconManager, create_random_button, create_lock_button, create_visibility_button
from app.ui.visual_hierarchy import VisualHierarchy
from app.ui.shaped_layer_panel import ShapedLayerPanel
from app.models.layer_group import LayerGroup
from app.utils.layer_tree import (
    display_entries,
    get_parent_group_id,
    is_effectively_locked,
    is_layer_group,
    set_parent_group_id,
)


from app.ui.drag_drop_layer_list import DragDropLayerList
from app.ui.layer_item import LayerItem
from app.ui.layer_panel_base import LayerPanelBase
from app.ui.layer_panel_selection import LayerPanelSelection
from app.ui.layer_panel_ops import LayerPanelOps
from app.ui.layer_panel_align import LayerPanelAlign

class LayerPanel(QWidget, LayerPanelBase, LayerPanelSelection, LayerPanelOps, LayerPanelAlign):
    """图层面板组件"""


    def __init__(self, document):
        super().__init__()
        self.document = None  # 初始化为None，等待set_document设置
        # 按选择顺序记录图层索引，首个元素作为多图层对齐基准
        self._selected_layer_indices = []
        self._selection_sync_in_progress = False
        self._binding_debug_mode = (os.environ.get("BTPW_BINDING_DEBUG_PANEL", "0") == "1")
        self._binding_debug_last_text = ""

        # 添加防抖和更新控制
        self._update_timer = QTimer(self)
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._perform_update)
        self._update_pending = False
        self._updating = False  # 更新锁，防止级联更新
        self._binding_debug_timer = QTimer(self)
        self._binding_debug_timer.setInterval(800)
        self._binding_debug_timer.timeout.connect(self._refresh_binding_debug_panel)

        # 先创建UI
        self.setup_ui()

        # 然后设置文档（这样可以确保信号连接正常）
        if document is not None:
            print(f"[图层面板] 初始化时设置文档，图层数量: {len(document.layers) if hasattr(document, 'layers') else 0}")
            self.set_document(document)
        else:
            print("[图层面板] 初始化时文档为None，等待后续设置")



# 以下方法实现位于各个 mixin 模块中，通过多重继承组合进来。
# 主类仅保留类声明、类级属性与 __init__。

