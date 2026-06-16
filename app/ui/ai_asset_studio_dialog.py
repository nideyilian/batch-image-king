"""Global AI API settings dialog."""

from __future__ import annotations

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class AIAssetStudioDialog(QDialog):
    """Configure shared API parameters used by layer-level AI generation."""

    SETTINGS_ORG = "批图王"
    SETTINGS_APP = "AIAssetStudio"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("AI接口设置")
        self.setModal(False)
        self.resize(560, 280)

        self._build_ui()
        self.load_settings()

    def settings(self) -> QSettings:
        return QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)

    def _build_ui(self):
        layout = QVBoxLayout(self)

        api_group = QGroupBox("接口参数")
        api_layout = QFormLayout(api_group)

        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("例如：https://api.example.com")
        self.endpoint_edit = QLineEdit()
        self.endpoint_edit.setPlaceholderText("例如：/v1/images/generations")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.default_model_edit = QLineEdit()
        self.default_model_edit.setPlaceholderText("例如：gpt-image-1 或 kling-v1")
        self.model_field_combo = QComboBox()
        self.model_field_combo.addItems(["model", "model_name"])

        api_layout.addRow("Base URL:", self.base_url_edit)
        api_layout.addRow("Endpoint:", self.endpoint_edit)
        api_layout.addRow("API Key:", self.api_key_edit)
        api_layout.addRow("默认模型:", self.default_model_edit)
        api_layout.addRow("模型字段:", self.model_field_combo)
        layout.addWidget(api_group)

        hint = QLabel("提示词、生成数量、处理方式位于每个图片图层的属性面板中。")
        hint.setStyleSheet("color: #8E8E93;")
        layout.addWidget(hint)

        button_layout = QHBoxLayout()
        self.save_button = QPushButton("保存")
        self.save_button.clicked.connect(self.save_settings)
        self.close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        self.close_buttons.rejected.connect(self.close)
        button_layout.addWidget(self.save_button)
        button_layout.addStretch()
        button_layout.addWidget(self.close_buttons)
        layout.addLayout(button_layout)

    def load_settings(self):
        settings = self.settings()
        self.base_url_edit.setText(str(settings.value("base_url", "") or ""))
        self.endpoint_edit.setText(str(settings.value("endpoint", "") or ""))
        self.api_key_edit.setText(str(settings.value("api_key", "") or ""))
        self.default_model_edit.setText(str(settings.value("default_model", "") or ""))
        model_field = str(settings.value("model_field", "model") or "model")
        index = self.model_field_combo.findText(model_field)
        if index >= 0:
            self.model_field_combo.setCurrentIndex(index)

    def save_settings(self):
        settings = self.settings()
        settings.setValue("base_url", self.base_url_edit.text().strip())
        settings.setValue("endpoint", self.endpoint_edit.text().strip())
        settings.setValue("api_key", self.api_key_edit.text())
        settings.setValue("default_model", self.default_model_edit.text().strip())
        settings.setValue("model_field", self.model_field_combo.currentText())
