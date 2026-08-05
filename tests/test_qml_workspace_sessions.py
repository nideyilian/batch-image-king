from __future__ import annotations

from pathlib import Path

import pytest

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace(document: Document | None = None) -> WorkspaceViewModel:
    document = document or Document()
    if document.canvas_width == 800 and document.canvas_height == 600:
        document.create_new(1080, 1350)
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


@pytest.mark.unit
def test_sessions_create_switch_and_preserve_document_state():
    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)
    first = workspace.document

    assert sessions.count == 1
    assert sessions.activeIndex == 0
    assert sessions.newDocument(1920, 1080) is True
    second = workspace.document
    assert workspace.addTextLayer() is True

    assert sessions.count == 2
    assert sessions.activeIndex == 1
    assert second is not first
    assert (workspace.canvasWidth, workspace.canvasHeight) == (1920, 1080)
    assert len(second.layers) == 1

    assert sessions.activateDocument(0) is True
    assert workspace.document is first
    assert (workspace.canvasWidth, workspace.canvasHeight) == (1080, 1350)
    assert len(first.layers) == 0

    assert sessions.activateDocument(1) is True
    assert workspace.document is second
    assert workspace.selectedLayerIndex == second.selected_layer_index


@pytest.mark.unit
@pytest.mark.parametrize(
    ("width", "height"),
    [(0, 1080), (15, 1080), (1080, 32769), (-1, 100)],
)
def test_sessions_reject_invalid_canvas_sizes(width: int, height: int):
    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)
    original = workspace.document

    assert sessions.newDocument(width, height) is False
    assert sessions.count == 1
    assert workspace.document is original
    assert "16" in workspace.statusMessage or "尺寸" in workspace.statusMessage


@pytest.mark.unit
def test_sessions_open_projects_in_tabs_and_deduplicate_paths(tmp_path: Path):
    saved = Document()
    saved.create_new(640, 480)
    project = tmp_path / "sample.cmp"
    assert saved.save_document(str(project)) is True

    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)

    assert sessions.openDocument(str(project)) is True
    opened = workspace.document
    assert sessions.count == 2
    assert (workspace.canvasWidth, workspace.canvasHeight) == (640, 480)

    assert sessions.activateDocument(0) is True
    assert sessions.openDocument(project.as_uri()) is True
    assert sessions.count == 2
    assert workspace.document is opened
    assert sessions.activeIndex == 1


@pytest.mark.unit
def test_modified_session_requires_confirmation_and_cancel_preserves_it():
    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)
    requests: list[tuple[int, str]] = []
    sessions.closeConfirmationRequested.connect(
        lambda index, title: requests.append((index, title))
    )
    workspace.document.is_modified = True

    assert sessions.requestClose(0) is False
    assert sessions.count == 1
    assert sessions.pendingCloseIndex == 0
    assert requests and requests[0][0] == 0

    sessions.cancelClose()
    assert sessions.pendingCloseIndex == -1
    assert sessions.count == 1


@pytest.mark.unit
def test_discard_close_and_last_session_replacement():
    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)
    original = workspace.document
    original.is_modified = True

    assert sessions.requestClose(0) is False
    assert sessions.discardAndClose(0) is True

    assert sessions.count == 1
    assert sessions.activeIndex == 0
    assert workspace.document is not original
    assert (workspace.canvasWidth, workspace.canvasHeight) == (1080, 1350)
    assert workspace.isModified is False


@pytest.mark.unit
def test_save_and_close_keeps_session_when_save_fails(tmp_path: Path, monkeypatch):
    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)
    sessions.newDocument(800, 800)
    document = workspace.document
    document.is_modified = True
    monkeypatch.setattr(document, "save_document", lambda _path: False)

    assert sessions.requestClose(1) is False
    assert sessions.saveAndClose(1, str(tmp_path / "blocked.cmp")) is False
    assert sessions.count == 2
    assert workspace.document is document
    assert document.is_modified is True


@pytest.mark.unit
def test_save_and_close_requests_path_for_untitled_document():
    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)
    requests: list[tuple[int, str]] = []
    sessions.savePathRequested.connect(lambda index, title: requests.append((index, title)))
    workspace.document.is_modified = True

    assert sessions.requestClose(0) is False
    assert sessions.saveAndClose(0, "") is False
    assert sessions.count == 1
    assert requests and requests[0][0] == 0


@pytest.mark.unit
def test_save_and_close_persists_document_then_activates_neighbor(tmp_path: Path):
    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)
    first = workspace.document
    assert sessions.newDocument(800, 800) is True
    assert workspace.addTextLayer() is True
    project = tmp_path / "saved-before-close.cmp"

    assert sessions.requestClose(1) is False
    assert sessions.saveAndClose(1, str(project)) is True

    assert project.exists()
    assert sessions.count == 1
    assert sessions.activeIndex == 0
    assert workspace.document is first
    loaded = Document()
    assert loaded.load_document(str(project)) is True
    assert (loaded.canvas_width, loaded.canvas_height) == (800, 800)
    assert len(loaded.layers) == 1


@pytest.mark.unit
def test_workspace_rejects_document_switch_while_export_is_running():
    workspace = _workspace()
    candidate = Document()
    candidate.create_new(300, 200)
    workspace.setExportRunning(True)

    assert workspace.activateDocument(candidate) is False
    assert workspace.document is not candidate
    assert "导出" in workspace.statusMessage
