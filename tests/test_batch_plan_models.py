"""批量导出计划数据模型的单元测试（P2：从超大文件抽离后可独立测试）。

这些测试是纯逻辑测试，不依赖 GUI / Qt / 真实 I/O，标记为 ``unit``。
"""
import pytest

from app.utils.batch_export_plan_models import (
    LayerCombination,
    ExportTask,
    PrecomputedExportPlan,
)


@pytest.mark.unit
def test_layer_combination_defaults():
    """未提供随机/参数 dict 时，__post_init__ 应补齐为空字典。"""
    combo = LayerCombination(
        index=0,
        layer_states={0: "/a.png"},
        layer_clone_settings={},
        combination_hash="h1",
        is_unique=True,
    )
    assert combo.index == 0
    assert combo.is_unique is True
    assert combo.layer_states == {0: "/a.png"}
    assert combo.random_transforms == {}
    assert combo.layer_parameters == {}


@pytest.mark.unit
def test_layer_combination_keeps_explicit_dicts():
    """显式传入的随机/参数 dict 不应被覆盖。"""
    rt = {0: {"random_offset_x": 5}}
    lp = {0: {"opacity": 1.0}}
    combo = LayerCombination(
        index=1,
        layer_states={},
        layer_clone_settings={},
        combination_hash="h2",
        is_unique=False,
        random_transforms=rt,
        layer_parameters=lp,
    )
    assert combo.random_transforms is rt
    assert combo.layer_parameters is lp


@pytest.mark.unit
def test_export_task_fields():
    """ExportTask 应正确承载组合与输出信息。"""
    combo = LayerCombination(0, {}, {}, "h", True)
    task = ExportTask(combo, "out.png", "/out.png", 1)
    assert task.combination is combo
    assert task.filename == "out.png"
    assert task.file_path == "/out.png"
    assert task.file_number == 1


@pytest.mark.unit
def test_precomputed_plan_defaults():
    """PrecomputedExportPlan 未提供诊断字段时默认为 None。"""
    plan = PrecomputedExportPlan(
        tasks=[],
        total_count=0,
        unique_combinations=0,
        estimated_time=0.0,
        memory_requirement_mb=0.0,
        optimization_suggestions=[],
    )
    assert plan.precompute_diagnostics is None
    assert plan.total_count == 0
    assert plan.tasks == []


@pytest.mark.unit
def test_precomputed_plan_with_tasks():
    """带任务与诊断的 Plan 应保持引用与数值。"""
    combo = LayerCombination(0, {0: "x"}, {}, "h", True)
    task = ExportTask(combo, "a.png", "/a.png", 1)
    plan = PrecomputedExportPlan(
        tasks=[task],
        total_count=1,
        unique_combinations=1,
        estimated_time=1.5,
        memory_requirement_mb=10.0,
        optimization_suggestions=["ok"],
        precompute_diagnostics={"scanned": 3},
    )
    assert len(plan.tasks) == 1
    assert plan.tasks[0] is task
    assert plan.precompute_diagnostics == {"scanned": 3}
