from pathlib import Path

import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.utils.preset_manager import PresetManager


def _build_workspace():
    document = Document()
    document.create_new(900, 1200)
    document.add_text_layer(TextLayer(name="主标题", x=20, y=30, width=400, height=120))
    document.add_text_layer(TextLayer(name="副标题", x=20, y=180, width=400, height=80))
    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    return workspace, sessions


@pytest.mark.unit
def test_project_preset_crud_and_duplicate_name(tmp_path: Path):
    workspace, sessions = _build_workspace()
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)

    assert view_model.saveCurrent("电商模板", "竖版商品模板") is True
    assert view_model.count == 1
    preset = view_model.presets[0]
    assert preset["name"] == "电商模板"
    assert preset["totalLayers"] == 2
    assert preset["canvasSizes"] == ["900x1200"]

    assert view_model.saveCurrent("电商模板", "重复") is False
    assert "同名" in view_model.lastError
    assert view_model.renamePreset(preset["id"], "商品主图", "新版") is True
    assert view_model.presets[0]["name"] == "商品主图"
    assert view_model.deletePreset(preset["id"]) is True
    assert view_model.count == 0


@pytest.mark.unit
def test_loading_preset_appends_document_and_preserves_configuration(tmp_path: Path):
    workspace, sessions = _build_workspace()
    workspace.addGuide("vertical", 160)
    workspace.document.binding_manager.create_binding_group(
        "文案组",
        workspace.document.layers,
    )
    workspace.document.layer_size_match_manager.set_global_enabled(True)
    relation_id = workspace.document.layer_size_match_manager.add_relation(
        "主标题",
        ["副标题"],
        padding=8,
        auto_mask={"auto_mask_enabled": True, "auto_mask_threshold": 40},
    )
    assert relation_id

    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)
    assert view_model.saveCurrent("完整配置", "") is True
    preset_id = view_model.presets[0]["id"]

    assert view_model.loadPreset(preset_id) == 1
    assert sessions.count == 2
    loaded = workspace.document
    assert (loaded.canvas_width, loaded.canvas_height) == (900, 1200)
    assert loaded.view_settings["vertical_guides"] == [160.0]
    assert len(loaded.binding_manager.binding_groups) == 1
    assert loaded.layer_size_match_manager.global_enabled is True
    assert loaded.layer_size_match_manager.relations[0]["padding"] == 8
    assert loaded.layer_size_match_manager.relations[0]["auto_mask_enabled"] is True


@pytest.mark.unit
def test_invalid_preset_identifier_is_rejected(tmp_path: Path):
    workspace, sessions = _build_workspace()
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)

    assert view_model.loadPreset("missing") == 0
    assert view_model.deletePreset("missing") is False


@pytest.mark.unit
def test_saving_project_preset_includes_every_open_tab(tmp_path: Path):
    workspace, sessions = _build_workspace()
    assert sessions.newDocument(640, 480) is True
    sessions.renameDocument(1, "方图")
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)

    assert view_model.saveCurrent("双标签模板", "") is True
    preset = view_model.presets[0]
    assert preset["documentCount"] == 2
    data = manager.load_preset(preset["id"])
    assert [item["name"] for item in data["documents"]] == ["未命名-1.cmp", "方图"]
