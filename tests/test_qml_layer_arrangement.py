from __future__ import annotations

from pathlib import Path

import pytest

from app.models.document import Document
from app.models.layer_group import LayerGroup
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.layer_list_model import LayerListModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.utils.layer_tree import get_parent_group_id


def _workspace() -> WorkspaceViewModel:
    document = Document()
    document.create_new(600, 400)
    geometries = [
        ("A", 20, 30, 80, 60),
        ("B", 180, 90, 100, 80),
        ("C", 330, 180, 60, 90),
        ("D", 470, 260, 70, 50),
    ]
    for name, x, y, width, height in geometries:
        document.add_layer(name, x, y, width, height, is_folder=False)
    document._history_manager.clear()
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


@pytest.mark.unit
def test_ctrl_shift_selection_and_combined_bounds():
    workspace = _workspace()

    assert workspace.selectLayerWithModifiers(1, False, False) is True
    assert workspace.selectLayerWithModifiers(3, True, False) is True
    assert workspace.selectedLayerIndices == [1, 3]
    assert workspace.selectedLayerIndex == 3
    assert workspace.selectedLayerCount == 2
    assert workspace.selectionBoundsX == 180
    assert workspace.selectionBoundsY == 90
    assert workspace.selectionBoundsWidth == 360
    assert workspace.selectionBoundsHeight == 220

    assert workspace.selectLayerWithModifiers(0, False, True) is True
    assert workspace.selectedLayerIndices == [0, 1, 2, 3]
    assert workspace.selectLayerWithModifiers(1, True, False) is True
    assert workspace.selectedLayerIndices == [0, 2, 3]


@pytest.mark.unit
def test_marquee_selection_and_batch_move():
    workspace = _workspace()

    assert workspace.selectLayersInRect(0, 0, 300, 190, False) is True
    assert workspace.selectedLayerIndices == [0, 1]
    assert workspace.moveSelectedLayersBy(15, -10) is True
    assert (workspace.document.layers[0].x, workspace.document.layers[0].y) == (35, 20)
    assert (workspace.document.layers[1].x, workspace.document.layers[1].y) == (195, 80)
    assert workspace.undo() is True
    assert (workspace.document.layers[0].x, workspace.document.layers[0].y) == (20, 30)


@pytest.mark.unit
def test_group_ungroup_and_round_trip(tmp_path: Path):
    workspace = _workspace()
    workspace.document.select_layers([0, 1], primary_index=0)

    assert workspace.groupSelectedLayers() is True
    assert isinstance(workspace.document.layers[0], LayerGroup)
    group = workspace.document.layers[0]
    assert get_parent_group_id(workspace.document.layers[1]) == group.group_id
    assert get_parent_group_id(workspace.document.layers[2]) == group.group_id
    assert workspace.selectedIsLayerGroup is True

    model = workspace.layerModel
    group_row = next(
        row
        for row in range(model.rowCount())
        if model.data(model.index(row, 0), LayerListModel.IsGroupRole) is True
    )
    assert model.data(model.index(group_row + 1, 0), LayerListModel.DepthRole) == 1
    assert model.data(model.index(group_row, 0), LayerListModel.SelectedRole) is True

    assert workspace.undo() is True
    assert all(not isinstance(layer, LayerGroup) for layer in workspace.document.layers)
    assert workspace.redo() is True
    assert isinstance(workspace.document.layers[0], LayerGroup)

    project = tmp_path / "grouped.cmp"
    assert workspace.saveDocumentTo(str(project)) is True
    loaded = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
    assert loaded.openDocument(str(project)) is True
    loaded_group = loaded.document.layers[0]
    assert isinstance(loaded_group, LayerGroup)
    assert get_parent_group_id(loaded.document.layers[1]) == loaded_group.group_id
    assert get_parent_group_id(loaded.document.layers[2]) == loaded_group.group_id

    assert loaded.ungroupSelectedGroups() is True
    assert all(not isinstance(layer, LayerGroup) for layer in loaded.document.layers)
    assert all(get_parent_group_id(layer) is None for layer in loaded.document.layers)


@pytest.mark.unit
def test_batch_visibility_lock_duplicate_delete_and_reorder():
    workspace = _workspace()
    workspace.document.select_layers([1, 2], primary_index=1)

    assert workspace.setSelectedLayersVisible(False) is True
    assert workspace.document.layers[1].visible is False
    assert workspace.document.layers[2].visible is False
    assert workspace.setSelectedLayersLocked(True) is True
    assert workspace.document.layers[1].locked is True
    assert workspace.document.layers[2].locked is True
    assert workspace.setSelectedLayersLocked(False) is True

    assert workspace.duplicateSelectedLayers() is True
    assert len(workspace.document.layers) == 6
    duplicated_names = [workspace.document.layers[index].name for index in workspace.selectedLayerIndices]
    assert duplicated_names == ["B 副本", "C 副本"]

    assert workspace.moveSelectedLayersTo(0) is True
    assert [layer.name for layer in workspace.document.layers[:2]] == ["B 副本", "C 副本"]
    assert workspace.deleteSelectedLayers() is True
    assert len(workspace.document.layers) == 4


@pytest.mark.unit
def test_multi_align_same_size_and_distribute():
    workspace = _workspace()
    workspace.document.select_layers([0, 1, 2, 3], primary_index=0)

    assert workspace.alignSelectedLayers("top") is True
    assert [layer.y for layer in workspace.document.layers] == [30, 30, 30, 30]
    assert workspace.alignSelectedLayers("same_size") is True
    assert [(layer.width, layer.height) for layer in workspace.document.layers] == [(80, 60)] * 4

    workspace.document.layers[0].x = 0
    workspace.document.layers[1].x = 150
    workspace.document.layers[2].x = 360
    workspace.document.layers[3].x = 520
    assert workspace.distributeSelectedLayers("horizontal") is True
    gaps = [
        workspace.document.layers[index + 1].x
        - workspace.document.layers[index].x
        - workspace.document.layers[index].width
        for index in range(3)
    ]
    assert max(gaps) - min(gaps) <= 1
