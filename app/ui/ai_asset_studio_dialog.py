"""Manage AI provider profiles and their available image models."""

from __future__ import annotations

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
    QVBoxLayout,
)

from app.services.ai_asset_service import AIAssetService
from app.services.ai_provider_config import AIProviderProfile, AIProviderStore


class _ModelFetchSignals(QObject):
    finished = Signal(object, str)


class _ModelFetchTask(QRunnable):
    def __init__(self, profile: AIProviderProfile):
        super().__init__()
        self.profile = profile
        self.signals = _ModelFetchSignals()

    @Slot()
    def run(self):
        try:
            models = AIAssetService().fetch_models(
                self.profile.base_url,
                self.profile.models_endpoint,
                self.profile.api_key,
                self.profile.auth_mode,
            )
            self.signals.finished.emit(models, "")
        except Exception as exc:
            self.signals.finished.emit([], str(exc))


class AIAssetStudioDialog(QDialog):
    SETTINGS_ORG = "批图王"
    SETTINGS_APP = "AIAssetStudio"

    def __init__(self, parent=None):
        super().__init__(parent)
        self.store = AIProviderStore(QSettings(self.SETTINGS_ORG, self.SETTINGS_APP))
        self.profiles = self.store.load_profiles()
        self._fetch_task = None

        self.setWindowTitle("AI接口设置")
        self.setModal(False)
        self.resize(680, 610)

        self._build_ui()
        self.refresh_profile_choices()

    def _build_ui(self):
        layout = QVBoxLayout(self)

        profile_row = QHBoxLayout()
        self.profile_combo = QComboBox()
        self.profile_combo.currentIndexChanged.connect(self.load_selected_profile)
        self.add_profile_btn = QPushButton("新增接口")
        self.add_profile_btn.clicked.connect(lambda: self.add_profile())
        self.delete_profile_btn = QPushButton("删除接口")
        self.delete_profile_btn.clicked.connect(self.delete_current_profile)
        profile_row.addWidget(QLabel("接口:"))
        profile_row.addWidget(self.profile_combo, 1)
        profile_row.addWidget(self.add_profile_btn)
        profile_row.addWidget(self.delete_profile_btn)
        layout.addLayout(profile_row)

        api_group = QGroupBox("接口参数")
        api_layout = QFormLayout(api_group)
        self.profile_name_edit = QLineEdit()
        self.base_url_edit = QLineEdit()
        self.base_url_edit.setPlaceholderText("例如：https://api.example.com")
        self.generation_endpoint_edit = QLineEdit()
        self.generation_endpoint_edit.setPlaceholderText("/v1/images/generations")
        self.models_endpoint_edit = QLineEdit()
        self.models_endpoint_edit.setPlaceholderText("/v1/models")
        self.api_key_edit = QLineEdit()
        self.api_key_edit.setEchoMode(QLineEdit.Password)
        self.auth_mode_combo = QComboBox()
        self.auth_mode_combo.addItem("Bearer Token", "bearer")
        self.auth_mode_combo.addItem("x-api-key", "x-api-key")
        self.auth_mode_combo.addItem("无需认证", "none")
        self.model_field_combo = QComboBox()
        self.model_field_combo.addItems(["model", "model_name"])

        api_layout.addRow("配置名称:", self.profile_name_edit)
        api_layout.addRow("Base URL:", self.base_url_edit)
        api_layout.addRow("生图 Endpoint:", self.generation_endpoint_edit)
        api_layout.addRow("模型 Endpoint:", self.models_endpoint_edit)
        api_layout.addRow("API Key:", self.api_key_edit)
        api_layout.addRow("认证方式:", self.auth_mode_combo)
        api_layout.addRow("模型字段:", self.model_field_combo)
        layout.addWidget(api_group)

        models_group = QGroupBox("可用模型")
        models_layout = QVBoxLayout(models_group)
        self.models_list = QListWidget()
        models_layout.addWidget(self.models_list)

        custom_row = QHBoxLayout()
        self.custom_model_edit = QLineEdit()
        self.custom_model_edit.setPlaceholderText("输入模型 ID")
        self.custom_model_edit.returnPressed.connect(self.add_custom_model)
        self.add_model_btn = QPushButton("添加模型")
        self.add_model_btn.clicked.connect(self.add_custom_model)
        self.remove_model_btn = QPushButton("删除选中")
        self.remove_model_btn.clicked.connect(self.remove_selected_model)
        custom_row.addWidget(self.custom_model_edit, 1)
        custom_row.addWidget(self.add_model_btn)
        custom_row.addWidget(self.remove_model_btn)
        models_layout.addLayout(custom_row)

        fetch_row = QHBoxLayout()
        self.fetch_models_btn = QPushButton("自动拉取模型")
        self.fetch_models_btn.clicked.connect(self.fetch_models)
        self.fetch_status_label = QLabel("")
        self.fetch_status_label.setStyleSheet("color: #8E8E93;")
        fetch_row.addWidget(self.fetch_models_btn)
        fetch_row.addWidget(self.fetch_status_label, 1)
        models_layout.addLayout(fetch_row)
        layout.addWidget(models_group, 1)

        buttons = QHBoxLayout()
        self.save_button = QPushButton("保存当前接口")
        self.save_button.clicked.connect(self.save_current_profile)
        close_buttons = QDialogButtonBox(QDialogButtonBox.Close)
        close_buttons.rejected.connect(self.close)
        buttons.addWidget(self.save_button)
        buttons.addStretch()
        buttons.addWidget(close_buttons)
        layout.addLayout(buttons)

    def refresh_profile_choices(self, selected_id: str = ""):
        active_id = selected_id or self.store.active_profile_id()
        self.profile_combo.blockSignals(True)
        self.profile_combo.clear()
        for profile in self.profiles:
            self.profile_combo.addItem(profile.name, profile.profile_id)
        index = self.profile_combo.findData(active_id)
        self.profile_combo.setCurrentIndex(index if index >= 0 else (0 if self.profiles else -1))
        self.profile_combo.blockSignals(False)
        self.load_selected_profile()

    def add_profile(self, name: str = ""):
        profile = AIProviderProfile(
            profile_id="",
            name=name or f"接口 {len(self.profiles) + 1}",
        )
        self.profiles.append(profile)
        self.store.save_profiles(self.profiles, profile.profile_id)
        self.refresh_profile_choices(profile.profile_id)
        return profile

    def delete_current_profile(self):
        profile = self.current_profile()
        if not profile:
            return
        self.profiles = [item for item in self.profiles if item.profile_id != profile.profile_id]
        self.store.save_profiles(self.profiles)
        self.refresh_profile_choices()

    def current_profile(self):
        profile_id = self.profile_combo.currentData()
        return next((profile for profile in self.profiles if profile.profile_id == profile_id), None)

    def load_selected_profile(self):
        profile = self.current_profile()
        enabled = profile is not None
        for widget in (
            self.profile_name_edit,
            self.base_url_edit,
            self.generation_endpoint_edit,
            self.models_endpoint_edit,
            self.api_key_edit,
            self.auth_mode_combo,
            self.model_field_combo,
            self.models_list,
            self.custom_model_edit,
            self.add_model_btn,
            self.remove_model_btn,
            self.fetch_models_btn,
            self.save_button,
            self.delete_profile_btn,
        ):
            widget.setEnabled(enabled)
        if not profile:
            self._clear_fields()
            return

        self.profile_name_edit.setText(profile.name)
        self.base_url_edit.setText(profile.base_url)
        self.generation_endpoint_edit.setText(profile.generation_endpoint)
        self.models_endpoint_edit.setText(profile.models_endpoint)
        self.api_key_edit.setText(profile.api_key)
        auth_index = self.auth_mode_combo.findData(profile.auth_mode)
        self.auth_mode_combo.setCurrentIndex(max(0, auth_index))
        model_field_index = self.model_field_combo.findText(profile.model_field)
        self.model_field_combo.setCurrentIndex(max(0, model_field_index))
        self._set_models(profile.models)

    def _clear_fields(self):
        for edit in (
            self.profile_name_edit,
            self.base_url_edit,
            self.generation_endpoint_edit,
            self.models_endpoint_edit,
            self.api_key_edit,
            self.custom_model_edit,
        ):
            edit.clear()
        self.models_list.clear()
        self.fetch_status_label.clear()

    def _set_models(self, models):
        self.models_list.clear()
        for model in models:
            self.models_list.addItem(model)

    def _models_from_list(self):
        return [self.models_list.item(index).text() for index in range(self.models_list.count())]

    def _update_profile_from_fields(self, profile: AIProviderProfile):
        profile.name = self.profile_name_edit.text().strip() or "未命名接口"
        profile.base_url = self.base_url_edit.text().strip()
        profile.generation_endpoint = self.generation_endpoint_edit.text().strip()
        profile.models_endpoint = self.models_endpoint_edit.text().strip()
        profile.api_key = self.api_key_edit.text()
        profile.auth_mode = str(self.auth_mode_combo.currentData() or "bearer")
        profile.model_field = self.model_field_combo.currentText()
        profile.models = list(dict.fromkeys(self._models_from_list()))

    def save_current_profile(self):
        profile = self.current_profile()
        if not profile:
            profile = self.add_profile()
        self._update_profile_from_fields(profile)
        self.store.save_profiles(self.profiles, profile.profile_id)
        self.refresh_profile_choices(profile.profile_id)

    def add_custom_model(self, model: str = ""):
        value = (model or self.custom_model_edit.text()).strip()
        if not value:
            return
        existing = set(self._models_from_list())
        if value not in existing:
            self.models_list.addItem(value)
        self.custom_model_edit.clear()

    def remove_selected_model(self):
        row = self.models_list.currentRow()
        if row >= 0:
            self.models_list.takeItem(row)

    def fetch_models(self):
        profile = self.current_profile()
        if not profile:
            return
        self._update_profile_from_fields(profile)
        if not profile.base_url and not profile.models_endpoint.startswith(("http://", "https://")):
            QMessageBox.warning(self, "参数缺失", "请填写 Base URL 或完整模型 Endpoint。")
            return
        if not profile.models_endpoint:
            QMessageBox.warning(self, "参数缺失", "请填写模型 Endpoint。")
            return

        self.fetch_models_btn.setEnabled(False)
        self.fetch_status_label.setText("正在拉取...")
        task = _ModelFetchTask(profile)
        task.signals.finished.connect(self._on_models_fetched)
        self._fetch_task = task
        QThreadPool.globalInstance().start(task)

    @Slot(object, str)
    def _on_models_fetched(self, models, error):
        self.fetch_models_btn.setEnabled(True)
        self._fetch_task = None
        if error:
            self.fetch_status_label.setText(f"拉取失败: {error}")
            return
        merged = list(dict.fromkeys(self._models_from_list() + list(models or [])))
        self._set_models(merged)
        self.fetch_status_label.setText(f"已拉取 {len(models or [])} 个模型")
        self.save_current_profile()
