from __future__ import annotations

from pathlib import Path

import pytest

from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_sessions_can_start_without_an_open_document():
    workspace = WorkspaceViewModel(auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace, include_initial_document=False)

    assert sessions.count == 0
    assert sessions.activeIndex == -1
    assert sessions.newDocument(800, 600) is True
    assert sessions.count == 1
    assert sessions.activeIndex == 0
    assert (workspace.canvasWidth, workspace.canvasHeight) == (800, 600)


@pytest.mark.unit
def test_qml_contains_the_complete_top_alignment_group():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert 'id: alignmentTools' in source
    for mode in ("left", "hcenter", "right", "top", "vcenter", "bottom"):
        assert f'alignmentMode: "{mode}"' in source
    assert 'distributionMode: "horizontal"' in source
    assert 'distributionMode: "vertical"' in source
    assert 'workspace.selectedLayerCount > 2' in source


@pytest.mark.unit
def test_qml_has_a_real_no_document_state():
    main_qml = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    launcher = (REPO_ROOT / "app/qml/qml_main.py").read_text(encoding="utf-8")

    assert 'readonly property bool hasOpenDocument: workspaceSessions.count > 0' in main_qml
    assert 'objectName: "noDocumentState"' in main_qml
    assert 'text: "没有打开的文档"' in main_qml
    assert 'newCanvasDialog.open()' in main_qml
    assert 'openDialog.open()' in main_qml
    assert 'include_initial_document=initial_document_requested' in launcher


@pytest.mark.unit
def test_rulers_are_fixed_to_the_canvas_viewport():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert 'id: viewportTopRuler' in source
    assert 'id: viewportLeftRuler' in source
    assert 'id: rulerOriginCorner' in source
    assert 'property real rulerOriginX: artboardFrame.x' in source
    assert 'property real rulerOriginY: artboardFrame.y' in source
    assert 'function rulerMajorStep()' in source
    assert 'id: topRuler' not in source
    assert 'id: leftRuler' not in source
