from __future__ import annotations

from pathlib import Path

import pytest

from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


REPO_ROOT = Path(__file__).resolve().parents[1]

def _launcher_source() -> str:
    """启动器全量源码（qml_main + qml_debug_entries）。

    2026-11-02 拆分：调试入口 / 窗口几何 / 初始文档准备搬进了
    ``app/qml/qml_debug_entries.py``。这些测试关心的是"启动器具备该能力"，
    与代码住在哪个文件无关，所以统一读全量源码，避免因为搬家误报。
    """
    launcher_dir = REPO_ROOT / "app" / "qml"
    return "\n".join(
        (launcher_dir / name).read_text(encoding="utf-8")
        for name in ("qml_main.py", "qml_debug_entries.py")
        if (launcher_dir / name).exists()
    )



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
def test_qml_restores_original_center_size_and_randomize_commands():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert 'alignmentMode: "center"' in source
    assert 'alignmentMode: "same_size"' in source
    assert 'id: randomizeAllLayersButton' in source
    assert 'workspace.randomizeAllLayers()' in source
    assert 'tooltip: "完全居中于画板"' in source
    assert 'tooltip: "完全匹配画板大小"' in source


@pytest.mark.unit
def test_randomize_all_layers_button_keeps_a_visible_disabled_state():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    button_source = source.split("id: randomizeAllLayersButton", 1)[1].split("}", 1)[0]

    assert "primary: enabled" in button_source
    assert "enabled: workspace.layerCount > 0 && !workspace.operationsBlocked" in button_source
    assert "layerModel.rowCount()" not in button_source


@pytest.mark.unit
def test_qml_has_a_real_no_document_state():
    main_qml = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    launcher = _launcher_source()

    assert 'readonly property bool hasOpenDocument: workspaceSessions.count > 0' in main_qml
    assert 'objectName: "noDocumentState"' in main_qml
    assert 'text: "没有打开的文档"' in main_qml
    assert 'newCanvasDialog.open()' in main_qml
    assert 'openDialog.open()' in main_qml
    # 2026-11-02 拆分：原来的局部变量 initial_document_requested 被抽成
    # wants_initial_document(args)。断言改成检查等价的新写法，语义不变：
    # 「是否预先建文档」必须由统一判定函数提供，而不是散在 main 里的临时变量。
    assert 'include_initial_document=wants_initial_document(args)' in launcher
    assert 'def wants_initial_document(' in launcher


@pytest.mark.unit
def test_blank_canvas_indicator_uses_reactive_layer_count():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert "workspace.layerCount === 0" in source
    assert "layerModel.rowCount()" not in source


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
