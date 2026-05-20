from PySide6.QtWidgets import QDialog, QVBoxLayout, QFormLayout, QSpinBox, QCheckBox, QPushButton, QHBoxLayout, QLabel, QComboBox, QColorDialog, QTabWidget, QWidget, QSlider, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

class LayerEffectsDialog(QDialog):
    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setWindowTitle("图层样式")
        self.setModal(True)
        self.resize(500, 400)

        # State variables
        self._current_stroke_color = (0, 0, 0, 255)
        self._current_overlay_color = (255, 0, 0, 255)
        self._current_gradient_start = (0, 0, 0, 255)
        self._current_gradient_end = (255, 255, 255, 255)

        self._setup_ui()
        self._load_current_layer()

    def _setup_ui(self):
        layout = QVBoxLayout(self)

        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Tab 1: 描边与圆角
        self._setup_stroke_tab()

        # Tab 2: 颜色叠加
        self._setup_color_overlay_tab()

        # Tab 3: 渐变叠加
        self._setup_gradient_overlay_tab()

        # Buttons
        btns = QHBoxLayout()
        self.ok_btn = QPushButton("确定")
        self.cancel_btn = QPushButton("取消")
        self.ok_btn.clicked.connect(self._apply_and_close)
        self.cancel_btn.clicked.connect(self.reject)
        btns.addWidget(self.ok_btn)
        btns.addWidget(self.cancel_btn)
        layout.addLayout(btns)

    def _setup_stroke_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.corner_spin = QSpinBox()
        self.corner_spin.setRange(0, 1000)
        form.addRow("圆角半径:", self.corner_spin)

        self.stroke_enable = QCheckBox("启用描边")
        form.addRow(self.stroke_enable)

        self.stroke_width = QSpinBox()
        self.stroke_width.setRange(1, 1000)
        form.addRow("描边宽度:", self.stroke_width)

        self.stroke_type = QComboBox()
        self.stroke_type.addItems(["内描边", "居中描边", "外描边"])
        form.addRow("描边类型:", self.stroke_type)

        color_layout = QHBoxLayout()
        self.stroke_color_label = QLabel("RGBA: (0,0,0,255)")
        self.stroke_pick_btn = QPushButton("选择颜色")
        self.stroke_pick_btn.clicked.connect(self._pick_stroke_color)
        color_layout.addWidget(self.stroke_color_label)
        color_layout.addWidget(self.stroke_pick_btn)
        form.addRow("描边颜色:", color_layout)

        self.tabs.addTab(tab, "描边与圆角")

    def _setup_color_overlay_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.color_overlay_enable = QCheckBox("启用颜色叠加")
        form.addRow(self.color_overlay_enable)

        # Color
        color_layout = QHBoxLayout()
        self.overlay_color_label = QLabel("RGBA: (255,0,0,255)")
        self.overlay_pick_btn = QPushButton("选择颜色")
        self.overlay_pick_btn.clicked.connect(self._pick_overlay_color)
        color_layout.addWidget(self.overlay_color_label)
        color_layout.addWidget(self.overlay_pick_btn)
        form.addRow("叠加颜色:", color_layout)

        # Opacity
        self.overlay_opacity_slider = QSlider(Qt.Horizontal)
        self.overlay_opacity_slider.setRange(0, 100)
        self.overlay_opacity_slider.setValue(100)
        self.overlay_opacity_label = QLabel("100%")
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(self.overlay_opacity_slider)
        opacity_layout.addWidget(self.overlay_opacity_label)
        self.overlay_opacity_slider.valueChanged.connect(lambda v: self.overlay_opacity_label.setText(f"{v}%"))
        form.addRow("不透明度:", opacity_layout)

        self.tabs.addTab(tab, "颜色叠加")

    def _setup_gradient_overlay_tab(self):
        tab = QWidget()
        form = QFormLayout(tab)

        self.gradient_overlay_enable = QCheckBox("启用渐变叠加")
        form.addRow(self.gradient_overlay_enable)

        # Start Color
        start_layout = QHBoxLayout()
        self.grad_start_label = QLabel("Start: (0,0,0,255)")
        self.grad_start_btn = QPushButton("起始颜色")
        self.grad_start_btn.clicked.connect(self._pick_grad_start)
        start_layout.addWidget(self.grad_start_label)
        start_layout.addWidget(self.grad_start_btn)
        form.addRow("渐变起始:", start_layout)

        # End Color
        end_layout = QHBoxLayout()
        self.grad_end_label = QLabel("End: (255,255,255,255)")
        self.grad_end_btn = QPushButton("结束颜色")
        self.grad_end_btn.clicked.connect(self._pick_grad_end)
        end_layout.addWidget(self.grad_end_label)
        end_layout.addWidget(self.grad_end_btn)
        form.addRow("渐变结束:", end_layout)

        # Angle
        self.grad_angle_spin = QSpinBox()
        self.grad_angle_spin.setRange(-360, 360)
        self.grad_angle_spin.setValue(90)
        form.addRow("角度 (度):", self.grad_angle_spin)

        # Opacity
        self.grad_opacity_slider = QSlider(Qt.Horizontal)
        self.grad_opacity_slider.setRange(0, 100)
        self.grad_opacity_slider.setValue(100)
        self.grad_opacity_label = QLabel("100%")
        opacity_layout = QHBoxLayout()
        opacity_layout.addWidget(self.grad_opacity_slider)
        opacity_layout.addWidget(self.grad_opacity_label)
        self.grad_opacity_slider.valueChanged.connect(lambda v: self.grad_opacity_label.setText(f"{v}%"))
        form.addRow("不透明度:", opacity_layout)

        self.tabs.addTab(tab, "渐变叠加")

    def _load_current_layer(self):
        idx = getattr(self.document, 'selected_layer_index', -1)
        if idx < 0 or idx >= len(self.document.layers):
            return
        layer = self.document.layers[idx]

        # Existing
        if hasattr(layer, 'corner_radius'):
            self.corner_spin.setValue(layer.corner_radius)
        if hasattr(layer, 'stroke_enabled'):
            self.stroke_enable.setChecked(layer.stroke_enabled)
        if hasattr(layer, 'stroke_width'):
            self.stroke_width.setValue(layer.stroke_width)
        if hasattr(layer, 'stroke_type'):
            self.stroke_type.setCurrentIndex(layer.stroke_type)
        if hasattr(layer, 'stroke_color'):
            self._current_stroke_color = layer.stroke_color
            self.stroke_color_label.setText(f"RGBA: {self._current_stroke_color}")

        # Color Overlay
        if hasattr(layer, 'color_overlay_enabled'):
            self.color_overlay_enable.setChecked(layer.color_overlay_enabled)
        if hasattr(layer, 'color_overlay_color'):
            self._current_overlay_color = layer.color_overlay_color
            self.overlay_color_label.setText(f"RGBA: {self._current_overlay_color}")
        if hasattr(layer, 'color_overlay_opacity'):
            val = int(layer.color_overlay_opacity * 100)
            self.overlay_opacity_slider.setValue(val)
            self.overlay_opacity_label.setText(f"{val}%")

        # Gradient Overlay
        if hasattr(layer, 'gradient_overlay_enabled'):
            self.gradient_overlay_enable.setChecked(layer.gradient_overlay_enabled)
        if hasattr(layer, 'gradient_overlay_colors') and len(layer.gradient_overlay_colors) >= 2:
            self._current_gradient_start = layer.gradient_overlay_colors[0]
            self._current_gradient_end = layer.gradient_overlay_colors[1]
            self.grad_start_label.setText(f"Start: {self._current_gradient_start}")
            self.grad_end_label.setText(f"End: {self._current_gradient_end}")
        if hasattr(layer, 'gradient_overlay_angle'):
            self.grad_angle_spin.setValue(int(layer.gradient_overlay_angle))
        if hasattr(layer, 'gradient_overlay_opacity'):
            val = int(layer.gradient_overlay_opacity * 100)
            self.grad_opacity_slider.setValue(val)
            self.grad_opacity_label.setText(f"{val}%")

    def _pick_color_generic(self, current_color, title):
        qcol = QColor.fromRgb(*current_color[:3], current_color[3])
        sel = QColorDialog.getColor(qcol, self, title, QColorDialog.ShowAlphaChannel)
        if sel.isValid():
            return (sel.red(), sel.green(), sel.blue(), sel.alpha())
        return None

    def _pick_stroke_color(self):
        col = self._pick_color_generic(self._current_stroke_color, "选择描边颜色")
        if col:
            self._current_stroke_color = col
            self.stroke_color_label.setText(f"RGBA: {col}")

    def _pick_overlay_color(self):
        col = self._pick_color_generic(self._current_overlay_color, "选择叠加颜色")
        if col:
            self._current_overlay_color = col
            self.overlay_color_label.setText(f"RGBA: {col}")

    def _pick_grad_start(self):
        col = self._pick_color_generic(self._current_gradient_start, "选择渐变起始颜色")
        if col:
            self._current_gradient_start = col
            self.grad_start_label.setText(f"Start: {col}")

    def _pick_grad_end(self):
        col = self._pick_color_generic(self._current_gradient_end, "选择渐变结束颜色")
        if col:
            self._current_gradient_end = col
            self.grad_end_label.setText(f"End: {col}")

    def _apply_and_close(self):
        idx = getattr(self.document, 'selected_layer_index', -1)
        if idx < 0 or idx >= len(self.document.layers):
            self.accept()
            return
        layer = self.document.layers[idx]

        # Apply Stroke & Corner
        if hasattr(layer, 'corner_radius'): layer.corner_radius = self.corner_spin.value()
        if hasattr(layer, 'stroke_enabled'): layer.stroke_enabled = self.stroke_enable.isChecked()
        if hasattr(layer, 'stroke_width'): layer.stroke_width = self.stroke_width.value()
        if hasattr(layer, 'stroke_type'): layer.stroke_type = self.stroke_type.currentIndex()
        if hasattr(layer, 'stroke_color'): layer.stroke_color = self._current_stroke_color

        # Apply Color Overlay
        if hasattr(layer, 'color_overlay_enabled'):
            layer.color_overlay_enabled = self.color_overlay_enable.isChecked()
        if hasattr(layer, 'color_overlay_color'):
            layer.color_overlay_color = self._current_overlay_color
        if hasattr(layer, 'color_overlay_opacity'):
            layer.color_overlay_opacity = self.overlay_opacity_slider.value() / 100.0

        # Apply Gradient Overlay
        if hasattr(layer, 'gradient_overlay_enabled'):
            layer.gradient_overlay_enabled = self.gradient_overlay_enable.isChecked()
        if hasattr(layer, 'gradient_overlay_colors'):
            layer.gradient_overlay_colors = [self._current_gradient_start, self._current_gradient_end]
        if hasattr(layer, 'gradient_overlay_angle'):
            layer.gradient_overlay_angle = float(self.grad_angle_spin.value())
        if hasattr(layer, 'gradient_overlay_opacity'):
            layer.gradient_overlay_opacity = self.grad_opacity_slider.value() / 100.0

        self.accept()
