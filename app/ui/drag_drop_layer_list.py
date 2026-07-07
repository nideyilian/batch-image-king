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
    from app.models.shaped_layer import ShapedLayer

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


class DragDropLayerList(QListWidget):
    """支持拖放的图层列表组件"""

    layer_moved = Signal(int, int)  # 拖放后触发信号: 源索引, 目标索引

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragDropMode(QAbstractItemView.InternalMove)
        # 支持PS风格多选（Ctrl/Shift）
        self.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # 拖拽交互增强状态
        self.drag_insert_line_visible = False
        self.drag_insert_position = -1
        self.drag_preview_enabled = True

    def dropEvent(self, event):
        """重写dropEvent处理图层拖放完成事件"""
        source_index = self.currentRow()
        if source_index < 0:
            return

        # 获取鼠标放下的位置
        drop_pos = event.pos()
        drop_item = self.itemAt(drop_pos)

        # 如果没有放在任何项上，则不处理
        if not drop_item:
            return

        target_index = self.row(drop_item)

        # 执行默认的拖放操作，更新界面
        super().dropEvent(event)

        # 发出图层移动信号
        if source_index != target_index:
            self.layer_moved.emit(source_index, target_index)

        # 清理拖拽状态
        self.drag_insert_line_visible = False
        self.drag_insert_position = -1
        self.repaint()

    def dragMoveEvent(self, event):
        """拖拽移动事件，显示插入位置指示器"""
        super().dragMoveEvent(event)

        # 计算插入位置
        drop_item = self.itemAt(event.pos())
        if drop_item:
            insert_index = self.row(drop_item)
            # 根据鼠标位置确定是插入到项目上方还是下方
            item_rect = self.visualItemRect(drop_item)
            if event.pos().y() > item_rect.center().y():
                insert_index += 1

            # 更新插入位置指示器
            if insert_index != self.drag_insert_position:
                self.drag_insert_position = insert_index
                self.drag_insert_line_visible = True
                self.repaint()
        else:
            # 如果不在任何项目上，隐藏插入指示器
            if self.drag_insert_line_visible:
                self.drag_insert_line_visible = False
                self.repaint()

    def dragLeaveEvent(self, event):
        """拖拽离开事件，隐藏插入位置指示器"""
        super().dragLeaveEvent(event)

        if self.drag_insert_line_visible:
            self.drag_insert_line_visible = False
            # 使用repaint()替代update()避免方法冲突
            self.repaint()

    def paintEvent(self, event):
        """重写绘制事件，绘制插入位置指示器"""
        super().paintEvent(event)

        # 绘制插入位置指示器
        if self.drag_insert_line_visible and self.drag_insert_position >= 0:
            painter = QPainter(self.viewport())

            # 设置插入线样式
            insert_pen = QPen(QColor(0, 160, 230), 3, Qt.SolidLine)
            painter.setPen(insert_pen)

            # 计算插入线位置
            y_position = 0
            if self.drag_insert_position == 0:
                # 插入到第一个位置
                y_position = 0
            elif self.drag_insert_position > self.count():
                # 插入到最后位置
                if self.count() > 0:
                    last_item = self.item(self.count() - 1)
                    last_rect = self.visualItemRect(last_item)
                    y_position = last_rect.bottom()
                else:
                    y_position = 0
            else:
                # 插入到指定位置
                target_item = self.item(self.drag_insert_position)
                if target_item:
                    target_rect = self.visualItemRect(target_item)
                    y_position = target_rect.top()

            # 绘制插入线
            line_width = self.viewport().width() - 20
            painter.drawLine(10, y_position, 10 + line_width, y_position)

            # 绘制箭头指示器
            arrow_size = 6
            painter.setBrush(QBrush(QColor(0, 160, 230)))

            # 左箭头
            left_arrow = [
                QPoint(5, y_position),
                QPoint(5 + arrow_size, y_position - arrow_size // 2),
                QPoint(5 + arrow_size, y_position + arrow_size // 2)
            ]
            painter.drawPolygon(left_arrow)

            # 右箭头
            right_x = 15 + line_width
            right_arrow = [
                QPoint(right_x, y_position),
                QPoint(right_x - arrow_size, y_position - arrow_size // 2),
                QPoint(right_x - arrow_size, y_position + arrow_size // 2)
            ]
            painter.drawPolygon(right_arrow)


