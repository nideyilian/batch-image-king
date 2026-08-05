from __future__ import annotations

from app.qml.legacy_feature_bridge import (
    LegacyDocumentManagerAdapter,
    LegacyFeatureBridge,
    _LegacyMainWindowAdapter,
)
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


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
    assert host.tab_widget.tabText(0) == "主图.cmp"
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
