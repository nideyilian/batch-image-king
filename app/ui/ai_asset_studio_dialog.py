"""Dialog for generating and importing AI image assets."""

from __future__ import annotations

import os
from typing import Optional

from PySide6.QtCore import QObject, QRunnable, QSettings, QThreadPool, Signal, Slot
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTextEdit,
    QVBoxLayout,
)

from app.services.ai_asset_service import AIAssetRequest, AIAssetResult, AIAssetService


class _WorkerSignals(QObject):
    finished = Signal(object)


class _GenerateAssetsTask(QRunnable):
    def __init__(self, service: AIAssetService, request: AIAssetRequest):
        super().__init__()
        self.service = service
        self.request = request
        self.signals = _WorkerSignals()

    @Slot()
    def run(self):
        result = self.service.generate_assets(self.request)
        self.signals.finished.emit(result)


class AIAssetStudioDialog(QDialog):
    SETTINGS_ORG = "批图王"
    SETTINGS_APP = "AIAssetStudio"

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.service = AIAssetService()
        self._running_task: Optional[_GenerateAssetsTask] = None
        self._last_result: Optional[AIAssetResult] = None
        self._last_output_dir = ""

        self.setWindowTitle("AI素材工坊")
        self.setModal(False)
        self.resize(760, 640)

        self._build_ui()
        self._load_settings()

    def _settings(self) -> QSettings:
        return QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        api_group = QGroupBox("API设置")
        api_layout = QFormLayout(api_group)
        self.base_url_edit = QLineEdit()
        self.endpoint_edit = QLineEdit()
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.model_edit = QLineEdit()
        self.model_field_combo = QComboBox()
        self.model_field_combo.addItems(["model", "model_name"])
        api_layout.addRow("Base URL:", self.base_url_edit)
        api_layout.addRow("Endpoint:", self.endpoint_edit)
        api_layout.addRow("API Key:", self.api_key_edit)
        api_layout.addRow("模型:", self.model_edit)
        api_layout.addRow("模型字段:", self.model_field_combo)
        layout.addWidget(api_group)

        prompt_group = QGroupBox("生成参数")
        prompt_layout = QFormLayout(prompt_group)
        self.prompt_edit = QTextEdit()
        self.prompt_edit.setAcceptRichText(False)
        self.prompt_edit.setFixedHeight(92)
        self.negative_prompt_edit = QTextEdit()
        self.negative_prompt_edit.setAcceptRichText(False)
        self.negative_prompt_edit.setFixedHeight(54)
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 20)
        self.size_combo = QComboBox()
        self.size_combo.addItems(["1024x1024", "768x1024", "1024x768", "512x512"])
        self.group_name_edit = QLineEdit()
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("仅生成", "raw")
        self.mode_combo.addItem("生成后基础抠图", "cutout")
        self.mode_combo.addItem("生成后基础抠图并自动分割", "segments")
        prompt_layout.addRow("提示词:", self.prompt_edit)
        prompt_layout.addRow("反向提示词:", self.negative_prompt_edit)
        prompt_layout.addRow("数量:", self.count_spin)
        prompt_layout.addRow("尺寸:", self.size_combo)
        prompt_layout.addRow("素材组:", self.group_name_edit)
        prompt_layout.addRow("处理模式:", self.mode_combo)
        layout.addWidget(prompt_group)

        result_group = QGroupBox("结果")
        result_layout = QVBoxLayout(result_group)
        self.status_label = QLabel("就绪")
        self.result_list = QListWidget()
        result_layout.addWidget(self.status_label)
        result_layout.addWidget(self.result_list, 1)
        layout.addWidget(result_group, 1)

        button_layout = QHBoxLayout()
        self.generate_button = QPushButton("生成")
        self.generate_button.clicked.connect(self.start_generation)
        self.import_button = QPushButton("导入为图片图层")
        self.import_button.setEnabled(False)
        self.import_button.clicked.connect(self.import_output_folder)
        self.close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.close_buttons.rejected.connect(self.close)
        button_layout.addWidget(self.generate_button)
        button_layout.addWidget(self.import_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_buttons)
        layout.addLayout(button_layout)

    def _load_settings(self):
        settings = self._settings()
        self.base_url_edit.setText(str(settings.value("base_url", "https://yunwu.ai") or ""))
        self.endpoint_edit.setText(str(settings.value("endpoint", "/v1/images/generations") or ""))
        self.api_key_edit.setText(str(settings.value("api_key", "") or ""))
        self.model_edit.setText(str(settings.value("model", "gpt-image-1") or ""))
        self.group_name_edit.setText(str(settings.value("group_name", "ai_assets") or ""))
        model_field = str(settings.value("model_field", "model") or "model")
        index = self.model_field_combo.findText(model_field)
        if index >= 0:
            self.model_field_combo.setCurrentIndex(index)

    def _save_settings(self):
        settings = self._settings()
        settings.setValue("base_url", self.base_url_edit.text().strip())
        settings.setValue("endpoint", self.endpoint_edit.text().strip())
        settings.setValue("api_key", self.api_key_edit.text())
        settings.setValue("model", self.model_edit.text().strip())
        settings.setValue("group_name", self.group_name_edit.text().strip())
        settings.setValue("model_field", self.model_field_combo.currentText())

    def build_request(self) -> AIAssetRequest:
        return AIAssetRequest(
            base_url=self.base_url_edit.text().strip(),
            endpoint=self.endpoint_edit.text().strip(),
            api_key=self.api_key_edit.text(),
            model=self.model_edit.text().strip(),
            model_field=self.model_field_combo.currentText(),
            prompt=self.prompt_edit.toPlainText().strip(),
            negative_prompt=self.negative_prompt_edit.toPlainText().strip(),
            count=self.count_spin.value(),
            size=self.size_combo.currentText(),
            group_name=self.group_name_edit.text().strip() or "ai_assets",
            process_mode=str(self.mode_combo.currentData() or "raw"),
        )

    def start_generation(self):
        request = self.build_request()
        if not request.base_url and not request.endpoint.startswith(("http://", "https://")):
            QMessageBox.warning(self, "参数缺失", "请填写 Base URL 或完整 Endpoint。")
            return
        if not request.endpoint:
            QMessageBox.warning(self, "参数缺失", "请填写 Endpoint。")
            return
        if not request.prompt:
            QMessageBox.warning(self, "参数缺失", "请填写提示词。")
            return

        self._save_settings()
        self.result_list.clear()
        self.status_label.setText("正在生成...")
        self.generate_button.setEnabled(False)
        self.import_button.setEnabled(False)

        task = _GenerateAssetsTask(self.service, request)
        task.signals.finished.connect(self._on_generation_finished)
        self._running_task = task
        QThreadPool.globalInstance().start(task)

    @Slot(object)
    def _on_generation_finished(self, result: AIAssetResult):
        self._last_result = result
        self._last_output_dir = self._resolve_output_dir(result)
        self.result_list.clear()

        for path in result.raw_paths:
            self.result_list.addItem(f"原图: {path}")
        for path in result.output_paths:
            self.result_list.addItem(f"输出: {path}")
        for error in result.errors:
            self.result_list.addItem(f"错误: {error}")
        if result.metadata_path:
            self.result_list.addItem(f"元数据: {result.metadata_path}")

        if result.raw_paths:
            self.status_label.setText(f"完成，输出目录: {self._last_output_dir}")
            self.import_button.setEnabled(bool(self._last_output_dir and self.document))
        else:
            self.status_label.setText("生成失败")
            self.import_button.setEnabled(False)
        self.generate_button.setEnabled(True)
        self._running_task = None

    def _resolve_output_dir(self, result: AIAssetResult) -> str:
        if result.output_paths:
            first = result.output_paths[0]
            if os.path.isfile(first) or os.path.splitext(first)[1]:
                return os.path.dirname(first)
            return first
        if result.raw_paths:
            return os.path.dirname(result.raw_paths[0])
        return ""

    def import_output_folder(self):
        if not self.document:
            QMessageBox.warning(self, "无法导入", "当前没有可用文档。")
            return
        if not self._last_output_dir:
            QMessageBox.warning(self, "无法导入", "没有可导入的素材目录。")
            return

        width = int(getattr(self.document, "canvas_width", getattr(self.document, "width", 800)) or 800)
        height = int(getattr(self.document, "canvas_height", getattr(self.document, "height", 600)) or 600)
        layer_name = f"AI素材-{self.group_name_edit.text().strip() or 'ai_assets'}"
        self.document.add_layer(layer_name, 0, 0, width, height, self._last_output_dir, False, True)
        self.status_label.setText(f"已导入为图片图层: {self._last_output_dir}")
