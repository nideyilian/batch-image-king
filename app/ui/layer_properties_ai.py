from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                               QPushButton, QSpinBox, QDoubleSpinBox, QLineEdit, QFormLayout,
                               QFileDialog, QGroupBox, QCheckBox, QComboBox,
                               QSlider, QMessageBox, QRadioButton, QButtonGroup,
                               QScrollArea, QFrame, QSizePolicy,
                               QMenu, QMainWindow, QDockWidget, QApplication, QTextEdit,
                               QProgressBar)
from PySide6.QtCore import Qt, Slot, Signal, QTimer, QSettings, QObject, QRunnable, QThreadPool
from PySide6.QtGui import QColor
import os
import time
from PIL import Image

try:
    from app.models.document_blend import BlendMode
    HAS_BLEND_MODE = True
except ImportError:
    HAS_BLEND_MODE = False

from app.ui.layer_transform_widget import LayerTransformWidget
from app.ui.collapsible_group import CollapsibleGroupBox
from app.ui.color_picker_dialog_a2 import get_color_a2
from app.ui.shaped_layer_panel import ShapePreviewWidget, ShapeType as PreviewShapeType
from app.ui.dark_theme import CursorDarkTheme
from app.utils.layer_tree import is_layer_group
from app.services.ai_asset_service import (
    AIAssetRequest,
    AIAssetResult,
    AIAssetService,
    localize_ai_error,
)
from app.services.ai_provider_config import AIProviderStore


class LayerPropertiesAi(object):
    """Mixin for layer_properties_ai (split from LayerPropertiesPanel)."""

    def _ai_settings(self):
        return QSettings("批图王", "AIAssetStudio")

    def _ai_provider_store(self):
        return AIProviderStore(self._ai_settings())

    def build_ai_asset_request_for_current_layer(self):
        profile = self._ai_provider_store().active_profile()
        if profile is None:
            raise ValueError("未配置 AI 接口")
        if not profile.selected_model:
            raise ValueError("请先在 AI接口设置 中选择当前模型")
        layer_name = getattr(self.current_layer, "name", "ai_assets") or "ai_assets"
        return AIAssetRequest(
            base_url=profile.base_url,
            endpoint=profile.generation_endpoint,
            api_key=profile.api_key,
            model=profile.selected_model,
            model_field=profile.model_field,
            auth_mode=profile.auth_mode,
            prompt=self.ai_prompt_edit.toPlainText().strip(),
            negative_prompt=self.ai_negative_prompt_edit.toPlainText().strip(),
            count=self.ai_count_spin.value(),
            size=self.ai_size_combo.currentText(),
            group_name=layer_name,
            process_mode=str(self.ai_mode_combo.currentData() or "raw"),
        )

    def start_ai_generation_for_current_layer(self):
        if not self.current_layer:
            QMessageBox.warning(self, "无法生成", "请先选择一个图片图层。")
            return

        try:
            request = self.build_ai_asset_request_for_current_layer()
        except ValueError as exc:
            QMessageBox.warning(self, "参数缺失", str(exc))
            return
        if not request.base_url and not request.endpoint.startswith(("http://", "https://")):
            QMessageBox.warning(self, "参数缺失", "请在当前接口配置中填写 Base URL。")
            return
        if not request.endpoint:
            QMessageBox.warning(self, "参数缺失", "请在当前接口配置中填写生图 Endpoint。")
            return
        if not request.model:
            QMessageBox.warning(self, "参数缺失", "请选择或输入一个模型 ID。")
            return
        if not request.prompt:
            QMessageBox.warning(self, "参数缺失", "请填写当前图层的 AI 生图提示词。")
            return

        self.ai_generate_btn.setEnabled(False)
        self.ai_progress_bar.setRange(0, 0)
        self.ai_progress_bar.setFormat("正在生成，请稍候...")
        self.ai_status_label.setText("正在提交生图请求...")
        task = _AIAssetLayerTask(AIAssetService(), request)
        task.signals.finished.connect(self._on_ai_generation_finished)
        self._ai_generation_task = task
        QThreadPool.globalInstance().start(task)

    @Slot(object)
    def _on_ai_generation_finished(self, result):
        self.ai_generate_btn.setEnabled(True)
        self._ai_generation_task = None
        if not isinstance(result, AIAssetResult) or not result.raw_paths:
            errors = getattr(result, "errors", None) or ["生成失败"]
            message = localize_ai_error(errors[0])
            self.ai_progress_bar.setRange(0, 100)
            self.ai_progress_bar.setValue(0)
            self.ai_progress_bar.setFormat("生成失败")
            self.ai_status_label.setText(message)
            return

        output_dir = self._resolve_ai_output_dir(result)
        if not output_dir:
            self.ai_progress_bar.setRange(0, 100)
            self.ai_progress_bar.setValue(0)
            self.ai_progress_bar.setFormat("生成失败")
            self.ai_status_label.setText("生成完成，但没有可用输出目录")
            return

        self.apply_ai_output_to_current_layer(output_dir)
        self.ai_progress_bar.setRange(0, 100)
        self.ai_progress_bar.setValue(100)
        self.ai_progress_bar.setFormat("生成完成")
        self.ai_status_label.setText(f"已生成并写入图层: {output_dir}")

    @staticmethod
    def _resolve_ai_output_dir(result):
        paths = list(getattr(result, "output_paths", None) or getattr(result, "raw_paths", None) or [])
        if not paths:
            return ""
        first = paths[0]
        if os.path.isfile(first) or os.path.splitext(first)[1]:
            return os.path.dirname(first)
        return first

    def apply_ai_output_to_current_layer(self, output_dir):
        if not self.current_layer:
            return
        if self.document:
            self.document.save_state("AI生图更新图层前")

        self.current_layer.image_source = output_dir
        self.current_layer.is_folder = True
        if hasattr(self.current_layer, "current_image_path"):
            self.current_layer.current_image_path = None
        for attr in ("_cached_image", "_cached_source_image", "_cached_image_path", "_cached_source_path"):
            if hasattr(self.current_layer, attr):
                setattr(self.current_layer, attr, None)

        if hasattr(self, "folder_radio"):
            self.folder_radio.setChecked(True)
        if hasattr(self, "source_path_edit"):
            self.source_path_edit.setText(output_dir)
        if hasattr(self, "current_image_label"):
            self.current_image_label.setText("无")

        if self.document:
            if hasattr(self.document, "_invalidate_render_cache"):
                self.document._invalidate_render_cache()
            if hasattr(self.document, "layer_changed"):
                self.document.layer_changed.emit()
            if hasattr(self.document, "document_changed"):
                self.document.document_changed.emit()
            self.document.save_state("AI生图更新图层")

