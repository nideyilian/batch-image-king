"""批量导出「去重策略 / 动态预算 / 短缺分析」行为测试（2026-11-02）。

为什么补这一组：
`_generate_binding_combinations_v2`（723 行 / 138 分支）与
`export_batch_optimized_v2`（514 行 / 140 分支）目前没有任何行为测试，
只有计数类断言。这两个巨型函数不敢直接拆，就是因为拆错了没人能发现。

但它们内部依赖的这批纯逻辑（本文件覆盖）是**可以独立验证**的，
而且正是拆分后最容易出错的地方：

- 去重策略决定"哪些组合被跳过" → 判错会少出图或出重复图
- 动态预算决定"最多尝试多少次" → 判错会提前放弃或空转
- 短缺分析决定"为什么没凑满"的诊断文案 → 判错会误导排查方向

被测模块：``app/utils/batch_export_dedup_budget.py``（330 行 / 14 个方法）。
用最小 stub 提供 ``document.export_settings`` / ``layer_image_pools`` /
``unique_use_enabled`` 三个依赖，不启动 Qt、不碰真实文档。
"""

from __future__ import annotations

import pytest

from app.utils.batch_export_dedup_budget import BatchExportDedupBudgetMixin


class _Stub(BatchExportDedupBudgetMixin):
    """最小宿主：只提供 mixin 实际访问的那几个成员。"""

    def __init__(self, settings=None, pools=None, unique_use=False):
        self.document = type("_Doc", (), {"export_settings": settings or {}})()
        self.layer_image_pools = pools or {}
        self.unique_use_enabled = unique_use


# ---------------------------------------------------------------------------
# 去重策略解析
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_dedup_strategy_defaults_by_mode():
    """默认策略按模式区分：绑定走分层（更严），普通走哈希。"""
    assert _Stub()._resolve_dedup_strategy("binding", True) == "layered"
    assert _Stub()._resolve_dedup_strategy("standard", True) == "hash"


@pytest.mark.unit
def test_dedup_strategy_none_when_not_avoiding_duplicates():
    """关闭避重时策略必须是 none —— 否则会白白跳过组合。"""
    for mode in ("binding", "standard"):
        assert _Stub()._resolve_dedup_strategy(mode, False) == "none"


@pytest.mark.unit
def test_dedup_strategy_honors_explicit_setting():
    assert _Stub({"dedup_strategy": "hash"})._resolve_dedup_strategy("binding", True) == "hash"
    assert _Stub({"dedup_strategy": "none"})._resolve_dedup_strategy("binding", True) == "none"


@pytest.mark.unit
def test_per_mode_setting_overrides_global():
    """``dedup_strategy_<mode>`` 优先于全局 ``dedup_strategy``。"""
    stub = _Stub({"dedup_strategy": "hash", "dedup_strategy_binding": "layered"})
    assert stub._resolve_dedup_strategy("binding", True) == "layered"
    # 未覆盖的模式仍回退到全局值
    assert stub._resolve_dedup_strategy("standard", True) == "hash"


@pytest.mark.unit
def test_invalid_dedup_strategy_falls_back_to_mode_default():
    """非法值不能放行，必须回退到模式默认（防止配置写错导致去重失效）。"""
    assert _Stub({"dedup_strategy": "xxx"})._resolve_dedup_strategy("binding", True) == "layered"
    assert _Stub({"dedup_strategy": "xxx"})._resolve_dedup_strategy("standard", True) == "hash"


@pytest.mark.unit
def test_dedup_strategy_is_whitespace_and_case_tolerant():
    assert _Stub({"dedup_strategy": "  HASH  "})._resolve_dedup_strategy("binding", True) == "hash"


# ---------------------------------------------------------------------------
# 文件签名
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_file_signature_keeps_layer_index_order():
    """签名必须按图层索引排序，否则同一组合换个遍历顺序就被当成新的。"""
    shuffled = {2: "/a/c.png", 0: "/a/a.png", 1: "/a/b.png"}
    assert _Stub()._build_layer_file_signature(shuffled) == ("L0:a.png", "L1:b.png", "L2:c.png")


@pytest.mark.unit
def test_file_signature_uses_basename_only_by_design():
    """签名只取 basename —— 这是**刻意**的，不是遗漏。

    前提：素材扫描用 ``os.scandir`` 只扫**一层**目录（不递归），
    因此同一批素材里不会出现"不同子目录下的同名文件"。
    如果将来改成递归扫描，这条测试会失败，提醒你 basename 会撞车、必须改成相对路径。
    """
    signature = _Stub()._build_layer_file_signature({0: "/p/a.png", 1: "/q/a.png"})
    assert signature == ("L0:a.png", "L1:a.png")
    # 不同图层的索引不同，所以即便 basename 相同，整体签名仍可区分
    assert signature[0] != signature[1]


# ---------------------------------------------------------------------------
# 去重判定与记录
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_dedup_skip_returns_false_when_strategy_is_none():
    stub = _Stub()
    state = stub._create_dedup_state("none")
    skip, reason = stub._dedup_should_skip(state, "h1", {0: "/a/x.png"})
    assert skip is False and reason == ""


@pytest.mark.unit
def test_layered_dedup_blocks_same_files_even_with_different_hash():
    """分层策略的核心价值：文件相同但哈希不同（例如文案变了）也应跳过。"""
    stub = _Stub()
    state = stub._create_dedup_state("layered")
    files = {0: "/a/x.png", 1: "/a/y.png"}

    assert stub._dedup_should_skip(state, "hash1", files) == (False, "")
    stub._dedup_record(state, "hash1", files)

    # 哈希不同，但文件组合相同 → 必须拦住，原因是 file_layers
    assert stub._dedup_should_skip(state, "hash2", files) == (True, "file_layers")


@pytest.mark.unit
def test_layered_dedup_blocks_same_files_within_same_category():
    """同分类内文件组合重复也要拦，原因是 file_layers_category。"""
    stub = _Stub()
    state = stub._create_dedup_state("layered")
    files = {0: "/a/x.png"}
    stub._dedup_record(state, "h1", files, category="猫")

    skip, reason = stub._dedup_should_skip(state, "h2", files, category="猫")
    assert (skip, reason) == (True, "file_layers")


@pytest.mark.unit
def test_layered_dedup_allows_same_files_across_categories_only_by_hash_rule():
    """换分类后，file_signatures 这一层仍会命中（这是当前实现的语义）。

    这条测试**记录现状**而不是表达偏好：文件组合完全相同、
    只是分类标签不同时，仍会被 ``file_layers`` 拦下。
    如果产品希望"同图不同分类算不同组合"，这里就是需要改的判定点。
    """
    stub = _Stub()
    state = stub._create_dedup_state("layered")
    files = {0: "/a/x.png"}
    stub._dedup_record(state, "h1", files, category="猫")

    skip, reason = stub._dedup_should_skip(state, "h2", files, category="狗")
    assert (skip, reason) == (True, "file_layers")


@pytest.mark.unit
def test_hash_strategy_ignores_file_signature():
    """hash 策略只看哈希：文件相同但哈希不同应当放行。"""
    stub = _Stub()
    state = stub._create_dedup_state("hash")
    files = {0: "/a/x.png"}
    stub._dedup_record(state, "h1", files)

    assert stub._dedup_should_skip(state, "h2", files) == (False, "")
    assert stub._dedup_should_skip(state, "h1", files) == (True, "hash")


@pytest.mark.unit
def test_relax_dedup_skips_file_layer_checks():
    """放宽模式下跳过文件级判定（组合空间不足时的保命开关）。"""
    stub = _Stub()
    state = stub._create_dedup_state("layered")
    files = {0: "/a/x.png"}
    stub._dedup_record(state, "h1", files)

    # 不放宽：拦住
    assert stub._dedup_should_skip(state, "h2", files)[0] is True
    # 放宽：放行文件级判定（哈希仍不同）
    assert stub._dedup_should_skip(state, "h2", files, relax_dedup=True) == (False, "")


@pytest.mark.unit
def test_force_hash_only_downgrades_layered_to_hash():
    """强制哈希模式：分层策略降级为只比哈希。"""
    stub = _Stub()
    state = stub._create_dedup_state("layered")
    files = {0: "/a/x.png"}
    stub._dedup_record(state, "h1", files)

    # 文件组合相同但哈希不同 → 降级后应放行
    assert stub._dedup_should_skip(state, "h2", files, force_hash_only=True) == (False, "")
    # 哈希相同 → 仍然拦
    assert stub._dedup_should_skip(state, "h1", files, force_hash_only=True) == (True, "hash")


@pytest.mark.unit
def test_dedup_record_is_noop_for_none_strategy():
    """none 策略不应记录任何状态（否则会污染后续判定）。"""
    stub = _Stub()
    state = stub._create_dedup_state("none")
    stub._dedup_record(state, "h1", {0: "/a/x.png"})
    assert state["hashes"] == set()
    assert state["file_signatures"] == set()


# ---------------------------------------------------------------------------
# 动态预算配置
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_budget_config_small_task_is_more_responsive():
    """小任务要更快响应：检查间隔与最小样本都减半。"""
    stub = _Stub()
    small = stub._get_dynamic_budget_config("binding", 100)
    large = stub._get_dynamic_budget_config("binding", 2000)

    assert small["check_interval"] < large["check_interval"]
    assert small["min_samples"] < large["min_samples"]


@pytest.mark.unit
def test_budget_limits_are_ordered_and_sane():
    """下限必须 ≤ 基准 ≤ 上限，且间隔/步长都在合理区间。"""
    stub = _Stub()
    for base in (50, 100, 500, 5000):
        for mode in ("binding", "standard"):
            cfg = stub._get_dynamic_budget_config(mode, base)
            assert 1 <= cfg["min_limit"] <= base <= cfg["max_limit"], (mode, base, cfg)
            assert 5 <= cfg["check_interval"] <= 100
            assert 10 <= cfg["min_samples"] <= 200
            assert 0.05 <= cfg["expand_step"] <= 1.0
            assert 0.01 <= cfg["shrink_step"] <= 0.5


@pytest.mark.unit
def test_budget_config_is_always_enabled():
    """当前实现按任务自动计算，不开放 UI 关闭入口。"""
    stub = _Stub()
    assert stub._get_dynamic_budget_config("binding", 100)["enabled"] is True
    assert stub._get_dynamic_budget_config("standard", 100)["enabled"] is True


# ---------------------------------------------------------------------------
# 动态预算调节
# ---------------------------------------------------------------------------

def _first_rebalance_attempt(stub, base: int, mode: str = "binding") -> int:
    """算出「第一次真正会触发调节」的 attempts 值（同时满足样本与间隔）。"""
    cfg = stub._get_dynamic_budget_config(mode, base)
    return next(
        a for a in range(1, 10_000)
        if a >= cfg["min_samples"] and a % cfg["check_interval"] == 0
    )


@pytest.mark.unit
def test_rebalance_noop_before_min_samples():
    """样本不足时不得调节（避免用几个样本就乱改预算）。"""
    stub = _Stub()
    state = stub._create_dynamic_budget_state("binding", 1000)
    before = state["current_limit"]

    stub._maybe_rebalance_dynamic_budget(state, attempts=5, generated=0, duplicate_attempts=0)
    assert state["current_limit"] == before
    assert state["events"] == []


@pytest.mark.unit
def test_rebalance_expands_on_low_success_rate():
    """成功率过低 → 扩大预算（多试几次，别急着放弃）。"""
    stub = _Stub()
    state = stub._create_dynamic_budget_state("binding", 1000)
    at = _first_rebalance_attempt(stub, 1000)
    before = state["current_limit"]

    stub._maybe_rebalance_dynamic_budget(state, attempts=at, generated=0, duplicate_attempts=0)

    assert state["current_limit"] > before
    assert state["expanded_times"] == 1
    event = state["events"][-1]
    assert event["action"] == "expand"
    assert event["at_attempt"] == at
    assert event["new_limit"] > event["old_limit"]


@pytest.mark.unit
def test_rebalance_shrinks_on_high_success_and_low_duplicate():
    """成功率高且几乎不重复 → 收缩预算（省掉空转）。"""
    stub = _Stub()
    state = stub._create_dynamic_budget_state("binding", 1000)
    at = _first_rebalance_attempt(stub, 1000)
    before = state["current_limit"]

    stub._maybe_rebalance_dynamic_budget(state, attempts=at, generated=at, duplicate_attempts=0)

    assert state["current_limit"] < before
    assert state["shrunk_times"] == 1
    assert state["events"][-1]["action"] == "shrink"


@pytest.mark.unit
def test_rebalance_respects_max_limit():
    """反复扩容不得越过上限。"""
    stub = _Stub()
    state = stub._create_dynamic_budget_state("binding", 1000)
    cfg = state["config"]
    at = _first_rebalance_attempt(stub, 1000)

    for _ in range(60):
        stub._maybe_rebalance_dynamic_budget(
            state, attempts=at, generated=0, duplicate_attempts=0
        )
    assert state["current_limit"] <= cfg["max_limit"]


@pytest.mark.unit
def test_rebalance_never_drops_below_attempts_already_made():
    """收缩时下界不能低于"已经尝试过的次数"，否则 while 条件立即不成立、白跑。"""
    stub = _Stub()
    state = stub._create_dynamic_budget_state("binding", 1000)
    at = _first_rebalance_attempt(stub, 1000)

    stub._maybe_rebalance_dynamic_budget(state, attempts=at, generated=at, duplicate_attempts=0)
    assert state["current_limit"] >= at


@pytest.mark.unit
def test_rebalance_events_are_capped():
    """事件列表最多留 8 条（防止诊断信息无限膨胀）。"""
    stub = _Stub()
    state = stub._create_dynamic_budget_state("binding", 1000)
    at = _first_rebalance_attempt(stub, 1000)

    for _ in range(20):
        stub._maybe_rebalance_dynamic_budget(state, attempts=at, generated=0, duplicate_attempts=0)

    assert len(state["events"]) <= 8


@pytest.mark.unit
def test_rebalance_disabled_config_is_noop():
    stub = _Stub()
    state = stub._create_dynamic_budget_state("binding", 1000)
    state["config"]["enabled"] = False
    before = state["current_limit"]

    stub._maybe_rebalance_dynamic_budget(state, attempts=9999, generated=0, duplicate_attempts=0)
    assert state["current_limit"] == before
    assert state["events"] == []


# ---------------------------------------------------------------------------
# 尝试预算估算
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_attempt_limit_stays_within_computed_bounds():
    """估算结果必须落在 [target*low, target*high] 内，且至少为 1。"""
    stub = _Stub()
    pools = {0: [f"{i}.png" for i in range(20)],
             1: [f"{i}.png" for i in range(20)],
             2: [f"{i}.png" for i in range(20)]}

    for mode, low_mul, high_mul in (("binding", 18, 120), ("standard", 4, 40)):
        for count in (1, 10, 100, 1000):
            limit = stub._estimate_base_attempt_limit(mode, count, True, pools)
            assert count * low_mul <= limit <= count * high_mul, (mode, count, limit)


@pytest.mark.unit
def test_attempt_limit_grows_with_requested_count():
    """请求越多，预算越多（单调不减）。"""
    stub = _Stub()
    pools = {0: ["a.png"], 1: ["b.png"]}
    limits = [
        stub._estimate_base_attempt_limit("binding", c, True, pools)
        for c in (1, 10, 100, 500)
    ]
    assert limits == sorted(limits)


@pytest.mark.unit
def test_attempt_limit_discounts_large_pools_and_layers():
    """大池 + 多图层容易命中新组合，预算应当打折（减少无效尝试）。"""
    stub = _Stub()
    big = {i: [f"{j}.png" for j in range(30)] for i in range(4)}
    tight = {0: ["a.png"], 1: ["b.png"]}
    for mode in ("binding", "standard"):
        big_limit = stub._estimate_base_attempt_limit(mode, 100, True, big)
        tight_limit = stub._estimate_base_attempt_limit(mode, 100, True, tight)
        assert big_limit < tight_limit, (mode, big_limit, tight_limit)


@pytest.mark.unit
def test_attempt_limit_handles_empty_or_invalid_pools():
    """空池 / 非法入参不能崩，也不能返回 0（否则 while 一次都不跑）。"""
    stub = _Stub()
    for pools in ({}, None, {0: [], 1: "not-a-list"}):
        limit = stub._estimate_base_attempt_limit("binding", 5, True, pools)
        assert isinstance(limit, int) and limit >= 1


@pytest.mark.unit
def test_attempt_limit_treats_zero_count_as_one():
    """count=0 时按 1 处理，避免出现 0 预算。"""
    stub = _Stub()
    assert stub._estimate_base_attempt_limit("binding", 0, True, {0: ["a.png"]}) >= 1


@pytest.mark.unit
def test_attempt_limit_without_dedup_is_cheaper():
    """不避重时可少试（绑定模式显式打折 0.85）。"""
    stub = _Stub()
    pools = {0: [f"{i}.png" for i in range(20)]}
    with_dedup = stub._estimate_base_attempt_limit("binding", 100, True, pools)
    without = stub._estimate_base_attempt_limit("binding", 100, False, pools)
    assert without <= with_dedup


@pytest.mark.unit
def test_attempt_limit_unique_use_raises_standard_budget():
    """普通模式下开启"独占使用"会显著限制可选量，预算要上调。"""
    pools = {0: [f"{i}.png" for i in range(20)]}
    normal = _Stub(pools=pools, unique_use=False)._estimate_base_attempt_limit(
        "standard", 100, True, pools
    )
    unique = _Stub(pools=pools, unique_use=True)._estimate_base_attempt_limit(
        "standard", 100, True, pools
    )
    assert unique > normal


# ---------------------------------------------------------------------------
# 短缺分析
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_shortage_reports_target_reached():
    stub = _Stub()
    result = stub._build_shortage_analysis(
        {"attempts": 100}, target_count=50, planned_count=50
    )
    assert result["shortage_count"] == 0
    assert "target_reached" in result["primary_reasons"]


@pytest.mark.unit
def test_shortage_detects_combination_space_exhausted():
    """组合空间本身不够 → 明确告知是"素材池限制"，而不是笼统的"效率低"。"""
    stub = _Stub()
    result = stub._build_shortage_analysis(
        {
            "attempts": 500,
            "combination_space": {"precompute_total_possible": 30},
        },
        target_count=100,
        planned_count=30,
    )
    assert result["shortage_count"] == 70
    assert "combination_space_limited" in result["primary_reasons"]


@pytest.mark.unit
def test_shortage_detects_dedup_blocking():
    """去重命中量 ≥ 缺口 → 说明是避重策略在拦，不是生成不够快。"""
    stub = _Stub()
    result = stub._build_shortage_analysis(
        {
            "attempts": 500,
            "duplicate_attempts": 400,
            "dedup_hits": {"file_layers": 60, "hash": 40},
        },
        target_count=100,
        planned_count=50,
    )
    assert result["dedup_total_hits"] == 100
    assert "dedup_blocking" in result["primary_reasons"]


@pytest.mark.unit
def test_shortage_detects_low_category_coverage():
    """绑定模式下分类没覆盖全 → 指出 category_coverage_low。"""
    stub = _Stub()
    result = stub._build_shortage_analysis(
        {
            "attempts": 200,
            "mode": "binding",
            "category_usage": {"猫": 30, "狗": 0},
            "available_categories": ["猫", "狗"],
        },
        target_count=100,
        planned_count=50,
    )
    assert "category_coverage_low" in result["primary_reasons"]


@pytest.mark.unit
def test_shortage_reports_force_generate_activation():
    """触发过强制生成仍不够 → 这是重要诊断信号。"""
    stub = _Stub()
    result = stub._build_shortage_analysis(
        {
            "attempts": 200,
            "mode": "binding",
            "force_generate_used": True,
            "category_usage": {},
            "available_categories": [],
        },
        target_count=100,
        planned_count=50,
    )
    assert "force_generate_activated" in result["primary_reasons"]


@pytest.mark.unit
def test_shortage_falls_back_to_efficiency_reason():
    """什么线索都没有时，至少给出一个可读的原因，不能是空列表。"""
    stub = _Stub()
    result = stub._build_shortage_analysis(
        {"attempts": 100}, target_count=100, planned_count=50
    )
    assert result["primary_reasons"] == ["generation_efficiency_low"]


@pytest.mark.unit
def test_shortage_counts_are_clamped_non_negative():
    """planned 超过 target（理论上不该发生）时，缺口不得为负。"""
    stub = _Stub()
    result = stub._build_shortage_analysis(
        {"attempts": 10}, target_count=10, planned_count=20
    )
    assert result["shortage_count"] == 0


@pytest.mark.unit
def test_shortage_rates_are_zero_when_attempts_zero():
    """attempts=0 时成功率/重复率必须是 0，不能除零。"""
    stub = _Stub()
    result = stub._build_shortage_analysis({}, target_count=10, planned_count=0)
    assert result["success_rate"] == 0.0
    assert result["duplicate_rate"] == 0.0


@pytest.mark.unit
def test_budget_summary_reflects_state():
    """汇总必须如实反映当前预算状态（诊断面板读的就是它）。"""
    stub = _Stub()
    state = stub._create_dynamic_budget_state("binding", 1000)
    at = _first_rebalance_attempt(stub, 1000)
    stub._maybe_rebalance_dynamic_budget(state, attempts=at, generated=0, duplicate_attempts=0)

    summary = stub._build_dynamic_budget_summary(
        state, attempts=at, generated=10, duplicate_attempts=8
    )
    assert summary["mode"] == "binding"
    assert summary["base_limit"] == 1000
    assert summary["final_limit"] == state["current_limit"]
    assert summary["expanded_times"] == 1
    assert summary["attempts"] == at
    assert summary["generated"] == 10
    assert 0.0 <= summary["success_rate"] <= 1.0
    assert 0.0 <= summary["duplicate_rate"] <= 1.0
    assert summary["events"]


# ---------------------------------------------------------------------------
# 放宽配置
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_relax_config_defaults():
    cfg = _Stub()._get_binding_relax_config()
    assert cfg["enabled"] is True
    assert cfg["min_attempts"] >= 1
    assert cfg["min_duplicate_attempts"] >= 1
    assert 0.0 <= cfg["max_success_rate"] <= 1.0


@pytest.mark.unit
def test_relax_config_sanitizes_bad_values():
    """配置写坏（0 / 负 / 超范围）时要夹紧，不能把阈值变成不可达或恒真。"""
    cfg = _Stub({
        "binding_relax_min_attempts": 0,
        "binding_relax_min_duplicate_attempts": -5,
        "binding_relax_max_success_rate": 9.9,
    })._get_binding_relax_config()
    assert cfg["min_attempts"] >= 1
    assert cfg["min_duplicate_attempts"] >= 1
    assert cfg["max_success_rate"] <= 1.0


@pytest.mark.unit
def test_relax_config_can_be_disabled():
    assert _Stub({"binding_relax_dedup_enabled": False})._get_binding_relax_config()["enabled"] is False


# ---------------------------------------------------------------------------
# 诊断信息暂存
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_diagnostics_accepts_dict_and_rejects_others():
    stub = _Stub()
    stub._set_precompute_diagnostics({"a": 1})
    assert stub._last_precompute_diagnostics == {"a": 1}

    stub._set_precompute_diagnostics(None)
    assert stub._last_precompute_diagnostics == {}

    stub._set_precompute_diagnostics("not-a-dict")
    assert stub._last_precompute_diagnostics == {}
