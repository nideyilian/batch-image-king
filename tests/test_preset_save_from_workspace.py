"""「把工作区改动保存回预设卡片」的契约测试。

这个能力之前**完全不存在**：`saveCurrent` / `saveAll` 都是「另存为新预设」
（每次生成新 id），用户在工作区改完图后无法存回原卡片，只能另存为，
于是库里堆出一堆重复预设。用户原话是「修改后保存的功能似乎也没实现」。

本测试锁住四条契约：
1. 覆盖保存到**同一张卡片**，不新增预设条目
2. 只收集 `source_preset_id` 匹配的页，不把别的预设的页混进来
3. 没打开过的预设拒绝保存（返回 `not_open`）
4. 保存后再从磁盘加载，能读到改动（图层、画布尺寸、页名）
"""
from __future__ import annotations

import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.utils.preset_manager import PresetManager


def _make_preset(manager, work_dir: str, title: str, page_names):
    documents = []
    for name in page_names:
        document = Document()
        document.create_new(400, 300)
        document.tab_name = name
        document.original_tab_name = name
        image_path = os.path.join(work_dir, f"{title}_{name}.png")
        Image.new("RGBA", (120, 90), (60, 110, 160, 255)).save(image_path)
        document.add_layer("原图层", 10, 20, 100, 70, image_source=image_path)
        documents.append(document)
    preset_id = manager.save_preset_documents(title, "", documents)
    assert preset_id
    return preset_id


@pytest.fixture()
def env(qapp, tmp_path):
    work_dir = str(tmp_path)
    manager = PresetManager(app_dir=work_dir, copy_initial=False)
    preset_a = _make_preset(manager, work_dir, "卡片A", ["主图", "细节图"])
    preset_b = _make_preset(manager, work_dir, "卡片B", ["B主图"])
    workspace = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace, include_initial_document=False)
    view_model = PresetManagerViewModel(
        workspace=workspace, sessions=sessions, manager=manager
    )
    return {
        "manager": manager,
        "sessions": sessions,
        "vm": view_model,
        "a": preset_a,
        "b": preset_b,
        "work_dir": work_dir,
    }


@pytest.mark.unit
def test_save_overwrites_same_preset_without_creating_new(env):
    """核心契约：存回原卡片，不新增条目。

    这条是「另存为」与「保存」的分界线。若实现用了 save_preset_documents，
    预设数量会增加、id 会变，用户看到的是一张新卡。
    """
    manager, sessions, vm = env["manager"], env["sessions"], env["vm"]
    vm.loadPreset(env["a"])
    doc = sessions.documentAt(0)
    doc.canvas_width = 888

    before = len(manager.get_all_presets())
    result = vm.savePresetFromWorkspace(env["a"])
    after = len(manager.get_all_presets())

    assert result["ok"] is True
    assert after == before, "保存不应该新增预设"

    raw = manager.load_preset(env["a"]) or {}
    assert raw["documents"][0]["canvas_width"] == 888


@pytest.mark.unit
def test_save_persists_new_layers(env):
    """图层增删是用户在编辑器里最常做的改动，必须能存住。"""
    manager, sessions, vm = env["manager"], env["sessions"], env["vm"]
    vm.loadPreset(env["a"])
    sessions.documentAt(0).add_layer(
        "用户新加", 50, 60, 120, 90, image_source=None, is_folder=False
    )
    assert vm.savePresetFromWorkspace(env["a"])["ok"] is True

    raw = manager.load_preset(env["a"]) or {}
    names = [layer.get("name") for layer in raw["documents"][0]["layers"]]
    assert "用户新加" in names


@pytest.mark.unit
def test_save_includes_renamed_page_title(env):
    """页名改过之后保存，磁盘上必须是新名字。

    注意要同时看 `name` 和 `original_tab_name`：
    摘要取名走 ``original_tab_name or tab_name or name``，
    只写一个会让卡片继续显示旧名。
    """
    manager, sessions, vm = env["manager"], env["sessions"], env["vm"]
    vm.loadPreset(env["b"])
    doc = sessions.documentAt(sessions.activeIndex)
    doc.tab_name = "新页名"
    doc.original_tab_name = "新页名"
    assert vm.savePresetFromWorkspace(env["b"])["ok"] is True

    raw = manager.load_preset(env["b"]) or {}
    page = raw["documents"][0]
    assert page["name"] == "新页名"
    assert page["original_tab_name"] == "新页名"


@pytest.mark.unit
def test_save_does_not_mix_pages_from_other_presets(env):
    """工作区同时开着 A 和 B 时，存 A 不能把 B 的页写进去。"""
    manager, sessions, vm = env["manager"], env["sessions"], env["vm"]
    vm.loadPreset(env["a"])
    vm.loadPreset(env["b"])

    result = vm.savePresetFromWorkspace(env["a"])
    assert result["ok"] is True
    assert result["saved"] == 2, f"只该保存 A 的 2 页，实际 {result['saved']}"

    raw = manager.load_preset(env["a"]) or {}
    names = [page["name"] for page in raw["documents"]]
    assert "B主图" not in names


@pytest.mark.unit
def test_save_rejected_when_preset_not_open(env):
    """没打开的预设没有可保存的内容，必须拒绝而不是静默清空它。"""
    work_dir = env["work_dir"]
    other = _make_preset(env["manager"], work_dir, "未打开", ["x"])
    result = env["vm"].savePresetFromWorkspace(other)
    assert result["ok"] is False
    assert result["reason"] == "not_open"
    # 关键：被拒绝时不能改动磁盘
    raw = env["manager"].load_preset(other) or {}
    assert len(raw["documents"]) == 1


@pytest.mark.unit
def test_save_rejected_for_missing_preset(env):
    result = env["vm"].savePresetFromWorkspace("不存在的id")
    assert result["ok"] is False
    assert result["reason"] == "preset_missing"


@pytest.mark.unit
def test_reload_after_save_returns_edited_content(env):
    """端到端：保存 → 关闭全部 → 重新打开，内容必须是编辑后的。"""
    manager, sessions, vm = env["manager"], env["sessions"], env["vm"]
    vm.loadPreset(env["a"])
    doc = sessions.documentAt(0)
    doc.canvas_width = 777
    doc.add_layer("新增层", 30, 40, 90, 70, image_source=None, is_folder=False)
    assert vm.savePresetFromWorkspace(env["a"])["ok"] is True

    for index in range(sessions.count - 1, -1, -1):
        sessions.requestClose(index)
        if sessions.count > index:
            sessions.discardAndClose(index)
    assert sessions.count == 0

    vm.loadPreset(env["a"])
    reloaded = sessions.documentAt(0)
    assert reloaded.canvas_width == 777
    assert "新增层" in [layer.name for layer in reloaded.layers]


@pytest.mark.unit
def test_can_save_and_page_count_reflect_open_state(env):
    """QML 靠这两个查询决定按钮可用性与文案。"""
    vm, sessions = env["vm"], env["sessions"]
    assert vm.canSavePresetFromWorkspace(env["a"]) is False
    vm.loadPreset(env["a"])
    assert vm.canSavePresetFromWorkspace(env["a"]) is True
    assert vm.openPageCount(env["a"]) == 2
    assert vm.canSavePresetFromWorkspace(env["b"]) is False


@pytest.mark.unit
def test_save_updates_cover_index_when_page_count_shrinks(env):
    """用户关掉几页后保存，封面下标不能越界。

    否则卡片封面取一个不存在的页，缩略图会变成空白。
    """
    manager, sessions, vm = env["manager"], env["sessions"], env["vm"]
    vm.loadPreset(env["a"])
    assert manager.set_cover_index(env["a"], 1)

    # 关掉第 2 页，只剩 1 页
    sessions.requestClose(1)
    if sessions.count > 1:
        sessions.discardAndClose(1)
    assert sessions.count == 1

    assert vm.savePresetFromWorkspace(env["a"])["ok"] is True
    info = manager.presets_index.get(env["a"], {})
    assert int(info.get("cover_index") or 0) == 0, f"cover_index={info.get('cover_index')}"
