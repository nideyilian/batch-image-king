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

from app.ui.drag_drop_layer_list import DragDropLayerList
from app.ui.layer_item import LayerItem

class LayerPanelBase(object):
    """Mixin for layer_panel_base (split from LayerPanel)."""

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

    def refresh_layers(self):
        """兼容旧控制器调用的图层刷新入口。"""
        self._schedule_update()

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
        self.layer_list.itemDoubleClicked.connect(self._toggle_group_expanded_for_item)
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

        self.group_btn = QPushButton("组")
        self.group_btn.setToolTip("从所选图层建立组")
        self.group_btn.clicked.connect(self.group_selected_layers)
        self._normalize_toolbar_button(self.group_btn)
        self._apply_button_style(self.group_btn, 'secondary', icon_button=True)
        button_layout.addWidget(self.group_btn)

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

