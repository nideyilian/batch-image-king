"""卡片内标签页管理：回归测试。

锁住 docs/card-tab-management-design.md 定义的契约，防止退化。
每条测试对应设计文档第六节列出的一个具体风险。
"""
from __future__ import annotations

import os
import threading
import time

import pytest

from app.models.document import Document
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.utils.preset_manager import PresetManager


def _doc(name: str, x: int = 10) -> Document:
    document = Document()
    document.create_new(400, 300)
    document.tab_name = name
    document.original_tab_name = name
    document.add_layer("L0", x, 20, 200, 150, image_source=None, is_folder=False)
    return document


@pytest.fixture()
def manager(tmp_path):
    return PresetManager(app_dir=str(tmp_path), copy_initial=False)


@pytest.fixture()
def preset_id(manager):
    return manager.save_preset_documents(
        "预设A", "", [_doc("第一页"), _doc("第二页", 30), _doc("第三页", 60)]
    )


@pytest.fixture()
def view_model(manager):
    class _Workspace:
        operationsBlocked = False

        def _set_status(self, *_args, **_kwargs):
            pass

    return PresetManagerViewModel(workspace=_Workspace(), manager=manager)


def _titles(manager, preset_id):
    data = manager.load_preset(preset_id)
    return [d.get("original_tab_name") or d.get("name") for d in data["documents"]]


# ---------------------------------------------------------------- 改名


@pytest.mark.unit
def test_rename_writes_both_name_fields(manager, preset_id):
    """两个字段必须同时写：摘要取 original_tab_name or tab_name or name。"""
    ok, reason = manager.rename_document(preset_id, 1, "新名字")
    assert (ok, reason) == (True, "")
    page = manager.load_preset(preset_id)["documents"][1]
    assert page["name"] == "新名字"
    assert page["original_tab_name"] == "新名字"
    # 摘要（卡片的数据源）也必须读到新名
    assert manager.get_preset_summary(preset_id)["tab_names"][1] == "新名字"


@pytest.mark.unit
def test_rename_rejects_out_of_range_page(manager, preset_id):
    assert manager.rename_document(preset_id, -1, "x") == (False, "page_missing")
    assert manager.rename_document(preset_id, 99, "x") == (False, "page_missing")


@pytest.mark.unit
def test_rename_missing_preset(manager):
    assert manager.rename_document("不存在", 0, "x") == (False, "preset_missing")


# ---------------------------------------------------------------- 校验


@pytest.mark.unit
@pytest.mark.parametrize(
    "title,expect_reason",
    [
        ("", "empty"),
        ("   ", "empty"),
        ("x" * 41, "too_long"),
        ("a\nb", "control_char"),
        ("a\tb", "control_char"),
        ("第二页", "duplicate"),
        ("第二页  ", "duplicate"),
    ],
)
def test_validate_rejects(view_model, preset_id, title, expect_reason):
    verdict = view_model.validateDocumentTitle(preset_id, 0, title)
    assert verdict["ok"] is False
    assert verdict["reason"] == expect_reason


@pytest.mark.unit
def test_validate_length_counts_characters_not_bytes(view_model, preset_id):
    """40 个中文字必须通过：按 Unicode 码点算，不是 UTF-8 字节数。"""
    verdict = view_model.validateDocumentTitle(preset_id, 0, "中" * 40)
    assert verdict["ok"] is True
    assert verdict["changed"] is True
    too_long = view_model.validateDocumentTitle(preset_id, 0, "中" * 41)
    assert too_long["ok"] is False


@pytest.mark.unit
def test_validate_same_value_is_noop(view_model, preset_id):
    verdict = view_model.validateDocumentTitle(preset_id, 0, "第一页")
    assert verdict["ok"] is True
    assert verdict["changed"] is False
    padded = view_model.validateDocumentTitle(preset_id, 0, "  第一页  ")
    assert padded["ok"] is True
    assert padded["changed"] is False


@pytest.mark.unit
def test_duplicate_check_is_preset_scoped(manager, view_model, preset_id):
    """跨预设同名必须允许（页名不是主键）。"""
    other_id = manager.save_preset_documents("预设B", "", [_doc("第一页")])
    verdict = view_model.validateDocumentTitle(other_id, 0, "第二页")
    assert verdict["ok"] is True
    assert verdict["changed"] is True


@pytest.mark.unit
def test_validate_failure_does_not_write(view_model, manager, preset_id):
    before = manager.load_preset(preset_id)["documents"][0]["name"]
    result = view_model.renameDocument(preset_id, 0, "")
    assert result["ok"] is False
    assert manager.load_preset(preset_id)["documents"][0]["name"] == before


# ---------------------------------------------------------------- 信号粒度


@pytest.mark.unit
def test_rename_emits_titles_signal_not_presets(qapp, view_model, preset_id):
    """改名只发 documentTitlesChanged：presetsChanged 会让整屏卡片重建、闪一下。"""
    counter = {"titles": 0, "presets": 0}
    view_model.documentTitlesChanged.connect(lambda _pid: counter.__setitem__("titles", counter["titles"] + 1))
    view_model.presetsChanged.connect(lambda: counter.__setitem__("presets", counter["presets"] + 1))

    result = view_model.renameDocument(preset_id, 1, "改了")
    assert result["ok"] is True
    assert counter["titles"] == 1
    assert counter["presets"] == 0


@pytest.mark.unit
def test_rename_same_value_emits_no_signal(qapp, view_model, preset_id):
    counter = {"titles": 0}
    view_model.documentTitlesChanged.connect(lambda _pid: counter.__setitem__("titles", counter["titles"] + 1))
    result = view_model.renameDocument(preset_id, 0, "第一页")
    assert result["ok"] is True
    assert result["changed"] is False
    assert counter["titles"] == 0


# ---------------------------------------------------------------- 清空


@pytest.mark.unit
def test_close_all_clears_documents_but_keeps_preset(qapp, manager, view_model, preset_id):
    manager.set_category(preset_id, "促销卡券")
    result = view_model.closeAllDocuments(preset_id, False)
    assert result["ok"] is True
    assert result["cleared"] == 3

    data = manager.load_preset(preset_id)
    assert data["documents"] == []
    assert data["name"] == "预设A"
    assert os.path.isfile(manager._preset_file_path(preset_id))
    # 分类属于索引元数据，清空内容不该动它
    assert manager.presets_index[preset_id]["category"] == "促销卡券"
    # 分类属于索引元数据，清空内容不该动它
    assert manager.presets_index[preset_id]["category"] == "促销卡券"


@pytest.mark.unit
def test_close_all_syncs_index(qapp, manager, view_model, preset_id):
    view_model.closeAllDocuments(preset_id, False)
    info = manager.presets_index[preset_id]
    assert info["document_count"] == 0
    assert info["total_layers"] == 0
    assert info["canvas_sizes"] == []
    assert info["cover_index"] == 0


@pytest.mark.unit
def test_close_all_keeps_manual_order(qapp, manager, view_model, preset_id):
    order_before = manager.presets_index[preset_id].get("order")
    view_model.closeAllDocuments(preset_id, False)
    assert manager.presets_index[preset_id].get("order") == order_before


@pytest.mark.unit
def test_card_document_count_becomes_zero(qapp, view_model, preset_id):
    """OR-1 陷阱：0 是合法值，不能 `or 1` 兜成 1。"""
    view_model.closeAllDocuments(preset_id, False)
    card = next(item for item in view_model.presets if item["id"] == preset_id)
    assert card["documentCount"] == 0
    assert card["tabTitles"] == []


@pytest.mark.unit
def test_close_all_on_empty_returns_no_documents(qapp, view_model, preset_id):
    view_model.closeAllDocuments(preset_id, False)
    again = view_model.closeAllDocuments(preset_id, False)
    assert again["ok"] is False
    assert again["reason"] == "no_documents"


@pytest.mark.unit
def test_close_all_emits_presets_and_cleared(qapp, view_model, preset_id):
    counter = {"presets": 0, "cleared": 0}
    view_model.presetsChanged.connect(lambda: counter.__setitem__("presets", counter["presets"] + 1))
    view_model.documentsCleared.connect(lambda _pid: counter.__setitem__("cleared", counter["cleared"] + 1))
    view_model.closeAllDocuments(preset_id, False)
    assert counter["presets"] >= 1
    assert counter["cleared"] == 1


@pytest.mark.unit
def test_empty_preset_cannot_be_loaded(manager, view_model, preset_id):
    """空预设点「打开」必须被拒，而不是给用户一个空白工作区。"""
    view_model.closeAllDocuments(preset_id, False)
    assert view_model.loadPreset(preset_id) == 0
    assert view_model.lastError != ""


# ---------------------------------------------------------------- 单页关闭 + 封面让位


@pytest.mark.unit
def test_close_page_moves_cover_back(manager, preset_id):
    manager.set_cover_index(preset_id, 2)
    ok, remaining, reason, removed = manager.close_document(preset_id, 2)
    assert (ok, remaining, reason) == (True, 2, "")
    # 必须带回被删页的完整 payload，否则撤销只能还原空壳
    assert isinstance(removed, dict) and removed.get("name") is not None
    # 必须带回被删页的完整 payload，否则撤销只能还原空壳
    assert isinstance(removed, dict) and removed.get("name") is not None
    # 删的是封面页：后一页接不上（已是最后一页），退一格
    assert manager.presets_index[preset_id]["cover_index"] == 1


@pytest.mark.unit
def test_close_page_before_cover_shifts_cover(manager, preset_id):
    manager.set_cover_index(preset_id, 1)
    manager.close_document(preset_id, 0)
    assert manager.presets_index[preset_id]["cover_index"] == 0


@pytest.mark.unit
def test_close_page_after_cover_keeps_cover(manager, preset_id):
    manager.set_cover_index(preset_id, 0)
    manager.close_document(preset_id, 2)
    assert manager.presets_index[preset_id]["cover_index"] == 0


# ---------------------------------------------------------------- 撤销


@pytest.mark.unit
def test_undo_restores_full_snapshot(qapp, manager, view_model, preset_id):
    manager.rename_document(preset_id, 1, "改过的")
    view_model.closeAllDocuments(preset_id, False)
    result = view_model.undoClearDocuments(preset_id)
    assert result["ok"] is True
    assert result["restored"] == 3
    assert _titles(manager, preset_id) == ["第一页", "改过的", "第三页"]


@pytest.mark.unit
def test_undo_token_is_single_use(qapp, view_model, preset_id):
    view_model.closeAllDocuments(preset_id, False)
    assert view_model.undoClearDocuments(preset_id)["ok"] is True
    second = view_model.undoClearDocuments(preset_id)
    assert second["ok"] is False
    assert second["reason"] == "no_undo"


@pytest.mark.unit
def test_undo_expires_after_30s(qapp, view_model, preset_id):
    view_model.closeAllDocuments(preset_id, False)
    docs, _stamp = view_model._undo_tokens[preset_id]
    # 手动把时间戳往前拨 31 秒，避免真等
    view_model._undo_tokens[preset_id] = (docs, time.monotonic() - 31.0)
    result = view_model.undoClearDocuments(preset_id)
    assert result["ok"] is False
    assert result["reason"] == "no_undo"


# ---------------------------------------------------------------- 并发与一致性


@pytest.mark.unit
def test_stale_write_is_rejected(manager, preset_id):
    """mtime 乐观锁：读到旧副本后别的入口改了文件，写回必须被拒。"""
    data, mtime = manager._read_preset_for_write(preset_id)
    assert data is not None
    data["documents"][0]["name"] = "竞争写入"
    time.sleep(0.02)
    manager.rename_document(preset_id, 2, "别的入口改的")
    ok, reason = manager._commit_preset_write(preset_id, data, mtime)
    assert ok is False
    assert reason == "stale"
    # 别人的修改不能被覆盖
    assert _titles(manager, preset_id)[2] == "别的入口改的"


@pytest.mark.unit
def test_concurrent_renames_do_not_corrupt_file(manager, preset_id):
    """两个线程同时改名：最终文件必须是其中一次的完整结果，不能半写。"""
    errors = []

    def worker(index, title):
        try:
            manager.rename_document(preset_id, index, title)
        except Exception as error:  # noqa: BLE001
            errors.append(error)

    threads = [
        threading.Thread(target=worker, args=(0, "线程A")),
        threading.Thread(target=worker, args=(1, "线程B")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    data = manager.load_preset(preset_id)
    assert len(data["documents"]) == 3  # 结构没被写坏
    assert isinstance(data["documents"][0].get("name"), str)


@pytest.mark.unit
def test_atomic_write_leaves_no_temp_files(manager, preset_id):
    manager.rename_document(preset_id, 0, "改名")
    leftovers = [f for f in os.listdir(manager.presets_dir) if f.endswith(".tmp")]
    assert leftovers == []


@pytest.mark.unit
def test_write_failure_keeps_disk_unchanged(manager, preset_id, monkeypatch):
    """写盘失败时内存态不能劈叉：磁盘上仍是旧名。"""
    before = _titles(manager, preset_id)

    def boom(*_args, **_kwargs):
        raise OSError("磁盘已满")

    monkeypatch.setattr(manager, "_dump_pickle_atomic", boom)
    ok, reason = manager.rename_document(preset_id, 0, "不会成功")
    assert ok is False
    assert reason == "io_failed"
    assert _titles(manager, preset_id) == before


# ---------------------------------------------------------------- busy 互斥


@pytest.mark.unit
def test_busy_blocks_write_operations(qapp, view_model, preset_id):
    view_model._set_busy(True, "正在处理")
    rename = view_model.renameDocument(preset_id, 0, "并发")
    assert rename["ok"] is False
    assert rename["reason"] == "busy"
    clear = view_model.closeAllDocuments(preset_id, False)
    assert clear["ok"] is False
    assert clear["reason"] == "busy"
    view_model._set_busy(False)
    assert view_model.busy is False


# ---------------------------------------------------------------- 页列表数据


@pytest.mark.unit
def test_tab_titles_match_card_summary(qapp, view_model, preset_id):
    """页列表与卡片必须同源，不能各写一套取名规则。"""
    titles = view_model.tabTitles(preset_id)
    card = next(item for item in view_model.presets if item["id"] == preset_id)
    assert [t["title"] for t in titles] == [t["title"] for t in card["tabTitles"]]
    assert len(titles) == card["documentCount"]


@pytest.mark.unit
def test_tab_titles_marks_cover(qapp, manager, view_model, preset_id):
    manager.set_cover_index(preset_id, 1)
    titles = view_model.tabTitles(preset_id)
    assert [t["isCover"] for t in titles] == [False, True, False]


@pytest.mark.unit
def test_close_document_returns_removed_payload(manager, preset_id):
    """必须带回被删页的完整 payload，否则撤销只能还原空壳。"""
    ok, remaining, reason, removed = manager.close_document(preset_id, 1)
    assert (ok, remaining, reason) == (True, 2, "")
    assert isinstance(removed, dict)
    assert removed["name"] == "第二页"
    # 图层内容必须一起带回来
    assert isinstance(removed["layers"], list)
    assert len(removed["layers"]) == 1


@pytest.mark.unit
def test_close_document_keeps_order_of_remaining(manager, preset_id):
    manager.close_document(preset_id, 1)
    data = manager.load_preset(preset_id)
    assert [d["name"] for d in data["documents"]] == ["第一页", "第三页"]


@pytest.mark.unit
def test_view_model_close_document_syncs_card(qapp, view_model, preset_id):
    result = view_model.closeDocument(preset_id, 1)
    assert result["ok"] is True
    assert result["remaining"] == 2
    assert result["title"] == "第二页"
    card = next(item for item in view_model.presets if item["id"] == preset_id)
    assert card["documentCount"] == 2
    assert len(card["tabTitles"]) == 2


@pytest.mark.unit
def test_close_last_document_enters_empty_state(qapp, manager, view_model, preset_id):
    view_model.closeDocument(preset_id, 2)
    view_model.closeDocument(preset_id, 1)
    result = view_model.closeDocument(preset_id, 0)
    assert result["ok"] is True
    assert result["remaining"] == 0
    # 预设本身保留
    assert manager.load_preset(preset_id)["documents"] == []
    card = next(item for item in view_model.presets if item["id"] == preset_id)
    assert card["documentCount"] == 0


@pytest.mark.unit
def test_close_document_undo_restores_real_layers(qapp, manager, view_model, preset_id):
    """撤销必须还原真实图层，而不只是一个同名空页。"""
    view_model.closeDocument(preset_id, 1)
    undo = view_model.undoClearDocuments(preset_id)
    assert undo["ok"] is True
    page = manager.load_preset(preset_id)["documents"][1]
    assert page["name"] == "第二页"
    assert len(page["layers"]) == 1
    assert page["layers"][0]["name"] == "L0"


@pytest.mark.unit
def test_close_document_out_of_range(qapp, view_model, preset_id):
    assert view_model.closeDocument(preset_id, 9)["reason"] == "page_missing"
    assert view_model.closeDocument(preset_id, -1)["reason"] == "page_missing"


@pytest.mark.unit
def test_close_document_missing_preset(qapp, view_model):
    assert view_model.closeDocument("nope", 0)["reason"] == "preset_missing"


@pytest.mark.unit
def test_close_document_blocked_by_busy(qapp, view_model, preset_id):
    view_model._set_busy(True, "正在处理")
    result = view_model.closeDocument(preset_id, 0)
    assert result["ok"] is False
    assert result["reason"] == "busy"
    view_model._set_busy(False)


@pytest.mark.unit
def test_close_document_undo_uses_full_snapshot_not_removed_payload(
    qapp, manager, view_model, preset_id
):
    """撤销用的是「关闭前的完整 documents」而非 PM 返回的 removed。

    这是刻意的双保险：即使 PM 层将来改了 removed 的结构（或只返回部分字段），
    撤销仍然能还原全部内容。这条测试锁住「撤销不依赖 removed」这一点。
    """
    before = manager.load_preset(preset_id)["documents"]
    before_layers = [len(doc["layers"]) for doc in before]
    view_model.closeDocument(preset_id, 0)
    undo = view_model.undoClearDocuments(preset_id)
    assert undo["ok"] is True
    after = manager.load_preset(preset_id)["documents"]
    assert [len(doc["layers"]) for doc in after] == before_layers
    assert [doc["name"] for doc in after] == [doc["name"] for doc in before]


