# -*- coding: utf-8 -*-
"""导出数量约束逻辑（P2 拆分超大文件）。

原属于 BatchExportPrecomputerV2 的一组方法，按"低风险评估、行为零变化"原则抽离为 mixin。
方法内对 self 的访问（self.document / self.layer_image_pools / self.unique_use_* /
self._precompute_total_possible 等）仍指向主类实例，故迁移不改任何运行时行为；调用点（self._xxx）不变。

契约镜像（与主模块保持一致，避免窗口程序下内置 print 崩溃）：
- print 复用编码安全的 safe_print；
- logger 使用本模块名（异常仍带 exc_info 记录）。
"""
import logging
import os
from typing import Any, Dict

from app.utils.print_utils import safe_print as print

logger = logging.getLogger(__name__)


class BatchExportConstraintMixin:
    """导出数量约束：唯一使用限制、理论组合数限制等。"""

    # =========================
    def _build_constraint_context(self, requested_count: int, avoid_duplicates: bool) -> Dict[str, Any]:
        """构建导出约束上下文（不改变行为，仅集中管理）。"""
        return {
            "requested_count": int(requested_count),
            "target_count": int(requested_count),
            "avoid_duplicates": bool(avoid_duplicates),
            "adjustment_reasons": [],
        }

    def _apply_unique_use_constraints(self, ctx: Dict[str, Any]):
        """应用唯一使用约束并更新目标导出数量。"""
        if not (self.unique_use_enabled and self.unique_use_layers):
            return

        try:
            caps = []
            valid_indices = []
            for idx in self.unique_use_layers:
                if not self._is_unique_use_eligible_layer(idx):
                    try:
                        layer_name = self.document.layers[int(idx)].name
                        print(f"[V2] 跳过不适用图像唯一使用的图层: {idx} '{layer_name}'")
                    except Exception:
                        logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                        pass
                    continue
                pool = [
                    path for path in self.layer_image_pools.get(idx, [])
                    if isinstance(path, str) and os.path.isfile(path)
                ]
                if pool:
                    caps.append(len(pool))
                    valid_indices.append(idx)
                    self._unique_used_map.setdefault(idx, set())
            if not caps:
                return

            unique_cap = min(caps)
            original_count = ctx["target_count"]
            ctx["target_count"] = min(ctx["target_count"], unique_cap)
            self.unique_use_layers = valid_indices

            if original_count != ctx["target_count"]:
                print(f"[V2] 图像唯一使用限制：最大可导出 {unique_cap} 张，调整为 {ctx['target_count']} 张")
                layer_names = []
                try:
                    for idx in valid_indices:
                        if idx < len(self.document.layers):
                            layer_names.append(self.document.layers[idx].name)
                except Exception:
                    layer_names = []
                if layer_names:
                    ctx["adjustment_reasons"].append(
                        f"图像唯一使用限制：所选图层最小图片数为 {unique_cap}（{', '.join(layer_names)}）"
                    )
                else:
                    ctx["adjustment_reasons"].append(f"图像唯一使用限制：最大可导出 {unique_cap} 张")
        except Exception as e:
            print(f"[V2] 图像唯一使用限制计算失败: {e}")

    def _apply_total_possible_constraints(self, ctx: Dict[str, Any]):
        """理论唯一组合不足时压缩导出数量，保持避免重复语义。"""
        if not (ctx["avoid_duplicates"] and self._precompute_total_possible and self._precompute_total_possible > 0):
            return

        if ctx["target_count"] > self._precompute_total_possible:
            print(
                f"[V2] 请求导出 {ctx['target_count']} 张，理论唯一组合只有 "
                f"{self._precompute_total_possible}，避免重复已启用，将导出数量调整为唯一组合数"
            )
            ctx["target_count"] = int(self._precompute_total_possible)
            ctx["adjustment_reasons"].append(
                f"唯一组合不足：理论唯一组合数仅 {self._precompute_total_possible}，避免重复已启用，已停止重复补足"
            )
