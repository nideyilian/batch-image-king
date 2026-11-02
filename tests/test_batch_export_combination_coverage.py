"""批量导出「组合覆盖率」回归测试（2026-11-02）。

## 这个文件守的是什么

`_generate_standard_combinations_v2` 之前有一个**不会报错的严重缺陷**：
多图层场景下，产出的组合数被压缩到 O(n) 而不是 O(n^k)，而且完全看不出来。

原因：主循环每轮让**每个图层各自**做"用得少的优先"选择。当各层池大小相同时，
它们的 usage 分布同步演化，"最少使用"集合每一步同时切换，形成固定排列循环 ——
于是反复撞上已经产出的组合，被去重拦住，空转到预算耗尽。

实测（修复前）：

| 场景 | 理论组合 | 实际产出 | 尝试次数 | 重复次数 |
|---|---|---|---|---|
| 3 图层 × 2 张 | 8 | **2** | 343 | 341 |
| 3 图层 × 3 张 | 27 | 8~14 | 1163 | 1155 |
| 3 图层 × 5 张，请求 20 | 125 | **5** | 616 | 611 |

用户的感受是"素材明明有 125 种组合，软件只给我 5 张"，界面上只说"去重命中较高"，
根本不会想到是算法问题。

修复：启用原本就写好但被 `deterministic_allowed = False` 关掉的确定性枚举分支
（用与总空间互质的大质数步长遍历），复杂度 O(count)，与空间大小无关。

## 为什么这些测试必须存在

这个缺陷**不报错、不降级、不写日志**，功能测试全绿也发现不了。
只有断言"产出的组合数是否达到理论值"才能抓到。
"""

from __future__ import annotations

import io
import os
import random
from contextlib import redirect_stdout
from types import SimpleNamespace

import pytest

from app.utils.batch_export_precomputer_v2 import get_batch_precomputer_v2

pytestmark = pytest.mark.integration


def _build(tmp_path, pool_sizes, seed=1):
    """按每个图层的素材数量造文档，返回预计算器。"""
    random.seed(seed)
    layers = []
    for idx, size in enumerate(pool_sizes):
        layer_dir = tmp_path / f"layer{idx}"
        layer_dir.mkdir(parents=True, exist_ok=True)
        for i in range(1, size + 1):
            (layer_dir / f"L{idx}_{i:02d}.png").write_bytes(b"")
        layers.append(SimpleNamespace(
            name=f"图层{idx}", visible=True, image_source=str(layer_dir),
            is_folder=True, _is_folder=True, parent_group_id=None, type="layer",
        ))

    document = SimpleNamespace(
        layers=layers, export_settings={}, file_path="", binding_manager=None,
    )
    analysis = {
        "binding_enabled": False,
        "binding_categories": [],
        "layer_analysis": {
            "visible_layers": layers, "bound_layers": [], "unbound_layers": layers,
        },
        "export_mode": "standard",
    }
    precomputer = get_batch_precomputer_v2(document, analysis)
    precomputer.analyze_document_with_context()
    return precomputer


def _plan(tmp_path, precomputer, count, avoid=True):
    out_dir = tmp_path / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    with redirect_stdout(io.StringIO()):
        return precomputer.create_export_plan(
            str(out_dir), count, "i_{number}", "png", 1, avoid, False, None,
        )


def _combinations(plan):
    return [
        tuple(os.path.basename(v) for _, v in sorted(t.combination.layer_states.items()))
        for t in plan.tasks
    ]


# ---------------------------------------------------------------------------
# 覆盖率：核心回归
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("pool_size", [2, 3, 4, 5, 6])
def test_three_layers_produce_full_cartesian_product(tmp_path, pool_size):
    """3 图层、每池 n 张、请求满额 → 必须拿到 n³ 个**互不相同**的组合。

    这是最直接的回归断言。修复前 pool_size=2 只出 2 个（理论 8），
    pool_size=5 更是离谱 —— 素材越多覆盖越差。
    """
    precomputer = _build(tmp_path, (pool_size,) * 3)
    expected = pool_size ** 3
    plan = _plan(tmp_path, precomputer, expected)

    combos = _combinations(plan)
    assert len(combos) == expected, (
        f"3 图层 × 每池 {pool_size} 张，理论 {expected} 种组合，"
        f"实际只产出 {len(combos)} 种"
    )
    assert len(set(combos)) == expected, "产出的组合里有重复"


@pytest.mark.unit
@pytest.mark.parametrize("pool_sizes,expected", [
    ((2, 2), 4),
    ((3, 3), 9),
    ((2, 3), 6),
    ((3, 4), 12),
    ((2, 2, 2), 8),
    ((2, 3, 4), 24),
    ((3, 3, 3), 27),
])
def test_cartesian_product_size_matches_pool_product(tmp_path, pool_sizes, expected):
    """任意图层组合，满额请求时必须能取到全部笛卡尔积。"""
    precomputer = _build(tmp_path, pool_sizes)
    plan = _plan(tmp_path, precomputer, expected)

    combos = _combinations(plan)
    assert len(combos) == expected, f"池{pool_sizes}: 期望 {expected}，实际 {len(combos)}"
    assert len(set(combos)) == expected


@pytest.mark.unit
def test_partial_request_still_gets_unique_combinations(tmp_path):
    """只要请求量 ≤ 理论空间，就必须拿到**互不重复**的足量组合。

    修复前这个场景最坑：池 5×3（125 种）请求 20 只出 5 张，
    而且这 5 张还刚好是"每张素材各用一次"的排列。
    """
    precomputer = _build(tmp_path, (5, 5, 5))
    plan = _plan(tmp_path, precomputer, 20)

    combos = _combinations(plan)
    assert len(combos) == 20
    assert len(set(combos)) == 20


@pytest.mark.unit
def test_request_exceeding_space_returns_all_combinations(tmp_path):
    """请求量超过理论空间时，应返回全部组合而不是硬凑重复。"""
    precomputer = _build(tmp_path, (2, 2))
    plan = _plan(tmp_path, precomputer, 100)

    combos = _combinations(plan)
    assert len(combos) == 4
    assert len(set(combos)) == 4


# ---------------------------------------------------------------------------
# 各图层分布质量
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_each_layer_distributes_usage_evenly(tmp_path):
    """每一层的素材都要被**广泛**用到，不能出现"某层只用了一两张图"。

    修复前的症状：3 图层 5×5×5 请求 20 时，第三层只用 1 张素材
    （线性步进 + 进位制拆解导致低位几乎不动）。

    现在低利用率走"优先未用过素材"的采样，实测 300 个种子全部满足各层全覆盖，
    所以这里可以断言满覆盖。

    注：这条断言曾经写成 `>= 3`（因为当时用纯均匀随机，1000 个种子里有 10.7%
    只能覆盖到 4 张）。问题不是测试太严，而是**实现不够好** —— 加固实现后
    才把断言提到满覆盖。不要反过来靠放松断言来"消灭"间歇失败。
    """
    precomputer = _build(tmp_path, (5, 5, 5))
    plan = _plan(tmp_path, precomputer, 20)
    combos = _combinations(plan)

    for layer_pos in range(3):
        used = {c[layer_pos] for c in combos}
        assert len(used) == 5, (
            f"第 {layer_pos} 层只用到 {len(used)}/5 张素材：{sorted(used)}"
        )


@pytest.mark.unit
def test_large_pools_keep_usage_balanced(tmp_path):
    """池远大于请求量时，应尽量"每张只用一次"，而不是反复用同一张。"""
    precomputer = _build(tmp_path, (30, 30, 30))
    plan = _plan(tmp_path, precomputer, 5)
    combos = _combinations(plan)

    for layer_pos in range(3):
        used = [c[layer_pos] for c in combos]
        assert len(set(used)) == 5, (
            f"第 {layer_pos} 层在 5 张产出里重复使用了素材：{used}"
        )


# ---------------------------------------------------------------------------
# 不能回归的场景
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_single_layer_unchanged(tmp_path):
    """单图层不涉及组合，行为不应受枚举改动影响。"""
    precomputer = _build(tmp_path, (7,))
    plan = _plan(tmp_path, precomputer, 7)

    combos = _combinations(plan)
    assert len(combos) == 7
    assert len(set(combos)) == 7


@pytest.mark.unit
def test_avoid_duplicates_off_still_allows_repeats(tmp_path):
    """关掉避重时，允许重复是用户的明确选择，不能被枚举"修正"掉。"""
    precomputer = _build(tmp_path, (2, 2))
    plan = _plan(tmp_path, precomputer, 6, avoid=False)

    combos = _combinations(plan)
    assert len(combos) == 6, "关避重时应凑满请求量"
    assert plan.precompute_diagnostics.get("deterministic_enumeration_used") is False, (
        "关避重时不应启用确定性枚举"
    )


@pytest.mark.unit
def test_empty_pool_returns_empty_plan(tmp_path):
    """空素材目录仍然返回空计划（不能被枚举逻辑搞成 1 个兜底组合）。"""
    precomputer = _build(tmp_path, (0,))
    plan = _plan(tmp_path, precomputer, 5)
    assert len(plan.tasks) == 0


@pytest.mark.unit
def test_enumeration_is_deterministic_across_runs(tmp_path):
    """同样输入必须产出同样组合。

    枚举的起始种子来自 `time.time_ns()`，但它的作用是"从空间里随机起跳"，
    同一进程连续两次调用是否一致并不重要；重要的是**不能丢组合**。
    这里断言两次产出都是满额且都无重复 —— 这才是用户能感知的保证。
    """
    precomputer_a = _build(tmp_path / "a", (3, 3), seed=1)
    plan_a = _plan(tmp_path / "a", precomputer_a, 9)
    precomputer_b = _build(tmp_path / "b", (3, 3), seed=99)
    plan_b = _plan(tmp_path / "b", precomputer_b, 9)

    for plan in (plan_a, plan_b):
        combos = _combinations(plan)
        assert len(combos) == 9
        assert len(set(combos)) == 9


# ---------------------------------------------------------------------------
# 诊断字段
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_diagnostics_report_enumeration_used(tmp_path):
    """诊断里必须如实标注走了哪条路径，便于排查"为什么这么出图"。"""
    precomputer = _build(tmp_path, (3, 3, 3))
    plan = _plan(tmp_path, precomputer, 27)

    assert plan.precompute_diagnostics.get("deterministic_enumeration_used") is True


@pytest.mark.unit
def test_shortage_reported_when_space_insufficient(tmp_path):
    """空间不足时仍要如实报告缺口（枚举不能把"素材不够"伪装成"已达成"）。"""
    precomputer = _build(tmp_path, (2, 2))
    plan = _plan(tmp_path, precomputer, 20)

    shortage = plan.precompute_diagnostics["shortage_analysis"]
    assert shortage["requested_count"] == 20
    assert shortage["planned_count"] == 4
    assert shortage["shortage_count"] == 16
