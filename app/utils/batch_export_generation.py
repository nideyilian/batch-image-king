# -*- coding: utf-8 -*-
"""组合生成核心 mixin（从 BatchExportPrecomputerV2 抽取，方法体原样迁移）。

两个方法（_generate_binding_combinations_v2 / _generate_standard_combinations_v2）为组合枚举主循环，
仅访问主类实例属性（self.*）与同组方法，调用点均为 self._xxx；迁移后由主类实例兜底，行为零变化。

编码安全契约：主模块顶部有 print = _safe_print 与模块级 logger；本 mixin 方法使用 print
（编码安全别名）与 logger.warning(..., exc_info=True)，故在此镜像主模块契约，避免退化。
"""
import logging
import hashlib
import math
import os
import random
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

from app.utils.batch_export_plan_models import LayerCombination
from app.utils.print_utils import safe_print as print

logger = logging.getLogger(__name__)


class BatchExportGenerationMixin:
    def _generate_binding_combinations_v2(self, count: int, avoid_duplicates: bool,
                                          cancel_callback: Optional[Callable[[], bool]] = None,
                                          progress_start: Optional[float] = None) -> List['LayerCombination']:
        """🔧 强化预计算V2 - 彻底修复重复问题"""
        print(f"[预计算强化V2] 🚀 开始生成 {count} 个完全预计算的组合")
        print(f"[预计算强化V2] 避重模式: {'开启' if avoid_duplicates else '关闭'}")

        combinations = []
        import random
        import time
        
        # 全局避重管理器
        global_avoid_manager = self._get_avoid_repeat_manager()
        
        # 迭代2.1：统一去重策略入口（默认保持原行为）
        dedup_strategy = self._resolve_dedup_strategy("binding", avoid_duplicates)
        dedup_state = self._create_dedup_state(dedup_strategy)
        dedup_hits = {"hash": 0, "file_layers": 0, "file_layers_category": 0, "other": 0}
        
        base_max_attempts = self._estimate_base_attempt_limit(
            mode="binding",
            count=count,
            avoid_duplicates=avoid_duplicates,
            layer_pools=self.layer_image_pools,
        )
        attempts = 0
        duplicate_attempts = 0
        dynamic_budget_state = self._create_dynamic_budget_state("binding", base_max_attempts)
        
        # 🔧 关键修复2: 智能分类轮换策略
        category_usage_tracker = {}  # 记录每个分类被使用的次数
        for cat in self.binding_categories:
            category_usage_tracker[cat] = 0
        
        # 🔧 关键修复：添加分类轮换索引，确保分类顺序使用而非随机选择
        category_rotation_index = 0
        
        print(f"[预计算强化V2] 可用分类: {self.binding_categories}")
        print(f"[预计算强化V2] 开始生成...")

        successfully_generated = 0
        relax_dedup = False  # 动态放宽避重：在组合空间不足时启用
        relax_trigger_attempt = 0
        relax_trigger_reason = ""
        pre_relax_generated = 0
        pre_relax_attempts = 0
        force_generate = False  # 强制生成模式：在接近上限时启用
        relax_config = self._get_binding_relax_config()
        progress_start = progress_start or time.time()
        self._render_progress_line("预计算", 0, count, progress_start, force=True)

        while successfully_generated < count and attempts < int(dynamic_budget_state["current_limit"]):
            if cancel_callback and cancel_callback():
                self._was_canceled = True
                self._render_progress_line("预计算", successfully_generated, count, progress_start, force=True)
                self._finish_progress_line()
                self._set_precompute_diagnostics({
                    "mode": "binding",
                    "dedup_strategy": dedup_strategy,
                    "requested_count": int(count),
                    "generated_count": int(len(combinations)),
                    "attempts": int(attempts),
                    "duplicate_attempts": int(duplicate_attempts),
                    "dedup_hits": dedup_hits,
                    "category_usage": {str(k): int(v) for k, v in category_usage_tracker.items()},
                    "available_categories": [str(c) for c in self.binding_categories],
                    "force_generate_used": bool(force_generate),
                    "relax_dedup_used": bool(relax_dedup),
                    "relax_trigger_attempt": int(relax_trigger_attempt),
                    "relax_trigger_reason": str(relax_trigger_reason),
                    "relax_gain_count": int(max(0, len(combinations) - pre_relax_generated)) if relax_dedup else 0,
                    "relax_gain_attempts": int(max(0, attempts - pre_relax_attempts)) if relax_dedup else 0,
                    "relax_config": dict(relax_config),
                    "dynamic_budget": self._build_dynamic_budget_summary(
                        dynamic_budget_state,
                        attempts=attempts,
                        generated=len(combinations),
                        duplicate_attempts=duplicate_attempts,
                    ),
                    "combination_space": {"precompute_total_possible": int(self._precompute_total_possible or 0)},
                })
                return combinations

            attempts += 1
            self._maybe_rebalance_dynamic_budget(
                dynamic_budget_state,
                attempts=attempts,
                generated=successfully_generated,
                duplicate_attempts=duplicate_attempts,
            )
            budget_limit = int(dynamic_budget_state["current_limit"])
            
            # 🔧 立即激活强制生成模式，如果成功率极低
            if not force_generate and attempts > 50 and successfully_generated <= 5:
                print(f"[预计算强化V2] 🚨 检测到生成困难，立即启用强制生成模式")
                force_generate = True
                duplicate_attempts = 0
                # 重置一些状态，给强制生成模式重新开始的机会
                dedup_state = self._create_dedup_state(dedup_strategy)

            if attempts >= budget_limit:
                print(f"[预计算强化V2] ⚠️ 达到当前预算上限 {budget_limit}，停止生成")
                print(f"[预计算强化V2] 成功生成 {successfully_generated}/{count} 个唯一组合")
                print(f"[预计算强化V2] 重复尝试次数: {duplicate_attempts}")
                
                # 🔧 终极修复：如果还远未达到目标，强制生成剩余组合
                if successfully_generated < count * 0.8:  # 如果完成度低于80%
                    remaining = count - successfully_generated
                    print(f"[预计算强化V2] 🚨 完成度过低({successfully_generated}/{count})，启动强制生成剩余{remaining}个组合")
                    
                    # 强制生成剩余组合，绕过大部分检查
                    force_generate = True
                    force_attempts = 0
                    max_force_attempts = remaining * 50
                    
                    while successfully_generated < count and force_attempts < max_force_attempts:
                        if cancel_callback and cancel_callback():
                            self._was_canceled = True
                            self._render_progress_line("预计算", successfully_generated, count, progress_start, force=True)
                            self._finish_progress_line()
                            self._set_precompute_diagnostics({
                                "mode": "binding",
                                "dedup_strategy": dedup_strategy,
                                "requested_count": int(count),
                                "generated_count": int(len(combinations)),
                                "attempts": int(attempts),
                                "duplicate_attempts": int(duplicate_attempts),
                                "dedup_hits": dedup_hits,
                                "category_usage": {str(k): int(v) for k, v in category_usage_tracker.items()},
                                "available_categories": [str(c) for c in self.binding_categories],
                                "force_generate_used": bool(force_generate),
                                "relax_dedup_used": bool(relax_dedup),
                                "relax_trigger_attempt": int(relax_trigger_attempt),
                                "relax_trigger_reason": str(relax_trigger_reason),
                                "relax_gain_count": int(max(0, len(combinations) - pre_relax_generated)) if relax_dedup else 0,
                                "relax_gain_attempts": int(max(0, attempts - pre_relax_attempts)) if relax_dedup else 0,
                                "relax_config": dict(relax_config),
                                "dynamic_budget": self._build_dynamic_budget_summary(
                                    dynamic_budget_state,
                                    attempts=attempts,
                                    generated=len(combinations),
                                    duplicate_attempts=duplicate_attempts,
                                ),
                                "combination_space": {"precompute_total_possible": int(self._precompute_total_possible or 0)},
                            })
                            return combinations

                        force_attempts += 1
                        
                        # 使用简单的轮换策略
                        category = self.binding_categories[force_attempts % len(self.binding_categories)]
                        
                        # 尝试获取基础状态，失败也继续
                        layer_states = self._get_diverse_binding_layer_states(category, global_avoid_manager, successfully_generated, avoid_duplicates)
                        
                        # 如果完全没有状态，尝试基础补全
                        if not layer_states:
                            layer_states = {}
                            for visible_idx, layer in enumerate(self.visible_layers):
                                layer_idx = self._to_doc_layer_idx(visible_idx)
                                try:
                                    if hasattr(layer, 'get_text_lines'):
                                        curr = getattr(layer, 'current_text', '示例文字')
                                        layer_states[layer_idx] = self._build_text_virtual_path(layer.name, curr)
                                    else:
                                        src = getattr(layer, 'image_source', None)
                                        if src and os.path.isdir(src):
                                            files = self._get_folder_images_cached(src)
                                            if files:
                                                layer_states[layer_idx] = files[force_attempts % len(files)]
                                except Exception:
                                    logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                                    pass
                        
                        if layer_states:
                            # 简化版组合生成
                            file_sig = self._build_layer_file_signature(layer_states)
                            combination_hash = hashlib.md5(str(file_sig).encode()).hexdigest()[:16]
                            should_skip, _ = self._dedup_should_skip(
                                dedup_state=dedup_state,
                                combination_hash=combination_hash,
                                layer_states=layer_states,
                                category=category,
                                force_hash_only=True,
                            )
                            if not should_skip:
                                self._dedup_record(
                                    dedup_state=dedup_state,
                                    combination_hash=combination_hash,
                                    layer_states=layer_states,
                                    category=category,
                                )
                                combination = LayerCombination(
                                    index=successfully_generated,
                                    layer_states=layer_states,
                                    layer_clone_settings={},
                                    combination_hash=combination_hash,
                                    is_unique=True,
                                    random_transforms={},
                                    layer_parameters={}
                                )
                                combinations.append(combination)
                                successfully_generated += 1
                                self._render_progress_line("预计算", successfully_generated, count, progress_start)
                            else:
                                duplicate_attempts += 1
                                dedup_hits["hash"] += 1
                else:
                    # 如果已经达到80%以上，直接退出
                    print(f"[预计算强化V2] ✅ 已达到目标完成度，正常结束")
                break
            
            # 🔧 提前触发强制生成：在达到最大尝试次数前就启用，如果成功率极低
            current_success_rate = successfully_generated / attempts if attempts > 0 else 0
            if not force_generate and attempts > budget_limit * 0.6 and successfully_generated < count * 0.3 and current_success_rate < 0.01:
                print(f"[预计算强化V2] 🚨 成功率过低({current_success_rate*100:.1f}%)，提前启用强制生成模式")
                force_generate = True

            # 迭代2.3：当 layered 去重命中过高时，放宽到 hash 层，优先凑满唯一组合
            if (
                avoid_duplicates
                and dedup_strategy == "layered"
                and not relax_dedup
                and relax_config.get("enabled", True)
            ):
                should_relax = (
                    attempts >= relax_config["min_attempts"]
                    and duplicate_attempts >= relax_config["min_duplicate_attempts"]
                    and current_success_rate <= relax_config["max_success_rate"]
                )
                if should_relax:
                    relax_dedup = True
                    relax_trigger_attempt = attempts
                    pre_relax_generated = successfully_generated
                    pre_relax_attempts = attempts
                    relax_trigger_reason = (
                        f"attempts={attempts}, duplicate_attempts={duplicate_attempts}, "
                        f"success_rate={current_success_rate:.4f}"
                    )
                    print(f"[预计算强化V2] ⚙️ 启用去重放宽：layered -> hash-only（{relax_trigger_reason}）")
            
            # 🔧 关键修复3: 使用轮换策略而非随机选择，确保分类均衡且不重复
            # 问题根源：random.choice()可能导致某些分类被过度使用
            # 解决方案：按顺序轮换分类，确保每个分类都被均匀使用
            sorted_categories = sorted(category_usage_tracker.items(), key=lambda x: x[1])
            min_usage = sorted_categories[0][1]
            least_used_cats = [cat for cat, usage in sorted_categories if usage == min_usage]
            
            # 使用轮换索引选择，而非随机选择
            category_index = category_rotation_index % len(least_used_cats)
            category = least_used_cats[category_index]
            category_rotation_index += 1
            
            # 🔧 强制生成模式：直接生成简化组合，绕过复杂逻辑
            if force_generate:
                # 强制生成模式：使用简单轮换策略
                layer_states = {}
                for visible_idx, layer in enumerate(self.visible_layers):
                    layer_idx = self._to_doc_layer_idx(visible_idx)
                    try:
                        is_bound = layer in self.bound_layers
                        if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)):
                            # 文字图层：绑定图层尝试匹配分类，非绑定图层不受分类限制
                            lines = []
                            try:
                                lines = [l for l in layer.get_text_lines() if str(l).strip()]
                            except Exception:
                                lines = []
                            
                            chosen = None
                            if is_bound:
                                for line in lines:
                                    if str(category) in str(line):
                                        chosen = str(line).strip()
                                        break
                            else:
                                if lines:
                                    chosen = str(lines[attempts % len(lines)]).strip()
                            
                            if not chosen:
                                curr = getattr(layer, 'current_text', f'{category}文字')
                                if curr:
                                    chosen = str(curr).strip()
                            
                            if chosen:
                                layer_states[layer_idx] = self._build_text_virtual_path(layer.name, chosen)
                            else:
                                layer_states[layer_idx] = self._build_text_virtual_path(layer.name, f"{category}示例文字")
                        else:
                            # 图像图层：绑定图层尝试匹配分类，非绑定图层不受分类限制
                            src = getattr(layer, 'image_source', None)
                            if src:
                                if os.path.isdir(src):
                                    # 尝试找分类相关文件
                                    try:
                                        if is_bound:
                                            files = self._get_folder_images_cached(src, category=str(category))
                                            if not files:
                                                files = self._get_folder_images_cached(src)
                                        else:
                                            files = self._get_folder_images_cached(src)
                                        
                                        if files:
                                            layer_states[layer_idx] = files[attempts % len(files)]
                                        else:
                                            layer_states[layer_idx] = f"default_{category}_image.jpg"
                                    except Exception:
                                        layer_states[layer_idx] = f"default_{category}_image.jpg"
                                else:
                                    layer_states[layer_idx] = src
                            else:
                                layer_states[layer_idx] = f"default_{category}_image.jpg"
                    except Exception as e:
                        print(f"[强制生成] 图层{layer_idx}处理失败: {e}")
                        # 最差情况下的回退
                        if hasattr(layer, 'get_text_lines'):
                            layer_states[layer_idx] = self._build_text_virtual_path(layer.name, f"{category}回退文字")
                        else:
                            layer_states[layer_idx] = f"default_{category}_fallback.jpg"
            else:
                # 正常模式：使用复杂的绑定组逻辑
                # 🔧 关键步骤1：从绑定组获取图层状态
                print(f"[🔍 预计算循环] 步骤1: 调用 _get_diverse_binding_layer_states...")
                layer_states = self._get_diverse_binding_layer_states(category, global_avoid_manager, successfully_generated, avoid_duplicates)
                print(f"[🔍 预计算循环] 步骤1完成: 获得 {len(layer_states)} 个图层状态")
                # 🐛 调试：打印 layer_states 的详细信息
                for layer_idx, img_path in layer_states.items():
                    print(f"[🔍 预计算调试] layer_states[{layer_idx}] = {os.path.basename(img_path) if img_path else 'None'}")
                
                # 🔧 激进修复：即使绑定组状态为空或部分，也继续尝试生成
                # 问题根源：过于依赖绑定组提供完整状态，导致分类利用率极低
                # 解决方案：允许部分状态，通过后续补全机制填充
                if not layer_states:
                    print(f"[🔍 预计算循环] ⚠️ layer_states 为空，但继续尝试补全")
                    # 不立即跳过，而是尝试通过非绑定图层选择器补全
                elif len(layer_states) < len(self.visible_layers):
                    print(f"[🔍 预计算循环] ⚠️ layer_states 部分缺失 ({len(layer_states)}/{len(self.visible_layers)})，尝试补全")
            
            # 🔧 早期预警：如果进度过于缓慢，提前启用强制模式
            current_success_rate = successfully_generated / attempts if attempts > 0 else 0
            if not force_generate and attempts > budget_limit * 0.1 and successfully_generated < count * 0.5 and current_success_rate < 0.1:
                print(f"[预计算强化V2] 🚨 成功率过低({current_success_rate*100:.1f}%)，提前启用强制生成模式")
                force_generate = True
                # 重置计数器，给强制生成模式重新开始的机会
                duplicate_attempts = 0
                print(f"[预计算强化V2] 🔄 切换到强制生成模式，重置重复计数器")
            
            # 🔧 关键步骤2：补充非绑定图层（不受绑定分类限制）
            if hasattr(self, 'non_binding_layer_selectors'):
                for layer_idx, selector in self.non_binding_layer_selectors.items():
                    if layer_idx not in layer_states and selector:
                        try:
                            raw_pool = selector.image_pool if hasattr(selector, 'image_pool') else []
                            pool_size = len(raw_pool)
                            if pool_size > 0:
                                selector_index = (successfully_generated * 7919 + layer_idx * 9973) % pool_size
                                selected_file = raw_pool[selector_index]
                                layer_states[layer_idx] = selected_file
                            else:
                                # 回退：使用选择器的下一个文件
                                next_file = selector.select_next_file() if hasattr(selector, 'select_next_file') else None
                                if next_file:
                                    layer_states[layer_idx] = next_file
                        except Exception as e:
                            next_file = selector.select_next_file() if hasattr(selector, 'select_next_file') else None
                            if next_file:
                                layer_states[layer_idx] = next_file

            # 图像唯一使用：对指定图层替换已使用的文件
            if self.unique_use_enabled and self.unique_use_layers and layer_states:
                for doc_layer_idx in list(layer_states.keys()):
                    if doc_layer_idx in self.unique_use_layers and self._is_unique_use_eligible_layer(doc_layer_idx):
                        used = self._unique_used_map.setdefault(doc_layer_idx, set())
                        if layer_states[doc_layer_idx] in used:
                            pool = self.layer_image_pools.get(doc_layer_idx, [])
                            candidates = [p for p in pool if p not in used]
                            if candidates:
                                import random
                                layer_states[doc_layer_idx] = random.choice(candidates)
                            else:
                                # 无可用文件，跳过本次生成尝试
                                continue
            
            # 🔧 激进修复：当绑定组完全无法提供状态时，尝试为所有可见图层补全
            if not layer_states and hasattr(self, 'visible_layers'):
                print(f"[🔍 预计算循环] ⚠️ 绑定组状态完全为空，尝试为所有可见图层补全")
                layer_states = {}
                
                for visible_idx, layer in enumerate(self.visible_layers):
                    layer_idx = self._to_doc_layer_idx(visible_idx)
                    try:
                        if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)):
                            # 文字图层补全
                            lines = []
                            try:
                                lines = [l for l in layer.get_text_lines() if str(l).strip()]
                            except Exception:
                                lines = []
                            chosen = None
                            for l in lines:
                                if str(category) in str(l):
                                    chosen = str(l).strip()
                                    break
                            if not chosen:
                                curr = getattr(layer, 'current_text', '')
                                if curr and str(category) in str(curr):
                                    chosen = str(curr).strip()
                            if chosen:
                                layer_states[layer_idx] = self._build_text_virtual_path(layer.name, chosen)
                        else:
                            # 图像图层补全
                            src = getattr(layer, 'image_source', None)
                            if src and os.path.isdir(src):
                                base_pool = []
                                try:
                                    base_pool = self._get_folder_images_cached(src, category=str(category))
                                except Exception:
                                    base_pool = []
                                if base_pool:
                                    sel_index = (successfully_generated * 7919 + layer_idx * 9973) % len(base_pool)
                                    layer_states[layer_idx] = base_pool[sel_index]
                    except Exception:
                        logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                        pass
            
            # 🔧 关键步骤3：生成组合的唯一标识（保持图层顺序）
            file_names_tuple = self._build_layer_file_signature(layer_states)
            
            # 🔧 关键步骤4：预计算所有随机变换参数
            random_transforms = {}
            layer_parameters = {}
            layer_clone_settings = {}
            
            # 为每个图层预计算完整的参数
            for layer_idx, file_path in layer_states.items():
                layer = self._resolve_layer_by_state_index(layer_idx)
                if layer is not None:
                    
                    # 🔧 关键修复7: 生成**完全确定性**的随机种子
                    # 移除time.time_ns()以确保相同输入产生相同结果
                    # 只基于组合索引、图层索引和文件路径
                    random_seed = hash((successfully_generated, layer_idx, os.path.basename(file_path), category)) & 0x7FFFFFFF
                    rng = random.Random(random_seed)
                    
                    # 预计算随机变换
                    transform_params = {}
                    if hasattr(layer, 'random_position_enabled') and layer.random_position_enabled:
                        transform_params['random_offset_x'] = rng.randint(
                            -layer.random_position_range, 
                            layer.random_position_range
                        )
                        transform_params['random_offset_y'] = rng.randint(
                            -layer.random_position_range,
                            layer.random_position_range
                        )
                    else:
                        transform_params['random_offset_x'] = 0
                        transform_params['random_offset_y'] = 0
                    
                    if hasattr(layer, 'random_scale_enabled') and layer.random_scale_enabled:
                        transform_params['random_scale'] = rng.uniform(
                            layer.random_scale_min,
                            layer.random_scale_max
                        )
                    else:
                        transform_params['random_scale'] = 1.0
                    
                    if hasattr(layer, 'random_rotation_enabled') and layer.random_rotation_enabled:
                        transform_params['random_rotation'] = rng.uniform(
                            -layer.random_rotation_range,
                            layer.random_rotation_range
                        )
                    else:
                        transform_params['random_rotation'] = 0.0
                    
                    random_transforms[layer_idx] = transform_params
                    
                    # 捕获完整的图层参数
                    layer_params = {
                        'opacity': getattr(layer, 'opacity', 1.0),
                        'blend_mode': getattr(layer, 'blend_mode', 0),
                        'x': getattr(layer, 'x', 0),
                        'y': getattr(layer, 'y', 0),
                        'width': getattr(layer, 'width', 100),
                        'height': getattr(layer, 'height', 100),
                        'fit_mode': getattr(layer, 'fit_mode', 0),
                        'crop_direction': getattr(layer, 'crop_direction', 0),
                        'corner_radius': getattr(layer, 'corner_radius', 0),
                        'stroke_enabled': getattr(layer, 'stroke_enabled', False),
                        'stroke_width': getattr(layer, 'stroke_width', 1),
                        'stroke_color': getattr(layer, 'stroke_color', (0, 0, 0, 255)),
                        'stroke_type': getattr(layer, 'stroke_type', 0),
                        'color_overlay_enabled': getattr(layer, 'color_overlay_enabled', False),
                        'color_overlay_color': getattr(layer, 'color_overlay_color', (255, 0, 0, 255)),
                        'color_overlay_opacity': getattr(layer, 'color_overlay_opacity', 1.0),
                        'gradient_overlay_enabled': getattr(layer, 'gradient_overlay_enabled', False),
                        'gradient_overlay_colors': getattr(layer, 'gradient_overlay_colors', [(0, 0, 0, 255), (255, 255, 255, 255)]),
                        'gradient_overlay_angle': getattr(layer, 'gradient_overlay_angle', 90.0),
                        'gradient_overlay_opacity': getattr(layer, 'gradient_overlay_opacity', 1.0),
                        'shape_type': getattr(getattr(layer, 'shape_type', None), 'value', getattr(layer, 'shape_type', 'rectangle')),
                        'trapezoid_top_width': getattr(layer, 'trapezoid_top_width', 100),
                        'trapezoid_bottom_width': getattr(layer, 'trapezoid_bottom_width', 80),
                        'trapezoid_slope_side': getattr(layer, 'trapezoid_slope_side', 'right'),
                        'polygon_rotation': getattr(layer, 'polygon_rotation', 0.0),
                        'polygon_corner_radius': getattr(layer, 'polygon_corner_radius', 0),
                        'rotation': getattr(layer, 'rotation', 0.0),
                        'flip_horizontal': getattr(layer, 'flip_horizontal', False),
                        'flip_vertical': getattr(layer, 'flip_vertical', False),
                    }
                    layer_parameters[layer_idx] = layer_params
                    
                    # 捕获分身设置
                    if hasattr(layer, 'clone_enabled') and layer.clone_enabled:
                        clone_settings = {
                            'enabled': True,
                            'rows': getattr(layer, 'clone_rows', 2),
                            'columns': getattr(layer, 'clone_columns', 2),
                            'row_spacing': getattr(layer, 'clone_row_spacing', 10),
                            'column_spacing': getattr(layer, 'clone_column_spacing', 10),
                        }
                        layer_clone_settings[layer_idx] = clone_settings
            
            # 🔧 关键步骤5：生成包含所有参数的完整哈希
            import hashlib
            hash_parts = []
            for layer_idx in sorted(layer_states.keys()):
                file_path = layer_states[layer_idx]
                transform = random_transforms.get(layer_idx, {})
                params = layer_parameters.get(layer_idx, {})
                
                part = (
                    f"L{layer_idx}:"
                    f"{os.path.basename(file_path)}:"
                    f"offset({transform.get('random_offset_x',0)},{transform.get('random_offset_y',0)}):"
                    f"scale({transform.get('random_scale',1.0):.3f}):"
                    f"rot({transform.get('random_rotation',0.0):.2f}):"
                    f"opacity({params.get('opacity',1.0):.2f}):"
                    f"blend({params.get('blend_mode',0)})"
                )
                hash_parts.append(part)
            
            combination_str = "|".join(hash_parts)
            combination_hash = hashlib.md5(combination_str.encode()).hexdigest()[:16]
            
            # 🔧 关键修复6: 统一策略去重判断
            should_skip, skip_reason = self._dedup_should_skip(
                dedup_state=dedup_state,
                combination_hash=combination_hash,
                layer_states=layer_states,
                category=category,
                relax_dedup=relax_dedup,
            )
            if should_skip:
                duplicate_attempts += 1
                if skip_reason in dedup_hits:
                    dedup_hits[skip_reason] += 1
                else:
                    dedup_hits["other"] += 1
                self._maybe_rebalance_dynamic_budget(
                    dynamic_budget_state,
                    attempts=attempts,
                    generated=successfully_generated,
                    duplicate_attempts=duplicate_attempts,
                )
                if duplicate_attempts % 20 == 0:
                    if skip_reason == "file_layers":
                        print(f"[预计算强化V2] ⚠️ 文件名+图层重复 {duplicate_attempts} 次")
                    elif skip_reason == "file_layers_category":
                        print(f"[预计算强化V2] ⚠️ 文件+图层+分类重复 {duplicate_attempts} 次")
                    else:
                        print(f"[预计算强化V2] ⚠️ 完整哈希重复 {duplicate_attempts} 次")
                continue
            
            # 🎉 成功生成一个唯一组合！
            # 但在创建组合前进行100%准确率验证
            
            # 🔧 100%准确率验证：确保导出组合的语义正确性
            try:
                # 尝试导入绑定完整性管理器
                from binding_100_percent_fix import BindingIntegrityManager
                integrity_manager = BindingIntegrityManager()
                
                # 准备图层状态信息用于验证
                layer_states_info = []
                for layer_idx, file_path in layer_states.items():
                    layer = self._resolve_layer_by_state_index(layer_idx)
                    if layer is not None:
                        layer_info = {
                            'name': getattr(layer, 'name', f'Layer_{layer_idx}'),
                            'type': 'text' if hasattr(layer, 'get_text_lines') else 'image',
                            'content': layer.get_text_lines() if hasattr(layer, 'get_text_lines') else None
                        }
                        layer_states_info.append(layer_info)
                
                # 验证绑定准确性
                validation_result = integrity_manager.validate_binding_accuracy(
                    layer_states_info, layer_states, category
                )
                
                if validation_result['is_valid']:
                    print(f"[预计算强化V2] ✅ 100%准确率验证通过 - 组合 {successfully_generated + 1}")
                else:
                    print(f"[预计算强化V2] ⚠️ 发现绑定不准确，自动修复中...")
                    # 尝试自动修复
                    corrected_states = integrity_manager.enforce_100_percent_binding_accuracy(
                        layer_states_info, category, None  # 这里不需要额外文件列表
                    )
                    
                    if corrected_states:
                        layer_states = corrected_states
                        print(f"[预计算强化V2] ✅ 自动修复完成")
                    else:
                        print(f"[预计算强化V2] ❌ 无法自动修复，使用原组合")
                        
            except ImportError:
                print(f"[预计算强化V2] ⚠️ 100%准确率验证模块未找到，跳过验证")
            except Exception as validation_error:
                print(f"[预计算强化V2] ⚠️ 100%准确率验证出错: {validation_error}")
                # 验证出错时继续使用原结果，不影响正常流程
            
            # 记录去重状态
            self._dedup_record(
                dedup_state=dedup_state,
                combination_hash=combination_hash,
                layer_states=layer_states,
                category=category,
            )
            
            # 🔧 关键步骤7：创建完整的预计算组合对象
            combination = LayerCombination(
                index=successfully_generated,
                layer_states=layer_states,
                layer_clone_settings=layer_clone_settings,
                combination_hash=combination_hash,
                is_unique=True,
                random_transforms=random_transforms,  # 完整的随机变换参数
                layer_parameters=layer_parameters     # 完整的图层参数
            )
            combinations.append(combination)
            
            # 记录分类使用
            category_usage_tracker[category] += 1
            successfully_generated += 1
            self._render_progress_line("预计算", successfully_generated, count, progress_start)

            # 唯一使用：记录本次消耗的文件
            if self.unique_use_enabled and self.unique_use_layers:
                for doc_layer_idx, file_path in layer_states.items():
                    if doc_layer_idx in self.unique_use_layers and self._is_unique_use_eligible_layer(doc_layer_idx):
                        self._unique_used_map.setdefault(doc_layer_idx, set()).add(file_path)
            
            # 🔍 详细显示信息（前10个、每50个、最后10个）
            should_log_detail = (
                successfully_generated <= 10 or
                successfully_generated % 50 == 0 or
                successfully_generated >= count - 10
            )
            
            if should_log_detail:
                print(f"\n[预计算强化V2] ✅ 第 {successfully_generated}/{count} 个组合:")
                print(f"  - 完整哈希: {combination_hash}")
                print(f"  - 分类: {category}")
                print(f"  - 图层-文件映射:")
                for layer_idx in sorted(layer_states.keys()):
                    file_name = os.path.basename(layer_states[layer_idx])
                    print(f"    L{layer_idx}: {file_name}")
                if successfully_generated <= 10 and combination.random_transforms:
                    print(f"  - 随机变换:")
                    for layer_idx in sorted(combination.random_transforms.keys())[:2]:
                        t = combination.random_transforms[layer_idx]
                        print(f"    L{layer_idx}: offset=({t['random_offset_x']},{t['random_offset_y']}), "
                              f"scale={t['random_scale']:.3f}, rot={t['random_rotation']:.2f}°")

        self._render_progress_line("预计算", min(len(combinations), count), count, progress_start, force=True)
        self._finish_progress_line()

        print(f"\n[预计算强化V2] ✅ 预计算完成!")
        print(f"  - 目标数量: {count}")
        print(f"  - 实际生成: {len(combinations)}")
        print(f"  - 成功率: {len(combinations)/count*100:.1f}%")
        print(f"  - 总尝试次数: {attempts}")
        print(f"  - 重复尝试: {duplicate_attempts}")
        print(f"  - 重复率: {duplicate_attempts/attempts*100:.1f}%")
        print(f"  - 分类使用情况: {category_usage_tracker}")
        print(f"  - 去重策略: {dedup_strategy}")
        print(f"  - 唯一文件组合: {len(dedup_state.get('file_signatures', set()))}")
        print(f"  - 唯一完整哈希: {len(dedup_state.get('hashes', set())) if dedup_state.get('hashes') else 'N/A'}")
        self._set_precompute_diagnostics({
            "mode": "binding",
            "dedup_strategy": dedup_strategy,
            "requested_count": int(count),
            "generated_count": int(len(combinations)),
            "attempts": int(attempts),
            "duplicate_attempts": int(duplicate_attempts),
            "dedup_hits": dedup_hits,
            "category_usage": {str(k): int(v) for k, v in category_usage_tracker.items()},
            "available_categories": [str(c) for c in self.binding_categories],
            "force_generate_used": bool(force_generate),
            "relax_dedup_used": bool(relax_dedup),
            "relax_trigger_attempt": int(relax_trigger_attempt),
            "relax_trigger_reason": str(relax_trigger_reason),
            "relax_gain_count": int(max(0, len(combinations) - pre_relax_generated)) if relax_dedup else 0,
            "relax_gain_attempts": int(max(0, attempts - pre_relax_attempts)) if relax_dedup else 0,
            "relax_config": dict(relax_config),
            "dynamic_budget": self._build_dynamic_budget_summary(
                dynamic_budget_state,
                attempts=attempts,
                generated=len(combinations),
                duplicate_attempts=duplicate_attempts,
            ),
            "combination_space": {
                "precompute_total_possible": int(self._precompute_total_possible or 0),
                "unique_hash_count": int(len(dedup_state.get("hashes", set()))),
                "unique_file_signature_count": int(len(dedup_state.get("file_signatures", set()))),
            },
        })
        
        if len(combinations) < count:
            print(f"[预计算强化V2] ⚠️ 可用唯一组合不足，已按最大唯一组合返回")
        
        return combinations


    def _generate_standard_combinations_v2(self, count: int, avoid_duplicates: bool,
                                           cancel_callback: Optional[Callable[[], bool]] = None,
                                           progress_start: Optional[float] = None) -> List['LayerCombination']:
        """V2 -  """
        print(f"[V2] : {count} ")

        combinations = []
        import random
        
        #  
        global_avoid_manager = self._get_avoid_repeat_manager()
        
        # 迭代2.1：统一去重策略入口（标准模式默认 hash）
        dedup_strategy = self._resolve_dedup_strategy("standard", avoid_duplicates)
        dedup_state = self._create_dedup_state(dedup_strategy)
        dedup_hits = {"hash": 0, "file_layers": 0, "file_layers_category": 0, "other": 0}
        base_max_attempts = self._estimate_base_attempt_limit(
            mode="standard",
            count=count,
            avoid_duplicates=avoid_duplicates,
            layer_pools=self.layer_image_pools,
        )
        attempts = 0
        duplicate_attempts = 0
        total_possible_estimate = 0
        deterministic_enumeration_used = False
        dynamic_budget_state = self._create_dynamic_budget_state("standard", base_max_attempts)
        
        #  
        optimized_pools = global_avoid_manager.optimize_image_pools(self.layer_image_pools, cancel_callback=cancel_callback)
        # 会话级均衡状态：压制"组合唯一但视觉上重复刷同一张"
        layer_session_usage: Dict[int, Dict[str, int]] = {
            int(layer_idx): {} for layer_idx, pool in optimized_pools.items() if pool
        }
        layer_recent_choices: Dict[int, List[str]] = {
            int(layer_idx): [] for layer_idx, pool in optimized_pools.items() if pool
        }
        recent_window = 4
        progress_start = progress_start or time.time()
        self._render_progress_line("预计算", 0, count, progress_start, force=True)

        try:
            non_empty = [(k, v) for k, v in sorted(optimized_pools.items(), key=lambda x: x[0]) if v]
            if not non_empty:
                self._set_precompute_diagnostics({
                    "mode": "standard",
                    "dedup_strategy": dedup_strategy,
                    "requested_count": int(count),
                    "generated_count": 0,
                    "attempts": 0,
                    "duplicate_attempts": 0,
                    "dedup_hits": dedup_hits,
                    "dynamic_budget": self._build_dynamic_budget_summary(
                        dynamic_budget_state, attempts=0, generated=0, duplicate_attempts=0
                    ),
                    "combination_space": {"total_possible_estimate": 0},
                })
                self._finish_progress_line()
                return []

            if not self.unique_use_enabled and avoid_duplicates:
                total_possible = 1
                for _, pool in non_empty:
                    total_possible *= len(pool)
                    if total_possible > 200000000:
                        break
                total_possible_estimate = int(total_possible)

                # C步：确定性枚举仅用于"组合空间与目标数量接近"的场景。
                # 当组合空间远大于导出数量时，枚举会让高位图层变化过慢，视觉上出现"某些素材被过度重复"。
                deterministic_space_ratio = float(total_possible) / float(max(1, count))
                deterministic_allowed = False
                if deterministic_allowed:
                    deterministic_enumeration_used = True
                    count = min(count, int(total_possible))
                    layer_indices = [idx for idx, _ in non_empty]
                    pools = [pool for _, pool in non_empty]
                    radices = [len(p) for p in pools]
                    start_seed = int(time.time_ns() & 0x7FFFFFFF)
                    step = 1
                    if total_possible > 1:
                        step = ((start_seed % max(1, total_possible - 1)) + 1)
                        while math.gcd(step, total_possible) != 1:
                            step += 1
                            if step >= total_possible:
                                step = 1
                                break

                    for out_index in range(count):
                        if cancel_callback and cancel_callback():
                            self._was_canceled = True
                            self._render_progress_line("预计算", len(combinations), count, progress_start, force=True)
                            self._finish_progress_line()
                            self._set_precompute_diagnostics({
                                "mode": "standard",
                                "dedup_strategy": dedup_strategy,
                                "requested_count": int(count),
                                "generated_count": int(len(combinations)),
                                "attempts": int(attempts),
                                "duplicate_attempts": int(duplicate_attempts),
                                "dedup_hits": dedup_hits,
                                "deterministic_enumeration_used": bool(deterministic_enumeration_used),
                                "dynamic_budget": self._build_dynamic_budget_summary(
                                    dynamic_budget_state,
                                    attempts=attempts,
                                    generated=len(combinations),
                                    duplicate_attempts=duplicate_attempts,
                                ),
                                "combination_space": {"total_possible_estimate": int(total_possible_estimate)},
                            })
                            return combinations

                        combo_index = (start_seed + out_index * step) % total_possible
                        rem = combo_index
                        layer_states = {}
                        for layer_pos, doc_layer_idx in enumerate(layer_indices):
                            base = radices[layer_pos]
                            sel = rem % base
                            rem //= base
                            layer_states[doc_layer_idx] = pools[layer_pos][sel]

                        combination_hash = self._generate_deterministic_hash(layer_states)
                        random_transforms, layer_parameters, layer_clone_settings = self._build_combination_runtime_metadata(
                            layer_states=layer_states,
                            combination_index=len(combinations),
                            category=None
                        )
                        combination = LayerCombination(
                            index=len(combinations),
                            layer_states=layer_states,
                            layer_clone_settings=layer_clone_settings,
                            combination_hash=combination_hash,
                            is_unique=True,
                            random_transforms=random_transforms,
                            layer_parameters=layer_parameters,
                        )
                        combinations.append(combination)
                        # 即使走确定性枚举，也持续记录全局使用计数，保证后续批次仍有"少用优先"约束
                        try:
                            global_avoid_manager.record_combination_usage(list(layer_states.values()))
                        except Exception:
                            logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                            pass
                        self._render_progress_line("预计算", len(combinations), count, progress_start)

                    self._render_progress_line("预计算", len(combinations), count, progress_start, force=True)
                    self._finish_progress_line()
                    self._save_persistent_folder_index_cache(force=True)
                    self._set_precompute_diagnostics({
                        "mode": "standard",
                        "dedup_strategy": dedup_strategy,
                        "requested_count": int(count),
                        "generated_count": int(len(combinations)),
                        "attempts": int(attempts),
                        "duplicate_attempts": int(duplicate_attempts),
                        "dedup_hits": dedup_hits,
                        "deterministic_enumeration_used": bool(deterministic_enumeration_used),
                        "deterministic_space_ratio": float(deterministic_space_ratio),
                        "dynamic_budget": self._build_dynamic_budget_summary(
                            dynamic_budget_state,
                            attempts=attempts,
                            generated=len(combinations),
                            duplicate_attempts=duplicate_attempts,
                        ),
                        "combination_space": {"total_possible_estimate": int(total_possible_estimate)},
                    })
                    return combinations
                else:
                    print(
                        f"[V2] 标准模式禁用确定性枚举(估算={int(total_possible)}，比值={deterministic_space_ratio:.2f})，"
                        f"使用均衡随机选图以降低连续重复感"
                    )
        except Exception:
            logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
            pass

        while len(combinations) < count and attempts < int(dynamic_budget_state["current_limit"]):
            if cancel_callback and cancel_callback():
                self._was_canceled = True
                self._render_progress_line("预计算", len(combinations), count, progress_start, force=True)
                self._finish_progress_line()
                self._set_precompute_diagnostics({
                    "mode": "standard",
                    "dedup_strategy": dedup_strategy,
                    "requested_count": int(count),
                    "generated_count": int(len(combinations)),
                    "attempts": int(attempts),
                    "duplicate_attempts": int(duplicate_attempts),
                    "dedup_hits": dedup_hits,
                    "deterministic_enumeration_used": bool(deterministic_enumeration_used),
                "deterministic_space_ratio": (
                    float(total_possible_estimate) / float(max(1, count))
                    if int(total_possible_estimate) > 0 else 0.0
                ),
                    "dynamic_budget": self._build_dynamic_budget_summary(
                        dynamic_budget_state,
                        attempts=attempts,
                        generated=len(combinations),
                        duplicate_attempts=duplicate_attempts,
                    ),
                    "combination_space": {"total_possible_estimate": int(total_possible_estimate)},
                })
                return combinations

            attempts += 1
            self._maybe_rebalance_dynamic_budget(
                dynamic_budget_state,
                attempts=attempts,
                generated=len(combinations),
                duplicate_attempts=duplicate_attempts,
            )
            
            layer_states = {}
            for doc_layer_idx, image_pool in optimized_pools.items():
                if image_pool:
                    selected_file = self._select_balanced_file_for_pool(
                        layer_idx=int(doc_layer_idx),
                        image_pool=image_pool,
                        global_avoid_manager=global_avoid_manager,
                        session_usage=layer_session_usage.setdefault(int(doc_layer_idx), {}),
                        recent_choices=layer_recent_choices.setdefault(int(doc_layer_idx), []),
                    )
                    if selected_file:
                        layer_states[doc_layer_idx] = selected_file

            # 图像唯一使用：对指定图层替换已使用的文件
            if self.unique_use_enabled and self.unique_use_layers:
                exhausted = False
                for doc_layer_idx in list(layer_states.keys()):
                    if doc_layer_idx in self.unique_use_layers and self._is_unique_use_eligible_layer(doc_layer_idx):
                        used = self._unique_used_map.setdefault(doc_layer_idx, set())
                        if layer_states[doc_layer_idx] in used:
                            pool = optimized_pools.get(doc_layer_idx, [])
                            candidates = [p for p in pool if p not in used]
                            if candidates:
                                layer_states[doc_layer_idx] = random.choice(candidates)
                            else:
                                exhausted = True
                                break
                if exhausted:
                    print(f"[V2] 唯一使用耗尽，停止生成（attempts={attempts}）")
                    break

            layer_states = self._enforce_no_consecutive_layer_reuse(
                layer_states=layer_states,
                optimized_pools=optimized_pools,
                global_avoid_manager=global_avoid_manager,
                layer_session_usage=layer_session_usage,
                layer_recent_choices=layer_recent_choices,
            )
            
            if not layer_states:
                print(f"[V2]  {attempts} ")
                continue
            
            # 生成确定性的组合哈希（包含图层索引与文件名）
            combination_hash = self._generate_deterministic_hash(layer_states)
            
            # 统一策略去重判断
            should_skip, _ = self._dedup_should_skip(
                dedup_state=dedup_state,
                combination_hash=combination_hash,
                layer_states=layer_states,
            )
            if should_skip:
                dedup_hits["hash"] += 1
                duplicate_attempts += 1
                self._maybe_rebalance_dynamic_budget(
                    dynamic_budget_state,
                    attempts=attempts,
                    generated=len(combinations),
                    duplicate_attempts=duplicate_attempts,
                )
                continue
            
            self._dedup_record(
                dedup_state=dedup_state,
                combination_hash=combination_hash,
                layer_states=layer_states,
            )

            # 
            random_transforms, layer_parameters, layer_clone_settings = self._build_combination_runtime_metadata(
                layer_states=layer_states,
                combination_index=len(combinations),
                category=None
            )
            combination = LayerCombination(
                index=len(combinations),
                layer_states=layer_states,
                layer_clone_settings=layer_clone_settings,  # 
                combination_hash=combination_hash,
                is_unique=True,
                random_transforms=random_transforms,
                layer_parameters=layer_parameters,
            )
            combinations.append(combination)
            
            # 记录到全局避重历史
            global_avoid_manager.record_combination_usage(list(layer_states.values()))
            # 会话内均衡计数：让后续组合自动避开"近期高频素材"
            for doc_layer_idx, selected_path in layer_states.items():
                layer_key = int(doc_layer_idx)
                usage_map = layer_session_usage.setdefault(layer_key, {})
                usage_map[selected_path] = usage_map.get(selected_path, 0) + 1
                recent_list = layer_recent_choices.setdefault(layer_key, [])
                recent_list.append(selected_path)
                if len(recent_list) > recent_window:
                    del recent_list[0]

            # 记录唯一使用消耗
            if self.unique_use_enabled and self.unique_use_layers:
                for doc_layer_idx, file_path in layer_states.items():
                    if doc_layer_idx in self.unique_use_layers and self._is_unique_use_eligible_layer(doc_layer_idx):
                        self._unique_used_map.setdefault(doc_layer_idx, set()).add(file_path)
            
            self._render_progress_line("预计算", len(combinations), count, progress_start)

        if len(combinations) < count:
            self._render_progress_line("预计算", len(combinations), count, progress_start, force=True)
            self._finish_progress_line()
            print(f"[V2]  {len(combinations)}  {count} ")
            print(f"[V2] : {attempts}/{int(dynamic_budget_state['current_limit'])}")
            print(f"[V2] ⚠  可用唯一组合不足，已按最大唯一组合返回")

        self._render_progress_line("预计算", len(combinations), count, progress_start, force=True)
        self._finish_progress_line()
        print(f"[V2] : {len(combinations)} ")
        self._set_precompute_diagnostics({
            "mode": "standard",
            "dedup_strategy": dedup_strategy,
            "requested_count": int(count),
            "generated_count": int(len(combinations)),
            "attempts": int(attempts),
            "duplicate_attempts": int(duplicate_attempts),
            "dedup_hits": dedup_hits,
            "deterministic_enumeration_used": bool(deterministic_enumeration_used),
            "deterministic_space_ratio": (
                float(total_possible_estimate) / float(max(1, count))
                if int(total_possible_estimate) > 0 else 0.0
            ),
            "dynamic_budget": self._build_dynamic_budget_summary(
                dynamic_budget_state,
                attempts=attempts,
                generated=len(combinations),
                duplicate_attempts=duplicate_attempts,
            ),
            "combination_space": {
                "total_possible_estimate": int(total_possible_estimate),
                "unique_hash_count": int(len(dedup_state.get("hashes", set()))),
            },
        })
        self._save_persistent_folder_index_cache(force=True)
        return combinations

