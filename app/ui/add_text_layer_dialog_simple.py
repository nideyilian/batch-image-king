#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化的添加文字图层对话框
只包含最基本的文字内容输入，其他参数在属性面板设置
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QLineEdit, QTextEdit, QPushButton, QDialogButtonBox, QCheckBox,
                               QMessageBox, QFrame, QSpinBox, QComboBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from app.models.text_layer import TextLayer, TextAlign
from app.ui.color_picker_dialog_a2 import get_color_a2
from app.ui.dark_theme import CursorDarkTheme


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
        """设置UI布局 - Photoshop 风格的文字创建面板"""
        self.setStyleSheet(f"""
            QDialog {{
                background-color: {CursorDarkTheme.BACKGROUND_PRIMARY};
                color: {CursorDarkTheme.TEXT_PRIMARY};
            }}
            QLabel {{
                color: {CursorDarkTheme.TEXT_SECONDARY};
                background: transparent;
                font-size: 12px;
            }}
            QLabel[role="title"] {{
                color: {CursorDarkTheme.TEXT_PRIMARY};
                font-size: 16px;
                font-weight: 700;
            }}
            QLabel[role="sectionTitle"] {{
                color: {CursorDarkTheme.TEXT_PRIMARY};
                font-size: 13px;
                font-weight: 700;
            }}
            QFrame[role="rail"] {{
                background-color: {CursorDarkTheme.BACKGROUND_SECONDARY};
                border: 1px solid {CursorDarkTheme.BORDER_PRIMARY};
                border-radius: 7px;
            }}
            QFrame[role="section"] {{
                background-color: {CursorDarkTheme.BACKGROUND_SECONDARY};
                border: 1px solid {CursorDarkTheme.BORDER_PRIMARY};
                border-radius: 7px;
            }}
            QTextEdit, QLineEdit, QSpinBox, QComboBox {{
                background-color: {CursorDarkTheme.BACKGROUND_ELEVATED};
                color: {CursorDarkTheme.TEXT_PRIMARY};
                border: 1px solid {CursorDarkTheme.BORDER_SECONDARY};
                border-radius: 4px;
                padding: 5px 7px;
                selection-background-color: {CursorDarkTheme.ACCENT_PRIMARY};
            }}
            QTextEdit:focus, QLineEdit:focus, QSpinBox:focus, QComboBox:focus {{
                border-color: {CursorDarkTheme.BORDER_FOCUS};
            }}
            QPushButton {{
                min-height: 30px;
                border: 1px solid {CursorDarkTheme.BORDER_SECONDARY};
                border-radius: 4px;
                background-color: {CursorDarkTheme.BACKGROUND_TERTIARY};
                color: {CursorDarkTheme.TEXT_PRIMARY};
                padding: 5px 14px;
            }}
            QPushButton:hover {{
                background-color: {CursorDarkTheme.HOVER_BG};
                border-color: {CursorDarkTheme.ACCENT_HOVER};
            }}
            QPushButton#primaryButton {{
                background-color: {CursorDarkTheme.ACCENT_PRIMARY};
                border-color: {CursorDarkTheme.ACCENT_HOVER};
                color: {CursorDarkTheme.TEXT_INVERTED};
                font-weight: 700;
            }}
            QCheckBox {{
                color: {CursorDarkTheme.TEXT_PRIMARY};
                spacing: 6px;
            }}
            QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border-radius: 3px;
                border: 1px solid {CursorDarkTheme.BORDER_SECONDARY};
                background: {CursorDarkTheme.BACKGROUND_ELEVATED};
            }}
            QCheckBox::indicator:checked {{
                background: {CursorDarkTheme.ACCENT_PRIMARY};
                border-color: {CursorDarkTheme.ACCENT_HOVER};
            }}
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        title_row = QHBoxLayout()
        title = QLabel("文字突出")
        title.setProperty("role", "title")
        title_row.addWidget(title)
        title_row.addStretch()
        layout.addLayout(title_row)

        body_layout = QHBoxLayout()
        body_layout.setSpacing(12)

        rail = QFrame()
        rail.setProperty("role", "rail")
        rail.setFixedWidth(96)
        rail_layout = QVBoxLayout(rail)
        rail_layout.setContentsMargins(10, 12, 10, 12)
        rail_layout.setSpacing(10)
        text_mode = QPushButton("T\n文字")
        text_mode.setObjectName("primaryButton")
        text_mode.setEnabled(False)
        rail_layout.addWidget(text_mode)
        rail_layout.addStretch()
        body_layout.addWidget(rail)

        content_frame = QFrame()
        content_frame.setProperty("role", "section")
        content_layout = QVBoxLayout(content_frame)
        content_layout.setContentsMargins(16, 16, 16, 16)
        content_layout.setSpacing(12)

        content_title = QLabel("文字内容")
        content_title.setProperty("role", "sectionTitle")
        content_layout.addWidget(content_title)

        name_layout = QHBoxLayout()
        name_layout.addWidget(QLabel("图层名称"))
        self.name_edit = QLineEdit("新文字图层")
        name_layout.addWidget(self.name_edit, 1)

        self.binding_mode_check = QCheckBox("启用绑定模式(按行文案)")
        self.binding_mode_check.setChecked(True)
        self.binding_mode_check.toggled.connect(self._update_text_tip)
        name_layout.addWidget(self.binding_mode_check)
        content_layout.addLayout(name_layout)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText("示例文字")
        self.text_edit.setMinimumHeight(130)
        self.text_edit.setPlaceholderText("请输入文字内容，每行一个选项（支持随机选择）")
        content_layout.addWidget(self.text_edit)

        # 提示文本
        self.tip_label = QLabel("")
        self.tip_label.setStyleSheet(f"color: {CursorDarkTheme.TEXT_MUTED}; font-size: 11px;")
        content_layout.addWidget(self.tip_label)
        self._update_text_tip(self.binding_mode_check.isChecked())

        style_title = QLabel("核心参数")
        style_title.setProperty("role", "sectionTitle")
        content_layout.addWidget(style_title)

        style_row = QHBoxLayout()
        style_row.setSpacing(10)
        style_row.addWidget(QLabel("字体"))
        self.font_combo = QComboBox()
        self.font_combo.addItems(["Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "Arial"])
        self.font_combo.setEditable(True)
        style_row.addWidget(self.font_combo, 1)

        style_row.addWidget(QLabel("字号"))
        self.font_size_spin = QSpinBox()
        self.font_size_spin.setRange(6, 240)
        self.font_size_spin.setValue(24)
        self.font_size_spin.setSuffix(" px")
        self.font_size_spin.setFixedWidth(92)
        style_row.addWidget(self.font_size_spin)

        self.color_btn = QPushButton("文字颜色")
        self.color_btn.clicked.connect(self.choose_text_color)
        style_row.addWidget(self.color_btn)
        content_layout.addLayout(style_row)

        align_row = QHBoxLayout()
        align_row.addWidget(QLabel("对齐方式"))
        self.align_combo = QComboBox()
        self.align_combo.addItems(["左对齐", "居中", "右对齐"])
        align_row.addWidget(self.align_combo)
        align_row.addStretch()
        content_layout.addLayout(align_row)

        body_layout.addWidget(content_frame, 1)
        layout.addLayout(body_layout, 1)

        # 按钮区域
        button_box = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
            Qt.Horizontal
        )
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)

        # 设置按钮中文文本
        button_box.button(QDialogButtonBox.Ok).setText("确定")
        button_box.button(QDialogButtonBox.Cancel).setText("取消")
        button_box.button(QDialogButtonBox.Ok).setObjectName("primaryButton")

        layout.addWidget(button_box)

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

    def choose_text_color(self):
        """选择新文字图层默认颜色。"""
        r, g, b, a = self.text_color
        color = get_color_a2(QColor(r, g, b, a), self, "选择文字颜色")
        if color.isValid():
            self.text_color = (color.red(), color.green(), color.blue(), color.alpha())
            self.color_btn.setStyleSheet(
                f"background-color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
                "color: #FFFFFF; border-color: #55B2FF;"
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
