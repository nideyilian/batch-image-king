from __future__ import annotations

from PySide6.QtCore import QObject, Property, Signal, Slot

from app.controllers.layer_controller import LayerController


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
    """Keep only non-visual controller compatibility used by the QML workbench."""

    clipboardChanged = Signal()

    def __init__(
        self,
        workspace,
        sessions=None,
        preset_view_model=None,
        parent=None,
    ) -> None:
        del sessions, preset_view_model
        super().__init__(parent)
        self._workspace = workspace
        self._layer_host = _LayerControllerHost(workspace)
        self._layer_controller = LayerController(self._layer_host)
        self._layer_controller.status_message.connect(
            lambda message, _timeout: self._workspace._set_status(
                str(message or ""), toast=True
            )
        )

    @Property(bool, notify=clipboardChanged)
    def hasLayerClipboard(self) -> bool:
        return bool(self._layer_host.layer_clipboard)

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


__all__ = ["LegacyFeatureBridge"]
