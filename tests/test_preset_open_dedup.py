"""同一预设卡片只对应一套标签页：重复点击不新建、而是激活已有页。

这个行为有三处容易做错，测试分别锁住：

1. **判断依据用标题而非来源标记**。不同预设可以有同名页（两个都有「主图」），
   按标题会把 A 卡片误判成「B 已打开」，表现为「点 A 却激活了 B 的标签页」。
2. **判定发生在读盘之后**。虽然功能看起来对，但每次重复点击都要
   pickle + 重建图层树（几百毫秒），点几下就卡一下。
3. **清空时按标题关标签页**。与第 1 点同源：清空 A 会顺手关掉 B 的同名页。
"""
from __future__ import annotations

import os
import sys

import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.document import Document
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.qml.preview_image_provider import PreviewImageProvider
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
        document.add_layer("L0", 10, 20, 100, 70, image_source=image_path)
        documents.append(document)
    preset_id = manager.save_preset_documents(title, "", documents)
    assert preset_id
    return preset_id


@pytest.fixture()
def env(qapp, tmp_path):
    work_dir = str(tmp_path)
    manager = PresetManager(app_dir=work_dir, copy_initial=False)
    preset_a = _make_preset(manager, work_dir, "卡片A", ["A-主图", "A-细节", "A-场景"])
    preset_b = _make_preset(manager, work_dir, "卡片B", ["B-主图", "B-细节"])
    # 故意与 A 第一页同名，用来验证「不能按标题判定」
    preset_c = _make_preset(manager, work_dir, "卡片C", ["A-主图"])

    workspace = WorkspaceViewModel(
        preview_provider=PreviewImageProvider(), auto_render=False
    )
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
        "c": preset_c,
    }


@pytest.mark.unit
def test_first_click_opens_all_pages(env):
    """首次点击的行为不能变：全部页打开且激活第一页。"""
    loaded = env["vm"].loadPreset(env["a"])
    assert loaded == 3
    assert env["sessions"].count == 3
    assert env["sessions"].activeIndex == 0


@pytest.mark.unit
def test_repeated_clicks_do_not_create_duplicate_tabs(env):
    """核心断言：连点 10 次，标签页数量不变。"""
    env["vm"].loadPreset(env["a"])
    for _ in range(10):
        env["vm"].loadPreset(env["a"])
    assert env["sessions"].count == 3


@pytest.mark.unit
def test_repeated_click_activates_existing_tab(env):
    """重复点击要把已有标签页切到前台，而不是什么都不做。"""
    env["vm"].loadPreset(env["a"])
    env["sessions"].activateDocument(2)
    assert env["sessions"].activeIndex == 2  # 先离开该页

    env["vm"].loadPreset(env["a"])
    assert env["sessions"].activeIndex == 0, "没有切回该预设的第一页"
    active = env["sessions"].documentAt(env["sessions"].activeIndex)
    assert str(getattr(active, "source_preset_id", "")) == env["a"]


@pytest.mark.unit
def test_different_presets_are_independent(env):
    env["vm"].loadPreset(env["a"])
    env["vm"].loadPreset(env["b"])
    assert env["sessions"].count == 5
    env["vm"].loadPreset(env["a"])
    assert env["sessions"].count == 5, "点回 A 却新增了标签页"


@pytest.mark.unit
def test_repeated_click_does_not_reload_from_disk(env, monkeypatch):
    """重复点击不能再读一遍 .cmp + 重建图层树。

    光看「标签页数量不变」不足以发现退化：把去重判定挪到读盘之后，
    数量依然不变，但每次点击都要 pickle + 反序列化（几百毫秒），
    连点几下就是明显卡顿。这条断言锁住「先查内存、后读盘」的顺序。
    """
    manager = env["manager"]
    calls = {"count": 0}
    original = manager.load_preset

    def counting_load(preset_id):
        calls["count"] += 1
        return original(preset_id)

    monkeypatch.setattr(manager, "load_preset", counting_load)

    env["vm"].loadPreset(env["a"])
    first_calls = calls["count"]
    assert first_calls >= 1, "首次打开应该读盘"

    for _ in range(5):
        env["vm"].loadPreset(env["a"])
    assert calls["count"] == first_calls, (
        f"重复点击又读盘了 {calls['count'] - first_calls} 次"
    )


@pytest.mark.unit
def test_same_page_title_across_presets_is_not_same_preset(env):
    """A 和 C 都有名为「A-主图」的页，必须当作两个不同预设。

    按标题匹配的实现会在这里失败：打开 C 时误判「已存在」而直接激活 A。
    """
    env["vm"].loadPreset(env["a"])
    env["vm"].loadPreset(env["c"])
    assert env["sessions"].count == 4, "C 没有正常打开"
    active = env["sessions"].documentAt(env["sessions"].activeIndex)
    assert str(getattr(active, "source_preset_id", "")) == env["c"]

    before = env["sessions"].count
    env["vm"].loadPreset(env["c"])
    assert env["sessions"].count == before, "重复点 C 新增了标签页"


@pytest.mark.unit
def test_reopen_after_closing_all_pages(env):
    """全部关闭后再点卡片，应该正常重新打开，不能被「幽灵已存在」挡住。"""
    env["vm"].loadPreset(env["a"])
    sessions = env["sessions"]
    for index in range(sessions.count - 1, -1, -1):
        sessions.requestClose(index)
        if sessions.count > index:
            sessions.discardAndClose(index)
    assert sessions.count == 0

    loaded = env["vm"].loadPreset(env["a"])
    assert loaded == 3
    assert sessions.count == 3


@pytest.mark.unit
def test_partial_close_is_respected(env):
    """用户主动关掉几页后，再点卡片只激活、不把关掉的页塞回来。"""
    env["vm"].loadPreset(env["a"])
    sessions = env["sessions"]
    sessions.requestClose(2)
    if sessions.count > 2:
        sessions.discardAndClose(2)
    sessions.requestClose(1)
    if sessions.count > 1:
        sessions.discardAndClose(1)
    assert sessions.count == 1

    loaded = env["vm"].loadPreset(env["a"])
    assert sessions.count == 1, "把用户关掉的页又塞回来了"
    assert loaded == 1


@pytest.mark.unit
def test_source_marker_does_not_leak_into_preset_file(env):
    """来源标记是运行时状态，绝不能写进 .cmp。"""
    env["vm"].loadPreset(env["a"])
    data = env["manager"].load_preset(env["a"]) or {}
    for page in data.get("documents", []):
        assert "source_preset_id" not in page
        assert "source_preset_page" not in page


@pytest.mark.unit
def test_last_load_reused_flag_distinguishes_activate_from_open(env):
    """QML 靠 ``lastLoadReused`` 决定提示语。

    重复点击时说「已加载 3 个标签页」会让用户以为又开了 3 个，与实际相反；
    所以标志必须在「激活已有页」时为 True、「真正新建」时为 False。
    注意它挂在 stateChanged 上：重复点击时 presets 毫无变化，
    若挂在 presetsChanged 上则界面永远刷不到这个值。
    """
    env["vm"].loadPreset(env["a"])
    assert env["vm"].lastLoadReused is False, "首次打开被误标成「复用」"

    env["vm"].loadPreset(env["a"])
    assert env["vm"].lastLoadReused is True, "重复点击没有被标成「复用」"

    env["vm"].loadPreset(env["b"])
    assert env["vm"].lastLoadReused is False, "打开另一张卡片时应为 False"


@pytest.mark.unit
def test_close_workspace_tabs_uses_source_marker_not_title(env):
    """清空 A 时不得关闭 B 的同名页。

    这是第 1 点的反面：两处判定（打开/清空）必须用同一个口径，
    否则会出现「打开时认成两个、清空时当成一个」。
    """
    env["vm"].loadPreset(env["a"])
    env["vm"].loadPreset(env["c"])  # C 的唯一页名与 A 第一页相同
    sessions = env["sessions"]
    assert sessions.count == 4

    closed = env["vm"]._close_workspace_tabs_for_preset(env["a"])
    assert closed == 3, f"关闭数量 {closed}，应为 A 的 3 页"
    # 剩下的是 C 那一页
    assert sessions.count == 1
    remaining = sessions.documentAt(0)
    assert str(getattr(remaining, "source_preset_id", "")) == env["c"]
