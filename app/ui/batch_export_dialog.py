from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QSpinBox, QLineEdit, QFormLayout,
                           QFileDialog, QDialogButtonBox, QComboBox, QCheckBox, QGroupBox, QMessageBox,
                           QInputDialog, QListWidget, QProgressBar, QListWidgetItem, QAbstractItemView, QWidget, QGridLayout,
                           QDoubleSpinBox)
from PySide6.QtCore import Qt, QMetaObject, Q_ARG, Slot, QTimer, QSettings, QRunnable, QThreadPool
import shiboken6
import datetime
import re
import os
import json
import time

from app.ui.batch_export_dialog_settings import BatchExportDialogSettingsMixin
from app.ui.batch_export_dialog_ui import BatchExportDialogUiMixin
from app.ui.batch_export_dialog_progress import BatchExportDialogProgressMixin

class BatchExportDialog(QDialog, BatchExportDialogSettingsMixin, BatchExportDialogUiMixin, BatchExportDialogProgressMixin):
    """批量导出对话框"""

    SETTINGS_ORG = "批图王"
    SETTINGS_APP = "BatchExportDialog"
    SETTINGS_KEY = "last_settings"

    def __init__(self, document, parent=None):
        super().__init__(parent)

        self.document = document
        self._host_parent = parent
        self.directory = document.export_settings.get('last_directory', "")

        # 初始化取消标志
        self.export_canceled = False
        self._export_running = False
        self._export_total_count = 0
        self._export_started_at = None
        self._last_exported_file_hint = ""
        self._progress_phase_hint = "准备导出"
        self._last_dynamic_budget_recommendation = None
        self._export_trace_path_announced = False
        self._updating_current_date_path = False
        self._progress_refresh_timer = QTimer(self)
        self._progress_refresh_timer.setInterval(500)
        self._progress_refresh_timer.timeout.connect(self._refresh_progress_display)

        self.setWindowTitle("批量导出图像")
        self.setMinimumWidth(760)

        self.setup_ui()
        self.load_settings()  # 加载上一次的设置

        # 注意：不要在这里调用super().accept()
        # 导出完成后会在export_completed中调用

        # 不立即结束UI：等待后台线程实际停止后再统一走 export_completed

    def get_traverse_mode(self):
        """获取当前是否为遍历模式"""
        return self.traverse_export_check.isChecked()
