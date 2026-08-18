#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
集成化文字编辑对话框 - 包含内容管理功能
"""

from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                               QTextEdit, QPushButton, QListWidget, QListWidgetItem,
                               QSplitter, QWidget, QMessageBox, QInputDialog)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class IntegratedTextEditorDialog(QDialog):
    """集成化文字编辑器对话框"""

    text_changed = Signal(str)  # 文字内容改变信号
    text_list_changed = Signal(list)  # 文字列表改变信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_text = ""
        self.text_lines = []
        self.setWindowTitle("文字内容编辑器")
        self.resize(800, 600)
        self.setup_ui()

    def setup_ui(self):
        """设置UI界面"""
        main_layout = QHBoxLayout(self)

        # 创建分割器
        splitter = QSplitter(Qt.Horizontal)
        main_layout.addWidget(splitter)

        # 左侧：文字编辑区域
        edit_widget = QWidget()
        edit_layout = QVBoxLayout(edit_widget)

        # 当前文字编辑
        edit_layout.addWidget(QLabel("当前文字:"))
        self.text_edit = QTextEdit()
        self.text_edit.setFont(QFont("Microsoft YaHei", 12))
        self.text_edit.setPlaceholderText("请输入或编辑文字内容...")
        self.text_edit.setMinimumHeight(200)
        edit_layout.addWidget(self.text_edit)

        # 快速操作按钮
        quick_buttons_layout = QHBoxLayout()

        self.apply_btn = QPushButton("应用")
        self.apply_btn.setStyleSheet("""
            QPushButton {
                background-color: #1677ff;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #4096ff;
            }
        """)

        self.clear_btn = QPushButton("清空")
        self.clear_btn.setStyleSheet("""
            QPushButton {
                background-color: #ff4d4f;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #ff7875;
            }
        """)

        quick_buttons_layout.addWidget(self.apply_btn)
        quick_buttons_layout.addWidget(self.clear_btn)
        quick_buttons_layout.addStretch()

        edit_layout.addLayout(quick_buttons_layout)

        # 右侧：文字列表管理
        list_widget = QWidget()
        list_layout = QVBoxLayout(list_widget)

        list_layout.addWidget(QLabel("文字列表:"))

        self.text_list_widget = QListWidget()
        self.text_list_widget.setFont(QFont("Microsoft YaHei", 11))
        self.text_list_widget.setMinimumWidth(250)
        list_layout.addWidget(self.text_list_widget)

        # 列表操作按钮
        list_buttons_layout = QHBoxLayout()

        self.add_btn = QPushButton("添加")
        self.delete_btn = QPushButton("删除")
        self.random_btn = QPushButton("随机")
        self.cycle_btn = QPushButton("循环")

        # 设置按钮样式
        button_style = """
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                border: 1px solid #4a4a4a;
                padding: 6px 12px;
                border-radius: 3px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #5a5a5a;
            }
        """

        for btn in [self.add_btn, self.delete_btn, self.random_btn, self.cycle_btn]:
            btn.setStyleSheet(button_style)
            list_buttons_layout.addWidget(btn)

        list_layout.addLayout(list_buttons_layout)

        # 底部操作按钮
        bottom_buttons_layout = QHBoxLayout()

        self.ok_btn = QPushButton("确定")
        self.ok_btn.setStyleSheet("""
            QPushButton {
                background-color: #1677ff;
                color: white;
                border: none;
                padding: 8px 24px;
                border-radius: 4px;
                font-weight: bold;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4096ff;
            }
        """)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setStyleSheet("""
            QPushButton {
                background-color: #3a3a3a;
                color: white;
                border: 1px solid #4a4a4a;
                padding: 8px 24px;
                border-radius: 4px;
                min-width: 80px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #5a5a5a;
            }
        """)

        bottom_buttons_layout.addStretch()
        bottom_buttons_layout.addWidget(self.cancel_btn)
        bottom_buttons_layout.addWidget(self.ok_btn)

        list_layout.addLayout(bottom_buttons_layout)

        # 添加到分割器
        splitter.addWidget(edit_widget)
        splitter.addWidget(list_widget)
        splitter.setStretchFactor(0, 2)  # 编辑区域占2/3
        splitter.setStretchFactor(1, 1)  # 列表区域占1/3

        # 连接信号
        self.connect_signals()

    def connect_signals(self):
        """连接信号"""
        # 编辑区域
        self.apply_btn.clicked.connect(self.apply_current_text)
        self.clear_btn.clicked.connect(self.clear_current_text)

        # 列表操作
        self.add_btn.clicked.connect(self.add_text_item)
        self.delete_btn.clicked.connect(self.delete_selected_item)
        self.random_btn.clicked.connect(self.select_random_text)
        self.cycle_btn.clicked.connect(self.cycle_to_next_text)

        # 列表选择
        self.text_list_widget.itemClicked.connect(self.on_list_item_clicked)
        self.text_list_widget.itemDoubleClicked.connect(self.apply_list_item)

        # 底部按钮
        self.ok_btn.clicked.connect(self.accept)
        self.cancel_btn.clicked.connect(self.reject)

    def set_text_content(self, current_text, text_lines=None):
        """设置文字内容"""
        self.current_text = current_text or ""
        self.text_lines = text_lines or []

        # 更新编辑器
        self.text_edit.setPlainText(self.current_text)

        # 更新列表
        self.update_text_list()

        # 高亮当前文字在列表中的位置
        self.highlight_current_text()

    def update_text_list(self):
        """更新文字列表显示"""
        self.text_list_widget.clear()
        for text in self.text_lines:
            if text.strip():  # 只添加非空文本
                item = QListWidgetItem(text.strip())
                item.setData(Qt.UserRole, text)
                self.text_list_widget.addItem(item)

    def highlight_current_text(self):
        """高亮当前文字在列表中的位置"""
        if not self.current_text:
            return

        # 查找匹配的项
        for i in range(self.text_list_widget.count()):
            item = self.text_list_widget.item(i)
            if item and item.data(Qt.UserRole) == self.current_text:
                item.setSelected(True)
                self.text_list_widget.scrollToItem(item)
                break

    def apply_current_text(self):
        """应用当前编辑的文字"""
        text = self.text_edit.toPlainText().strip()
        self.current_text = text
        self.text_changed.emit(text)

        # 如果列表中没有这个文本，添加到列表
        if text and text not in self.text_lines:
            self.text_lines.append(text)
            self.update_text_list()
            self.text_list_changed.emit(self.text_lines)

    def clear_current_text(self):
        """清空当前文字"""
        self.text_edit.clear()
        self.current_text = ""
        self.text_changed.emit("")

    def add_text_item(self):
        """添加新的文字项"""
        text, ok = QInputDialog.getText(self, "添加文字", "请输入新的文字内容:")
        if ok and text.strip():
            if text.strip() not in self.text_lines:
                self.text_lines.append(text.strip())
                self.update_text_list()
                self.text_list_changed.emit(self.text_lines)

    def delete_selected_item(self):
        """删除选中的文字项"""
        current_item = self.text_list_widget.currentItem()
        if not current_item:
            QMessageBox.information(self, "提示", "请先选择要删除的文字项")
            return

        text = current_item.data(Qt.UserRole)
        reply = QMessageBox.question(
            self, "确认删除", f"确定要删除文字 '{text}' 吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes and text in self.text_lines:
            self.text_lines.remove(text)

            # 如果删除的是当前文字，需要更新
            if self.current_text == text:
                self.current_text = self.text_lines[0] if self.text_lines else ""
                self.text_edit.setPlainText(self.current_text)
                self.text_changed.emit(self.current_text)

            self.update_text_list()
            self.text_list_changed.emit(self.text_lines)

    def select_random_text(self):
        """随机选择一个文字"""
        import random
        if not self.text_lines:
            QMessageBox.information(self, "提示", "文字列表为空")
            return

        # 确保随机选择不同的文本（如果可能）
        available_texts = [text for text in self.text_lines if text != self.current_text]
        if not available_texts and len(self.text_lines) == 1:
            available_texts = self.text_lines

        if available_texts:
            self.current_text = random.choice(available_texts)
            self.text_edit.setPlainText(self.current_text)
            self.highlight_current_text()
            self.text_changed.emit(self.current_text)

    def cycle_to_next_text(self):
        """循环到下一个文字"""
        if not self.text_lines:
            QMessageBox.information(self, "提示", "文字列表为空")
            return

        if len(self.text_lines) == 1:
            return

        # 找到当前文本的位置
        try:
            current_index = self.text_lines.index(self.current_text)
            next_index = (current_index + 1) % len(self.text_lines)
        except ValueError:
            # 如果当前文本不在列表中，从第一个开始
            next_index = 0

        self.current_text = self.text_lines[next_index]
        self.text_edit.setPlainText(self.current_text)
        self.highlight_current_text()
        self.text_changed.emit(self.current_text)

    def on_list_item_clicked(self, item):
        """列表项被点击"""
        if item:
            text = item.data(Qt.UserRole)
            self.text_edit.setPlainText(text)

    def apply_list_item(self, item):
        """双击列表项应用文字"""
        if item:
            text = item.data(Qt.UserRole)
            self.current_text = text
            self.text_edit.setPlainText(text)
            self.text_changed.emit(text)

    def get_current_text(self):
        """获取当前文字"""
        return self.current_text

    def get_text_lines(self):
        """获取文字列表"""
        return self.text_lines.copy()