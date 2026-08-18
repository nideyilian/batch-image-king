from __future__ import annotations

import time
from pathlib import Path

import pytest

from app.models.document import Document
from app.qml.viewmodels.multi_tab_export_view_model import MultiTabExportViewModel
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _wait_until(qapp, predicate, timeout=3.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        qapp.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    qapp.processEvents()
    assert predicate(), "等待多标签导出状态超时"


def _workspace_sessions():
    document = Document()
    document.create_new(320, 240)
    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    sessions.newDocument(640, 480)
    sessions.newDocument(1080, 1080)
    sessions.activateDocument(0)
    return workspace, sessions


def _row(view_model, row):
    index = view_model.index(row, 0)
    return {
        "title": view_model.data(index, view_model.TitleRole),
        "enabled": view_model.data(index, view_model.EnabledRole),
        "count": view_model.data(index, view_model.CountRole),
        "start": view_model.data(index, view_model.StartIndexRole),
        "subdirectory": view_model.data(index, view_model.SubdirectoryRole),
        "status": view_model.data(index, view_model.StatusRole),
        "error": view_model.data(index, view_model.ErrorRole),
    }


@pytest.mark.unit
def test_multi_tab_configuration_and_session_refresh(tmp_path: Path):
    workspace, sessions = _workspace_sessions()
    view_model = MultiTabExportViewModel(workspace, sessions)

    assert view_model.count == 3
    assert view_model.selectedDocumentCount == 3
    assert view_model.totalImages == 30
    assert view_model.setDocumentEnabled(1, False) is True
    assert view_model.setDocumentCount(0, 3) is True
    assert view_model.setDocumentStartIndex(0, 20) is True
    assert view_model.setDocumentSubdirectory(0, "商品/方图") is True
    assert view_model.selectedDocumentCount == 2
    assert view_model.totalImages == 13
    assert _row(view_model, 0)["start"] == 20
    assert _row(view_model, 0)["subdirectory"] == "商品/方图"
    assert view_model.setDocumentSubdirectory(0, "../outside") is False

    sessions.newDocument(1920, 1080)
    assert view_model.count == 4
    assert sessions.discardAndClose(3) is True
    assert view_model.count == 3


@pytest.mark.unit
def test_multi_tab_export_is_serial_and_isolates_failures(qapp, tmp_path: Path):
    workspace, sessions = _workspace_sessions()
    call_order = []

    def runner(document, **kwargs):
        row = [sessions.documentAt(index) for index in range(sessions.count)].index(document)
        call_order.append(row)
        assert kwargs["directory"].startswith(str(tmp_path))
        assert kwargs["count"] == row + 2
        assert kwargs["start_index"] == 10 + row
        document.export_progress_updated.emit(row + 1)
        if row == 1:
            document._last_export_error = "素材缺失"
            return False
        document.export_progress_updated.emit(row + 2)
        return True

    view_model = MultiTabExportViewModel(workspace, sessions, runner=runner)
    view_model.outputDirectory = str(tmp_path)
    view_model.filenameTemplate = "tab_{number:03d}"
    for row in range(3):
        assert view_model.setDocumentCount(row, row + 2)
        assert view_model.setDocumentStartIndex(row, 10 + row)

    assert view_model.startExport() is True
    assert workspace.exportRunning is True
    _wait_until(qapp, lambda: not view_model.running)

    assert call_order == [0, 1, 2]
    assert _row(view_model, 0)["status"] == "完成"
    assert _row(view_model, 1)["status"] == "失败"
    assert _row(view_model, 2)["status"] == "完成"
    assert "素材缺失" in view_model.failureSummary
    assert view_model.succeeded is False
    assert view_model.canceled is False
    assert workspace.exportRunning is False


@pytest.mark.unit
def test_multi_tab_export_cancel_stops_queue(qapp, tmp_path: Path):
    workspace, sessions = _workspace_sessions()
    calls = []

    def runner(document, **kwargs):
        calls.append(document)
        while not kwargs["cancel_callback"]():
            time.sleep(0.01)
        document._last_export_error = "已取消"
        return False

    view_model = MultiTabExportViewModel(workspace, sessions, runner=runner)
    view_model.outputDirectory = str(tmp_path)
    assert view_model.startExport() is True
    _wait_until(qapp, lambda: len(calls) == 1)
    assert view_model.cancelExport() is True
    _wait_until(qapp, lambda: not view_model.running)

    assert len(calls) == 1
    assert view_model.canceled is True
    assert view_model.succeeded is False
    assert workspace.exportRunning is False
