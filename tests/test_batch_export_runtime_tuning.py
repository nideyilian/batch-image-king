"""批量导出「执行阶段调参与诊断汇总」行为测试（2026-11-02）。

接着 `test_batch_export_dedup_budget.py`（预计算阶段的去重/预算），
本文件覆盖**执行阶段**的纯逻辑：

- ``_derive_runtime_tuning_plan``：按作品数与格式推导 workers / io profile
- ``_should_retry_with_default_runtime``：调参失败后是否值得用默认参数重试
- ``_summarize_precompute_diagnostics``：把诊断转成用户能看懂的建议
- ``_record_export_report``：报告落内存 + 历史 + jsonl

这些都在 ``export_batch_optimized_v2``（514 行 / 140 分支）内部被调用，
是拆分它时必须先能验证的部分。

顺带修掉一个返回类型缺陷：``_should_retry_with_default_runtime`` 原先
在"两个覆盖项都为空"时返回 ``None`` 而非 ``False``（表达式短路值泄漏），
已显式 ``bool()`` 收口，见 test_retry_decision_always_returns_bool。
"""

from __future__ import annotations

import json

import pytest

from app.utils.optimized_batch_executor import (
    OptimizedBatchExportManager,
    _should_retry_with_default_runtime,
)

Manager = OptimizedBatchExportManager


class _Doc:
    """最小文档替身：只提供调参逻辑访问的 export_settings。"""

    def __init__(self, settings=None):
        self.export_settings = settings or {}


def _plan(planned_count: int, file_format: str = "png", *, doc=None, reasons=None):
    summary = {"shortage": {"primary_reasons": list(reasons or [])}}
    return Manager._derive_runtime_tuning_plan(
        doc or _Doc(), summary, planned_count, file_format
    )


# ---------------------------------------------------------------------------
# 运行时调参计划
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_tuning_disabled_returns_minimal_plan():
    """用户关掉自动调参时，只回一个 enabled=False，不要带任何推导值。"""
    plan = _plan(300, "png", doc=_Doc({"auto_runtime_tuning_enabled": False}))
    assert plan == {"enabled": False}


@pytest.mark.unit
def test_small_batch_uses_at_most_two_workers():
    """≤20 张时限制在 1~2 个 worker：小任务上多线程只会互相抢 CPU。"""
    for count in (1, 5, 20):
        plan = _plan(count)
        assert 1 <= plan["derived_workers"] <= 2, (count, plan)


@pytest.mark.unit
def test_medium_batch_does_not_override_workers():
    """20 < count < 300 且无特殊原因时不覆盖 workers（交给默认策略）。"""
    for count in (50, 120, 299):
        plan = _plan(count)
        assert plan["derived_workers"] is None, (count, plan)


@pytest.mark.unit
def test_large_batch_capped_at_six_workers():
    """≥300 张才提速，但上限 6 —— 再高会挤占 UI 线程（曾是激进策略的教训）。"""
    for count in (300, 1000, 5000):
        plan = _plan(count)
        assert 2 <= plan["derived_workers"] <= 6, (count, plan)


@pytest.mark.unit
def test_combination_space_limited_small_batch_damps_down():
    """素材空间受限且量小时，降低并发并把 IO 调成偏向体积。"""
    plan = _plan(50, "jpg", reasons=["combination_space_limited"])
    assert plan["derived_workers"] <= 3
    assert plan["derived_io_profile"] == "size"
    assert "combination_space_limited" in plan["reasons"]


@pytest.mark.unit
def test_combination_space_limited_ignored_for_large_batch():
    """量已经很大时不再因"空间受限"降并发（否则大任务永远快不起来）。"""
    plan = _plan(300, "jpg", reasons=["combination_space_limited"])
    assert plan["derived_workers"] >= 2


@pytest.mark.unit
def test_png_and_bmp_large_batch_prefer_speed():
    """无损格式大任务走 speed —— 编码慢，优先吞吐。"""
    for fmt in ("png", "PNG", "bmp"):
        assert _plan(120, fmt)["derived_io_profile"] == "speed", fmt


@pytest.mark.unit
def test_jpeg_large_batch_does_not_force_speed_profile():
    """JPEG 本身编码快，不需要专门的 speed profile。"""
    assert _plan(500, "jpg")["derived_io_profile"] is None
    assert _plan(500, "jpeg")["derived_io_profile"] is None


@pytest.mark.unit
def test_small_png_batch_does_not_switch_io_profile():
    """speed profile 只在 ≥120 张时启用（小任务切了没收益）。"""
    assert _plan(119, "png")["derived_io_profile"] is None


@pytest.mark.unit
def test_tuning_plan_always_declares_no_manual_override():
    """自动推导出的计划不得声称是用户手改的（UI 据此显示"已自动优化"）。"""
    plan = _plan(300, "png")
    assert plan["manual_worker_override"] is False
    assert plan["manual_io_override"] is False
    assert plan["planned_count"] == 300


@pytest.mark.unit
def test_tuning_plan_tolerates_missing_shortage_section():
    """预计算摘要缺 shortage 字段时不能崩。"""
    plan = Manager._derive_runtime_tuning_plan(_Doc(), {}, 300, "png")
    assert plan["enabled"] is True
    assert plan["reasons"] == []


# ---------------------------------------------------------------------------
# 重试决策
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_retry_allowed_when_tuning_applied_and_nothing_exported():
    decision = _should_retry_with_default_runtime(
        success=False,
        runtime_tuning={"enabled": True, "derived_workers": 3},
        completed_count=0,
        canceled=False,
    )
    assert decision is True


@pytest.mark.unit
def test_no_retry_when_successful():
    assert _should_retry_with_default_runtime(
        success=True,
        runtime_tuning={"enabled": True, "derived_workers": 3},
        completed_count=0,
        canceled=False,
    ) is False


@pytest.mark.unit
def test_no_retry_when_any_file_already_exported():
    """已经出过文件就不能重试 —— 否则会产出重复文件、覆盖已有结果。"""
    assert _should_retry_with_default_runtime(
        success=False,
        runtime_tuning={"enabled": True, "derived_workers": 3},
        completed_count=1,
        canceled=False,
    ) is False


@pytest.mark.unit
def test_no_retry_when_canceled():
    """用户主动取消不是"失败"，重试等于无视用户意图。"""
    assert _should_retry_with_default_runtime(
        success=False,
        runtime_tuning={"enabled": True, "derived_workers": 3},
        completed_count=0,
        canceled=True,
    ) is False


@pytest.mark.unit
def test_no_retry_when_tuning_disabled():
    assert _should_retry_with_default_runtime(
        success=False,
        runtime_tuning={"enabled": False},
        completed_count=0,
        canceled=False,
    ) is False


@pytest.mark.unit
def test_no_retry_when_tuning_derived_nothing():
    """调参开着但没推导出任何覆盖项时，重试没有意义（参数本来就一样）。"""
    assert _should_retry_with_default_runtime(
        success=False,
        runtime_tuning={"enabled": True, "derived_workers": None, "derived_io_profile": None},
        completed_count=0,
        canceled=False,
    ) is False


@pytest.mark.unit
def test_retry_decision_always_returns_bool():
    """返回类型必须恒为 bool。

    历史实现用 ``... or runtime_tuning.get("derived_io_profile")`` 收尾，
    两个覆盖项都为空时会把 ``None`` 直接返回出去（短路值泄漏）。
    调用方写的是 ``if can_retry:`` 所以没出事，但一旦有人写 ``is False``
    或把它塞进导出报告，就会踩坑。
    """
    cases = [
        {"enabled": True, "derived_workers": None, "derived_io_profile": None},
        {"enabled": True, "derived_workers": 3, "derived_io_profile": None},
        {"enabled": True, "derived_workers": None, "derived_io_profile": "speed"},
        {"enabled": False},
        {},
    ]
    for tuning in cases:
        for success in (True, False):
            for completed in (0, 5):
                for canceled in (True, False):
                    value = _should_retry_with_default_runtime(
                        success=success,
                        runtime_tuning=tuning,
                        completed_count=completed,
                        canceled=canceled,
                    )
                    assert value is True or value is False, (
                        f"返回了 {value!r}（{type(value).__name__}），"
                        f"调参={tuning} success={success} completed={completed} canceled={canceled}"
                    )


@pytest.mark.unit
def test_retry_decision_tolerates_none_completed_count():
    """completed_count 传 None 时按 0 处理（不能 int(None) 崩掉）。"""
    assert _should_retry_with_default_runtime(
        success=False,
        runtime_tuning={"enabled": True, "derived_workers": 2},
        completed_count=None,
        canceled=False,
    ) is True


# ---------------------------------------------------------------------------
# 诊断汇总 → 用户可读建议
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_summary_maps_each_shortage_reason_to_advice():
    """每种短缺原因都要有对应建议，否则用户看到"没凑满"却不知怎么办。"""
    mapping = {
        "combination_space_limited": "组合空间",
        "dedup_blocking": "去重",
        "category_coverage_low": "分类覆盖",
    }
    for reason, keyword in mapping.items():
        summary = Manager._summarize_precompute_diagnostics(
            {"shortage_analysis": {"primary_reasons": [reason], "shortage_count": 3}}
        )
        joined = " ".join(summary["recommendations"])
        assert keyword in joined, (reason, joined)


@pytest.mark.unit
def test_summary_mentions_relax_gain_when_used():
    summary = Manager._summarize_precompute_diagnostics(
        {"relax_dedup_used": True, "relax_gain_count": 12}
    )
    assert any("12" in item for item in summary["recommendations"])


@pytest.mark.unit
def test_summary_reports_budget_adjustments():
    summary = Manager._summarize_precompute_diagnostics(
        {"dynamic_budget": {"enabled": True, "expanded_times": 2, "shrunk_times": 1}}
    )
    joined = " ".join(summary["recommendations"])
    assert "2" in joined and "1" in joined


@pytest.mark.unit
def test_summary_suggests_enabling_budget_when_disabled():
    summary = Manager._summarize_precompute_diagnostics({"dynamic_budget": {"enabled": False}})
    assert any("动态预算" in item for item in summary["recommendations"])


@pytest.mark.unit
def test_summary_falls_back_when_no_reason_but_shortage_exists():
    """有缺口但没命中任何已知原因时，也要给一条可操作建议。

    注意：诊断里若**没有** ``dynamic_budget`` 字段，会先命中"可开启动态预算"
    那条通用建议（实现里是 else 分支）。所以这里显式带上
    ``dynamic_budget.enabled=True``，才能走到"提高尝试上限"的兜底建议。
    """
    summary = Manager._summarize_precompute_diagnostics(
        {
            "shortage_analysis": {"primary_reasons": [], "shortage_count": 7},
            "dynamic_budget": {"enabled": True},
        }
    )
    assert any("尝试上限" in item for item in summary["recommendations"])


@pytest.mark.unit
def test_summary_suggests_budget_when_field_absent():
    """诊断里没有 dynamic_budget 字段时，提示"可开启"（视为未启用）。

    这是当前实现的语义：缺失 == 未启用。如果将来改成"缺失就静默"，
    这条测试会失败，提醒同步 UI 文案与判断条件。
    """
    summary = Manager._summarize_precompute_diagnostics(
        {"shortage_analysis": {"primary_reasons": [], "shortage_count": 7}}
    )
    assert any("动态预算" in item for item in summary["recommendations"])


@pytest.mark.unit
def test_summary_preserves_mode_and_strategy():
    summary = Manager._summarize_precompute_diagnostics(
        {"mode": "binding", "dedup_strategy": "layered"}
    )
    assert summary["mode"] == "binding"
    assert summary["dedup_strategy"] == "layered"


@pytest.mark.unit
def test_summary_handles_empty_diagnostics():
    """空诊断不能崩，且仍给出基线建议。"""
    summary = Manager._summarize_precompute_diagnostics({})
    assert summary["shortage"] == {}
    assert summary["recommendations"]


@pytest.mark.unit
def test_summary_handles_none_diagnostics():
    summary = Manager._summarize_precompute_diagnostics(None)
    assert isinstance(summary["recommendations"], list)


# ---------------------------------------------------------------------------
# 导出报告记录
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_record_report_sets_last_and_history(tmp_path, monkeypatch):
    """报告要同时落到 _last_export_report 与历史列表。"""
    import app.utils.optimized_batch_executor as module

    # 把日志目录指到 tmp，避免污染真实用户目录
    monkeypatch.setattr(module.os_module.path, "expanduser", lambda p: str(tmp_path))

    doc = _Doc()
    Manager._record_export_report(doc, {"total": 3})

    assert doc._last_export_report == {"total": 3}
    assert doc._export_report_history == [{"total": 3}]


@pytest.mark.unit
def test_record_report_appends_jsonl(tmp_path, monkeypatch):
    """同时写一份 jsonl 便于事后排查（历史只留在内存，重启即失）。"""
    import app.utils.optimized_batch_executor as module

    monkeypatch.setattr(module.os_module.path, "expanduser", lambda p: str(tmp_path))

    doc = _Doc()
    Manager._record_export_report(doc, {"total": 1})
    Manager._record_export_report(doc, {"total": 2})

    report_file = doc._last_export_report_file
    assert report_file.endswith("export_reports.jsonl")

    lines = [
        json.loads(line)
        for line in open(report_file, encoding="utf-8").read().splitlines()
        if line.strip()
    ]
    assert lines == [{"total": 1}, {"total": 2}]


@pytest.mark.unit
def test_record_report_trims_history_to_limit(tmp_path, monkeypatch):
    """历史条数受 export_settings.export_report_history_limit 约束。"""
    import app.utils.optimized_batch_executor as module

    monkeypatch.setattr(module.os_module.path, "expanduser", lambda p: str(tmp_path))

    doc = _Doc({"export_report_history_limit": 10})  # 下限会被夹到 10
    for i in range(25):
        Manager._record_export_report(doc, {"i": i})

    assert len(doc._export_report_history) == 10
    # 保留的是最近 10 条
    assert doc._export_report_history[0] == {"i": 15}
    assert doc._export_report_history[-1] == {"i": 24}


@pytest.mark.unit
def test_record_report_clamps_absurd_history_limit(tmp_path, monkeypatch):
    """配置写坏（如 1 或 99999）要被夹到 [10, 300]。"""
    import app.utils.optimized_batch_executor as module

    monkeypatch.setattr(module.os_module.path, "expanduser", lambda p: str(tmp_path))

    doc = _Doc({"export_report_history_limit": 99999})
    for i in range(320):
        Manager._record_export_report(doc, {"i": i})
    assert len(doc._export_report_history) == 300


@pytest.mark.unit
def test_record_report_ignores_non_dict(tmp_path, monkeypatch):
    """非 dict 不得写入（否则 jsonl 里会出现裸字符串，后续解析全崩）。"""
    import app.utils.optimized_batch_executor as module

    monkeypatch.setattr(module.os_module.path, "expanduser", lambda p: str(tmp_path))

    doc = _Doc()
    doc._last_export_report = "previous"  # 预置一个值，确认不会被非 dict 覆盖
    Manager._record_export_report(doc, "not-a-dict")

    assert doc._last_export_report == "previous"
    assert getattr(doc, "_export_report_history", None) in (None, [])


@pytest.mark.unit
def test_record_report_never_raises_on_broken_document(tmp_path, monkeypatch):
    """文档对象不可写时也不能抛 —— 记录报告失败不该影响导出结果。"""
    import app.utils.optimized_batch_executor as module

    monkeypatch.setattr(module.os_module.path, "expanduser", lambda p: str(tmp_path))

    class Frozen:
        """用 __slots__ 让属性赋值直接失败。"""
        __slots__ = ()
        export_settings = {}

    # 不应抛异常
    Manager._record_export_report(Frozen(), {"total": 1})
