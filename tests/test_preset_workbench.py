"""预设工作台数据层测试：缩略图缓存 + 搜索/排序/收藏/筛选。

覆盖三条容易静默失效的契约：
1. 缩略图缓存有效性按「缩略图不旧于源 .cmp」判断，源更新后必须重算。
2. visiblePresets 必须受 scope / category / 搜索词 / 排序共同约束。
3. 收藏切换要落进索引，且 presets 输出能反映出来。
"""

from pathlib import Path

import pytest

from app.models.document import Document
from app.models.text_layer import TextLayer
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.utils.preset_manager import PresetManager
from app.utils.preset_thumbnail import (
    PresetThumbnailService,
    is_cache_valid,
    thumb_path_for,
)


def _build_workspace():
    document = Document()
    document.create_new(600, 400)
    document.add_text_layer(TextLayer(name="标题", x=10, y=10, width=300, height=60))
    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    return workspace, sessions


def _build_vm(tmp_path: Path):
    workspace, sessions = _build_workspace()
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    return PresetManagerViewModel(workspace, sessions, manager=manager), manager


@pytest.mark.unit
def test_thumb_path_and_cache_validity(tmp_path: Path):
    """缓存失效判据：文件缺失 / 尺寸为 0 / 源比缩略图新。"""
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    source = presets_dir / "abc.cmp"
    source.write_bytes(b"fake")
    target = Path(thumb_path_for(str(presets_dir), "abc"))
    target.parent.mkdir(parents=True, exist_ok=True)

    assert not is_cache_valid(str(target), str(source)), "缩略图不存在时应判定失效"

    target.write_bytes(b"")
    assert not is_cache_valid(str(target), str(source)), "0 字节缩略图应判定失效"

    target.write_bytes(b"\x89PNG\r\n\x1a\n")
    assert is_cache_valid(str(target), str(source)), "缩略图不旧于源时应命中缓存"

    # 源更新后必须重算
    import os

    newer = source.stat().st_mtime + 5
    os.utime(source, (newer, newer))
    assert not is_cache_valid(str(target), str(source)), "源更新后缓存应失效"


@pytest.mark.unit
def test_thumbnail_service_request_many_counts_only_new(tmp_path: Path):
    """request_many 只把真正新入队的算进返回值，已在队列或命中缓存的不重复计数。"""
    presets_dir = tmp_path / "presets"
    presets_dir.mkdir()
    for name in ("a", "b"):
        (presets_dir / f"{name}.cmp").write_bytes(b"fake")

    service = PresetThumbnailService(str(presets_dir))
    try:
        queued = service.request_many(["a", "b", "", "a"])
        assert queued == 2, "空 id 与重复 id 不应计入"

        again = service.request_many(["a"], )
        assert again == 0, "同一预设已在待处理集合中时不应重复入队"
    finally:
        service.stop()


@pytest.mark.unit
def test_visible_presets_search_sort_and_scope(tmp_path: Path):
    """搜索 / 排序 / 收藏视图的组合过滤。"""
    view_model, manager = _build_vm(tmp_path)

    assert view_model.saveCurrent("女装主图", "夏季连衣裙") is True
    assert view_model.saveCurrent("男装主图", "秋季夹克") is True
    assert view_model.saveCurrent("食品海报", "空气炸锅蛋挞") is True
    assert view_model.count == 3

    # 搜索命中描述而不只是名称
    view_model.setSearchText("连衣裙")
    assert view_model.visibleCount == 1
    assert view_model.visiblePresets[0]["name"] == "女装主图"

    # 搜索大小写/空格不敏感
    view_model.setSearchText("  秋季  ")
    assert view_model.visibleCount == 1
    view_model.setSearchText("")
    assert view_model.visibleCount == 3

    # 名称排序
    view_model.setSortMode("name")
    names = [item["name"] for item in view_model.visiblePresets]
    assert names == sorted(names, key=str.casefold)

    # 收藏视图只含收藏项
    target_id = view_model.visiblePresets[0]["id"]
    assert view_model.toggleFavorite(target_id) is True
    assert view_model.favoriteCount == 1
    view_model.setScope("favorite")
    assert view_model.visibleCount == 1
    assert view_model.visiblePresets[0]["id"] == target_id

    # 取消收藏后收藏视图清空
    assert view_model.toggleFavorite(target_id) is True
    assert view_model.favoriteCount == 0
    assert view_model.visibleCount == 0

    view_model.setScope("all")
    assert view_model.visibleCount == 3


@pytest.mark.unit
def test_favorite_persists_into_index(tmp_path: Path):
    """收藏状态必须落进 presets_index.json，重建 VM 后仍然存在。"""
    view_model, manager = _build_vm(tmp_path)
    view_model.saveCurrent("持久化测试", "")
    preset_id = view_model.presets[0]["id"]

    view_model.toggleFavorite(preset_id)

    reloaded = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    summary = reloaded.get_preset_summary(preset_id)
    assert summary is not None
    assert summary["favorite"] is True


@pytest.mark.unit
def test_categories_aggregate_actual_values(tmp_path: Path):
    """分类清单来自预设实际取值，不写死。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    view_model.saveCurrent("乙", "")

    categories = view_model.categories
    assert len(categories) == 1
    assert categories[0]["name"] == "未分类"
    assert categories[0]["count"] == 2


@pytest.mark.unit
def test_recent_scope_requires_last_used(tmp_path: Path):
    """没有使用记录的预设不应出现在「最近使用」。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("从未使用", "")
    view_model.saveCurrent("用过一次", "")
    assert view_model.recentCount == 0

    used_id = [p["id"] for p in view_model.presets if p["name"] == "用过一次"][0]
    view_model.loadPreset(used_id)

    assert view_model.recentCount == 1
    view_model.setScope("recent")
    assert view_model.visibleCount == 1
    assert view_model.visiblePresets[0]["name"] == "用过一次"


# ---------------------------------------------------------------------------
# 分类与标签（工作台左侧分类树 / 右侧检查器编辑）
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_set_category_moves_preset_between_buckets(tmp_path: Path):
    """分类写入后，categories 聚合与 list 输出必须同步。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    view_model.saveCurrent("乙", "")
    target = view_model.presets[0]["id"]

    assert view_model.setPresetCategory(target, "女装") is True

    buckets = {item["name"]: item["count"] for item in view_model.categories}
    assert buckets == {"未分类": 1, "女装": 1}

    updated = [item for item in view_model.presets if item["id"] == target][0]
    assert updated["category"] == "女装"


@pytest.mark.unit
def test_empty_category_falls_back_to_uncategorized(tmp_path: Path):
    """空串/空白必须归入「未分类」，不能产生空分类节点。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    target = view_model.presets[0]["id"]

    assert view_model.setPresetCategory(target, "女装") is True
    assert view_model.setPresetCategory(target, "   ") is True

    updated = [item for item in view_model.presets if item["id"] == target][0]
    assert updated["category"] == "未分类"
    assert all(item["name"] for item in view_model.categories), "不应出现空名分类"


@pytest.mark.unit
def test_set_tags_splits_dedupes_and_keeps_order(tmp_path: Path):
    """中英文逗号都支持、去空、去重且保序。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    target = view_model.presets[0]["id"]

    assert view_model.setPresetTags(target, "主图，夏季, 女装,主图, ,") is True

    updated = [item for item in view_model.presets if item["id"] == target][0]
    assert updated["tags"] == ["主图", "夏季", "女装"]


@pytest.mark.unit
def test_search_matches_tags_and_category(tmp_path: Path):
    """搜索必须覆盖标签与分类，否则打了标签也搜不到。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲模板", "")
    view_model.saveCurrent("乙模板", "")
    target = view_model.presets[0]["id"]
    view_model.setPresetTags(target, "空气炸锅")
    view_model.setPresetCategory(target, "厨房电器")

    view_model.setSearchText("空气炸锅")
    assert view_model.visibleCount == 1
    assert view_model.visiblePresets[0]["id"] == target

    view_model.setSearchText("厨房电器")
    assert view_model.visibleCount == 1

    view_model.setSearchText("")
    assert view_model.visibleCount == 2


@pytest.mark.unit
def test_rename_category_moves_all_members(tmp_path: Path):
    """重命名分类必须批量改挂，且返回受影响条数。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    view_model.saveCurrent("乙", "")
    view_model.saveCurrent("丙", "")
    ids = [item["id"] for item in view_model.presets]
    view_model.setPresetCategory(ids[0], "女装")
    view_model.setPresetCategory(ids[1], "女装")

    affected = view_model.renameCategory("女装", "夏季女装")
    assert affected == 2

    buckets = {item["name"]: item["count"] for item in view_model.categories}
    assert buckets.get("夏季女装") == 2
    assert "女装" not in buckets


@pytest.mark.unit
def test_rename_category_follows_active_filter(tmp_path: Path):
    """正停在旧分类上时重命名，当前筛选要跟着改，否则左栏会突然空掉。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    target = view_model.presets[0]["id"]
    view_model.setPresetCategory(target, "女装")

    view_model.setCategory("女装")
    assert view_model.visibleCount == 1

    view_model.renameCategory("女装", "夏季女装")

    assert view_model.category == "夏季女装", "筛选条件应跟随重命名"
    assert view_model.visibleCount == 1, "重命名后不应把当前列表清空"


# ---------------------------------------------------------------------------
# 分类与标签（工作台左侧分类树 / 右侧检查器编辑）
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_set_category_moves_preset_between_buckets(tmp_path: Path):
    """分类写入后，categories 聚合与 list 输出必须同步。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    view_model.saveCurrent("乙", "")
    target = view_model.presets[0]["id"]

    assert view_model.setPresetCategory(target, "女装") is True

    buckets = {item["name"]: item["count"] for item in view_model.categories}
    assert buckets == {"未分类": 1, "女装": 1}

    updated = [item for item in view_model.presets if item["id"] == target][0]
    assert updated["category"] == "女装"


@pytest.mark.unit
def test_empty_category_falls_back_to_uncategorized(tmp_path: Path):
    """空串/空白必须归入「未分类」，不能产生空分类节点。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    target = view_model.presets[0]["id"]

    assert view_model.setPresetCategory(target, "女装") is True
    assert view_model.setPresetCategory(target, "   ") is True

    updated = [item for item in view_model.presets if item["id"] == target][0]
    assert updated["category"] == "未分类"
    assert all(item["name"] for item in view_model.categories), "不应出现空名分类"


@pytest.mark.unit
def test_set_tags_splits_dedupes_and_keeps_order(tmp_path: Path):
    """中英文逗号都支持、去空、去重且保序。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    target = view_model.presets[0]["id"]

    assert view_model.setPresetTags(target, "主图，夏季, 女装,主图, ,") is True

    updated = [item for item in view_model.presets if item["id"] == target][0]
    assert updated["tags"] == ["主图", "夏季", "女装"]


@pytest.mark.unit
def test_search_matches_tags_and_category(tmp_path: Path):
    """搜索必须覆盖标签与分类，否则打了标签也搜不到。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲模板", "")
    view_model.saveCurrent("乙模板", "")
    target = view_model.presets[0]["id"]
    view_model.setPresetTags(target, "空气炸锅")
    view_model.setPresetCategory(target, "厨房电器")

    view_model.setSearchText("空气炸锅")
    assert view_model.visibleCount == 1
    assert view_model.visiblePresets[0]["id"] == target

    view_model.setSearchText("厨房电器")
    assert view_model.visibleCount == 1

    view_model.setSearchText("")
    assert view_model.visibleCount == 2


@pytest.mark.unit
def test_rename_category_moves_all_members(tmp_path: Path):
    """重命名分类必须批量改挂，且返回受影响条数。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    view_model.saveCurrent("乙", "")
    view_model.saveCurrent("丙", "")
    ids = [item["id"] for item in view_model.presets]
    view_model.setPresetCategory(ids[0], "女装")
    view_model.setPresetCategory(ids[1], "女装")

    affected = view_model.renameCategory("女装", "夏季女装")
    assert affected == 2

    buckets = {item["name"]: item["count"] for item in view_model.categories}
    assert buckets.get("夏季女装") == 2
    assert "女装" not in buckets


@pytest.mark.unit
def test_rename_category_follows_active_filter(tmp_path: Path):
    """正停在旧分类上时重命名，当前筛选要跟着改，否则左栏会突然空掉。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    target = view_model.presets[0]["id"]
    view_model.setPresetCategory(target, "女装")

    view_model.setCategory("女装")
    assert view_model.visibleCount == 1

    view_model.renameCategory("女装", "夏季女装")

    assert view_model.category == "夏季女装", "筛选条件应跟随重命名"
    assert view_model.visibleCount == 1, "重命名后不应把当前列表清空"


@pytest.mark.unit
def test_presets_expose_canvas_sizes_and_layer_count(tmp_path: Path):
    """卡片数据必须含画布尺寸与图层数。

    回归护栏：``get_all_presets()`` 只返回索引项（没有 canvas_sizes），
    早先 VM 直接拿它当摘要用，导致卡片上所有预设都显示「未知画布」。
    VM 必须改走 ``get_preset_summary()`` 才能拿到真实尺寸。
    """
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("尺寸测试", "")

    item = view_model.presets[0]
    assert item["canvasSizes"] == ["600x400"], "必须解析出真实画布尺寸"
    assert item["totalLayers"] == 1, "必须解析出真实图层数"
    assert item["documentCount"] == 1


@pytest.mark.unit
def test_presets_report_missing_sources(tmp_path: Path):
    """素材路径失效时必须能被探测到，供卡片显示「素材缺失」。

    素材被用户删掉后预设仍可打开，只是渲染变空。不提示的话
    用户会以为是程序坏了。

    注意：TextLayer 不接收 image_source（反序列化后为 None），
    所以这里必须用真实的图片图层来构造场景，不能用文本图层。
    """
    import pickle

    from app.utils.preset_thumbnail import check_missing_sources

    # 造一个带图片图层的文档（image_source 指向不存在的路径）
    document = Document()
    document.create_new(600, 400)
    ghost = tmp_path / "gone" / "missing.png"
    document.add_layer("图片层", 0, 0, 200, 200, image_source=str(ghost))

    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)
    assert view_model.saveCurrent("缺素材测试", "") is True

    preset_id = view_model.presets[0]["id"]
    missing = check_missing_sources(preset_id, manager.presets_dir)
    assert missing == ["图片层"], f"应探测到缺失素材，实际 {missing}"


# ---------------------------------------------------------------------------
# 手动排序 / 封面指定 / 删除分类
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_manual_sort_seeds_order_preserving_current_view(tmp_path: Path):
    """首次进手动排序时，播种后的顺序必须和用户刚才看到的一致。

    否则用户一切到「手动排序」，列表会突然按另一种规则重排，
    看起来像"我什么都没动，顺序自己变了"。
    """
    view_model, manager = _build_vm(tmp_path)
    for name in ("甲", "乙", "丙", "丁"):
        view_model.saveCurrent(name, "")

    before = [item["name"] for item in view_model.visiblePresets]
    view_model.setSortMode("manual")
    after = [item["name"] for item in view_model.visiblePresets]

    assert after == before, "播种顺序必须与播种前的展示顺序一致"
    assert all(item["order"] != (1 << 30) for item in view_model.presets), "所有预设都应被播种"


@pytest.mark.unit
def test_move_preset_reorders_and_persists(tmp_path: Path):
    """拖拽重排后顺序必须落盘，重建 manager 仍然生效。"""
    view_model, manager = _build_vm(tmp_path)
    for name in ("甲", "乙", "丙", "丁"):
        view_model.saveCurrent(name, "")
    view_model.setSortMode("manual")

    original = [item["name"] for item in view_model.visiblePresets]
    moved_id = view_model.visiblePresets[0]["id"]
    assert view_model.movePreset(moved_id, 2) is True

    expected = original[1:3] + [original[0]] + original[3:]
    assert [item["name"] for item in view_model.visiblePresets] == expected

    # 新开一个 VM 读同一份索引，顺序必须保持
    reloaded_manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    orders = {
        p["name"]: p["order"]
        for p in reloaded_manager.get_all_presets()
    }
    assert orders[original[0]] == 2, "位次应已写入索引"


@pytest.mark.unit
def test_move_preset_clamps_out_of_range_target(tmp_path: Path):
    """越界的目标位次要被钳住，不能抛异常或丢数据。"""
    view_model, _ = _build_vm(tmp_path)
    for name in ("甲", "乙", "丙"):
        view_model.saveCurrent(name, "")
    view_model.setSortMode("manual")
    target_id = view_model.visiblePresets[0]["id"]

    assert view_model.movePreset(target_id, 999) is True
    assert view_model.visibleCount == 3
    assert view_model.visiblePresets[-1]["id"] == target_id

    assert view_model.movePreset(target_id, -50) is True
    assert view_model.visiblePresets[0]["id"] == target_id


@pytest.mark.unit
def test_cover_index_persists_and_candidates_exposed(tmp_path: Path):
    """多标签预设应暴露封面候选，且下标能持久化。

    单文档预设没有可选项，coverCandidates 必须是空列表——
    QML 靠这个决定要不要显示封面选择器。
    """
    document = Document()
    document.create_new(600, 400)
    document.add_text_layer(TextLayer(name="t", x=0, y=0, width=100, height=40))
    second = Document()
    second.create_new(800, 600)
    second.add_text_layer(TextLayer(name="t2", x=0, y=0, width=100, height=40))

    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)

    ids = manager.save_preset_documents("多页预设", "", [document, second], {})
    assert isinstance(ids, str) and ids

    item = [p for p in view_model.presets if p["id"] == ids][0]
    assert len(item["coverCandidates"]) == 2, "两页预设应给出 2 个候选"
    assert item["coverIndex"] == 0

    assert view_model.setCoverDocument(ids, 1) is True
    assert view_model.presets[0]["coverIndex"] == 1

    reloaded = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    assert reloaded.get_preset_summary(ids)["cover_index"] == 1


@pytest.mark.unit
def test_single_document_preset_has_no_cover_candidates(tmp_path: Path):
    """单文档预设不该有封面候选（QML 据此隐藏选择器）。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("单页", "")
    assert view_model.presets[0]["coverCandidates"] == []


@pytest.mark.unit
def test_delete_category_moves_members_to_uncategorized(tmp_path: Path):
    """删分类 = 成员归「未分类」，且不删任何预设。"""
    view_model, manager = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    view_model.saveCurrent("乙", "")
    view_model.saveCurrent("丙", "")
    ids = [item["id"] for item in view_model.presets]
    view_model.setPresetCategory(ids[0], "临时分类")
    view_model.setPresetCategory(ids[1], "临时分类")

    assert view_model.deleteCategory("临时分类") == 2
    assert view_model.count == 3, "预设不能被删除"
    assert all(item["category"] == "未分类" for item in view_model.presets)
    assert "临时分类" not in {c["name"] for c in view_model.categories}


@pytest.mark.unit
def test_delete_category_rejects_uncategorized(tmp_path: Path):
    """「未分类」是兜底桶，不允许删除。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    assert view_model.deleteCategory("未分类") == 0
    assert view_model.deleteCategory("") == 0


@pytest.mark.unit
def test_delete_active_category_falls_back_to_all(tmp_path: Path):
    """正停在被删分类上时，筛选要退回全部，否则停在空列表像丢了数据。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    target = view_model.presets[0]["id"]
    view_model.setPresetCategory(target, "待删分类")
    view_model.setCategory("待删分类")
    assert view_model.visibleCount == 1

    view_model.deleteCategory("待删分类")

    assert view_model.category == "", "筛选应退回全部"
    assert view_model.visibleCount == 1, "预设仍应可见"


# ---------------------------------------------------------------------------
# 手动排序 / 封面指定 / 删除分类
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_manual_sort_seeds_order_preserving_current_view(tmp_path: Path):
    """首次进手动排序时，播种后的顺序必须和用户刚才看到的一致。

    否则用户一切到「手动排序」，列表会突然按另一种规则重排，
    看起来像"我什么都没动，顺序自己变了"。
    """
    view_model, manager = _build_vm(tmp_path)
    for name in ("甲", "乙", "丙", "丁"):
        view_model.saveCurrent(name, "")

    before = [item["name"] for item in view_model.visiblePresets]
    view_model.setSortMode("manual")
    after = [item["name"] for item in view_model.visiblePresets]

    assert after == before, "播种顺序必须与播种前的展示顺序一致"
    assert all(item["order"] != (1 << 30) for item in view_model.presets), "所有预设都应被播种"


@pytest.mark.unit
def test_move_preset_reorders_and_persists(tmp_path: Path):
    """拖拽重排后顺序必须落盘，重建 manager 仍然生效。"""
    view_model, manager = _build_vm(tmp_path)
    for name in ("甲", "乙", "丙", "丁"):
        view_model.saveCurrent(name, "")
    view_model.setSortMode("manual")

    original = [item["name"] for item in view_model.visiblePresets]
    moved_id = view_model.visiblePresets[0]["id"]
    assert view_model.movePreset(moved_id, 2) is True

    expected = original[1:3] + [original[0]] + original[3:]
    assert [item["name"] for item in view_model.visiblePresets] == expected

    # 新开一个 VM 读同一份索引，顺序必须保持
    reloaded_manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    orders = {
        p["name"]: p["order"]
        for p in reloaded_manager.get_all_presets()
    }
    assert orders[original[0]] == 2, "位次应已写入索引"


@pytest.mark.unit
def test_move_preset_clamps_out_of_range_target(tmp_path: Path):
    """越界的目标位次要被钳住，不能抛异常或丢数据。"""
    view_model, _ = _build_vm(tmp_path)
    for name in ("甲", "乙", "丙"):
        view_model.saveCurrent(name, "")
    view_model.setSortMode("manual")
    target_id = view_model.visiblePresets[0]["id"]

    assert view_model.movePreset(target_id, 999) is True
    assert view_model.visibleCount == 3
    assert view_model.visiblePresets[-1]["id"] == target_id

    assert view_model.movePreset(target_id, -50) is True
    assert view_model.visiblePresets[0]["id"] == target_id


@pytest.mark.unit
def test_cover_index_persists_and_candidates_exposed(tmp_path: Path):
    """多标签预设应暴露封面候选，且下标能持久化。

    单文档预设没有可选项，coverCandidates 必须是空列表——
    QML 靠这个决定要不要显示封面选择器。
    """
    document = Document()
    document.create_new(600, 400)
    document.add_text_layer(TextLayer(name="t", x=0, y=0, width=100, height=40))
    second = Document()
    second.create_new(800, 600)
    second.add_text_layer(TextLayer(name="t2", x=0, y=0, width=100, height=40))

    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)

    ids = manager.save_preset_documents("多页预设", "", [document, second], {})
    assert isinstance(ids, str) and ids

    item = [p for p in view_model.presets if p["id"] == ids][0]
    assert len(item["coverCandidates"]) == 2, "两页预设应给出 2 个候选"
    assert item["coverIndex"] == 0

    assert view_model.setCoverDocument(ids, 1) is True
    assert view_model.presets[0]["coverIndex"] == 1

    reloaded = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    assert reloaded.get_preset_summary(ids)["cover_index"] == 1


@pytest.mark.unit
def test_single_document_preset_has_no_cover_candidates(tmp_path: Path):
    """单文档预设不该有封面候选（QML 据此隐藏选择器）。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("单页", "")
    assert view_model.presets[0]["coverCandidates"] == []


@pytest.mark.unit
def test_delete_category_moves_members_to_uncategorized(tmp_path: Path):
    """删分类 = 成员归「未分类」，且不删任何预设。"""
    view_model, manager = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    view_model.saveCurrent("乙", "")
    view_model.saveCurrent("丙", "")
    ids = [item["id"] for item in view_model.presets]
    view_model.setPresetCategory(ids[0], "临时分类")
    view_model.setPresetCategory(ids[1], "临时分类")

    assert view_model.deleteCategory("临时分类") == 2
    assert view_model.count == 3, "预设不能被删除"
    assert all(item["category"] == "未分类" for item in view_model.presets)
    assert "临时分类" not in {c["name"] for c in view_model.categories}


@pytest.mark.unit
def test_delete_category_rejects_uncategorized(tmp_path: Path):
    """「未分类」是兜底桶，不允许删除。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    assert view_model.deleteCategory("未分类") == 0
    assert view_model.deleteCategory("") == 0


@pytest.mark.unit
def test_delete_active_category_falls_back_to_all(tmp_path: Path):
    """正停在被删分类上时，筛选要退回全部，否则停在空列表像丢了数据。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("甲", "")
    target = view_model.presets[0]["id"]
    view_model.setPresetCategory(target, "待删分类")
    view_model.setCategory("待删分类")
    assert view_model.visibleCount == 1

    view_model.deleteCategory("待删分类")

    assert view_model.category == "", "筛选应退回全部"
    assert view_model.visibleCount == 1, "预设仍应可见"


# ---------------------------------------------------------------------------
# 多页缩略图（卡片页码圆点 + 悬停轮播）
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_thumb_path_pages_are_distinct(tmp_path: Path):
    """第 0 页沿用旧文件名，其余页加 __pN 后缀。

    这样加多页支持不会让已有缓存全部失效。
    """
    from app.utils.preset_thumbnail import thumb_path_for

    page0 = thumb_path_for(str(tmp_path), "abc", 0)
    page1 = thumb_path_for(str(tmp_path), "abc", 1)
    page3 = thumb_path_for(str(tmp_path), "abc", 3)

    assert page0.endswith("abc.png")
    assert page1.endswith("abc__p1.png")
    assert page3.endswith("abc__p3.png")
    assert len({page0, page1, page3}) == 3


@pytest.mark.unit
def test_thumb_path_invalid_page_falls_back_to_cover(tmp_path: Path):
    """非法页号不能抛异常，回退到首页路径。"""
    from app.utils.preset_thumbnail import thumb_path_for

    assert thumb_path_for(str(tmp_path), "abc", -5).endswith("abc.png")
    assert thumb_path_for(str(tmp_path), "abc", "x").endswith("abc.png")


@pytest.mark.unit
def test_page_thumbs_returns_empty_for_single_document(tmp_path: Path):
    """单文档预设不启用轮播（QML 靠空列表判断）。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("单页预设", "")
    assert view_model.presets[0]["pageThumbs"] == []


@pytest.mark.unit
def test_page_thumbs_skips_pages_not_rendered(tmp_path: Path):
    """只返回已落盘的页，没渲染好的页不能出现在列表里。

    否则 QML 会拿到不存在的路径，显示成破图。
    """
    from app.utils.preset_thumbnail import thumb_path_for

    document = Document()
    document.create_new(600, 400)
    document.add_text_layer(TextLayer(name="t", x=0, y=0, width=100, height=40))
    second = Document()
    second.create_new(800, 600)
    second.add_text_layer(TextLayer(name="t2", x=0, y=0, width=100, height=40))

    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)
    preset_id = manager.save_preset_documents("两页", "", [document, second], {})

    # 一页都没渲染时必须是空列表
    item = [p for p in view_model.presets if p["id"] == preset_id][0]
    assert item["pageThumbs"] == []
    assert len(item["coverCandidates"]) == 2, "但封面候选应已知有 2 页"

    # 手工放一张第 0 页的图，应只出现 1 项
    import os

    cover = thumb_path_for(manager.presets_dir, preset_id, 0)
    os.makedirs(os.path.dirname(cover), exist_ok=True)
    with open(cover, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)

    item = [p for p in view_model.presets if p["id"] == preset_id][0]
    assert len(item["pageThumbs"]) == 1, "只有第 0 页存在，就只返回它"


# ---------------------------------------------------------------------------
# 多页缩略图（卡片页码圆点 + 悬停轮播）
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_thumb_path_pages_are_distinct(tmp_path: Path):
    """第 0 页沿用旧文件名，其余页加 __pN 后缀。

    这样加多页支持不会让已有缓存全部失效。
    """
    from app.utils.preset_thumbnail import thumb_path_for

    page0 = thumb_path_for(str(tmp_path), "abc", 0)
    page1 = thumb_path_for(str(tmp_path), "abc", 1)
    page3 = thumb_path_for(str(tmp_path), "abc", 3)

    assert page0.endswith("abc.png")
    assert page1.endswith("abc__p1.png")
    assert page3.endswith("abc__p3.png")
    assert len({page0, page1, page3}) == 3


@pytest.mark.unit
def test_thumb_path_invalid_page_falls_back_to_cover(tmp_path: Path):
    """非法页号不能抛异常，回退到首页路径。"""
    from app.utils.preset_thumbnail import thumb_path_for

    assert thumb_path_for(str(tmp_path), "abc", -5).endswith("abc.png")
    assert thumb_path_for(str(tmp_path), "abc", "x").endswith("abc.png")


@pytest.mark.unit
def test_page_thumbs_returns_empty_for_single_document(tmp_path: Path):
    """单文档预设不启用轮播（QML 靠空列表判断）。"""
    view_model, _ = _build_vm(tmp_path)
    view_model.saveCurrent("单页预设", "")
    assert view_model.presets[0]["pageThumbs"] == []


@pytest.mark.unit
def test_page_thumbs_skips_pages_not_rendered(tmp_path: Path):
    """只返回已落盘的页，没渲染好的页不能出现在列表里。

    否则 QML 会拿到不存在的路径，显示成破图。
    """
    from app.utils.preset_thumbnail import thumb_path_for

    document = Document()
    document.create_new(600, 400)
    document.add_text_layer(TextLayer(name="t", x=0, y=0, width=100, height=40))
    second = Document()
    second.create_new(800, 600)
    second.add_text_layer(TextLayer(name="t2", x=0, y=0, width=100, height=40))

    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    manager = PresetManager(app_dir=tmp_path / "data", copy_initial=False)
    view_model = PresetManagerViewModel(workspace, sessions, manager=manager)
    preset_id = manager.save_preset_documents("两页", "", [document, second], {})

    # 一页都没渲染时必须是空列表
    item = [p for p in view_model.presets if p["id"] == preset_id][0]
    assert item["pageThumbs"] == []
    assert len(item["coverCandidates"]) == 2, "但封面候选应已知有 2 页"

    # 手工放一张第 0 页的图，应只出现 1 项
    import os

    cover = thumb_path_for(manager.presets_dir, preset_id, 0)
    os.makedirs(os.path.dirname(cover), exist_ok=True)
    with open(cover, "wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)

    item = [p for p in view_model.presets if p["id"] == preset_id][0]
    assert len(item["pageThumbs"]) == 1, "只有第 0 页存在，就只返回它"
