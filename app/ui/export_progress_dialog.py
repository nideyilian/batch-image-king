from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                            QPushButton, QProgressBar, QListWidget,
                            QDialogButtonBox, QMessageBox)
from PySide6.QtCore import Qt, QSize

class ExportProgressDialog(QDialog):
    """导出进度对话框"""

    def __init__(self, count, parent=None):
        """
        初始化进度对话框

        参数:
            count: 总导出数量
            parent: 父窗口
        """
        super().__init__(parent)

        self.count = count
        self.exported_count = 0
        self.export_thread = None

        self.setWindowTitle("导出进度")
        self.setMinimumSize(500, 400)
        self.setup_ui()

    def setup_ui(self):
        """设置界面"""
        layout = QVBoxLayout(self)

        # 标题
        title_label = QLabel(f"正在批量导出{self.count}个图像文件...")
        title_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(title_label)

        # 进度条
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        layout.addWidget(self.progress_bar)

        # 当前状态
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("当前状态:"))
        self.status_label = QLabel("准备导出...")
        self.status_label.setStyleSheet("font-weight: bold; color: #2F9CF4;")
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()
        layout.addLayout(status_layout)

        # 导出日志
        log_label = QLabel("导出日志:")
        layout.addWidget(log_label)

        self.log_list = QListWidget()
        self.log_list.setAlternatingRowColors(True)
        self.log_list.setMaximumHeight(200)
        layout.addWidget(self.log_list)

        # 按钮
        button_layout = QHBoxLayout()
        button_layout.addStretch()

        self.cancel_button = QPushButton("取消导出")
        self.cancel_button.clicked.connect(self.cancel_export)
        button_layout.addWidget(self.cancel_button)

        self.close_button = QPushButton("关闭")
        self.close_button.setEnabled(False)
        self.close_button.clicked.connect(self.accept)
        button_layout.addWidget(self.close_button)

        layout.addLayout(button_layout)

    def set_export_thread(self, thread):
        """设置导出线程"""
        self.export_thread = thread

        # 连接信号
        if self.export_thread:
            self.export_thread.progress_updated.connect(self.update_progress)
            self.export_thread.file_exported.connect(self.add_log)
            self.export_thread.export_completed.connect(self.export_finished)

    def update_progress(self, value):
        """更新进度条"""
        self.progress_bar.setValue(value)
        self.exported_count = int(value * self.count / 100)
        self.status_label.setText(f"已导出 {self.exported_count}/{self.count}")

    def add_log(self, message):
        """添加日志信息"""
        self.log_list.addItem(message)
        # 滚动到最底部
        self.log_list.scrollToBottom()

    def export_finished(self, success, message):
        """导出完成处理"""
        if success:
            self.progress_bar.setValue(100)
            self.status_label.setText(f"导出完成: {self.count}/{self.count}")
            self.status_label.setStyleSheet("font-weight: bold; color: green;")
        else:
            self.status_label.setText("导出失败或已取消")
            self.status_label.setStyleSheet("font-weight: bold; color: red;")

        self.add_log(message)
        self.cancel_button.setEnabled(False)
        self.close_button.setEnabled(True)

        if success:
            QMessageBox.information(self, "导出完成", message)

    def cancel_export(self):
        """取消导出操作"""
        # 防止重复弹窗
        if hasattr(self, '_canceling') and self._canceling:
            return

        if self.export_thread and self.export_thread.isRunning():
            self._canceling = True

            # 询问确认
            reply = QMessageBox.question(
                self, "确认取消",
                "确定要取消导出操作吗？已导出的文件不会被删除。",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)

            if reply == QMessageBox.Yes:
                self.export_thread.cancel()
                self.cancel_button.setEnabled(False)
                self.status_label.setText("正在取消导出...")
                self.add_log("用户取消了导出操作")
            else:
                # 用户选择不取消，重置标志
                self._canceling = False

    def closeEvent(self, event):
        """窗口关闭事件处理"""
        # 防止重复弹窗
        if hasattr(self, '_closing') and self._closing:
            event.accept()
            return

        if self.export_thread and self.export_thread.isRunning():
            self._closing = True

            # 如果线程还在运行，询问是否取消
            reply = QMessageBox.question(
                self, "确认关闭",
                "导出操作正在进行中，关闭窗口将取消导出。确定要关闭吗？",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No)

            if reply == QMessageBox.Yes:
                # 取消导出并关闭
                if hasattr(self.export_thread, 'cancel'):
                    self.export_thread.cancel()
                event.accept()
            else:
                # 用户选择不关闭，重置标志
                self._closing = False
                event.ignore()
        else:
            event.accept()