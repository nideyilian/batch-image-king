from __future__ import annotations

from app.qml.legacy_feature_bridge import (
    LegacyDocumentManagerAdapter,
    LegacyFeatureBridge,
    _LegacyMainWindowAdapter,
)
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.models.shaped_layer_new import ShapedLayer
from app.models.text_layer import TextLayer
from PySide6.QtWidgets import QDialog


def _workspace_with_sessions():
    workspace = WorkspaceViewModel(auto_render=False)
    workspace.newDocument(320, 240)
    sessions = WorkspaceSessionViewModel(workspace)
    return workspace, sessions


def test_legacy_document_manager_adapter_tracks_qml_sessions():
    workspace, sessions = _workspace_with_sessions()
    assert sessions.newDocument(640, 480) is True
    adapter = LegacyDocumentManagerAdapter(sessions)

    assert adapter.get_document_count() == 2
    assert adapter.active_document_index == 1
    assert adapter.get_document(1) is workspace.document
    assert adapter.get_document_name(1).endswith(".cmp")

    assert adapter.set_active_document(0) is True
    assert sessions.activeIndex == 0


def test_legacy_preset_host_exposes_all_qml_documents_and_titles():
    workspace, sessions = _workspace_with_sessions()
    sessions.renameDocument(0, "主图")
    sessions.newDocument(640, 480)
    manager = LegacyDocumentManagerAdapter(sessions)
    host = _LegacyMainWindowAdapter(manager)

    assert host.tab_widget.count() == 2
    assert host.tab_widget.tabText(0) == "主图"
    assert host.documents == [sessions.documentAt(0), sessions.documentAt(1)]

    host._set_current_editing_preset("preset-id", "商品预设", "说明")
    assert host._current_editing_preset_id == "preset-id"
    assert host._current_editing_preset_name == "商品预设"


def test_legacy_bridge_copies_layers_between_qml_documents():
    workspace, sessions = _workspace_with_sessions()
    workspace.addTextLayer()
    source = workspace.document
    assert workspace.selectLayer(0) is True

    bridge = LegacyFeatureBridge(workspace, sessions)
    assert bridge.copySelectedLayers() is True
    assert bridge.hasLayerClipboard is True

    assert sessions.newDocument(640, 480) is True
    target = workspace.document
    assert target is not source
    assert len(target.layers) == 0

    assert bridge.pasteLayers() is True
    assert len(target.layers) == 1
    assert target.layers[0].name.startswith(source.layers[0].name)
    assert target.selected_layer_index == 0


def test_bridge_select_all_and_rename_commands_use_active_document(monkeypatch):
    workspace, sessions = _workspace_with_sessions()
    workspace.addTextLayer()
    workspace.addTextLayer()
    bridge = LegacyFeatureBridge(workspace, sessions)

    assert bridge.selectAllLayers() is True
    assert workspace.selectedLayerCount == 2

    monkeypatch.setattr(bridge, "_prompt_text", lambda *_args: ("新名称", True))
    assert bridge.renameSelectedLayer() is True
    assert workspace.selectedLayerName == "新名称"


def test_bridge_uses_classic_creation_dialog_results(monkeypatch):
    workspace, sessions = _workspace_with_sessions()
    bridge = LegacyFeatureBridge(workspace, sessions)
    text_layer = TextLayer(name="旧版文字", x=50, y=50, width=300, height=100)
    shaped_layer = ShapedLayer(
        name="旧版异形",
        x=-20,
        y=30,
        width=240,
        height=180,
        image_source=None,
        is_folder=True,
    )

    class FakeTextDialog:
        def exec(self):
            return QDialog.Accepted

        def get_text_layer(self):
            return text_layer

    class FakeShapeDialog:
        def exec(self):
            return QDialog.Accepted

        def get_created_layer(self):
            return shaped_layer

    import app.ui.add_shaped_layer_dialog as shape_dialog_module
    import app.ui.add_text_layer_dialog_simple as text_dialog_module

    monkeypatch.setattr(text_dialog_module, "AddTextLayerDialog", FakeTextDialog)
    monkeypatch.setattr(shape_dialog_module, "AddShapedLayerDialog", FakeShapeDialog)

    assert bridge.openAddTextLayer() is True
    assert bridge.openAddShapedLayer() is True
    assert workspace.document.layers == [text_layer, shaped_layer]
    assert shaped_layer.image_source is None
    assert shaped_layer.is_folder is True
    assert (text_layer.x, text_layer.y, text_layer.width, text_layer.height) == (50, 50, 300, 100)


def test_bridge_new_document_uses_complete_classic_canvas_settings(monkeypatch):
    workspace, sessions = _workspace_with_sessions()
    bridge = LegacyFeatureBridge(workspace, sessions)
    import app.ui.new_canvas_dialog as canvas_dialog_module

    monkeypatch.setattr(
        canvas_dialog_module,
        "get_canvas_settings",
        lambda **_kwargs: {
            "document_name": "横版海报",
            "width": 1920,
            "height": 1080,
            "transparent": True,
        },
    )

    assert bridge.openNewDocument() is True
    assert sessions.count == 2
    assert (workspace.canvasWidth, workspace.canvasHeight) == (1920, 1080)
    assert sessions.data(sessions.index(1, 0), sessions.TitleRole) == "横版海报"
