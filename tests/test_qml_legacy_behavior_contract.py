from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.layer_list_model import LayerListModel
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace(width: int = 320, height: int = 240) -> WorkspaceViewModel:
    document = Document()
    document.create_new(width, height)
    document._history_manager.clear()
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


@pytest.mark.unit
def test_empty_image_layer_preserves_classic_creation_contract():
    workspace = _workspace()

    assert workspace.addEmptyImageLayer() is True
    layer = workspace.document.layers[0]

    assert layer.name == "图层 1"
    assert (layer.x, layer.y, layer.width, layer.height) == (0, 0, 200, 200)
    assert layer.image_source is None
    assert layer.current_image_path is None
    assert layer.is_folder is True


@pytest.mark.unit
def test_selecting_image_source_automatically_sets_its_mode(tmp_path: Path):
    source = tmp_path / "source.png"
    replacement = tmp_path / "replacement.png"
    folder = tmp_path / "assets"
    folder.mkdir()
    Image.new("RGBA", (20, 20), (255, 0, 0, 255)).save(source)
    Image.new("RGBA", (20, 20), (0, 255, 0, 255)).save(replacement)
    Image.new("RGBA", (20, 20), (0, 0, 255, 255)).save(folder / "folder-source.png")
    workspace = _workspace()
    assert workspace.addImageLayer(str(source)) is True

    assert workspace.setSelectedImageSource(str(folder)) is True
    layer = workspace.document.layers[0]
    assert layer.is_folder is True
    assert layer.image_source == str(folder)
    assert layer.current_image_path == str(folder / "folder-source.png")

    assert workspace.setSelectedImageSource(str(replacement)) is True
    assert layer.is_folder is False
    assert layer.image_source == str(replacement)
    assert layer.current_image_path == str(replacement)


@pytest.mark.unit
def test_layers_can_move_outside_canvas_and_keep_negative_coordinates():
    workspace = _workspace()
    workspace.addEmptyImageLayer()

    assert workspace.moveSelectedLayersBy(-75, -55) is True
    assert (workspace.document.layers[0].x, workspace.document.layers[0].y) == (-75, -55)
    assert workspace.applySelectedGeometry(-120, 260, 10, 10) is True
    assert (workspace.selectedX, workspace.selectedY) == (-120, 260)


@pytest.mark.unit
def test_layer_list_displays_visual_top_layer_first():
    workspace = _workspace()
    for name in ("底层", "中层", "顶层"):
        workspace.document.add_layer(name, 0, 0, 20, 20)
    model = LayerListModel(workspace.document)

    assert model.data(model.index(0, 0), model.NameRole) == "顶层"
    assert model.data(model.index(0, 0), model.LayerIndexRole) == 2
    assert model.data(model.index(2, 0), model.NameRole) == "底层"
    assert model.data(model.index(2, 0), model.LayerIndexRole) == 0


@pytest.mark.unit
def test_canvas_hit_testing_keeps_locked_layers_pickable_and_skips_transparent_pixels(tmp_path: Path):
    opaque = tmp_path / "opaque.png"
    transparent = tmp_path / "transparent.png"
    Image.new("RGBA", (20, 20), (20, 160, 90, 255)).save(opaque)
    overlay = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    overlay.putpixel((10, 10), (240, 30, 30, 255))
    overlay.save(transparent)

    workspace = _workspace(100, 100)
    workspace.document.add_layer("底层", 10, 10, 20, 20, str(opaque), False, False)
    workspace.document.add_layer("透明顶层", 10, 10, 20, 20, str(transparent), False, False)
    workspace.document.layers[0].locked = True

    assert workspace.hitTestLayerAt(11, 11) == 0
    assert workspace.hitTestLayerAt(20, 20) == 1


@pytest.mark.unit
def test_ctrl_canvas_click_cycles_through_overlapping_layers():
    workspace = _workspace(100, 100)
    workspace.document.add_layer("底层", 10, 10, 30, 30)
    workspace.document.add_layer("顶层", 10, 10, 30, 30)

    assert workspace.selectLayerAtWithModifiers(20, 20, False, False) == 1
    assert workspace.selectLayerAtWithModifiers(20, 20, True, False) == 0
    assert workspace.selectLayerAtWithModifiers(20, 20, True, False) == 1


@pytest.mark.unit
def test_dragging_bottom_panel_item_to_top_updates_document_stack():
    workspace = _workspace()
    for name in ("底层", "中层", "顶层"):
        workspace.document.add_layer(name, 0, 0, 20, 20)
    workspace.selectLayer(0)

    assert workspace.moveSelectedLayersTo(2) is True
    assert [layer.name for layer in workspace.document.layers] == ["中层", "顶层", "底层"]


@pytest.mark.unit
def test_zoom_and_pan_use_classic_document_view_settings():
    workspace = _workspace()
    workspace.document.view_settings.update(
        {"zoom_factor": 2.5, "offset_x": 41, "offset_y": -27}
    )

    assert workspace.zoomFactor == pytest.approx(2.5)
    assert workspace.viewOffsetX == 41
    assert workspace.viewOffsetY == -27
    assert workspace.setZoomFactor(20) is True
    assert workspace.zoomFactor == pytest.approx(10.0)
    assert workspace.setZoomFactor(0.01) is True
    assert workspace.zoomFactor == pytest.approx(0.1)
    assert workspace.setViewOffset(-90, 125) is True
    assert workspace.document.view_settings["offset_x"] == -90
    assert workspace.document.view_settings["offset_y"] == 125


@pytest.mark.unit
def test_sessions_allow_duplicate_paths_and_sync_classic_tab_names(tmp_path: Path):
    source = _workspace()
    project = tmp_path / "same.cmp"
    assert source.saveDocumentTo(str(project)) is True

    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)
    assert sessions.openDocument(str(project)) is True
    assert sessions.openDocument(str(project)) is True
    assert sessions.count == 3

    assert sessions.renameDocument(2, "商品主图") is True
    document = sessions.documentAt(2)
    assert document.name == "商品主图"
    assert document.tab_name == "商品主图"
    assert document.original_tab_name == "商品主图"


@pytest.mark.unit
def test_duplicate_tab_copies_only_classic_document_scope():
    workspace = _workspace()
    workspace.addEmptyImageLayer()
    workspace.document.view_settings["zoom_factor"] = 3.0
    workspace.document.binding_manager.global_enabled = False
    sessions = WorkspaceSessionViewModel(workspace)
    source_document = workspace.document

    index = sessions.duplicateDocument(0)
    duplicate = sessions.documentAt(index)

    assert len(duplicate.layers) == 1
    assert duplicate.layers[0] is not source_document.layers[0]
    assert duplicate.export_settings == source_document.export_settings
    assert duplicate.view_settings["zoom_factor"] == pytest.approx(1.0)
    assert duplicate.binding_manager.global_enabled is True


@pytest.mark.unit
def test_closing_last_tab_does_not_insert_an_unrequested_document():
    workspace = _workspace()
    sessions = WorkspaceSessionViewModel(workspace)
    workspace.document.is_modified = False

    assert sessions.requestClose(0) is True
    assert sessions.count == 0
    assert sessions.activeIndex == -1
