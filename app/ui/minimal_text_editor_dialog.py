#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
极简文字编辑对话框 - 类似微软记事本的简洁界面
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QTextEdit, QPushButton)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont

from app.ui.tokens_v2 import Color


class MinimalTextEditorDialog(QDialog):
    """极简文字编辑器对话框 - 类似微软记事本风格"""

    text_changed = Signal(str)  # 文字内容改变信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_text = ""
        self.setWindowTitle("编辑文字")
        self.resize(500, 350)  # 适中的大小，类似记事本
        self.setup_ui()

    def setup_ui(self):
        """设置UI界面 - 极简风格"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(12, 12, 12, 12)

        # 简单的标题
        title_label = QLabel("文字内容")
        title_label.setStyleSheet(f"font-weight: 600; font-size: 14px; color: {Color.text_primary};")
        main_layout.addWidget(title_label)

        # 主要编辑区域 - 类似记事本的简洁文本框
        self.text_edit = QTextEdit()
        self.text_edit.setFont(QFont("Microsoft YaHei", 11))
        self.text_edit.setPlaceholderText("在此输入文字内容...")

        # 样式交给全局主题（dark_theme / provider）。
        #
        # 这里原本有一整套内联 QSS（#1E1E1E 底 / #303033 描边 / #2F9CF4 主色 /
        # #55B2FF hover），与全局主题并存 = 两套真值。删掉后：
        # - 文本框走全局 QTextEdit 规则（surface_3 底、无描边、focus 才出边框）
        # - 两个按钮靠 variant 属性区分主次，由 polisher/全局 QSS 统一渲染
        main_layout.addWidget(self.text_edit)

        # 底部按钮区域
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        # 取消按钮
        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setProperty("variant", "secondary")

        # 确定按钮
        self.ok_btn = QPushButton("确定")
        self.ok_btn.setProperty("variant", "default")

        button_layout.addWidget(self.cancel_btn)
        button_layout.addWidget(self.ok_btn)

        main_layout.addLayout(button_layout)

        # 连接信号
        self.connect_signals()

    def connect_signals(self):
        """连接信号"""
        # 按钮信号
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

        # 文本实时改变信号
        self.text_edit.textChanged.connect(self.on_text_changed)

    def set_text_content(self, current_text):
        """设置文字内容 - 简化版"""
        self.current_text = current_text or ""
        self.text_edit.setPlainText(self.current_text)

    def on_text_changed(self):
        """文本内容改变时发出信号"""
        current_text = self.text_edit.toPlainText()
        self.text_changed.emit(current_text)

    def get_current_text(self):
        """获取当前文字"""
        return self.text_edit.toPlainText()