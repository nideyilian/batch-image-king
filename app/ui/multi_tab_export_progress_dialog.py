from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QProgressBar, QListWidget, QListWidgetItem,
                           QSplitter, QWidget, QMessageBox, QTableWidget,
                           QTableWidgetItem, QHeaderView)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QFont, QIcon, QColor, QBrush
import os

class MultiTabExportProgressDialog(QDialog):
    """多标签页批量导出进度对话框"""

    def __init__(self, total_count, parent=None):
        super().__init__(parent)

        self.total_count = total_count
        self.export_thread = None
        self.current_tab_index = -1
        self.current_tab_name = ""
        self.started = False

        # 设置对话框属性
        self.setWindowTitle("多标签页导出进度")
        self.setMinimumSize(500, 350)
        self.setModal(True)

        # 设置全局样式
        self.setStyleSheet("""
            QLabel { font-weight: bold; }
            QProgressBar { border: 1px solid #aaa; text-align: center; }
            QProgressBar::chunk { background-color: #4CAF50; }
        """)

        self.setup_ui()

    def setup_ui(self):
        """设置UI"""
        layout = QVBoxLayout(self)

        # 当前标签页信息
        self.tab_info = QLabel("准备导出...")
        self.tab_info.setStyleSheet("font-weight: bold; font-size: 12pt;")
        layout.addWidget(self.tab_info)

        # 当前目录
        self.dir_label = QLabel("输出目录: 等待开始...")
        layout.addWidget(self.dir_label)

        # 标签页表格（显示导出进度）
        self.tabs_table = QTableWidget()
        self.tabs_table.setColumnCount(3)
        self.tabs_table.setHorizontalHeaderLabels(["标签页", "状态", "目录"])
        self.tabs_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self.tabs_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self.tabs_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self.tabs_table.horizontalHeader().setStyleSheet("QHeaderView::section { font-weight: bold; }")
        layout.addWidget(self.tabs_table)

        # 总进度信息
        self.progress_info = QLabel(f"总进度: 0/{self.total_count}")
        layout.addWidget(self.progress_info)

        # 总进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setMinimum(0)
        self.progress_bar.setMaximum(self.total_count)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 取消按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch(1)

        self.cancel_button = QPushButton("取消")
        self.cancel_button.clicked.connect(self.cancel_export)
        button_layout.addWidget(self.cancel_button)

        layout.addLayout(button_layout)

    def set_export_thread(self, thread):
        """设置导出线程并连接信号"""
        self.export_thread = thread

        # 连接信号
        if self.export_thread:
            self.export_thread.progress_updated.connect(self.update_progress)
            self.export_thread.tab_progress_updated.connect(self.update_tab_progress)
            self.export_thread.export_completed.connect(self.handle_completion)

            # 准备表格
            self.prepare_tabs_table()

            # 启动线程
            self.started = True
            self.export_thread.start()

    def prepare_tabs_table(self):
        """准备标签页表格"""
        if not self.export_thread:
            return

        # 获取设置中的所有标签页信息
        selected_tabs = self.export_thread.settings['selected_tabs']

        # 设置表格行数
        self.tabs_table.setRowCount(len(selected_tabs))

        # 填充表格
        for i, tab_info in enumerate(selected_tabs):
            tab_name = tab_info['name']
            document = tab_info['document']

            # 标签页名称
            name_item = QTableWidgetItem(tab_name)
            self.tabs_table.setItem(i, 0, name_item)

            # 状态
            status_item = QTableWidgetItem("等待...")
            self.tabs_table.setItem(i, 1, status_item)

            # 获取导出目录信息
            dir_path = document.export_settings.get('last_directory', '') if hasattr(document, 'export_settings') else ''
            if not dir_path:
                dir_path = os.path.join(os.path.expanduser("~"), "Pictures", "模块批量出图")

            # 添加子文件夹
            subfolder_path = os.path.join(dir_path, tab_name)

            # 目录
            dir_item = QTableWidgetItem(subfolder_path)
            self.tabs_table.setItem(i, 2, dir_item)

    def update_progress(self, current, total):
        """更新总进度"""
        self.progress_bar.setValue(current)
        self.progress_info.setText(f"总进度: {current}/{total}")

    def update_tab_progress(self, tab_index, tab_name):
        """更新当前处理的标签页信息"""
        self.current_tab_index = tab_index
        self.current_tab_name = tab_name

        # 更新标签页信息
        self.tab_info.setText(f"正在处理: {tab_name}")

        # 获取标签页的目录信息
        if self.export_thread:
            selected_tabs = self.export_thread.settings['selected_tabs']
            tab_info = next((tab for tab in selected_tabs if tab['index'] == tab_index), None)

            if tab_info:
                # 更新表格中的状态
                for i in range(self.tabs_table.rowCount()):
                    name_item = self.tabs_table.item(i, 0)
                    if name_item and name_item.text() == tab_name:
                        status_item = self.tabs_table.item(i, 1)
                        if status_item:
                            status_item.setText("正在导出")
                            # 使用蓝色文本代替绿色
                            status_item.setForeground(QBrush(QColor("#2F9CF4")))
                            # 高亮显示当前处理的行
                            for col in range(self.tabs_table.columnCount()):
                                item = self.tabs_table.item(i, col)
                                if item:
                                    item.setBackground(QBrush(QColor(230, 240, 250)))  # 浅蓝色背景
                                    item.setForeground(QBrush(QColor("#2F9CF4")))  # 深蓝色文本

                # 显示当前目录
                document = tab_info['document']
                dir_path = document.export_settings.get('last_directory', '') if hasattr(document, 'export_settings') else ''
                if not dir_path:
                    dir_path = os.path.join(os.path.expanduser("~"), "Pictures", "模块批量出图")

                # 添加子文件夹
                dir_path = os.path.join(dir_path, tab_name)

                self.dir_label.setText(f"输出目录: {dir_path}")

    def handle_completion(self, success, message):
        """处理导出完成事件"""
        if success:
            # 更新所有标签页的状态为已完成
            for i in range(self.tabs_table.rowCount()):
                status_item = self.tabs_table.item(i, 1)
                if status_item:
                    if status_item.text() != "正在导出":
                        status_item.setText("已完成")

            # 更新当前处理的标签页状态
            self.tab_info.setText("导出完成")

            # 显示成功消息
            QMessageBox.information(self, "导出完成", message)
            self.accept()
        else:
            # 显示错误消息
            QMessageBox.warning(self, "导出错误", message)
            self.reject()

    def cancel_export(self):
        """取消导出操作"""
        # 防止重复弹窗
        if hasattr(self, '_canceling') and self._canceling:
            return

        if self.export_thread and self.started:
            self._canceling = True

            reply = QMessageBox.question(
                self, "确认取消",
                "确定要取消导出操作吗？已导出的文件将保留。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.export_thread.cancel()
                # 不要立即关闭对话框，等待线程处理取消事件
            else:
                # 用户选择不取消，重置标志
                self._canceling = False
        else:
            self.reject()

    def closeEvent(self, event):
        """关闭窗口事件处理"""
        # 防止重复弹窗
        if hasattr(self, '_closing') and self._closing:
            event.accept()
            return

        if self.export_thread and self.started and not self.export_thread.isFinished():
            self._closing = True

            reply = QMessageBox.question(
                self, "确认关闭",
                "导出操作正在进行中，关闭窗口将取消导出。确定要关闭吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )

            if reply == QMessageBox.Yes:
                self.export_thread.cancel()
                event.accept()
            else:
                # 用户选择不关闭，重置标志
                self._closing = False
                event.ignore()
        else:
            event.accept()