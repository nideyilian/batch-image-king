import os
import re

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QFormLayout, QLineEdit, QListWidget, QMessageBox, QDialogButtonBox,
    QGroupBox, QProgressDialog, QApplication
)
from PySide6.QtCore import Qt

from app.ui.tokens_v2 import Color
from app.ui.design_spec import FontSize, Space as _Space
from app.ui.batch_export_dialog import BatchExportDialog
from app.utils.preset_document_loader import documents_from_preset_data


class PresetRunDialog(QDialog):
    """Confirm and run a preset without loading it into the editor."""

    def __init__(self, preset_manager, preset_id, parent=None):
        super().__init__(parent)
        self.preset_manager = preset_manager
        self.preset_id = preset_id
        self.preset_data = self.preset_manager.load_preset(preset_id)
        self.summary = self.preset_manager.get_preset_summary(preset_id) or {}
        self.documents = documents_from_preset_data(self.preset_data, parent=None)

        self.setWindowTitle("运行预设")
        self.setMinimumWidth(560)
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(_Space.SM)

        title = QLabel(self.summary.get('name', '未命名预设'))
        title.setStyleSheet(f"font-size: {FontSize.LG}px; font-weight: bold;")
        layout.addWidget(title)

        desc = QLabel(self.summary.get('description', '') or "将按预设中保存的批量导出设置运行。")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {Color.text_secondary};")
        layout.addWidget(desc)

        info_group = QGroupBox("导出摘要")
        info_layout = QFormLayout(info_group)
        settings = self.summary.get('export_settings') or {}
        info_layout.addRow("标签页:", QLabel(str(self.summary.get('document_count', len(self.documents)))))
        info_layout.addRow("画布:", QLabel(" / ".join(self.summary.get('canvas_sizes', [])) or "未知"))
        info_layout.addRow("数量:", QLabel(str(settings.get('count', 10))))
        info_layout.addRow("格式:", QLabel(self._format_name(settings.get('format_index', 1))))
        info_layout.addRow("质量策略:", QLabel(str(settings.get('export_quality_profile', 'quality'))))
        layout.addWidget(info_group)

        output_row = QHBoxLayout()
        self.output_edit = QLineEdit()
        self.output_edit.setPlaceholderText("选择导出目录...")
        default_dir = self._resolve_default_output_dir()
        if default_dir:
            self.output_edit.setText(default_dir)
        output_row.addWidget(QLabel("输出目录:"))
        output_row.addWidget(self.output_edit, 1)
        browse_btn = QPushButton("浏览")
        browse_btn.clicked.connect(self.choose_output_dir)
        output_row.addWidget(browse_btn)
        layout.addLayout(output_row)

        docs_group = QGroupBox("包含的标签页")
        docs_layout = QVBoxLayout(docs_group)
        self.docs_list = QListWidget()
        for index, document in enumerate(self.documents):
            name = getattr(document, 'original_tab_name', '') or getattr(document, 'tab_name', '') or f"标签页 {index + 1}"
            settings = getattr(document, 'export_settings', {}) or {}
            count = settings.get('count', 10)
            self.docs_list.addItem(f"{name}  |  {document.canvas_width}x{document.canvas_height}  |  {count} 张")
        docs_layout.addWidget(self.docs_list)
        layout.addWidget(docs_group)

        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.button(QDialogButtonBox.Ok).setText("开始运行")
        self.button_box.button(QDialogButtonBox.Cancel).setText("取消")
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        layout.addWidget(self.button_box)

    def choose_output_dir(self):
        directory = QFileDialog.getExistingDirectory(self, "选择导出目录", self.output_edit.text())
        if directory:
            self.output_edit.setText(directory)

    def run_exports(self):
        output_dir = self.output_edit.text().strip()
        if not output_dir:
            QMessageBox.warning(self, "运行预设", "请选择导出目录")
            return False

        try:
            os.makedirs(output_dir, exist_ok=True)
        except Exception as exc:
            QMessageBox.warning(self, "运行预设", f"无法创建导出目录: {exc}")
            return False

        if not self.documents:
            QMessageBox.warning(self, "运行预设", "预设中没有可导出的标签页")
            return False

        progress = QProgressDialog("正在运行预设...", "取消", 0, len(self.documents), self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)

        all_ok = True
        for index, document in enumerate(self.documents):
            if progress.wasCanceled():
                all_ok = False
                break
            name = getattr(document, 'original_tab_name', '') or getattr(document, 'tab_name', '') or f"标签页 {index + 1}"
            progress.setLabelText(f"正在导出：{name}")
            progress.setValue(index)
            QApplication.processEvents()

            doc_output_dir = output_dir
            if len(self.documents) > 1:
                doc_output_dir = os.path.join(output_dir, self._safe_name(name))
                os.makedirs(doc_output_dir, exist_ok=True)

            document.export_settings['last_directory'] = doc_output_dir
            dialog = BatchExportDialog(document, self)
            dialog.directory = doc_output_dir
            if hasattr(dialog, 'path_edit'):
                dialog.path_edit.setText(doc_output_dir)
            ok = dialog.do_export()
            dialog.deleteLater()
            if not ok:
                all_ok = False
                break

        progress.setValue(len(self.documents))
        if all_ok:
            self.preset_manager.touch_preset_used(self.preset_id)
            QMessageBox.information(self, "运行预设", "预设导出已完成。")
        else:
            QMessageBox.warning(self, "运行预设", "预设导出未完成，请检查导出设置或素材路径。")
        return all_ok

    def _resolve_default_output_dir(self):
        for document in self.documents:
            directory = (getattr(document, 'export_settings', {}) or {}).get('last_directory', '')
            if directory:
                return directory
        return ''

    def _format_name(self, format_index):
        return {0: 'PNG', 1: 'JPEG', 2: 'BMP'}.get(int(format_index or 1), 'JPEG')

    def _safe_name(self, name):
        safe = re.sub(r'[<>:"/\\\\|?*]', '_', str(name)).strip()
        return safe[:50] or "tab"
