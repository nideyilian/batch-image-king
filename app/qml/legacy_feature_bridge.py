from __future__ import annotations

import os
from typing import Dict, Optional

from PySide6.QtCore import QObject, Property, Qt, Signal, Slot
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QMessageBox

from app.controllers.layer_controller import LayerController


class LegacyDocumentManagerAdapter:
    """Expose QML document sessions through the legacy manager contract."""

    def __init__(self, sessions) -> None:
        self._sessions = sessions

    @property
    def active_document_index(self) -> int:
        return int(self._sessions.activeIndex)

    def get_document_count(self) -> int:
        return int(self._sessions.count)

    def get_document(self, index: int):
        return self._sessions.documentAt(int(index))

    def get_document_name(self, index: int) -> str:
        document = self.get_document(index)
        if document is None:
            return f"标签页 {int(index) + 1}"
        path = str(getattr(document, "current_file_path", "") or "")
        if path:
            return os.path.basename(path)
        sessions = getattr(self._sessions, "_sessions", [])
        if 0 <= int(index) < len(sessions):
            return str(self._sessions._title_for(sessions[int(index)]))
        return f"未命名-{int(index) + 1}.cmp"

    def set_active_document(self, index: int) -> bool:
        return bool(self._sessions.activateDocument(int(index)))

    def is_document_modified(self, index: int) -> bool:
        document = self.get_document(index)
        return bool(getattr(document, "is_modified", False)) if document else False


class _LegacyTabWidgetAdapter:
    def __init__(self, document_manager: LegacyDocumentManagerAdapter) -> None:
        self._document_manager = document_manager

    def count(self) -> int:
        return self._document_manager.get_document_count()

    def tabText(self, index: int) -> str:
        return self._document_manager.get_document_name(index)

    def currentIndex(self) -> int:
        return self._document_manager.active_document_index

    def setCurrentIndex(self, index: int) -> None:
        self._document_manager.set_active_document(index)


class _LegacyMainWindowAdapter:
    """Provide the subset used by the mature preset manager dialog."""

    def __init__(self, document_manager: LegacyDocumentManagerAdapter, preset_manager=None) -> None:
        self._document_manager = document_manager
        self.tab_widget = _LegacyTabWidgetAdapter(document_manager)
        if preset_manager is None:
            from app.utils.preset_manager import PresetManager

            preset_manager = PresetManager()
        self.preset_manager = preset_manager
        self._current_editing_preset_id = None
        self._current_editing_preset_name = ""
        self._current_editing_preset_description = ""

    @property
    def documents(self):
        return [
            self._document_manager.get_document(index)
            for index in range(self._document_manager.get_document_count())
        ]

    @staticmethod
    def get_global_settings():
        return {}

    def _set_current_editing_preset(self, preset_id, name, description="") -> None:
        self._current_editing_preset_id = preset_id
        self._current_editing_preset_name = str(name or "")
        self._current_editing_preset_description = str(description or "")

    @staticmethod
    def _sync_document_view_settings_from_tab(_index: int) -> None:
        return None


class _LayerControllerHost:
    def __init__(self, workspace) -> None:
        self.workspace = workspace
        self.layer_panel = None
        self.layer_clipboard = None
        self.layer_style_clipboard = None

    @property
    def document(self):
        return self.workspace.document

    def update_canvas(self) -> None:
        self.workspace.layerModel.reset_from_document()
        self.workspace.selectionChanged.emit()
        self.workspace.documentInfoChanged.emit()
        self.workspace.historyStateChanged.emit()
        self.workspace.requestPreview(force=True)


class LegacyFeatureBridge(QObject):
    """Open mature QWidget tools without duplicating their business logic in QML."""

    clipboardChanged = Signal()

    def __init__(self, workspace, sessions, preset_view_model=None, parent=None) -> None:
        super().__init__(parent)
        self._workspace = workspace
        self._sessions = sessions
        self._preset_view_model = preset_view_model
        self._document_manager = LegacyDocumentManagerAdapter(sessions)
        preset_manager = getattr(preset_view_model, "_manager", None)
        self._main_window_adapter = _LegacyMainWindowAdapter(
            self._document_manager, preset_manager
        )
        self._windows: Dict[object, object] = {}
        self._layer_host = _LayerControllerHost(workspace)
        self._layer_controller = LayerController(self._layer_host)
        self._layer_controller.status_message.connect(
            lambda message, _timeout: self._status(message)
        )
        workspace.documentObjectChanged.connect(self._on_document_changed)

    @Property(bool, notify=clipboardChanged)
    def hasLayerClipboard(self) -> bool:
        return bool(self._layer_host.layer_clipboard)

    def _status(self, message: str) -> None:
        self._workspace._set_status(str(message or ""), toast=True)

    @staticmethod
    def _prompt_text(title: str, label: str, value: str):
        return QInputDialog.getText(None, title, label, text=str(value or ""))

    def _window_key(self, name: str, *, per_document: bool = False):
        return (name, id(self._workspace.document)) if per_document else name

    def _show_window(self, key, factory):
        existing = self._windows.get(key)
        if existing is not None:
            existing.show()
            existing.raise_()
            existing.activateWindow()
            return existing
        try:
            window = factory()
            if window is None:
                return None
            window.setAttribute(Qt.WA_DeleteOnClose, True)
            self._windows[key] = window

            def clear_reference(*_args) -> None:
                if self._windows.get(key) is window:
                    self._windows.pop(key, None)

            window.destroyed.connect(clear_reference)
            window.show()
            window.raise_()
            window.activateWindow()
            return window
        except Exception as error:
            self._status(f"无法打开高级工具：{error}")
            return None

    @Slot(object)
    def _on_document_changed(self, document) -> None:
        panel = self._windows.get("advanced_properties")
        if panel is not None and hasattr(panel, "set_document"):
            panel.set_document(document)

    def _refresh_workspace(self, status: str) -> None:
        self._workspace.document.is_modified = True
        self._layer_host.update_canvas()
        self._status(status)

    @Slot(result=bool)
    def openNewDocument(self) -> bool:
        from app.ui.new_canvas_dialog import get_canvas_settings

        settings = get_canvas_settings(
            default_settings={"width": 1080, "height": 1350, "document_name": "未命名文档"}
        )
        if not settings:
            return False
        if not self._sessions.newDocument(settings["width"], settings["height"]):
            return False
        self._sessions.renameDocument(
            self._sessions.activeIndex, str(settings.get("document_name") or "未命名文档")
        )
        return True

    @Slot(result=bool)
    def openAddTextLayer(self) -> bool:
        from app.ui.add_text_layer_dialog_simple import AddTextLayerDialog

        dialog = AddTextLayerDialog()
        if dialog.exec() != QDialog.Accepted:
            return False
        try:
            self._workspace.document.add_text_layer(dialog.get_text_layer())
            self._refresh_workspace("成功添加文字图层")
            return True
        except Exception as error:
            self._status(f"添加文字图层失败：{error}")
            return False

    @Slot(result=bool)
    def openAddShapedLayer(self) -> bool:
        from app.ui.add_shaped_layer_dialog import AddShapedLayerDialog

        dialog = AddShapedLayerDialog()
        if dialog.exec() != QDialog.Accepted:
            return False
        try:
            self._workspace.document.add_shaped_layer(dialog.get_created_layer())
            self._refresh_workspace("成功添加异形图层")
            return True
        except Exception as error:
            self._status(f"添加异形图层失败：{error}")
            return False

    @Slot(result=bool)
    def openAdvancedLayerProperties(self) -> bool:
        def create():
            from app.ui.layer_properties import LayerPropertiesPanel

            panel = LayerPropertiesPanel(self._workspace.document)
            panel.setWindowFlag(Qt.Window, True)
            panel.setWindowTitle("高级图层属性")
            panel.resize(430, 820)
            ai_group = getattr(panel, "ai_generation_group", None)
            if ai_group is not None:
                ai_group.hide()
            return panel

        return self._show_window("advanced_properties", create) is not None

    @Slot(result=bool)
    def openBatchExport(self) -> bool:
        from app.ui.batch_export_dialog import BatchExportDialog

        key = self._window_key("batch_export", per_document=True)

        def create():
            dialog = BatchExportDialog(self._workspace.document)
            dialog.setModal(False)
            dialog.setWindowModality(Qt.NonModal)
            return dialog

        return self._show_window(key, create) is not None

    @Slot(result=bool)
    def openMultiTabExport(self) -> bool:
        from app.ui.multi_tab_export_dialog import MultiTabExportDialog

        return self._show_window(
            "multi_tab_export",
            lambda: MultiTabExportDialog(self._document_manager),
        ) is not None

    @Slot(result=bool)
    def openBindingManager(self) -> bool:
        from app.ui.binding_manager_dialog import LayerBindingManagerDialog

        key = self._window_key("binding_manager", per_document=True)
        return self._show_window(
            key, lambda: LayerBindingManagerDialog(self._workspace.document)
        ) is not None

    @Slot(result=bool)
    def openSizeMatchManager(self) -> bool:
        from app.ui.layer_size_match_dialog import LayerSizeMatchDialog

        key = self._window_key("size_match", per_document=True)
        return self._show_window(
            key, lambda: LayerSizeMatchDialog(self._workspace.document)
        ) is not None

    @Slot(result=bool)
    def openCanvasPresetManager(self) -> bool:
        from app.ui.canvas_preset_dialog import CanvasPresetManagerDialog

        return self._show_window(
            "canvas_presets", lambda: CanvasPresetManagerDialog()
        ) is not None

    @Slot(result=bool)
    def openPresetManager(self) -> bool:
        from app.ui.preset_store_dialog import PresetStoreDialog

        def create():
            dialog = PresetStoreDialog(self._main_window_adapter)
            dialog.preset_edit_requested.connect(
                lambda preset_id: self._load_preset_from_store(preset_id, dialog)
            )
            return dialog

        return self._show_window("preset_store", create) is not None

    def _save_modified_documents_before_preset(self) -> bool:
        modified = [
            index
            for index in range(self._document_manager.get_document_count())
            if self._document_manager.is_document_modified(index)
        ]
        if not modified:
            return True
        message = QMessageBox()
        message.setWindowTitle("加载预设")
        message.setText("当前有未保存的文档。继续加载预设前是否保存？")
        save_button = message.addButton("保存", QMessageBox.AcceptRole)
        discard_button = message.addButton("不保存", QMessageBox.DestructiveRole)
        cancel_button = message.addButton("取消", QMessageBox.RejectRole)
        message.exec()
        clicked = message.clickedButton()
        if clicked == cancel_button:
            return False
        if clicked == discard_button:
            return True
        if clicked != save_button:
            return False
        for index in modified:
            self._sessions.activateDocument(index)
            path = str(getattr(self._workspace.document, "current_file_path", "") or "")
            if not path:
                path, _filter = QFileDialog.getSaveFileName(
                    None, "保存项目", "", "批图王项目 (*.cmp)"
                )
            if not path or not self._workspace.saveDocumentTo(path):
                return False
        return True

    def _load_preset_from_store(self, preset_id: str, dialog=None) -> bool:
        if not self._save_modified_documents_before_preset():
            return False
        close_existing = False
        if self._document_manager.get_document_count() > 0:
            message = QMessageBox()
            message.setWindowTitle("进入编辑")
            message.setText("是否要关闭现有标签页并加载预设？\n选择“否”会把预设添加到当前标签页之后。")
            close_button = message.addButton("关闭现有", QMessageBox.AcceptRole)
            append_button = message.addButton("追加加载", QMessageBox.DestructiveRole)
            cancel_button = message.addButton("取消", QMessageBox.RejectRole)
            message.exec()
            clicked = message.clickedButton()
            if clicked == cancel_button:
                return False
            close_existing = clicked == close_button
            if clicked not in (close_button, append_button):
                return False
        manager = self._main_window_adapter.preset_manager
        data = manager.load_preset(str(preset_id or ""))
        if not data:
            self._status("无法读取预设")
            return False
        from app.utils.preset_document_loader import documents_from_preset_data

        documents = documents_from_preset_data(data)
        loaded = (
            self._sessions.replaceDocuments(documents, "加载预设")
            if close_existing
            else self._sessions.appendDocuments(documents, "加载预设")
        )
        if not loaded:
            self._status("预设中没有可用文档")
            return False
        manager.touch_preset_used(str(preset_id or ""))
        if dialog is not None:
            dialog.accept()
        self._status(f"已加载预设，共 {loaded} 个标签页")
        return True

    @Slot(int, result=bool)
    def restoreExportWindow(self, index: int) -> bool:
        document = self._sessions.documentAt(int(index))
        if document is None:
            return False
        for name in ("batch_export", "multi_tab_export"):
            key = (name, id(document)) if name == "batch_export" else name
            window = self._windows.get(key)
            if window is not None and bool(getattr(window, "_export_started", False)):
                self._sessions.activateDocument(int(index))
                window.show()
                window.raise_()
                window.activateWindow()
                return True
        self._status("当前标签页没有正在后台运行的导出任务")
        return False

    @Slot(result=bool)
    def openResizeCanvas(self) -> bool:
        from app.ui.resize_canvas_dialog import ResizeCanvasDialog

        document = self._workspace.document
        dialog = ResizeCanvasDialog(document.canvas_width, document.canvas_height)
        if dialog.exec() != QDialog.Accepted:
            return False
        width, height = dialog.get_canvas_size()
        mode = int(dialog.get_adjustment_mode())
        return self._resize_canvas(int(width), int(height), mode)

    def _resize_canvas(self, width: int, height: int, mode: int) -> bool:
        document = self._workspace.document
        old_width = max(1, int(document.canvas_width))
        old_height = max(1, int(document.canvas_height))
        if width == old_width and height == old_height:
            return True
        if not 16 <= width <= 32768 or not 16 <= height <= 32768:
            self._status("画布尺寸必须在 16 到 32768 像素之间")
            return False

        with self._workspace.documentLock:
            self._workspace._ensure_history_baseline()
            width_scale = width / old_width
            height_scale = height / old_height
            for layer in document.layers:
                if not all(hasattr(layer, attr) for attr in ("x", "y", "width", "height")):
                    continue
                if mode == 0:
                    layer.x = int(round(layer.x * width_scale))
                    layer.y = int(round(layer.y * height_scale))
                    layer.width = max(1, int(round(layer.width * width_scale)))
                    layer.height = max(1, int(round(layer.height * height_scale)))
                elif mode == 1:
                    layer.x = int(round((width - layer.width) / 2))
                    layer.y = int(round((height - layer.height) / 2))
                elif mode == 2:
                    layer.x = 0
                    layer.y = 0
                for cache_name in ("_cached_image", "cached_image"):
                    if hasattr(layer, cache_name):
                        setattr(layer, cache_name, None)
            document.canvas_width = width
            document.canvas_height = height
            document.is_modified = True
            document._invalidate_render_cache()
            document.bump_hit_test_version()
            document.save_state("调整画布尺寸")
            document.document_changed.emit()
        self._layer_host.update_canvas()
        self._status(f"画布已调整为 {width} x {height}")
        return True

    @Slot(result=bool)
    def copySelectedLayers(self) -> bool:
        success = bool(self._layer_controller.copy_layer())
        self.clipboardChanged.emit()
        return success

    @Slot(result=bool)
    def pasteLayers(self) -> bool:
        success = bool(self._layer_controller.paste_layer())
        self.clipboardChanged.emit()
        return success

    @Slot(result=bool)
    def selectAllLayers(self) -> bool:
        layers = self._workspace.document.layers
        if not layers:
            return False
        self._workspace.document.select_layers(
            list(range(len(layers))), primary_index=0
        )
        self._workspace.layerModel.reset_from_document()
        self._workspace.selectionChanged.emit()
        return True

    @Slot(result=bool)
    def renameSelectedLayer(self) -> bool:
        layer = self._workspace._selected_layer()
        if layer is None:
            return False
        name, accepted = self._prompt_text("重命名图层", "请输入新名称:", layer.name)
        if not accepted or not str(name).strip():
            return False
        return bool(self._workspace.setSelectedName(str(name).strip()))

    @Slot(result=bool)
    def renameCurrentTab(self) -> bool:
        index = int(self._sessions.activeIndex)
        current = self._document_manager.get_document_name(index)
        name, accepted = self._prompt_text("重命名标签页", "请输入新名称:", current)
        if not accepted or not str(name).strip():
            return False
        return bool(self._sessions.renameDocument(index, str(name).strip()))


__all__ = ["LegacyDocumentManagerAdapter", "LegacyFeatureBridge"]
