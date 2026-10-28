import logging

logger = logging.getLogger(__name__)
from app.ui.design_spec import Space as _Space, Width as _Width, IconSize as _IconSize
from app.utils.print_utils import safe_print
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QDoubleSpinBox, QLineEdit, QFormLayout,
                               QFileDialog, QGroupBox, QCheckBox, QComboBox,
                               QSlider, QMessageBox, QRadioButton, QButtonGroup,
                               QScrollArea, QFrame, QSizePolicy,
                               QMenu, QMainWindow, QDockWidget, QApplication, QTextEdit,
                               QProgressBar, QTabWidget)
from PySide6.QtCore import (Qt, Slot, Signal, QTimer, QSettings, QObject,
                            QRunnable, QThreadPool, QSize)
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
from app.ui.design_tokens import Tokens
from app.ui.property_widgets import PropertySection, PropertySwitch, switch_row
from app.utils.layer_tree import is_layer_group
from app.services.ai_asset_service import (
    AIAssetRequest,
    AIAssetResult,
    AIAssetService,
    localize_ai_error,
)
from app.services.ai_provider_config import AIProviderStore


class LayerPropertiesLayout(object):
    """Mixin for layer_properties_layout (split from LayerPropertiesPanel)."""

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
                logger.warning("静默异常已忽略: except in ui/layer_properties_layout.py", exc_info=True)
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
                logger.warning("静默异常已忽略: except in ui/layer_properties_layout.py", exc_info=True)
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
        main_layout.setSpacing(_Space.NONE)

        self.property_tabs = QTabWidget()
        self.property_tabs.setObjectName("layerPropertyTabs")
        self.property_tabs.setDocumentMode(True)
        self.property_tabs.tabBar().setExpanding(True)
        self.property_tabs.tabBar().setUsesScrollButtons(False)
        self.property_tabs.setMinimumWidth(Tokens.SIDEBAR_MIN_WIDTH)
        self.property_tabs.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
        self.property_tabs.setStyleSheet(self._layer_panel_stylesheet())

        def create_tab_page(label, object_name):
            scroll_area = QScrollArea()
            scroll_area.setObjectName(object_name)
            scroll_area.setMinimumWidth(0)
            scroll_area.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Expanding)
            scroll_area.setWidgetResizable(True)
            scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
            scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
            scroll_area.setProperty("role", "scroll-area")

            content = QWidget()
            content.setObjectName("layerPropertiesContent")
            content.setMinimumWidth(0)
            content.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
            content.setStyleSheet(self._layer_panel_stylesheet())
            content_layout = QVBoxLayout(content)
            content_layout.setContentsMargins(
                Tokens.SIDEBAR_PADDING,
                0,
                Tokens.SIDEBAR_PADDING,
                Tokens.SIDEBAR_PADDING,
            )
            content_layout.setSpacing(Tokens.SIDEBAR_SECTION_GAP)
            scroll_area.setWidget(content)
            self.property_tabs.addTab(scroll_area, label)
            return scroll_area, content, content_layout

        self.basic_scroll_area, self.basic_tab_content, self.scroll_layout = create_tab_page(
            "基本参数", "basicParametersScroll"
        )
        self.more_scroll_area, self.more_tab_content, self.more_scroll_layout = create_tab_page(
            "更多参数", "moreParametersScroll"
        )
        main_layout.addWidget(self.property_tabs)

        # 1. 基本属性组 (默认展开)
        self.basic_group = PropertySection("基本属性")
        basic_form = self._form()

        # 图层名称
        self.name_edit = QLineEdit()
        self.name_edit.setPlaceholderText("图层名称")
        self.name_edit.textChanged.connect(self.update_layer_name)
        basic_form.addRow(self._label("名称:"), self.name_edit)

        # 图层位置 X 和 Y 在同一行
        # 同"尺寸"行的处理：用 prefix 代替独立标签，把宽度让给输入框
        pos_layout = QHBoxLayout()
        pos_layout.setSpacing(_Space.XS)
        self.x_spin = QSpinBox()
        self.x_spin.setRange(-10000, 10000)
        self.x_spin.setPrefix("X ")
        self.x_spin.valueChanged.connect(self.update_layer_position)
        pos_layout.addWidget(self.x_spin)
        pos_layout.addSpacing(4)

        self.y_spin = QSpinBox()
        self.y_spin.setRange(-10000, 10000)
        self.y_spin.setPrefix("Y ")
        self.y_spin.valueChanged.connect(self.update_layer_position)
        pos_layout.addWidget(self.y_spin)
        basic_form.addRow(self._label("位置:"), pos_layout)

        # 图层宽度和高度在同一行，添加锁定比例按钮
        size_layout = QHBoxLayout()
        size_layout.setSpacing(_Space.XS)
        self.width_spin = QSpinBox()
        self.width_spin.setRange(1, 10000)
        self.width_spin.valueChanged.connect(self.update_layer_size)
        # 用 prefix 表达 W/H，不再各占一个 "宽:"/"高:" 标签。
        #
        # 为什么（2026-10-28 实测）：这一行原来有 5 个元素
        #   尺寸: [宽:] [spin] [锁] [高:] [spin]
        # 面板宽 360 时，QSpinBox 的 sizeHint 是 109，实际只分到 57 ——
        # 被挤掉一半，数字看不全，整行还会折成两行。
        # 去掉两个 58px 的标签、改用 prefix 后，两个 spin 各能拿到 ~110px。
        self.width_spin.setPrefix("W ")
        size_layout.addWidget(self.width_spin)

        # 锁定比例按钮 - 嵌在尺寸输入行里的紧凑图标按钮
        self.aspect_lock_btn = QPushButton()
        self.aspect_lock_btn.setObjectName("aspectLockButton")
        # 尺寸用 setFixedSize 显式锁定 SM 档（24），**不要**只依赖 uiSize 属性。
        #
        # 踩过的坑（2026-10-28 实测三次）：
        # 1) 写死 26 → 不在 24/28/36 三档内，且压过全局规则，渲染 26；
        # 2) 只写 uiSize="iconSm" → 这个按钮 setCheckable(True) 后，
        #    QPushButton:checked 的 sizeHint 参与计算，实测渲染 40×30；
        # 3) 再叠加 variant 属性 → QPushButton[variant] 规则把 height 拉到 36。
        # setFixedSize 是唯一能压住这三条的值，且数值仍取自 design_spec。
        self.aspect_lock_btn.setProperty("uiSize", "iconSm")
        self.aspect_lock_btn.setFixedSize(_IconSize.SM, _IconSize.SM)
        self.aspect_lock_btn.setIconSize(QSize(_IconSize.SM, _IconSize.SM))
        self.aspect_lock_btn.setCheckable(True)
        self.aspect_lock_btn.setProperty("role", "toggle")
        self.aspect_lock_btn.setChecked(False)
        self.aspect_lock_btn.setToolTip("锁定宽高比例")
        self.aspect_lock_btn.clicked.connect(self.toggle_aspect_ratio_lock)
        self.update_aspect_lock_icon()
        size_layout.addWidget(self.aspect_lock_btn)

        self.height_spin = QSpinBox()
        self.height_spin.setRange(1, 10000)
        self.height_spin.valueChanged.connect(self.update_layer_size)
        self.height_spin.setPrefix("H ")
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
        self.opacity_label.setProperty("role", "badge")
        self.opacity_label.setProperty("variant", "outline")
        self.opacity_label.setAlignment(Qt.AlignCenter)
        self.opacity_label.setMinimumWidth(48)
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
        self.shape_group = PropertySection("形状")
        shape_layout = QVBoxLayout()
        shape_layout.setSpacing(_Space.XS)

        # 形状类型：保留隐藏下拉框作为兼容层，用户入口改为分段按钮
        self.shape_type_combo = QComboBox()
        self.shape_type_combo.addItems(["矩形", "直角梯形", "圆形", "正五边形", "正六边形"])
        self.shape_type_combo.currentTextChanged.connect(self.update_shape_type)
        self.shape_type_combo.hide()

        shape_segment_layout = QHBoxLayout()
        shape_segment_layout.setSpacing(_Space.XS)
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
        shape_main_row.setSpacing(_Space.XS)

        # 形状参数控制
        self.shape_params_widget = QWidget()
        self.shape_params_layout = self._form(self.shape_params_widget)
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
        self.shape_preview.setFixedSize(_Width.SPIN, _Width.SPIN)
        self.shape_preview.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        preview_container = QFrame()
        preview_container.setObjectName("shapePreviewContainer")
        pc_layout = QVBoxLayout(preview_container)
        pc_layout.setContentsMargins(6, 6, 6, 6)
        pc_layout.setSpacing(_Space.XS)
        pc_layout.addWidget(self.shape_preview, alignment=Qt.AlignCenter)
        shape_main_row.addWidget(preview_container, 0, Qt.AlignTop)

        shape_layout.addLayout(shape_main_row)
        for row in range(self.shape_params_layout.rowCount()):
            for role in (QFormLayout.LabelRole, QFormLayout.FieldRole):
                item = self.shape_params_layout.itemAt(row, role)
                if item and item.widget():
                    item.widget().hide()

        corner_form = self._form()
        self.vector_corner_radius_spin = QSpinBox()
        self.vector_corner_radius_spin.setRange(0, 1000)
        self.vector_corner_radius_spin.valueChanged.connect(self.update_vector_corner_radius_all)
        corner_form.addRow(self._label("统一圆角:"), self.vector_corner_radius_spin)

        vector_corner_layout = QHBoxLayout()
        vector_corner_layout.setSpacing(_Space.XS)
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
        corner_form.addRow(self._blank_label(), self.convert_to_path_btn)
        shape_layout.addLayout(corner_form)

        self.shape_group.add_content_layout(shape_layout)
        self.scroll_layout.addWidget(self.shape_group)
        self._register_module_group("shape", "形状", self.shape_group)

        # 外观：填充模式与描边按开关渐进展开
        self.appearance_group = PropertySection("外观")
        appearance_layout = QVBoxLayout()
        appearance_layout.setSpacing(8)

        appearance_layout.addWidget(self._section_label("填充"))
        fill_mode_layout = QHBoxLayout()
        fill_mode_layout.setSpacing(_Space.XS)
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

        self.fill_solid_enabled_checkbox = PropertySwitch()
        self.fill_solid_enabled_checkbox.clicked.connect(self.update_fill_solid_enabled)
        self.fill_solid_enabled_checkbox.hide()

        self.fill_solid_controls_widget, fill_solid_controls_layout = self._make_control_group()
        fill_solid_form = self._form()
        self.fill_solid_color_btn = QPushButton("填充颜色")
        self.fill_solid_color_btn.setObjectName("colorSwatchButton")
        self.fill_solid_color_btn.setProperty("swatchLabel", "")
        self.fill_solid_color_btn.clicked.connect(self.pick_fill_solid_color)
        fill_solid_form.addRow(self._label("填充颜色:"), self.fill_solid_color_btn)
        fill_solid_controls_layout.addLayout(fill_solid_form)
        appearance_layout.addWidget(self.fill_solid_controls_widget)

        self.fill_gradient_enabled_checkbox = PropertySwitch()
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
        fill_gradient_form = self._form()
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

        # "启用描边" 是普通字段开关，与"混合模式:"同级，
        # 不该用 featureTitle（15px bold，比区块标题还大）
        stroke_toggle_row, self.stroke_enabled_checkbox = switch_row(
            "启用描边", role="fieldLabel")
        self.stroke_enabled_checkbox.clicked.connect(self.update_stroke_enabled)
        appearance_layout.addLayout(stroke_toggle_row)

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
        stroke_width_layout.addWidget(self._label("描边对齐:", inline=True))
        stroke_width_layout.addWidget(self.stroke_type_combo)
        stroke_controls_form = self._form()
        stroke_controls_form.addRow(self._label("描边粗细:"), stroke_width_layout)

        self.stroke_color_btn = QPushButton("描边颜色")
        self.stroke_color_btn.setObjectName("colorSwatchButton")
        self.stroke_color_btn.setProperty("swatchLabel", "")
        self.stroke_color_btn.clicked.connect(self.pick_stroke_color)
        stroke_controls_form.addRow(self._label("描边颜色:"), self.stroke_color_btn)
        stroke_controls_layout.addLayout(stroke_controls_form)
        appearance_layout.addWidget(self.stroke_controls_widget)

        self.stroke_advanced_group = CollapsibleGroupBox("高级线条", collapsed=True)
        stroke_advanced_form = self._form()

        self.stroke_join_combo = QComboBox()
        self.stroke_join_combo.addItems(["斜接", "圆角", "斜切"])
        self.stroke_join_combo.currentTextChanged.connect(self.update_stroke_join)
        stroke_line_layout = QHBoxLayout()
        stroke_line_layout.setSpacing(8)
        stroke_line_layout.addWidget(self.stroke_join_combo)

        self.stroke_cap_combo = QComboBox()
        self.stroke_cap_combo.addItems(["平头", "圆头", "方头"])
        self.stroke_cap_combo.currentTextChanged.connect(self.update_stroke_cap)
        stroke_line_layout.addWidget(self._label("描边端点:", inline=True))
        stroke_line_layout.addWidget(self.stroke_cap_combo)
        stroke_advanced_form.addRow(self._label("描边连接:"), stroke_line_layout)

        stroke_dash_layout = QHBoxLayout()
        self.stroke_dash_length_spin = QSpinBox()
        self.stroke_dash_length_spin.setRange(0, 1000)
        self.stroke_dash_length_spin.valueChanged.connect(self.update_stroke_dash)
        self.stroke_dash_length_spin.setToolTip("段长：为 0 时连续实线；大于 0 时沿路径绘制虚线")
        stroke_dash_layout.addWidget(self._label("段长:", inline=True))
        stroke_dash_layout.addWidget(self.stroke_dash_length_spin)
        self.stroke_dash_gap_spin = QSpinBox()
        self.stroke_dash_gap_spin.setRange(0, 1000)
        self.stroke_dash_gap_spin.valueChanged.connect(self.update_stroke_dash)
        self.stroke_dash_gap_spin.setToolTip("虚线间隔；连续实线时请设为 0")
        stroke_dash_layout.addWidget(self._label("间隔:", inline=True))
        stroke_dash_layout.addWidget(self.stroke_dash_gap_spin)
        stroke_advanced_form.addRow(self._label("虚线:"), stroke_dash_layout)
        self.stroke_advanced_group.add_content_layout(stroke_advanced_form)
        appearance_layout.addWidget(self.stroke_advanced_group)

        self.appearance_group.add_content_layout(appearance_layout)
        self.scroll_layout.addWidget(self.appearance_group)
        self._register_module_group("appearance", "外观", self.appearance_group)
        self._sync_appearance_visibility()

        # 2. 图像源设置组 (默认展开)
        #
        # ⚠ 2026-10-28 改：这里原来是裸 QVBoxLayout，四个子控件从分区最左边
        # （x=12）起排，而上面的「基本属性」字段列从 x=84 起 —— 同一个面板
        # 出现两条竖线，截图里一眼就"乱"。现在改走 self._form()，
        # 无条件落在同一条标签列栅格上（整行控件用 _blank_label() 占位）。
        self.source_group = PropertySection("图像源")
        source_form = self._form()

        # 图像源类型选择
        source_type_layout = QHBoxLayout()
        source_type_layout.setSpacing(_Space.MD)
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
        source_form.addRow(self._label("来源:"), source_type_layout)

        # 图像源路径
        source_path_layout = QHBoxLayout()
        source_path_layout.setSpacing(_Space.XS)
        self.source_path_edit = QLineEdit()
        self.source_path_edit.setPlaceholderText("输入或粘贴文件/文件夹路径")
        self.source_path_edit.setReadOnly(False)  # 允许输入
        self.source_path_edit.returnPressed.connect(self.handle_path_input)  # 添加回车处理
        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setProperty("variant", "outline")
        self.browse_btn.clicked.connect(self.browse_image)
        source_path_layout.addWidget(self.source_path_edit)
        source_path_layout.addWidget(self.browse_btn)
        source_form.addRow(self._label("路径:"), source_path_layout)

        # 随机按钮
        self.random_btn = QPushButton("随机选择")
        self.random_btn.setProperty("variant", "secondary")
        self.random_btn.clicked.connect(self.randomize_image)
        source_form.addRow(self._blank_label(), self.random_btn)

        # 当前图像预览：值只放文件名，「当前:」走统一的标签列，
        # 这样它和其他字段的竖线一致（原来整串文字从最左边起排）。
        self.current_image_label = QLabel("无")
        self.current_image_label.setProperty("role", "muted")
        self.current_image_label.setWordWrap(True)
        source_form.addRow(self._label("当前:"), self.current_image_label)

        self.source_group.add_content_layout(source_form)
        self.scroll_layout.addWidget(self.source_group)
        self._register_module_group("source", "图像源设置", self.source_group)

        self.ai_generation_group = PropertySection("AI生图")
        ai_layout = self._form()

        self.ai_prompt_edit = QTextEdit()
        self.ai_prompt_edit.setAcceptRichText(False)
        self.ai_prompt_edit.setFixedHeight(_Width.COMBO)
        self.ai_prompt_edit.setPlaceholderText("输入当前图层的生图提示词")
        self.ai_negative_prompt_edit = QTextEdit()
        self.ai_negative_prompt_edit.setAcceptRichText(False)
        self.ai_negative_prompt_edit.setFixedHeight(_Width.VALUE_LABEL)
        self.ai_negative_prompt_edit.setPlaceholderText("可选：输入不希望出现的内容")
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
        self.ai_generate_btn.setProperty("variant", "default")
        self.ai_generate_btn.clicked.connect(self.start_ai_generation_for_current_layer)
        self.ai_progress_bar = QProgressBar()
        self.ai_progress_bar.setProperty("role", "progress")
        self.ai_progress_bar.setRange(0, 100)
        self.ai_progress_bar.setValue(0)
        self.ai_progress_bar.setFormat("等待生成")
        self.ai_status_label = QLabel("使用工具栏的 AI接口设置 作为全局 API 参数")
        self.ai_status_label.setProperty("role", "muted")

        ai_layout.addRow(self._label("提示词:"), self.ai_prompt_edit)
        ai_layout.addRow(self._label("反向提示词:"), self.ai_negative_prompt_edit)
        ai_layout.addRow(self._label("数量:"), self.ai_count_spin)
        ai_layout.addRow(self._label("尺寸:"), self.ai_size_combo)
        ai_layout.addRow(self._label("处理:"), self.ai_mode_combo)
        ai_layout.addRow(self._blank_label(), self.ai_generate_btn)
        ai_layout.addRow(self._label("进度:"), self.ai_progress_bar)
        ai_layout.addRow(self._blank_label(), self.ai_status_label)

        self.ai_generation_group.add_content_layout(ai_layout)
        self.scroll_layout.addWidget(self.ai_generation_group)
        self._register_module_group("ai_generation", "AI生图", self.ai_generation_group)

        # 3. 高级设置组 (默认收起)
        self.advanced_group = PropertySection("高级设置")
        advanced_form = self._form()

        # 使用原始尺寸
        self.use_original_size_checkbox = PropertySwitch()
        self.use_original_size_checkbox.clicked.connect(self.update_use_original_size)
        # 开关行也走统一标签列（原来直接塞裸 QLabel，宽度 52、左对齐，
        # 与同组「适配模式:」的右对齐 72 列形成两条竖线）
        advanced_form.addRow(self._label("智能裁剪:"), self.use_original_size_checkbox)

        # 图像适配模式
        # 索引定义（与 Layer.FIT_* 保持一致）：
        #   0 = 智能缩放裁剪 (FIT_SMART_CROP)
        #   1 = 智能缩放不裁剪 (FIT_SMART_FIT)
        #   2 = 智能适配不缩放 (FIT_NO_SCALE) - 保持原图尺寸，避免拉伸变形
        self.fit_mode_combo = QComboBox()
        self.fit_mode_combo.addItem("智能缩放裁剪")
        self.fit_mode_combo.addItem("智能缩放不裁剪")
        self.fit_mode_combo.addItem("智能适配不缩放")
        self.fit_mode_combo.currentIndexChanged.connect(self.update_fit_mode)
        advanced_form.addRow(self._label("适配模式:"), self.fit_mode_combo)

        # 裁剪方向
        self.crop_direction_combo = QComboBox()
        self.crop_direction_combo.addItem("居中裁剪")
        self.crop_direction_combo.addItem("顶部裁剪")
        self.crop_direction_combo.addItem("底部裁剪")
        self.crop_direction_combo.addItem("左侧裁剪")
        self.crop_direction_combo.addItem("右侧裁剪")
        self.crop_direction_combo.currentIndexChanged.connect(self.update_crop_direction)
        advanced_form.addRow(self._label("裁剪方向:"), self.crop_direction_combo)

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
        advanced_form.addRow(self._label("混合模式:"), self.blend_mode_combo)

        self.advanced_group.add_content_layout(advanced_form)
        self.scroll_layout.addWidget(self.advanced_group)
        self._register_module_group("advanced", "高级设置", self.advanced_group)

        # 4. 图层分身组 (默认收起)
        self.clone_group = PropertySection("图层分身")
        clone_layout = self._form()

        # 启用分身
        self.clone_enabled_checkbox = QCheckBox("启用图层分身")
        self.clone_enabled_checkbox.setChecked(False)
        self.clone_enabled_checkbox.clicked.connect(self.update_clone_enabled)
        clone_layout.addRow(self._blank_label(), self.clone_enabled_checkbox)

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
        clone_layout.addRow(self._label("数量:"), clone_count_layout)

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
        clone_layout.addRow(self._label("间距:"), spacing_layout)

        # 分身自定义大小
        self.clone_custom_size_checkbox = QCheckBox("自定义分身大小")
        self.clone_custom_size_checkbox.setChecked(False)
        self.clone_custom_size_checkbox.clicked.connect(self.update_clone_custom_size_enabled)
        clone_layout.addRow(self._blank_label(), self.clone_custom_size_checkbox)

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
        clone_layout.addRow(self._label("分身尺寸:"), clone_size_layout)

        # 元素填充功能
        self.fill_enabled_checkbox = QCheckBox("启用元素填充")
        self.fill_enabled_checkbox.setChecked(False)
        self.fill_enabled_checkbox.clicked.connect(self.update_fill_enabled)
        clone_layout.addRow(self._blank_label(), self.fill_enabled_checkbox)

        self.fill_mode_combo = QComboBox()
        self.fill_mode_combo.addItems(["常规网格", "错位排列", "边框排列"])
        self.fill_mode_combo.currentIndexChanged.connect(self.update_fill_mode)
        clone_layout.addRow(self._label("排列:"), self.fill_mode_combo)

        self.fill_spacing_spin = QSpinBox()
        self.fill_spacing_spin.setRange(0, 10000)
        self.fill_spacing_spin.setValue(0)
        self.fill_spacing_spin.valueChanged.connect(self.update_fill_spacing)
        clone_layout.addRow(self._label("元素间距:"), self.fill_spacing_spin)

        self.fill_margin_spin = QSpinBox()
        self.fill_margin_spin.setRange(0, 1000)
        self.fill_margin_spin.setValue(0)
        self.fill_margin_spin.valueChanged.connect(self.update_fill_margin)
        clone_layout.addRow(self._label("画布边距:"), self.fill_margin_spin)

        self.fill_angle_spin = QDoubleSpinBox()
        self.fill_angle_spin.setRange(0.0, 360.0)
        self.fill_angle_spin.setDecimals(1)
        self.fill_angle_spin.setValue(0.0)
        self.fill_angle_spin.valueChanged.connect(self.update_fill_angle)
        clone_layout.addRow(self._label("元素角度:"), self.fill_angle_spin)

        self.clone_mirror_combo = QComboBox()
        self.clone_mirror_combo.addItems(["无镜像", "左右镜像", "上下镜像"])
        self.clone_mirror_combo.currentIndexChanged.connect(self.update_clone_mirror_mode_index)
        clone_layout.addRow(self._label("镜像:"), self.clone_mirror_combo)

        self.clone_group.add_content_layout(clone_layout)
        self.scroll_layout.addWidget(self.clone_group)
        self._register_module_group("clone", "图层分身", self.clone_group)

        # 5.（已移除）右侧栏“图层绑定/图层大小匹配”入口
        # 用户从左侧图层面板入口统一管理，避免重复入口造成混淆。
        self.bind_status_label = QLabel("未绑定")
        self.bind_status_label.setProperty("role", "muted")

        # 6. 图层变换组 (默认收起)
        self.transform_group = PropertySection("图层变换")
        self.transform_widget = LayerTransformWidget()
        self.transform_widget.rotation_changed.connect(self.update_layer_rotation)
        self.transform_widget.flip_horizontal_changed.connect(self.update_layer_flip_horizontal)
        self.transform_widget.flip_vertical_changed.connect(self.update_layer_flip_vertical)
        self.transform_widget.transform_reset.connect(self.reset_layer_transforms)
        self.transform_group.set_content_widget(self.transform_widget)
        self.scroll_layout.addWidget(self.transform_group)
        self._register_module_group("transform", "图层变换", self.transform_group)

        # 7. 随机变换组 (默认收起)
        self.random_transform_group = PropertySection("随机变换")
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

        # 按任务频率分配到两个顶层参数页，页内分区始终完整展示。
        self._reorder_layer_property_modules()

        # 8. 异形图层属性面板（初始隐藏）- 移入滚动区域以避免覆盖问题
        from app.ui.shaped_layer_panel import ShapedLayerPanel
        self.shaped_layer_panel = ShapedLayerPanel()
        self.shaped_layer_panel.hide()
        self.scroll_layout.addWidget(self.shaped_layer_panel)

        # 添加一个拉伸项，使控件集中在顶部
        self._scroll_stretch_index = self.scroll_layout.count()
        self.scroll_layout.addStretch(1)
        self.more_scroll_layout.addStretch(1)

        # 保存对普通图层面板的引用
        self.normal_layer_panel = self.property_tabs

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
        """收窄控件最小宽度，让 dock 可以随窗口变窄。

        ⚠ 2026-10-28 大改：这里原本还会**遍历整棵布局树重写间距/边距/对齐**：

            layout.setHorizontalSpacing(Tokens.ROW_GAP)   # 覆盖 _form() 的 12
            layout.setContentsMargins(0, 0, 0, 0)         # 抹掉分区内边距
            layout.setRowWrapPolicy(WrapLongRows)         # 覆盖 _form() 的 DontWrapRows

        这是"改一处被另一处覆盖"的典型：`_form()` 里刚统一好的行距/列距/不折行，
        构造完成后被这个函数逐个改回去 —— 于是同一份代码里存在**两个写布局的人**，
        谁也不服谁。这也是为什么反复调 `_form()` 看不出效果。

        布局规格现在只有 `_form()` 一个写入方，这里只保留"按内容收窄"的职责
        （它确实与布局规格无关，是窗口自适应需要的）。
        """
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

    def _register_module_group(self, module_key: str, title: str, group):
        """注册侧边栏分区；新版完整侧边栏不再提供模块拆分入口。"""
        self._module_groups[module_key] = group
        self._module_group_titles[module_key] = title
        self._module_order.append(module_key)

    def _reorder_layer_property_modules(self):
        """把属性分区分配到“基本参数”和“更多参数”两个页面。"""
        basic_order = ["basic", "source", "advanced", "shape", "appearance"]
        more_order = ["ai_generation", "clone", "transform", "random_transform"]
        desired_order = basic_order + more_order
        for key in desired_order:
            group = self._module_groups.get(key)
            if group is not None:
                self.scroll_layout.removeWidget(group)
                self.more_scroll_layout.removeWidget(group)
        for key in basic_order:
            group = self._module_groups.get(key)
            if group is not None:
                self.scroll_layout.addWidget(group)
        for key in more_order:
            group = self._module_groups.get(key)
            if group is not None:
                self.more_scroll_layout.addWidget(group)
        self._module_order = [k for k in desired_order if k in self._module_groups]

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
        # ⚠ 这里**不要**先 addDockWidget 再 setFloating(True)（2026-10-28 修正）。
        # 那个组合会让 dock 处于「既注册在停靠区、又标记为浮窗」的矛盾状态：
        # 用户把它拖回主窗口时，Qt 认为它「本来就在区里」，不产生落点吸附，
        # 表现就是「拖出来之后吸不回去」。
        # 正确做法：setParent(main_window) + setFloating(True)，由 Qt 自己
        # 处理浮窗；用户拖回时走正常的 dock 落点流程。
        dock.setParent(main_window)
        dock.show()
        dock.resize(260, 520)
        dock.setFloating(True)

        # 信号必须在 show 之后接，否则初始的 visible 变化会误触发「合并回面板」
        dock.visibilityChanged.connect(
            lambda visible, k=module_key: self._on_module_dock_visibility_changed(k, visible)
        )
        dock.topLevelChanged.connect(
            lambda _floating, _k=module_key: self._persist_module_layout()
        )
        if hasattr(dock, "dockLocationChanged"):
            dock.dockLocationChanged.connect(
                lambda _area, _k=module_key: self._persist_module_layout()
            )

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
        """完整侧边栏模式下不再恢复旧版模块拆分状态。"""
        return None

    def save_module_layout(self):
        """对外保存接口，供主窗口关闭时调用。"""
        self._persist_module_layout()

    def update_aspect_lock_icon(self):
        """更新锁定比例按钮的图标 - 专业简洁设计。

        ⚠ 不要在这里设置 `variant` 属性（2026-10-28 修正）。
        本按钮的尺寸由 `uiSize="iconSm"`（24px）控制，但 QSS 里
        `QPushButton[variant]` 这条属性选择器会把 height 强制成 LG 档（36），
        特异性高于 uiSize —— 实测该按钮渲染成 28×28，比同排按钮大一圈。
        语义色通过图标颜色表达就够，不需要借 variant 表达。
        """
        from app.ui.icon_manager import IconManager

        if self.aspect_lock_btn.isChecked():
            IconManager.apply_icon_to_button(self.aspect_lock_btn, 'link', 'primary')
            self.aspect_lock_btn.setToolTip("已锁定宽高比例 - 点击解锁")
        else:
            IconManager.apply_icon_to_button(self.aspect_lock_btn, 'unlink', 'secondary')
            self.aspect_lock_btn.setToolTip("宽高比例未锁定 - 点击锁定")
        self.aspect_lock_btn.style().unpolish(self.aspect_lock_btn)
        self.aspect_lock_btn.style().polish(self.aspect_lock_btn)

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
