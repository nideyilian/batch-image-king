#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
简化版文字编辑对话框 - 类似创建文字图层弹窗的样式
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QTextEdit, QPushButton, QMessageBox)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class SimpleTextEditorDialog(QDialog):
    """简化版文字编辑器对话框"""

    text_changed = Signal(str)  # 文字内容改变信号
    text_list_changed = Signal(list)  # 文字列表改变信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_text = ""
        self.text_lines = []
        self.setWindowTitle("编辑文字")
        self.resize(500, 400)
        self.setup_ui()

    def setup_ui(self):
        """设置UI界面 - 简化版"""
        main_layout = QVBoxLayout(self)
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(16, 16, 16, 16)

        # 文字编辑区域
        main_layout.addWidget(QLabel("文字内容:"))

        self.text_edit = QTextEdit()
        self.text_edit.setFont(QFont("Microsoft YaHei", 12))
        self.text_edit.setPlaceholderText("请输入或编辑文字内容，支持多行...")
        self.text_edit.setMinimumHeight(200)
        main_layout.addWidget(self.text_edit)

        # 文字列表管理（简化版）
        list_label = QLabel("文字预设:")
        list_label.setStyleSheet("font-weight: bold; margin-top: 10px;")
        main_layout.addWidget(list_label)

        # 快速操作按钮
        button_layout = QHBoxLayout()
        button_layout.setSpacing(8)

        self.add_btn = QPushButton("添加当前文字")
        self.delete_btn = QPushButton("删除选中")
        self.random_btn = QPushButton("随机选择")

        # 设置按钮样式
        button_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                border: 1px solid #4a4a4a;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 12px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """

        for btn in [self.add_btn, self.delete_btn, self.random_btn]:
            btn.setStyleSheet(button_style)
            button_layout.addWidget(btn)

        button_layout.addStretch()
        main_layout.addLayout(button_layout)

        # 文字列表（简化显示）
        self.list_display = QTextEdit()
        self.list_display.setFont(QFont("Microsoft YaHei", 10))
        self.list_display.setPlaceholderText("文字预设列表将显示在这里...")
        self.list_display.setMaximumHeight(100)
        self.list_display.setReadOnly(True)
        main_layout.addWidget(self.list_display)

        # 底部按钮
        bottom_layout = QHBoxLayout()
        bottom_layout.addStretch()

        self.cancel_btn = QPushButton("取消")
        self.ok_btn = QPushButton("确定")

        # 设置主要按钮样式
        # 主色由 tokens_v2 统一控制，此处不再写死色值
        self.ok_btn.setProperty("variant", "primary")

        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                border: 1px solid #4a4a4a;
                padding: 8px 24px;
                border-radius: 4px;
                min-width: 80px;
                margin-right: 8px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #5a5a5a;
            }
            QPushButton:pressed {
                background-color: #2a2a2a;
            }
        """)

        bottom_layout.addWidget(self.cancel_btn)
        bottom_layout.addWidget(self.ok_btn)

        main_layout.addLayout(bottom_layout)

        # 连接信号
        self.connect_signals()

    def connect_signals(self):
        """连接信号"""
        # 列表操作
        self.add_btn.clicked.connect(self.add_current_text)
        self.delete_btn.clicked.connect(self.delete_selected_text)
        self.random_btn.clicked.connect(self.select_random_text)

        # 底部按钮
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def set_text_content(self, current_text, text_lines=None):
        """设置文字内容"""
        self.current_text = current_text or ""
        self.text_lines = text_lines or []

        # 更新编辑器
        self.text_edit.setPlainText(self.current_text)

        # 更新列表显示
        self.update_list_display()

    def update_list_display(self):
        """更新列表显示"""
        if not self.text_lines:
            self.list_display.setPlainText("暂无文字预设")
            return

        display_text = []
        for i, text in enumerate(self.text_lines, 1):
            # 高亮当前文字
            if text == self.current_text:
                display_text.append(f"★ {i}. {text}")
            else:
                display_text.append(f"  {i}. {text}")

        self.list_display.setPlainText("\n".join(display_text))

    def add_current_text(self):
        """添加当前文字到列表"""
        text = self.text_edit.toPlainText().strip()
        if not text:
            QMessageBox.information(self, "提示", "请先输入文字内容")
            return

        if text in self.text_lines:
            QMessageBox.information(self, "提示", "该文字已存在于列表中")
            return

        self.text_lines.append(text)
        self.update_list_display()
        self.text_list_changed.emit(self.text_lines)
        QMessageBox.information(self, "成功", "文字已添加到预设列表")

    def delete_selected_text(self):
        """删除选中的文字（简化版 - 删除当前文字）"""
        current_text = self.text_edit.toPlainText().strip()
        if not current_text:
            QMessageBox.information(self, "提示", "没有可删除的文字")
            return

        if current_text in self.text_lines:
            self.text_lines.remove(current_text)
            self.update_list_display()
            self.text_list_changed.emit(self.text_lines)
            QMessageBox.information(self, "成功", "文字已从预设列表删除")
        else:
            QMessageBox.information(self, "提示", "当前文字不在预设列表中")

    def select_random_text(self):
        """随机选择文字"""
        if not self.text_lines:
            QMessageBox.information(self, "提示", "预设列表为空，请先添加文字")
            return

        import random
        selected_text = random.choice(self.text_lines)
        self.text_edit.setPlainText(selected_text)
        self.current_text = selected_text
        self.update_list_display()
        self.text_changed.emit(selected_text)

    def get_current_text(self):
        """获取当前文字"""
        return self.text_edit.toPlainText().strip()

    def get_text_lines(self):
        """获取文字列表"""
        return self.text_lines.copy()