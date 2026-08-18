"""FastRenderer 烟雾测试（不真跑渲染，仅验证结构）。

覆盖：

- FastRenderer 可实例化，全局单例可获取
- 类级 batch metrics 是 dict，且包含关键键
- reset_batch_metrics / _inc_batch_metric / get_batch_metrics 行为正确
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.fast_renderer import (  # noqa: E402
    FastRenderer,
    get_global_fast_renderer,
)


pytestmark = pytest.mark.unit


class TestFastRendererStructure:
    def test_instantiate_creates_independent_renderer(self):
        r = FastRenderer()
        # 应有缓存容器
        assert r._layer_surface_cache is not None
        assert r._export_layer_surface_cache is not None
        assert r._interactive_base_cache is not None

    def test_global_singleton_is_fast_renderer(self):
        r1 = get_global_fast_renderer()
        r2 = get_global_fast_renderer()
        assert isinstance(r1, FastRenderer)
        # 单例
        assert r1 is r2

    def test_batch_metrics_shape(self):
        # 类级字典包含关键监控键
        keys = set(FastRenderer._batch_metrics.keys())
        for required in ("export_layer_cache_hits", "export_layer_cache_misses",
                         "layer_surface_cache_hits", "layer_surface_cache_misses",
                         "apply_effects_calls"):
            assert required in keys


class TestBatchMetrics:
    def setup_method(self):
        # 每个用例前重置一次，避免互相污染
        FastRenderer.reset_batch_metrics()

    def test_reset_clears_all_metrics(self):
        # 先手动加几个值
        FastRenderer._inc_batch_metric("export_layer_cache_hits", 5)
        FastRenderer._inc_batch_metric("apply_effects_calls", 3)
        FastRenderer.reset_batch_metrics()
        metrics = FastRenderer.get_batch_metrics()
        for v in metrics.values():
            assert v == 0

    def test_inc_increments_existing_key(self):
        FastRenderer._inc_batch_metric("export_layer_cache_misses", 2)
        FastRenderer._inc_batch_metric("export_layer_cache_misses", 3)
        metrics = FastRenderer.get_batch_metrics()
        assert metrics["export_layer_cache_misses"] == 5

    def test_inc_creates_unknown_key(self):
        FastRenderer._inc_batch_metric("custom_metric", 1)
        metrics = FastRenderer.get_batch_metrics()
        assert metrics["custom_metric"] == 1
