# -*- coding: utf-8 -*-
"""BatchExportPrecomputerV2 - 批量导出预计算核心（从 batch_export_precomputer.py 拆分）"""

import logging

logger = logging.getLogger(__name__)
import os
import sys
import re
import hashlib
import time
import json
import math
from typing import List, Dict, Tuple, Any, Optional, Callable
from dataclasses import dataclass
from concurrent.futures import ThreadPoolExecutor, as_completed
from app.utils.print_utils import safe_print as _safe_print

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print

# P2 收敛：原 v1 的共享数据模型已下沉到 app.utils.batch_export_plan_models，
# 从本超大文件抽离，便于复用与单测（本文件仅保留工厂与 BatchExportPrecomputerV2 类）。
from app.utils.batch_export_plan_models import (
    LayerCombination,
    ExportTask,
    PrecomputedExportPlan,
)
from app.utils.batch_export_dedup_budget import BatchExportDedupBudgetMixin
from app.utils.batch_export_constraints import BatchExportConstraintMixin
from app.utils.batch_export_folder_cache import BatchExportFolderCacheMixin
from app.utils.batch_export_combination_metadata import BatchExportCombinationMetadataMixin
from app.utils.batch_export_generation import BatchExportGenerationMixin
from app.utils.batch_export_hashing import generate_deterministic_hash


def get_batch_precomputer_v2(document, document_analysis: dict) -> 'BatchExportPrecomputerV2':
    """V2 工厂：构造批量导出预计算机（原 v1 的兼容入口，现已下沉到本模块）。"""
    return BatchExportPrecomputerV2(document, document_analysis)


from app.utils.text_layer_virtual_path import build_text_layer_virtual_path


class BatchExportPrecomputerV2(BatchExportDedupBudgetMixin, BatchExportConstraintMixin,
                           BatchExportFolderCacheMixin, BatchExportCombinationMetadataMixin,
                           BatchExportGenerationMixin):
    """ V2 - """

    def __init__(self, document, document_analysis: dict):
        self.document = document
        self.document_analysis = document_analysis

        # 安全地获取配置，提供默认值
        self.binding_enabled = document_analysis.get('binding_enabled', False)
        self.binding_categories = document_analysis.get('binding_categories', [])
        self.layer_analysis = document_analysis.get('layer_analysis', {})
        self.export_mode = document_analysis.get('export_mode', 'standard')

        # 安全地获取图层分析，提供默认值
        self.visible_layers = self.layer_analysis.get('visible_layers', [])
        self.bound_layers = self.layer_analysis.get('bound_layers', [])
        self.unbound_layers = self.layer_analysis.get('unbound_layers', [])
        self.visible_layer_doc_indices = self._build_visible_layer_doc_indices()

        # 
        self.layer_image_pools = {}
        self.binding_combinations = {}
        self.non_binding_layer_selectors = {}
        # 图像唯一使用设置
        try:
            self.unique_use_enabled = bool(getattr(self.document, 'export_settings', {}).get('unique_use_enabled', False))
            self.unique_use_layers = list(getattr(self.document, 'export_settings', {}).get('unique_use_layers', []))
        except Exception:
            self.unique_use_enabled = False
            self.unique_use_layers = []
        self.unique_use_layers = self._normalize_unique_use_layers(self.unique_use_layers)
        self._unique_used_map = {}
        self._precompute_total_possible = None
        self._precompute_progress_last_time = 0.0
        self._was_canceled = False
        self._supported_image_ext = ('.png', '.jpg', '.jpeg', '.bmp', '.gif', '.tif', '.tiff', '.webp')
        self._folder_index_cache = {}  # key: abs_dir -> {'mtime_ns': int, 'files': List[str]}
        self._folder_index_cache_dirty = False
        self._folder_index_last_save_time = 0.0
        self._persistent_folder_index_path = self._get_persistent_folder_index_path()
        self._load_persistent_folder_index_cache()
        self._verbose_template_logs = os.environ.get("BTPW_VERBOSE_TEMPLATE_LOGS", "0") == "1"
        self._last_precompute_diagnostics: Dict[str, Any] = {}

        print(f"[V2] :")
        print(f"  - : {self.export_mode}")
        print(f"  - : {self.binding_enabled}")
        print(f"  - : {len(self.visible_layers)}")
        print(f"  - : {len(self.bound_layers)}")
        print(f"  - : {len(self.unbound_layers)}")

    def _get_avoid_repeat_manager(self):
        """获取当前文档专属的避重管理器，与旧版预计算器保持一致。"""
        from app.utils.global_avoid_repeat_manager import GlobalAvoidRepeatManager
        doc_path = str(getattr(self.document, "file_path", "") or "")
        if doc_path:
            scope_key = os.path.abspath(doc_path)
        else:
            scope_key = f"unsaved_{id(self.document)}"
        return GlobalAvoidRepeatManager(scope_key=scope_key)

    def _build_visible_layer_doc_indices(self) -> List[int]:
        """建立 visible_layers -> document.layers 的稳定索引映射。"""
        try:
            if not hasattr(self.document, 'layers'):
                return list(range(len(self.visible_layers)))
            indices = [idx for idx, layer in enumerate(self.document.layers) if bool(getattr(layer, 'visible', False))]
            if len(indices) == len(self.visible_layers):
                return indices
            # 回退：长度不一致时保持可用，不中断导出流程
            return list(range(len(self.visible_layers)))
        except Exception:
            return list(range(len(self.visible_layers)))

    def _to_doc_layer_idx(self, visible_idx: int) -> int:
        """把可见层序号转换为 document.layers 的真实索引。"""
        try:
            idx = int(visible_idx)
        except Exception:
            return int(visible_idx)
        if 0 <= idx < len(self.visible_layer_doc_indices):
            return int(self.visible_layer_doc_indices[idx])
        return idx

    def _resolve_layer_by_state_index(self, state_layer_idx: int):
        """
        解析组合里的图层索引到真实图层对象。
        兼容两种语义：
        - document.layers 的真实索引（新逻辑）
        - visible_layers 的相对索引（历史逻辑）
        在存在隐藏层时优先避免把"可见层索引"误当成文档索引。
        """
        try:
            idx = int(state_layer_idx)
        except Exception:
            idx = state_layer_idx
        if not isinstance(idx, int):
            return None

        doc_layers = getattr(self.document, 'layers', []) if hasattr(self.document, 'layers') else []
        visible_count = len(self.visible_layers)
        visible_doc_indices = list(self.visible_layer_doc_indices or [])
        visible_doc_set = set([int(v) for v in visible_doc_indices if isinstance(v, int)])
        has_hidden_layers = bool(doc_layers) and (len(doc_layers) != visible_count)

        # 1) 当存在隐藏层且 idx 明显不是可见文档索引时，按"可见层索引"解析
        if has_hidden_layers and 0 <= idx < visible_count and idx not in visible_doc_set:
            try:
                mapped_doc_idx = self._to_doc_layer_idx(idx)
                if 0 <= mapped_doc_idx < len(doc_layers):
                    return doc_layers[mapped_doc_idx]
            except Exception:
                logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                pass

        # 2) 按"文档真实索引"解析（新逻辑主路径）
        try:
            if 0 <= idx < len(doc_layers):
                # 存在隐藏层时，仅接受可见图层索引，避免命中隐藏层
                if (not has_hidden_layers) or (idx in visible_doc_set):
                    return doc_layers[idx]
        except Exception:
            logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
            pass

        # 3) 兼容回退：按可见层索引解析
        try:
            if 0 <= idx < visible_count:
                mapped_doc_idx = self._to_doc_layer_idx(idx)
                if 0 <= mapped_doc_idx < len(doc_layers):
                    return doc_layers[mapped_doc_idx]
                return self.visible_layers[idx]
        except Exception:
            logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
            pass

        return None

    def _capture_clone_settings(self, layer) -> Dict[str, Any]:
        """采集分身参数，兼容新旧图层字段。"""
        clone_settings: Dict[str, Any] = {}

        if hasattr(layer, 'clone_enabled'):
            clone_settings['clone_enabled'] = bool(getattr(layer, 'clone_enabled', False))
        elif hasattr(layer, '_clone_enabled'):
            clone_settings['clone_enabled'] = bool(getattr(layer, '_clone_enabled', False))
        else:
            clone_settings['clone_enabled'] = False

        if hasattr(layer, 'clone_rows'):
            clone_settings['clone_rows'] = int(getattr(layer, 'clone_rows', 1) or 1)
        elif hasattr(layer, '_clone_rows'):
            clone_settings['clone_rows'] = int(getattr(layer, '_clone_rows', 1) or 1)
        else:
            clone_settings['clone_rows'] = 1

        if hasattr(layer, 'clone_columns'):
            clone_settings['clone_columns'] = int(getattr(layer, 'clone_columns', 1) or 1)
        elif hasattr(layer, '_clone_columns'):
            clone_settings['clone_columns'] = int(getattr(layer, '_clone_columns', 1) or 1)
        else:
            clone_settings['clone_columns'] = 1

        if hasattr(layer, 'clone_row_spacing'):
            clone_settings['clone_row_spacing'] = int(getattr(layer, 'clone_row_spacing', 0) or 0)
        elif hasattr(layer, '_clone_row_spacing'):
            clone_settings['clone_row_spacing'] = int(getattr(layer, '_clone_row_spacing', 0) or 0)
        else:
            clone_settings['clone_row_spacing'] = 0

        if hasattr(layer, 'clone_column_spacing'):
            clone_settings['clone_column_spacing'] = int(getattr(layer, 'clone_column_spacing', 0) or 0)
        elif hasattr(layer, '_clone_column_spacing'):
            clone_settings['clone_column_spacing'] = int(getattr(layer, '_clone_column_spacing', 0) or 0)
        else:
            clone_settings['clone_column_spacing'] = 0

        return clone_settings



    def analyze_document_with_context(self, cancel_callback: Optional[Callable[[], bool]] = None) -> int:
        """"""
        print(f"[V2] : {self.export_mode}")
        if cancel_callback and cancel_callback():
            self._was_canceled = True
            self._precompute_total_possible = 0
            return 0

        if self.export_mode == 'binding':
            total = self._analyze_binding_mode(cancel_callback=cancel_callback)
        else:
            total = self._analyze_standard_mode(cancel_callback=cancel_callback)

        self._precompute_total_possible = total
        return total

    def _render_progress_line(self, label: str, current: int, total: int, start_time: float, force: bool = False):
        if total <= 0:
            return
        now = time.time()
        if not force and current != total and (now - self._precompute_progress_last_time) < 0.05:
            return
        self._precompute_progress_last_time = now
        ratio = min(max(current / total, 0.0), 1.0)
        bar_len = 28
        filled = int(bar_len * ratio)
        bar = "█" * filled + " " * (bar_len - filled)
        elapsed = max(0.0, now - start_time)
        sys.stdout.write(f"\r[{label}] |{bar}| {current}/{total} ({ratio*100:5.1f}%) 用时{elapsed:6.1f}s")
        sys.stdout.flush()

    def _finish_progress_line(self):
        sys.stdout.write("\n")
        sys.stdout.flush()

    def _analyze_binding_mode(self, cancel_callback: Optional[Callable[[], bool]] = None) -> int:
        """🔧 彻底修复：不再预计算固定组合，每次都动态获取"""
        print("[V2] 分析绑定模式...")
        if cancel_callback and cancel_callback():
            self._was_canceled = True
            return 0

        # 初始化图层图片池
        self._initialize_layer_image_pools(cancel_callback=cancel_callback)
        if self._was_canceled:
            return 0

        # 🔧 关键修复：不再预计算固定组合！
        # 旧代码会为每个分类预计算一个固定组合，导致严重重复
        # 新代码：只验证分类可用性，不存储固定组合
        self.binding_combinations = {}  # 保留空字典以兼容性，但不使用
        binding_manager = self.document.binding_manager

        print(f"[V2] 🔧 检测到 {len(self.binding_categories)} 个绑定分类")
        
        # 验证每个分类是否可用
        valid_categories = []
        for category in self.binding_categories:
            if cancel_callback and cancel_callback():
                self._was_canceled = True
                return total_combinations if 'total_combinations' in locals() else 0
            category_valid = False
            for group_id, group in binding_manager.binding_groups.items():
                if cancel_callback and cancel_callback():
                    self._was_canceled = True
                    return total_combinations if 'total_combinations' in locals() else 0
                if category in group.file_categories:
                    category_valid = True
                    print(f"[V2] ✅ 分类 '{category}' 在绑定组 '{group.name}' 中可用")
                    break
            
            if category_valid:
                valid_categories.append(category)
            else:
                print(f"[V2] ⚠️ 分类 '{category}' 不可用，将跳过")
        
        # 更新有效分类列表
        self.binding_categories = valid_categories
        
        # 初始化非绑定图层选择器
        self._initialize_non_binding_layer_selectors_v2(cancel_callback=cancel_callback)
        if self._was_canceled:
            return 0

        # 计算理论组合数（每个分类对应的组合数总和）
        # 绑定模式下：同一分类需要同时满足多个绑定组，同时还需考虑非绑定图层池
        total_combinations = 0
        for category in self.binding_categories:
            if cancel_callback and cancel_callback():
                self._was_canceled = True
                return total_combinations
            per_category_combinations = 1
            has_any_group = False

            # 绑定组组合数：按组相乘
            for group_id, group in binding_manager.binding_groups.items():
                if cancel_callback and cancel_callback():
                    self._was_canceled = True
                    return total_combinations
                if category in group.file_categories:
                    has_any_group = True
                    layer_counts = []
                    for layer_idx in group.file_categories[category].keys():
                        layer_counts.append(len(group.file_categories[category][layer_idx]))

                    if layer_counts:
                        group_combinations = 1
                        for count in layer_counts:
                            group_combinations *= count
                        per_category_combinations *= group_combinations

            # 非绑定图层组合数：按图层池相乘（不受绑定分类限制）
            for doc_layer_idx, selector in self.non_binding_layer_selectors.items():
                if cancel_callback and cancel_callback():
                    self._was_canceled = True
                    return total_combinations
                pool = getattr(selector, 'image_pool', []) if selector else []
                if not pool:
                    continue
                pool_size = len(pool)
                if pool_size > 0:
                    per_category_combinations *= pool_size

            if has_any_group and per_category_combinations > 0:
                total_combinations += per_category_combinations
                print(f"[V2] 分类 '{category}' 理论组合数: {per_category_combinations}")
        
        print(f"[V2] 总理论组合数: {total_combinations}")
        print(f"[V2] 🎯 关键改进：每次导出时动态获取组合，确保不重复！")
        return total_combinations

    def _analyze_standard_mode(self, cancel_callback: Optional[Callable[[], bool]] = None) -> int:
        """"""
        print("[V2] ...")
        if cancel_callback and cancel_callback():
            self._was_canceled = True
            return 0

        # 
        self._initialize_layer_image_pools(cancel_callback=cancel_callback)
        if self._was_canceled:
            return 0

        # 
        total_combinations = 1
        from app.utils.layer_tree import is_layer_group, is_effectively_visible
        for doc_layer_idx, layer in enumerate(self.document.layers):
            if cancel_callback and cancel_callback():
                self._was_canceled = True
                return 0
            if (not is_layer_group(layer)) and is_effectively_visible(layer, self.document.layers):
                layer_pool_size = len(self.layer_image_pools.get(doc_layer_idx, []))
                if layer_pool_size > 0:
                    total_combinations *= layer_pool_size

        print(f"[V2] : {total_combinations}")
        return total_combinations

    def _initialize_layer_image_pools(self, cancel_callback: Optional[Callable[[], bool]] = None):
        """"""
        print("[V2] ...")

        #  
        from app.utils.layer_tree import is_layer_group, is_effectively_visible
        for doc_layer_idx, layer in enumerate(self.document.layers):
            if cancel_callback and cancel_callback():
                self._was_canceled = True
                return
            if is_layer_group(layer) or not is_effectively_visible(layer, self.document.layers):
                continue
                
            image_pool = []
            text_candidates = []

            if hasattr(layer, 'get_text_lines') or hasattr(layer, 'text_content'):
                text_candidates = self._get_text_layer_export_candidates(layer)
                if text_candidates:
                    image_pool = [self._build_text_virtual_path(layer.name, text) for text in text_candidates]
            elif hasattr(layer, 'image_source') and layer.image_source:
                if getattr(layer, 'is_folder', False):
                    # 
                    try:
                        image_pool = self._get_folder_images_cached(layer.image_source, cancel_callback=cancel_callback)
                    except Exception as e:
                        print(f"[V2]  {doc_layer_idx} '{layer.name}' : {e}")
                else:
                    # 
                    if os.path.exists(layer.image_source):
                        image_pool = [layer.image_source]

            self.layer_image_pools[doc_layer_idx] = image_pool
            print(f"[V2]  {doc_layer_idx} '{layer.name}': {len(image_pool)} ")

    def _build_text_virtual_path(self, layer_name: str, text_value: Any) -> str:
        """构建编码后的文字图层虚拟路径，避免特殊字符导致解析截断。"""
        return build_text_layer_virtual_path(layer_name, text_value)

    def _get_text_layer_export_candidates(self, layer) -> List[str]:
        """提取用于导出的文字候选，兼容绑定/非绑定两种模式。"""
        try:
            if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)):
                raw_lines = layer.get_text_lines() or []
                candidates = [str(line) for line in raw_lines if line is not None and str(line).strip()]
                if candidates:
                    return candidates
        except Exception:
            logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
            pass

        current_text = getattr(layer, 'current_text', '')
        if current_text is not None and str(current_text).strip():
            return [str(current_text)]

        text_content = getattr(layer, 'text_content', '')
        if text_content is None or not str(text_content).strip():
            return []

        content_str = str(text_content)
        if bool(getattr(layer, 'text_binding_enabled', False)):
            lines = [line.strip() for line in content_str.splitlines() if line.strip()]
            if lines:
                return lines
        return [content_str]

    def _initialize_non_binding_layer_selectors_v2(self, cancel_callback: Optional[Callable[[], bool]] = None):
        """V2"""
        print("[V2] ...")

        self.non_binding_layer_selectors = {}

        #  
        for doc_layer_idx, layer in enumerate(self.document.layers):
            if cancel_callback and cancel_callback():
                self._was_canceled = True
                return
            if not layer.visible:
                continue
                
            if layer not in self.bound_layers:
                # 
                image_pool = self.layer_image_pools.get(doc_layer_idx, [])
                if image_pool:
                    from app.utils.smart_layer_selector import SmartLayerSelector
                    selector = SmartLayerSelector(image_pool, layer.name)
                    self.non_binding_layer_selectors[doc_layer_idx] = selector
                    print(f"[V2]  {doc_layer_idx} '{layer.name}' ")

    def _is_text_layer(self, layer) -> bool:
        """判断是否为文字图层，避免把文案候选误当作图片唯一使用资源。"""
        try:
            if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)):
                return True
            class_name = layer.__class__.__name__ if layer is not None else ""
            if class_name == "TextLayer":
                return True
            return bool(hasattr(layer, 'text_content') and not hasattr(layer, 'image_source'))
        except Exception:
            return False

    def _is_unique_use_eligible_layer(self, doc_layer_idx: int) -> bool:
        """图像唯一使用只适用于真实图片图层，不适用于文字图层的虚拟文案路径。"""
        try:
            idx = int(doc_layer_idx)
            if not hasattr(self.document, 'layers') or idx < 0 or idx >= len(self.document.layers):
                return False
            layer = self.document.layers[idx]
            if self._is_text_layer(layer):
                return False
            pool = self.layer_image_pools.get(idx, [])
            if not pool:
                return False
            return any(isinstance(path, str) and os.path.isfile(path) for path in pool)
        except Exception:
            return False

    def _normalize_unique_use_layers(self, unique_layers: List[int]) -> List[int]:
        """清洗旧设置/索引漂移造成的无效唯一使用图层。"""
        normalized = []
        for idx in unique_layers or []:
            try:
                int_idx = int(idx)
            except Exception:
                logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                continue
            if int_idx in normalized:
                continue
            if not hasattr(self.document, 'layers') or int_idx < 0 or int_idx >= len(self.document.layers):
                continue
            layer = self.document.layers[int_idx]
            if self._is_text_layer(layer):
                try:
                    print(f"[V2] 忽略文字图层的图像唯一使用设置: {int_idx} '{getattr(layer, 'name', '')}'")
                except Exception:
                    logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                    pass
                continue
            normalized.append(int_idx)
        return normalized

    # =========================
    # 迭代2：职责拆分（同文件内）

    def _empty_plan(self) -> 'PrecomputedExportPlan':
        return PrecomputedExportPlan(
            tasks=[],
            total_count=0,
            unique_combinations=0,
            estimated_time=0.0,
            memory_requirement_mb=0.0,
            optimization_suggestions=[f"{self.export_mode}", "0", ""]
        )

    def _plan_combinations(
        self,
        target_count: int,
        avoid_duplicates: bool,
        traverse_mode: bool,
        cancel_callback: Optional[Callable[[], bool]],
        precompute_start: float,
    ) -> List['LayerCombination']:
        """组合规划阶段：按模式生成组合。"""
        if traverse_mode:
            return self._generate_exhaustive_combinations_v2(
                target_count, avoid_duplicates, cancel_callback=cancel_callback, progress_start=precompute_start
            )
        if self.export_mode == 'binding':
            return self._generate_binding_combinations_v2(
                target_count, avoid_duplicates, cancel_callback=cancel_callback, progress_start=precompute_start
            )
        return self._generate_standard_combinations_v2(
            target_count, avoid_duplicates, cancel_callback=cancel_callback, progress_start=precompute_start
        )

    def _build_export_tasks(
        self,
        combinations: List['LayerCombination'],
        directory: str,
        filename_template: str,
        file_format: str,
        start_index: int,
        cancel_callback: Optional[Callable[[], bool]],
    ) -> List[ExportTask]:
        """任务构建阶段：按配置并行/串行生成 ExportTask。"""
        tasks: List[ExportTask] = []
        combination_count = len(combinations)
        cpu_count = os.cpu_count() or 4
        # 自动线程策略：小任务保守，大任务提高并行度
        if combination_count < 128:
            filename_workers = min(4, cpu_count)
        elif combination_count < 800:
            filename_workers = min(max(4, cpu_count), 8)
        else:
            filename_workers = min(max(6, cpu_count), 12)
        filename_workers = max(1, min(16, filename_workers))

        if combination_count >= 64 and filename_workers > 1 and not (cancel_callback and cancel_callback()):
            built_tasks: List[Optional[ExportTask]] = [None] * combination_count
            with ThreadPoolExecutor(max_workers=filename_workers) as executor:
                future_to_index = {
                    executor.submit(
                        self._build_export_task,
                        directory,
                        filename_template,
                        file_format,
                        start_index,
                        combination,
                        i
                    ): i
                    for i, combination in enumerate(combinations)
                }
                for future in as_completed(future_to_index):
                    if cancel_callback and cancel_callback():
                        self._was_canceled = True
                        break
                    idx = future_to_index[future]
                    try:
                        built_tasks[idx] = future.result()
                    except Exception as e:
                        print(f"[V2] 任务构建失败，回退默认命名: {e}")
                        fallback_number = start_index + idx
                        fallback_name = f"batch_{fallback_number:04d}.{file_format}"
                        built_tasks[idx] = ExportTask(
                            combination=combinations[idx],
                            filename=fallback_name,
                            file_path=os.path.join(directory, fallback_name),
                            file_number=fallback_number
                        )
            if not self._was_canceled:
                tasks = [t for t in built_tasks if t is not None]
            return self._ensure_unique_task_paths(tasks, directory, file_format)

        for i, combination in enumerate(combinations):
            if cancel_callback and cancel_callback():
                self._was_canceled = True
                break
            tasks.append(
                self._build_export_task(
                    directory,
                    filename_template,
                    file_format,
                    start_index,
                    combination,
                    i
                )
            )
        return self._ensure_unique_task_paths(tasks, directory, file_format)

    def _ensure_unique_task_paths(self, tasks: List[ExportTask], directory: str, file_format: str) -> List[ExportTask]:
        """避免模板冲突导致后续图片覆盖前面的导出结果。"""
        seen = set()
        extension = f".{file_format.lower().lstrip('.')}"
        for task in tasks:
            original_name = str(getattr(task, 'filename', '') or f"batch_{task.file_number:04d}{extension}")
            root, ext = os.path.splitext(original_name)
            if not ext:
                ext = extension
            candidate = original_name
            collision_index = 2
            while candidate.lower() in seen:
                candidate = f"{root}-{task.file_number:04d}-{collision_index}{ext}"
                collision_index += 1
            if candidate != original_name:
                task.filename = candidate
                task.file_path = os.path.join(directory, candidate)
            seen.add(candidate.lower())
        return tasks




    def create_export_plan(self, directory: str, count: int, filename_template: str,
                          file_format: str, start_index: int, avoid_duplicates: bool = True,
                          traverse_mode: bool = False, cancel_callback: Optional[Callable[[], bool]] = None) -> 'PrecomputedExportPlan':
        """"""
        print(f"[V2] : {count} ")
        ctx = self._build_constraint_context(count, avoid_duplicates)
        self._apply_unique_use_constraints(ctx)
        self._apply_total_possible_constraints(ctx)

        if cancel_callback and cancel_callback():
            self._was_canceled = True
            return self._empty_plan()

        precompute_start = time.time()
        self._precompute_progress_last_time = 0.0

        combinations = self._plan_combinations(
            target_count=ctx["target_count"],
            avoid_duplicates=ctx["avoid_duplicates"],
            traverse_mode=traverse_mode,
            cancel_callback=cancel_callback,
            precompute_start=precompute_start,
        )

        if (
            len(combinations) < ctx["target_count"]
            and ctx["avoid_duplicates"]
            and not traverse_mode
            and not (self.unique_use_enabled and self.unique_use_layers)
            and not (cancel_callback and cancel_callback())
        ):
            shortage = int(ctx["target_count"] - len(combinations))
            print(
                f"[V2] 去重组合不足，剩余 {shortage} 张未补足，"
                f"避免重复已启用，不使用重复组合补齐"
            )
            ctx["adjustment_reasons"].append(
                f"去重组合不足：避免重复已启用，未使用重复组合补足剩余 {shortage} 张"
            )

        tasks = self._build_export_tasks(
            combinations=combinations,
            directory=directory,
            filename_template=filename_template,
            file_format=file_format,
            start_index=start_index,
            cancel_callback=cancel_callback,
        )

        if self._was_canceled:
            return self._empty_plan()

        if len(combinations) < ctx["target_count"]:
            ctx["adjustment_reasons"].append(
                f"生成组合不足：仅生成 {len(combinations)} / 请求 {ctx['target_count']}"
            )

        # 
        plan = PrecomputedExportPlan(
            tasks=tasks,
            total_count=len(tasks),
            unique_combinations=len(combinations),
            estimated_time=len(tasks) * 0.5,  # 0.5
            memory_requirement_mb=len(tasks) * 10,  # 10MB
            optimization_suggestions=[
                f"{self.export_mode}",
                f"{len(combinations)}",
                ""
            ]
        )

        # 附加导出调整信息，供 UI 提示
        plan.adjustment_info = {
            'requested': ctx["requested_count"],
            'planned': len(combinations),
            'reasons': ctx["adjustment_reasons"]
        }
        base_diag = dict(getattr(self, "_last_precompute_diagnostics", {}) or {})
        base_diag.update({
            "requested_count": int(ctx["requested_count"]),
            "target_count": int(ctx["target_count"]),
            "planned_count": int(len(combinations)),
            "adjustment_reasons": list(ctx["adjustment_reasons"]),
        })
        base_diag["shortage_analysis"] = self._build_shortage_analysis(
            diagnostics=base_diag,
            target_count=int(ctx["target_count"]),
            planned_count=int(len(combinations)),
        )
        plan.precompute_diagnostics = base_diag

        print(f"[V2] : {len(tasks)} ")
        self._save_persistent_folder_index_cache(force=True)
        return plan

    def _build_export_task(self, directory: str, filename_template: str, file_format: str,
                           start_index: int, combination: 'LayerCombination', index: int) -> ExportTask:
        """构建单个导出任务（用于串行/并行共用）"""
        file_number = start_index + index
        filename = self._process_filename_template(
            filename_template,
            file_number,
            combination,
            index
        )
        if not filename.endswith(f'.{file_format}'):
            filename += f'.{file_format}'
        file_path = os.path.join(directory, filename)
        return ExportTask(
            combination=combination,
            filename=filename,
            file_path=file_path,
            file_number=file_number
        )

    def _process_filename_template(self, template: str, file_number: int, combination: 'LayerCombination', combination_index: int) -> str:
        """
        

        Args:
            template: 
            file_number: 
            combination: 
            combination_index: 

        Returns:
            
        """
        #  
        from app.utils.filename_template_processor import FilenameTemplateProcessor
        
        try:
            # 
            context = FilenameTemplateProcessor.create_context(
                number=file_number,
                index=file_number,
                count=len(combination.layer_states),
                layer_states=combination.layer_states,
                combination_hash=getattr(combination, 'combination_hash', ''),
                binding_info=getattr(combination, 'binding_info', '')
            )
            
            #  
            context['document'] = self.document
            context['current_combination'] = combination
            
            result = FilenameTemplateProcessor.process_template(template, context)
            if self._verbose_template_logs:
                print(f"[V2] : '{template}' -> '{result}'")
            return result
            
        except Exception as e:
            print(f"[V2] : {e}")
            # 
            return f"batch_{file_number:04d}"
            processed_template = processed_template.replace("{index}", str(file_number))
            processed_template = processed_template.replace("{count}", str(len(combination.layer_states)))

            # 
            if "{layer}" in processed_template or "{layers}" in processed_template:
                # 
                first_layer_name = ""
                layer_names = []

                for layer_idx, file_path in combination.layer_states.items():
                    if file_path and os.path.isfile(file_path):
                        try:
                            basename = os.path.basename(file_path)
                            if isinstance(basename, bytes):
                                basename = basename.decode('utf-8', 'ignore')
                            filename = os.path.splitext(basename)[0]
                            # 
                            clean_name = self._extract_main_filename(filename)
                            if clean_name:
                                if not first_layer_name:
                                    first_layer_name = clean_name
                                if clean_name not in layer_names:
                                    layer_names.append(clean_name)
                        except Exception as e:
                            print(f"[] : {e}")
                            continue

                #  {layer} 
                if "{layer}" in processed_template:
                    layer_name = first_layer_name if first_layer_name else "layer"
                    layer_name = self._clean_filename(layer_name)
                    processed_template = processed_template.replace("{layer}", layer_name)

                #  {layers} 
                if "{layers}" in processed_template:
                    combined_name = "-".join(layer_names[:3]) if layer_names else "layers"  # 3
                    combined_name = self._clean_filename(combined_name)
                    processed_template = processed_template.replace("{layers}", combined_name)

            #  {layer:index}
            layer_pattern = r'\{layer:(\d+)\}'
            def replace_layer_by_index(match):
                layer_index = int(match.group(1))
                if layer_index in combination.layer_states:
                    file_path = combination.layer_states[layer_index]
                    if file_path and os.path.isfile(file_path):
                        try:
                            basename = os.path.basename(file_path)
                            if isinstance(basename, bytes):
                                basename = basename.decode('utf-8', 'ignore')
                            filename = os.path.splitext(basename)[0]
                            clean_name = self._extract_main_filename(filename)
                            return self._clean_filename(clean_name) if clean_name else f"layer{layer_index}"
                        except Exception as e:
                            print(f"[] : {e}")
                            return f"layer{layer_index}"
                    else:
                        return f"layer{layer_index}"
                else:
                    return "layer"

            processed_template = re.sub(layer_pattern, replace_layer_by_index, processed_template)

            # hash
            if "{combo}" in processed_template:
                combo_str = "_".join(os.path.splitext(os.path.basename(path))[0]
                                   for path in combination.layer_states.values() if isinstance(path, str))
                combo_hash = hashlib.md5(combo_str.encode()).hexdigest()[:8]
                processed_template = processed_template.replace("{combo}", combo_hash)

            # 
            processed_template = self._clean_filename(processed_template)

            # 
            if not processed_template:
                processed_template = f"export_{file_number}"

            return processed_template

        except Exception as e:
            print(f"[] : {e}")
            # 
            return f"export_{file_number}"

    def _select_balanced_file_for_pool(
        self,
        layer_idx: int,
        image_pool: List[str],
        global_avoid_manager,
        session_usage: Dict[str, int],
        recent_choices: List[str],
        disallow_paths: Optional[set] = None,
    ) -> Optional[str]:
        """从全量池选择更均衡的文件，避免单图层在短时间内高频重复。"""
        if not image_pool:
            return None
        try:
            import random
            disallow = set(disallow_paths or set())
            candidate_pool = [p for p in image_pool if p not in disallow]
            if not candidate_pool:
                candidate_pool = list(image_pool)
            # 大池性能优化：仅评估采样子集，避免每次全池打分导致预计算过慢
            if len(candidate_pool) > 160:
                sampled = random.sample(candidate_pool, 160)
                # 保留少量"本批次最少使用"候选，确保均衡效果不丢
                usage_pairs = sorted(
                    [(p, int(session_usage.get(p, 0))) for p in candidate_pool],
                    key=lambda x: (x[1], str(x[0]))
                )
                low_usage_keep = [p for p, _ in usage_pairs[:24]]
                merged = list(dict.fromkeys(sampled + low_usage_keep))
                candidate_pool = merged
            # 均匀分布硬约束：尽量把每张图使用次数压在"平均值+缓冲"以内
            total_selected = int(sum([int(v) for v in (session_usage or {}).values()]) or 0)
            expected_avg = float(total_selected + 1) / float(max(1, len(candidate_pool)))
            max_allowed_usage = int(math.ceil(expected_avg)) + 1
            balanced_pool = [p for p in candidate_pool if int(session_usage.get(p, 0)) <= max_allowed_usage]
            if balanced_pool:
                candidate_pool = balanced_pool
            scored: List[tuple] = []
            min_score = None
            recent_tail = list(recent_choices[-6:]) if recent_choices else []
            recent_set = set(recent_tail)
            last_path = recent_tail[-1] if recent_tail else None
            for path in candidate_pool:
                global_count = 0
                try:
                    global_count = int(global_avoid_manager.get_image_usage_count(path))
                except Exception:
                    global_count = 0
                local_count = int(session_usage.get(path, 0))
                recent_penalty = 3 if path in recent_set else 0
                streak_len = 0
                for prev in reversed(recent_tail):
                    if prev == path:
                        streak_len += 1
                    else:
                        break
                streak_penalty = streak_len * 20
                adjacent_penalty = 25 if (last_path is not None and path == last_path) else 0
                # 本次导出内计数权重更高，保证当前批次观感均匀；全局历史作为次级约束
                score = (
                    (local_count * 3)
                    + (global_count * 1)
                    + recent_penalty
                    + streak_penalty
                    + adjacent_penalty
                )
                scored.append((path, score))
                if min_score is None or score < min_score:
                    min_score = score
            if min_score is None:
                return random.choice(candidate_pool)
            candidates = [p for p, s in scored if s == min_score]
            if not candidates:
                return random.choice(candidate_pool)
            # 候选过多时采样，降低极大池排序/随机成本
            if len(candidates) > 16:
                candidates = random.sample(candidates, 16)
            return random.choice(candidates)
        except Exception:
            try:
                import random
                return random.choice(image_pool)
            except Exception:
                return image_pool[0] if image_pool else None

    def _enforce_no_consecutive_layer_reuse(
        self,
        layer_states: Dict[int, str],
        optimized_pools: Dict[int, List[str]],
        global_avoid_manager,
        layer_session_usage: Dict[int, Dict[str, int]],
        layer_recent_choices: Dict[int, List[str]],
    ) -> Dict[int, str]:
        """尽量避免同一图层连续使用同一素材（有可替代素材时强制替换）。"""
        adjusted = dict(layer_states or {})
        try:
            for doc_layer_idx, selected_path in list(adjusted.items()):
                layer_key = int(doc_layer_idx)
                pool = list(optimized_pools.get(layer_key, []) or [])
                if len(pool) <= 1:
                    continue
                recent = layer_recent_choices.setdefault(layer_key, [])
                if not recent:
                    continue
                last_path = recent[-1]
                if str(selected_path or "") != str(last_path or ""):
                    continue
                replacement = self._select_balanced_file_for_pool(
                    layer_idx=layer_key,
                    image_pool=pool,
                    global_avoid_manager=global_avoid_manager,
                    session_usage=layer_session_usage.setdefault(layer_key, {}),
                    recent_choices=recent,
                    disallow_paths={selected_path},
                )
                if replacement and str(replacement) != str(selected_path):
                    adjusted[layer_key] = replacement
            return adjusted
        except Exception:
            return adjusted

    def _select_diverse_category(self, category_usage_tracker: dict, global_avoid_manager, combination_index: int) -> str:
        """  - """
        if not self.binding_categories:
            print(f"[V2] ")
            return None
        
        # 
        if len(self.binding_categories) == 1:
            selected = self.binding_categories[0]
            print(f"[V2] : '{selected}'")
            return selected
        
        try:
            # 
            category_scores = []
            
            for category in self.binding_categories:
                # 
                base_score = len(self.binding_combinations.get(category, {}))
                
                # 
                usage_count = category_usage_tracker.get(category, 0)
                usage_penalty = usage_count * 0.3  # 0.3
                
                # 
                diversity_bonus = 0
                if hasattr(global_avoid_manager, 'get_category_diversity_score'):
                    try:
                        diversity_bonus = global_avoid_manager.get_category_diversity_score(category)
                    except Exception:
                        diversity_bonus = 0
                
                # 
                rotation_bonus = 0
                if combination_index < len(self.binding_categories):
                    # 
                    target_category_index = combination_index % len(self.binding_categories)
                    if self.binding_categories.index(category) == target_category_index:
                        rotation_bonus = 2.0
                
                final_score = base_score - usage_penalty + diversity_bonus + rotation_bonus
                category_scores.append((category, final_score))
                
                print(f"[V2]  '{category}' : ({base_score}) - ({usage_penalty:.1f}) + ({diversity_bonus:.1f}) + ({rotation_bonus:.1f}) = {final_score:.1f}")
            
            # 
            category_scores.sort(key=lambda x: x[1], reverse=True)
            
            # 3
            top_categories = category_scores[:min(3, len(category_scores))]
            weights = [max(0.1, score) for _, score in top_categories]  # 
            
            # 
            if len(top_categories) > 1 and top_categories[0][1] - top_categories[1][1] < 1.0:
                import random
                selected_category = random.choices([cat for cat, _ in top_categories], weights=weights)[0]
            else:
                selected_category = top_categories[0][0]
            
            print(f"[V2] : '{selected_category}'")
            return selected_category
            
        except Exception as e:
            print(f"[V2] : {e}")
            # 
            selected = self.binding_categories[combination_index % len(self.binding_categories)]
            print(f"[V2] : '{selected}'")
            return selected
    
    def _get_diverse_binding_layer_states(self, category: str, global_avoid_manager, combination_index: int, avoid_duplicates: bool = False) -> dict:
        """🔧 关键修复：直接使用原始绑定组，不创建临时组，保持避重状态
        
        参数:
            category: 分类名称
            global_avoid_manager: 全局避重管理器
            combination_index: 组合索引
            avoid_duplicates: 是否启用避重机制
        """
        print(f"\n[🔍 预计算详细日志] _get_diverse_binding_layer_states 被调用")
        print(f"  组合索引: {combination_index}")
        print(f"  请求分类: {category}")
        print(f"  避重模式: {'启用' if avoid_duplicates else '禁用'}")
        
        layer_states = {}
        
        binding_manager = self.document.binding_manager
        if not binding_manager:
            print(f"[🔍 预计算详细日志] ⚠️ 警告：binding_manager 为空")
            return layer_states
        
        print(f"[🔍 预计算详细日志] 绑定组数量: {len(binding_manager.binding_groups)}")
        
        # 🔧 关键修复：直接使用原始绑定组的get_matched_files，保持状态连续性
        for group_id, group in binding_manager.binding_groups.items():
            print(f"[🔍 预计算详细日志] 检查绑定组: {group.name} (ID: {group_id})")
            
            # 确保绑定组已分析文件分类
            if not group.file_categories:
                print(f"[🔍 预计算详细日志] 绑定组 '{group.name}' 的 file_categories 为空，重建中...")
                # 只在第一次需要时分析
                group._rebuild_file_categories()
                print(f"[🔍 预计算详细日志] 重建后分类数: {len(group.file_categories)}")
            else:
                print(f"[🔍 预计算详细日志] 绑定组 '{group.name}' 已有分类: {list(group.file_categories.keys())}")
            
            # 🔧 关键修复：按绑定组自身可用分类选择，不强制使用公共分类。
            # 预览模式里每个绑定组独立随机选择分类；批量导出时若公共分类不存在于
            # 当前组，则回退到该组自己的可用分类，确保绑定继续生效。
            group_category = category
            if group_category not in group.file_categories:
                available_categories = group.get_available_categories()
                if available_categories:
                    # 使用组合索引做确定性选择，保证结果可复现且多样
                    group_category = available_categories[combination_index % len(available_categories)]
                    print(f"[🔍 预计算详细日志] 分类 '{category}' 在绑定组 '{group.name}' 中不可用，回退到组内分类 '{group_category}'")
                else:
                    print(f"[🔍 预计算详细日志] 绑定组 '{group.name}' 没有任何可用分类，跳过")
                    continue

            print(f"[🔍 预计算详细日志] ✅ 使用分类 '{group_category}' 处理绑定组 '{group.name}'")
            # 直接调用原始组的get_matched_files，传递避重参数
            matched_files = group.get_matched_files(group_category, avoid_duplicates=avoid_duplicates)
            print(f"[🔍 预计算详细日志] get_matched_files 返回了 {len(matched_files)} 个图层文件")

            
            # 计算并建立"组内索引 -> 可见文档图层索引"映射
            # 优先对象身份，其次绑定关系，最后名称回退，避免同名图层误配
            group_idx_to_doc_idx = {}
            used_doc_ids = set()
            for group_idx, group_layer in enumerate(group.layers):
                matched_doc_idx = None

                # 1) 对象身份匹配（最精确）
                for visible_idx, doc_layer in enumerate(self.visible_layers):
                    if doc_layer is group_layer and id(doc_layer) not in used_doc_ids:
                        matched_doc_idx = self._to_doc_layer_idx(visible_idx)
                        break

                # 2) 绑定关系 + 名称匹配
                if matched_doc_idx is None:
                    for visible_idx, doc_layer in enumerate(self.visible_layers):
                        if id(doc_layer) in used_doc_ids:
                            continue
                        if (binding_manager.layer_to_group.get(id(doc_layer)) == group_id and
                            getattr(doc_layer, 'name', None) == getattr(group_layer, 'name', None)):
                            matched_doc_idx = self._to_doc_layer_idx(visible_idx)
                            break

                # 3) 名称回退（兼容旧数据）
                if matched_doc_idx is None:
                    for visible_idx, doc_layer in enumerate(self.visible_layers):
                        if id(doc_layer) in used_doc_ids:
                            continue
                        if getattr(doc_layer, 'name', None) == getattr(group_layer, 'name', None):
                            matched_doc_idx = self._to_doc_layer_idx(visible_idx)
                            break

                if matched_doc_idx is not None:
                    group_idx_to_doc_idx[group_idx] = matched_doc_idx
                    try:
                        if hasattr(self.document, 'layers') and 0 <= matched_doc_idx < len(self.document.layers):
                            used_doc_ids.add(id(self.document.layers[matched_doc_idx]))
                    except Exception:
                        logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                        pass

            expected_count = len(group_idx_to_doc_idx)

            # 覆盖不完整时尝试补全缺失图层
            if len(matched_files) != expected_count:
                print(f"[🔍 预计算详细日志] ⚠️ 覆盖不完整，尝试补全缺失图层 (覆盖 {len(matched_files)}/{expected_count})")
                completed = dict(matched_files)
                for gi in range(len(group.layers)):
                    if gi not in group_idx_to_doc_idx:
                        continue
                    if gi in completed:
                        continue
                    layer_obj = group.layers[gi]
                    doc_idx = group_idx_to_doc_idx[gi]
                    try:
                        if hasattr(layer_obj, 'get_text_lines') and callable(getattr(layer_obj, 'get_text_lines', None)):
                            lines = []
                            try:
                                lines = [l for l in layer_obj.get_text_lines() if str(l).strip()]
                            except Exception:
                                lines = []
                            chosen = None
                            for l in lines:
                                if str(group_category) in str(l):
                                    chosen = str(l).strip()
                                    break
                            if not chosen:
                                curr = getattr(layer_obj, 'current_text', '')
                                if curr and str(group_category) in str(curr):
                                    chosen = str(curr).strip()
                            if chosen:
                                completed[gi] = self._build_text_virtual_path(layer_obj.name, chosen)
                            else:
                                pass
                        else:
                            base_pool = []
                            src = getattr(layer_obj, 'image_source', None)
                            if src and os.path.isdir(src):
                                try:
                                    base_pool = self._get_folder_images_cached(src, category=str(group_category))
                                except Exception:
                                    base_pool = []
                            if base_pool:
                                sel = base_pool[(combination_index * 7919 + gi * 9973) % len(base_pool)]
                                completed[gi] = sel
                    except Exception:
                        logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                        pass
                if len(completed) != expected_count:
                    print(f"[🔍 预计算详细日志] ⚠️ 补全失败，跳过绑定组 '{group.name}' (覆盖 {len(completed)}/{expected_count})")
                    continue
                matched_files = completed

            if not matched_files:
                if combination_index < 5:
                    print(f"[Precompute V2] Warning: No matched files for group {group_id} in category '{group_category}'")
                continue
            
            # Map group layer indices to document layer indices
            for group_layer_idx, file_path in matched_files.items():
                doc_layer_idx = group_idx_to_doc_idx.get(group_layer_idx)
                if doc_layer_idx is None:
                    continue
                if not hasattr(self.document, 'layers') or not (0 <= doc_layer_idx < len(self.document.layers)):
                    continue
                doc_layer = self.document.layers[doc_layer_idx]
                layer_states[doc_layer_idx] = file_path
                # 🔧 详细日志：前30次都显示
                if combination_index < 30 or combination_index % 10 == 0:
                    print(f"[预计算V2] 组合#{combination_index+1} 图层{doc_layer_idx} '{doc_layer.name}' <- {os.path.basename(file_path)}")

            # 写入绑定调试追踪（导出预计算链路）
            try:
                if hasattr(binding_manager, 'append_debug_trace'):
                    trace_rows = []
                    for group_layer_idx, file_path in matched_files.items():
                        doc_layer_idx = group_idx_to_doc_idx.get(group_layer_idx)
                        if (doc_layer_idx is not None and hasattr(self.document, 'layers')
                                and doc_layer_idx < len(self.document.layers)):
                            layer_name = getattr(self.document.layers[doc_layer_idx], 'name', f'layer_{doc_layer_idx}')
                        else:
                            layer_name = f'group_layer_{group_layer_idx}'
                        trace_rows.append((layer_name, file_path))
                    binding_manager.append_debug_trace("export_precompute", group.name, group_category, trace_rows)
            except Exception:
                logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                pass
        
        return layer_states
    
    def _get_diverse_binding_layer_states_OLD_BROKEN(self, category: str, global_avoid_manager, combination_index: int) -> dict:
        """  - """
        layer_states = {}
        
        #   binding_combinations
        if category in self.binding_combinations:
            layer_states.update(self.binding_combinations[category])
            
            if hasattr(global_avoid_manager, 'get_diverse_binding_combination'):
                try:
                    binding_manager = self.document.binding_manager
                    if binding_manager:
                        for group_id, group in binding_manager.binding_groups.items():
                            # 
                            all_combinations = self._generate_all_category_combinations(group, category)
                            if all_combinations and len(all_combinations) > 1:  # 
                                layer_indices = list(range(len(group.layers)))
                                optimal_combination = global_avoid_manager.get_diverse_binding_combination(
                                    group_id, category, all_combinations, layer_indices
                                )
                                
                                if optimal_combination:
                                    print(f"[V2] ")
                                    # 
                                    for layer_index_in_group, file_path in optimal_combination.items():
                                        if layer_index_in_group < len(group.layers):
                                            group_layer = group.layers[layer_index_in_group]
                                            # 
                                            for doc_layer_idx, doc_layer in enumerate(self.document.layers):
                                                if doc_layer.name == group_layer.name and doc_layer.visible:
                                                    layer_states[doc_layer_idx] = file_path
                                                    print(f"[V2]  '{category}'  {doc_layer_idx} '{doc_layer.name}' -> {os.path.basename(file_path)}")
                                                    break
                                else:
                                    print(f"[V2] ")
                            else:
                                print(f"[V2]  {group.name}  '{category}'  {len(all_combinations) if all_combinations else 0} ")
                except Exception as e:
                    print(f"[V2] : {e}")
        else:
            print(f"[V2]  '{category}' ")
            
            # 
            binding_manager = self.document.binding_manager
            if binding_manager:
                for group_id, group in binding_manager.binding_groups.items():
                    # 
                    if hasattr(group, '_matched_files_cache'):
                        group._matched_files_cache.clear()
                    
                    # 旧方法不启用避重
                    matched_files = group.get_matched_files(category, avoid_duplicates=False)
                    for layer_index_in_group, file_path in matched_files.items():
                        if layer_index_in_group < len(group.layers):
                            group_layer = group.layers[layer_index_in_group]
                            # 
                            for doc_layer_idx, doc_layer in enumerate(self.document.layers):
                                if doc_layer.name == group_layer.name and doc_layer.visible:
                                    layer_states[doc_layer_idx] = file_path
                                    print(f"[V2]  '{category}'  {doc_layer_idx} '{doc_layer.name}' -> {os.path.basename(file_path)}")
                                    break
        
        # 
        print(f"[V2] : {len(layer_states)} ")
        for doc_layer_idx, file_path in layer_states.items():
            print(f"[V2]  {doc_layer_idx}: {os.path.basename(file_path)}")
        
        return layer_states
    
    def _select_diverse_file_for_layer(self, layer_idx: int, selector, global_avoid_manager) -> str:
        """ """
        # 
        image_pool = self.layer_image_pools.get(layer_idx, [])
        
        if not image_pool:
            # 
            return selector.select_next_file()
        
        #  
        if hasattr(global_avoid_manager, 'get_least_used_images'):
            try:
                # 3
                least_used = global_avoid_manager.get_least_used_images(image_pool, min(3, len(image_pool)))
                if least_used:
                    import random
                    selected_file = random.choice(least_used)
                    usage_count = global_avoid_manager.get_image_usage_count(selected_file)
                    print(f"[V2]  {layer_idx} : {os.path.basename(selected_file)} (: {usage_count})")
                    return selected_file
            except Exception as e:
                print(f"[V2] : {e}")
        
        # 
        return selector.select_next_file()
    
    def _generate_all_category_combinations(self, group, category: str) -> list:
        """"""
        try:
            import itertools
            
            # 
            layer_file_lists = []
            
            for layer in group.layers:
                if hasattr(layer, 'image_source') and layer.image_source:
                    if getattr(layer, 'is_folder', False):
                        # 
                        layer_files = []
                        try:
                            layer_files = self._get_folder_images_cached(layer.image_source, category=category)
                        except Exception:
                            logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
                            pass
                        
                        if layer_files:
                            layer_file_lists.append(layer_files)
                    else:
                        # 
                        if category.lower() in os.path.basename(layer.image_source).lower():
                            layer_file_lists.append([layer.image_source])
            
            # 
            if layer_file_lists and all(layer_file_lists):
                all_combinations = []
                for combo_tuple in itertools.product(*layer_file_lists):
                    combo_dict = {i: file_path for i, file_path in enumerate(combo_tuple)}
                    all_combinations.append(combo_dict)
                
                print(f"[V2]  {group.name}  '{category}'  {len(all_combinations)} ")
                return all_combinations
            
        except Exception as e:
            print(f"[V2] : {e}")
        
        return []
    
    def _generate_deterministic_hash(self, layer_states: dict) -> str:
        """生成稳定的组合哈希：按图层索引顺序 + 文件名，不含时间/随机因子"""
        return generate_deterministic_hash(layer_states)

    def _extract_main_filename(self, filename: str) -> str:
        """"""
        import re

        if not filename:
            return ""

        # 
        # : "image_001" -> "image", "photo (1)" -> "photo", "pic-02" -> "pic"
        patterns = [
            r'[-_\s]*\(\d+\)$',  #  (1), (2) 
            r'[-_\s]*\d+$',      # 
            r'[-_\s]*\[\d+\]$',  #  [1], [2] 
        ]

        result = filename
        for pattern in patterns:
            result = re.sub(pattern, '', result)

        # 
        result = result.strip()

        # 
        if not result:
            result = filename

        return result

    def _clean_filename(self, filename: str) -> str:
        """"""
        import re
        import unicodedata

        if not isinstance(filename, str):
            filename = str(filename)

        # UnicodeNFKC
        try:
            filename = unicodedata.normalize('NFKC', filename)
        except Exception:
            try:
                filename = filename.encode('utf-8', 'ignore').decode('utf-8')
            except Exception:
                filename = "export"

        # Unicode
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in illegal_chars:
            filename = filename.replace(char, '_')

        # 
        filename = ''.join(char for char in filename if unicodedata.category(char)[0] != 'C')

        # 
        filename = re.sub(r'[-_\s]+', '-', filename)

        # 
        filename = filename.strip('-_ \t')

        # 
        if not filename:
            filename = "export"

        # 
        if len(filename) > 100:
            filename = filename[:100]

        return filename
