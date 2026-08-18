from __future__ import annotations

from pathlib import Path

from PIL import Image
import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace(document: Document) -> WorkspaceViewModel:
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


def _image_and_text_document(tmp_path: Path) -> Document:
    source = tmp_path / "product.png"
    Image.new("RGBA", (80, 60), (40, 150, 115, 255)).save(source)
    document = Document()
    document.create_new(320, 240)
    document.add_layer(
        "产品图",
        20,
        30,
        80,
        60,
        image_source=str(source),
        use_original_size=False,
        is_folder=False,
    )
    text = TextLayer(name="标题", x=40, y=120, width=180, height=60)
    text.text_content = "文案 A\n文案 B"
    text.current_text = "文案 A"
    text.font_size = 36
    document.add_text_layer(text)
    document._history_manager.clear()
    return document


def _three_text_document() -> Document:
    document = Document()
    document.create_new(320, 240)
    for index, name in enumerate(("底层", "中层", "顶层")):
        layer = TextLayer(name=name, x=20 + index * 20, y=30, width=100, height=40)
        layer.text_content = name
        layer.current_text = name
        document.add_text_layer(layer)
    document._history_manager.clear()
    return document


@pytest.mark.unit
def test_duplicate_image_layer_is_independent_unique_and_atomic(tmp_path: Path):
    document = _image_and_text_document(tmp_path)
    workspace = _workspace(document)
    workspace.selectLayer(0)
    original = document.layers[0]

    assert workspace.canDuplicateLayer is True
    assert workspace.duplicateSelectedLayer() is True
    assert len(document.layers) == 3
    duplicate = document.layers[1]
    assert workspace.selectedLayerIndex == 1
    assert duplicate is not original
    assert duplicate.name == "产品图 副本"
    assert duplicate._layer_id != original._layer_id
    assert duplicate.image_source == original.image_source
    assert (duplicate.x, duplicate.y) == (32, 42)

    duplicate.opacity = 0.25
    assert original.opacity == pytest.approx(1.0)

    assert workspace.undo() is True
    assert len(document.layers) == 2
    assert [layer.name for layer in document.layers] == ["产品图", "标题"]


@pytest.mark.unit
def test_duplicate_names_increment_without_collisions(tmp_path: Path):
    document = _image_and_text_document(tmp_path)
    workspace = _workspace(document)
    workspace.selectLayer(0)

    assert workspace.duplicateSelectedLayer() is True
    workspace.selectLayer(0)
    assert workspace.duplicateSelectedLayer() is True

    names = [layer.name for layer in document.layers]
    assert names[:3] == ["产品图", "产品图 副本 2", "产品图 副本"]
    assert len(set(names)) == len(names)


@pytest.mark.unit
def test_duplicate_text_preserves_candidates_and_style(tmp_path: Path):
    document = _image_and_text_document(tmp_path)
    workspace = _workspace(document)
    workspace.selectLayer(1)
    original = document.layers[1]

    assert workspace.duplicateSelectedLayer() is True
    duplicate = document.layers[2]
    assert duplicate.name == "标题 副本"
    assert duplicate.get_text_lines() == ["文案 A", "文案 B"]
    assert duplicate.current_text == "文案 A"
    assert duplicate.font_size == 36
    assert duplicate.get_text_lines() is not original.get_text_lines()

    duplicate.set_text_lines(["独立文案"])
    assert original.get_text_lines() == ["文案 A", "文案 B"]


@pytest.mark.unit
def test_move_selected_layer_forward_backward_and_undo():
    document = _three_text_document()
    workspace = _workspace(document)
    workspace.selectLayer(1)
    selected = document.layers[1]

    assert workspace.canMoveLayerForward is True
    assert workspace.canMoveLayerBackward is True
    assert workspace.moveSelectedLayer("forward") is True
    assert [layer.name for layer in document.layers] == ["底层", "顶层", "中层"]
    assert document.layers[workspace.selectedLayerIndex] is selected
    assert workspace.selectedLayerIndex == 2
    assert workspace.canMoveLayerForward is False

    assert workspace.undo() is True
    assert [layer.name for layer in document.layers] == ["底层", "中层", "顶层"]
    assert workspace.selectedLayerIndex == 1

    assert workspace.moveSelectedLayer("backward") is True
    assert [layer.name for layer in document.layers] == ["中层", "底层", "顶层"]
    assert workspace.selectedLayerIndex == 0


@pytest.mark.unit
def test_layer_stack_commands_respect_locks_and_boundaries():
    document = _three_text_document()
    workspace = _workspace(document)
    workspace.selectLayer(1)
    document.layers[2].locked = True
    workspace.selectionChanged.emit()

    assert workspace.canMoveLayerForward is False
    assert workspace.moveSelectedLayer("forward") is False
    assert [layer.name for layer in document.layers] == ["底层", "中层", "顶层"]

    document.layers[1].locked = True
    workspace.selectionChanged.emit()
    assert workspace.canDuplicateLayer is False
    assert workspace.canMoveLayerBackward is False
    assert workspace.duplicateSelectedLayer() is False

    document.layers[1].locked = False
    workspace.selectLayer(0)
    assert workspace.canMoveLayerBackward is False
    assert workspace.moveSelectedLayer("backward") is False


@pytest.mark.unit
def test_duplicate_and_order_survive_save_round_trip(tmp_path: Path):
    document = _image_and_text_document(tmp_path)
    workspace = _workspace(document)
    workspace.selectLayer(0)
    assert workspace.duplicateSelectedLayer() is True
    assert workspace.moveSelectedLayer("forward") is True
    project = tmp_path / "layer-stack.cmp"
    assert workspace.saveDocumentTo(str(project)) is True

    loaded = _workspace(Document())
    assert loaded.openDocument(str(project)) is True
    assert [layer.name for layer in loaded.document.layers] == ["产品图", "标题", "产品图 副本"]
    assert loaded.document.layers[0]._layer_id != loaded.document.layers[2]._layer_id
