from __future__ import annotations

from app.qml.legacy_feature_bridge import LegacyFeatureBridge
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace_with_sessions():
    workspace = WorkspaceViewModel(auto_render=False)
    workspace.newDocument(320, 240)
    sessions = WorkspaceSessionViewModel(workspace)
    return workspace, sessions


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


def test_bridge_select_all_uses_active_document():
    workspace, sessions = _workspace_with_sessions()
    workspace.addTextLayer()
    workspace.addTextLayer()
    bridge = LegacyFeatureBridge(workspace, sessions)

    assert bridge.selectAllLayers() is True
    assert workspace.selectedLayerCount == 2

    assert not hasattr(bridge, "openAddTextLayer")
    assert not hasattr(bridge, "openAddShapedLayer")
    assert not hasattr(bridge, "renameSelectedLayer")


def test_bridge_no_longer_exposes_widget_popup_routes():
    workspace, sessions = _workspace_with_sessions()
    bridge = LegacyFeatureBridge(workspace, sessions)

    popup_routes = (
        "openNewDocument",
        "openBatchExport",
        "openMultiTabExport",
        "openBindingManager",
        "openSizeMatchManager",
        "openCanvasPresetManager",
        "openPresetManager",
        "restoreExportWindow",
        "openResizeCanvas",
        "renameCurrentTab",
    )
    assert all(not hasattr(bridge, route) for route in popup_routes)
