from pathlib import Path

import pytest

from app.models.document import Document
from app.qml.viewmodels.canvas_preset_view_model import CanvasPresetViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.utils.canvas_preset_manager import CanvasPresetManager


def _workspace(document=None):
    return WorkspaceViewModel(document=document or Document(), auto_render=False)


def _document(width, height):
    document = Document()
    document.canvas_width = width
    document.canvas_height = height
    return document


@pytest.mark.unit
def test_guide_visibility_lifecycle_and_snapping():
    workspace = _workspace()

    assert workspace.showRulers is True
    assert workspace.showGuides is True
    assert workspace.snapToGuides is True
    assert workspace.setShowRulers(False) is True
    assert workspace.setShowGuides(False) is True
    assert workspace.setSnapToGuides(False) is True

    assert workspace.setShowGuides(True) is True
    assert workspace.setSnapToGuides(True) is True
    assert workspace.addGuide("vertical", 100) is True
    assert workspace.addGuide("horizontal", 80) is True
    assert workspace.verticalGuides == [100.0]
    assert workspace.horizontalGuides == [80.0]

    snapped = workspace.snapPosition(94, 72, 40, 20, 7)
    assert snapped["x"] == 100
    assert snapped["y"] == 70
    assert snapped["snappedX"] is True
    assert snapped["snappedY"] is True

    assert workspace.moveGuide("vertical", 0, 140) is True
    assert workspace.verticalGuides == [140.0]
    assert workspace.removeGuide("horizontal", 0) is True
    assert workspace.horizontalGuides == []
    assert workspace.clearGuides() is True
    assert workspace.verticalGuides == []


@pytest.mark.unit
def test_guides_are_isolated_and_round_trip_with_document(tmp_path: Path):
    first = _workspace()
    second = _workspace()
    first.addGuide("vertical", 123)
    first.setShowRulers(False)

    assert second.verticalGuides == []
    assert second.showRulers is True

    project = tmp_path / "guides.cmp"
    assert first.saveDocumentTo(str(project)) is True
    loaded = _workspace()
    assert loaded.openDocument(str(project)) is True
    assert loaded.verticalGuides == [123.0]
    assert loaded.showRulers is False


@pytest.mark.unit
def test_canvas_resize_and_view_settings_are_undoable():
    workspace = _workspace(_document(640, 480))
    workspace.document.save_state("初始")

    assert workspace.resizeCanvas(1080, 1350) is True
    assert (workspace.canvasWidth, workspace.canvasHeight) == (1080, 1350)
    assert workspace.undo() is True
    assert (workspace.canvasWidth, workspace.canvasHeight) == (640, 480)

    assert workspace.addGuide("vertical", 64) is True
    assert workspace.verticalGuides == [64.0]
    assert workspace.undo() is True
    assert workspace.verticalGuides == []


@pytest.mark.unit
def test_canvas_preset_crud_and_apply(tmp_path: Path):
    manager = CanvasPresetManager(config_dir=str(tmp_path / "config"))
    workspace = _workspace(_document(640, 480))
    view_model = CanvasPresetViewModel(workspace=workspace, manager=manager)

    built_in_count = view_model.count
    assert built_in_count > 0
    assert view_model.deletePreset(view_model.presets[0]["name"]) is False
    assert view_model.createPreset("", 100, 100) is False
    assert view_model.createPreset("电商竖图", 1080, 1350) is True
    assert view_model.count == built_in_count + 1

    custom_index = view_model.count - 1
    assert view_model.presets[custom_index]["is_builtin"] is False
    assert view_model.applyPreset(custom_index) is True
    assert (workspace.canvasWidth, workspace.canvasHeight) == (1080, 1350)

    assert view_model.renamePreset("电商竖图", "商品详情", 1200, 1600) is True
    assert view_model.presets[-1]["name"] == "商品详情"
    assert view_model.deletePreset("商品详情") is True
    assert view_model.count == built_in_count
