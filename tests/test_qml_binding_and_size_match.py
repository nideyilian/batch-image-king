from pathlib import Path

import pytest

from app.models.document import Document
from app.models.layer_new import Layer
from app.models.text_layer import TextLayer
from app.qml.viewmodels.binding_manager_view_model import BindingManagerViewModel
from app.qml.viewmodels.size_match_view_model import SizeMatchViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace():
    document = Document()
    document.create_new(800, 600)
    document.layers.append(Layer(name="背景孔位", x=0, y=0, width=800, height=600, parent=document))
    document.layers.append(Layer(name="商品图", x=80, y=60, width=300, height=300, parent=document))
    text = TextLayer(name="标题", x=40, y=450, width=500, height=80)
    text.text_content = "春季新品\n夏季限定"
    document.add_text_layer(text)
    document._history_manager.clear()
    document.save_state("初始")
    return WorkspaceViewModel(document=document, auto_render=False)


@pytest.mark.unit
def test_binding_group_crud_and_candidate_sources():
    workspace = _workspace()
    bindings = BindingManagerViewModel(workspace)

    assert [item["name"] for item in bindings.layerOptions] == ["背景孔位", "商品图", "标题"]
    assert bindings.layerOptions[-1]["type"] == "文字"
    assert bindings.layerOptions[-1]["candidateCount"] == 2

    group_id = bindings.createGroup("商品组合", [0, 1])
    assert group_id
    assert bindings.groups[0]["layerNames"] == ["背景孔位", "商品图"]
    assert bindings.createGroup("商品组合", [1, 2]) == ""
    assert bindings.renameGroup(group_id, "主图组合") is True
    assert bindings.groups[0]["name"] == "主图组合"
    assert bindings.setGlobalEnabled(False) is True
    assert bindings.globalEnabled is False
    assert bindings.deleteGroup(group_id) is True
    assert bindings.groups == []


@pytest.mark.unit
def test_size_match_relation_parameters_and_undo():
    workspace = _workspace()
    size_match = SizeMatchViewModel(workspace)

    relation_id = size_match.addRelation(
        "背景孔位",
        ["商品图"],
        6,
        False,
        True,
        True,
        48,
        12,
    )
    assert relation_id
    relation = size_match.relations[0]
    assert relation["padding"] == 6
    assert relation["autoRotate"] is True
    assert relation["autoMaskEnabled"] is True
    assert relation["autoMaskThreshold"] == 48
    assert relation["autoMaskTolerance"] == 12

    assert size_match.setGlobalEnabled(True) is True
    assert workspace.document.layer_size_match_manager.get_active_relations()
    assert workspace.undo() is True
    assert size_match.globalEnabled is False
    assert len(size_match.relations) == 1
    assert size_match.removeRelation(relation_id) is True
    assert size_match.relations == []


@pytest.mark.unit
def test_binding_and_size_match_round_trip_and_document_isolation(tmp_path: Path):
    workspace = _workspace()
    bindings = BindingManagerViewModel(workspace)
    size_match = SizeMatchViewModel(workspace)
    assert bindings.createGroup("绑定组", [0, 1])
    assert size_match.addRelation("背景孔位", ["商品图"], 4, False, False, True, 32, 18)
    assert size_match.setGlobalEnabled(True)

    project = tmp_path / "relations.cmp"
    assert workspace.saveDocumentTo(str(project)) is True
    second = _workspace()
    second_bindings = BindingManagerViewModel(second)
    assert second_bindings.groups == []

    assert second.openDocument(str(project)) is True
    second_size = SizeMatchViewModel(second)
    assert second_bindings.groups[0]["name"] == "绑定组"
    assert second_size.globalEnabled is True
    assert second_size.relations[0]["targetNames"] == ["商品图"]
