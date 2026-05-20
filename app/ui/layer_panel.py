from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QListWidget, QListWidgetItem, QCheckBox,
                           QAbstractItemView, QInputDialog, QMenu, QApplication,
                           QDialog, QDialogButtonBox, QTextEdit, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QTimer, QRect, QPoint
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QDropEvent, QPen, QBrush
import sys
import os

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

class LayerItem(QWidget):
    """图层列表项组件"""

    def __init__(self, layer, index, panel=None):
        super().__init__()
        self.layer = layer
        self.index = index
        self.panel = panel  # 保存对LayerPanel的引用
        self.is_selected = False
        self.is_hovered = False

        # 设置初始样式
        self.setObjectName("layerItem")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(5, 3, 5, 3)
        layout.setSpacing(5)

        # 可见性切换按钮 - 改为使用按钮显示眼睛图标
        self.visibility_btn = QPushButton()
        self.visibility_btn.setFixedSize(18, 18)
        self.visibility_btn.setCheckable(True)
        self.visibility_btn.setChecked(layer.visible)
        self.visibility_btn.clicked.connect(self.toggle_visibility)
        self.visibility_btn.setObjectName("visibilityButton")
        self.update_visibility_icon()
        layout.addWidget(self.visibility_btn)

        # 锁定图标按钮
        self.lock_btn = QPushButton()
        self.lock_btn.setFixedSize(18, 18)
        self.lock_btn.setCheckable(True)
        self.lock_btn.setChecked(layer.locked)
        self.lock_btn.setObjectName("lockButton")
        self.update_lock_icon()
        self.lock_btn.clicked.connect(self.toggle_lock)
        layout.addWidget(self.lock_btn)

        # 绑定状态图标
        self.bind_label = QLabel()
        self.bind_label.setFixedSize(16, 16)
        self.bind_label.setObjectName("bindLabel")
        self.update_bind_icon()
        layout.addWidget(self.bind_label)

        # 图层名称
        layer_name = getattr(layer, 'name', f'图层 {index}')
        self.name_label = QLabel(layer_name)
        self.name_label.setObjectName("nameLabel")
        self.name_label.setMinimumHeight(16)
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.name_label.setWordWrap(False)
        self.name_label.setToolTip(layer_name)
        self.name_label.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        layout.addWidget(self.name_label)

        layout.addStretch()

        # 图层尺寸信息
        layer_width = getattr(layer, 'width', 0)
        layer_height = getattr(layer, 'height', 0)
        size_text = f"{layer_width}x{layer_height}"
        self.size_label = QLabel(size_text)
        self.size_label.setObjectName("sizeLabel")
        self.size_label.setMinimumHeight(16)
        self.size_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        layout.addWidget(self.size_label)

        # 应用样式并更新显示
        self.apply_style()
        self.update_labels()

        # 减少调试输出 - 只在调试模式下输出
        # print(f"创建UI图层项: 名称='{layer_name}', 尺寸='{size_text}'")

    def update_labels(self):
        """更新标签内容和样式 - 优化版本"""
        # 确保标签已创建
        if not (hasattr(self, 'name_label') and self.name_label and
                hasattr(self, 'size_label') and self.size_label):
            return

        # 获取当前显示的内容
        current_name = self.name_label.text()
        current_size = self.size_label.text()

        # 计算新的内容
        layer_name = getattr(self.layer, 'name', f'图层 {self.index}')
        layer_width = getattr(self.layer, 'width', 0)
        layer_height = getattr(self.layer, 'height', 0)
        size_text = f"{layer_width}x{layer_height}"

        # 只有内容实际发生变化时才更新
        content_changed = False

        if current_name != layer_name:
            self.name_label.setToolTip(layer_name)
            fm = self.name_label.fontMetrics()
            elided = fm.elidedText(layer_name, Qt.ElideMiddle, max(80, self.name_label.width()))
            self.name_label.setText(elided)
            content_changed = True

        if current_size != size_text:
            self.size_label.setText(size_text)
            content_changed = True

        # 更新图标状态（这些通常不需要频繁更新）
        self.update_visibility_icon()
        self.update_lock_icon()
        self.update_bind_icon()

        # 只有在内容发生变化或样式需要更新时才重新应用样式
        if content_changed or self.is_selected:
            self.apply_style()

        # 减少不必要的强制重绘
        if content_changed:
            self.name_label.update()
            self.size_label.update()
            self.update()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, 'name_label') and self.name_label:
            text = getattr(self.layer, 'name', f'图层 {self.index}')
            fm = self.name_label.fontMetrics()
            elided = fm.elidedText(text, Qt.ElideMiddle, max(80, self.name_label.width()))
            self.name_label.setText(elided)

        # 减少调试输出 - 只在内容实际变化时输出
        # if content_changed:
        #     print(f"更新UI标签: 名称='{layer_name}', 尺寸='{size_text}', 选中={self.is_selected}")

    def apply_style(self):
        """应用现代化样式，使用视觉层级管理器"""
        # 获取统一的颜色和样式
        vh = VisualHierarchy

        # 基础组件样式
        style = f"""
        QWidget#layerItem {{
            background: {'#253244' if self.is_selected else '#1F1F1F'};
            border: 1px solid {'#2F9CF4' if self.is_selected else '#303033'};
            border-radius: 5px;
            padding: 0px;
        }}

        QPushButton#visibilityButton {{
            background: transparent;
            border: 1px solid {vh.get_color('border', 'secondary')};
            border-radius: {vh.get_radius('sm')}px;
            color: {vh.get_color('text', 'secondary')};
            font-size: 12px;
            padding: 0px;
            min-width: 16px;
            min-height: 16px;
        }}

        QPushButton#visibilityButton:hover {{
            background: {vh.get_color('interactive', 'hover')};
            border: 1px solid {vh.get_color('border', 'focus')};
            color: {vh.get_color('text', 'primary')};
        }}

        QPushButton#visibilityButton:pressed {{
            background: {vh.get_color('interactive', 'active')};
            border: 1px solid {vh.get_color('border', 'focus')};
        }}

        QPushButton#visibilityButton:checked {{
            background: {vh.get_color('interactive', 'selected')};
            border: 1px solid {vh.get_color('border', 'focus')};
            color: {vh.get_color('text', 'primary')};
        }}

        QPushButton#lockButton {{
            background: transparent;
            border: 1px solid {vh.get_color('border', 'secondary')};
            border-radius: {vh.get_radius('sm')}px;
            color: {vh.get_color('text', 'secondary')};
            font-size: 12px;
            padding: 0px;
            min-width: 16px;
            min-height: 16px;
        }}

        QPushButton#lockButton:hover {{
            background: {vh.get_color('interactive', 'hover')};
            border: 1px solid {vh.get_color('border', 'focus')};
            color: {vh.get_color('text', 'primary')};
        }}

        QPushButton#lockButton:pressed {{
            background: {vh.get_color('interactive', 'active')};
            border: 1px solid {vh.get_color('border', 'focus')};
        }}

        QLabel#bindLabel {{
            background: transparent;
            color: {vh.get_color('primary', 'light')};
            font-size: 10px;
        }}
        """

        # 根据选中状态设置文字样式
        if self.is_selected:
            name_color = vh.get_color('text', 'primary')
            size_color = vh.get_color('primary', 'light')
            name_weight = 'bold'
        else:
            name_color = vh.get_color('text', 'secondary')
            size_color = vh.get_color('text', 'hint')
            name_weight = 'normal'

        style += f"""
        QLabel#nameLabel {{
            background: transparent;
            color: {name_color};
            font-family: "Microsoft YaHei", "SimHei", Arial, sans-serif;
            font-size: {vh.FONTS['body']['size']}px;
            font-weight: {name_weight};
            border: none;
            padding: 0px;
        }}

        QLabel#sizeLabel {{
            background: transparent;
            color: {size_color};
            font-family: "Microsoft YaHei", "SimHei", Arial, sans-serif;
            font-size: {vh.FONTS['small']['size']}px;
            font-weight: normal;
            border: none;
            padding: 0px;
        }}

        """

        # 应用字体（仅在标签存在时）
        if hasattr(self, 'name_label') and self.name_label:
            self.name_label.setFont(vh.get_font('body'))
        if hasattr(self, 'size_label') and self.size_label:
            self.size_label.setFont(vh.get_font('small'))

        self.setStyleSheet(style)

    def set_selected(self, selected):
        """设置选中状态"""
        if self.is_selected != selected:
            self.is_selected = selected
            self.update_appearance()
            # 减少调试输出 - 只在状态实际变化时输出
            # print(f"UI图层 {getattr(self.layer, 'name', '未知')} 选中状态变更: {selected}")

    def update_appearance(self):
        """更新外观状态"""
        # 重新应用样式（包含文字颜色的更新）
        self.apply_style()
        # 强制更新标签显示（仅在标签存在时）
        if hasattr(self, 'name_label') and self.name_label:
            self.name_label.update()
        if hasattr(self, 'size_label') and self.size_label:
            self.size_label.update()
        # 触发重绘以更新背景
        self.update()

    def enterEvent(self, event):
        """鼠标进入事件"""
        self.is_hovered = True
        # 触发重绘以显示悬浮效果
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        """鼠标离开事件"""
        self.is_hovered = False
        # 触发重绘以移除悬浮效果
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        """重写绘制事件，手动绘制选中和悬浮背景"""
        # 获取组件矩形
        rect = self.rect()

        # 如果有背景需要绘制，先绘制背景
        if self.is_selected or self.is_hovered:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)

            vh = VisualHierarchy

            if self.is_selected:
                # 选中状态：使用视觉层级的选中色
                background_color = QColor(vh.get_color('interactive', 'selected'))
                border_color = QColor(vh.get_color('border', 'focus'))
            else:  # is_hovered
                # 悬浮状态：使用视觉层级的悬浮色
                background_color = QColor(vh.get_color('interactive', 'hover'))
                border_color = QColor(vh.get_color('border', 'primary'))

            # 绘制圆角背景
            painter.setBrush(QBrush(background_color))
            painter.setPen(QPen(border_color, 1))
            painter.drawRoundedRect(
                rect.adjusted(vh.get_spacing('xs'), vh.get_spacing('xs'),
                             -vh.get_spacing('xs'), -vh.get_spacing('xs')),
                vh.get_radius('sm'), vh.get_radius('sm')
            )

            painter.end()

        # 调用基类的paintEvent以正常绘制所有子控件
        super().paintEvent(event)

    def toggle_visibility(self, checked):
        """切换图层可见性"""
        # 打印调试信息
        print(f"【调试】切换图层可见性: {self.layer.name}, 从 {self.layer.visible} 到 {checked}")

        # 保存当前状态
        if self.panel and hasattr(self.panel, 'document'):
            self.panel.document.save_state("切换图层可见性前")

            # 更新图层可见性
            self.layer.visible = checked

            # 更新可见性图标
            self.update_visibility_icon()

            # 直接通知文档已更改，确保画布重绘
            self.panel.document.document_changed.emit()
            print(f"【调试】已发送document_changed信号")

            # 如果有主窗口的画布引用，强制更新
            from app.main_window import MainWindow
            for widget in self.window().findChildren(QWidget):
                if isinstance(widget, MainWindow):
                    print(f"【调试】找到主窗口，尝试强制更新画布")
                    if hasattr(widget, 'canvas'):
                        widget.canvas.update()
                        print(f"【调试】已强制更新画布")

            # 保存更改后的状态
            self.panel.document.save_state("切换图层可见性")

    def toggle_lock(self):
        """切换图层锁定状态"""
        # 保存当前状态
        if self.panel and self.panel.document:
            self.panel.document.save_state("切换图层锁定状态前")

        # 更新图层锁定状态
        self.layer.locked = not self.layer.locked

        # 立即更新图标显示
        self.update_lock_icon()

        # 发送文档更改信号
        if self.panel and self.panel.document:
            self.panel.document.document_changed.emit()
            # 保存更改后的状态
            self.panel.document.save_state("切换图层锁定状态")

    def update_lock_icon(self):
        """更新锁定图标"""
        if self.layer.locked:
            # 锁定状态：使用图标管理器
            IconManager.apply_icon_to_button(self.lock_btn, 'lock', 'warning')
            self.lock_btn.setToolTip("图层已锁定 - 点击解锁")
        else:
            # 未锁定状态：使用图标管理器
            IconManager.apply_icon_to_button(self.lock_btn, 'unlock', 'secondary')
            self.lock_btn.setToolTip("图层未锁定 - 点击锁定")

        # 重新应用样式并触发重绘
        self.apply_style()
        self.update()

    def update_visibility_icon(self):
        """更新可见性图标"""
        if self.layer.visible:
            # 可见状态：使用图标管理器
            IconManager.apply_icon_to_button(self.visibility_btn, 'visible', 'primary')
            self.visibility_btn.setToolTip("图层可见 - 点击隐藏")
        else:
            # 隐藏状态：使用图标管理器
            IconManager.apply_icon_to_button(self.visibility_btn, 'hidden', 'secondary')
            self.visibility_btn.setToolTip("图层隐藏 - 点击显示")

        # 重新应用样式并触发重绘
        self.apply_style()
        self.update()

    def update_bind_icon(self):
        """更新绑定状态图标"""
        # 直接使用panel的document引用，避免遍历父组件
        document = self.panel.document if self.panel else None

        if not document or not hasattr(document, 'binding_manager'):
            # 隐藏绑定图标
            self.bind_label.setText("")
            self.bind_label.setStyleSheet("")
            self.bind_label.setToolTip("")
            return

        try:
            binding_info = document.binding_manager.get_layer_binding_info(self.layer)
            if binding_info:
                group_id, group_name = binding_info
                # 显示绑定图标
                icon_text = IconManager.get_icon_text('link')
                self.bind_label.setText(icon_text)
                self.bind_label.setAlignment(Qt.AlignCenter)
                self.bind_label.setStyleSheet("""
                    QLabel {
                        color: #2F9CF4;
                        font-weight: bold;
                        background-color: rgba(0, 122, 204, 0.1);
                        border: 1px solid #2F9CF4;
                        border-radius: 2px;
                    }
                """)
                tooltip = f"图层已绑定\\n绑定组: {group_name}"
                self.bind_label.setToolTip(tooltip)
            else:
                # 隐藏绑定图标
                self.bind_label.setText("")
                self.bind_label.setStyleSheet("")
                self.bind_label.setToolTip("")
        except Exception as e:
            print(f"更新绑定图标时出错: {e}")
            # 出错时隐藏图标
            self.bind_label.setText("")
            self.bind_label.setStyleSheet("")
            self.bind_label.setToolTip("")

class LayerPanel(QWidget):
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
        self._update_timer = QTimer()
        self._update_timer.setSingleShot(True)
        self._update_timer.timeout.connect(self._perform_update)
        self._update_pending = False
        self._updating = False  # 更新锁，防止级联更新
        self._binding_debug_timer = QTimer()
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

    def _is_export_ui_frozen(self):
        """导出期间是否冻结图层面板更新（由导出设置控制）"""
        doc = getattr(self, 'document', None)
        if not doc or not bool(getattr(doc, '_is_batch_export_running', False)):
            return False
        try:
            settings = getattr(doc, 'export_settings', {}) or {}
            return bool(settings.get('freeze_preview_during_export', False))
        except Exception:
            return False

    def _schedule_update(self):
        """安排延迟更新，实现防抖功能"""
        print(f"[图层面板] _schedule_update: 被调用，当前更新状态: {self._updating}")
        if self._is_export_ui_frozen():
            print(f"[图层面板] _schedule_update: 批量导出运行中，跳过UI更新调度")
            return

        if self._updating:
            print(f"[图层面板] _schedule_update: 正在更新中，忽略新请求")
            return  # 如果正在更新，忽略新的更新请求

        self._update_pending = True
        # 设置50ms的防抖延迟，多次连续调用只会执行最后一次
        self._update_timer.start(50)
        print(f"[图层面板] _schedule_update: 已开始50ms定时器")

    def _perform_update(self):
        """执行实际的UI更新"""
        print(f"[图层面板] _perform_update: 被调用，更新等待: {self._update_pending}")
        if self._is_export_ui_frozen():
            print(f"[图层面板] _perform_update: 批量导出运行中，跳过UI更新")
            return

        if not self._update_pending:
            print(f"[图层面板] _perform_update: 无更新等待，退出")
            return

        self._update_pending = False
        self._updating = True

        try:
            print(f"[图层面板] _perform_update: 开始调用update_layers")
            self.update_layers()
            print(f"[图层面板] _perform_update: update_layers完成")
        except Exception as e:
            print(f"[图层面板] _perform_update: update_layers异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._updating = False
            print(f"[图层面板] _perform_update: 更新完成，重置更新状态")

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(3)

        # 图层列表 - 使用自定义的支持拖放的列表组件
        self.layer_list = DragDropLayerList()
        self.layer_list.itemClicked.connect(self.layer_selected)
        self.layer_list.itemSelectionChanged.connect(self._on_layer_list_selection_changed)
        self.layer_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.layer_list.customContextMenuRequested.connect(self.show_context_menu)
        self.layer_list.layer_moved.connect(self.on_layer_moved)

        layout.addWidget(self.layer_list)

        # 按钮控制栏（固定高度，避免底部被挤压）
        self.button_bar = QWidget()
        self.button_bar.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.button_bar.setMinimumHeight(30)
        button_layout = QHBoxLayout(self.button_bar)
        button_layout.setContentsMargins(0, 0, 0, 0)
        button_layout.setSpacing(2)

        # 添加图层按钮
        self.add_btn = IconManager.create_icon_button('add', 16, 'primary', "添加新图层")
        self.add_btn.clicked.connect(self.add_layer)
        self._normalize_toolbar_button(self.add_btn)
        self._apply_button_style(self.add_btn, 'primary', icon_button=True)
        button_layout.addWidget(self.add_btn)

        # 删除图层按钮
        self.delete_btn = IconManager.create_icon_button('remove', 16, 'danger', "删除所选图层")
        self.delete_btn.clicked.connect(self.delete_layer)
        self._normalize_toolbar_button(self.delete_btn)
        self._apply_button_style(self.delete_btn, 'danger', icon_button=True)
        button_layout.addWidget(self.delete_btn)

        # 向上移动图层按钮
        self.up_btn = IconManager.create_icon_button('up', 16, 'secondary', "向上移动图层")
        self.up_btn.clicked.connect(self.move_layer_up)
        self._normalize_toolbar_button(self.up_btn)
        self._apply_button_style(self.up_btn, 'secondary', icon_button=True)
        button_layout.addWidget(self.up_btn)

        # 向下移动图层按钮
        self.down_btn = IconManager.create_icon_button('down', 16, 'secondary', "向下移动图层")
        self.down_btn.clicked.connect(self.move_layer_down)
        self._normalize_toolbar_button(self.down_btn)
        self._apply_button_style(self.down_btn, 'secondary', icon_button=True)
        button_layout.addWidget(self.down_btn)

        # 添加分割线
        button_layout.addItem(self._create_separator())

        # 随机化所有图层按钮 - 使用图标管理器
        self.random_btn = create_random_button()
        self.random_btn.setToolTip("随机化所有图层\n绑定的图层将选择匹配的图片")
        self._normalize_toolbar_button(self.random_btn)
        self._apply_button_style(self.random_btn, 'primary', icon_button=True)
        self.random_btn.clicked.connect(self.randomize_all)
        button_layout.addWidget(self.random_btn)

        # 绑定管理按钮 - 使用图标管理器
        self.binding_btn = IconManager.create_icon_button('link', 16, 'primary', "图层绑定管理器\n创建和管理图层绑定组")
        self.binding_btn.clicked.connect(self.open_binding_manager)
        self._normalize_toolbar_button(self.binding_btn)
        self._apply_button_style(self.binding_btn, 'primary', icon_button=True)
        button_layout.addWidget(self.binding_btn)

        # 图层大小匹配管理按钮 - 使用图标管理器保持一致
        self.size_match_btn = IconManager.create_icon_button('fit', 16, 'secondary', "图层大小匹配管理器\n配置镂空图层与下层图像的自动匹配")
        self.size_match_btn.clicked.connect(self.open_size_match_manager)
        self._normalize_toolbar_button(self.size_match_btn)
        self._apply_button_style(self.size_match_btn, 'secondary', icon_button=True)
        button_layout.addWidget(self.size_match_btn)

        # 调试模式：显示绑定调试面板开关
        self.binding_debug_toggle = None
        if self._binding_debug_mode:
            self.binding_debug_toggle = QCheckBox("调试:显示绑定匹配")
            self.binding_debug_toggle.setChecked(False)
            self.binding_debug_toggle.toggled.connect(self._toggle_binding_debug_panel)
            button_layout.addWidget(self.binding_debug_toggle)

        layout.addWidget(self.button_bar)

        # 调试模式：绑定调试面板（默认隐藏）
        self.binding_debug_panel = QWidget()
        debug_layout = QVBoxLayout(self.binding_debug_panel)
        debug_layout.setContentsMargins(0, 4, 0, 0)
        debug_layout.setSpacing(4)

        debug_toolbar = QHBoxLayout()
        debug_toolbar.addWidget(QLabel("绑定调试记录"))
        debug_toolbar.addStretch()

        self.binding_debug_clear_btn = QPushButton("清空")
        self.binding_debug_clear_btn.clicked.connect(self._clear_binding_debug_panel)
        self._apply_button_style(self.binding_debug_clear_btn, 'secondary')
        debug_toolbar.addWidget(self.binding_debug_clear_btn)
        debug_layout.addLayout(debug_toolbar)

        self.binding_debug_text = QTextEdit()
        self.binding_debug_text.setReadOnly(True)
        self.binding_debug_text.setMinimumHeight(120)
        self.binding_debug_text.setMaximumHeight(220)
        self.binding_debug_text.setPlaceholderText("调试模式下将显示每次绑定选择的分类与图层文件映射")
        debug_layout.addWidget(self.binding_debug_text)

        self.binding_debug_panel.setVisible(False)
        layout.addWidget(self.binding_debug_panel)

        # 应用面板级别的样式
        self._apply_panel_style()

    def _apply_button_style(self, button, variant='primary', icon_button=False):
        """为按钮应用统一的样式"""
        vh = VisualHierarchy

        if not icon_button:
            button.setFont(vh.get_font('button'))

        variant_colors = {
            'primary': vh.get_color('border', 'primary'),
            'secondary': vh.get_color('border', 'secondary'),
            'danger': vh.get_color('state', 'error')
        }
        accent = variant_colors.get(variant, vh.get_color('border', 'secondary'))
        text_color = vh.get_color('text', 'primary') if variant != 'danger' else vh.get_color('state', 'error')

        # 应用按钮样式
        if icon_button:
            style = f"""
            QPushButton {{
                background-color: {vh.get_color('background', 'secondary')};
                border: 1px solid {accent};
                color: {text_color};
                border-radius: {vh.get_radius('md')}px;
                padding: 0px;
            }}
            QPushButton:hover {{
                background-color: {vh.get_color('background', 'surface')};
                border: 1px solid {vh.get_color('border', 'focus')};
                color: {vh.get_color('text', 'primary')};
            }}
            QPushButton:pressed {{
                background-color: {vh.get_color('interactive', 'active')};
                border: 1px solid {accent};
                color: {vh.get_color('text', 'primary')};
            }}
            QPushButton:disabled {{
                background-color: {vh.get_color('background', 'primary')};
                border: 1px solid {vh.get_color('border', 'secondary')};
                color: {vh.get_color('text', 'disabled')};
            }}
            """
        elif variant == 'primary':
            style = f"""
            QPushButton {{
                background-color: {vh.get_color('background', 'secondary')};
                border: 1px solid {vh.get_color('border', 'primary')};
                color: {vh.get_color('text', 'primary')};
                border-radius: {vh.get_radius('md')}px;
                padding: {vh.get_spacing('sm')}px {vh.get_spacing('md')}px;
                min-width: 24px;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: {vh.get_color('background', 'surface')};
                border: 1px solid {vh.get_color('border', 'focus')};
                color: {vh.get_color('text', 'primary')};
            }}
            QPushButton:pressed {{
                background-color: {vh.get_color('primary', 'main')};
                border: 1px solid {vh.get_color('primary', 'dark')};
                color: {vh.get_color('primary', 'contrast')};
            }}
            QPushButton:disabled {{
                background-color: {vh.get_color('background', 'primary')};
                border: 1px solid {vh.get_color('border', 'secondary')};
                color: {vh.get_color('text', 'disabled')};
            }}
            """
        elif variant == 'secondary':
            style = f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {vh.get_color('border', 'secondary')};
                color: {vh.get_color('text', 'secondary')};
                border-radius: {vh.get_radius('md')}px;
                padding: {vh.get_spacing('sm')}px {vh.get_spacing('md')}px;
                min-width: 24px;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: {vh.get_color('interactive', 'hover')};
                border: 1px solid {vh.get_color('border', 'primary')};
                color: {vh.get_color('text', 'primary')};
            }}
            QPushButton:pressed {{
                background-color: {vh.get_color('interactive', 'active')};
                border: 1px solid {vh.get_color('border', 'focus')};
                color: {vh.get_color('text', 'primary')};
            }}
            QPushButton:disabled {{
                background-color: transparent;
                border: 1px solid {vh.get_color('border', 'secondary')};
                color: {vh.get_color('text', 'disabled')};
            }}
            """
        else:  # danger
            style = f"""
            QPushButton {{
                background-color: transparent;
                border: 1px solid {vh.get_color('state', 'error')};
                color: {vh.get_color('state', 'error')};
                border-radius: {vh.get_radius('md')}px;
                padding: {vh.get_spacing('sm')}px {vh.get_spacing('md')}px;
                min-width: 24px;
                min-height: 24px;
            }}
            QPushButton:hover {{
                background-color: {vh.get_color('state', 'error')};
                border: 1px solid {vh.get_color('state', 'error')};
                color: {vh.get_color('primary', 'contrast')};
            }}
            QPushButton:pressed {{
                background-color: #D32F2F;
                border: 1px solid #D32F2F;
                color: {vh.get_color('primary', 'contrast')};
            }}
            QPushButton:disabled {{
                background-color: transparent;
                border: 1px solid {vh.get_color('border', 'secondary')};
                color: {vh.get_color('text', 'disabled')};
            }}
            """

        button.setStyleSheet(style)

    def _normalize_toolbar_button(self, button):
        """统一底部工具按钮尺寸和图标字体，避免被挤压和风格不一致。"""
        size = 24
        button.setFixedSize(size, size)
        font = button.font()
        font.setFamily(IconManager.ICON_FONT_FAMILY)
        font.setPointSize(12)
        font.setBold(False)
        button.setFont(font)

    def _create_separator(self):
        """创建分割线"""
        from PySide6.QtWidgets import QSpacerItem, QSizePolicy
        return QSpacerItem(4, 1,
                          QSizePolicy.Fixed, QSizePolicy.Minimum)

    def _apply_panel_style(self):
        """应用面板级别的样式"""
        vh = VisualHierarchy

        # 设置图层列表样式
        list_style = f"""
        QListWidget {{
            background-color: {vh.get_color('background', 'primary')};
            border: 1px solid {vh.get_color('border', 'primary')};
            border-radius: 5px;
            padding: 3px;
            outline: none;
            selection-background-color: transparent;
        }}

        QListWidget::item {{
            background: transparent;
            border: none;
            padding: 0px;
            margin: 1px 0px;
            border-radius: 5px;
        }}

        QListWidget::item:selected {{
            background: transparent;
            border: none;
        }}

        QListWidget::item:hover {{
            background: transparent;
        }}

        QListWidget::item:focus {{
            background: transparent;
            outline: none;
        }}
        """

        self.layer_list.setStyleSheet(list_style)

        # 设置标签样式
        label_style = f"""
        QLabel {{
            color: {vh.get_color('text', 'primary')};
            font-size: {vh.FONTS['body']['size']}px;
            font-weight: 700;
            margin: {vh.get_spacing('sm')}px 0px;
            background: transparent;
        }}
        """

        # 应用到所有标签
        for label in self.findChildren(QLabel):
            if label.objectName() not in ['nameLabel', 'sizeLabel', 'bindLabel']:  # 排除图层项目中的标签
                label.setFont(vh.get_font('body'))
                label.setStyleSheet(label_style)

    def update_layers(self):
        """更新图层列表 - 优化版本"""
        if self._is_export_ui_frozen():
            print("[图层面板] update_layers: 批量导出运行中，跳过更新")
            return
        # 如果没有文档，清空列表并禁用控件
        if not self.document:
            print("[图层面板] update_layers: 文档为None，清空列表")
            self.layer_list.clear()
            self._set_controls_enabled(False)
            return

        if not self.document.layers:
            print("[图层面板] update_layers: 文档无图层，清空列表")
            self.layer_list.clear()
            self._set_controls_enabled(False)
            return

        print(f"[图层面板] update_layers: 文档图层数={len(self.document.layers)}, 列表项数={self.layer_list.count()}")

        # 当前选中的图层索引（支持多选，首选图层作为主选中）
        selected_indices = self._sanitize_selected_indices()
        selected_index = selected_indices[0] if selected_indices else -1
        print(f"[图层面板] update_layers: 选中图层索引={selected_indices}")

        # 尝试增量更新而非完整重建
        can_incremental = self._can_incremental_update()
        print(f"[图层面板] update_layers: 能否增量更新={can_incremental}")

        if can_incremental:
            print("[图层面板] update_layers: 执行增量更新")
            self._incremental_update(selected_indices, selected_index)
        else:
            print("[图层面板] update_layers: 执行完整重建")
            self._full_rebuild(selected_indices, selected_index)

        print(f"[图层面板] update_layers: 更新完成，列表项数={self.layer_list.count()}")

        # 启用控件
        self._set_controls_enabled(True)

        # 延迟刷新图标状态，确保所有组件都已正确创建
        QTimer.singleShot(50, self.refresh_all_icons)

    def _can_incremental_update(self):
        """判断是否可以进行增量更新"""
        # 如果图层数量没有变化，可以尝试增量更新
        return len(self.document.layers) == self.layer_list.count()

    def _incremental_update(self, selected_indices, primary_index):
        """增量更新图层列表"""
        selected_set = set(selected_indices)
        self._selection_sync_in_progress = True
        # 只更新必要的属性，不重新创建所有项
        try:
            for i in range(self.layer_list.count()):
                list_item = self.layer_list.item(i)
                layer_widget = self.layer_list.itemWidget(list_item)

                if layer_widget:
                    # 计算真实图层索引
                    real_index = len(self.document.layers) - 1 - i

                    if 0 <= real_index < len(self.document.layers):
                        # 更新图层数据引用
                        layer_widget.layer = self.document.layers[real_index]
                        layer_widget.index = real_index

                        # 更新选中状态
                        is_selected = real_index in selected_set
                        if layer_widget.is_selected != is_selected:
                            layer_widget.set_selected(is_selected)
                        list_item.setSelected(is_selected)

                        # 更新图层显示信息（但不重新创建UI）
                        layer_widget.update_labels()

                        # 如果是主选中的图层，设置为当前项
                        if real_index == primary_index:
                            self.layer_list.setCurrentItem(list_item)
                            self.layer_list.scrollToItem(list_item)
        finally:
            self._selection_sync_in_progress = False

    def _full_rebuild(self, selected_indices, primary_index):
        """完整重建图层列表"""
        print(f"[图层面板] _full_rebuild: 开始重建，图层数={len(self.document.layers)}")
        selected_set = set(selected_indices)

        # 清空现有列表
        self.layer_list.clear()
        print(f"[图层面板] _full_rebuild: 已清空列表")

        # 从顶部到底部填充列表 (界面中最上面的图层是列表索引0)
        self._selection_sync_in_progress = True
        try:
            for i, layer in enumerate(reversed(self.document.layers)):
            # 计算逆序之后的真实索引
                real_index = len(self.document.layers) - 1 - i
                print(f"[图层面板] _full_rebuild: 创建图层项 {i}: {layer.name} (真实索引={real_index})")

                try:
                    # 创建列表项
                    item = QListWidgetItem()

                    # 创建自定义小部件
                    widget = LayerItem(layer, real_index, self)

                    # 设置项目大小
                    item.setSizeHint(widget.sizeHint())

                    # 添加到列表
                    self.layer_list.addItem(item)
                    self.layer_list.setItemWidget(item, widget)
                    print(f"[图层面板] _full_rebuild: 已添加图层项到列表，当前列表项数={self.layer_list.count()}")

                    # 设置选中状态（支持多选）
                    is_selected = real_index in selected_set
                    widget.set_selected(is_selected)
                    item.setSelected(is_selected)

                    # 如果是主选中的图层，设置为当前项
                    if real_index == primary_index:
                        self.layer_list.setCurrentItem(item)
                        # 滚动到选中的图层
                        self.layer_list.scrollToItem(item)
                        print(f"[图层面板] _full_rebuild: 设置图层 {layer.name} 为主选中状态")

                except Exception as e:
                    print(f"[图层面板] _full_rebuild: 创建图层项时出错: {e}")
                    import traceback
                    traceback.print_exc()
        finally:
            self._selection_sync_in_progress = False

        print(f"[图层面板] _full_rebuild: 重建完成，列表项数={self.layer_list.count()}")

        # 如果有选中的图层，更新界面
        if primary_index >= 0 and primary_index < len(self.document.layers):
            print(f"[图层面板] _full_rebuild: 图层已选中: {self.document.layers[primary_index].name}")

    def layer_selected(self, item):
        """图层选中事件处理"""
        # 如果没有文档，不做任何处理
        if not self.document:
            print("警告: document为空，无法处理图层选择")
            return

        # 获取点击图层的实际索引（列表显示顺序与文档顺序相反）
        display_index = self.layer_list.row(item)
        actual_index = len(self.document.layers) - display_index - 1
        if not (0 <= actual_index < len(self.document.layers)):
            return

        modifiers = QApplication.keyboardModifiers()
        current_selected = set(self._get_selected_indices_from_ui())

        if modifiers & Qt.ControlModifier:
            # Ctrl：追加/取消选择，保持首选图层顺序
            if actual_index in current_selected and actual_index not in self._selected_layer_indices:
                self._selected_layer_indices.append(actual_index)
            elif actual_index not in current_selected:
                self._selected_layer_indices = [idx for idx in self._selected_layer_indices if idx != actual_index]
        elif modifiers & Qt.ShiftModifier:
            # Shift：范围选择，已有顺序保持在前，新选中的追加
            ordered_existing = [idx for idx in self._selected_layer_indices if idx in current_selected]
            for idx in self._ordered_selected_indices_from_ui():
                if idx not in ordered_existing:
                    ordered_existing.append(idx)
            self._selected_layer_indices = ordered_existing
        else:
            # 普通点击：重置为单选
            self._selected_layer_indices = [actual_index]

        self._selected_layer_indices = self._sanitize_selected_indices()
        self._refresh_layer_widgets_selection()
        self._sync_primary_selection_to_document()
        self._update_selected_layer_controls()

    def add_layer(self):
        """添加新图层 - 直接添加默认图层，无弹窗"""
        if self.document.canvas_width == 0 or self.document.canvas_height == 0:
            return

        try:
            # 直接调用文档的add_layer方法，传递所需参数
            layer_name = f"图层 {len(self.document.layers) + 1}"

            # 调用文档的add_layer方法，传递所需的参数
            layer = self.document.add_layer(
                name=layer_name,
                x=0,
                y=0,
                width=200,
                height=200,
                image_source=None,
                use_original_size=False,
                is_folder=True
            )

            # 更新UI
            self._schedule_update()

        except Exception as e:
            print(f"添加图层时出错: {e}")

    def get_selected_indices(self):
        """获取选中的图层索引列表"""
        if self.document is None:
            return []
        doc_selection = getattr(self.document, 'selected_layer_indices', [])
        if doc_selection:
            return list(doc_selection)
        if self._selected_layer_indices:
            return list(self._selected_layer_indices)
        if self.document.selected_layer_index >= 0:
            return [self.document.selected_layer_index]
        return []

    def _ordered_selected_indices_from_ui(self):
        """按列表显示顺序获取选中的实际图层索引。"""
        selected = []
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item and item.isSelected():
                actual = len(self.document.layers) - i - 1
                if 0 <= actual < len(self.document.layers):
                    selected.append(actual)
        return selected

    def _get_selected_indices_from_ui(self):
        """获取当前UI选中的图层索引集合。"""
        return self._ordered_selected_indices_from_ui()

    def _sanitize_selected_indices(self):
        """过滤无效索引并在必要时回退到文档主选中图层。"""
        if not self.document:
            self._selected_layer_indices = []
            return []
        max_index = len(self.document.layers) - 1
        sanitized = []
        for idx in self._selected_layer_indices:
            if 0 <= idx <= max_index and idx not in sanitized:
                sanitized.append(idx)
        if not sanitized and 0 <= self.document.selected_layer_index <= max_index:
            sanitized = [self.document.selected_layer_index]
        self._selected_layer_indices = sanitized
        return sanitized

    def _refresh_layer_widgets_selection(self):
        """同步列表项和自定义图层项的选中高亮状态。"""
        if not self.document:
            return
        selected_set = set(self._selected_layer_indices)
        self._selection_sync_in_progress = True
        try:
            for i in range(self.layer_list.count()):
                list_item = self.layer_list.item(i)
                widget = self.layer_list.itemWidget(list_item)
                actual = len(self.document.layers) - i - 1
                is_selected = actual in selected_set
                if list_item is not None:
                    list_item.setSelected(is_selected)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(is_selected)
        finally:
            self._selection_sync_in_progress = False

    def _sync_primary_selection_to_document(self):
        """将首选图层同步给文档，保持与现有单选逻辑兼容。"""
        if not self.document:
            return
        primary_index = self._selected_layer_indices[0] if self._selected_layer_indices else -1
        current_selection = list(getattr(self.document, 'selected_layer_indices', []))
        if primary_index != self.document.selected_layer_index or current_selection != self._selected_layer_indices:
            self._selection_sync_in_progress = True
            try:
                if hasattr(self.document, 'select_layers'):
                    self.document.select_layers(self._selected_layer_indices, primary_index=primary_index)
                else:
                    self.document.select_layer(primary_index)
            finally:
                self._selection_sync_in_progress = False

    def _update_selected_layer_controls(self):
        """根据当前主选中图层刷新控制区状态。"""
        if not self.document or not self._selected_layer_indices:
            self.selected_layer = None
            self.delete_btn.setEnabled(False)
            self.up_btn.setEnabled(False)
            self.down_btn.setEnabled(False)
            return

        primary_index = self._selected_layer_indices[0]
        if not (0 <= primary_index < len(self.document.layers)):
            return

        self.selected_layer = self.document.layers[primary_index]

        self.delete_btn.setEnabled(not self.selected_layer.locked)
        self.up_btn.setEnabled(primary_index > 0 and not self.selected_layer.locked)
        self.down_btn.setEnabled(primary_index < len(self.document.layers) - 1 and not self.selected_layer.locked)

    def _on_layer_list_selection_changed(self):
        """处理列表选择变化（键盘选择、程序同步等场景）。"""
        if self._selection_sync_in_progress or not self.document:
            return
        ui_selected = self._ordered_selected_indices_from_ui()
        if not ui_selected:
            self._selected_layer_indices = []
            self._update_selected_layer_controls()
            return

        # 保留已存在选择顺序，将新选择追加到末尾
        ordered_existing = [idx for idx in self._selected_layer_indices if idx in ui_selected]
        for idx in ui_selected:
            if idx not in ordered_existing:
                ordered_existing.append(idx)
        self._selected_layer_indices = ordered_existing

        self._refresh_layer_widgets_selection()
        self._sync_primary_selection_to_document()
        self._update_selected_layer_controls()

    def select_all_layers(self):
        """选择当前文档中的所有图层。"""
        if not self.document:
            return
        self._selected_layer_indices = list(range(len(self.document.layers)))
        self._refresh_layer_widgets_selection()
        self._sync_primary_selection_to_document()
        self._update_selected_layer_controls()

    def select_layer(self, index):
        """选择单个图层，供控制器和旧调用路径使用。"""
        if not self.document or not (0 <= index < len(self.document.layers)):
            return
        self._selected_layer_indices = [index]
        self._refresh_layer_widgets_selection()
        self._sync_primary_selection_to_document()
        self._update_selected_layer_controls()

    def delete_layer(self):
        """删除选中的图层，支持多选并跳过锁定图层。"""
        if not self.document:
            return
        selected_indices = [
            idx for idx in self.get_selected_indices()
            if 0 <= idx < len(self.document.layers) and not getattr(self.document.layers[idx], 'locked', False)
        ]
        if not selected_indices:
            return
        self.document.save_state("批量删除图层前" if len(selected_indices) > 1 else "删除图层前")
        for idx in sorted(selected_indices, reverse=True):
            layer_to_remove = self.document.layers[idx]
            if hasattr(self.document, 'binding_manager') and self.document.binding_manager:
                self.document.binding_manager.remove_layer_from_group(layer_to_remove)
            del self.document.layers[idx]
        fallback = min(min(selected_indices), len(self.document.layers) - 1) if self.document.layers else -1
        if hasattr(self.document, 'select_layers'):
            self.document.select_layers([fallback] if fallback >= 0 else [])
        else:
            self.document.selected_layer_index = fallback
        self.document.document_changed.emit()
        self.document.layer_changed.emit()
        self.document.save_state("批量删除图层" if len(selected_indices) > 1 else "删除图层")

    def move_layer_up(self):
        """上移图层"""
        if self.document.selected_layer_index > 0:
            # 交换当前图层和上一个图层的位置
            from_index = self.document.selected_layer_index
            to_index = from_index - 1
            self.document.move_layer(from_index, to_index)
            self._schedule_update()

    def move_layer_down(self):
        """下移图层"""
        if self.document.selected_layer_index < len(self.document.layers) - 1:
            # 交换当前图层和下一个图层的位置
            from_index = self.document.selected_layer_index
            to_index = from_index + 1
            self.document.move_layer(from_index, to_index)
            self._schedule_update()

    def randomize_all(self):
        """随机化所有图层"""
        if self.document:
            self.document.randomize_all_layers()
            # 随机化后刷新绑定状态显示
            self.refresh_binding_status()
            self._refresh_binding_debug_panel(force=True)

    def open_binding_manager(self):
        """打开绑定管理器"""
        if not self.document:
            return

        try:
            from app.ui.binding_manager_dialog import LayerBindingManagerDialog
            dialog = LayerBindingManagerDialog(self.document, self)
            result = dialog.exec()

            # 刷新图层显示（更新绑定状态）
            self._schedule_update()
            # 强制更新所有图层项的绑定状态
            self.refresh_binding_status()
            self._refresh_binding_debug_panel(force=True)

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"打开绑定管理器时出错: {str(e)}")
            print(f"打开绑定管理器出错: {e}")

    def open_size_match_manager(self):
        """打开图层大小匹配管理器"""
        if not self.document:
            return
        try:
            from app.ui.layer_size_match_dialog import LayerSizeMatchDialog
            dialog = LayerSizeMatchDialog(self.document, self)
            dialog.exec()
            self._schedule_update()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"打开图层大小匹配管理器时出错: {str(e)}")
            print(f"打开图层大小匹配管理器出错: {e}")

    def _toggle_binding_debug_panel(self, enabled: bool):
        """切换绑定调试面板显示（仅调试模式可见）。"""
        if not self._binding_debug_mode:
            return
        self.binding_debug_panel.setVisible(bool(enabled))

        binding_manager = getattr(self.document, 'binding_manager', None) if self.document else None
        if binding_manager and hasattr(binding_manager, 'set_debug_trace_enabled'):
            binding_manager.set_debug_trace_enabled(bool(enabled))

        if enabled:
            self._refresh_binding_debug_panel(force=True)
            self._binding_debug_timer.start()
        else:
            self._binding_debug_timer.stop()

    def _clear_binding_debug_panel(self):
        """清空绑定调试记录。"""
        binding_manager = getattr(self.document, 'binding_manager', None) if self.document else None
        if binding_manager and hasattr(binding_manager, 'clear_debug_traces'):
            binding_manager.clear_debug_traces()
        self._binding_debug_last_text = ""
        if hasattr(self, 'binding_debug_text') and self.binding_debug_text:
            self.binding_debug_text.clear()

    def _refresh_binding_debug_panel(self, force: bool = False):
        """刷新绑定调试面板内容。"""
        if not self._binding_debug_mode:
            return
        if not hasattr(self, 'binding_debug_panel') or not self.binding_debug_panel.isVisible():
            return

        binding_manager = getattr(self.document, 'binding_manager', None) if self.document else None
        if not binding_manager or not hasattr(binding_manager, 'get_debug_trace_text'):
            return

        try:
            debug_text = binding_manager.get_debug_trace_text(limit=120)
            if force or debug_text != self._binding_debug_last_text:
                self.binding_debug_text.setPlainText(debug_text)
                self.binding_debug_last_text = debug_text
                cursor = self.binding_debug_text.textCursor()
                cursor.movePosition(cursor.End)
                self.binding_debug_text.setTextCursor(cursor)
        except Exception as e:
            print(f"[图层面板] 刷新绑定调试面板失败: {e}")

    def refresh_binding_status(self):
        """刷新所有图层项的绑定状态显示"""
        try:
            for i in range(self.layer_list.count()):
                item = self.layer_list.item(i)
                if item:
                    widget = self.layer_list.itemWidget(item)
                    if isinstance(widget, LayerItem):
                        widget.update_bind_icon()
                        widget.update_lock_icon()  # 同时刷新锁定图标
        except Exception as e:
            print(f"刷新绑定状态时出错: {e}")

    def refresh_all_icons(self):
        """刷新所有图层项的图标状态"""
        if self._is_export_ui_frozen():
            print("[图层面板] refresh_all_icons: 批量导出运行中，跳过图标刷新")
            return
        try:
            for i in range(self.layer_list.count()):
                item = self.layer_list.item(i)
                if item:
                    widget = self.layer_list.itemWidget(item)
                    if isinstance(widget, LayerItem):
                        # 强制刷新所有图标状态
                        widget.update_bind_icon()
                        widget.update_lock_icon()
                        widget.update_visibility_icon()
                        # 确保可见性按钮状态正确
                        widget.visibility_btn.setChecked(widget.layer.visible)
        except Exception as e:
            print(f"刷新所有图标时出错: {e}")

    def show_context_menu(self, position):
        """显示图层右键菜单"""
        if not self.document or not self.layer_list.count():
            return

        menu = QMenu()

        # 获取当前选中项
        item = self.layer_list.itemAt(position)
        if not item:
            # 如果没有点击在图层项上，提供有限选项
            add_action = menu.addAction("添加图层")

            # 如果有剪贴板内容，允许粘贴
            paste_action = None
            if self._get_main_window() and hasattr(self._get_main_window(), 'layer_clipboard') and self._get_main_window().layer_clipboard:
                paste_action = menu.addAction("粘贴图层")

            action = menu.exec_(self.layer_list.mapToGlobal(position))
            if action == add_action:
                self.add_layer()
            elif paste_action and action == paste_action:
                self._paste_layer()
            return

        # 确定图层索引（不自动选中，保持当前选中状态）
        index = self.layer_list.row(item)
        actual_index = len(self.document.layers) - index - 1  # 转换为实际图层索引

        # 获取右键点击的图层实例（不改变当前选中状态）
        layer = self.document.layers[actual_index]

        # 基础操作
        rename_action = menu.addAction("重命名")

        menu.addSeparator()

        selected_indices = self.get_selected_indices()
        has_multi_selection = len(selected_indices) > 1
        if has_multi_selection:
            multi_menu = menu.addMenu(f"多图层操作 ({len(selected_indices)})")
            show_selected_action = multi_menu.addAction("显示选中图层")
            hide_selected_action = multi_menu.addAction("隐藏选中图层")
            multi_menu.addSeparator()
            lock_selected_action = multi_menu.addAction("锁定选中图层")
            unlock_selected_action = multi_menu.addAction("解锁选中图层")
            multi_menu.addSeparator()
            distribute_h_action = multi_menu.addAction("水平等距分布")
            distribute_v_action = multi_menu.addAction("垂直等距分布")
            multi_menu.addSeparator()
            same_size_action = multi_menu.addAction("匹配首选图层尺寸")
        else:
            show_selected_action = None
            hide_selected_action = None
            lock_selected_action = None
            unlock_selected_action = None
            distribute_h_action = None
            distribute_v_action = None
            same_size_action = None

        # 复制粘贴操作
        copy_action = menu.addAction("复制图层")

        # 检查是否有剪贴板内容
        main_window = self._get_main_window()
        paste_action = None
        if main_window and hasattr(main_window, 'layer_clipboard') and main_window.layer_clipboard:
            paste_action = menu.addAction("粘贴图层")

        menu.addSeparator()

        # 图层样式操作
        copy_style_action = menu.addAction("复制图层样式")

        # 检查是否有样式剪贴板内容
        paste_style_action = None
        if main_window and hasattr(main_window, 'layer_style_clipboard') and main_window.layer_style_clipboard:
            paste_style_action = menu.addAction("粘贴图层样式")

        menu.addSeparator()

        # 图层操作
        delete_action = menu.addAction("删除图层")

        menu.addSeparator()

        # 随机与锁定
        randomize_action = menu.addAction("随机更换图像")
        randomize_action.setToolTip("同名图层将选择相同核心名称的图片")

        lock_action = menu.addAction("锁定图层" if not layer.locked else "解锁图层")

        menu.addSeparator()

        # 图层效果选项
        effects_action = menu.addAction("编辑图层效果...")

        # 异形图层编辑选项
        try:
            from app.models.shaped_layer_new import ShapedLayer
        except ImportError:
            from app.models.shaped_layer import ShapedLayer
        if isinstance(layer, ShapedLayer):
            shaped_action = menu.addAction("编辑异形图层...")

        # 执行菜单并获取所选操作
        action = menu.exec_(self.layer_list.mapToGlobal(position))

        # 处理用户选择（操作被右键点击的图层，不改变当前选中状态）
        if action == rename_action:
            self.rename_layer_at_index(actual_index)
        elif has_multi_selection and action == show_selected_action:
            self.set_selected_layers_visible(True)
        elif has_multi_selection and action == hide_selected_action:
            self.set_selected_layers_visible(False)
        elif has_multi_selection and action == lock_selected_action:
            self.set_selected_layers_locked(True)
        elif has_multi_selection and action == unlock_selected_action:
            self.set_selected_layers_locked(False)
        elif has_multi_selection and action == distribute_h_action:
            self.align_layers("distribute_horizontal")
        elif has_multi_selection and action == distribute_v_action:
            self.align_layers("distribute_vertical")
        elif has_multi_selection and action == same_size_action:
            self.align_layers("same_size")
        elif action == copy_action:
            self._copy_layer_at_index(actual_index)
        elif paste_action and action == paste_action:
            self._paste_layer()
        elif action == copy_style_action:
            self._copy_layer_style_at_index(actual_index)
        elif paste_style_action and action == paste_style_action:
            self._paste_layer_style_at_index(actual_index)
        elif action == delete_action:
            self.delete_layer_at_index(actual_index)
        elif action == randomize_action:
            self.randomize_layer_at_index(actual_index)
        elif action == lock_action:
            self.toggle_layer_lock_at_index(actual_index)
        elif action == effects_action:
            self.edit_layer_effects_at_index(actual_index)
        elif 'shaped_action' in locals() and action == shaped_action:
            self.edit_shaped_layer_at_index(actual_index)

    def edit_shaped_layer_at_index(self, index):
        """编辑指定索引的异形图层"""
        try:
            if not self.document or index < 0 or index >= len(self.document.layers):
                return

            layer = self.document.layers[index]
            if not isinstance(layer, ShapedLayer):
                return

            # 选中该图层，属性面板会自动显示异形图层控件
            self.document.selected_layer_index = index

            # 获取主窗口并确保属性面板可见
            main_window = self._get_main_window()
            if main_window and hasattr(main_window, 'properties_dock'):
                main_window.properties_dock.show()
                main_window.properties_dock.raise_()

        except Exception as e:
            print(f"编辑异形图层时出错: {e}")

    def _get_main_window(self):
        """获取主窗口引用"""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'layer_clipboard'):  # 主窗口特征
                return parent
            parent = parent.parent()
        return None

    def _copy_layer(self):
        """复制图层"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'copy_layer'):
            main_window.copy_layer()

    def _paste_layer(self):
        """粘贴图层"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'paste_layer'):
            main_window.paste_layer()

    def _copy_layer_style(self):
        """复制图层样式"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'copy_layer_style'):
            main_window.copy_layer_style()

    def _paste_layer_style(self):
        """粘贴图层样式"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'paste_layer_style'):
            main_window.paste_layer_style()

    def rename_layer(self):
        """重命名图层"""
        if self.document.selected_layer_index < 0:
            return

        layer = self.document.layers[self.document.selected_layer_index]

        new_name, ok = QInputDialog.getText(self, "重命名图层",
                                          "图层名称:", text=layer.name)
        if ok and new_name:
            layer.name = new_name
            self._schedule_update()

    def randomize_layer(self):
        """随机化选中的图层图像"""
        if self.document.selected_layer_index < 0:
            return

        layer = self.document.layers[self.document.selected_layer_index]
        self._randomize_single_layer_with_restrictions(layer)
        self.document.document_changed.emit()

    def edit_layer_effects(self):
        if self.document.selected_layer_index < 0:
            return
        from app.ui.layer_effects_dialog import LayerEffectsDialog
        dialog = LayerEffectsDialog(self.document, self)
        if dialog.exec():
            self.document.document_changed.emit()

    def edit_layer_effects_at_index(self, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return
        original_selected_index = self.document.selected_layer_index
        self.document.selected_layer_index = layer_index
        try:
            from app.ui.layer_effects_dialog import LayerEffectsDialog
            dialog = LayerEffectsDialog(self.document, self)
            if dialog.exec():
                self.document.document_changed.emit()
        finally:
            self.document.selected_layer_index = original_selected_index

    def edit_shaped_layer_at_index(self, layer_index):
        """编辑指定索引的异形图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        try:
            from app.models.shaped_layer_new import ShapedLayer
        except ImportError:
            from app.models.shaped_layer import ShapedLayer

        layer = self.document.layers[layer_index]
        if not isinstance(layer, ShapedLayer):
            return

        original_selected_index = self.document.selected_layer_index
        self.document.selected_layer_index = layer_index
        try:
            from app.ui.shaped_layer_panel import ShapedLayerDialog
            dialog = ShapedLayerDialog(layer, self)
            if dialog.exec():
                self.document.document_changed.emit()
        finally:
            self.document.selected_layer_index = original_selected_index

    def rename_layer_at_index(self, layer_index):
        """重命名指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        layer = self.document.layers[layer_index]
        main_window = self._get_main_window()
        if main_window:
            # 临时选中要重命名的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.rename_layer()
            finally:
                self.document.selected_layer_index = original_selected_index

    def _copy_layer_at_index(self, layer_index):
        """复制指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        main_window = self._get_main_window()
        if main_window:
            # 临时选中要复制的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.copy_layer()
            finally:
                self.document.selected_layer_index = original_selected_index

    def _copy_layer_style_at_index(self, layer_index):
        """复制指定索引图层的样式"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        main_window = self._get_main_window()
        if main_window:
            # 临时选中要复制样式的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.copy_layer_style()
            finally:
                self.document.selected_layer_index = original_selected_index

    def _paste_layer_style_at_index(self, layer_index):
        """粘贴样式到指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        main_window = self._get_main_window()
        if main_window:
            # 临时选中要粘贴样式的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.paste_layer_style()
            finally:
                self.document.selected_layer_index = original_selected_index

    def delete_layer_at_index(self, layer_index):
        """删除指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        main_window = self._get_main_window()
        if main_window:
            # 临时选中要删除的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.delete_layer()
            finally:
                # 删除后不需要恢复选中状态，因为图层已被删除
                pass

    def randomize_layer_at_index(self, layer_index):
        """随机化指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        layer = self.document.layers[layer_index]
        self._randomize_single_layer_with_restrictions(layer)
        self.document.document_changed.emit()

    def _randomize_single_layer_with_restrictions(self, layer):
        """使用文件限制随机化单个图层"""
        try:
            # 检查是否是文字图层
            from app.models.text_layer import TextLayer
            if isinstance(layer, TextLayer):
                layer.randomize_text()
                print(f"[图层面板] 随机化文字图层: {layer.name}")
                return

            # 普通图层处理
            # 首先确保绑定管理器分析了文件限制
            if hasattr(self.document, 'binding_manager') and self.document.binding_manager.global_enabled:
                print(f"[图层面板] 为单图层随机化分析文件限制...")
                self.document.binding_manager.analyze_and_restrict_layer_files(self.document.layers)

                # 检查是否是绑定图层
                if self.document.binding_manager.is_layer_bound(layer):
                    print(f"[图层面板] 图层 '{layer.name}' 是绑定图层，使用绑定组随机化")
                    # 绑定图层：使用绑定管理器处理
                    bound_layers_mapping = self.document.binding_manager.randomize_bound_layers(self.document.layers)
                    if id(layer) in bound_layers_mapping:
                        print(f"[图层面板] 绑定图层 '{layer.name}' 已更新")
                    else:
                        print(f"[图层面板] 警告：绑定图层 '{layer.name}' 未在绑定结果中")
                else:
                    # 非绑定图层：使用文件限制
                    restricted_files = self.document.binding_manager.get_layer_file_restrictions(layer)
                    if restricted_files:
                        print(f"[图层面板] 图层 '{layer.name}' 使用文件限制随机化，可选文件: {len(restricted_files)} 个")
                        layer.get_random_image(force_random=True, restrict_to_bound_files=restricted_files)
                    else:
                        print(f"[图层面板] 图层 '{layer.name}' 无文件限制，正常随机化")
                        layer.get_random_image(force_random=True)
            else:
                # 没有绑定管理器或未启用，正常随机化
                print(f"[图层面板] 图层 '{layer.name}' 正常随机化（无绑定管理器）")
                layer.get_random_image(force_random=True)

        except Exception as e:
            print(f"[图层面板] 随机化图层 '{layer.name}' 时出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时回退到正常随机化
            layer.get_random_image(force_random=True)

    def toggle_layer_lock_at_index(self, layer_index):
        """切换指定索引图层的锁定状态"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        layer = self.document.layers[layer_index]
        layer.locked = not layer.locked
        self.document.document_changed.emit()
        self._schedule_update()

    def toggle_layer_lock(self):
        """切换当前选中图层的锁定状态"""
        if self.document.selected_layer_index < 0:
            return

        layer = self.document.layers[self.document.selected_layer_index]
        layer.locked = not layer.locked

        # 通知文档已更改
        self.document.document_changed.emit()

        # 更新图层列表
        self._schedule_update()

    def on_layer_moved(self, source_index, target_index):
        """处理图层拖放移动"""
        # 计算实际的图层索引（界面索引和数据索引是相反的）
        layer_count = len(self.document.layers)
        source_actual_index = layer_count - source_index - 1
        target_actual_index = layer_count - target_index - 1
        selected_indices = self.get_selected_indices()

        if source_actual_index in selected_indices and len(selected_indices) > 1:
            selected_indices = [
                idx for idx in selected_indices
                if 0 <= idx < len(self.document.layers) and not getattr(self.document.layers[idx], 'locked', False)
            ]
            if not selected_indices:
                return
            self.document.save_state("批量拖放重排序图层前")
            selected_objects = [self.document.layers[idx] for idx in sorted(selected_indices)]
            remaining = [
                layer for idx, layer in enumerate(self.document.layers)
                if idx not in set(selected_indices)
            ]
            removed_before_target = sum(1 for idx in selected_indices if idx < target_actual_index)
            insert_at = max(0, min(len(remaining), target_actual_index - removed_before_target))
            self.document.layers = remaining[:insert_at] + selected_objects + remaining[insert_at:]
            new_selection = []
            for layer in selected_objects:
                new_idx = self.document.layers.index(layer)
                new_selection.append(new_idx)
            if hasattr(self.document, 'select_layers'):
                self.document.select_layers(new_selection, primary_index=new_selection[0] if new_selection else -1)
            self.document.layer_changed.emit()
            self.document.document_changed.emit()
            self.document.save_state("批量拖放重排序图层")
        else:
            # 移动图层
            self.document.move_layer(source_actual_index, target_actual_index)
            self.document.document_changed.emit()

    def set_document(self, document):
        """设置面板关联的文档并刷新显示"""
        print(f"[图层面板] 设置文档: {'null' if document is None else '有效文档'}")

        # 如果有旧文档，断开连接
        if self.document:
            try:
                self.document.layer_changed.disconnect(self._schedule_update)
                if hasattr(self.document, 'document_changed'):
                    self.document.document_changed.disconnect(self.update_layers_and_binding_status)
                if hasattr(self.document, 'layers_changed'):
                    self.document.layers_changed.disconnect(self.refresh_binding_status)
                if hasattr(self.document, 'layer_selected'):
                    self.document.layer_selected.disconnect(self.on_layer_selected_from_document)
                if hasattr(self.document, 'layers_selection_changed'):
                    self.document.layers_selection_changed.disconnect(self.on_layers_selection_changed_from_document)
                print(f"[图层面板] 已断开旧文档信号连接")
            except Exception as e:
                print(f"[图层面板] 断开旧文档信号连接时出错: {e}")

        # 设置新文档
        self.document = document
        self._selected_layer_indices = []
        if self._binding_debug_mode and self.binding_debug_toggle and self.document:
            bm = getattr(self.document, 'binding_manager', None)
            if bm and hasattr(bm, 'set_debug_trace_enabled'):
                bm.set_debug_trace_enabled(bool(self.binding_debug_toggle.isChecked()))

        # 如果新文档不为空，连接信号并更新界面
        if self.document:
            print(f"[图层面板] 连接新文档信号，图层数量: {len(self.document.layers)}")

            # 连接文档信号
            self.document.layer_changed.connect(self._schedule_update)

            # 连接文档更改信号
            if hasattr(self.document, 'document_changed'):
                self.document.document_changed.connect(self.update_layers_and_binding_status)

            # 连接layers_changed信号到绑定状态刷新
            if hasattr(self.document, 'layers_changed'):
                self.document.layers_changed.connect(self.refresh_binding_status)

            # 连接layer_selected信号来更新选中状态
            if hasattr(self.document, 'layer_selected'):
                self.document.layer_selected.connect(self.on_layer_selected_from_document)
            if hasattr(self.document, 'layers_selection_changed'):
                self.document.layers_selection_changed.connect(self.on_layers_selection_changed_from_document)

            # 立即更新图层列表显示
            print(f"[图层面板] 立即更新图层列表")
            self._schedule_update()

            # 启用控件
            self._set_controls_enabled(True)

            print(f"[图层面板] 文档设置完成，图层数量: {len(self.document.layers)}")
        else:
            print(f"[图层面板] 清空图层列表")
            # 清空列表
            self.layer_list.clear()
            self._selected_layer_indices = []
            # 禁用控件
            self._set_controls_enabled(False)
            if self._binding_debug_mode:
                self._binding_debug_timer.stop()
                self._binding_debug_last_text = ""
                if hasattr(self, 'binding_debug_text') and self.binding_debug_text:
                    self.binding_debug_text.clear()
        """设置面板关联的文档"""
        # 如果有旧文档，断开连接
        if self.document:
            try:
                self.document.layer_changed.disconnect(self._schedule_update)
                self.document.document_changed.disconnect(self.update_layers_and_binding_status)
                if hasattr(self.document, 'layers_changed'):
                    self.document.layers_changed.disconnect(self.refresh_binding_status)
                if hasattr(self.document, 'layer_selected'):
                    self.document.layer_selected.disconnect(self.on_layer_selected_from_document)
                if hasattr(self.document, 'layers_selection_changed'):
                    self.document.layers_selection_changed.disconnect(self.on_layers_selection_changed_from_document)
            except Exception as e:
                print(f"断开旧文档信号连接时出错: {e}")

        # 设置新文档
        self.document = document

        # 如果新文档不为空，连接信号
        if self.document:
            self.document.layer_changed.connect(self._schedule_update)
            # 使用统一的更新方法，避免重复连接
            self.document.document_changed.connect(self.update_layers_and_binding_status)
            # 连接layers_changed信号到绑定状态刷新
            if hasattr(self.document, 'layers_changed'):
                self.document.layers_changed.connect(self.refresh_binding_status)
            # 连接layer_selected信号来更新选中状态
            if hasattr(self.document, 'layer_selected'):
                self.document.layer_selected.connect(self.on_layer_selected_from_document)
            if hasattr(self.document, 'layers_selection_changed'):
                self.document.layers_selection_changed.connect(self.on_layers_selection_changed_from_document)
            self._schedule_update()
        else:
            # 清空列表
            self.layer_list.clear()

    def update_layers_and_binding_status(self):
        """统一更新图层列表和绑定状态"""
        if self._is_export_ui_frozen():
            print("[图层面板] update_layers_and_binding_status: 批量导出运行中，跳过")
            return
        self._schedule_update()
        # 延迟刷新绑定状态，确保图层列表已更新
        QTimer.singleShot(10, self.refresh_binding_status)

    def on_layer_selected_from_document(self, selected_index):
        """处理来自Document的图层选中信号"""
        print(f"Document发出图层选中信号: 索引={selected_index}")
        if self._selection_sync_in_progress:
            return

        doc_selection = list(getattr(self.document, 'selected_layer_indices', []))
        if doc_selection:
            self._selected_layer_indices = doc_selection
        elif 0 <= selected_index < len(self.document.layers):
            self._selected_layer_indices = [selected_index]
        else:
            self._selected_layer_indices = []

        self._refresh_layer_widgets_selection()
        self._update_selected_layer_controls()

    def on_layers_selection_changed_from_document(self, selected_indices):
        """处理来自Document的多图层选中信号。"""
        if self._selection_sync_in_progress:
            return
        self._selected_layer_indices = [
            idx for idx in list(selected_indices or [])
            if self.document and 0 <= idx < len(self.document.layers)
        ]
        self._refresh_layer_widgets_selection()
        self._update_selected_layer_controls()

    def clear_layer_cache(self, layer):
        """清除图层的图像缓存，处理不同的缓存属性命名"""
        if hasattr(layer, '_cached_image'):
            layer._cached_image = None
        if hasattr(layer, 'cached_image'):
            layer.cached_image = None

    def _show_status_message(self, message, timeout=2000):
        """在主窗口状态栏展示简短反馈。"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'statusBar'):
            main_window.statusBar().showMessage(message, timeout)

    def _valid_selected_indices(self):
        """获取去重后的有效选中图层索引。"""
        if not self.document:
            return []
        valid_indices = []
        for idx in self.get_selected_indices():
            if 0 <= idx < len(self.document.layers) and idx not in valid_indices:
                valid_indices.append(idx)
        return valid_indices

    def _finalize_multi_layer_operation(self, action_name, changed_layers):
        """统一完成多图层操作的缓存、历史和刷新。"""
        if not changed_layers:
            return False
        for layer in changed_layers:
            self.clear_layer_cache(layer)
        if hasattr(self.document, '_needs_cache_refresh'):
            self.document._needs_cache_refresh = True
        self.document.document_changed.emit()
        self.document.layer_changed.emit()
        self.document.save_state(action_name)
        if hasattr(self, 'refresh_all_icons'):
            self.refresh_all_icons()
        self._refresh_layer_widgets_selection()
        self._update_selected_layer_controls()
        return True

    def set_selected_layers_visible(self, visible):
        """批量设置选中图层可见性。"""
        self.document.save_state("批量显示图层前" if visible else "批量隐藏图层前")
        changed_layers = []
        for idx in self._valid_selected_indices():
            layer = self.document.layers[idx]
            if getattr(layer, 'visible', True) != visible:
                layer.visible = visible
                changed_layers.append(layer)

        if self._finalize_multi_layer_operation("批量显示图层" if visible else "批量隐藏图层", changed_layers):
            action_text = "显示" if visible else "隐藏"
            self._show_status_message(f"已{action_text} {len(changed_layers)} 个图层", 2000)

    def set_selected_layers_locked(self, locked):
        """批量设置选中图层锁定状态。"""
        self.document.save_state("批量锁定图层前" if locked else "批量解锁图层前")
        changed_layers = []
        for idx in self._valid_selected_indices():
            layer = self.document.layers[idx]
            if getattr(layer, 'locked', False) != locked:
                layer.locked = locked
                changed_layers.append(layer)

        if self._finalize_multi_layer_operation("批量锁定图层" if locked else "批量解锁图层", changed_layers):
            action_text = "锁定" if locked else "解锁"
            self._show_status_message(f"已{action_text} {len(changed_layers)} 个图层", 2000)

    def align_layers(self, align_type):
        """对齐图层到画板"""
        if not self.document or not hasattr(self.document, 'layers') or not self.document.layers:
            return

        # 获取当前选中的图层索引（支持多选）
        selected_indices = self.get_selected_indices()
        selected_index = selected_indices[0] if selected_indices else self.document.selected_layer_index
        if selected_index < 0:
            return

        # 多选对齐：以首选图层为基准，仅移动/缩放其余选中图层
        if len(selected_indices) > 1:
            self._align_layers_to_reference(selected_indices, align_type)
            return

        # 保存当前状态
        self.document.save_state("对齐图层前")

        # 获取当前选中的图层
        layer = self.document.layers[selected_index]

        # 检查图层是否锁定
        if layer.locked:
            return  # 如果图层锁定，不执行任何对齐操作

        # 获取画布尺寸
        canvas_width = self.document.canvas_width
        canvas_height = self.document.canvas_height

        # 是否需要清除缓存
        need_clear_cache = False

        # 检查是否启用了分身功能
        is_clone_enabled = (hasattr(layer, 'clone_enabled') and layer.clone_enabled and
                           hasattr(layer, 'clone_rows') and layer.clone_rows > 0 and
                           hasattr(layer, 'clone_columns') and layer.clone_columns > 0)

        # 如果启用了分身，获取所有分身位置并计算整体的边界
        if is_clone_enabled:
            try:
                # 获取所有分身位置
                if hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                    # 复制当前图层位置，以便可以恢复如果出错
                    original_x, original_y = layer.x, layer.y

                    clone_positions = layer.get_clone_positions()
                    all_positions = [(layer.x, layer.y)] + clone_positions
                    # 元素填充整体位置
                    fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
                    if fill_enabled:
                        spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                        angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                        mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                        dx = max(1, int(layer.width + spacing))
                        dy = max(1, int(layer.height + spacing))
                        positions = []
                        cx = canvas_width / 2.0
                        cy = canvas_height / 2.0
                        base_x = layer.x
                        base_y = layer.y
                        import math
                        angle = math.radians(angle_deg % 360.0)
                        start_y = -layer.height
                        end_y = canvas_height + layer.height
                        if mode == 'border':
                            seen = set()
                            for x in range(0, max(1, canvas_width - layer.width + 1), dx):
                                px = base_x + x
                                py_top = base_y + 0
                                py_bottom = base_y + (canvas_height - layer.height)
                                seen.add((px, py_top))
                                seen.add((px, py_bottom))
                            for y in range(0, max(1, canvas_height - layer.height + 1), dy):
                                py = base_y + y
                                px_left = base_x + 0
                                px_right = base_x + (canvas_width - layer.width)
                                seen.add((px_left, py))
                                seen.add((px_right, py))
                            positions = list(seen)
                        else:
                            step_y = dy
                            i_row = 0
                            for row_y in range(start_y, end_y + 1, step_y):
                                offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                                for col_x in range(-layer.width, canvas_width + layer.width + 1, dx):
                                    x0 = base_x + col_x + offset
                                    y0 = base_y + row_y
                                    if angle != 0.0:
                                        rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                                        ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                                        x = int(rx)
                                        y = int(ry)
                                    else:
                                        x = x0
                                        y = y0
                                    positions.append((x, y))
                                i_row += 1
                        all_positions = positions if positions else all_positions
                    mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                    if mirror_mode and mirror_mode != 'none':
                        positions = all_positions[:]
                        min_x = min([x for x, _ in positions])
                        max_x = max([x + layer.width for x, _ in positions])
                        min_y = min([y for _, y in positions])
                        max_y = max([y + layer.height for _, y in positions])
                        group_width = max_x - min_x
                        group_height = max_y - min_y
                        mirrored_positions = []
                        if mirror_mode == 'horizontal':
                            mirrored_left = canvas_width - (min_x + group_width)
                            for cx, cy in positions:
                                offset_x = cx - min_x
                                mirrored_positions.append((mirrored_left + offset_x, cy))
                        elif mirror_mode == 'vertical':
                            mirrored_top = canvas_height - (min_y + group_height)
                            for cx, cy in positions:
                                offset_y = cy - min_y
                                mirrored_positions.append((cx, mirrored_top + offset_y))
                        all_positions = all_positions + mirrored_positions

                    # 计算分身整体的边界（包括原始图层）
                    min_x = min([pos[0] for pos in all_positions])
                    max_x = max([pos[0] + layer.width for pos in all_positions])
                    min_y = min([pos[1] for pos in all_positions])
                    max_y = max([pos[1] + layer.height for pos in all_positions])

                    # 计算整体宽度和高度
                    total_width = max_x - min_x
                    total_height = max_y - min_y

                    # 计算主图层与整体边界的偏移
                    offset_x = layer.x - min_x
                    offset_y = layer.y - min_y

                    # 根据对齐类型执行不同的对齐操作
                    if align_type == "left":
                        # 左对齐到画板
                        layer.x = 0 + offset_x  # 保持分身之间的相对位置
                        need_clear_cache = True

                    elif align_type == "hcenter":
                        # 水平居中于画板
                        layer.x = int((canvas_width - total_width) / 2) + offset_x
                        need_clear_cache = True

                    elif align_type == "right":
                        # 右对齐到画板
                        layer.x = int(canvas_width - total_width) + offset_x
                        need_clear_cache = True

                    elif align_type == "top":
                        # 顶部对齐到画板
                        layer.y = 0 + offset_y
                        need_clear_cache = True

                    elif align_type == "vcenter":
                        # 垂直居中于画板
                        layer.y = int((canvas_height - total_height) / 2) + offset_y
                        need_clear_cache = True

                    elif align_type == "bottom":
                        # 底部对齐到画板
                        layer.y = int(canvas_height - total_height) + offset_y
                        need_clear_cache = True

                    elif align_type == "center":
                        # 完全居中于画板
                        layer.x = int((canvas_width - total_width) / 2) + offset_x
                        layer.y = int((canvas_height - total_height) / 2) + offset_y
                        need_clear_cache = True

                    elif align_type == "same_size":
                        # 对于分身，暂不支持same_size操作
                        if not layer.use_original_size:
                            # 这里可以根据需求实现，例如按比例缩放或提示用户不支持
                            print("分身模式下不支持调整到相同大小")

                            # 暂时采用简单处理：取消分身并调整为画布大小
                            layer.clone_enabled = False
                            layer.width = canvas_width
                            layer.height = canvas_height
                            layer.x = 0
                            layer.y = 0
                            need_clear_cache = True

                    # 如果需要，清除缓存图像以强制重新加载
                    if need_clear_cache:
                        self.clear_layer_cache(layer)

                    # 通知文档已更改
                    self.document.document_changed.emit()

                    # 保存更改后的状态
                    self.document.save_state("对齐分身图层")
                    return

            except Exception as e:
                print(f"分身对齐出错: {e}")
                # 出错时回退到常规对齐

        # 镜像但未启用分身时的整体对齐
        mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
        if (not is_clone_enabled) and mirror_mode and mirror_mode != 'none':
            try:
                positions = [(layer.x, layer.y)]
                min_x = layer.x
                max_x = layer.x + layer.width
                min_y = layer.y
                max_y = layer.y + layer.height
                group_width = max_x - min_x
                group_height = max_y - min_y
                mirrored_positions = []
                if mirror_mode == 'horizontal':
                    mirrored_left = canvas_width - (min_x + group_width)
                    mirrored_positions.append((mirrored_left, layer.y))
                elif mirror_mode == 'vertical':
                    mirrored_top = canvas_height - (min_y + group_height)
                    mirrored_positions.append((layer.x, mirrored_top))
                all_positions = positions + mirrored_positions
                min_x = min([pos[0] for pos in all_positions])
                max_x = max([pos[0] + layer.width for pos in all_positions])
                min_y = min([pos[1] for pos in all_positions])
                max_y = max([pos[1] + layer.height for pos in all_positions])
                total_width = max_x - min_x
                total_height = max_y - min_y
                offset_x = layer.x - min_x
                offset_y = layer.y - min_y
                if align_type == "left":
                    layer.x = 0 + offset_x
                    need_clear_cache = True
                elif align_type == "hcenter":
                    layer.x = int((canvas_width - total_width) / 2) + offset_x
                    need_clear_cache = True
                elif align_type == "right":
                    layer.x = int(canvas_width - total_width) + offset_x
                    need_clear_cache = True
                elif align_type == "top":
                    layer.y = 0 + offset_y
                    need_clear_cache = True
                elif align_type == "vcenter":
                    layer.y = int((canvas_height - total_height) / 2) + offset_y
                    need_clear_cache = True
                elif align_type == "bottom":
                    layer.y = int(canvas_height - total_height) + offset_y
                    need_clear_cache = True
                elif align_type == "center":
                    layer.x = int((canvas_width - total_width) / 2) + offset_x
                    layer.y = int((canvas_height - total_height) / 2) + offset_y
                    need_clear_cache = True
                if need_clear_cache:
                    self.clear_layer_cache(layer)
                self.document.document_changed.emit()
                self.document.save_state("对齐镜像图层")
                return
            except Exception:
                pass

        fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
        if (not is_clone_enabled) and fill_enabled:
            try:
                spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                dx = max(1, int(layer.width + spacing))
                dy = max(1, int(layer.height + spacing))
                positions = []
                cx = canvas_width / 2.0
                cy = canvas_height / 2.0
                base_x = layer.x
                base_y = layer.y
                import math
                angle = math.radians(angle_deg % 360.0)
                start_y = -layer.height
                end_y = canvas_height + layer.height
                step_y = max(1, int(dy * 0.866)) if mode == 'hex' else dy
                i_row = 0
                for row_y in range(start_y, end_y + 1, step_y):
                    offset = 0
                    if mode == 'staggered' and (i_row % 2 == 1):
                        offset = dx // 2
                    if mode == 'hex' and (i_row % 2 == 1):
                        offset = dx // 2
                    if mode == 'diagonal':
                        offset = (i_row * (dx // 2)) % dx
                    for col_x in range(-layer.width, canvas_width + layer.width + 1, dx):
                        x0 = base_x + col_x + offset
                        y0 = base_y + row_y
                        if angle != 0.0:
                            rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                            ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                            x = int(rx)
                            y = int(ry)
                        else:
                            x = x0
                            y = y0
                        positions.append((x, y))
                    i_row += 1
                if positions:
                    min_x = min([pos[0] for pos in positions])
                    max_x = max([pos[0] + layer.width for pos in positions])
                    min_y = min([pos[1] for pos in positions])
                    max_y = max([pos[1] + layer.height for pos in positions])
                    total_width = max_x - min_x
                    total_height = max_y - min_y
                    offset_x = layer.x - min_x
                    offset_y = layer.y - min_y
                    if align_type == "left":
                        layer.x = 0 + offset_x
                        need_clear_cache = True
                    elif align_type == "hcenter":
                        layer.x = int((canvas_width - total_width) / 2) + offset_x
                        need_clear_cache = True
                    elif align_type == "right":
                        layer.x = int(canvas_width - total_width) + offset_x
                        need_clear_cache = True
                    elif align_type == "top":
                        layer.y = 0 + offset_y
                        need_clear_cache = True
                    elif align_type == "vcenter":
                        layer.y = int((canvas_height - total_height) / 2) + offset_y
                        need_clear_cache = True
                    elif align_type == "bottom":
                        layer.y = int(canvas_height - total_height) + offset_y
                        need_clear_cache = True
                    elif align_type == "center":
                        layer.x = int((canvas_width - total_width) / 2) + offset_x
                        layer.y = int((canvas_height - total_height) / 2) + offset_y
                        need_clear_cache = True
                    if need_clear_cache:
                        self.clear_layer_cache(layer)
                    self.document.document_changed.emit()
                    self.document.save_state("对齐填充整体")
                    return
            except Exception:
                pass

        # 常规单图层对齐（无分身或分身/镜像处理失败时）
        # 根据对齐类型执行不同的对齐操作
        if align_type == "left":
            # 左对齐到画板
            layer.x = 0
            need_clear_cache = True

        elif align_type == "hcenter":
            # 水平居中于画板
            layer.x = int((canvas_width - layer.width) / 2)
            need_clear_cache = True

        elif align_type == "right":
            # 右对齐到画板
            layer.x = int(canvas_width - layer.width)
            need_clear_cache = True

        elif align_type == "top":
            # 顶部对齐到画板
            layer.y = 0
            need_clear_cache = True

        elif align_type == "vcenter":
            # 垂直居中于画板
            layer.y = int((canvas_height - layer.height) / 2)
            need_clear_cache = True

        elif align_type == "bottom":
            # 底部对齐到画板
            layer.y = int(canvas_height - layer.height)
            need_clear_cache = True

        elif align_type == "center":
            # 完全居中于画板
            layer.x = int((canvas_width - layer.width) / 2)
            layer.y = int((canvas_height - layer.height) / 2)
            need_clear_cache = True

        elif align_type == "same_size":
            # 适应画板大小 - 完全匹配画板尺寸，不保留原始比例
            if not layer.use_original_size:
                # 直接设置为画板大小
                layer.width = canvas_width
                layer.height = canvas_height

                # 重置位置到左上角
                layer.x = 0
                layer.y = 0

                # 对于same_size操作，总是需要清除缓存
                need_clear_cache = True

        # 如果需要，清除缓存图像以强制重新加载
        if need_clear_cache:
            self.clear_layer_cache(layer)
            # 标记文档需要缓存刷新
            if hasattr(self.document, '_needs_cache_refresh'):
                self.document._needs_cache_refresh = True

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("对齐图层")

    def _align_layers_to_reference(self, selected_indices, align_type):
        """多图层对齐：以首选图层为基准对齐其余图层。"""
        valid_indices = []
        for idx in selected_indices:
            if 0 <= idx < len(self.document.layers) and idx not in valid_indices:
                valid_indices.append(idx)
        if len(valid_indices) < 2:
            return

        if align_type in ("distribute_horizontal", "distribute_vertical"):
            self._distribute_layers_evenly(valid_indices, align_type)
            return

        ref_index = valid_indices[0]
        ref_layer = self.document.layers[ref_index]
        ref_left = int(ref_layer.x)
        ref_top = int(ref_layer.y)
        ref_right = int(ref_layer.x + ref_layer.width)
        ref_bottom = int(ref_layer.y + ref_layer.height)
        ref_center_x = ref_layer.x + ref_layer.width / 2.0
        ref_center_y = ref_layer.y + ref_layer.height / 2.0

        changed_layers = []

        for target_index in valid_indices[1:]:
            layer = self.document.layers[target_index]
            if getattr(layer, 'locked', False):
                continue

            changed = False
            if align_type == "left":
                new_x = ref_left
                if int(layer.x) != new_x:
                    layer.x = new_x
                    changed = True
            elif align_type == "hcenter":
                new_x = int(ref_center_x - layer.width / 2.0)
                if int(layer.x) != new_x:
                    layer.x = new_x
                    changed = True
            elif align_type == "right":
                new_x = int(ref_right - layer.width)
                if int(layer.x) != new_x:
                    layer.x = new_x
                    changed = True
            elif align_type == "top":
                new_y = ref_top
                if int(layer.y) != new_y:
                    layer.y = new_y
                    changed = True
            elif align_type == "vcenter":
                new_y = int(ref_center_y - layer.height / 2.0)
                if int(layer.y) != new_y:
                    layer.y = new_y
                    changed = True
            elif align_type == "bottom":
                new_y = int(ref_bottom - layer.height)
                if int(layer.y) != new_y:
                    layer.y = new_y
                    changed = True
            elif align_type == "center":
                new_x = int(ref_center_x - layer.width / 2.0)
                new_y = int(ref_center_y - layer.height / 2.0)
                if int(layer.x) != new_x or int(layer.y) != new_y:
                    layer.x = new_x
                    layer.y = new_y
                    changed = True
            elif align_type == "same_size":
                new_width = int(ref_layer.width)
                new_height = int(ref_layer.height)
                if int(layer.width) != new_width or int(layer.height) != new_height:
                    layer.width = new_width
                    layer.height = new_height
                    changed = True

            if changed:
                changed_layers.append(layer)

        if self._finalize_multi_layer_operation("多图层对齐", changed_layers):
            self._show_status_message(f"已对齐 {len(changed_layers)} 个图层", 2000)

    def _distribute_layers_evenly(self, valid_indices, align_type):
        """按图层边缘间距等距分布，首尾图层固定。"""
        horizontal = align_type == "distribute_horizontal"
        axis_start = "x" if horizontal else "y"
        axis_size = "width" if horizontal else "height"
        sorted_indices = sorted(
            valid_indices,
            key=lambda idx: (
                int(getattr(self.document.layers[idx], axis_start, 0)),
                idx,
            ),
        )
        if len(sorted_indices) < 3:
            self._show_status_message("等距分布需要至少三个图层", 3000)
            return

        layers = [self.document.layers[idx] for idx in sorted_indices]
        first = layers[0]
        last = layers[-1]
        start_pos = float(getattr(first, axis_start, 0))
        end_pos = float(getattr(last, axis_start, 0)) + float(getattr(last, axis_size, 0))
        total_size = sum(float(getattr(layer, axis_size, 0)) for layer in layers)
        gap = (end_pos - start_pos - total_size) / (len(layers) - 1)

        cursor = start_pos
        changed_layers = []
        for i, layer in enumerate(layers):
            target_pos = int(round(cursor))
            if i not in (0, len(layers) - 1) and not getattr(layer, 'locked', False):
                if int(getattr(layer, axis_start, 0)) != target_pos:
                    setattr(layer, axis_start, target_pos)
                    changed_layers.append(layer)
            cursor += float(getattr(layer, axis_size, 0)) + gap

        action_name = "水平等距分布图层" if horizontal else "垂直等距分布图层"
        if self._finalize_multi_layer_operation(action_name, changed_layers):
            direction_text = "水平" if horizontal else "垂直"
            self._show_status_message(f"已{direction_text}等距分布 {len(layers)} 个图层", 2000)

    def _set_controls_enabled(self, enabled):
        """设置控件启用/禁用状态

        Args:
            enabled: 是否启用控件
        """
        # 设置按钮状态
        self.add_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        self.up_btn.setEnabled(enabled and self.document and
                              self.document.selected_layer_index > 0)
        self.down_btn.setEnabled(enabled and self.document and
                               self.document.selected_layer_index < len(self.document.layers) - 1)
        self.random_btn.setEnabled(enabled)

        print(f"设置控件状态: {'启用' if enabled else '禁用'}")
