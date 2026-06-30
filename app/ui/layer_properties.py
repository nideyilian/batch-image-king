from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QSpinBox, QDoubleSpinBox, QLineEdit, QFormLayout,
                           QFileDialog, QGroupBox, QCheckBox, QComboBox,
                           QSlider, QMessageBox, QRadioButton, QButtonGroup,
                           QScrollArea, QFrame, QSizePolicy,
                           QMenu, QMainWindow, QDockWidget, QApplication, QTextEdit)
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
from app.services.ai_asset_service import AIAssetRequest, AIAssetResult, AIAssetService
from app.services.ai_provider_config import AIProviderStore


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

class LayerPropertiesPanel(QWidget):
    """图层属性面板"""

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

    def _layer_panel_stylesheet(self):
        """图层属性面板的局部样式，贴近参考图的暗色卡片界面。"""
        return f"""
            QWidget#layerPropertiesContent {{
                background-color: #181818;
            }}
            QLabel {{
                color: {CursorDarkTheme.TEXT_PRIMARY};
                font-size: 13px;
                background: transparent;
            }}
            QLabel#fieldLabel {{
                color: {CursorDarkTheme.TEXT_PRIMARY};
                font-weight: 500;
            }}
            QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
                min-height: 24px;
                background-color: #111214;
                color: {CursorDarkTheme.TEXT_PRIMARY};
                border: 1px solid #34363A;
                border-radius: 5px;
                padding: 3px 6px;
                selection-background-color: {CursorDarkTheme.ACCENT_PRIMARY};
            }}
            QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{
                border-color: {CursorDarkTheme.ACCENT_PRIMARY};
            }}
            QSpinBox::up-button, QDoubleSpinBox::up-button,
            QSpinBox::down-button, QDoubleSpinBox::down-button {{
                width: 18px;
                border: none;
                background: transparent;
            }}
            QComboBox::drop-down {{
                width: 18px;
                border: none;
            }}
            QPushButton {{
                min-height: 24px;
                background-color: #202226;
                color: {CursorDarkTheme.TEXT_PRIMARY};
                border: 1px solid #34363A;
                border-radius: 5px;
                padding: 3px 6px;
            }}
            QPushButton:hover {{
                border-color: {CursorDarkTheme.ACCENT_HOVER};
                background-color: #292C31;
            }}
            QPushButton:checked {{
                background-color: {CursorDarkTheme.ACCENT_PRIMARY};
                border-color: {CursorDarkTheme.ACCENT_HOVER};
                color: #FFFFFF;
            }}
            QCheckBox, QRadioButton {{
                color: {CursorDarkTheme.TEXT_PRIMARY};
                spacing: 8px;
                font-size: 13px;
            }}
            QCheckBox::indicator {{
                width: 18px;
                height: 18px;
                border-radius: 4px;
                border: 1px solid #52555B;
                background-color: #151618;
            }}
            QCheckBox::indicator:checked {{
                background-color: {CursorDarkTheme.ACCENT_PRIMARY};
                border-color: {CursorDarkTheme.ACCENT_HOVER};
            }}
            QRadioButton::indicator {{
                width: 15px;
                height: 15px;
                border-radius: 8px;
                border: 1px solid #52555B;
                background-color: #151618;
            }}
            QRadioButton::indicator:checked {{
                background-color: {CursorDarkTheme.ACCENT_PRIMARY};
                border-color: {CursorDarkTheme.ACCENT_HOVER};
            }}
            QSlider::groove:horizontal {{
                height: 5px;
                background: #34363A;
                border-radius: 2px;
            }}
            QSlider::sub-page:horizontal {{
                background: {CursorDarkTheme.ACCENT_PRIMARY};
                border-radius: 2px;
            }}
            QSlider::handle:horizontal {{
                width: 17px;
                height: 17px;
                margin: -6px 0;
                border-radius: 9px;
                background: {CursorDarkTheme.ACCENT_HOVER};
                border: 1px solid {CursorDarkTheme.ACCENT_PRIMARY};
            }}
            QPushButton#aspectLockButton {{
                min-width: 26px;
                max-width: 26px;
                min-height: 26px;
                max-height: 26px;
                padding: 0;
                font-size: 14px;
            }}
            QPushButton#colorSwatchButton {{
                min-height: 27px;
                text-align: center;
                font-weight: 600;
            }}
            QPushButton[segmentButton="true"] {{
                min-height: 26px;
                padding: 3px 4px;
                font-size: 12px;
            }}
            QPushButton[segmentButton="true"]:checked {{
                background-color: {CursorDarkTheme.ACCENT_PRIMARY};
                border-color: {CursorDarkTheme.ACCENT_HOVER};
                color: #FFFFFF;
                font-weight: 700;
            }}
            QLabel#propertySectionLabel {{
                color: #8E95A3;
                font-size: 11px;
                font-weight: 700;
                padding-top: 2px;
            }}
            QFrame#propertyDivider {{
                background-color: #34363A;
                min-height: 1px;
                max-height: 1px;
                border: none;
            }}
            QFrame#shapePreviewContainer {{
                background-color: #202226;
                border: 1px solid #34363A;
                border-radius: 6px;
            }}
        """

    def _label(self, text):
        label = QLabel(text)
        label.setObjectName("fieldLabel")
        return label

    def _divider(self):
        divider = QFrame()
        divider.setObjectName("propertyDivider")
        divider.setFrameShape(QFrame.HLine)
        return divider

    def _section_label(self, text):
        label = QLabel(text)
        label.setObjectName("propertySectionLabel")
        return label

    def _make_segment_button(self, text, checked=False):
        button = QPushButton(text)
        button.setCheckable(True)
        button.setChecked(checked)
        button.setProperty("segmentButton", True)
        button.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Fixed)
        return button

    def _make_control_group(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)
        return widget, layout

    def _is_export_ui_frozen(self):
        """导出期间是否冻结属性面板更新（由导出设置控制）"""
        doc = getattr(self, 'document', None)
        if not doc or not bool(getattr(doc, '_is_batch_export_running', False)):
            return False
        try:
            settings = getattr(doc, 'export_settings', {}) or {}
            return bool(settings.get('freeze_preview_during_export', False))
        except Exception:
            return False

    def _emit_document_change(self, throttled=False, include_layer_changed=False, fields=None, reason=""):
        """统一发射文档变更信号，支持高频交互节流"""
        if not self.document:
            return

        # 由属性面板本地改动触发时，短时间抑制回流到 update_panel 的全量刷新
        self._suppress_panel_refresh_until = time.time() + 0.35

        layer_index = getattr(self.document, "selected_layer_index", -1)
        normalized_fields = list(fields) if fields else []
        if hasattr(self.document, "set_change_context"):
            self.document.set_change_context(
                source="layer_properties_panel",
                layer_index=layer_index,
                fields=normalized_fields,
                reason=reason
            )

        if not throttled:
            self.document.document_changed.emit()
            if include_layer_changed:
                self.document.layer_changed.emit()
            return

        if include_layer_changed:
            self._deferred_layer_changed = True
        self._deferred_context_fields = normalized_fields
        self._deferred_context_reason = reason or ""

        # 高频参数调整采用短延时合并，避免连续重绘
        if self._ui_change_timer.isActive():
            self._ui_change_timer.stop()
        self._ui_change_timer.start(20)

    def _flush_deferred_document_change(self):
        """执行节流后的文档变更发射"""
        if not self.document:
            return

        if hasattr(self.document, "set_change_context"):
            self.document.set_change_context(
                source="layer_properties_panel",
                layer_index=getattr(self.document, "selected_layer_index", -1),
                fields=self._deferred_context_fields,
                reason=self._deferred_context_reason
            )

        self.document.document_changed.emit()
        if self._deferred_layer_changed:
            self.document.layer_changed.emit()
            self._deferred_layer_changed = False
        self._deferred_context_fields = []
        self._deferred_context_reason = ""

    def _save_state_deferred(self, action_name, delay_ms=220):
        """统一延迟保存历史，避免滑块拖动期间产生大量历史快照"""
        if not self.document:
            return

        self._deferred_action_name = action_name
        if self._history_timer.isActive():
            self._history_timer.stop()
        self._history_timer.start(delay_ms)

    def _flush_deferred_history_save(self):
        """写入最后一次延迟的历史记录"""
        if not self.document or not self._deferred_action_name:
            return

        action_name = self._deferred_action_name
        self._deferred_action_name = None
        self.document.save_state(action_name)

    def _on_layers_selection_changed(self, _indices):
        """多选变化时刷新属性面板类型与混合/批量编辑状态。"""
        if self.document and getattr(self.document, 'selected_layer_index', -1) >= 0:
            self.layer_selected(self.document.selected_layer_index)
        else:
            self.update_panel()

    def _selected_editable_layers(self, allow_locked=False):
        """获取属性面板当前应作用的选中图层。"""
        if not self.document or not hasattr(self.document, 'layers'):
            return []
        indices = list(getattr(self.document, 'selected_layer_indices', []) or [])
        if not indices and getattr(self.document, 'selected_layer_index', -1) >= 0:
            indices = [self.document.selected_layer_index]
        layers = []
        for idx in indices:
            if 0 <= idx < len(self.document.layers):
                layer = self.document.layers[idx]
                if is_layer_group(layer):
                    continue
                if allow_locked or not getattr(layer, 'locked', False):
                    layers.append(layer)
        return layers

    def _is_multi_layer_edit(self):
        return len(self._selected_editable_layers(allow_locked=True)) > 1

    def _selected_layers_all_match(self, layer_type):
        layers = self._selected_editable_layers(allow_locked=True)
        return bool(layers) and all(isinstance(layer, layer_type) for layer in layers)

    def _selected_layers_have_mixed_value(self, attr):
        layers = self._selected_editable_layers(allow_locked=True)
        if len(layers) < 2:
            return False
        marker = object()
        first = getattr(layers[0], attr, marker)
        return any(getattr(layer, attr, marker) != first for layer in layers[1:])

    def _apply_to_selected_layers(self, attrs, action_name, fields=None, allow_locked=False, clear_cache=False):
        """把属性字典批量写入当前选区。"""
        layers = self._selected_editable_layers(allow_locked=allow_locked)
        if not layers:
            return 0
        changed_layers = []
        for layer in layers:
            changed = False
            for attr, value in attrs.items():
                if hasattr(layer, attr) and getattr(layer, attr) != value:
                    setattr(layer, attr, value)
                    changed = True
            if changed:
                if clear_cache:
                    if hasattr(layer, 'cached_image'):
                        layer.cached_image = None
                    if hasattr(layer, '_cached_image'):
                        layer._cached_image = None
                changed_layers.append(layer)
        if not changed_layers:
            return 0
        self._emit_document_change(
            throttled=True,
            include_layer_changed=True,
            fields=fields or list(attrs.keys()),
            reason=action_name
        )
        self._save_state_deferred(action_name)
        return len(changed_layers)

    def delayed_update_panel(self):
        """当文档内容变化时，延迟更新面板以确保最新数据显示"""
        if self._is_export_ui_frozen():
            return
        # 来自本属性面板的变更直接跳过全量回刷，避免未修改字段抖动
        if self.document and time.time() < self._suppress_panel_refresh_until and hasattr(self.document, "get_change_context"):
            try:
                ctx = self.document.get_change_context(max_age_ms=1200)
                if ctx and ctx.get("source") == "layer_properties_panel":
                    selected_index = getattr(self.document, "selected_layer_index", -1)
                    if ctx.get("layer_index", -1) == selected_index:
                        if 0 <= selected_index < len(self.document.layers):
                            if self.current_layer is self.document.layers[selected_index]:
                                return
            except Exception:
                pass
        # 本地参数编辑期间，避免 document_changed 回流触发全量 update_panel
        # 仅在当前仍是同一选中图层时抑制，防止图层切换被误拦截
        if time.time() < self._suppress_panel_refresh_until:
            try:
                idx = getattr(self.document, 'selected_layer_index', -1)
                if idx >= 0 and idx < len(self.document.layers):
                    if self.current_layer is self.document.layers[idx]:
                        return
            except Exception:
                pass

        # 更新的前提是已经选择了图层
        if hasattr(self.document, 'selected_layer_index') and self.document.selected_layer_index >= 0:
            safe_print(f"文档变化，更新面板，当前选中图层: {self.document.selected_layer_index}")
            if not self.current_layer:
                self.layer_selected(self.document.selected_layer_index)
            else:
                self.update_panel()

    def setup_ui(self):
        """初始化用户界面"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(2)

        # 创建滚动区域
        scroll_area = QScrollArea()
        scroll_area.setMinimumWidth(0)
        scroll_area.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        # 应用暗色主题样式到滚动区域
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #181818;
            }
            QScrollBar:vertical {
                background-color: #181818;
                width: 12px;
                border-radius: 6px;
            }
            QScrollBar::handle:vertical {
                background-color: #3A3A3D;
                border-radius: 6px;
                min-height: 20px;
                margin: 2px;
            }
            QScrollBar::handle:vertical:hover {
                background-color: #8E8E93;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)

        # 滚动内容控件
        scroll_content = QWidget()
        scroll_content.setObjectName("layerPropertiesContent")
        scroll_content.setMinimumWidth(0)
        scroll_content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        scroll_content.setStyleSheet(self._layer_panel_stylesheet())
        self.scroll_layout = QVBoxLayout(scroll_content)
        self.scroll_layout.setContentsMargins(4, 6, 4, 8)
        self.scroll_layout.setSpacing(5)

        # 1. 基本属性组 (默认展开)
        self.basic_group = CollapsibleGroupBox("基本属性", collapsed=False)
        basic_form = QFormLayout()

        # 图层名称
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("图层名称")
        self.name_edit.textChanged.connect(self.update_layer_name)
        basic_form.addRow(self._label("名称:"), self.name_edit)

        # 图层位置 X 和 Y 在同一行
        pos_layout = QHBoxLayout()
        pos_layout.setSpacing(5)
        self.x_spin = QSpinBox()
        self.x_spin.setRange(-10000, 10000)
        self.x_spin.valueChanged.connect(self.update_layer_position)
        pos_layout.addWidget(self._label("X:"))
        pos_layout.addWidget(self.x_spin)
        pos_layout.addSpacing(4)

        self.y_spin = QSpinBox()
        self.y_spin.setRange(-10000, 10000)
        self.y_spin.valueChanged.connect(self.update_layer_position)
        pos_layout.addWidget(self._label("Y:"))
        pos_layout.addWidget(self.y_spin)
        basic_form.addRow(self._label("位置:"), pos_layout)

        # 图层宽度和高度在同一行，添加锁定比例按钮
        size_layout = QHBoxLayout()
        size_layout.setSpacing(5)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 10000)
        self.width_spin.valueChanged.connect(self.update_layer_size)
        size_layout.addWidget(self._label("宽:"))
        size_layout.addWidget(self.width_spin)

        # 锁定比例按钮 - 重新设计为更符合整体UI风格
        self.aspect_lock_btn = QPushButton()
        self.aspect_lock_btn.setObjectName("aspectLockButton")
        self.aspect_lock_btn.setFixedSize(26, 26)
        self.aspect_lock_btn.setCheckable(True)
        self.aspect_lock_btn.setChecked(False)
        self.aspect_lock_btn.setToolTip("锁定宽高比例")
        self.aspect_lock_btn.clicked.connect(self.toggle_aspect_ratio_lock)
        self.update_aspect_lock_icon()
        size_layout.addWidget(self.aspect_lock_btn)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 10000)
        self.height_spin.valueChanged.connect(self.update_layer_size)
        size_layout.addWidget(self._label("高:"))
        size_layout.addWidget(self.height_spin)
        basic_form.addRow(self._label("尺寸:"), size_layout)

        # 初始化锁定比例相关变量
        self.aspect_ratio_locked = False
        self.original_aspect_ratio = 1.0
        self._updating_size = False  # 防止递归更新

        # 图层透明度
        opacity_layout = QHBoxLayout()
        self.opacity_slider = QSlider(Qt.Horizontal)
        self.opacity_slider.setRange(0, 100)
        self.opacity_slider.setValue(100)
        self.opacity_slider.valueChanged.connect(self.update_layer_opacity)
        self.opacity_label = QLabel("100%")
        self.opacity_label.setAlignment(Qt.AlignCenter)
        self.opacity_label.setMinimumWidth(48)
        self.opacity_label.setStyleSheet("background-color: #111214; border: 1px solid #34363A; border-radius: 5px; padding: 3px 8px;")
        opacity_layout.addWidget(self.opacity_slider)
        opacity_layout.addWidget(self.opacity_label)
        basic_form.addRow(self._label("不透明度:"), opacity_layout)

        # 图层可见性和锁定
        status_layout = QHBoxLayout()
        status_layout.setSpacing(8)
        self.visible_checkbox = QCheckBox("可见")
        self.visible_checkbox.setChecked(True)
        self.visible_checkbox.clicked.connect(self.update_layer_visibility)
        status_layout.addWidget(self.visible_checkbox)
        status_layout.addSpacing(4)

        self.locked_checkbox = QCheckBox("锁定")
        self.locked_checkbox.setChecked(False)
        self.locked_checkbox.clicked.connect(self.update_layer_lock)
        status_layout.addWidget(self.locked_checkbox)
        status_layout.addStretch()
        basic_form.addRow(self._label("状态:"), status_layout)

        self.basic_group.add_content_layout(basic_form)
        self.scroll_layout.addWidget(self.basic_group)
        self._register_module_group("basic", "基本属性", self.basic_group)

        # 形状（几何参数优先，减少默认认知负担）
        self.shape_group = CollapsibleGroupBox("形状", collapsed=False)
        shape_layout = QVBoxLayout()
        shape_layout.setSpacing(6)

        # 形状类型：保留隐藏下拉框作为兼容层，用户入口改为分段按钮
        self.shape_type_combo = QComboBox()
        self.shape_type_combo.addItems(["矩形", "直角梯形", "圆形", "正五边形", "正六边形"])
        self.shape_type_combo.currentTextChanged.connect(self.update_shape_type)
        self.shape_type_combo.hide()

        shape_segment_layout = QHBoxLayout()
        shape_segment_layout.setSpacing(5)
        self.shape_type_button_group = QButtonGroup(self)
        self.shape_type_button_group.setExclusive(True)
        self.shape_type_buttons = []
        shape_button_specs = [
            ("矩形", "矩形"),
            ("梯形", "直角梯形"),
            ("圆形", "圆形"),
            ("五边", "正五边形"),
            ("六边", "正六边形"),
        ]
        for text, shape_text in shape_button_specs:
            button = self._make_segment_button(text, checked=(shape_text == "矩形"))
            button.setProperty("shapeText", shape_text)
            button.clicked.connect(lambda checked=False, value=shape_text: self.update_shape_type(value))
            self.shape_type_button_group.addButton(button)
            self.shape_type_buttons.append(button)
            shape_segment_layout.addWidget(button)
        shape_layout.addLayout(shape_segment_layout)

        # 形状参数 + 形状预览并排
        shape_main_row = QHBoxLayout()
        shape_main_row.setSpacing(6)

        # 形状参数控制
        self.shape_params_widget = QWidget()
        self.shape_params_layout = QFormLayout(self.shape_params_widget)
        self.shape_params_layout.setContentsMargins(0, 0, 0, 0)

        # 梯形参数
        self.trapezoid_top_spin = QSpinBox()
        self.trapezoid_top_spin.setRange(1, 100)
        self.trapezoid_top_spin.setValue(100)
        self.trapezoid_top_spin.valueChanged.connect(self.update_trapezoid_params)
        self.shape_params_layout.addRow(self._label("上底宽度:"), self.trapezoid_top_spin)

        self.trapezoid_bottom_spin = QSpinBox()
        self.trapezoid_bottom_spin.setRange(1, 100)
        self.trapezoid_bottom_spin.setValue(80)
        self.trapezoid_bottom_spin.valueChanged.connect(self.update_trapezoid_params)
        self.shape_params_layout.addRow(self._label("下底宽度:"), self.trapezoid_bottom_spin)

        self.trapezoid_side_combo = QComboBox()
        self.trapezoid_side_combo.addItems(["左侧", "右侧"])
        self.trapezoid_side_combo.currentTextChanged.connect(self.update_trapezoid_params)
        self.shape_params_layout.addRow(self._label("斜边方向:"), self.trapezoid_side_combo)

        # 多边形参数
        self.polygon_rotation_spin = QDoubleSpinBox()
        self.polygon_rotation_spin.setRange(0, 360)
        self.polygon_rotation_spin.setValue(0)
        self.polygon_rotation_spin.valueChanged.connect(self.update_polygon_params)
        self.shape_params_layout.addRow(self._label("旋转角度:"), self.polygon_rotation_spin)

        self.polygon_radius_spin = QSpinBox()
        self.polygon_radius_spin.setRange(0, 100)
        self.polygon_radius_spin.setValue(0)
        self.polygon_radius_spin.valueChanged.connect(self.update_polygon_params)
        self.shape_params_layout.addRow(self._label("圆角半径:"), self.polygon_radius_spin)

        shape_main_row.addWidget(self.shape_params_widget, 1)

        # 形状预览
        self.shape_preview = ShapePreviewWidget()
        self.shape_preview.setFixedSize(58, 58)
        self.shape_preview.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        preview_container = QFrame()
        preview_container.setObjectName("shapePreviewContainer")
        pc_layout = QVBoxLayout(preview_container)
        pc_layout.setContentsMargins(6, 6, 6, 6)
        pc_layout.setSpacing(3)
        pc_layout.addWidget(self.shape_preview, alignment=Qt.AlignCenter)
        shape_main_row.addWidget(preview_container, 0, Qt.AlignTop)

        shape_layout.addLayout(shape_main_row)
        for row in range(self.shape_params_layout.rowCount()):
            for role in (QFormLayout.LabelRole, QFormLayout.FieldRole):
                item = self.shape_params_layout.itemAt(row, role)
                if item and item.widget():
                    item.widget().hide()

        corner_form = QFormLayout()
        self.vector_corner_radius_spin = QSpinBox()
        self.vector_corner_radius_spin.setRange(0, 1000)
        self.vector_corner_radius_spin.valueChanged.connect(self.update_vector_corner_radius_all)
        corner_form.addRow(self._label("统一圆角:"), self.vector_corner_radius_spin)

        vector_corner_layout = QHBoxLayout()
        vector_corner_layout.setSpacing(5)
        self.vector_corner_tl_spin = QSpinBox()
        self.vector_corner_tl_spin.setRange(0, 1000)
        self.vector_corner_tl_spin.setPrefix("TL  ")
        self.vector_corner_tl_spin.valueChanged.connect(self.update_vector_corner_radii_detail)
        vector_corner_layout.addWidget(self.vector_corner_tl_spin)
        self.vector_corner_tr_spin = QSpinBox()
        self.vector_corner_tr_spin.setRange(0, 1000)
        self.vector_corner_tr_spin.setPrefix("TR  ")
        self.vector_corner_tr_spin.valueChanged.connect(self.update_vector_corner_radii_detail)
        vector_corner_layout.addWidget(self.vector_corner_tr_spin)
        self.vector_corner_br_spin = QSpinBox()
        self.vector_corner_br_spin.setRange(0, 1000)
        self.vector_corner_br_spin.setPrefix("BR  ")
        self.vector_corner_br_spin.valueChanged.connect(self.update_vector_corner_radii_detail)
        vector_corner_layout.addWidget(self.vector_corner_br_spin)
        self.vector_corner_bl_spin = QSpinBox()
        self.vector_corner_bl_spin.setRange(0, 1000)
        self.vector_corner_bl_spin.setPrefix("BL  ")
        self.vector_corner_bl_spin.valueChanged.connect(self.update_vector_corner_radii_detail)
        vector_corner_layout.addWidget(self.vector_corner_bl_spin)
        corner_form.addRow(self._label("四角圆角:"), vector_corner_layout)

        self.convert_to_path_btn = QPushButton("矩形转路径节点")
        self.convert_to_path_btn.clicked.connect(self.convert_rect_to_path_nodes)
        corner_form.addRow("", self.convert_to_path_btn)
        shape_layout.addLayout(corner_form)

        self.shape_group.add_content_layout(shape_layout)
        self.scroll_layout.addWidget(self.shape_group)
        self._register_module_group("shape", "形状", self.shape_group)

        # 外观：填充模式与描边按开关渐进展开
        self.appearance_group = CollapsibleGroupBox("外观", collapsed=False)
        appearance_layout = QVBoxLayout()
        appearance_layout.setSpacing(8)

        appearance_layout.addWidget(self._section_label("填充"))
        fill_mode_layout = QHBoxLayout()
        fill_mode_layout.setSpacing(5)
        self.fill_mode_button_group = QButtonGroup(self)
        self.fill_mode_button_group.setExclusive(True)
        self.fill_mode_buttons = []
        for text, mode in [("无", "none"), ("纯色", "solid"), ("渐变", "gradient")]:
            button = self._make_segment_button(text, checked=(mode == "none"))
            button.setProperty("fillMode", mode)
            button.clicked.connect(lambda checked=False, value=mode: self._set_fill_mode(value))
            self.fill_mode_button_group.addButton(button)
            self.fill_mode_buttons.append(button)
            fill_mode_layout.addWidget(button)
        appearance_layout.addLayout(fill_mode_layout)

        self.fill_solid_enabled_checkbox = QCheckBox("启用纯色填充")
        self.fill_solid_enabled_checkbox.clicked.connect(self.update_fill_solid_enabled)
        self.fill_solid_enabled_checkbox.hide()

        self.fill_solid_controls_widget, fill_solid_controls_layout = self._make_control_group()
        fill_solid_form = QFormLayout()
        self.fill_solid_color_btn = QPushButton("填充颜色")
        self.fill_solid_color_btn.setObjectName("colorSwatchButton")
        self.fill_solid_color_btn.setProperty("swatchLabel", "")
        self.fill_solid_color_btn.clicked.connect(self.pick_fill_solid_color)
        fill_solid_form.addRow(self._label("填充颜色:"), self.fill_solid_color_btn)
        fill_solid_controls_layout.addLayout(fill_solid_form)
        appearance_layout.addWidget(self.fill_solid_controls_widget)

        self.fill_gradient_enabled_checkbox = QCheckBox("启用渐变填充")
        self.fill_gradient_enabled_checkbox.clicked.connect(self.update_fill_gradient_enabled)
        self.fill_gradient_enabled_checkbox.hide()

        self.fill_gradient_controls_widget, fill_gradient_controls_layout = self._make_control_group()
        gradient_color_layout = QHBoxLayout()
        self.fill_gradient_start_btn = QPushButton("起点色")
        self.fill_gradient_start_btn.setObjectName("colorSwatchButton")
        self.fill_gradient_start_btn.setProperty("swatchLabel", "起点色")
        self.fill_gradient_start_btn.clicked.connect(self.pick_gradient_start_color)
        gradient_color_layout.addWidget(self.fill_gradient_start_btn)
        self.fill_gradient_end_btn = QPushButton("终点色")
        self.fill_gradient_end_btn.setObjectName("colorSwatchButton")
        self.fill_gradient_end_btn.setProperty("swatchLabel", "终点色")
        self.fill_gradient_end_btn.clicked.connect(self.pick_gradient_end_color)
        gradient_color_layout.addWidget(self.fill_gradient_end_btn)
        fill_gradient_form = QFormLayout()
        fill_gradient_form.addRow(self._label("渐变颜色:"), gradient_color_layout)

        self.fill_gradient_angle_spin = QDoubleSpinBox()
        self.fill_gradient_angle_spin.setRange(0.0, 360.0)
        self.fill_gradient_angle_spin.setDecimals(1)
        self.fill_gradient_angle_spin.valueChanged.connect(self.update_fill_gradient_angle)
        fill_gradient_form.addRow(self._label("渐变角度:"), self.fill_gradient_angle_spin)

        self.fill_gradient_opacity_spin = QSpinBox()
        self.fill_gradient_opacity_spin.setRange(0, 100)
        self.fill_gradient_opacity_spin.valueChanged.connect(self.update_fill_gradient_opacity)
        fill_gradient_form.addRow(self._label("渐变不透明:"), self.fill_gradient_opacity_spin)
        fill_gradient_controls_layout.addLayout(fill_gradient_form)
        appearance_layout.addWidget(self.fill_gradient_controls_widget)

        appearance_layout.addWidget(self._divider())
        appearance_layout.addWidget(self._section_label("描边"))

        self.stroke_enabled_checkbox = QCheckBox("启用描边")
        self.stroke_enabled_checkbox.clicked.connect(self.update_stroke_enabled)
        appearance_layout.addWidget(self.stroke_enabled_checkbox)

        self.stroke_controls_widget, stroke_controls_layout = self._make_control_group()

        self.stroke_width_spin = QSpinBox()
        self.stroke_width_spin.setRange(1, 200)
        self.stroke_width_spin.valueChanged.connect(self.update_stroke_width)
        stroke_width_layout = QHBoxLayout()
        stroke_width_layout.setSpacing(8)
        stroke_width_layout.addWidget(self.stroke_width_spin)

        self.stroke_type_combo = QComboBox()
        self.stroke_type_combo.addItems(["内描边", "居中描边", "外描边"])
        self.stroke_type_combo.currentIndexChanged.connect(self.update_stroke_type)
        stroke_width_layout.addWidget(self._label("描边对齐:"))
        stroke_width_layout.addWidget(self.stroke_type_combo)
        stroke_controls_form = QFormLayout()
        stroke_controls_form.addRow(self._label("描边粗细:"), stroke_width_layout)

        self.stroke_color_btn = QPushButton("描边颜色")
        self.stroke_color_btn.setObjectName("colorSwatchButton")
        self.stroke_color_btn.setProperty("swatchLabel", "")
        self.stroke_color_btn.clicked.connect(self.pick_stroke_color)
        stroke_controls_form.addRow(self._label("描边颜色:"), self.stroke_color_btn)
        stroke_controls_layout.addLayout(stroke_controls_form)
        appearance_layout.addWidget(self.stroke_controls_widget)

        self.stroke_advanced_group = CollapsibleGroupBox("高级线条", collapsed=True)
        stroke_advanced_form = QFormLayout()

        self.stroke_join_combo = QComboBox()
        self.stroke_join_combo.addItems(["斜接", "圆角", "斜切"])
        self.stroke_join_combo.currentTextChanged.connect(self.update_stroke_join)
        stroke_line_layout = QHBoxLayout()
        stroke_line_layout.setSpacing(8)
        stroke_line_layout.addWidget(self.stroke_join_combo)

        self.stroke_cap_combo = QComboBox()
        self.stroke_cap_combo.addItems(["平头", "圆头", "方头"])
        self.stroke_cap_combo.currentTextChanged.connect(self.update_stroke_cap)
        stroke_line_layout.addWidget(self._label("描边端点:"))
        stroke_line_layout.addWidget(self.stroke_cap_combo)
        stroke_advanced_form.addRow(self._label("描边连接:"), stroke_line_layout)

        stroke_dash_layout = QHBoxLayout()
        self.stroke_dash_length_spin = QSpinBox()
        self.stroke_dash_length_spin.setRange(0, 1000)
        self.stroke_dash_length_spin.valueChanged.connect(self.update_stroke_dash)
        self.stroke_dash_length_spin.setToolTip("为 0 时连续实线；大于 0 时沿路径绘制虚线")
        stroke_dash_layout.addWidget(self._label("段长(0=实线)"))
        stroke_dash_layout.addWidget(self.stroke_dash_length_spin)
        self.stroke_dash_gap_spin = QSpinBox()
        self.stroke_dash_gap_spin.setRange(0, 1000)
        self.stroke_dash_gap_spin.valueChanged.connect(self.update_stroke_dash)
        self.stroke_dash_gap_spin.setToolTip("虚线间隔；连续实线时请设为 0")
        stroke_dash_layout.addWidget(self._label("间隔"))
        stroke_dash_layout.addWidget(self.stroke_dash_gap_spin)
        stroke_advanced_form.addRow(self._label("虚线:"), stroke_dash_layout)
        self.stroke_advanced_group.add_content_layout(stroke_advanced_form)
        appearance_layout.addWidget(self.stroke_advanced_group)

        self.appearance_group.add_content_layout(appearance_layout)
        self.scroll_layout.addWidget(self.appearance_group)
        self._register_module_group("appearance", "外观", self.appearance_group)
        self._sync_appearance_visibility()

        # 2. 图像源设置组 (默认展开)
        self.source_group = CollapsibleGroupBox("图像源设置", collapsed=False)
        source_layout = QVBoxLayout()

        # 图像源类型选择
        source_type_layout = QHBoxLayout()
        self.folder_radio = QRadioButton("文件夹")
        self.file_radio = QRadioButton("单个文件")
        self.folder_radio.setChecked(True)

        # 使用更安全的方式连接信号
        self._source_type_changing = False  # 防止递归
        self.folder_radio.toggled.connect(self.handle_folder_toggled)
        self.file_radio.toggled.connect(self.handle_file_toggled)

        source_type_layout.addWidget(self.folder_radio)
        source_type_layout.addWidget(self.file_radio)
        source_type_layout.addStretch()
        source_layout.addLayout(source_type_layout)

        # 图像源路径
        source_path_layout = QHBoxLayout()
        self.source_path_edit = QLineEdit()
        self.source_path_edit.setPlaceholderText("输入或粘贴文件/文件夹路径")
        self.source_path_edit.setReadOnly(False)  # 允许输入
        self.source_path_edit.returnPressed.connect(self.handle_path_input)  # 添加回车处理
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.clicked.connect(self.browse_image)
        source_path_layout.addWidget(self.source_path_edit)
        source_path_layout.addWidget(self.browse_btn)
        source_layout.addLayout(source_path_layout)

        # 随机按钮
        self.random_btn = QPushButton("随机选择")
        self.random_btn.clicked.connect(self.randomize_image)
        source_layout.addWidget(self.random_btn)

        # 当前图像预览
        self.current_image_label = QLabel("当前图像: 无")
        self.current_image_label.setStyleSheet("color: #8E8E93; font-size: 8pt;")
        source_layout.addWidget(self.current_image_label)

        self.source_group.add_content_layout(source_layout)
        self.scroll_layout.addWidget(self.source_group)
        self._register_module_group("source", "图像源设置", self.source_group)

        self.ai_generation_group = CollapsibleGroupBox("AI生图", collapsed=True)
        ai_layout = QFormLayout()

        self.ai_prompt_edit = QTextEdit()
        self.ai_prompt_edit.setAcceptRichText(False)
        self.ai_prompt_edit.setFixedHeight(76)
        self.ai_negative_prompt_edit = QTextEdit()
        self.ai_negative_prompt_edit.setAcceptRichText(False)
        self.ai_negative_prompt_edit.setFixedHeight(48)
        self.ai_provider_combo = QComboBox()
        self.ai_provider_combo.currentIndexChanged.connect(self.refresh_ai_model_choices)
        self.ai_model_combo = QComboBox()
        self.ai_model_combo.setEditable(True)
        self.ai_model_combo.setInsertPolicy(QComboBox.NoInsert)
        self.ai_refresh_btn = QPushButton("刷新接口/模型")
        self.ai_refresh_btn.clicked.connect(self.refresh_ai_provider_choices)
        self.ai_count_spin = QSpinBox()
        self.ai_count_spin.setRange(1, 20)
        self.ai_count_spin.setValue(1)
        self.ai_size_combo = QComboBox()
        self.ai_size_combo.addItems(["1024x1024", "768x1024", "1024x768", "512x512"])
        self.ai_mode_combo = QComboBox()
        self.ai_mode_combo.addItem("仅生成", "raw")
        self.ai_mode_combo.addItem("生成后基础抠图", "cutout")
        self.ai_mode_combo.addItem("生成后基础抠图并自动分割", "segments")
        self.ai_generate_btn = QPushButton("生成到当前图层")
        self.ai_generate_btn.clicked.connect(self.start_ai_generation_for_current_layer)
        self.ai_status_label = QLabel("使用工具栏的 AI接口设置 作为全局 API 参数")
        self.ai_status_label.setStyleSheet("color: #8E8E93; font-size: 8pt;")

        ai_layout.addRow("提示词:", self.ai_prompt_edit)
        ai_layout.addRow("反向提示词:", self.ai_negative_prompt_edit)
        ai_layout.addRow("接口:", self.ai_provider_combo)
        ai_layout.addRow("模型:", self.ai_model_combo)
        ai_layout.addRow("", self.ai_refresh_btn)
        ai_layout.addRow("数量:", self.ai_count_spin)
        ai_layout.addRow("尺寸:", self.ai_size_combo)
        ai_layout.addRow("处理:", self.ai_mode_combo)
        ai_layout.addRow("", self.ai_generate_btn)
        ai_layout.addRow("", self.ai_status_label)

        self.ai_generation_group.add_content_layout(ai_layout)
        self.scroll_layout.addWidget(self.ai_generation_group)
        self._register_module_group("ai_generation", "AI生图", self.ai_generation_group)
        self.refresh_ai_provider_choices()

        # 3. 高级设置组 (默认收起)
        self.advanced_group = CollapsibleGroupBox("高级设置", collapsed=True)
        advanced_form = QFormLayout()

        # 使用原始尺寸
        self.use_original_size_checkbox = QCheckBox("智能裁剪")
        self.use_original_size_checkbox.clicked.connect(self.update_use_original_size)
        advanced_form.addRow("", self.use_original_size_checkbox)

        # 图像适配模式
        self.fit_mode_combo = QComboBox()
        self.fit_mode_combo.addItem("智能缩放裁剪")
        self.fit_mode_combo.addItem("智能缩放不裁剪")
        self.fit_mode_combo.currentIndexChanged.connect(self.update_fit_mode)
        advanced_form.addRow("适配模式:", self.fit_mode_combo)

        # 裁剪方向
        self.crop_direction_combo = QComboBox()
        self.crop_direction_combo.addItem("居中裁剪")
        self.crop_direction_combo.addItem("顶部裁剪")
        self.crop_direction_combo.addItem("底部裁剪")
        self.crop_direction_combo.addItem("左侧裁剪")
        self.crop_direction_combo.addItem("右侧裁剪")
        self.crop_direction_combo.currentIndexChanged.connect(self.update_crop_direction)
        advanced_form.addRow("裁剪方向:", self.crop_direction_combo)

        # 混合模式
        self.blend_mode_combo = QComboBox()
        # 添加混合模式选项
        if HAS_BLEND_MODE:
            # 从BlendMode类获取所有模式
            for mode in BlendMode.get_all_modes():
                self.blend_mode_combo.addItem(mode)
        else:
            # 如果没有导入成功，只添加正常模式
            self.blend_mode_combo.addItem("正常")
        self.blend_mode_combo.currentTextChanged.connect(self.update_blend_mode)
        advanced_form.addRow("混合模式:", self.blend_mode_combo)

        self.advanced_group.add_content_layout(advanced_form)
        self.scroll_layout.addWidget(self.advanced_group)
        self._register_module_group("advanced", "高级设置", self.advanced_group)

        # 4. 图层分身组 (默认收起)
        self.clone_group = CollapsibleGroupBox("图层分身", collapsed=True)
        clone_layout = QFormLayout()

        # 启用分身
        self.clone_enabled_checkbox = QCheckBox("启用图层分身")
        self.clone_enabled_checkbox.setChecked(False)
        self.clone_enabled_checkbox.clicked.connect(self.update_clone_enabled)
        clone_layout.addRow("", self.clone_enabled_checkbox)

        # 分身行数和列数放在同一行
        clone_count_layout = QHBoxLayout()
        self.clone_rows_spin = QSpinBox()
        self.clone_rows_spin.setRange(1, 100)
        self.clone_rows_spin.setValue(1)
        self.clone_rows_spin.valueChanged.connect(self.update_clone_settings)
        clone_count_layout.addWidget(QLabel("行:"))
        clone_count_layout.addWidget(self.clone_rows_spin)

        self.clone_columns_spin = QSpinBox()
        self.clone_columns_spin.setRange(1, 100)
        self.clone_columns_spin.setValue(1)
        self.clone_columns_spin.valueChanged.connect(self.update_clone_settings)
        clone_count_layout.addWidget(QLabel("列:"))
        clone_count_layout.addWidget(self.clone_columns_spin)
        clone_layout.addRow("数量:", clone_count_layout)

        # 行间距和列间距放在同一行
        spacing_layout = QHBoxLayout()
        self.row_spacing_spin = QSpinBox()
        self.row_spacing_spin.setRange(0, 10000)  # 提高最大行间距到10000px
        self.row_spacing_spin.setValue(0)
        self.row_spacing_spin.valueChanged.connect(self.update_clone_settings)
        spacing_layout.addWidget(QLabel("行:"))
        spacing_layout.addWidget(self.row_spacing_spin)

        self.column_spacing_spin = QSpinBox()
        self.column_spacing_spin.setRange(0, 10000)  # 提高最大列间距到10000px
        self.column_spacing_spin.setValue(0)
        self.column_spacing_spin.valueChanged.connect(self.update_clone_settings)
        spacing_layout.addWidget(QLabel("列:"))
        spacing_layout.addWidget(self.column_spacing_spin)
        clone_layout.addRow("间距:", spacing_layout)

        # 分身自定义大小
        self.clone_custom_size_checkbox = QCheckBox("自定义分身大小")
        self.clone_custom_size_checkbox.setChecked(False)
        self.clone_custom_size_checkbox.clicked.connect(self.update_clone_custom_size_enabled)
        clone_layout.addRow("", self.clone_custom_size_checkbox)

        # 分身宽度和高度
        clone_size_layout = QHBoxLayout()
        self.clone_width_spin = QSpinBox()
        self.clone_width_spin.setRange(1, 10000)
        self.clone_width_spin.setValue(100)
        self.clone_width_spin.setEnabled(False)
        self.clone_width_spin.valueChanged.connect(self.update_clone_custom_size)
        clone_size_layout.addWidget(QLabel("宽:"))
        clone_size_layout.addWidget(self.clone_width_spin)

        self.clone_height_spin = QSpinBox()
        self.clone_height_spin.setRange(1, 10000)
        self.clone_height_spin.setValue(100)
        self.clone_height_spin.setEnabled(False)
        self.clone_height_spin.valueChanged.connect(self.update_clone_custom_size)
        clone_size_layout.addWidget(QLabel("高:"))
        clone_size_layout.addWidget(self.clone_height_spin)
        clone_layout.addRow("分身尺寸:", clone_size_layout)

        # 元素填充功能
        self.fill_enabled_checkbox = QCheckBox("启用元素填充")
        self.fill_enabled_checkbox.setChecked(False)
        self.fill_enabled_checkbox.clicked.connect(self.update_fill_enabled)
        clone_layout.addRow("", self.fill_enabled_checkbox)

        self.fill_mode_combo = QComboBox()
        self.fill_mode_combo.addItems(["常规网格", "错位排列", "边框排列"])
        self.fill_mode_combo.currentIndexChanged.connect(self.update_fill_mode)
        clone_layout.addRow("排列:", self.fill_mode_combo)

        self.fill_spacing_spin = QSpinBox()
        self.fill_spacing_spin.setRange(0, 10000)
        self.fill_spacing_spin.setValue(0)
        self.fill_spacing_spin.valueChanged.connect(self.update_fill_spacing)
        clone_layout.addRow("元素间距:", self.fill_spacing_spin)

        self.fill_margin_spin = QSpinBox()
        self.fill_margin_spin.setRange(0, 1000)
        self.fill_margin_spin.setValue(0)
        self.fill_margin_spin.valueChanged.connect(self.update_fill_margin)
        clone_layout.addRow("画布边距:", self.fill_margin_spin)

        self.fill_angle_spin = QDoubleSpinBox()
        self.fill_angle_spin.setRange(0.0, 360.0)
        self.fill_angle_spin.setDecimals(1)
        self.fill_angle_spin.setValue(0.0)
        self.fill_angle_spin.valueChanged.connect(self.update_fill_angle)
        clone_layout.addRow("元素角度:", self.fill_angle_spin)

        self.clone_mirror_combo = QComboBox()
        self.clone_mirror_combo.addItems(["无镜像", "左右镜像", "上下镜像"])
        self.clone_mirror_combo.currentIndexChanged.connect(self.update_clone_mirror_mode_index)
        clone_layout.addRow("镜像:", self.clone_mirror_combo)

        self.clone_group.add_content_layout(clone_layout)
        self.scroll_layout.addWidget(self.clone_group)
        self._register_module_group("clone", "图层分身", self.clone_group)

        # 5.（已移除）右侧栏“图层绑定/图层大小匹配”入口
        # 用户从左侧图层面板入口统一管理，避免重复入口造成混淆。
        self.bind_status_label = QLabel("未绑定")
        self.bind_status_label.setStyleSheet("color: #606064; font-size: 9pt;")

        # 6. 图层变换组 (默认收起)
        self.transform_group = CollapsibleGroupBox("图层变换", collapsed=True)
        self.transform_widget = LayerTransformWidget()
        self.transform_widget.rotation_changed.connect(self.update_layer_rotation)
        self.transform_widget.flip_horizontal_changed.connect(self.update_layer_flip_horizontal)
        self.transform_widget.flip_vertical_changed.connect(self.update_layer_flip_vertical)
        self.transform_widget.transform_reset.connect(self.reset_layer_transforms)
        self.transform_group.set_content_widget(self.transform_widget)
        self.scroll_layout.addWidget(self.transform_group)
        self._register_module_group("transform", "图层变换", self.transform_group)

        # 7. 随机变换组 (默认收起)
        self.random_transform_group = CollapsibleGroupBox("随机变换", collapsed=True)
        from app.ui.layer_random_transform_widget import LayerRandomTransformWidget
        self.random_transform_widget = LayerRandomTransformWidget()
        self.random_transform_widget.random_position_enabled_changed.connect(self.update_random_position_enabled)
        self.random_transform_widget.random_position_range_changed.connect(self.update_random_position_range)
        self.random_transform_widget.random_scale_enabled_changed.connect(self.update_random_scale_enabled)
        self.random_transform_widget.random_scale_min_changed.connect(self.update_random_scale_min)
        self.random_transform_widget.random_scale_max_changed.connect(self.update_random_scale_max)
        self.random_transform_widget.random_rotation_enabled_changed.connect(self.update_random_rotation_enabled)
        self.random_transform_widget.random_rotation_range_changed.connect(self.update_random_rotation_range)
        self.random_transform_widget.generate_random_params.connect(self.generate_random_params)
        self.random_transform_widget.reset_random_params.connect(self.reset_random_params)
        self.random_transform_group.set_content_widget(self.random_transform_widget)
        self.scroll_layout.addWidget(self.random_transform_group)
        self._register_module_group("random_transform", "随机变换", self.random_transform_group)

        # 8. 异形图层属性面板（初始隐藏）- 移入滚动区域以避免覆盖问题
        from app.ui.shaped_layer_panel import ShapedLayerPanel
        self.shaped_layer_panel = ShapedLayerPanel()
        self.shaped_layer_panel.hide()
        self.scroll_layout.addWidget(self.shaped_layer_panel)

        # 添加一个拉伸项，使控件集中在顶部
        self._scroll_stretch_index = self.scroll_layout.count()
        self.scroll_layout.addStretch(1)

        # 设置滚动区域
        scroll_area.setWidget(scroll_content)
        main_layout.addWidget(scroll_area)

        # 保存对普通图层面板的引用
        self.normal_layer_panel = scroll_area

        # 创建文字图层属性面板（初始隐藏）
        from app.ui.text_layer_properties import TextLayerPropertiesPanel
        self.text_layer_panel = TextLayerPropertiesPanel()
        self.text_layer_panel.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        self.text_layer_panel.setMinimumWidth(0)
        self.text_layer_panel.hide()
        main_layout.addWidget(self.text_layer_panel)
        self.text_layer_panel.layer_changed.connect(self.delayed_update_panel)

        # 连接异形图层面板的信号 - 更新为参数变更时同步基本属性面板
        self.shaped_layer_panel.shape_changed.connect(self.on_shaped_layer_changed)
        self.shaped_layer_panel.parameter_changed.connect(self.on_shaped_layer_param_changed)

        # 初始禁用所有控件
        self._apply_compact_layouts()
        self.set_controls_enabled(False)

    def _apply_compact_layouts(self):
        """统一压缩属性面板内部表单间距，避免右侧面板挤占画布。"""
        def compact(layout):
            if layout is None:
                return
            if isinstance(layout, QFormLayout):
                layout.setHorizontalSpacing(5)
                layout.setVerticalSpacing(3)
                layout.setContentsMargins(0, 0, 0, 0)
                layout.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
                layout.setFormAlignment(Qt.AlignTop)
                layout.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
                layout.setRowWrapPolicy(QFormLayout.WrapLongRows)
            else:
                layout.setSpacing(min(layout.spacing() if layout.spacing() >= 0 else 4, 4))

            for i in range(layout.count()):
                item = layout.itemAt(i)
                compact(item.layout())
                widget = item.widget()
                if widget is not None:
                    compact(widget.layout())

        compact(self.layout())
        compact(getattr(self, "scroll_layout", None))
        self._apply_adaptive_widths()

    def _apply_adaptive_widths(self):
        """降低属性面板的最小宽度，让 dock 可以按内容自适应收窄。"""
        compact_types = (QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPushButton)
        for widget_type in compact_types:
            for widget in self.findChildren(widget_type):
                if widget is self.aspect_lock_btn:
                    continue
                widget.setMinimumWidth(0)
                widget.setSizePolicy(QSizePolicy.Ignored, widget.sizePolicy().verticalPolicy())

        for spin_type in (QSpinBox, QDoubleSpinBox):
            for spin in self.findChildren(spin_type):
                spin.setMinimumWidth(48)

        for combo in self.findChildren(QComboBox):
            combo.setMinimumWidth(58)

        for edit in self.findChildren(QLineEdit):
            edit.setMinimumWidth(40)

        for btn in (getattr(self, "browse_btn", None),):
            if btn is not None:
                btn.setMinimumWidth(46)
                btn.setMaximumWidth(58)
                btn.setSizePolicy(QSizePolicy.Fixed, btn.sizePolicy().verticalPolicy())

        for btn in (
            getattr(self, "stroke_color_btn", None),
            getattr(self, "fill_solid_color_btn", None),
            getattr(self, "fill_gradient_start_btn", None),
            getattr(self, "fill_gradient_end_btn", None),
        ):
            if btn is not None:
                btn.setMinimumWidth(32)

        for group in self._module_groups.values():
            group.setMinimumWidth(0)
            group.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)

    def _register_module_group(self, module_key: str, title: str, group: CollapsibleGroupBox):
        """注册可拆分模块，并为标题栏添加右键菜单。"""
        self._module_groups[module_key] = group
        self._module_group_titles[module_key] = title
        self._module_order.append(module_key)

        group.title_frame.setContextMenuPolicy(Qt.CustomContextMenu)
        group.title_frame.customContextMenuRequested.connect(
            lambda pos, k=module_key, g=group: self._show_module_context_menu(k, g.title_frame.mapToGlobal(pos))
        )
        group.title_frame.setToolTip("右键可拆分/组合模块")

    def _show_module_context_menu(self, module_key: str, global_pos):
        """显示模块拆分/组合菜单。"""
        if module_key not in self._module_groups:
            return

        menu = QMenu(self)
        detached = module_key in self._module_docks
        if detached:
            merge_action = menu.addAction("合并回图层属性")
            merge_action.triggered.connect(lambda: self._attach_module_group(module_key))
        else:
            detach_action = menu.addAction("拆分为独立模块")
            detach_action.triggered.connect(lambda: self._detach_module_group(module_key))

        menu.addSeparator()
        detach_all_action = menu.addAction("全部拆分")
        merge_all_action = menu.addAction("全部合并")
        detach_all_action.triggered.connect(self._detach_all_module_groups)
        merge_all_action.triggered.connect(self._attach_all_module_groups)
        menu.exec(global_pos)

    def _get_module_settings(self):
        return QSettings("批图王", "批图王")

    def _dock_area_to_int(self, area) -> int:
        """兼容不同 PySide6 枚举实现的 DockArea 序列化。"""
        try:
            return int(area)
        except Exception:
            try:
                return int(area.value)
            except Exception:
                return int(Qt.RightDockWidgetArea.value)

    def _int_to_dock_area(self, value):
        """从持久化值恢复为 Qt.DockWidgetArea。"""
        try:
            return Qt.DockWidgetArea(int(value))
        except Exception:
            return Qt.RightDockWidgetArea

    def _persist_module_layout(self):
        """保存模块拆分/组合状态与停靠几何信息。"""
        settings = self._get_module_settings()
        settings.beginGroup("layer_properties_modules")
        settings.setValue("detached_keys", list(self._module_docks.keys()))

        main_window = self._get_main_window()
        for module_key in self._module_order:
            dock = self._module_docks.get(module_key)
            settings.beginGroup(module_key)
            settings.setValue("detached", dock is not None)
            if dock is not None:
                settings.setValue("floating", dock.isFloating())
                if dock.isFloating():
                    settings.setValue("geometry", dock.saveGeometry())
                if main_window is not None:
                    settings.setValue("dock_area", self._dock_area_to_int(main_window.dockWidgetArea(dock)))
            settings.endGroup()
        settings.endGroup()
        settings.sync()

    def _get_main_window(self):
        win = self.window()
        if isinstance(win, QMainWindow):
            return win
        return None

    def _is_group_attached(self, group: CollapsibleGroupBox) -> bool:
        """是否仍在图层属性滚动布局中。"""
        return group.parent() == self.scroll_layout.parentWidget()

    def _insert_group_back_in_order(self, module_key: str):
        """按原顺序把模块插回属性面板。"""
        group = self._module_groups[module_key]
        insert_at = 0
        for key in self._module_order:
            if key == module_key:
                break
            prev_group = self._module_groups.get(key)
            if prev_group is not None and self._is_group_attached(prev_group):
                insert_at += 1
        self.scroll_layout.insertWidget(insert_at, group)

    def _detach_module_group(self, module_key: str):
        """将模块拆分为独立停靠窗，可自由拖拽组合。"""
        group = self._module_groups.get(module_key)
        if group is None or module_key in self._module_docks:
            return

        main_window = self._get_main_window()
        if main_window is None:
            return

        self.scroll_layout.removeWidget(group)
        group.setParent(None)

        dock = QDockWidget(self._module_group_titles.get(module_key, module_key), main_window)
        dock.setObjectName(f"layer_properties_module_{module_key}_dock")
        dock.setAllowedAreas(Qt.LeftDockWidgetArea | Qt.RightDockWidgetArea)
        dock.setFeatures(
            QDockWidget.DockWidgetMovable |
            QDockWidget.DockWidgetFloatable
        )
        dock.setWidget(group)
        main_window.addDockWidget(Qt.RightDockWidgetArea, dock)
        dock.visibilityChanged.connect(
            lambda visible, k=module_key: self._on_module_dock_visibility_changed(k, visible)
        )
        dock.topLevelChanged.connect(lambda _floating, _k=module_key: self._persist_module_layout())
        if hasattr(dock, "dockLocationChanged"):
            dock.dockLocationChanged.connect(lambda _area, _k=module_key: self._persist_module_layout())
        dock.setFloating(True)
        dock.resize(260, 520)
        dock.show()
        self._module_docks[module_key] = dock
        if not self._restoring_module_layout:
            self._persist_module_layout()

    def _on_module_dock_visibility_changed(self, module_key: str, visible: bool):
        """用户关闭独立模块窗口时，自动合并回属性面板。"""
        if visible:
            return
        app = QApplication.instance()
        if app is not None and app.closingDown():
            return
        if module_key in self._module_docks:
            self._attach_module_group(module_key)

    def _attach_module_group(self, module_key: str):
        """将独立模块合并回图层属性面板。"""
        if module_key not in self._module_docks:
            return

        dock = self._module_docks.pop(module_key)
        group = self._module_groups.get(module_key)
        if group is None:
            return

        main_window = self._get_main_window()
        if main_window is not None:
            main_window.removeDockWidget(dock)

        group.setParent(None)
        self._insert_group_back_in_order(module_key)
        dock.deleteLater()
        if not self._restoring_module_layout:
            self._persist_module_layout()

    def _detach_all_module_groups(self):
        for key in self._module_order:
            self._detach_module_group(key)

    def _attach_all_module_groups(self):
        for key in list(self._module_docks.keys()):
            self._attach_module_group(key)

    def restore_module_layout(self):
        """恢复模块拆分/组合状态和停靠布局。"""
        settings = self._get_module_settings()
        settings.beginGroup("layer_properties_modules")
        detached_keys = settings.value("detached_keys", [])
        settings.endGroup()

        if isinstance(detached_keys, str):
            detached_keys = [detached_keys]
        detached_keys = [k for k in detached_keys if k in self._module_groups]
        if not detached_keys:
            return

        main_window = self._get_main_window()
        if main_window is None:
            return

        self._restoring_module_layout = True
        try:
            for module_key in detached_keys:
                self._detach_module_group(module_key)
                dock = self._module_docks.get(module_key)
                if dock is None:
                    continue

                settings.beginGroup("layer_properties_modules")
                settings.beginGroup(module_key)
                floating = settings.value("floating", True, type=bool)
                dock_area = settings.value("dock_area", self._dock_area_to_int(Qt.RightDockWidgetArea), type=int)
                geometry = settings.value("geometry")
                settings.endGroup()
                settings.endGroup()

                if floating:
                    dock.setFloating(True)
                    if geometry is not None:
                        try:
                            dock.restoreGeometry(geometry)
                        except Exception:
                            pass
                else:
                    dock.setFloating(False)
                    main_window.addDockWidget(self._int_to_dock_area(dock_area), dock)
        finally:
            self._restoring_module_layout = False
            self._persist_module_layout()

    def save_module_layout(self):
        """对外保存接口，供主窗口关闭时调用。"""
        self._persist_module_layout()

    def update_aspect_lock_icon(self):
        """更新锁定比例按钮的图标 - 专业简洁设计"""
        from app.ui.icon_manager import IconManager

        if self.aspect_lock_btn.isChecked():
            # 锁定状态 - 使用图标管理器的链接图标
            IconManager.apply_icon_to_button(self.aspect_lock_btn, 'link', 'primary')
            self.aspect_lock_btn.setStyleSheet("""
                QPushButton {
                    background-color: #2F9CF4;
                    color: #ffffff;
                    border: 1px solid #55B2FF;
                    border-radius: 5px;
                    font-size: 13px;
                    font-weight: normal;
                    padding: 0px;
                    margin: 0px;
                }
                QPushButton:hover {
                    background-color: #55B2FF;
                    border-color: #7DC4FF;
                }
                QPushButton:pressed {
                    background-color: #1F7EC8;
                    border-color: #2F9CF4;
                }
            """)
            self.aspect_lock_btn.setToolTip("已锁定宽高比例 - 点击解锁")
        else:
            # 解锁状态 - 使用图标管理器的解锁图标
            IconManager.apply_icon_to_button(self.aspect_lock_btn, 'unlink', 'secondary')
            self.aspect_lock_btn.setStyleSheet("""
                QPushButton {
                    background-color: #202226;
                    color: #8E8E93;
                    border: 1px solid #34363A;
                    border-radius: 5px;
                    font-size: 13px;
                    font-weight: normal;
                    padding: 0px;
                    margin: 0px;
                }
                QPushButton:hover {
                    background-color: #292C31;
                    color: #C7C7C9;
                    border-color: #55B2FF;
                }
                QPushButton:pressed {
                    background-color: #1F7EC8;
                    border-color: #2F9CF4;
                }
            """)
            self.aspect_lock_btn.setToolTip("宽高比例未锁定 - 点击锁定")

    def toggle_aspect_ratio_lock(self):
        """切换锁定比例状态"""
        self.aspect_ratio_locked = self.aspect_lock_btn.isChecked()
        self.update_aspect_lock_icon()

        if self.current_layer:
            # 保存锁定状态到图层属性
            self.current_layer.aspect_ratio_locked = self.aspect_ratio_locked

            if self.aspect_ratio_locked:
                # 锁定时，根据当前控件的数值计算宽高比（优先使用用户设置的尺寸）
                try:
                    w = self.width_spin.value() if hasattr(self, 'width_spin') and self.width_spin else self.current_layer.width
                    h = self.height_spin.value() if hasattr(self, 'height_spin') and self.height_spin else self.current_layer.height
                    if h and h > 0:
                        self.original_aspect_ratio = float(w) / float(h)
                    else:
                        self.original_aspect_ratio = 1.0
                except Exception:
                    self.original_aspect_ratio = 1.0
                safe_print(f"锁定宽高比: {self.original_aspect_ratio:.3f}")
            else:
                safe_print("解锁宽高比")

            # 通知文档已更改
            if self.document:
                self.document.document_changed.emit()

    def calculate_locked_size(self, changed_dimension, new_value):
        """根据锁定的宽高比计算另一个尺寸"""
        if not self.aspect_ratio_locked or self.original_aspect_ratio <= 0:
            return None

        if changed_dimension == 'width':
            # 宽度改变，计算新高度
            new_height = int(round(new_value / self.original_aspect_ratio))
            return max(1, new_height)  # 确保高度至少为1
        elif changed_dimension == 'height':
            # 高度改变，计算新宽度
            new_width = int(round(new_value * self.original_aspect_ratio))
            return max(1, new_width)  # 确保宽度至少为1

        return None

    def set_controls_enabled(self, enabled):
        """启用或禁用所有控件"""
        if enabled and self.current_layer is None:
            safe_print("警告: 尝试启用控件，但current_layer为None")
            return

        safe_print(f"设置控件状态: {'启用' if enabled else '禁用'}")

        try:
            # 基本控件
            if hasattr(self, 'name_edit'):
                self.name_edit.setEnabled(enabled)

            # 获取锁定状态
            is_locked = enabled and self.current_layer and hasattr(self.current_layer, 'locked') and self.current_layer.locked

            # 位置和尺寸控件 - 只有在未锁定时启用
            position_enabled = enabled and not is_locked
            if hasattr(self, 'x_spin'):
                self.x_spin.setEnabled(position_enabled)
            if hasattr(self, 'y_spin'):
                self.y_spin.setEnabled(position_enabled)
            if hasattr(self, 'width_spin'):
                self.width_spin.setEnabled(position_enabled)
            if hasattr(self, 'height_spin'):
                self.height_spin.setEnabled(position_enabled)
            if hasattr(self, 'aspect_lock_btn'):
                self.aspect_lock_btn.setEnabled(position_enabled)

            # 样式控件 - 只有在未锁定时启用
            if hasattr(self, 'use_original_size_checkbox'):
                self.use_original_size_checkbox.setEnabled(position_enabled)
            if hasattr(self, 'fit_mode_combo'):
                self.fit_mode_combo.setEnabled(position_enabled)
            if hasattr(self, 'crop_direction_combo'):
                self.crop_direction_combo.setEnabled(position_enabled)

            # 混合模式
            if hasattr(self, 'blend_mode_combo'):
                self.blend_mode_combo.setEnabled(position_enabled)

            # 杂项控件
            if hasattr(self, 'opacity_slider'):
                self.opacity_slider.setEnabled(position_enabled)
            if hasattr(self, 'visible_checkbox'):
                self.visible_checkbox.setEnabled(enabled)  # 可见性总是可以更改
            if hasattr(self, 'locked_checkbox'):
                self.locked_checkbox.setEnabled(enabled)   # 锁定状态总是可以更改

            # 图像源控件
            source_enabled = enabled and not is_locked
            if hasattr(self, 'folder_radio'):
                self.folder_radio.setEnabled(source_enabled)
            if hasattr(self, 'file_radio'):
                self.file_radio.setEnabled(source_enabled)
            if hasattr(self, 'source_path_edit'):
                self.source_path_edit.setEnabled(source_enabled)  # 路径输入框与其他图像源控件同步
            if hasattr(self, 'browse_btn'):
                self.browse_btn.setEnabled(source_enabled)
            if hasattr(self, 'random_btn') and hasattr(self, 'folder_radio'):
                self.random_btn.setEnabled(source_enabled and self.folder_radio.isChecked())

            # 分身设置
            clone_enabled = enabled and not is_locked
            if hasattr(self, 'clone_enabled_checkbox'):
                self.clone_enabled_checkbox.setEnabled(clone_enabled)

                # 分身详细设置 - 只有在启用分身且未锁定时才启用
                clone_settings_enabled = clone_enabled and self.clone_enabled_checkbox.isChecked()
                if hasattr(self, 'clone_rows_spin'):
                    self.clone_rows_spin.setEnabled(clone_settings_enabled)
                if hasattr(self, 'clone_columns_spin'):
                    self.clone_columns_spin.setEnabled(clone_settings_enabled)
                if hasattr(self, 'row_spacing_spin'):
                    self.row_spacing_spin.setEnabled(clone_settings_enabled)
                if hasattr(self, 'column_spacing_spin'):
                    self.column_spacing_spin.setEnabled(clone_settings_enabled)
                if hasattr(self, 'clone_custom_size_checkbox'):
                    self.clone_custom_size_checkbox.setEnabled(clone_settings_enabled)
                    # 自定义大小控件只有在启用分身和启用自定义大小时才可用
                    custom_size_enabled = clone_settings_enabled and self.clone_custom_size_checkbox.isChecked()
                    if hasattr(self, 'clone_width_spin'):
                        self.clone_width_spin.setEnabled(custom_size_enabled)
                    if hasattr(self, 'clone_height_spin'):
                        self.clone_height_spin.setEnabled(custom_size_enabled)

            # 绑定入口已移至左侧栏，右侧不再维护 manage_binding_btn 状态

            # 形状控件设置
            shape_enabled = enabled and not is_locked
            if hasattr(self, 'shape_type_combo'):
                self.shape_type_combo.setEnabled(shape_enabled)
            if hasattr(self, 'shape_type_buttons'):
                for button in self.shape_type_buttons:
                    button.setEnabled(shape_enabled)
            if hasattr(self, 'shape_params_widget'):
                self.shape_params_widget.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_radius_spin'):
                self.vector_corner_radius_spin.setEnabled(shape_enabled)
            if hasattr(self, 'convert_to_path_btn'):
                self.convert_to_path_btn.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_tl_spin'):
                self.vector_corner_tl_spin.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_tr_spin'):
                self.vector_corner_tr_spin.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_br_spin'):
                self.vector_corner_br_spin.setEnabled(shape_enabled)
            if hasattr(self, 'vector_corner_bl_spin'):
                self.vector_corner_bl_spin.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_join_combo'):
                self.stroke_join_combo.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_cap_combo'):
                self.stroke_cap_combo.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_dash_length_spin'):
                self.stroke_dash_length_spin.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_dash_gap_spin'):
                self.stroke_dash_gap_spin.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_enabled_checkbox'):
                self.stroke_enabled_checkbox.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_width_spin'):
                self.stroke_width_spin.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_type_combo'):
                self.stroke_type_combo.setEnabled(shape_enabled)
            if hasattr(self, 'stroke_color_btn'):
                self.stroke_color_btn.setEnabled(shape_enabled)
            if hasattr(self, 'fill_solid_enabled_checkbox'):
                self.fill_solid_enabled_checkbox.setEnabled(shape_enabled)
            if hasattr(self, 'fill_mode_buttons'):
                for button in self.fill_mode_buttons:
                    button.setEnabled(shape_enabled)
            if hasattr(self, 'fill_solid_color_btn'):
                self.fill_solid_color_btn.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_enabled_checkbox'):
                self.fill_gradient_enabled_checkbox.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_start_btn'):
                self.fill_gradient_start_btn.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_end_btn'):
                self.fill_gradient_end_btn.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_angle_spin'):
                self.fill_gradient_angle_spin.setEnabled(shape_enabled)
            if hasattr(self, 'fill_gradient_opacity_spin'):
                self.fill_gradient_opacity_spin.setEnabled(shape_enabled)

            # 变换控件设置
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(self.current_layer if enabled and not is_locked else None)

            # 设置随机变换控件的图层
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(self.current_layer if enabled and not is_locked else None)

            # 同步独立模块窗口启用态（随面板整体状态变化）
            for dock in self._module_docks.values():
                dock.setEnabled(enabled)

        except Exception as e:
            safe_print(f"设置控件状态时出错: {e}")
            import traceback
            traceback.print_exc()

    def layer_selected(self, layer_index):
        """当选择图层时更新面板"""
        if not self.document:
            safe_print("警告: document为空，无法选择图层")
            return

        safe_print(f"选择图层: {layer_index}")

        # 检查索引是否有效
        if not hasattr(self.document, 'layers'):
            safe_print("警告: document没有layers属性")
            return

        if not isinstance(self.document.layers, list):
            safe_print(f"警告: document.layers不是列表，而是 {type(self.document.layers)}")
            return

        if layer_index < 0 or layer_index >= len(self.document.layers):
            safe_print(f"警告: 图层索引 {layer_index} 超出范围 0-{len(self.document.layers)-1}")
            self.current_layer = None
            self.set_controls_enabled(False)
            return

        # 设置当前图层并更新面板
        self.current_layer = self.document.layers[layer_index]
        print(f"图层已选中: {self.current_layer.name}")
        print(f"图层形状类型: {getattr(self.current_layer, 'shape_type', '无')}")

        if is_layer_group(self.current_layer):
            self.text_layer_panel.hide()
            self.shaped_layer_panel.hide()
            self.normal_layer_panel.show()
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(None)
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(None)
            self.update_panel()
            return

        # 检查图层类型并切换面板
        from app.models.text_layer import TextLayer
        try:
            from app.models.shaped_layer_new import ShapedLayer as NewShapedLayer
            ShapedLayerType = NewShapedLayer
        except ImportError:
            from app.models.shaped_layer import ShapedLayer
            ShapedLayerType = ShapedLayer
        is_multi = self._is_multi_layer_edit()
        is_text_layer = isinstance(self.current_layer, TextLayer)
        is_shaped_layer = isinstance(self.current_layer, ShapedLayerType)
        if is_multi:
            is_text_layer = is_text_layer and self._selected_layers_all_match(TextLayer)
            is_shaped_layer = is_shaped_layer and self._selected_layers_all_match(ShapedLayerType)

        if is_text_layer:
            # 显示文字图层面板，隐藏其他面板
            self.normal_layer_panel.hide()
            self.shaped_layer_panel.hide()
            self.text_layer_panel.show()
            self.text_layer_panel.set_text_layer(self.current_layer)
        elif is_shaped_layer:
            # 异形图层需要通用属性与特有属性同时可用：同时显示普通面板与异形面板
            self.text_layer_panel.hide()
            self.normal_layer_panel.show()
            self.shaped_layer_panel.show()
            self.shaped_layer_panel.set_layer(self.current_layer)

            # 设置变换控件的图层（通用属性仍然适用）
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(self.current_layer)
            # 设置随机变换控件的图层
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(self.current_layer)
        else:
            # 显示普通图层面板，隐藏其他面板
            self.text_layer_panel.hide()
            self.shaped_layer_panel.hide()
            self.normal_layer_panel.show()

            # 设置变换控件的图层
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(self.current_layer)

            # 设置随机变换控件的图层
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(self.current_layer)

        # 更新面板 - 这会同时设置控件状态
        self.update_panel()

    def update_panel(self):
        """更新面板显示当前选中图层的属性"""
        if self._is_export_ui_frozen():
            return
        if not self.document or not hasattr(self.document, 'selected_layer_index') or self.document.selected_layer_index < 0:
            self.set_controls_enabled(False)
            return

        layer_index = self.document.selected_layer_index
        if layer_index < 0 or layer_index >= len(self.document.layers):
            self.set_controls_enabled(False)
            return

        layer = self.document.layers[layer_index]
        self.current_layer = layer
        if is_layer_group(layer):
            self._update_group_panel(layer)
            return
        selected_layers = self._selected_editable_layers(allow_locked=True)
        is_multi = len(selected_layers) > 1

        safe_print(f"更新图层属性面板，图层索引: {layer_index}, 名称: {layer.name}")

        # 检查是否是文字图层
        from app.models.text_layer import TextLayer
        if isinstance(layer, TextLayer) and not is_multi:
            # 文字图层由文字图层面板处理
            return

        # 普通图层处理
        # 阻断信号连接，避免触发事件
        self._block_all_signals(True)

        try:
            # 更新控件值
            # 名称
            self.name_edit.setText(f"已选择 {len(selected_layers)} 个图层" if is_multi else layer.name)
            self.name_edit.setEnabled(not is_multi)

            # 位置
            self.x_spin.setValue(layer.x)
            self.y_spin.setValue(layer.y)

            # 尺寸
            self.width_spin.setValue(layer.width)
            self.height_spin.setValue(layer.height)
            mixed_tip = "多选：当前值不完全相同，修改后会应用到所有未锁定选中图层"
            for attr, widget in (
                ("x", self.x_spin),
                ("y", self.y_spin),
                ("width", self.width_spin),
                ("height", self.height_spin),
                ("opacity", self.opacity_slider),
            ):
                if hasattr(widget, 'setToolTip'):
                    widget.setToolTip(mixed_tip if is_multi and self._selected_layers_have_mixed_value(attr) else "")

            # 初始化锁定比例状态
            if hasattr(layer, 'aspect_ratio_locked'):
                self.aspect_ratio_locked = layer.aspect_ratio_locked
                self.aspect_lock_btn.setChecked(layer.aspect_ratio_locked)
            else:
                self.aspect_ratio_locked = False
                self.aspect_lock_btn.setChecked(False)

            # 计算并保存当前宽高比
            if layer.height > 0:
                self.original_aspect_ratio = layer.width / layer.height
            else:
                self.original_aspect_ratio = 1.0

            # 更新锁定按钮图标
            self.update_aspect_lock_icon()

            # 原始尺寸
            use_original_size = hasattr(layer, 'use_original_size') and layer.use_original_size
            self.use_original_size_checkbox.setChecked(use_original_size)

            # 适配模式
            fit_mode = 0
            if hasattr(layer, 'fit_mode'):
                fit_mode = layer.fit_mode if isinstance(layer.fit_mode, int) else 0
            self.fit_mode_combo.setCurrentIndex(fit_mode)

            # 裁剪方向
            crop_direction = 0
            if hasattr(layer, 'crop_direction'):
                crop_direction = layer.crop_direction if isinstance(layer.crop_direction, int) and 0 <= layer.crop_direction <= 4 else 0
            self.crop_direction_combo.setCurrentIndex(crop_direction)

            # 混合模式
            if hasattr(self, 'blend_mode_combo'):
                try:
                    if hasattr(layer, 'blend_mode'):
                        # 获取混合模式值
                        mode_value = layer.blend_mode

                        # 转换数字为字符串
                        mode_names = [
                            "正常", "正片叠底", "滤色", "叠加", "柔光", "强光",
                            "颜色减淡", "颜色加深", "变暗", "变亮", "差值", "排除",
                            "色相", "饱和度", "颜色", "明度"
                        ]

                        if isinstance(mode_value, int) and 0 <= mode_value < len(mode_names):
                            mode_text = mode_names[mode_value]
                        else:
                            # 如果是字符串或其他类型，尝试直接使用
                            mode_text = str(mode_value)

                        # 查找是否存在于下拉框中
                        index = self.blend_mode_combo.findText(mode_text)
                        if index >= 0:
                            self.blend_mode_combo.setCurrentIndex(index)
                        else:
                            # 如果没有找到，设为正常模式
                            self.blend_mode_combo.setCurrentText("正常")
                    else:
                        # 如果没有blend_mode属性，设为"正常"
                        self.blend_mode_combo.setCurrentText("正常")
                except Exception as e:
                    safe_print(f"设置混合模式出错: {e}")
                    self.blend_mode_combo.setCurrentText("正常")

            # 不透明度
            opacity = 1.0 if not hasattr(layer, 'opacity') else layer.opacity
            opacity_percent = int(opacity * 100)
            self.opacity_slider.setValue(opacity_percent)
            self.opacity_label.setText(f"{opacity_percent}%")

            # 可见性
            visible = True if not hasattr(layer, 'visible') else layer.visible
            self.visible_checkbox.setChecked(visible)

            # 锁定状态
            locked = False if not hasattr(layer, 'locked') else layer.locked
            self.locked_checkbox.setChecked(locked)

            # 形状属性
            if not hasattr(layer, 'shape_type'):
                shape_type = "rectangle"
            else:
                # 处理枚举类型，获取字符串值
                shape_type_value = layer.shape_type
                if hasattr(shape_type_value, 'value'):
                    shape_type = shape_type_value.value
                else:
                    shape_type = str(shape_type_value)

            shape_type_map = {
                "rectangle": "矩形",
                "right_trapezoid": "直角梯形",
                "circle": "圆形",
                "pentagon": "正五边形",
                "hexagon": "正六边形"
            }
            shape_type_text = shape_type_map.get(shape_type, "矩形")
            self.shape_type_combo.setCurrentText(shape_type_text)
            self._sync_shape_segment_buttons(shape_type_text)

            # 更新形状参数控件的可见性
            print(f"准备更新形状参数可见性: shape_type={shape_type}")
            print(f"形状参数容器是否可见: {self.shape_params_widget.isVisible()}")

            # 确保形状参数容器是可见的
            self.shape_params_widget.setVisible(True)
            print(f"设置形状参数容器为可见")

            self.update_shape_params_visibility(shape_type)

            # 梯形参数
            if hasattr(layer, 'trapezoid_top_width'):
                self.trapezoid_top_spin.setValue(layer.trapezoid_top_width)
            if hasattr(layer, 'trapezoid_bottom_width'):
                self.trapezoid_bottom_spin.setValue(layer.trapezoid_bottom_width)
            if hasattr(layer, 'trapezoid_slope_side'):
                side_text = "左侧" if layer.trapezoid_slope_side == "left" else "右侧"
                self.trapezoid_side_combo.setCurrentText(side_text)

            # 多边形参数
            if hasattr(layer, 'polygon_rotation'):
                self.polygon_rotation_spin.setValue(layer.polygon_rotation)
            if hasattr(layer, 'polygon_corner_radius'):
                self.polygon_radius_spin.setValue(layer.polygon_corner_radius)

            # 矢量外观属性
            self.vector_corner_tl_spin.setValue(int(getattr(layer, 'vector_corner_radius_tl', getattr(layer, 'corner_radius', 0))))
            self.vector_corner_tr_spin.setValue(int(getattr(layer, 'vector_corner_radius_tr', getattr(layer, 'corner_radius', 0))))
            self.vector_corner_br_spin.setValue(int(getattr(layer, 'vector_corner_radius_br', getattr(layer, 'corner_radius', 0))))
            self.vector_corner_bl_spin.setValue(int(getattr(layer, 'vector_corner_radius_bl', getattr(layer, 'corner_radius', 0))))
            self.vector_corner_radius_spin.setValue(max(
                self.vector_corner_tl_spin.value(),
                self.vector_corner_tr_spin.value(),
                self.vector_corner_br_spin.value(),
                self.vector_corner_bl_spin.value()
            ))
            join_map = {"miter": "斜接", "round": "圆角", "bevel": "斜切"}
            cap_map = {"butt": "平头", "round": "圆头", "square": "方头"}
            self.stroke_join_combo.setCurrentText(join_map.get(getattr(layer, 'stroke_join', 'miter'), "斜接"))
            self.stroke_cap_combo.setCurrentText(cap_map.get(getattr(layer, 'stroke_cap', 'butt'), "平头"))
            self.stroke_dash_length_spin.setValue(int(getattr(layer, 'stroke_dash_length', 0)))
            self.stroke_dash_gap_spin.setValue(int(getattr(layer, 'stroke_dash_gap', 0)))
            self.stroke_enabled_checkbox.setChecked(bool(getattr(layer, 'stroke_enabled', False)))
            self.stroke_width_spin.setValue(int(getattr(layer, 'stroke_width', 1)))
            self.stroke_type_combo.setCurrentIndex(int(getattr(layer, 'stroke_type', 0)))

            stroke_color = tuple(getattr(layer, 'stroke_color', (0, 0, 0, 255)))
            self._set_button_color(self.stroke_color_btn, stroke_color)
            fill_color = tuple(getattr(layer, 'color_overlay_color', (255, 0, 0, 255)))
            self._set_button_color(self.fill_solid_color_btn, fill_color)
            grad_colors = list(getattr(layer, 'gradient_overlay_colors', [(0, 0, 0, 255), (255, 255, 255, 255)]))
            if len(grad_colors) < 2:
                grad_colors = [(0, 0, 0, 255), (255, 255, 255, 255)]
            self._set_button_color(self.fill_gradient_start_btn, tuple(grad_colors[0]))
            self._set_button_color(self.fill_gradient_end_btn, tuple(grad_colors[1]))
            self.fill_solid_enabled_checkbox.setChecked(bool(getattr(layer, 'color_overlay_enabled', False)))
            self.fill_gradient_enabled_checkbox.setChecked(bool(getattr(layer, 'gradient_overlay_enabled', False)))
            self.fill_gradient_angle_spin.setValue(float(getattr(layer, 'gradient_overlay_angle', 90.0)))
            self.fill_gradient_opacity_spin.setValue(int(float(getattr(layer, 'gradient_overlay_opacity', 1.0)) * 100))
            self._sync_appearance_visibility()

            # 更新形状预览
            try:
                from app.models.layer_properties import ShapeType as LPShapeType
                lp_type = layer.shape_type if hasattr(layer, 'shape_type') else LPShapeType.RECTANGLE
                # 映射到预览用枚举
                mapping = {
                    LPShapeType.RECTANGLE: PreviewShapeType.RECTANGLE,
                    LPShapeType.RIGHT_TRAPEZOID: PreviewShapeType.RIGHT_TRAPEZOID,
                    LPShapeType.CIRCLE: PreviewShapeType.CIRCLE,
                    LPShapeType.PENTAGON: PreviewShapeType.PENTAGON,
                    LPShapeType.HEXAGON: PreviewShapeType.HEXAGON,
                }
                self.shape_preview.set_shape_type(mapping.get(lp_type, PreviewShapeType.RECTANGLE))
                if hasattr(layer, 'trapezoid_top_width') and hasattr(layer, 'trapezoid_bottom_width') and hasattr(layer, 'trapezoid_slope_side'):
                    self.shape_preview.set_trapezoid_params(
                        layer.trapezoid_top_width,
                        layer.trapezoid_bottom_width,
                        layer.trapezoid_slope_side
                    )
                sides = 5 if (hasattr(layer, 'shape_type') and str(getattr(layer, 'shape_type').value) == 'pentagon') else 6
                if hasattr(layer, 'polygon_rotation'):
                    self.shape_preview.set_polygon_params(layer.polygon_rotation, sides)
                self.shape_preview.update()
            except Exception:
                pass

            # 图像源类型
            is_folder = True if not hasattr(layer, 'is_folder') else layer.is_folder
            self.folder_radio.setChecked(is_folder)
            self.file_radio.setChecked(not is_folder)

            # 图像源路径
            image_source = "" if not hasattr(layer, 'image_source') or layer.image_source is None else layer.image_source
            self.source_path_edit.setText(image_source)

            # 当前图像预览 - 添加文件存在性检查
            if hasattr(layer, 'current_image_path') and layer.current_image_path:
                if os.path.isfile(layer.current_image_path):
                    filename = os.path.basename(layer.current_image_path)
                    self.current_image_label.setText(f"当前图像: {filename}")
                else:
                    # 文件不存在，清空路径并显示无
                    # 🔧 关键修复：使用公共属性setter
                    layer.current_image_path = None
                    self.current_image_label.setText("当前图像: 无")
            else:
                self.current_image_label.setText("当前图像: 无")

            # 更新分身设置 - 安全地检查属性是否存在
            has_clone_properties = (hasattr(layer, 'clone_enabled') and
                                  hasattr(layer, 'clone_rows') and
                                  hasattr(layer, 'clone_columns') and
                                  hasattr(layer, 'clone_row_spacing') and
                                  hasattr(layer, 'clone_column_spacing'))

            if has_clone_properties:
                try:
                    self.clone_enabled_checkbox.setChecked(layer.clone_enabled)
                    self.clone_rows_spin.setValue(layer.clone_rows)
                    self.clone_columns_spin.setValue(layer.clone_columns)
                    self.row_spacing_spin.setValue(layer.clone_row_spacing)
                    self.column_spacing_spin.setValue(layer.clone_column_spacing)

                    # 更新自定义大小设置
                    custom_size_enabled = getattr(layer, 'clone_custom_size_enabled', False)
                    self.clone_custom_size_checkbox.setChecked(custom_size_enabled)
                    self.clone_width_spin.setEnabled(custom_size_enabled)
                    self.clone_height_spin.setEnabled(custom_size_enabled)
                    if hasattr(layer, 'clone_custom_width'):
                        self.clone_width_spin.setValue(layer.clone_custom_width)
                    if hasattr(layer, 'clone_custom_height'):
                        self.clone_height_spin.setValue(layer.clone_custom_height)

                    mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                    mirror_text_map = {
                        'none': '无镜像',
                        'horizontal': '左右镜像',
                        'vertical': '上下镜像'
                    }
                    self.clone_mirror_combo.setCurrentText(mirror_text_map.get(mirror_mode, '无镜像'))
                except Exception as e:
                    safe_print(f"更新分身设置出错: {e}")
                    self.clone_enabled_checkbox.setChecked(False)
                    self.clone_rows_spin.setValue(1)
                    self.clone_columns_spin.setValue(1)
                    self.row_spacing_spin.setValue(0)
                    self.column_spacing_spin.setValue(0)
                    self.clone_mirror_combo.setCurrentText('无镜像')
            else:
                # 初始化分身属性为默认值
                if hasattr(layer, 'clone_enabled'):
                    layer.clone_enabled = False
                if hasattr(layer, 'clone_rows'):
                    layer.clone_rows = 1
                if hasattr(layer, 'clone_columns'):
                    layer.clone_columns = 1
                if hasattr(layer, 'clone_row_spacing'):
                    layer.clone_row_spacing = 0
                if hasattr(layer, 'clone_column_spacing'):
                    layer.clone_column_spacing = 0
                if not hasattr(layer, 'clone_mirror_mode'):
                    layer.clone_mirror_mode = 'none'

                self.clone_enabled_checkbox.setChecked(False)
                self.clone_rows_spin.setValue(1)
                self.clone_columns_spin.setValue(1)
                self.row_spacing_spin.setValue(0)
                self.column_spacing_spin.setValue(0)
                self.clone_mirror_combo.setCurrentText('无镜像')

            # 更新绑定设置 - 安全地检查属性是否存在
            has_bind_properties = (hasattr(layer, 'bind_enabled') and
                                 hasattr(layer, 'bind_group') and
                                 hasattr(layer, 'bind_strategy'))

            if has_bind_properties:
                try:
                    # 绑定状态显示
                    bind_status = f"已绑定到组: {layer.bind_group}" if layer.bind_group else "未绑定"
                    self.bind_status_label.setText(bind_status)

                    # 绑定策略已简化，不再需要UI控件
                    pass
                except Exception as e:
                    safe_print(f"更新绑定设置出错: {e}")
                    self.bind_status_label.setText("未绑定")
            else:
                # 初始化绑定属性为默认值
                if not hasattr(layer, 'bind_enabled'):
                    layer.bind_enabled = False
                if not hasattr(layer, 'bind_group'):
                    layer.bind_group = None
                if not hasattr(layer, 'bind_strategy'):
                    layer.bind_strategy = "filename"

                self.bind_status_label.setText("未绑定")

        finally:
            # 恢复信号连接
            self._block_all_signals(False)

        # 启用控件并设置其状态
        self.set_controls_enabled(True)
        if is_multi:
            self.name_edit.setEnabled(False)

    def _update_group_panel(self, group):
        """显示图层组的基础属性，组不参与位置/尺寸/效果编辑。"""
        self._block_all_signals(True)
        try:
            if self.text_layer_panel:
                self.text_layer_panel.hide()
            if hasattr(self, 'shaped_layer_panel') and self.shaped_layer_panel:
                self.shaped_layer_panel.hide()
            if hasattr(self, 'normal_layer_panel') and self.normal_layer_panel:
                self.normal_layer_panel.show()

            self.name_edit.setText(getattr(group, 'name', '图层组'))
            self.visible_checkbox.setChecked(bool(getattr(group, 'visible', True)))
            self.locked_checkbox.setChecked(bool(getattr(group, 'locked', False)))
            if hasattr(self, 'opacity_label'):
                self.opacity_label.setText("--")
            if hasattr(self, 'current_image_label'):
                self.current_image_label.setText("图层组")

            self.set_controls_enabled(False)
            self.name_edit.setEnabled(True)
            self.visible_checkbox.setEnabled(True)
            self.locked_checkbox.setEnabled(True)
            if hasattr(self, 'transform_widget'):
                self.transform_widget.set_layer(None)
            if hasattr(self, 'random_transform_widget'):
                self.random_transform_widget.set_layer(None)
        finally:
            self._block_all_signals(False)

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

    def update_layer_name(self, name):
        """更新图层名称"""
        if not self.current_layer:
            return

        safe_print(f"更新图层名称: {name}")  # 调试信息

        # 保存当前状态
        self.document.save_state("修改图层名称前")

        # 更新图层名称
        self.current_layer.name = name

        # 通知文档已更改
        self._emit_document_change(
            throttled=False,
            include_layer_changed=True,
            fields=["name"],
            reason="name"
        )

        # 保存更改后的状态
        self.document.save_state("修改图层名称")

    def update_layer_position(self):
        """更新图层位置"""
        if not self.current_layer:
            return
        if self._is_multi_layer_edit():
            changed = self._apply_to_selected_layers(
                {"x": self.x_spin.value(), "y": self.y_spin.value()},
                "批量移动图层",
                fields=["position"],
                allow_locked=False,
                clear_cache=False,
            )
            if changed:
                safe_print(f"批量更新图层位置: {changed} 个图层")
            return
        if self.current_layer.locked:
            return

        safe_print(f"更新图层位置: X={self.x_spin.value()}, Y={self.y_spin.value()}")  # 调试信息

        # 更新图层位置
        self.current_layer.x = self.x_spin.value()
        self.current_layer.y = self.y_spin.value()

        # 高频输入采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["position"], reason="position")
        self._save_state_deferred("移动图层")

    def update_layer_size(self):
        """更新图层尺寸"""
        if not self.current_layer or self._updating_size:
            return
        if self._is_multi_layer_edit():
            changed = self._apply_to_selected_layers(
                {"width": self.width_spin.value(), "height": self.height_spin.value()},
                "批量调整图层尺寸",
                fields=["size"],
                allow_locked=False,
                clear_cache=True,
            )
            if changed:
                safe_print(f"批量更新图层尺寸: {changed} 个图层")
            return
        if self.current_layer.locked:
            return

        # 防止递归更新
        self._updating_size = True

        try:
            new_width = self.width_spin.value()
            new_height = self.height_spin.value()

            safe_print(f"更新图层尺寸: 宽={new_width}, 高={new_height}")  # 调试信息

            # 如果启用了锁定比例，需要判断哪个尺寸发生了变化
            if self.aspect_ratio_locked:
                current_width = self.current_layer.width
                current_height = self.current_layer.height

                # 判断是宽度还是高度发生了变化
                width_changed = new_width != current_width
                height_changed = new_height != current_height

                if width_changed and not height_changed:
                    # 宽度改变，计算新高度
                    calculated_height = self.calculate_locked_size('width', new_width)
                    if calculated_height is not None:
                        new_height = calculated_height
                        # 使用 blockSignals 避免触发信号
                        self.height_spin.blockSignals(True)
                        self.height_spin.setValue(new_height)
                        self.height_spin.blockSignals(False)
                        safe_print(f"锁定比例: 宽度改变为{new_width}，自动调整高度为{new_height}")

                elif height_changed and not width_changed:
                    # 高度改变，计算新宽度
                    calculated_width = self.calculate_locked_size('height', new_height)
                    if calculated_width is not None:
                        new_width = calculated_width
                        # 使用 blockSignals 避免触发信号
                        self.width_spin.blockSignals(True)
                        self.width_spin.setValue(new_width)
                        self.width_spin.blockSignals(False)
                        safe_print(f"锁定比例: 高度改变为{new_height}，自动调整宽度为{new_width}")

                elif width_changed and height_changed:
                    # 两个都改变了，优先使用宽度的变化
                    calculated_height = self.calculate_locked_size('width', new_width)
                    if calculated_height is not None:
                        new_height = calculated_height
                        # 使用 blockSignals 避免触发信号
                        self.height_spin.blockSignals(True)
                        self.height_spin.setValue(new_height)
                        self.height_spin.blockSignals(False)
                        safe_print(f"锁定比例: 两个尺寸都改变，以宽度为准，调整高度为{new_height}")

            # 更新图层尺寸
            self.current_layer.width = new_width
            self.current_layer.height = new_height

            # 清除缓存图像以强制重新加载
            self.current_layer.cached_image = None

            # 高频输入采用节流刷新与延迟历史保存
            self._emit_document_change(throttled=True, fields=["size"], reason="size")
            self._save_state_deferred("调整图层尺寸")

        finally:
            self._updating_size = False

    def update_use_original_size(self, use_original):
        """更新是否使用智能裁剪"""
        if not self.current_layer:
            return

        safe_print(f"更新智能裁剪状态: {use_original}")

        # 保存当前状态用于撤销
        self.document.save_state("更改智能裁剪设置前")

        # 记录当前图层尺寸
        width = self.current_layer.width
        height = self.current_layer.height
        safe_print(f"图层当前尺寸: {width}x{height}")

        # 更新图层的智能裁剪设置
        self.current_layer.use_original_size = use_original

        # 清除缓存图像，强制重新加载和处理
        self.current_layer.cached_image = None

        # 立即更新图层图像，这会触发智能裁剪过程
        if self.current_layer.image_source:
            safe_print(f"正在应用智能裁剪")
            self.current_layer.get_random_image()

        # 确保尺寸控件始终可用，智能裁剪只影响图像处理方式，不影响UI控件状态
        enabled = not self.current_layer.locked
        self.width_spin.setEnabled(enabled)
        self.height_spin.setEnabled(enabled)

        # 通知文档内容已更改，触发重绘
        self.document.document_changed.emit()

        # 保存修改后的状态
        self.document.save_state("更改智能裁剪设置后")

    def update_fit_mode(self, mode):
        """更新图像适配模式"""
        if not self.current_layer:
            return

        safe_print(f"更新适配模式: {mode}")  # 调试信息

        # 保存当前状态
        self.document.save_state("更改适配模式前")

        # 更新适配模式
        self.current_layer.fit_mode = mode

        # 更新裁剪方向控件的启用状态
        from app.models.document import Layer
        self.crop_direction_combo.setEnabled(mode == Layer.FIT_SMART_CROP)

        # 清除缓存图像以强制重新加载
        self.current_layer.cached_image = None

        # 立即重新加载和处理图像
        if self.current_layer.image_source:
            safe_print(f"正在应用新的适配模式")
            self.current_layer.get_random_image()

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改适配模式")

    def update_crop_direction(self, direction):
        """更新裁剪方向"""
        if not self.current_layer:
            return

        safe_print(f"更新裁剪方向: {direction}")  # 调试信息

        # 保存当前状态
        self.document.save_state("更改裁剪方向前")

        # 更新裁剪方向
        self.current_layer.crop_direction = direction

        # 清除缓存图像以强制重新加载
        self.current_layer.cached_image = None

        # 立即重新加载和处理图像
        if self.current_layer.image_source:
            safe_print(f"正在应用新的裁剪方向")
            self.current_layer.get_random_image()

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改裁剪方向")

    def update_layer_opacity(self, opacity):
        """更新图层透明度"""
        if not self.current_layer:
            return

        safe_print(f"更新透明度: {opacity}%")  # 调试信息
        if self._is_multi_layer_edit():
            changed = self._apply_to_selected_layers(
                {"opacity": opacity / 100.0},
                "批量修改图层透明度",
                fields=["opacity"],
                allow_locked=False,
                clear_cache=False,
            )
            self.opacity_label.setText(f"{opacity}%")
            if changed:
                safe_print(f"批量更新透明度: {changed} 个图层")
            return

        # 更新图层透明度
        self.current_layer.opacity = opacity / 100.0
        self.opacity_label.setText(f"{opacity}%")

        # 滑块调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["opacity"], reason="opacity")
        self._save_state_deferred("修改图层透明度")

    def update_layer_visibility(self, visible):
        """更新图层可见性"""
        if not self.current_layer:
            return

        safe_print(f"更新可见性: {visible}")  # 调试信息

        if self._is_multi_layer_edit():
            self.document.save_state("批量切换图层可见性前")
            changed = self._apply_to_selected_layers(
                {"visible": visible},
                "批量切换图层可见性",
                fields=["visibility"],
                allow_locked=True,
                clear_cache=False,
            )
            return

        # 保存当前状态
        self.document.save_state("切换图层可见性前")

        # 更新图层可见性
        self.current_layer.visible = visible

        # 通知文档已更改
        self._emit_document_change(
            throttled=False,
            fields=["visibility"],
            reason="visibility"
        )

        # 保存更改后的状态
        self.document.save_state("切换图层可见性")

    def update_layer_lock(self, locked):
        """更新图层锁定状态"""
        if not self.current_layer:
            return

        safe_print(f"更新锁定状态: {locked}")  # 调试信息

        if is_layer_group(self.current_layer):
            self.document.save_state("切换图层组锁定状态前")
            self.current_layer.locked = locked
            self._emit_document_change(
                throttled=False,
                fields=["lock"],
                reason="lock"
            )
            self.document.save_state("切换图层组锁定状态")
            self._update_group_panel(self.current_layer)
            return

        if self._is_multi_layer_edit():
            self.document.save_state("批量切换图层锁定状态前")
            changed = self._apply_to_selected_layers(
                {"locked": locked},
                "批量切换图层锁定状态",
                fields=["lock"],
                allow_locked=True,
                clear_cache=False,
            )
            self.x_spin.setEnabled(not locked)
            self.y_spin.setEnabled(not locked)
            self.width_spin.setEnabled(not locked)
            self.height_spin.setEnabled(not locked)
            return

        # 保存当前状态
        self.document.save_state("切换图层锁定状态前")

        # 更新图层锁定状态
        self.current_layer.locked = locked

        # 调整位置和尺寸控件的启用状态
        self.x_spin.setEnabled(not locked)
        self.y_spin.setEnabled(not locked)

        # 尺寸控件始终可用，除非图层被锁定
        self.width_spin.setEnabled(not locked)
        self.height_spin.setEnabled(not locked)

        # 通知文档已更改
        self._emit_document_change(
            throttled=False,
            fields=["lock"],
            reason="lock"
        )

        # 保存更改后的状态
        self.document.save_state("切换图层锁定状态")

    def _ai_settings(self):
        return QSettings("批图王", "AIAssetStudio")

    def _ai_provider_store(self):
        return AIProviderStore(self._ai_settings())

    def refresh_ai_provider_choices(self):
        store = self._ai_provider_store()
        profiles = store.load_profiles()
        current_id = self.ai_provider_combo.currentData() or store.active_profile_id()
        self.ai_provider_combo.blockSignals(True)
        self.ai_provider_combo.clear()
        for profile in profiles:
            self.ai_provider_combo.addItem(profile.name, profile.profile_id)
        index = self.ai_provider_combo.findData(current_id)
        self.ai_provider_combo.setCurrentIndex(index if index >= 0 else (0 if profiles else -1))
        self.ai_provider_combo.blockSignals(False)
        self.refresh_ai_model_choices()

    def _selected_ai_profile(self):
        profile_id = self.ai_provider_combo.currentData()
        profiles = self._ai_provider_store().load_profiles()
        return next((profile for profile in profiles if profile.profile_id == profile_id), None)

    def refresh_ai_model_choices(self):
        current_model = self.ai_model_combo.currentText().strip()
        profile = self._selected_ai_profile()
        models = list(profile.models) if profile else []
        self.ai_model_combo.blockSignals(True)
        self.ai_model_combo.clear()
        self.ai_model_combo.addItems(models)
        if current_model and (not models or current_model in models):
            self.ai_model_combo.setCurrentText(current_model)
        elif models:
            self.ai_model_combo.setCurrentIndex(0)
        self.ai_model_combo.blockSignals(False)

    def build_ai_asset_request_for_current_layer(self):
        profile = self._selected_ai_profile()
        if profile is None:
            raise ValueError("未配置 AI 接口")
        layer_name = getattr(self.current_layer, "name", "ai_assets") or "ai_assets"
        return AIAssetRequest(
            base_url=profile.base_url,
            endpoint=profile.generation_endpoint,
            api_key=profile.api_key,
            model=self.ai_model_combo.currentText().strip(),
            model_field=profile.model_field,
            auth_mode=profile.auth_mode,
            prompt=self.ai_prompt_edit.toPlainText().strip(),
            negative_prompt=self.ai_negative_prompt_edit.toPlainText().strip(),
            count=self.ai_count_spin.value(),
            size=self.ai_size_combo.currentText(),
            group_name=layer_name,
            process_mode=str(self.ai_mode_combo.currentData() or "raw"),
        )

    def start_ai_generation_for_current_layer(self):
        if not self.current_layer:
            QMessageBox.warning(self, "无法生成", "请先选择一个图片图层。")
            return

        try:
            request = self.build_ai_asset_request_for_current_layer()
        except ValueError as exc:
            QMessageBox.warning(self, "参数缺失", str(exc))
            return
        if not request.base_url and not request.endpoint.startswith(("http://", "https://")):
            QMessageBox.warning(self, "参数缺失", "请在当前接口配置中填写 Base URL。")
            return
        if not request.endpoint:
            QMessageBox.warning(self, "参数缺失", "请在当前接口配置中填写生图 Endpoint。")
            return
        if not request.model:
            QMessageBox.warning(self, "参数缺失", "请选择或输入一个模型 ID。")
            return
        if not request.prompt:
            QMessageBox.warning(self, "参数缺失", "请填写当前图层的 AI 生图提示词。")
            return

        self.ai_generate_btn.setEnabled(False)
        self.ai_status_label.setText("正在生成...")
        task = _AIAssetLayerTask(AIAssetService(), request)
        task.signals.finished.connect(self._on_ai_generation_finished)
        self._ai_generation_task = task
        QThreadPool.globalInstance().start(task)

    @Slot(object)
    def _on_ai_generation_finished(self, result):
        self.ai_generate_btn.setEnabled(True)
        self._ai_generation_task = None
        if not isinstance(result, AIAssetResult) or not result.raw_paths:
            errors = getattr(result, "errors", None) or ["生成失败"]
            self.ai_status_label.setText(str(errors[0]))
            return

        output_dir = self._resolve_ai_output_dir(result)
        if not output_dir:
            self.ai_status_label.setText("生成完成，但没有可用输出目录")
            return

        self.apply_ai_output_to_current_layer(output_dir)
        self.ai_status_label.setText(f"已生成并写入图层: {output_dir}")

    @staticmethod
    def _resolve_ai_output_dir(result):
        paths = list(getattr(result, "output_paths", None) or getattr(result, "raw_paths", None) or [])
        if not paths:
            return ""
        first = paths[0]
        if os.path.isfile(first) or os.path.splitext(first)[1]:
            return os.path.dirname(first)
        return first

    def apply_ai_output_to_current_layer(self, output_dir):
        if not self.current_layer:
            return
        if self.document:
            self.document.save_state("AI生图更新图层前")

        self.current_layer.image_source = output_dir
        self.current_layer.is_folder = True
        if hasattr(self.current_layer, "current_image_path"):
            self.current_layer.current_image_path = None
        for attr in ("_cached_image", "_cached_source_image", "_cached_image_path", "_cached_source_path"):
            if hasattr(self.current_layer, attr):
                setattr(self.current_layer, attr, None)

        if hasattr(self, "folder_radio"):
            self.folder_radio.setChecked(True)
        if hasattr(self, "source_path_edit"):
            self.source_path_edit.setText(output_dir)
        if hasattr(self, "current_image_label"):
            self.current_image_label.setText("当前图像: 无")

        if self.document:
            if hasattr(self.document, "_invalidate_render_cache"):
                self.document._invalidate_render_cache()
            if hasattr(self.document, "layer_changed"):
                self.document.layer_changed.emit()
            if hasattr(self.document, "document_changed"):
                self.document.document_changed.emit()
            self.document.save_state("AI生图更新图层")

    def browse_image(self):
        """浏览并选择图像文件"""
        if not self.current_layer:
            return

        # 打开文件对话框
        if self.folder_radio.isChecked():
            folder_path = QFileDialog.getExistingDirectory(self, "选择图像文件夹")
            if folder_path:
                safe_print(f"选择文件夹: {folder_path}")  # 调试信息

                # 保存当前状态
                self.document.save_state("更改图层图像源前")

                # 更新图层图像源
                self.current_layer.image_source = folder_path
                self.current_layer.is_folder = True
                self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
                self.current_layer.cached_image = None

                # 清除快速渲染器缓存（关键修复）
                self.document._invalidate_render_cache()

                # 更新路径显示
                self.source_path_edit.setText(folder_path)
                self.current_image_label.setText("当前图像: 无")

                # 更新随机按钮状态
                self.random_btn.setEnabled(True)

                # 通知文档已更改
                self.document.document_changed.emit()

                # 保存更改后的状态
                self.document.save_state("更改图层图像源")
        else:
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择图像文件",
                "",
                "图像文件 (*.png *.jpg *.jpeg *.bmp *.gif);;所有文件 (*.*)"
            )

            if file_path:
                safe_print(f"选择文件: {file_path}")  # 调试信息

                # 保存当前状态
                self.document.save_state("更改图层图像源前")

                # 更新图层图像源
                self.current_layer.image_source = file_path
                self.current_layer.is_folder = False
                self.current_layer.current_image_path = file_path  # 🔧 修复：使用公共属性
                self.current_layer.cached_image = None

                # 清除快速渲染器缓存（关键修复）
                self.document._invalidate_render_cache()

                # 更新路径显示
                self.source_path_edit.setText(file_path)
                if os.path.isfile(file_path):
                    self.current_image_label.setText(f"当前图像: {os.path.basename(file_path)}")
                else:
                    # 文件不存在，清空并显示无
                    self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
                    self.current_image_label.setText("当前图像: 无")

                # 更新随机按钮状态
                self.random_btn.setEnabled(False)

                # 通知文档已更改
                self.document.document_changed.emit()

                # 保存更改后的状态
                self.document.save_state("更改图层图像源")

    def randomize_image(self):
        """随机选择图像"""
        if not self.current_layer or not self.current_layer.is_folder:
            return

        safe_print("随机选择图像")  # 调试信息

        # 保存当前状态
        self.document.save_state("随机选择图像前")

        # 使用文件限制进行随机选择
        image = self._randomize_layer_with_restrictions(self.current_layer)
        if image:
            if hasattr(self.current_layer, 'current_image_path') and self.current_layer.current_image_path and os.path.isfile(self.current_layer.current_image_path):
                self.current_image_label.setText(f"当前图像: {os.path.basename(self.current_layer.current_image_path)}")
            else:
                self.current_image_label.setText("当前图像: 无")

            # 如果使用原始尺寸，更新尺寸控件
            if self.current_layer.use_original_size:
                self.width_spin.setValue(self.current_layer.width)
                self.height_spin.setValue(self.current_layer.height)

            # 使渲染缓存失效，确保预览窗口显示最新的随机图像
            self.document._invalidate_render_cache()

            # 强制通知文档已更改，确保UI刷新
            self.document.document_changed.emit()
            self.document.layer_changed.emit()  # 也发送图层变化信号

            # 保存更改后的状态
            self.document.save_state("随机选择图像")

    def _randomize_layer_with_restrictions(self, layer):
        """使用文件限制随机化图层"""
        try:
            # 首先确保绑定管理器分析了文件限制
            if hasattr(self.document, 'binding_manager') and self.document.binding_manager.global_enabled:
                safe_print(f"[图层属性] 为单图层随机化分析文件限制...")
                self.document.binding_manager.analyze_and_restrict_layer_files(self.document.layers)

                # 检查是否是绑定图层
                if self.document.binding_manager.is_layer_bound(layer):
                    safe_print(f"[图层属性] 图层 '{layer.name}' 是绑定图层，使用绑定组随机化")
                    # 绑定图层：使用绑定管理器处理
                    bound_layers_mapping = self.document.binding_manager.randomize_bound_layers(self.document.layers)
                    if id(layer) in bound_layers_mapping:
                        safe_print(f"[图层属性] 绑定图层 '{layer.name}' 已更新")
                        return layer.cached_image  # 返回更新后的图像
                    else:
                        safe_print(f"[图层属性] 警告：绑定图层 '{layer.name}' 未在绑定结果中")
                        return layer.get_random_image(force_random=True)
                else:
                    # 非绑定图层：使用文件限制
                    restricted_files = self.document.binding_manager.get_layer_file_restrictions(layer)
                    if restricted_files:
                        safe_print(f"[图层属性] 图层 '{layer.name}' 使用文件限制随机化，可选文件: {len(restricted_files)} 个")
                        return layer.get_random_image(force_random=True, restrict_to_bound_files=restricted_files)
                    else:
                        safe_print(f"[图层属性] 图层 '{layer.name}' 无文件限制，正常随机化")
                        return layer.get_random_image(force_random=True)
            else:
                # 没有绑定管理器或未启用，正常随机化
                safe_print(f"[图层属性] 图层 '{layer.name}' 正常随机化（无绑定管理器）")
                return layer.get_random_image(force_random=True)

        except Exception as e:
            safe_print(f"[图层属性] 随机化图层 '{layer.name}' 时出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时回退到正常随机化
            return layer.get_random_image(force_random=True)

    def handle_folder_toggled(self, checked):
        """处理文件夹单选按钮状态变化"""
        if checked and not self._source_type_changing:
            self.toggle_source_type(self.folder_radio)

    def handle_file_toggled(self, checked):
        """处理单个文件单选按钮状态变化"""
        if checked and not self._source_type_changing:
            self.toggle_source_type(self.file_radio)

    def toggle_source_type(self, button):
        """切换图像源类型（文件夹/单个文件）"""
        if not self.current_layer:
            return

        # 防止递归
        self._source_type_changing = True
        try:
            is_folder = (button == self.folder_radio)
            safe_print(f"切换图像源类型: {'文件夹' if is_folder else '单个文件'}")  # 调试信息

            # 如果状态没有变化，则不处理
            if self.current_layer.is_folder == is_folder:
                self._source_type_changing = False
                return

            # 保存当前状态
            if self.document:
                self.document.save_state("切换图像源类型前")

            # 更新图像源类型
            self.current_layer.is_folder = is_folder

            # 清除当前图像
            self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
            self.current_layer.cached_image = None
            self.current_image_label.setText("当前图像: 无")

            # 更新随机按钮状态
            self.random_btn.setEnabled(is_folder)

            # 标记文档为已修改
            if self.document:
                self.document.is_modified = True
                self.document.save_state("切换图像源类型")

                # 延迟发送变更信号以避免递归
                QTimer.singleShot(0, self.document.document_changed.emit)

            # 确保UI更新以反映变化
            self.update_panel()
        finally:
            self._source_type_changing = False

    def on_layer_changed(self):
        """当图层列表变化时调用"""
        safe_print("图层列表已变化")
        # 如果有图层但没有选中的图层，自动选择第一个
        if hasattr(self.document, 'layers') and len(self.document.layers) > 0:
            if self.document.selected_layer_index < 0:
                safe_print("自动选择第一个图层")
                self.document.select_layer(0)
            elif self.document.selected_layer_index >= len(self.document.layers):
                safe_print("选中索引超出范围，重置为最后一个图层")
                # 修复：重置为最后一个图层而不是第一个，这样更符合用户预期
                # 因为通常删除图层等操作会导致索引超出范围，选择最后一个图层更合理
                self.document.select_layer(len(self.document.layers) - 1)

    def set_document(self, document):
        """设置关联的文档"""
        # 如果有旧文档，断开信号连接
        if self.document:
            self.document.layer_changed.disconnect(self.on_layer_changed)
            self.document.layer_selected.disconnect(self.layer_selected)
            if hasattr(self.document, 'layers_selection_changed'):
                try:
                    self.document.layers_selection_changed.disconnect(self._on_layers_selection_changed)
                except Exception:
                    pass
            self.document.document_changed.disconnect(self.delayed_update_panel)

        # 设置新文档
        self.document = document
        self.current_layer = None
        if self.text_layer_panel:
            self.text_layer_panel.set_document(document)

        # 如果新文档不为空，连接信号
        if self.document:
            self.document.layer_changed.connect(self.on_layer_changed)
            self.document.layer_selected.connect(self.layer_selected)
            if hasattr(self.document, 'layers_selection_changed'):
                self.document.layers_selection_changed.connect(self._on_layers_selection_changed)
            self.document.document_changed.connect(self.delayed_update_panel)

            # 如果文档有图层且已选择图层，直接触发选择
            if hasattr(self.document, 'layers') and len(self.document.layers) > 0:
                if hasattr(self.document, 'selected_layer_index') and self.document.selected_layer_index >= 0:
                    self.layer_selected(self.document.selected_layer_index)
                else:
                    # 自动选择第一个图层
                    self.document.select_layer(0)
        else:
            # 禁用所有控件
            self.set_controls_enabled(False)

    def update_clone_enabled(self, enabled):
        """更新图层分身启用状态"""
        if not self.current_layer:
            return

        # 保存当前状态
        if self.document:
            self.document.save_state("修改图层分身设置前")

        safe_print(f"更新图层分身: {enabled}")

        # 确保图层有所有必要的分身属性
        self._ensure_clone_properties()

        # 如果启用分身，并且行列都是1，则自动设置为2x2以便立即看到效果
        if enabled and self.current_layer.clone_rows == 1 and self.current_layer.clone_columns == 1:
            self.current_layer.clone_rows = 2
            self.current_layer.clone_columns = 2
            self.clone_rows_spin.setValue(2)
            self.clone_columns_spin.setValue(2)
            # 确保UI更新以反映新值
            self.clone_rows_spin.valueChanged.emit(2)
            self.clone_columns_spin.valueChanged.emit(2)

        # 设置分身启用状态
        self.current_layer.clone_enabled = enabled

        # 清除图层缓存以便重新渲染
        self.current_layer.cached_image = None

        # 启用或禁用分身设置控件
        self.clone_rows_spin.setEnabled(enabled)
        self.clone_columns_spin.setEnabled(enabled)
        self.row_spacing_spin.setEnabled(enabled)
        self.column_spacing_spin.setEnabled(enabled)

        # 绑定入口已移至左侧栏，这里无需管理右侧按钮状态

        # 通知文档变化
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改图层分身设置后")

    def update_clone_mirror_mode_index(self, index):
        if not self.current_layer:
            return
        if self.document:
            self.document.save_state("修改图层分身镜像前")
        text = self.clone_mirror_combo.itemText(index)
        mode_map = {"无镜像": "none", "左右镜像": "horizontal", "上下镜像": "vertical"}
        self._ensure_clone_properties()
        self.current_layer.clone_mirror_mode = mode_map.get(text, "none")
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.layer_changed.emit()
            self.document.save_state("修改图层分身镜像后")

    def _ensure_clone_properties(self):
        """确保图层具有所有必要的分身属性"""
        if not self.current_layer:
            return

        # 设置默认的分身属性（如果不存在）
        if not hasattr(self.current_layer, 'clone_enabled'):
            self.current_layer.clone_enabled = False
        if not hasattr(self.current_layer, 'clone_rows'):
            self.current_layer.clone_rows = 2  # 默认设置为2行
        if not hasattr(self.current_layer, 'clone_columns'):
            self.current_layer.clone_columns = 2  # 默认设置为2列
        if not hasattr(self.current_layer, 'clone_row_spacing'):
            self.current_layer.clone_row_spacing = 10  # 设置默认间距
        if not hasattr(self.current_layer, 'clone_column_spacing'):
            self.current_layer.clone_column_spacing = 10  # 设置默认间距
        if not hasattr(self.current_layer, 'clone_mirror_mode'):
            self.current_layer.clone_mirror_mode = "none"
        if not hasattr(self.current_layer, 'clone_custom_size_enabled'):
            self.current_layer.clone_custom_size_enabled = False
        if not hasattr(self.current_layer, 'clone_custom_width'):
            self.current_layer.clone_custom_width = self.current_layer.width if hasattr(self.current_layer, 'width') else 100
        if not hasattr(self.current_layer, 'clone_custom_height'):
            self.current_layer.clone_custom_height = self.current_layer.height if hasattr(self.current_layer, 'height') else 100

        if not hasattr(self.current_layer, 'clone_fill_enabled'):
            self.current_layer.clone_fill_enabled = False
        if not hasattr(self.current_layer, 'clone_fill_mode'):
            self.current_layer.clone_fill_mode = "grid"
        if not hasattr(self.current_layer, 'clone_fill_spacing'):
            self.current_layer.clone_fill_spacing = 0
        if not hasattr(self.current_layer, 'clone_fill_margin'):
            self.current_layer.clone_fill_margin = 0  # 添加边距属性初始化
        if not hasattr(self.current_layer, 'clone_fill_angle'):
            self.current_layer.clone_fill_angle = 0.0

        # 添加get_clone_positions方法如果不存在
        if not hasattr(self.current_layer, 'get_clone_positions') or not callable(getattr(self.current_layer, 'get_clone_positions')):
            # 创建一个更稳定的方法，不依赖闭包捕获层属性
            def get_clone_positions(self):
                """获取分身的所有位置，返回(x, y)坐标列表"""
                if not self.clone_enabled:
                    return [(self.x, self.y)]  # 未启用分身时只返回原始位置

                # 如果启用了填充模式，使用填充算法
                if hasattr(self, 'clone_fill_enabled') and self.clone_fill_enabled:
                    return self._get_fill_positions()

                # 否则使用基本网格分身
                positions = []
                for row in range(self.clone_rows):
                    for col in range(self.clone_columns):
                        x = self.x + col * (self.width + self.clone_column_spacing)
                        y = self.y + row * (self.height + self.clone_row_spacing)
                        positions.append((x, y))

                return positions

            def _get_fill_positions(self):
                """获取填充模式的位置，支持网格、错位、边框排列"""
                spacing = int(getattr(self, 'clone_fill_spacing', 0))
                angle_deg = float(getattr(self, 'clone_fill_angle', 0.0))
                mode = str(getattr(self, 'clone_fill_mode', 'grid'))
                margin = int(getattr(self, 'clone_fill_margin', 0))  # 新增边距参数

                dx = max(1, int(self.width + spacing))
                dy = max(1, int(self.height + spacing))
                positions = []

                # 获取画布尺寸（使用估计值或默认值）
                canvas_width = getattr(self, '_canvas_width', 800)  # 默认值
                canvas_height = getattr(self, '_canvas_height', 600)  # 默认值

                base_x = self.x
                base_y = self.y

                import math
                angle = math.radians(angle_deg % 360.0)
                cx = canvas_width / 2.0
                cy = canvas_height / 2.0

                if mode == 'border':
                    # 边框排列：确保四角有元素，行距列距统一，支持边距
                    # 应用边距到画布尺寸
                    effective_width = canvas_width - 2 * margin
                    effective_height = canvas_height - 2 * margin

                    # 计算每边的元素数量，确保四角都有元素
                    # 顶部和底部：计算水平方向可以放置的元素数量（包括两端的角）
                    top_bottom_count = max(2, (effective_width + dx) // dx)  # 至少2个（两角）
                    # 左侧和右侧：计算垂直方向可以放置的元素数量（包括两端的角）
                    left_right_count = max(2, (effective_height + dy) // dy)  # 至少2个（两角）

                    # 计算统一的间距，确保元素均匀分布
                    if top_bottom_count > 1:
                        top_bottom_spacing = (effective_width - self.width) / (top_bottom_count - 1)
                    else:
                        top_bottom_spacing = 0

                    if left_right_count > 1:
                        left_right_spacing = (effective_height - self.height) / (left_right_count - 1)
                    else:
                        left_right_spacing = 0

                    # 顶部边缘（包括左上角和右上角）
                    for i in range(top_bottom_count):
                        x = margin + int(i * top_bottom_spacing)
                        if x <= canvas_width - self.width - margin:  # 确保不超出有效区域
                            positions.append((x, margin))

                    # 底部边缘（包括左下角和右下角）
                    for i in range(top_bottom_count):
                        x = margin + int(i * top_bottom_spacing)
                        if x <= canvas_width - self.width - margin:  # 确保不超出有效区域
                            positions.append((x, canvas_height - self.height - margin))

                    # 左侧边缘（不包括已经放置的角落元素）
                    for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                        y = margin + int(i * left_right_spacing)
                        if margin < y < canvas_height - self.height - margin:  # 确保有效位置
                            positions.append((margin, y))

                    # 右侧边缘（不包括已经放置的角落元素）
                    for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                        y = margin + int(i * left_right_spacing)
                        if margin < y < canvas_height - self.height - margin:  # 确保有效位置
                            positions.append((canvas_width - self.width - margin, y))
                else:
                    # 网格或错位排列
                    start_y = -self.height
                    end_y = canvas_height + self.height
                    step_y = dy
                    i_row = 0
                    for row_y in range(start_y, end_y + 1, step_y):
                        offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                        for col_x in range(-self.width, canvas_width + self.width + 1, dx):
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

                return positions if positions else [(self.x, self.y)]

            # 使用方法类型绑定到图层实例
            import types
            self.current_layer.get_clone_positions = types.MethodType(get_clone_positions, self.current_layer)

    def update_clone_custom_size_enabled(self, enabled):
        """更新分身自定义大小启用状态"""
        if not self.current_layer:
            return

        # 保存当前状态
        if self.document:
            self.document.save_state("修改分身自定义大小设置前")

        safe_print(f"更新分身自定义大小: {enabled}")

        # 确保图层有所有必要的分身属性
        self._ensure_clone_properties()

        # 设置自定义大小启用状态
        self.current_layer.clone_custom_size_enabled = enabled

        # 启用或禁用自定义大小控件
        self.clone_width_spin.setEnabled(enabled)
        self.clone_height_spin.setEnabled(enabled)

        # 如果启用，设置初始值为当前图层大小
        if enabled:
            self.clone_width_spin.setValue(self.current_layer.width)
            self.clone_height_spin.setValue(self.current_layer.height)
            self.current_layer.clone_custom_width = self.current_layer.width
            self.current_layer.clone_custom_height = self.current_layer.height

        # 清除图层缓存以便重新渲染
        self.current_layer.cached_image = None

        # 通知文档变化
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改分身自定义大小设置后")

    def update_clone_custom_size(self):
        """更新分身自定义大小"""
        if not self.current_layer:
            return

        # 确保图层有所有必要的分身属性
        self._ensure_clone_properties()

        # 更新自定义大小
        self.current_layer.clone_custom_width = self.clone_width_spin.value()
        self.current_layer.clone_custom_height = self.clone_height_spin.value()

        # 清除图层缓存以便重新渲染
        self.current_layer.cached_image = None

        safe_print(f"[UI] 更新分身自定义大小: 宽={self.current_layer.clone_custom_width}, 高={self.current_layer.clone_custom_height}")
        safe_print(f"[UI] 当前图层: {self.current_layer.name}, 原始尺寸: {self.current_layer.width}x{self.current_layer.height}")
        safe_print(f"[UI] 自定义大小启用: {self.current_layer.clone_custom_size_enabled}")

        # 通知文档变化
        if self.document:
            self._emit_document_change(throttled=True, fields=["clone_custom_size"], reason="clone_custom_size")
            # 强制更新画布
            if hasattr(self.document, 'canvas_updated'):
                self.document.canvas_updated.emit()
            self._save_state_deferred("修改分身自定义大小")

    def update_clone_settings(self):
        """更新图层分身设置"""
        if not self.current_layer:
            return

        try:
            # 确保图层有所有必要的分身属性
            self._ensure_clone_properties()

            # 更新图层分身设置
            self.current_layer.clone_rows = self.clone_rows_spin.value()
            self.current_layer.clone_columns = self.clone_columns_spin.value()
            self.current_layer.clone_row_spacing = self.row_spacing_spin.value()
            self.current_layer.clone_column_spacing = self.column_spacing_spin.value()

            # 清除图层缓存以便重新渲染
            self.current_layer.cached_image = None

            safe_print(f"更新分身设置: 行={self.current_layer.clone_rows}, 列={self.current_layer.clone_columns}, 行距={self.current_layer.clone_row_spacing}, 列距={self.current_layer.clone_column_spacing}")

            # 通知文档变化
            if self.document:
                self._emit_document_change(throttled=True, fields=["clone_grid"], reason="clone_grid")
                self._save_state_deferred("修改图层分身设置")

        except Exception as e:
            safe_print(f"更新分身设置出错: {e}")

    def update_fill_enabled(self, enabled):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_enabled = bool(enabled)
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充启用")

    def update_fill_mode(self, index):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        text = self.fill_mode_combo.itemText(index)
        mode_map = {"常规网格": "grid", "错位排列": "staggered", "边框排列": "border"}
        self.current_layer.clone_fill_mode = mode_map.get(text, "grid")
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充排列")

    def update_fill_spacing(self, value):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_spacing = int(value)
        self.current_layer.cached_image = None
        if self.document:
            self._emit_document_change(throttled=True, fields=["fill_spacing"], reason="fill_spacing")
            self._save_state_deferred("修改元素填充间距")

    def update_fill_margin(self, value):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_margin = int(value)
        self.current_layer.cached_image = None
        if self.document:
            self._emit_document_change(throttled=True, fields=["fill_margin"], reason="fill_margin")
            self._save_state_deferred("修改元素填充边距")

    def update_fill_angle(self, value):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_angle = float(value)
        self.current_layer.cached_image = None
        if self.document:
            self._emit_document_change(throttled=True, fields=["fill_angle"], reason="fill_angle")
            self._save_state_deferred("修改元素填充角度")

    def sync_ui_with_layer(self):
        """同步UI控件值与当前图层属性"""
        if not self.current_layer:
            return

        # 阻止信号，避免递归更新
        self.blockSignals(True)

        try:
            # 同步名称 - 添加调试信息
            print(f"[调试] 图层对象: {self.current_layer}")
            print(f"[调试] 图层name属性: {self.current_layer.name}")
            print(f"[调试] name属性类型: {type(self.current_layer.name)}")

            # 同步名称
            layer_name = self.current_layer.name
            if isinstance(layer_name, str):
                self.name_edit.setText(layer_name)
            else:
                print(f"[错误] 图层名称不是字符串，而是: {type(layer_name)}")
                # 尝试获取字符串表示
                self.name_edit.setText(str(layer_name))

            # 同步位置
            self.x_spin.setValue(self.current_layer.x)
            self.y_spin.setValue(self.current_layer.y)

            # 同步尺寸
            self.width_spin.setValue(self.current_layer.width)
            self.height_spin.setValue(self.current_layer.height)

            # 同步透明度
            opacity_percent = int(self.current_layer.opacity * 100)
            self.opacity_slider.setValue(opacity_percent)
            self.opacity_label.setText(f"{opacity_percent}%")

            # 同步其他控件状态
            self.visible_checkbox.setChecked(self.current_layer.visible)
            self.locked_checkbox.setChecked(self.current_layer.locked)
            self.use_original_size_checkbox.setChecked(self.current_layer.use_original_size)

            # 同步适配模式
            self.fit_mode_combo.setCurrentIndex(self.current_layer.fit_mode)

            # 同步裁剪方向
            self.crop_direction_combo.setCurrentIndex(self.current_layer.crop_direction)
            self.crop_direction_combo.setEnabled(self.current_layer.fit_mode == 1)

            # 同步启用状态
            self.width_spin.setEnabled(not self.current_layer.use_original_size and not self.current_layer.locked)
            self.height_spin.setEnabled(not self.current_layer.use_original_size and not self.current_layer.locked)

            # 同步图像路径
            if hasattr(self.current_layer, 'image_source') and self.current_layer.image_source:
                self.source_path_edit.setText(self.current_layer.image_source)
                # 更新图像名称显示（校验文件存在性）
                if hasattr(self.current_layer, 'current_image_path') and self.current_layer.current_image_path and os.path.isfile(self.current_layer.current_image_path):
                    self.current_image_label.setText(f"当前图像: {os.path.basename(self.current_layer.current_image_path)}")
                else:
                    # 文件不存在或未设置
                    if hasattr(self.current_layer, 'current_image_path'):
                        self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
                    self.current_image_label.setText("当前图像: 无")
                # 更新随机按钮状态
                self.random_btn.setEnabled(self.current_layer.is_folder)
            else:
                self.source_path_edit.setText("")
                self.current_image_label.setText("当前图像: 无")
                self.random_btn.setEnabled(False)

            # 同步随机变换控件
            if hasattr(self, 'random_transform_widget') and self.random_transform_widget:
                self.random_transform_widget.update_from_layer()
                safe_print("同步随机变换控件")

            # 同步形状参数可见性
            if hasattr(self.current_layer, 'shape_type'):
                shape_type = self.current_layer.shape_type
                if hasattr(shape_type, 'value'):
                    shape_type_value = shape_type.value
                else:
                    shape_type_value = str(shape_type)
                print(f"同步形状参数可见性: {shape_type_value}")

                # 同步形状类型下拉框
                shape_type_map = {
                    "rectangle": "矩形",
                    "right_trapezoid": "直角梯形",
                    "circle": "圆形",
                    "pentagon": "正五边形",
                    "hexagon": "正六边形"
                }
                shape_type_text = shape_type_map.get(shape_type_value, "矩形")
                self.shape_type_combo.setCurrentText(shape_type_text)
                self._sync_shape_segment_buttons(shape_type_text)

                self.update_shape_params_visibility(shape_type_value)

            mirror_mode = getattr(self.current_layer, 'clone_mirror_mode', 'none')
            mirror_text_map = {
                'none': '无镜像',
                'horizontal': '左右镜像',
                'vertical': '上下镜像'
            }
            self.clone_mirror_combo.setCurrentText(mirror_text_map.get(mirror_mode, '无镜像'))

            safe_print(f"同步UI与图层完成: 尺寸={self.current_layer.width}x{self.current_layer.height}")
        finally:
            # 恢复信号
            self.blockSignals(False)

    def _block_all_signals(self, block):
        """阻断或恢复所有控件的信号"""
        # 阻断主要控件的信号以避免在更新界面时触发事件
        self.name_edit.blockSignals(block)
        self.x_spin.blockSignals(block)
        self.y_spin.blockSignals(block)
        self.width_spin.blockSignals(block)
        self.height_spin.blockSignals(block)
        self.use_original_size_checkbox.blockSignals(block)
        self.fit_mode_combo.blockSignals(block)
        self.crop_direction_combo.blockSignals(block)
        self.opacity_slider.blockSignals(block)
        self.visible_checkbox.blockSignals(block)
        self.locked_checkbox.blockSignals(block)
        self.folder_radio.blockSignals(block)
        self.file_radio.blockSignals(block)
        self.clone_enabled_checkbox.blockSignals(block)
        self.clone_rows_spin.blockSignals(block)
        self.clone_columns_spin.blockSignals(block)
        self.row_spacing_spin.blockSignals(block)
        self.column_spacing_spin.blockSignals(block)
        if hasattr(self, 'clone_mirror_combo'):
            self.clone_mirror_combo.blockSignals(block)
        self.source_path_edit.blockSignals(block)  # 阻断路径输入框信号

        # 混合模式下拉框
        if hasattr(self, 'blend_mode_combo'):
            self.blend_mode_combo.blockSignals(block)

        # 形状控件
        if hasattr(self, 'shape_type_combo'):
            self.shape_type_combo.blockSignals(block)
        if hasattr(self, 'shape_type_buttons'):
            for button in self.shape_type_buttons:
                button.blockSignals(block)
        if hasattr(self, 'trapezoid_top_spin'):
            self.trapezoid_top_spin.blockSignals(block)
        if hasattr(self, 'trapezoid_bottom_spin'):
            self.trapezoid_bottom_spin.blockSignals(block)
        if hasattr(self, 'trapezoid_side_combo'):
            self.trapezoid_side_combo.blockSignals(block)
        if hasattr(self, 'polygon_rotation_spin'):
            self.polygon_rotation_spin.blockSignals(block)
        if hasattr(self, 'polygon_radius_spin'):
            self.polygon_radius_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_radius_spin'):
            self.vector_corner_radius_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_tl_spin'):
            self.vector_corner_tl_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_tr_spin'):
            self.vector_corner_tr_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_br_spin'):
            self.vector_corner_br_spin.blockSignals(block)
        if hasattr(self, 'vector_corner_bl_spin'):
            self.vector_corner_bl_spin.blockSignals(block)
        if hasattr(self, 'stroke_join_combo'):
            self.stroke_join_combo.blockSignals(block)
        if hasattr(self, 'stroke_cap_combo'):
            self.stroke_cap_combo.blockSignals(block)
        if hasattr(self, 'stroke_dash_length_spin'):
            self.stroke_dash_length_spin.blockSignals(block)
        if hasattr(self, 'stroke_dash_gap_spin'):
            self.stroke_dash_gap_spin.blockSignals(block)
        if hasattr(self, 'stroke_enabled_checkbox'):
            self.stroke_enabled_checkbox.blockSignals(block)
        if hasattr(self, 'stroke_width_spin'):
            self.stroke_width_spin.blockSignals(block)
        if hasattr(self, 'stroke_type_combo'):
            self.stroke_type_combo.blockSignals(block)
        if hasattr(self, 'fill_solid_enabled_checkbox'):
            self.fill_solid_enabled_checkbox.blockSignals(block)
        if hasattr(self, 'fill_gradient_enabled_checkbox'):
            self.fill_gradient_enabled_checkbox.blockSignals(block)
        if hasattr(self, 'fill_mode_buttons'):
            for button in self.fill_mode_buttons:
                button.blockSignals(block)
        if hasattr(self, 'fill_gradient_angle_spin'):
            self.fill_gradient_angle_spin.blockSignals(block)
        if hasattr(self, 'fill_gradient_opacity_spin'):
            self.fill_gradient_opacity_spin.blockSignals(block)

        # 变换控件
        if hasattr(self, 'transform_widget'):
            # 阻断变换控件内部的信号
            self.transform_widget.blockSignals(block)

    def update_blend_mode(self, mode):
        """更新混合模式"""
        if not self.current_layer:
            return

        safe_print(f"更新混合模式: {mode}")  # 调试信息

        # 保存当前状态
        self.document.save_state("更改混合模式前")

        # 转换混合模式字符串为数字
        mode_map = {
            "正常": 0,
            "正片叠底": 1,
            "滤色": 2,
            "叠加": 3,
            "柔光": 4,
            "强光": 5,
            "颜色减淡": 6,
            "颜色加深": 7,
            "变暗": 8,
            "变亮": 9,
            "差值": 10,
            "排除": 11,
            "色相": 12,
            "饱和度": 13,
            "颜色": 14,
            "明度": 15
        }

        # 获取对应的数字值
        mode_value = mode_map.get(mode, 0)  # 默认为正常模式

        # 更新混合模式
        self.current_layer.blend_mode = mode_value

        # 使渲染缓存失效，确保预览窗口显示最新的混合效果
        self.document._invalidate_render_cache()

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改混合模式")

    def handle_path_input(self):
        """处理用户输入的路径"""
        if not self.current_layer:
            return

        path = self.source_path_edit.text()
        if not path or path.strip() == "":
            return

        safe_print(f"处理路径输入: {path}")

        # 检查路径是否存在
        if not os.path.exists(path):
            QMessageBox.warning(self, "路径错误", f"无法访问路径:\n{path}\n请确认路径存在且有权限访问。")
            return

        # 保存当前状态
        self.document.save_state("更改图层图像源前")

        # 确定是文件夹还是文件
        is_folder = os.path.isdir(path)

        # 如果类型不匹配当前选择，更新单选按钮状态
        if is_folder != self.folder_radio.isChecked():
            if is_folder:
                self.folder_radio.setChecked(True)
            else:
                self.file_radio.setChecked(True)

        # 更新图层图像源
        self.current_layer.image_source = path
        self.current_layer.is_folder = is_folder

        if is_folder:
            # 文件夹处理
            self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
            self.current_image_label.setText("当前图像: 无")
            # 启用随机按钮
            self.random_btn.setEnabled(True)
        else:
            # 文件处理
            self.current_layer.current_image_path = path  # 🔧 修复：使用公共属性
            if os.path.isfile(path):
                self.current_image_label.setText(f"当前图像: {os.path.basename(path)}")
            else:
                self.current_layer.current_image_path = None  # 🔧 修复：使用公共属性
                self.current_image_label.setText("当前图像: 无")
            # 禁用随机按钮
            self.random_btn.setEnabled(False)

        # 清除缓存图像
        self.current_layer.cached_image = None

        # 清除快速渲染器缓存（关键修复）
        self.document._invalidate_render_cache()

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改图层图像源")

    def open_binding_manager(self):
        """打开绑定管理器"""
        if not self.document:
            return

        # 确保文档有绑定管理器（兼容性检查）
        if not hasattr(self.document, 'binding_manager'):
            try:
                from app.models.binding_manager import LayerBindingManager
                self.document.binding_manager = LayerBindingManager()
                safe_print("为文档初始化绑定管理器")
            except Exception as e:
                from PySide6.QtWidgets import QMessageBox
                QMessageBox.critical(self, "错误", f"无法初始化绑定管理器: {str(e)}")
                return

        try:
            from app.ui.binding_manager_dialog import LayerBindingManagerDialog
            dialog = LayerBindingManagerDialog(self.document, self)
            result = dialog.exec()

            # 刷新当前图层的绑定状态显示
            if self.current_layer:
                self.update_bind_status()

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"打开绑定管理器时出错: {str(e)}")

    def open_size_match_manager(self):
        """打开图层大小匹配管理器"""
        if not self.document:
            return
        try:
            from app.ui.layer_size_match_dialog import LayerSizeMatchDialog
            dialog = LayerSizeMatchDialog(self.document, self)
            dialog.exec()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"打开图层大小匹配管理器时出错: {str(e)}")

    def update_bind_status(self):
        """更新绑定状态显示"""
        if not self.current_layer or not self.document:
            return

        try:
            binding_info = self.document.binding_manager.get_layer_binding_info(self.current_layer)
            if binding_info:
                group_id, group_name = binding_info
                self.bind_status_label.setText(f"已绑定到: {group_name}")
                self.bind_status_label.setStyleSheet("color: #2F9CF4; font-weight: bold; font-size: 9pt;")
            else:
                self.bind_status_label.setText("未绑定")
                self.bind_status_label.setStyleSheet("color: #606064; font-size: 9pt;")
        except Exception as e:
            safe_print(f"更新绑定状态时出错: {e}")
            self.bind_status_label.setText("未绑定")
            self.bind_status_label.setStyleSheet("color: #606064; font-size: 9pt;")

    def update_layer_rotation(self, rotation):
        """更新图层旋转角度"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新图层旋转角度: {rotation}°")

        # 更新图层属性
        self.current_layer.rotation = rotation

        # 高频旋转输入采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["rotation"], reason="rotation")
        self._save_state_deferred("旋转图层")

    def update_layer_flip_horizontal(self, flip):
        """更新图层水平翻转"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新图层水平翻转: {flip}")

        # 保存状态
        self.document.save_state("水平翻转图层前")

        # 更新图层属性
        self.current_layer.flip_horizontal = flip

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("水平翻转图层")

    def update_layer_flip_vertical(self, flip):
        """更新图层垂直翻转"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新图层垂直翻转: {flip}")

        # 保存状态
        self.document.save_state("垂直翻转图层前")

        # 更新图层属性
        self.current_layer.flip_vertical = flip

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("垂直翻转图层")

    def reset_layer_transforms(self):
        """重置图层所有变换"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print("重置图层所有变换")

        # 保存状态
        self.document.save_state("重置变换前")

        # 重置图层变换
        self.current_layer.reset_transformations()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("重置变换")

    # 随机变换相关方法
    def update_random_position_enabled(self, enabled):
        """更新随机位置抖动启用状态"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机位置抖动启用状态: {enabled}")

        # 保存状态
        self.document.save_state("更改随机位置抖动设置前")

        # 更新图层属性
        self.current_layer.random_position_enabled = enabled

        # 如果启用了随机位置但还没有生成随机参数，自动生成
        if enabled:
            if hasattr(self.current_layer, 'generate_random_transform_params'):
                self.current_layer.generate_random_transform_params()
                safe_print("自动生成随机变换参数")

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("更改随机位置抖动设置")

    def update_random_position_range(self, range_value):
        """更新随机位置抖动范围"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机位置抖动范围: {range_value}")

        # 更新图层属性
        self.current_layer.random_position_range = range_value

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 高频范围调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["random_position_range"], reason="random_position_range")
        self._save_state_deferred("更改随机位置抖动范围")

    def update_random_scale_enabled(self, enabled):
        """更新随机缩放启用状态"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机缩放启用状态: {enabled}")

        # 保存状态
        self.document.save_state("更改随机缩放设置前")

        # 更新图层属性
        self.current_layer.random_scale_enabled = enabled

        # 如果启用了随机缩放但还没有生成随机参数，自动生成
        if enabled:
            if hasattr(self.current_layer, 'generate_random_transform_params'):
                self.current_layer.generate_random_transform_params()
                safe_print("自动生成随机变换参数")

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("更改随机缩放设置")

    def update_random_scale_min(self, min_value):
        """更新最小随机缩放比例"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新最小随机缩放比例: {min_value}")

        # 更新图层属性
        self.current_layer.random_scale_min = min_value

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 高频范围调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["random_scale_min"], reason="random_scale_min")
        self._save_state_deferred("更改最小随机缩放比例")

    def update_random_scale_max(self, max_value):
        """更新最大随机缩放比例"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新最大随机缩放比例: {max_value}")

        # 更新图层属性
        self.current_layer.random_scale_max = max_value

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 高频范围调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["random_scale_max"], reason="random_scale_max")
        self._save_state_deferred("更改最大随机缩放比例")

    def update_random_rotation_enabled(self, enabled):
        """更新随机旋转启用状态"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机旋转启用状态: {enabled}")

        # 保存状态
        self.document.save_state("更改随机旋转设置前")

        # 更新图层属性
        self.current_layer.random_rotation_enabled = enabled

        # 如果启用了随机旋转但还没有生成随机参数，自动生成
        if enabled:
            if hasattr(self.current_layer, 'generate_random_transform_params'):
                self.current_layer.generate_random_transform_params()
                safe_print("自动生成随机变换参数")

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("更改随机旋转设置")

    def update_random_rotation_range(self, range_value):
        """更新随机旋转角度范围"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新随机旋转角度范围: {range_value}")

        # 更新图层属性
        self.current_layer.random_rotation_range = range_value

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 高频范围调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["random_rotation_range"], reason="random_rotation_range")
        self._save_state_deferred("更改随机旋转角度范围")

    def generate_random_params(self):
        """为当前图层生成新的随机变换参数"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"为图层 '{self.current_layer.name}' 生成新的随机变换参数")

        # 保存状态
        self.document.save_state("生成随机变换参数前")

        # 生成随机参数
        if hasattr(self.current_layer, 'generate_random_transform_params'):
            self.current_layer.generate_random_transform_params()

        # 使渲染缓存失效，确保预览窗口显示最新的随机变换
        self.document._invalidate_render_cache()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("生成随机变换参数")

    def reset_random_params(self):
        """重置当前图层的随机变换参数"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"重置图层 '{self.current_layer.name}' 的随机变换参数")

        # 保存状态
        self.document.save_state("重置随机变换参数前")

        # 重置随机参数
        if hasattr(self.current_layer, 'reset_random_transforms'):
            self.current_layer.reset_random_transforms()

        # 通知文档变更
        self.document.document_changed.emit()

        # 保存状态
        self.document.save_state("重置随机变换参数")

    def on_shaped_layer_changed(self):
        """异形图层属性改变处理"""
        if self.current_layer and hasattr(self.current_layer, 'cached_image'):
            self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()

    def on_shaped_layer_param_changed(self):
        """异形图层参数变更处理 - 同步基本属性面板"""
        if self.current_layer and self.document:
            # 同步基本属性面板中的形状参数显示
            self.sync_ui_with_layer()
            # 触发文档变更
            self.document.document_changed.emit()

    def _sync_shape_segment_buttons(self, shape_type_text):
        """同步形状分段按钮状态，保留隐藏下拉框兼容旧逻辑。"""
        if not hasattr(self, "shape_type_buttons"):
            return
        text_map = {
            "矩形": "矩形",
            "直角梯形": "梯形",
            "圆形": "圆形",
            "正五边形": "五边",
            "正六边形": "六边",
        }
        visible_text = text_map.get(shape_type_text, "矩形")
        for button in self.shape_type_buttons:
            button.blockSignals(True)
            try:
                button.setChecked(button.text() == visible_text)
            finally:
                button.blockSignals(False)

    def _current_fill_mode(self):
        if getattr(self, "fill_gradient_enabled_checkbox", None) and self.fill_gradient_enabled_checkbox.isChecked():
            return "gradient"
        if getattr(self, "fill_solid_enabled_checkbox", None) and self.fill_solid_enabled_checkbox.isChecked():
            return "solid"
        return "none"

    def _set_fill_mode(self, mode, update_layer=True):
        """切换填充模式，并保持旧复选框与新分段按钮同步。"""
        if mode not in {"none", "solid", "gradient"}:
            mode = "none"

        solid_enabled = mode == "solid"
        gradient_enabled = mode == "gradient"

        for button in getattr(self, "fill_mode_buttons", []):
            button.blockSignals(True)
            try:
                button.setChecked(button.property("fillMode") == mode)
            finally:
                button.blockSignals(False)

        self._block_all_signals(True)
        try:
            if hasattr(self, "fill_solid_enabled_checkbox"):
                self.fill_solid_enabled_checkbox.setChecked(solid_enabled)
            if hasattr(self, "fill_gradient_enabled_checkbox"):
                self.fill_gradient_enabled_checkbox.setChecked(gradient_enabled)
        finally:
            self._block_all_signals(False)

        if update_layer and self.current_layer and not self.current_layer.locked:
            self.current_layer.color_overlay_enabled = solid_enabled
            self.current_layer.gradient_overlay_enabled = gradient_enabled
            self._emit_document_change(throttled=True, fields=["fill_mode"], reason="fill_mode")
            self._save_state_deferred("切换填充模式")

        self._sync_appearance_visibility()

    def _sync_appearance_visibility(self):
        """根据填充/描边开关收起无关控件。"""
        mode = self._current_fill_mode()
        for button in getattr(self, "fill_mode_buttons", []):
            button.blockSignals(True)
            try:
                button.setChecked(button.property("fillMode") == mode)
            finally:
                button.blockSignals(False)

        if hasattr(self, "fill_solid_controls_widget"):
            self.fill_solid_controls_widget.setVisible(mode == "solid")
        if hasattr(self, "fill_gradient_controls_widget"):
            self.fill_gradient_controls_widget.setVisible(mode == "gradient")

        stroke_enabled = bool(
            hasattr(self, "stroke_enabled_checkbox") and self.stroke_enabled_checkbox.isChecked()
        )
        if hasattr(self, "stroke_controls_widget"):
            self.stroke_controls_widget.setVisible(stroke_enabled)
        if hasattr(self, "stroke_advanced_group"):
            self.stroke_advanced_group.setVisible(stroke_enabled)

    def update_shape_type(self, shape_type_text):
        """更新形状类型"""
        if not self.current_layer or self.current_layer.locked:
            if hasattr(self, "shape_type_combo"):
                self.shape_type_combo.blockSignals(True)
                try:
                    self.shape_type_combo.setCurrentText(shape_type_text)
                finally:
                    self.shape_type_combo.blockSignals(False)
            self._sync_shape_segment_buttons(shape_type_text)
            return

        safe_print(f"更新形状类型: {shape_type_text}")

        # 导入ShapeType枚举
        from app.models.layer_properties import ShapeType

        # 保存当前状态
        self.document.save_state("更改形状类型前")

        # 转换形状类型文本为枚举值
        shape_type_map = {
            "矩形": ShapeType.RECTANGLE,
            "直角梯形": ShapeType.RIGHT_TRAPEZOID,
            "圆形": ShapeType.CIRCLE,
            "正五边形": ShapeType.PENTAGON,
            "正六边形": ShapeType.HEXAGON
        }

        shape_type_value = shape_type_map.get(shape_type_text, ShapeType.RECTANGLE)

        # 更新图层形状类型
        self.current_layer.shape_type = shape_type_value
        if hasattr(self, "shape_type_combo"):
            self.shape_type_combo.blockSignals(True)
            try:
                self.shape_type_combo.setCurrentText(shape_type_text)
            finally:
                self.shape_type_combo.blockSignals(False)
        self._sync_shape_segment_buttons(shape_type_text)

        # 更新形状参数控件的可见性
        print(f"形状类型变更: {shape_type_value.value}")
        self.update_shape_params_visibility(shape_type_value.value)

        # 更新形状预览
        try:
            mapping = {
                "矩形": PreviewShapeType.RECTANGLE,
                "直角梯形": PreviewShapeType.RIGHT_TRAPEZOID,
                "圆形": PreviewShapeType.CIRCLE,
                "正五边形": PreviewShapeType.PENTAGON,
                "正六边形": PreviewShapeType.HEXAGON,
            }
            self.shape_preview.set_shape_type(mapping.get(shape_type_text, PreviewShapeType.RECTANGLE))
            # 多边形边数设置
            sides = 5 if shape_type_text == "正五边形" else (6 if shape_type_text == "正六边形" else 5)
            self.shape_preview.set_polygon_params(self.polygon_rotation_spin.value(), sides)
            self.shape_preview.update()
        except Exception:
            pass

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("更改形状类型")

    def update_trapezoid_params(self):
        """更新梯形参数"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新梯形参数")

        # 更新梯形参数
        self.current_layer.trapezoid_top_width = self.trapezoid_top_spin.value()
        self.current_layer.trapezoid_bottom_width = self.trapezoid_bottom_spin.value()

        # 转换斜边方向
        side_text = self.trapezoid_side_combo.currentText()
        side_value = "left" if side_text == "左侧" else "right"
        self.current_layer.trapezoid_slope_side = side_value

        # 同步形状预览
        try:
            self.shape_preview.set_trapezoid_params(
                self.trapezoid_top_spin.value(),
                self.trapezoid_bottom_spin.value(),
                "left" if self.trapezoid_side_combo.currentText() == "左侧" else "right"
            )
            self.shape_preview.update()
        except Exception:
            pass

        # 高频参数调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["trapezoid_params"], reason="trapezoid_params")
        self._save_state_deferred("更改梯形参数")

    def update_polygon_params(self):
        """更新多边形参数"""
        if not self.current_layer or self.current_layer.locked:
            return

        safe_print(f"更新多边形参数")

        # 更新多边形参数
        self.current_layer.polygon_rotation = self.polygon_rotation_spin.value()
        self.current_layer.polygon_corner_radius = self.polygon_radius_spin.value()

        # 同步形状预览
        try:
            sides = 5 if self.shape_type_combo.currentText() == "正五边形" else (6 if self.shape_type_combo.currentText() == "正六边形" else 5)
            self.shape_preview.set_polygon_params(self.polygon_rotation_spin.value(), sides)
            self.shape_preview.update()
        except Exception:
            pass

        # 高频参数调整采用节流刷新与延迟历史保存
        self._emit_document_change(throttled=True, fields=["polygon_params"], reason="polygon_params")
        self._save_state_deferred("更改多边形参数")

    def update_vector_corner_radius_all(self, value):
        """统一设置四角矢量圆角"""
        if not self.current_layer or self.current_layer.locked:
            return
        radius = int(value)
        self.current_layer.vector_corner_radius_tl = radius
        self.current_layer.vector_corner_radius_tr = radius
        self.current_layer.vector_corner_radius_br = radius
        self.current_layer.vector_corner_radius_bl = radius
        self.current_layer.corner_radius = radius
        self._block_all_signals(True)
        try:
            self.vector_corner_tl_spin.setValue(radius)
            self.vector_corner_tr_spin.setValue(radius)
            self.vector_corner_br_spin.setValue(radius)
            self.vector_corner_bl_spin.setValue(radius)
        finally:
            self._block_all_signals(False)
        self._emit_document_change(throttled=True, fields=["vector_corner_radius"], reason="vector_corner_radius")
        self._save_state_deferred("调整矢量圆角")

    def convert_rect_to_path_nodes(self):
        """将当前矩形转换为可编辑路径节点"""
        if not self.current_layer or self.current_layer.locked:
            return
        if hasattr(self.current_layer, 'convert_rect_to_vector_path'):
            self.current_layer.convert_rect_to_vector_path()
            self._emit_document_change(throttled=False, fields=["vector_path"], reason="vector_path")
            self._save_state_deferred("矩形转路径")

    def update_vector_corner_radii_detail(self):
        """分别设置四角矢量圆角"""
        if not self.current_layer or self.current_layer.locked:
            return
        tl = int(self.vector_corner_tl_spin.value())
        tr = int(self.vector_corner_tr_spin.value())
        br = int(self.vector_corner_br_spin.value())
        bl = int(self.vector_corner_bl_spin.value())
        self.current_layer.vector_corner_radius_tl = tl
        self.current_layer.vector_corner_radius_tr = tr
        self.current_layer.vector_corner_radius_br = br
        self.current_layer.vector_corner_radius_bl = bl
        self.current_layer.corner_radius = max(tl, tr, br, bl)
        self._block_all_signals(True)
        try:
            self.vector_corner_radius_spin.setValue(max(tl, tr, br, bl))
        finally:
            self._block_all_signals(False)
        self._emit_document_change(throttled=True, fields=["vector_corner_radius_detail"], reason="vector_corner_radius_detail")
        self._save_state_deferred("调整四角圆角")

    def update_stroke_join(self, text):
        if not self.current_layer or self.current_layer.locked:
            return
        join_map = {"斜接": "miter", "圆角": "round", "斜切": "bevel"}
        self.current_layer.stroke_join = join_map.get(text, "miter")
        self._emit_document_change(throttled=True, fields=["stroke_join"], reason="stroke_join")
        self._save_state_deferred("调整描边连接")

    def update_stroke_cap(self, text):
        if not self.current_layer or self.current_layer.locked:
            return
        cap_map = {"平头": "butt", "圆头": "round", "方头": "square"}
        self.current_layer.stroke_cap = cap_map.get(text, "butt")
        self._emit_document_change(throttled=True, fields=["stroke_cap"], reason="stroke_cap")
        self._save_state_deferred("调整描边端点")

    def update_stroke_dash(self):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.stroke_dash_length = int(self.stroke_dash_length_spin.value())
        self.current_layer.stroke_dash_gap = int(self.stroke_dash_gap_spin.value())
        self._emit_document_change(throttled=True, fields=["stroke_dash"], reason="stroke_dash")
        self._save_state_deferred("调整描边虚线")

    def update_stroke_enabled(self, enabled):
        if not self.current_layer:
            return
        if self._is_multi_layer_edit():
            self._apply_to_selected_layers(
                {"stroke_enabled": bool(enabled)},
                "批量切换描边",
                fields=["stroke_enabled"],
                allow_locked=False,
                clear_cache=True,
            )
            self._sync_appearance_visibility()
            return
        if self.current_layer.locked:
            return
        self.current_layer.stroke_enabled = bool(enabled)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=True, fields=["stroke_enabled"], reason="stroke_enabled")
        self._save_state_deferred("切换描边")

    def update_stroke_width(self, value):
        if not self.current_layer:
            return
        if self._is_multi_layer_edit():
            self._apply_to_selected_layers(
                {"stroke_width": int(value)},
                "批量调整描边粗细",
                fields=["stroke_width"],
                allow_locked=False,
                clear_cache=True,
            )
            return
        if self.current_layer.locked:
            return
        self.current_layer.stroke_width = int(value)
        self._emit_document_change(throttled=True, fields=["stroke_width"], reason="stroke_width")
        self._save_state_deferred("调整描边粗细")

    def update_stroke_type(self, index):
        if not self.current_layer:
            return
        if self._is_multi_layer_edit():
            self._apply_to_selected_layers(
                {"stroke_type": int(index)},
                "批量调整描边对齐",
                fields=["stroke_type"],
                allow_locked=False,
                clear_cache=True,
            )
            return
        if self.current_layer.locked:
            return
        self.current_layer.stroke_type = int(index)
        self._emit_document_change(throttled=True, fields=["stroke_type"], reason="stroke_type")
        self._save_state_deferred("调整描边对齐")

    def pick_stroke_color(self):
        if not self.current_layer or self.current_layer.locked:
            return
        current = tuple(getattr(self.current_layer, 'stroke_color', (0, 0, 0, 255)))
        color = get_color_a2(QColor(current[0], current[1], current[2], current[3]), self, "选择描边颜色")
        if not color.isValid():
            return
        rgba = (color.red(), color.green(), color.blue(), color.alpha())
        self.current_layer.stroke_color = rgba
        self.current_layer.stroke_enabled = True
        self._set_button_color(self.stroke_color_btn, rgba)
        self._block_all_signals(True)
        try:
            self.stroke_enabled_checkbox.setChecked(True)
        finally:
            self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=False, fields=["stroke_color"], reason="stroke_color")
        self._save_state_deferred("修改描边颜色")

    def update_fill_solid_enabled(self, enabled):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.color_overlay_enabled = bool(enabled)
        if enabled:
            self.current_layer.gradient_overlay_enabled = False
            self._block_all_signals(True)
            try:
                self.fill_gradient_enabled_checkbox.setChecked(False)
            finally:
                self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=True, fields=["fill_solid_enabled"], reason="fill_solid_enabled")
        self._save_state_deferred("切换纯色填充")

    def pick_fill_solid_color(self):
        if not self.current_layer or self.current_layer.locked:
            return
        current = tuple(getattr(self.current_layer, 'color_overlay_color', (255, 0, 0, 255)))
        color = get_color_a2(QColor(current[0], current[1], current[2], current[3]), self, "选择填充颜色")
        if not color.isValid():
            return
        rgba = (color.red(), color.green(), color.blue(), color.alpha())
        self.current_layer.color_overlay_color = rgba
        self.current_layer.color_overlay_enabled = True
        self.current_layer.gradient_overlay_enabled = False
        self._set_button_color(self.fill_solid_color_btn, rgba)
        self._block_all_signals(True)
        try:
            self.fill_solid_enabled_checkbox.setChecked(True)
            self.fill_gradient_enabled_checkbox.setChecked(False)
        finally:
            self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=False, fields=["fill_solid_color"], reason="fill_solid_color")
        self._save_state_deferred("修改填充颜色")

    def update_fill_gradient_enabled(self, enabled):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.gradient_overlay_enabled = bool(enabled)
        if enabled:
            self.current_layer.color_overlay_enabled = False
            self._block_all_signals(True)
            try:
                self.fill_solid_enabled_checkbox.setChecked(False)
            finally:
                self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=True, fields=["fill_gradient_enabled"], reason="fill_gradient_enabled")
        self._save_state_deferred("切换渐变填充")

    def pick_gradient_start_color(self):
        self._pick_gradient_color(0, self.fill_gradient_start_btn, "选择渐变起点色")

    def pick_gradient_end_color(self):
        self._pick_gradient_color(1, self.fill_gradient_end_btn, "选择渐变终点色")

    def _pick_gradient_color(self, idx, btn, title):
        if not self.current_layer or self.current_layer.locked:
            return
        colors = list(getattr(self.current_layer, 'gradient_overlay_colors', [(0, 0, 0, 255), (255, 255, 255, 255)]))
        if len(colors) < 2:
            colors = [(0, 0, 0, 255), (255, 255, 255, 255)]
        current = tuple(colors[idx])
        color = get_color_a2(QColor(current[0], current[1], current[2], current[3]), self, title)
        if not color.isValid():
            return
        colors[idx] = (color.red(), color.green(), color.blue(), color.alpha())
        self.current_layer.gradient_overlay_colors = colors
        self.current_layer.gradient_overlay_enabled = True
        self.current_layer.color_overlay_enabled = False
        self._set_button_color(btn, colors[idx])
        self._block_all_signals(True)
        try:
            self.fill_gradient_enabled_checkbox.setChecked(True)
            self.fill_solid_enabled_checkbox.setChecked(False)
        finally:
            self._block_all_signals(False)
        self._sync_appearance_visibility()
        self._emit_document_change(throttled=False, fields=["fill_gradient_colors"], reason="fill_gradient_colors")
        self._save_state_deferred("修改渐变颜色")

    def update_fill_gradient_angle(self, value):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.gradient_overlay_angle = float(value)
        self._emit_document_change(throttled=True, fields=["fill_gradient_angle"], reason="fill_gradient_angle")
        self._save_state_deferred("调整渐变角度")

    def update_fill_gradient_opacity(self, value):
        if not self.current_layer or self.current_layer.locked:
            return
        self.current_layer.gradient_overlay_opacity = float(value) / 100.0
        self._emit_document_change(throttled=True, fields=["fill_gradient_opacity"], reason="fill_gradient_opacity")
        self._save_state_deferred("调整渐变不透明度")

    def _set_button_color(self, btn, rgba):
        if not btn:
            return
        r, g, b, a = [int(x) for x in rgba]
        text_color = "#111214" if (r * 0.299 + g * 0.587 + b * 0.114) > 170 else "#F4F4F5"
        label = btn.property("swatchLabel")
        if label is None:
            label = btn.text() or ""
        btn.setStyleSheet(
            f"background-color: rgba({r}, {g}, {b}, {a});"
            f"color: {text_color};"
            "border: 1px solid #34363A; border-radius: 5px;"
            "min-height: 27px; padding: 3px 8px; font-weight: 600;"
        )
        btn.setText(str(label))

    def update_shape_params_visibility(self, shape_type):
        """根据形状类型更新参数控件的可见性"""
        print(f"更新形状参数可见性: shape_type={shape_type}")
        print(f"布局行数: {self.shape_params_layout.rowCount()}")

        # 隐藏所有形状参数控件
        for i in range(self.shape_params_layout.rowCount()):
            item = self.shape_params_layout.itemAt(i, QFormLayout.LabelRole)
            if item:
                print(f"隐藏标签行 {i}: {item.widget()}")
                item.widget().hide()
            item = self.shape_params_layout.itemAt(i, QFormLayout.FieldRole)
            if item:
                print(f"隐藏字段行 {i}: {item.widget()}")
                item.widget().hide()

        # 根据形状类型显示相应的参数控件
        print(f"处理形状类型: {shape_type}")
        if shape_type == "right_trapezoid":
            # 显示梯形参数
            print("显示梯形参数")
            self._show_shape_param_rows([0, 1, 2])  # 上底宽度, 下底宽度, 斜边方向
        elif shape_type in ["pentagon", "hexagon"]:
            # 显示多边形参数
            print("显示多边形参数")
            self._show_shape_param_rows([3, 4])  # 旋转角度, 圆角半径
        elif shape_type == "circle":
            # 圆形不需要额外参数
            print("圆形无额外参数")
            pass
        elif shape_type == "rectangle":
            # 矩形不需要额外参数
            print("矩形无额外参数")
            pass
        else:
            # 未识别的形状类型，不显示额外参数
            print(f"未识别的形状类型: {shape_type}")
            pass

    def _show_shape_param_rows(self, row_indices):
        """显示指定的形状参数行"""
        print(f"显示形状参数行: {row_indices}")
        for row_index in row_indices:
            print(f"处理行 {row_index}")
            if row_index < self.shape_params_layout.rowCount():
                label_item = self.shape_params_layout.itemAt(row_index, QFormLayout.LabelRole)
                field_item = self.shape_params_layout.itemAt(row_index, QFormLayout.FieldRole)
                print(f"标签项: {label_item}, 字段项: {field_item}")
                if label_item and label_item.widget():
                    print(f"显示标签行 {row_index}")
                    label_item.widget().show()
                if field_item and field_item.widget():
                    print(f"显示字段行 {row_index}")
                    field_item.widget().show()
            else:
                print(f"行 {row_index} 超出范围，总行数: {self.shape_params_layout.rowCount()}")


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")
    def update_fill_enabled(self, enabled):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_enabled = enabled
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充启用")

    def update_fill_mode(self, index):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        text = self.fill_mode_combo.itemText(index)
        mode_map = {"常规网格": "grid", "错位排列": "staggered", "边框排列": "border"}
        mode = mode_map.get(text, "grid")
        self.current_layer.clone_fill_mode = mode
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充排列")

    def update_fill_spacing(self, value):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_spacing = int(value)
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充间距")

    def update_fill_angle(self, value):
        if not self.current_layer:
            return
        self._ensure_clone_properties()
        self.current_layer.clone_fill_angle = float(value)
        self.current_layer.cached_image = None
        if self.document:
            self.document.document_changed.emit()
            self.document.save_state("修改元素填充角度")
            # 同步元素填充
            self._ensure_clone_properties()
            self.fill_enabled_checkbox.setChecked(bool(getattr(self.current_layer, 'clone_fill_enabled', False)))
            mode = getattr(self.current_layer, 'clone_fill_mode', 'grid')
            # 正确设置下拉框索引：grid=0, staggered=1, border=2
            index_map = {'grid': 0, 'staggered': 1, 'border': 2}
            self.fill_mode_combo.setCurrentIndex(index_map.get(mode, 0))
            self.fill_spacing_spin.setValue(int(getattr(self.current_layer, 'clone_fill_spacing', 0)))
            self.fill_margin_spin.setValue(int(getattr(self.current_layer, 'clone_fill_margin', 0)))
            self.fill_angle_spin.setValue(float(getattr(self.current_layer, 'clone_fill_angle', 0.0)))
