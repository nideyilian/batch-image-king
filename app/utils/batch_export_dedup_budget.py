# -*- coding: utf-8 -*-
"""去重策略 / 动态预算调节 / 短缺分析等可复用逻辑（P2 拆分超大文件）。

原属于 BatchExportPrecomputerV2 的一组方法，按"低风险评估、行为零变化"原则抽离为 mixin。
方法内对 self 的访问（self.document / self.layer_image_pools / self.unique_use_enabled 等）
仍指向主类实例，故迁移不改任何运行时行为；调用点（self._xxx）保持不变。
注意：新增方法时若依赖主类其它实例属性/方法，请确保这些成员仍由主类提供。
"""
import os
from typing import Any, Dict, List, Optional, Tuple


class BatchExportDedupBudgetMixin:
    """去重策略、动态预算调节、短缺分析等无状态逻辑。"""

    def _resolve_dedup_strategy(self, mode: str, avoid_duplicates: bool) -> str:
        """解析去重策略（迭代2.1：统一入口，可配置，可回退）。"""
        if not avoid_duplicates:
            return "none"
        settings = getattr(self.document, 'export_settings', {}) or {}
        mode_key = f"dedup_strategy_{mode}"
        strategy = settings.get(mode_key) or settings.get("dedup_strategy")
        if not strategy:
            return "layered" if mode == "binding" else "hash"
        strategy = str(strategy).strip().lower()
        if strategy in {"none", "hash", "layered"}:
            return strategy
        return "layered" if mode == "binding" else "hash"

    def _create_dedup_state(self, strategy: str) -> Dict[str, Any]:
        """根据策略创建去重状态容器。"""
        state = {
            "strategy": strategy,
            "hashes": set(),
            "file_signatures": set(),
            "file_category_signatures": set(),
        }
        return state

    def _build_layer_file_signature(self, layer_states: Dict[int, str]) -> Tuple[str, ...]:
        """构建稳定文件签名：保持图层索引顺序，避免误判。"""
        signatures = []
        for layer_idx in sorted(layer_states.keys()):
            file_path = layer_states[layer_idx]
            signatures.append(f"L{layer_idx}:{os.path.basename(file_path)}")
        return tuple(signatures)

    def _dedup_should_skip(
        self,
        dedup_state: Dict[str, Any],
        combination_hash: str,
        layer_states: Dict[int, str],
        category: Optional[str] = None,
        relax_dedup: bool = False,
        force_hash_only: bool = False,
    ) -> Tuple[bool, str]:
        """统一去重判断，返回 (是否跳过, 原因码)。"""
        strategy = dedup_state.get("strategy", "none")
        if strategy == "none":
            return False, ""

        effective_strategy = "hash" if force_hash_only else strategy

        if effective_strategy == "layered" and not relax_dedup:
            file_sig = self._build_layer_file_signature(layer_states)
            if file_sig in dedup_state["file_signatures"]:
                return True, "file_layers"

            if category is not None:
                file_cat_sig = (str(category), file_sig)
                if file_cat_sig in dedup_state["file_category_signatures"]:
                    return True, "file_layers_category"

        if combination_hash in dedup_state["hashes"]:
            return True, "hash"

        return False, ""

    def _dedup_record(
        self,
        dedup_state: Dict[str, Any],
        combination_hash: str,
        layer_states: Dict[int, str],
        category: Optional[str] = None,
    ):
        """统一记录去重状态。"""
        strategy = dedup_state.get("strategy", "none")
        if strategy == "none":
            return

        dedup_state["hashes"].add(combination_hash)

        if strategy == "layered":
            file_sig = self._build_layer_file_signature(layer_states)
            dedup_state["file_signatures"].add(file_sig)
            if category is not None:
                dedup_state["file_category_signatures"].add((str(category), file_sig))

    def _set_precompute_diagnostics(self, diagnostics: Optional[Dict[str, Any]]):
        """记录最近一次预计算诊断信息，供执行器写入导出报告。"""
        if isinstance(diagnostics, dict):
            self._last_precompute_diagnostics = diagnostics
        else:
            self._last_precompute_diagnostics = {}

    def _get_binding_relax_config(self) -> Dict[str, Any]:
        """读取绑定模式去重放宽配置（迭代2.3）。"""
        settings = getattr(self.document, 'export_settings', {}) or {}
        enabled = bool(settings.get('binding_relax_dedup_enabled', True))
        min_attempts = int(settings.get('binding_relax_min_attempts', 80) or 80)
        min_duplicate_attempts = int(settings.get('binding_relax_min_duplicate_attempts', 40) or 40)
        max_success_rate = float(settings.get('binding_relax_max_success_rate', 0.2) or 0.2)
        return {
            "enabled": enabled,
            "min_attempts": max(1, min_attempts),
            "min_duplicate_attempts": max(1, min_duplicate_attempts),
            "max_success_rate": max(0.0, min(1.0, max_success_rate)),
        }

    def _get_dynamic_budget_config(self, mode: str, base_limit: int) -> Dict[str, Any]:
        """读取动态预算配置（迭代3）。"""
        # 按任务自动计算，不提供UI自定义入口（默认功能）
        enabled = True
        if mode == "binding":
            min_ratio = 0.85
            max_ratio = 3.0
            check_interval = 18
            min_samples = 26
            expand_step = 0.20
            shrink_step = 0.10
            low_success = 0.18
            high_success = 0.62
            high_duplicate = 0.70
            low_duplicate = 0.28
        else:
            min_ratio = 0.7
            max_ratio = 2.2
            check_interval = 20
            min_samples = 28
            expand_step = 0.16
            shrink_step = 0.14
            low_success = 0.14
            high_success = 0.68
            high_duplicate = 0.74
            low_duplicate = 0.30

        # 小任务提高响应速度，避免预算调节过慢
        if base_limit <= 120:
            check_interval = max(10, check_interval // 2)
            min_samples = max(12, min_samples // 2)
            max_ratio = max(1.8, max_ratio - 0.4)

        min_limit = max(1, int(base_limit * max(0.2, min_ratio)))
        max_limit = max(min_limit, int(base_limit * max(1.0, max_ratio)))

        return {
            "enabled": enabled,
            "check_interval": max(5, check_interval),
            "min_samples": max(10, min_samples),
            "expand_step": max(0.05, min(1.0, expand_step)),
            "shrink_step": max(0.01, min(0.5, shrink_step)),
            "low_success": max(0.0, min(1.0, low_success)),
            "high_success": max(0.0, min(1.0, high_success)),
            "high_duplicate": max(0.0, min(1.0, high_duplicate)),
            "low_duplicate": max(0.0, min(1.0, low_duplicate)),
            "min_limit": min_limit,
            "max_limit": max_limit,
        }

    def _create_dynamic_budget_state(self, mode: str, base_limit: int) -> Dict[str, Any]:
        config = self._get_dynamic_budget_config(mode, base_limit)
        return {
            "mode": mode,
            "base_limit": int(base_limit),
            "current_limit": int(base_limit),
            "config": config,
            "expanded_times": 0,
            "shrunk_times": 0,
            "events": [],
        }

    def _maybe_rebalance_dynamic_budget(self, state: Dict[str, Any], attempts: int, generated: int, duplicate_attempts: int):
        """按实时成功率/重复率动态调整尝试预算。"""
        config = state.get("config", {})
        if not config.get("enabled", True):
            return
        if attempts < config["min_samples"]:
            return
        if attempts % config["check_interval"] != 0:
            return

        current_limit = int(state.get("current_limit", state.get("base_limit", attempts)))
        success_rate = self._safe_ratio(generated, attempts)
        duplicate_rate = self._safe_ratio(duplicate_attempts, attempts)
        next_limit = current_limit
        action = ""

        if success_rate <= config["low_success"] or duplicate_rate >= config["high_duplicate"]:
            grow = max(1, int(current_limit * config["expand_step"]))
            next_limit = min(config["max_limit"], current_limit + grow)
            if next_limit > current_limit:
                action = "expand"
                state["expanded_times"] = int(state.get("expanded_times", 0)) + 1
        elif success_rate >= config["high_success"] and duplicate_rate <= config["low_duplicate"]:
            shrink = max(1, int(current_limit * config["shrink_step"]))
            floor = max(config["min_limit"], attempts + config["check_interval"])
            next_limit = max(floor, current_limit - shrink)
            if next_limit < current_limit:
                action = "shrink"
                state["shrunk_times"] = int(state.get("shrunk_times", 0)) + 1

        state["current_limit"] = int(next_limit)
        if action:
            events = state.setdefault("events", [])
            events.append({
                "action": action,
                "at_attempt": int(attempts),
                "old_limit": int(current_limit),
                "new_limit": int(next_limit),
                "success_rate": float(success_rate),
                "duplicate_rate": float(duplicate_rate),
            })
            if len(events) > 8:
                del events[:-8]

    def _build_dynamic_budget_summary(self, state: Dict[str, Any], attempts: int, generated: int, duplicate_attempts: int) -> Dict[str, Any]:
        return {
            "enabled": bool(state.get("config", {}).get("enabled", True)),
            "mode": str(state.get("mode", "")),
            "base_limit": int(state.get("base_limit", 0)),
            "final_limit": int(state.get("current_limit", 0)),
            "expanded_times": int(state.get("expanded_times", 0)),
            "shrunk_times": int(state.get("shrunk_times", 0)),
            "attempts": int(attempts),
            "generated": int(generated),
            "duplicate_attempts": int(duplicate_attempts),
            "success_rate": self._safe_ratio(generated, attempts),
            "duplicate_rate": self._safe_ratio(duplicate_attempts, attempts),
            "events": list(state.get("events", [])),
        }

    def _safe_ratio(self, numerator: int, denominator: int) -> float:
        if denominator <= 0:
            return 0.0
        return float(numerator) / float(denominator)

    def _estimate_base_attempt_limit(
        self,
        mode: str,
        count: int,
        avoid_duplicates: bool,
        layer_pools: Optional[Dict[int, List[str]]] = None,
    ) -> int:
        """
        估算预计算基础尝试预算。
        目标：在保持去重效果的同时，减少"大池+多层"场景的无效尝试开销。
        """
        target = max(1, int(count or 0))
        pools = layer_pools if isinstance(layer_pools, dict) else (self.layer_image_pools or {})
        non_empty = [list(v) for v in pools.values() if isinstance(v, list) and len(v) > 0]
        layer_cnt = max(1, len(non_empty))
        avg_pool = float(sum([len(v) for v in non_empty])) / float(layer_cnt) if non_empty else 1.0

        if str(mode) == "binding":
            base = target * 55
            if avg_pool >= 12 and layer_cnt >= 3:
                base = int(base * 0.75)
            elif avg_pool <= 4:
                base = int(base * 1.30)
            if not avoid_duplicates:
                base = int(base * 0.85)
            low = target * 18
            high = target * 120
        else:
            base = target * (14 if avoid_duplicates else 8)
            if avg_pool >= 16 and layer_cnt >= 3:
                base = int(base * 0.70)
            elif avg_pool <= 3 or layer_cnt <= 2:
                base = int(base * 1.40)
            if bool(getattr(self, 'unique_use_enabled', False)):
                base = int(base * 1.30)
            low = target * 4
            high = target * 40

        return int(max(low, min(high, max(1, base))))

    def _build_shortage_analysis(self, diagnostics: Dict[str, Any], target_count: int, planned_count: int) -> Dict[str, Any]:
        """构建统一短缺分析，定位"为什么没凑满"。"""
        target = int(max(0, target_count))
        planned = int(max(0, planned_count))
        shortage = max(0, target - planned)
        attempts = int(diagnostics.get("attempts", 0) or 0)
        duplicates = int(diagnostics.get("duplicate_attempts", 0) or 0)
        dedup_hits = diagnostics.get("dedup_hits", {}) or {}
        dedup_total = int(sum(int(v or 0) for v in dedup_hits.values()))
        success_rate = self._safe_ratio(planned, attempts)
        duplicate_rate = self._safe_ratio(duplicates, attempts)

        reasons = []
        if shortage <= 0:
            reasons.append("target_reached")
        else:
            combo_space = diagnostics.get("combination_space", {}) or {}
            total_possible = int(combo_space.get("precompute_total_possible", 0) or combo_space.get("total_possible_estimate", 0) or 0)
            if total_possible > 0 and planned >= total_possible:
                reasons.append("combination_space_limited")
            if dedup_total > 0 and dedup_total >= max(10, shortage):
                reasons.append("dedup_blocking")
            if diagnostics.get("mode") == "binding":
                cat_usage = diagnostics.get("category_usage", {}) or {}
                used_categories = sum(1 for _, v in cat_usage.items() if int(v or 0) > 0)
                total_categories = len(diagnostics.get("available_categories", []) or [])
                if total_categories > 0 and used_categories < total_categories:
                    reasons.append("category_coverage_low")
                if diagnostics.get("force_generate_used"):
                    reasons.append("force_generate_activated")
            if not reasons:
                reasons.append("generation_efficiency_low")

        return {
            "target_count": target,
            "planned_count": planned,
            "shortage_count": shortage,
            "attempts": attempts,
            "duplicate_attempts": duplicates,
            "success_rate": success_rate,
            "duplicate_rate": duplicate_rate,
            "dedup_total_hits": dedup_total,
            "primary_reasons": reasons,
        }
