from __future__ import annotations

from pathlib import Path

import pytest

from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_qml_routes_business_popups_to_native_overlays():
    qml_source = (REPO_ROOT / "app" / "qml" / "Main.qml").read_text(encoding="utf-8")
    bridge_source = (REPO_ROOT / "app" / "qml" / "legacy_feature_bridge.py").read_text(
        encoding="utf-8"
    )

    assert "legacyTools.open" not in qml_source
    assert 'id: resizeCanvasDialog' in qml_source
    assert 'id: renameDocumentDialog' in qml_source
    assert 'function openBatchExportDrawer()' in qml_source
    assert 'function openMultiTabExportDrawer()' in qml_source
    assert 'function openProjectPresetDrawer()' in qml_source
    assert 'function openCanvasPresetDrawer()' in qml_source
    assert 'function openDataRelations(tab)' in qml_source
    assert "QtWidgets" not in bridge_source
    assert "app.ui." not in bridge_source


@pytest.mark.unit
def test_resize_canvas_supports_all_native_dialog_adjustment_modes():
    workspace = WorkspaceViewModel(auto_render=False)
    assert workspace.newDocument(200, 100) is True
    assert workspace.addTextLayer() is True
    layer = workspace.document.layers[0]
    layer.x, layer.y, layer.width, layer.height = 10, 20, 40, 30

    assert workspace.resizeCanvas(400, 200, 0) is True
    assert (layer.x, layer.y, layer.width, layer.height) == (20, 40, 80, 60)

    assert workspace.resizeCanvas(500, 300, 1) is True
    assert (layer.x, layer.y) == (210, 120)

    assert workspace.resizeCanvas(600, 400, 2) is True
    assert (layer.x, layer.y) == (0, 0)


@pytest.mark.unit
def test_session_title_is_available_to_native_rename_dialog():
    workspace = WorkspaceViewModel(auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace)

    assert sessions.titleAt(0).startswith("未命名-")
    assert sessions.renameDocument(0, "商品主图") is True
    assert sessions.titleAt(0) == "商品主图"
    assert sessions.titleAt(-1) == ""
