#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的添加文字图层对话框
只包含最基本的文字内容输入，其他参数在属性面板设置
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QTextEdit, QPushButton, QCheckBox,
                               QMessageBox, QFrame, QSpinBox, QComboBox)
from PySide6.QtGui import QColor

from app.models.text_layer import TextLayer, TextAlign
from app.ui.color_picker_dialog_a2 import get_color_a2
from app.ui.dialog_a2 import DialogA2


class AddTextLayerDialog(QDialog):
    """简化的添加文字图层对话框"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.text_layer = None
        self.text_color = (0, 0, 0, 255)
        self.setup_ui()
        self.setWindowTitle("文字突出")
        self.setModal(True)
        self.resize(720, 560)

    def setup_ui(self):
        """设置 Dialog A2 创建弹窗布局。"""
        DialogA2.apply(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            DialogA2.OUTER_MARGIN,
            DialogA2.OUTER_MARGIN,
            DialogA2.OUTER_MARGIN,
            DialogA2.OUTER_MARGIN,
        )
        root.setSpacing(DialogA2.CONTENT_GAP)

        self.title_label = QLabel("文字突出")
        self.title_label.setProperty("role", "dialogTitle")
        root.addWidget(self.title_label)

        self.content_card = self._make_card()
        content_layout = QVBoxLayout(self.content_card)
        content_layout.setContentsMargins(*DialogA2.CARD_MARGIN)
        content_layout.setSpacing(DialogA2.CARD_GAP)

        content_header = QHBoxLayout()
        content_title = QLabel("文字内容")
        content_title.setProperty("role", "sectionTitle")
        self.content_summary_label = QLabel("1 条 · 绑定模式开启")
        self.content_summary_label.setProperty("role", "hint")
        content_header.addWidget(content_title)
        content_header.addStretch()
        content_header.addWidget(self.content_summary_label)
        content_layout.addLayout(content_header)

        name_layout = QHBoxLayout()
        name_layout.setSpacing(DialogA2.CONTENT_GAP)
        name_layout.addWidget(self._field_label("图层名称"))
        self.name_edit = QLineEdit("新文字图层")
        self.name_edit.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        name_layout.addWidget(self.name_edit, 1)

        self.binding_mode_check = QCheckBox("绑定")
        self.binding_mode_check.setChecked(True)
        self.binding_mode_check.toggled.connect(self._update_text_tip)
        name_layout.addWidget(self.binding_mode_check)
        content_layout.addLayout(name_layout)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText("示例文字")
        self.text_edit.setMinimumHeight(150)
        self.text_edit.setPlaceholderText("请输入文字内容，每行一个选项（支持随机选择）")
        self.text_edit.textChanged.connect(self._refresh_content_summary)
        content_layout.addWidget(self.text_edit)

        self.tip_label = QLabel("")
        self.tip_label.setProperty("role", "hint")
        content_layout.addWidget(self.tip_label)
        root.addWidget(self.content_card, 1)

        self.core_card = self._make_card()
        core_layout = QVBoxLayout(self.core_card)
        core_layout.setContentsMargins(*DialogA2.CARD_MARGIN)
        core_layout.setSpacing(DialogA2.CARD_GAP)

        core_header = QHBoxLayout()
        core_title = QLabel("核心参数")
        core_title.setProperty("role", "sectionTitle")
        self.core_summary_label = QLabel("微软雅黑 · 24px")
        self.core_summary_label.setProperty("role", "hint")
        core_header.addWidget(core_title)
        core_header.addStretch()
        core_header.addWidget(self.core_summary_label)
        core_layout.addLayout(core_header)

        font_row = QHBoxLayout()
        font_row.setSpacing(DialogA2.CONTENT_GAP)
        font_row.addWidget(self._field_label("字体"))
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "Arial"])
        self.font_combo.setEditable(True)
        self.font_combo.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        self.font_combo.currentTextChanged.connect(self._refresh_core_summary)
        font_row.addWidget(self.font_combo, 1)
        self.color_btn = QPushButton("文字颜色")
        self.color_btn.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        self.color_btn.clicked.connect(self.choose_text_color)
        font_row.addWidget(self.color_btn)
        core_layout.addLayout(font_row)

        params_row = QHBoxLayout()
        params_row.setSpacing(DialogA2.CONTENT_GAP)
        params_row.addWidget(self._field_label("字号"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 240)
        self.font_size_spin.setValue(24)
        self.font_size_spin.setSuffix(" px")
        self.font_size_spin.setFixedSize(92, DialogA2.CONTROL_HEIGHT)
        self.font_size_spin.valueChanged.connect(self._refresh_core_summary)
        params_row.addWidget(self.font_size_spin)
        params_row.addWidget(self._field_label("对齐方式"))
        self.align_combo = QComboBox()
        self.align_combo.addItems(["左对齐", "居中", "右对齐"])
        self.align_combo.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        params_row.addWidget(self.align_combo, 1)
        core_layout.addLayout(params_row)
        root.addWidget(self.core_card)

        self.footer_frame = QFrame()
        self.footer_frame.setProperty("role", "dialogFooter")
        footer_layout = QHBoxLayout(self.footer_frame)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch()
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        DialogA2.mark_primary(self.ok_button)
        DialogA2.mark_secondary(self.cancel_button)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.ok_button)
        footer_layout.addWidget(self.cancel_button)
        root.addWidget(self.footer_frame)

        self._update_text_tip(self.binding_mode_check.isChecked())
        self._refresh_core_summary()

    def _make_card(self):
        card = QFrame()
        card.setProperty("role", "dialogCard")
        return card

    def _field_label(self, text):
        label = QLabel(text)
        label.setProperty("role", "fieldLabel")
        label.setFixedWidth(DialogA2.FIELD_LABEL_WIDTH)
        return label

    def _refresh_content_summary(self):
        if not hasattr(self, "content_summary_label"):
            return
        text_lines = [line for line in self.text_edit.toPlainText().splitlines() if line.strip()]
        count = max(1, len(text_lines))
        mode = "绑定模式开启" if self.binding_mode_check.isChecked() else "真实换行"
        self.content_summary_label.setText(f"{count} 条 · {mode}")

    def _refresh_core_summary(self):
        if not hasattr(self, "core_summary_label"):
            return
        font = self.font_combo.currentText().strip() or "Microsoft YaHei"
        if font == "Microsoft YaHei":
            font = "微软雅黑"
        self.core_summary_label.setText(f"{font} · {self.font_size_spin.value()}px")

    def get_text_layer(self) -> TextLayer:
        """获取配置好的文字图层 - 简化版本"""
        # 获取编辑器文本（保留换行）
        text_content = self.text_edit.toPlainText()

        # 创建文字图层 - 只设置基本属性，其他用默认值
        self.text_layer = TextLayer(
            name=self.name_edit.text(),
            x=50,      # 默认位置
            y=50,      # 默认位置
            width=300,  # 默认大小
            height=100  # 默认大小
        )

        # 只设置最基本的属性，其他都在属性面板调整
        self.text_layer.font_family = self.font_combo.currentText().strip() or "Microsoft YaHei"
        self.text_layer.font_size = int(self.font_size_spin.value())
        self.text_layer.text_color = self.text_color
        align_map = {
            "左对齐": TextAlign.LEFT,
            "居中": TextAlign.CENTER,
            "右对齐": TextAlign.RIGHT,
        }
        self.text_layer.text_align = align_map.get(self.align_combo.currentText(), TextAlign.LEFT)
        self.text_layer.text_binding_enabled = self.binding_mode_check.isChecked()

        # 根据绑定模式设置文字内容
        self.text_layer.text_content = text_content
        text_lines = self.text_layer.get_text_lines()
        if not text_lines:
            self.text_layer.text_content = "示例文字"
            text_lines = self.text_layer.get_text_lines()
        self.text_layer.current_text = text_lines[0] if text_lines else "示例文字"

        return self.text_layer

    def accept(self):
        """确认按钮处理"""
        # 验证输入
        if not self.name_edit.text().strip():
            QMessageBox.warning(self, "警告", "请输入图层名称")
            return

        text_content = self.text_edit.toPlainText().strip()
        if not text_content:
            QMessageBox.warning(self, "警告", "请输入文字内容")
            return

        # 创建图层
        self.get_text_layer()
        super().accept()

    def _update_text_tip(self, enabled: bool):
        if enabled:
            self.tip_label.setText("提示：每行文字作为一个绑定候选文案")
            self.text_edit.setPlaceholderText("请输入文字内容，每行一个选项（支持随机选择）")
        else:
            self.tip_label.setText("提示：关闭绑定模式后，输入框换行会作为同一文案的真实换行")
            self.text_edit.setPlaceholderText("请输入完整文案，支持真实换行")
        self._refresh_content_summary()

    def choose_text_color(self):
        """选择新文字图层默认颜色。"""
        r, g, b, a = self.text_color
        color = get_color_a2(QColor(r, g, b, a), self, "选择文字颜色")
        if color.isValid():
            self.text_color = (color.red(), color.green(), color.blue(), color.alpha())
            self.color_btn.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
                "color: #FFFFFF; border-color: #55B2FF; font-weight: 700;"
            )


# 测试代码
if __name__ == "__main__":
    import sys
    from PySide6.QtWidgets import QApplication

    app = QApplication(sys.argv)

    dialog = AddTextLayerDialog()
    if dialog.exec() == QDialog.Accepted:
        text_layer = dialog.text_layer
        print(f"创建文字图层: {text_layer.name}")
        print(f"文字内容: {text_layer.current_text}")

    sys.exit(0)
