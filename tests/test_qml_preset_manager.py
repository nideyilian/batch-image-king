import pickle
from pathlib import Path

import pytest
from PySide6.QtCore import QUrl

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
    assert preset["type"] == "single_document"
    assert preset["documentCount"] == 1
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
    assert view_model.duplicatePreset("missing") == ""
    assert view_model.exportPreset("missing", str(tmp_path / "missing.preset")) is False
    assert view_model.deletePreset("missing") is False


@pytest.mark.unit
def test_saving_current_project_preset_uses_only_active_tab(tmp_path: Path):
    workspace, sessions = _build_workspace()
    assert sessions.newDocument(640, 480) is True
    sessions.renameDocument(1, "方图")
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)

    assert view_model.saveCurrent("当前标签模板", "") is True
    preset = view_model.presets[0]
    assert preset["type"] == "single_document"
    assert preset["documentCount"] == 1
    assert preset["canvasSizes"] == ["640x480"]
    data = manager.load_preset(preset["id"])
    assert [item["name"] for item in data["documents"]] == ["方图"]


@pytest.mark.unit
def test_saving_all_project_preset_includes_every_open_tab(tmp_path: Path):
    workspace, sessions = _build_workspace()
    assert sessions.newDocument(640, 480) is True
    sessions.renameDocument(1, "方图")
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)

    assert view_model.saveAll("双标签模板", "") is True
    preset = view_model.presets[0]
    assert preset["type"] == "multi_document"
    assert preset["documentCount"] == 2
    data = manager.load_preset(preset["id"])
    assert [item["name"] for item in data["documents"]] == ["未命名-1.cmp", "方图"]


@pytest.mark.unit
def test_project_preset_transfer_and_duplicate_lifecycle(tmp_path: Path):
    workspace, sessions = _build_workspace()
    manager = PresetManager(app_dir=tmp_path / "source", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)
    assert view_model.saveCurrent("源模板", "可迁移") is True
    preset_id = view_model.presets[0]["id"]

    duplicate_id = view_model.duplicatePreset(preset_id)
    assert duplicate_id
    assert view_model.count == 2
    assert {preset["name"] for preset in view_model.presets} == {"源模板", "源模板 副本"}

    single_path = tmp_path / "源模板.preset"
    assert view_model.exportPreset(
        preset_id, QUrl.fromLocalFile(str(single_path)).toString()
    ) is True
    assert single_path.exists()

    collection_path = tmp_path / "预设合集.preset"
    assert view_model.exportAll(
        QUrl.fromLocalFile(str(collection_path)).toString()
    ) == 2
    assert collection_path.exists()

    target_manager = PresetManager(app_dir=tmp_path / "target", copy_initial=False)
    target_view_model = PresetManagerViewModel(
        workspace, sessions, manager=target_manager
    )
    assert target_view_model.importPreset(
        QUrl.fromLocalFile(str(collection_path)).toString()
    ) == 2
    assert target_view_model.count == 2


@pytest.mark.unit
def test_import_rejects_arbitrary_dictionary_without_creating_preset(tmp_path: Path):
    workspace, sessions = _build_workspace()
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)
    invalid_path = tmp_path / "invalid.preset"
    with invalid_path.open("wb") as file_obj:
        pickle.dump({"name": "不是文档"}, file_obj)

    assert view_model.importPreset(str(invalid_path)) == 0
    assert view_model.count == 0
    assert list(Path(manager.presets_dir).glob("*.cmp")) == []
    assert "格式不正确" in view_model.lastError


@pytest.mark.unit
def test_collection_import_is_atomic_when_one_item_is_invalid(tmp_path: Path):
    workspace, sessions = _build_workspace()
    source = PresetManager(app_dir=tmp_path / "source", copy_initial=False)
    source_id = source.save_preset_from_document("有效预设", workspace.document)
    valid_data = source.load_preset(source_id)
    collection_path = tmp_path / "broken-collection.preset"
    with collection_path.open("wb") as file_obj:
        pickle.dump(
            {
                "version": 2,
                "export_type": "all_presets",
                "presets": [
                    {"info": {"name": "有效预设"}, "data": valid_data},
                    {"info": {"name": "损坏预设"}, "data": {"unexpected": True}},
                ],
            },
            file_obj,
        )

    target = PresetManager(app_dir=tmp_path / "target", copy_initial=False)
    before_index = target.presets_index.copy()

    assert target.import_preset(collection_path) is None
    assert target.presets_index == before_index
    assert list(Path(target.presets_dir).glob("*.cmp")) == []


@pytest.mark.unit
def test_collection_export_is_atomic_when_one_preset_is_corrupt(tmp_path: Path):
    workspace, _sessions = _build_workspace()
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    valid_id = manager.save_preset_from_document("有效预设", workspace.document)
    corrupt_id = manager.save_preset_from_document("损坏预设", workspace.document)
    assert valid_id and corrupt_id
    corrupt_path = Path(manager.presets_dir) / f"{corrupt_id}.cmp"
    with corrupt_path.open("wb") as file_obj:
        pickle.dump({"unexpected": True}, file_obj)

    export_path = tmp_path / "existing.preset"
    export_path.write_bytes(b"keep-existing-export")

    assert manager.export_all_presets(export_path) == 0
    assert export_path.read_bytes() == b"keep-existing-export"
    assert "已损坏" in manager.last_error


@pytest.mark.unit
def test_saving_preset_without_open_documents_is_rejected(tmp_path: Path):
    document = Document()
    document.create_new(800, 800)
    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(
        workspace=workspace, include_initial_document=False
    )
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)

    assert view_model.saveCurrent("空工作区", "") is False
    assert view_model.saveAll("空工作区", "") is False
    assert "没有可保存" in view_model.lastError


@pytest.mark.unit
def test_qml_project_preset_drawer_exposes_complete_lifecycle_actions():
    qml_source = (
        Path(__file__).resolve().parents[1] / "app" / "qml" / "Main.qml"
    ).read_text(encoding="utf-8")

    for contract in (
        'label: "保存当前文档"',
        'label: "保存全部文档"',
        "projectPresets.saveCurrent(",
        "projectPresets.saveAll(",
        "projectPresets.duplicatePreset(",
        "projectPresets.importPreset(",
        "projectPresets.exportPreset(",
        "projectPresets.exportAll(",
        'tooltip: "导入预设"',
        'tooltip: "导出全部预设"',
        'tooltip: "复制预设"',
        'tooltip: "导出预设"',
    ):
        assert contract in qml_source
