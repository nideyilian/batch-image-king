"""批量导出「端到端行为」测试：从素材目录到导出计划（2026-11-02）。

前面两个文件覆盖的是**纯逻辑**（策略解析、预算调节、文件名清洗）；
本文件走完整链路：

    临时素材目录 → get_batch_precomputer_v2 → analyze_document_with_context
    → create_export_plan → 检查 tasks / 文件名 / 诊断

为什么必须做这一步：``_generate_binding_combinations_v2``（723 行 / 138 分支）
与 ``export_batch_optimized_v2``（514 行 / 140 分支）本体至今零覆盖。
只测纯逻辑挡不住"调用链接错、参数传错、状态没同步"这类问题 ——
而拆分这两个函数时，最可能出错的恰恰是这些。

本文件同时锁住一个 2026-11-02 修掉的**用户可见缺陷**：
素材不足时诊断报"目标已达成"（详见 test_shortage_reports_gap_against_requested）。
"""

from __future__ import annotations

import os

import pytest

from app.utils.batch_export_precomputer_v2 import get_batch_precomputer_v2

# 需要真实文件系统读写 + 完整预计算链路
pytestmark = pytest.mark.integration


def _make_images(directory: str, count: int, prefix: str = "a") -> None:
    """造 count 个空图片文件（预计算只统计数量，不读像素）。"""
    for index in range(1, count + 1):
        open(os.path.join(directory, f"{prefix}_{index:02d}.jpg"), "wb").close()


def _folder_layer(directory: str, name: str = "素材层"):
    from types import SimpleNamespace

    return SimpleNamespace(
        name=name,
        visible=True,
        image_source=directory,
        is_folder=True,
        _is_folder=True,
        parent_group_id=None,
        type="layer",
    )


def _build(tmp_path, image_count: int, settings=None, prefix: str = "a"):
    """搭一个「单目录图层」的最小文档并完成分析，返回预计算器。"""
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir(exist_ok=True)
    _make_images(str(asset_dir), image_count, prefix)

    layer = _folder_layer(str(asset_dir))
    document = _make_document([layer], settings)
    analysis = {
        "binding_enabled": False,
        "binding_categories": [],
        "layer_analysis": {
            "visible_layers": [layer],
            "bound_layers": [],
            "unbound_layers": [layer],
        },
        "export_mode": "standard",
    }
    precomputer = get_batch_precomputer_v2(document, analysis)
    counted = precomputer.analyze_document_with_context()
    return precomputer, counted, asset_dir


def _make_document(layers, settings=None):
    from types import SimpleNamespace

    return SimpleNamespace(
        layers=list(layers),
        export_settings=dict(settings or {}),
        file_path="",
        binding_manager=None,
    )


def _plan(tmp_path, precomputer, count, template="img_{number:03d}",
          fmt="png", start_index=1, avoid_duplicates=True, traverse=False):
    out_dir = tmp_path / "out"
    out_dir.mkdir(exist_ok=True)
    return precomputer.create_export_plan(
        str(out_dir), count, template, fmt, start_index,
        avoid_duplicates, traverse, None,
    )


# ---------------------------------------------------------------------------
# 基础链路
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_single_folder_layer_counts_all_supported_images(tmp_path):
    """素材数量统计要认得各扩展名（这里是 4 种常见格式）。"""
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    for name in ("a_01.jpg", "b_02.jpeg", "c_03.png", "d_04.webp"):
        (asset_dir / name).write_bytes(b"")

    layer = _folder_layer(str(asset_dir))
    analysis = {
        "binding_enabled": False,
        "binding_categories": [],
        "layer_analysis": {"visible_layers": [layer], "bound_layers": [], "unbound_layers": [layer]},
        "export_mode": "standard",
    }
    precomputer = get_batch_precomputer_v2(_make_document([layer]), analysis)
    assert precomputer.analyze_document_with_context() == 4


@pytest.mark.unit
def test_plan_task_count_matches_available_material(tmp_path):
    """3 张素材、请求 3 张 → 恰好 3 个任务，文件名连续。"""
    precomputer, counted, _ = _build(tmp_path, 3)
    assert counted == 3

    plan = _plan(tmp_path, precomputer, 3)
    assert len(plan.tasks) == 3
    assert [task.filename for task in plan.tasks] == [
        "img_001.png", "img_002.png", "img_003.png",
    ]


@pytest.mark.unit
def test_plan_tasks_carry_resolved_file_paths(tmp_path):
    """每个任务都要有可用的绝对输出路径（执行阶段直接拿它落盘）。"""
    precomputer, _, _ = _build(tmp_path, 2)
    plan = _plan(tmp_path, precomputer, 2)

    out_dir = str(tmp_path / "out")
    for task in plan.tasks:
        assert os.path.isabs(task.file_path)
        assert os.path.dirname(task.file_path) == out_dir
        assert task.file_path.endswith(".png")


@pytest.mark.unit
def test_plan_hashes_are_unique_per_task(tmp_path):
    """同一批次内组合哈希必须互不相同 —— 去重与断点续传都依赖它。"""
    precomputer, _, _ = _build(tmp_path, 5)
    plan = _plan(tmp_path, precomputer, 5)

    hashes = [task.combination.combination_hash for task in plan.tasks]
    assert len(hashes) == len(set(hashes))


@pytest.mark.unit
def test_plan_layers_states_reference_real_files(tmp_path):
    """任务里的图层状态必须指向真实存在的素材文件。"""
    precomputer, _, asset_dir = _build(tmp_path, 3)
    plan = _plan(tmp_path, precomputer, 3)

    available = {
        os.path.normcase(os.path.abspath(str(asset_dir / name)))
        for name in os.listdir(asset_dir)
    }
    for task in plan.tasks:
        for path in task.combination.layer_states.values():
            assert os.path.normcase(os.path.abspath(path)) in available


# ---------------------------------------------------------------------------
# 素材不足（本次修复重点）
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_plan_never_exceeds_available_unique_combinations(tmp_path):
    """仅 2 张素材、请求 10 张：只能出 2 张，不能凭空造。"""
    precomputer, _, _ = _build(tmp_path, 2)
    plan = _plan(tmp_path, precomputer, 10)
    assert len(plan.tasks) == 2


@pytest.mark.unit
def test_shortage_reports_gap_against_requested(tmp_path):
    """诊断必须说出「请求 10、只出 2、缺 8」。

    历史缺陷：原先 shortage 用的是**被约束压低后**的 target（2），
    算出来缺口为 0 → primary_reasons 报 ``target_reached``（"目标已达成"）。
    用户在界面上看到"已达成"，却明明少了 8 张图，完全不知道是素材不够。
    """
    precomputer, _, _ = _build(tmp_path, 2)
    plan = _plan(tmp_path, precomputer, 10)

    shortage = plan.precompute_diagnostics["shortage_analysis"]
    assert shortage["requested_count"] == 10
    assert shortage["planned_count"] == 2
    assert shortage["shortage_count"] == 8, "缺口必须按用户请求量算，而不是压低后的目标"
    assert "target_reached" not in shortage["primary_reasons"], (
        "少给 8 张却报「目标已达成」—— 这正是历史缺陷的症状"
    )
    assert "target_capped_by_constraints" in shortage["primary_reasons"]


@pytest.mark.unit
def test_shortage_summary_is_actionable_for_user(tmp_path):
    """诊断摘要要给出人能看懂的建议，而不是只抛原因码。"""
    from app.utils.optimized_batch_executor import OptimizedBatchExportManager

    precomputer, _, _ = _build(tmp_path, 2)
    plan = _plan(tmp_path, precomputer, 10)
    summary = OptimizedBatchExportManager._summarize_precompute_diagnostics(
        plan.precompute_diagnostics
    )

    joined = " ".join(summary["recommendations"])
    assert "10" in joined and "2" in joined, f"建议里应写明请求数与实际数: {joined}"
    assert "素材" in joined


@pytest.mark.unit
def test_shortage_when_exactly_enough_material(tmp_path):
    """素材刚好够时不应误报短缺。"""
    precomputer, _, _ = _build(tmp_path, 3)
    plan = _plan(tmp_path, precomputer, 3)

    shortage = plan.precompute_diagnostics["shortage_analysis"]
    assert shortage["shortage_count"] == 0
    assert "target_reached" in shortage["primary_reasons"]


@pytest.mark.unit
def test_empty_asset_folder_produces_empty_plan(tmp_path):
    """空素材目录不能崩，返回空计划。"""
    asset_dir = tmp_path / "assets"
    asset_dir.mkdir()
    layer = _folder_layer(str(asset_dir))
    analysis = {
        "binding_enabled": False,
        "binding_categories": [],
        "layer_analysis": {"visible_layers": [layer], "bound_layers": [], "unbound_layers": [layer]},
        "export_mode": "standard",
    }
    precomputer = get_batch_precomputer_v2(_make_document([layer]), analysis)
    assert precomputer.analyze_document_with_context() == 0

    plan = _plan(tmp_path, precomputer, 5)
    assert len(plan.tasks) == 0


# ---------------------------------------------------------------------------
# 避重开 / 关
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_avoid_duplicates_allows_repeats_when_space_is_insufficient(tmp_path):
    """素材不足且开了避重：仍只出 2 张（不重复用同一张图）。"""
    precomputer, _, _ = _build(tmp_path, 2)
    plan = _plan(tmp_path, precomputer, 6, avoid_duplicates=True)
    assert len(plan.tasks) == 2


@pytest.mark.unit
def test_without_avoid_duplicates_material_can_repeat(tmp_path):
    """关掉避重后，2 张素材可以凑满 6 张（允许重复使用同一张图）。"""
    precomputer, _, _ = _build(tmp_path, 2)
    plan = _plan(tmp_path, precomputer, 6, avoid_duplicates=False)

    assert len(plan.tasks) == 6
    used = [os.path.basename(next(iter(t.combination.layer_states.values())))
            for t in plan.tasks]
    assert len(set(used)) == 2, "应只用这 2 张素材反复组合"


# ---------------------------------------------------------------------------
# 文件名模板
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("template,expected", [
    ("{number}", ["1.png", "2.png"]),
    ("x_{number:04d}", ["x_0001.png", "x_0002.png"]),
    ("n_{number:02d}", ["n_01.png", "n_02.png"]),
])
def test_number_placeholder_formats_correctly(tmp_path, template, expected):
    """``{number}`` 支持补齐格式，且扩展名由 file_format 决定。"""
    precomputer, _, _ = _build(tmp_path, 3)
    plan = _plan(tmp_path, precomputer, 2, template=template)
    assert [t.filename for t in plan.tasks] == expected


@pytest.mark.unit
def test_layer_placeholder_uses_material_main_name(tmp_path):
    """``{layer}`` 取自素材主名（去掉序号后缀）。"""
    precomputer, _, _ = _build(tmp_path, 3, prefix="product")
    plan = _plan(tmp_path, precomputer, 2, template="{layer}_{number}")
    names = [t.filename for t in plan.tasks]
    assert all(name.startswith("product_") for name in names), names


@pytest.mark.unit
def test_combo_placeholder_produces_unique_names(tmp_path):
    """``{combo}`` 必须让每个文件名互不相同（否则会互相覆盖）。"""
    precomputer, _, _ = _build(tmp_path, 4)
    plan = _plan(tmp_path, precomputer, 4, template="{combo}")
    names = [t.filename for t in plan.tasks]
    assert len(names) == len(set(names))


@pytest.mark.unit
def test_start_index_offsets_numbering(tmp_path):
    """``start_index`` 决定编号起点（断点续传时接着上一个文件编）。"""
    precomputer, _, _ = _build(tmp_path, 3)
    plan = _plan(tmp_path, precomputer, 2, template="n_{number:02d}", start_index=100)
    assert [t.filename for t in plan.tasks] == ["n_100.png", "n_101.png"]


@pytest.mark.unit
def test_file_format_controls_extension(tmp_path):
    precomputer, _, _ = _build(tmp_path, 2)
    for fmt in ("png", "jpg", "webp"):
        plan = _plan(tmp_path, precomputer, 2, fmt=fmt)
        assert all(t.filename.endswith(f".{fmt}") for t in plan.tasks), fmt


@pytest.mark.unit
def test_illegal_template_characters_are_cleaned(tmp_path):
    """模板里的非法字符要经过清洗，不能原样落到磁盘上。"""
    precomputer, _, _ = _build(tmp_path, 2)
    plan = _plan(tmp_path, precomputer, 2, template='a<b>:{number}')
    for task in plan.tasks:
        assert "<" not in task.filename and ">" not in task.filename
        assert ":" not in task.filename


# ---------------------------------------------------------------------------
# 诊断完整性
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_diagnostics_contains_fields_ui_depends_on(tmp_path):
    """这几个字段被执行器的诊断摘要直接读取，缺一个 UI 就白屏。"""
    precomputer, _, _ = _build(tmp_path, 3)
    plan = _plan(tmp_path, precomputer, 3)
    diag = plan.precompute_diagnostics

    for key in (
        "mode", "dedup_strategy", "requested_count", "generated_count",
        "attempts", "duplicate_attempts", "shortage_analysis",
        "combination_space", "dynamic_budget",
    ):
        assert key in diag, f"诊断缺少 {key}"


@pytest.mark.unit
def test_dedup_strategy_is_layered_only_in_binding_mode(tmp_path):
    """普通模式默认走 hash 去重，不应误用分层的文件签名策略。"""
    precomputer, _, _ = _build(tmp_path, 3)
    plan = _plan(tmp_path, precomputer, 3)
    assert plan.precompute_diagnostics["dedup_strategy"] == "hash"


@pytest.mark.unit
def test_plan_reports_unique_combination_count(tmp_path):
    """``unique_combinations`` 要与实际任务数一致（避重开启时）。"""
    precomputer, _, _ = _build(tmp_path, 4)
    plan = _plan(tmp_path, precomputer, 4, avoid_duplicates=True)
    assert plan.unique_combinations == len(plan.tasks)


@pytest.mark.unit
def test_cancel_callback_returns_empty_plan(tmp_path):
    """用户取消时要立刻返回空计划，不能继续算几十秒。"""
    precomputer, _, _ = _build(tmp_path, 10)
    out_dir = tmp_path / "out"
    out_dir.mkdir()

    plan = precomputer.create_export_plan(
        str(out_dir), 10, "x_{number}", "png", 1, True, False,
        lambda: True,  # 一进来就取消
    )
    assert len(plan.tasks) == 0
