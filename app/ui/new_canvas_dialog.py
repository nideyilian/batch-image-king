"""新建画布对话框 — 设计系统视觉试点。

保留全部既有功能（预设下拉、宽高二选、比例快捷、透明背景、预设管理/保存），
并落地新设计系统：
- 头部范式（标题 + 说明）。
- SVG 图标（来自 IconManager）。
- 实时画布比例预览卡片。
- 行内校验（InlineAlert），取代模态错误框。
- 规范的主次按钮与 Enter/Escape 行为。

预设数据来源于 CanvasPresetManager（内置 + 用户自定义），不依赖外部 controller。
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QSpinBox,
    QComboBox, QCheckBox, QDialogButtonBox, QFrame, QSizePolicy,
    QInputDialog, QWidget, QSpacerItem,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QPainter, QColor, QBrush, QPen, QPaintEvent, QFontMetrics

from app.ui.canvas_preset_dialog import CanvasPresetManagerDialog
from app.ui.design_tokens import Tokens
from app.ui.icon_manager import IconManager
from app.ui.ui_primitives import InlineAlert
from app.ui.components import Button, Input
from app.utils.canvas_preset_manager import CanvasPresetManager


class _CanvasPreview(QWidget):
    """画布比例实时预览：按宽高比居中绘制一个代表画布的矩形。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._w = 1080
        self._h = 1080
        self.setMinimumSize(180, 180)

    def set_size(self, w, h):
        self._w = max(1, int(w))
        self._h = max(1, int(h))
        self.update()

    def paintEvent(self, ev: QPaintEvent):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        pad = 18
        area = self.rect().adjusted(pad, pad, -pad, -pad)
        aw, ah = area.width(), area.height()
        if aw <= 0 or ah <= 0:
            return
        scale = min(aw / self._w, ah / self._h)
        rw, rh = self._w * scale, self._h * scale
        x = area.x() + (aw - rw) / 2
        y = area.y() + (ah - rh) / 2

        # 预览区底色
        p.fillRect(self.rect(), QColor(Tokens.BG_SECONDARY))
        # 棋盘格提示透明区域
        cell = 12
        base = QColor(Tokens.BORDER_SUBTLE)
        alt = QColor(Tokens.BG_ELEVATED)
        for cy in range(int(y), int(y + rh), cell):
            for cx in range(int(x), int(x + rw), cell):
                cw = min(cell, int(x + rw) - cx)
                ch = min(cell, int(y + rh) - cy)
                fill = base if ((cx // cell + cy // cell) % 2 == 0) else alt
                p.fillRect(cx, cy, cw, ch, fill)

        # 画布矩形
        rect_color = QColor(Tokens.BG_ELEVATED)
        p.setBrush(QBrush(rect_color))
        p.setPen(QPen(QColor(Tokens.ACCENT), 1.5))
        p.drawRoundedRect(int(x), int(y), int(rw), int(rh), 4, 4)

        # 尺寸文字
        fm = QFontMetrics(self.font())
        text = f"{self._w} × {self._h}"
        tw = fm.horizontalAdvance(text)
        ty = area.y() + ah - 4
        p.setPen(QColor(Tokens.TEXT_SECONDARY))
        p.drawText(int(area.x() + (aw - tw) / 2), ty, text)


class NewCanvasDialog(QDialog):
    """新建画布对话框。"""

    def __init__(self, parent=None, controller=None, default_settings=None, title=None):
        super().__init__(parent)
        self.controller = controller
        self.preset_manager = CanvasPresetManager()
        self.result_settings = None
        self._default = default_settings or {}

        self.setObjectName("NewCanvasDialog")
        self.setProperty("role", "dialog")
        self.setWindowTitle(title or "新建画布")
        self.setModal(True)
        self.setMinimumWidth(520)
        self.setMinimumHeight(420)

        # 作用域化应用 section 角色样式，其余控件沿用全局主题
        self.setStyleSheet(
            Tokens.panel_qss("QDialog#NewCanvasDialog") +
            f"QDialog#NewCanvasDialog QWidget#HeaderBar {{ "
            f"border-bottom: 1px solid {Tokens.BORDER_SOFT}; }}"
            f"QDialog#NewCanvasDialog QWidget#FooterBar {{ "
            f"border-top: 1px solid {Tokens.BORDER_SOFT}; }}"
        )

        self._build_header()
        self._build_body(default_settings)
        self._refresh_presets(default_settings)
        self._build_footer()
        self._wire()
        self._apply_layout()

    # ------------------------------------------------------------------ #
    # 构建
    # ------------------------------------------------------------------ #
    def _build_header(self):
        bar = QWidget()
        bar.setObjectName("HeaderBar")
        bar.setFixedHeight(64)
        layout = QHBoxLayout(bar)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.setSpacing(12)

        icon = QLabel()
        icon.setPixmap(IconManager.get_icon("image", 22, Tokens.ACCENT).pixmap(22, 22))
        icon.setFixedSize(22, 22)
        layout.addWidget(icon)

        texts = QVBoxLayout()
        texts.setSpacing(2)
        title = QLabel(self.windowTitle())
        title.setObjectName("DialogTitle")
        title.setProperty("role", "dialog-title")
        desc = QLabel("设置画布尺寸与文档名称，开始你的设计。")
        desc.setProperty("role", "muted")
        texts.addWidget(title)
        texts.addWidget(desc)
        layout.addLayout(texts)
        layout.addStretch(1)

        self._header = bar

    def _build_body(self, default_settings):
        body = QWidget()
        layout = QHBoxLayout(body)
        layout.setContentsMargins(20, 16, 20, 16)
        layout.setSpacing(20)

        # 左侧：表单
        left = QVBoxLayout()
        left.setSpacing(12)

        name_label = QLabel("文档名称")
        name_label.setProperty("role", "fieldLabel")
        self.name_edit = Input(placeholder="未命名文档")
        self.name_edit.setMinimumHeight(32)
        default_name = (default_settings or {}).get("document_name", "未命名文档")
        self.name_edit.setText(default_name)
        left.addWidget(name_label)
        left.addWidget(self.name_edit)

        # 行内校验提示
        self.alert = InlineAlert()
        left.addWidget(self.alert)

        preset_label = QLabel("画布预设")
        preset_label.setProperty("role", "fieldLabel")
        self.preset_combo = QComboBox()
        self.preset_combo.setMinimumHeight(32)
        left.addWidget(preset_label)
        left.addWidget(self.preset_combo)

        size_label = QLabel("画布尺寸（像素）")
        size_label.setProperty("role", "fieldLabel")
        left.addWidget(size_label)

        size_row = QHBoxLayout()
        size_row.setSpacing(8)
        self.width_spin = self._make_spin()
        self.height_spin = self._make_spin()
        # 兼容旧调用方 DocumentController.new_document() 读取 width_spinbox/height_spinbox
        self.width_spinbox = self.width_spin
        self.height_spinbox = self.height_spin
        w_label = QLabel("宽")
        w_label.setProperty("role", "mutedLabel")
        h_label = QLabel("高")
        h_label.setProperty("role", "mutedLabel")
        swap_btn = IconManager.create_icon_button("swap")
        swap_btn.setToolTip("交换宽高")
        swap_btn.setAccessibleName("交换宽高")
        swap_btn.setFixedSize(32, 32)
        swap_btn.clicked.connect(self._swap_dimensions)
        size_row.addWidget(w_label)
        size_row.addWidget(self.width_spin)
        size_row.addWidget(h_label)
        size_row.addWidget(self.height_spin)
        size_row.addWidget(swap_btn)
        size_row.addStretch(1)
        left.addLayout(size_row)

        # 比例快捷
        ratio_row = QHBoxLayout()
        ratio_row.setSpacing(8)
        for label, (w, h) in (("16:9", (1920, 1080)), ("4:3", (1600, 1200)), ("1:1", (1080, 1080))):
            btn = Button(label, variant="ghost", size="sm")
            btn.setToolTip(f"应用 {label} 比例（{w}×{h}）")
            btn.setAccessibleName(f"应用 {label} 比例")
            btn.clicked.connect(lambda _checked, w=w, h=h: self._apply_ratio(w, h))
            ratio_row.addWidget(btn)
        ratio_row.addStretch(1)
        left.addLayout(ratio_row)

        # 透明背景
        self.transparent_check = QCheckBox("透明背景")
        left.addWidget(self.transparent_check)

        # 预设操作
        preset_ops = QHBoxLayout()
        preset_ops.setSpacing(8)
        manage_btn = Button("管理预设", variant="ghost", size="sm")
        manage_btn.setIcon(IconManager.get_icon("settings", 16, "secondary"))
        manage_btn.setIconSize(QSize(16, 16))
        manage_btn.setToolTip("管理画布预设")
        manage_btn.setAccessibleName("管理画布预设")
        manage_btn.clicked.connect(self._manage_presets)
        save_btn = Button("保存为预设…", variant="ghost", size="sm")
        save_btn.setIcon(IconManager.get_icon("plus", 16, "secondary"))
        save_btn.setIconSize(QSize(16, 16))
        save_btn.setToolTip("保存当前尺寸为预设")
        save_btn.setAccessibleName("保存为预设")
        save_btn.clicked.connect(self._save_preset)
        preset_ops.addWidget(manage_btn)
        preset_ops.addWidget(save_btn)
        preset_ops.addStretch(1)
        left.addLayout(preset_ops)

        left.addSpacerItem(QSpacerItem(0, 0, QSizePolicy.Minimum, QSizePolicy.Expanding))

        # 右侧：预览卡片
        right = QVBoxLayout()
        right.setSpacing(8)
        preview_frame = QFrame()
        preview_frame.setProperty("role", "section")
        preview_inner = QVBoxLayout(preview_frame)
        preview_inner.setContentsMargins(12, 12, 12, 12)
        ph = QLabel("画布预览")
        ph.setProperty("role", "fieldLabel")
        self.preview = _CanvasPreview()
        preview_inner.addWidget(ph)
        preview_inner.addWidget(self.preview, 1)
        right.addWidget(preview_frame, 1)

        layout.addLayout(left, 3)
        layout.addLayout(right, 2)
        self._body = body

    def _build_footer(self):
        footer = QWidget()
        footer.setObjectName("FooterBar")
        layout = QHBoxLayout(footer)
        layout.setContentsMargins(20, 12, 20, 12)
        layout.addStretch(1)
        self.button_box = QDialogButtonBox()
        cancel = self.button_box.addButton("取消", QDialogButtonBox.ButtonRole.RejectRole)
        cancel.setProperty("variant", "outline")
        cancel.setMinimumHeight(36)
        ok = self.button_box.addButton("确定", QDialogButtonBox.ButtonRole.AcceptRole)
        ok.setProperty("variant", "default")
        ok.setMinimumHeight(36)
        ok.setDefault(True)
        self.button_box.rejected.connect(self.reject)
        self.button_box.accepted.connect(self.accept)
        layout.addWidget(self.button_box)
        self._footer = footer

    # ------------------------------------------------------------------ #
    # 控件工厂
    # ------------------------------------------------------------------ #
    def _make_spin(self):
        spin = QSpinBox()
        spin.setRange(1, 10000)
        spin.setSuffix(" px")
        spin.setMinimumHeight(32)
        spin.setButtonSymbols(QSpinBox.ButtonSymbols.PlusMinus)
        return spin

    def _apply_layout(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self._header)
        main.addWidget(self._body, 1)
        main.addWidget(self._footer)
        self.setLayout(main)

    # ------------------------------------------------------------------ #
    # 信号
    # ------------------------------------------------------------------ #
    def _wire(self):
        self.width_spin.valueChanged.connect(
            lambda v: self.preview.set_size(v, self.height_spin.value()))
        self.height_spin.valueChanged.connect(
            lambda v: self.preview.set_size(self.width_spin.value(), v))
        self.preset_combo.currentTextChanged.connect(self._on_preset_changed)
        self.name_edit.returnPressed.connect(self.accept)
        self.name_edit.textChanged.connect(self._on_name_changed)

    def _refresh_presets(self, default_settings=None):
        self._default = default_settings or {}
        presets = self.preset_manager.get_all_presets()
        names = [p["name"] for p in presets]
        self.preset_combo.blockSignals(True)
        self.preset_combo.clear()
        self.preset_combo.addItem("自定义")
        for n in names:
            self.preset_combo.addItem(n)
        self.preset_combo.blockSignals(False)

        ds = default_settings or {}
        w = int(ds.get("width", 1080))
        h = int(ds.get("height", 1080))
        self.width_spin.setValue(w)
        self.height_spin.setValue(h)
        self.transparent_check.setChecked(bool(ds.get("transparent", False)))
        name = ds.get("document_name")
        if name:
            self.name_edit.setText(name)
        for p in presets:
            if p["name"] == self.preset_combo.currentText():
                break
        self.preview.set_size(self.width_spin.value(), self.height_spin.value())

    def _on_name_changed(self, text):
        if text.strip():
            self.alert.setVisible(False)

    def _on_preset_changed(self, text):
        if text == "自定义":
            return
        for p in self.preset_manager.get_all_presets():
            if p["name"] == text:
                self.width_spin.blockSignals(True)
                self.height_spin.blockSignals(True)
                self.width_spin.setValue(int(p["width"]))
                self.height_spin.setValue(int(p["height"]))
                self.transparent_check.setChecked(bool(p.get("transparent", False)))
                self.width_spin.blockSignals(False)
                self.height_spin.blockSignals(False)
                self.preview.set_size(p["width"], p["height"])
                break

    def _swap_dimensions(self):
        w = self.width_spin.value()
        h = self.height_spin.value()
        self.width_spin.setValue(h)
        self.height_spin.setValue(w)
        self.preset_combo.setCurrentText("自定义")

    def _apply_ratio(self, w, h):
        self.width_spin.setValue(w)
        self.height_spin.setValue(h)
        self.preset_combo.setCurrentText("自定义")

    def _manage_presets(self):
        dlg = CanvasPresetManagerDialog(self)
        dlg.exec()
        # 管理对话框内部使用独立管理器实例，关闭后从磁盘刷新本对话框的预设
        self.preset_manager.user_presets = self.preset_manager.load_user_presets()
        self._refresh_presets(self._default)

    def _save_preset(self):
        name, ok = QInputDialog.getText(self, "保存为预设", "预设名称：")
        if not ok or not name.strip():
            return
        name = name.strip()
        width = self.width_spin.value()
        height = self.height_spin.value()
        if self.preset_manager.preset_exists(name):
            self.alert.set_level("error")
            self.alert.set_text(f"预设「{name}」已存在，请换一个名称。")
            return
        success = self.preset_manager.add_custom_preset(name, width, height, "自定义")
        if success:
            self.alert.set_level("success")
            self.alert.set_text(f"已保存预设「{name}」。")
        else:
            self.alert.set_level("error")
            self.alert.set_text("保存预设失败，请检查尺寸是否有效。")
        self.alert.setVisible(True)
        self._refresh_presets(self._default)

    # ------------------------------------------------------------------ #
    # 校验与结果
    # ------------------------------------------------------------------ #
    def accept(self):
        name = self.name_edit.text().strip()
        if not name:
            self.alert.set_level("error")
            self.alert.set_text("请输入文档名称。")
            self.alert.setVisible(True)
            self.name_edit.setFocus()
            return
        width = self.width_spin.value()
        height = self.height_spin.value()
        if not (1 <= width <= 10000) or not (1 <= height <= 10000):
            self.alert.set_level("error")
            self.alert.set_text("画布宽高需在 1–10000 像素之间。")
            self.alert.setVisible(True)
            return

        self.result_settings = {
            "document_name": name,
            "width": width,
            "height": height,
            "transparent": self.transparent_check.isChecked(),
            "unit": "px",
        }
        super().accept()


def get_canvas_settings(parent=None, controller=None, default_settings=None, title=None):
    """显示新建画布对话框，返回设置字典或 None。"""
    dialog = NewCanvasDialog(parent, controller, default_settings, title)
    if dialog.exec() == QDialog.DialogCode.Accepted:
        return dialog.result_settings
    return None
