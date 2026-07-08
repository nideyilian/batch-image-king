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
from app.utils.print_utils import safe_print as _safe_print

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print

# 复用主模块中的 dataclass 定义，避免重复声明
from app.utils.batch_export_precomputer import (
    LayerCombination,
    ExportTask,
    PrecomputedExportPlan,
)
from app.utils.text_layer_virtual_path import build_text_layer_virtual_path


class BatchExportPrecomputerV2:
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
        在存在隐藏层时优先避免把“可见层索引”误当成文档索引。
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

        # 1) 当存在隐藏层且 idx 明显不是可见文档索引时，按“可见层索引”解析
        if has_hidden_layers and 0 <= idx < visible_count and idx not in visible_doc_set:
            try:
                mapped_doc_idx = self._to_doc_layer_idx(idx)
                if 0 <= mapped_doc_idx < len(doc_layers):
                    return doc_layers[mapped_doc_idx]
            except Exception:
                logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
                pass

        # 2) 按“文档真实索引”解析（新逻辑主路径）
        try:
            if 0 <= idx < len(doc_layers):
                # 存在隐藏层时，仅接受可见图层索引，避免命中隐藏层
                if (not has_hidden_layers) or (idx in visible_doc_set):
                    return doc_layers[idx]
        except Exception:
            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
            pass

        # 3) 兼容回退：按可见层索引解析
        try:
            if 0 <= idx < visible_count:
                mapped_doc_idx = self._to_doc_layer_idx(idx)
                if 0 <= mapped_doc_idx < len(doc_layers):
                    return doc_layers[mapped_doc_idx]
                return self.visible_layers[idx]
        except Exception:
            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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

    def _get_persistent_folder_index_path(self) -> str:
        """获取目录索引持久化文件路径（跨导出复用）"""
        try:
            base_dir = os.path.join(os.path.expanduser("~"), ".config", "批图王", "cache")
            os.makedirs(base_dir, exist_ok=True)
            return os.path.join(base_dir, "folder_index_v2.json")
        except Exception:
            return ""

    def _load_persistent_folder_index_cache(self):
        """加载持久化目录索引缓存"""
        path = self._persistent_folder_index_path
        if not path or not os.path.isfile(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            if isinstance(payload, dict):
                cache = payload.get('cache', {})
                if isinstance(cache, dict):
                    for abs_dir, entry in cache.items():
                        if not isinstance(entry, dict):
                            continue
                        mtime_ns = int(entry.get('mtime_ns', -1))
                        files = entry.get('files', [])
                        if isinstance(files, list):
                            self._folder_index_cache[abs_dir] = {
                                'mtime_ns': mtime_ns,
                                'files': [str(p) for p in files if isinstance(p, str)]
                            }
        except Exception:
            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
            pass

    def _save_persistent_folder_index_cache(self, force: bool = False):
        """保存持久化目录索引缓存（节流写入）"""
        if not self._folder_index_cache_dirty:
            return
        path = self._persistent_folder_index_path
        if not path:
            return
        now = time.time()
        if not force and (now - self._folder_index_last_save_time) < 2.0:
            return
        try:
            payload = {
                'version': 1,
                'saved_at': int(now),
                'cache': self._folder_index_cache
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)
            self._folder_index_cache_dirty = False
            self._folder_index_last_save_time = now
        except Exception:
            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
            pass

    def _get_directory_mtime_ns(self, directory: str) -> int:
        try:
            return int(os.stat(directory).st_mtime_ns)
        except Exception:
            return -1

    def _scan_folder_images(self, directory: str, cancel_callback: Optional[Callable[[], bool]] = None) -> List[str]:
        """使用 scandir 扫描目录图片，减少系统调用开销"""
        files: List[str] = []
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if cancel_callback and cancel_callback():
                        self._was_canceled = True
                        break
                    try:
                        if not entry.is_file():
                            continue
                        name_lower = entry.name.lower()
                        if name_lower.endswith(self._supported_image_ext):
                            files.append(entry.path)
                    except Exception:
                        logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
                        continue
        except Exception:
            return []
        return files

    def _get_folder_images_cached(self, directory: str, category: Optional[str] = None,
                                  cancel_callback: Optional[Callable[[], bool]] = None) -> List[str]:
        """获取目录图片列表（带临时索引缓存，按目录 mtime 自动失效）"""
        if not directory:
            return []
        abs_dir = os.path.abspath(directory)
        if not os.path.isdir(abs_dir):
            return []

        dir_mtime_ns = self._get_directory_mtime_ns(abs_dir)
        cache_entry = self._folder_index_cache.get(abs_dir)

        if cache_entry and cache_entry.get('mtime_ns') == dir_mtime_ns:
            base_files = cache_entry.get('files', [])
        else:
            base_files = self._scan_folder_images(abs_dir, cancel_callback=cancel_callback)
            self._folder_index_cache[abs_dir] = {
                'mtime_ns': dir_mtime_ns,
                'files': base_files,
            }
            self._folder_index_cache_dirty = True

        if category is None:
            return list(base_files)

        cat = str(category).lower()
        if not cat:
            return list(base_files)
        return [p for p in base_files if cat in os.path.basename(p).lower()]

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
            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
                logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
                    logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
                    pass
                continue
            normalized.append(int_idx)
        return normalized

    # =========================
    # 迭代2：职责拆分（同文件内）
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
                        logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
            return self._generate_standard_combinations_v2(
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
        目标：在保持去重效果的同时，减少“大池+多层”场景的无效尝试开销。
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
        """构建统一短缺分析，定位“为什么没凑满”。"""
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

    def _build_combination_runtime_metadata(
        self,
        layer_states: Dict[int, str],
        combination_index: int,
        category: Optional[str] = None
    ) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
        """
        为组合构建运行时元数据（随机变换/图层参数/分身参数）。
        统一标准模式与绑定模式的预计算行为，避免导出阶段状态漂移。
        """
        random_transforms: Dict[int, Dict[str, Any]] = {}
        layer_parameters: Dict[int, Dict[str, Any]] = {}
        layer_clone_settings: Dict[int, Dict[str, Any]] = {}
        category_key = str(category or "")

        import random
        for layer_idx, file_path in layer_states.items():
            layer = self._resolve_layer_by_state_index(layer_idx)
            if layer is None:
                continue

            # 文字图层不参与随机缩放/旋转
            is_text_layer = bool(hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)))

            # 使用稳定种子，保证预计算可复现
            random_seed = hash((
                int(combination_index),
                int(layer_idx),
                os.path.basename(str(file_path or "")),
                category_key,
            )) & 0x7FFFFFFF
            rng = random.Random(random_seed)

            if is_text_layer:
                transform_params = {
                    'random_offset_x': 0,
                    'random_offset_y': 0,
                    'random_scale': 1.0,
                    'random_rotation': 0.0,
                }
            else:
                if bool(getattr(layer, 'random_position_enabled', False)):
                    position_range = int(getattr(layer, 'random_position_range', 0) or 0)
                    offset_x = rng.randint(-position_range, position_range)
                    offset_y = rng.randint(-position_range, position_range)
                else:
                    offset_x = 0
                    offset_y = 0

                if bool(getattr(layer, 'random_scale_enabled', False)):
                    scale_min = float(getattr(layer, 'random_scale_min', 1.0) or 1.0)
                    scale_max = float(getattr(layer, 'random_scale_max', 1.0) or 1.0)
                    random_scale = rng.uniform(min(scale_min, scale_max), max(scale_min, scale_max))
                else:
                    random_scale = 1.0

                if bool(getattr(layer, 'random_rotation_enabled', False)):
                    rotate_range = float(getattr(layer, 'random_rotation_range', 0.0) or 0.0)
                    random_rotation = rng.uniform(-rotate_range, rotate_range)
                else:
                    random_rotation = 0.0

                transform_params = {
                    'random_offset_x': int(offset_x),
                    'random_offset_y': int(offset_y),
                    'random_scale': float(random_scale),
                    'random_rotation': float(random_rotation),
                }

            random_transforms[int(layer_idx)] = transform_params

            layer_parameters[int(layer_idx)] = {
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

            clone_settings = self._capture_clone_settings(layer)
            if clone_settings:
                layer_clone_settings[int(layer_idx)] = clone_settings

        return random_transforms, layer_parameters, layer_clone_settings

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
                                except:
                                    logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
                                    except:
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
                        logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
        # 会话级均衡状态：压制“组合唯一但视觉上重复刷同一张”
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

                # C步：确定性枚举仅用于“组合空间与目标数量接近”的场景。
                # 当组合空间远大于导出数量时，枚举会让高位图层变化过慢，视觉上出现“某些素材被过度重复”。
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
                        # 即使走确定性枚举，也持续记录全局使用计数，保证后续批次仍有“少用优先”约束
                        try:
                            global_avoid_manager.record_combination_usage(list(layer_states.values()))
                        except Exception:
                            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
            # 会话内均衡计数：让后续组合自动避开“近期高频素材”
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
                # 保留少量“本批次最少使用”候选，确保均衡效果不丢
                usage_pairs = sorted(
                    [(p, int(session_usage.get(p, 0))) for p in candidate_pool],
                    key=lambda x: (x[1], str(x[0]))
                )
                low_usage_keep = [p for p, _ in usage_pairs[:24]]
                merged = list(dict.fromkeys(sampled + low_usage_keep))
                candidate_pool = merged
            # 均匀分布硬约束：尽量把每张图使用次数压在“平均值+缓冲”以内
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
                    except:
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
            
            if category in group.file_categories:
                print(f"[🔍 预计算详细日志] ✅ 分类 '{category}' 在绑定组 '{group.name}' 中找到")
                # 直接调用原始组的get_matched_files，传递避重参数
                matched_files = group.get_matched_files(category, avoid_duplicates=avoid_duplicates)
                print(f"[🔍 预计算详细日志] get_matched_files 返回了 {len(matched_files)} 个图层文件")
                
                # 计算并建立“组内索引 -> 可见文档图层索引”映射
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
                            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
                                    if str(category) in str(l):
                                        chosen = str(l).strip()
                                        break
                                if not chosen:
                                    curr = getattr(layer_obj, 'current_text', '')
                                    if curr and str(category) in str(curr):
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
                                        base_pool = self._get_folder_images_cached(src, category=str(category))
                                    except Exception:
                                        base_pool = []
                                if base_pool:
                                    sel = base_pool[(combination_index * 7919 + gi * 9973) % len(base_pool)]
                                    completed[gi] = sel
                        except Exception:
                            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
                            pass
                    if len(completed) != expected_count:
                        print(f"[🔍 预计算详细日志] ⚠️ 补全失败，跳过绑定组 '{group.name}' (覆盖 {len(completed)}/{expected_count})")
                        continue
                    matched_files = completed

                if not matched_files:
                    if combination_index < 5:
                        print(f"[Precompute V2] Warning: No matched files for group {group_id} in category '{category}'")
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
                        binding_manager.append_debug_trace("export_precompute", group.name, category, trace_rows)
                except Exception:
                    logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
                        except:
                            logger.debug("静默异常已忽略: except in utils/batch_export_precomputer_v2.py")
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
        import hashlib
        parts = []
        for layer_idx in sorted(layer_states.keys()):
            file_path = layer_states[layer_idx]
            parts.append(f"L{layer_idx}:{os.path.basename(file_path)}")
        combined_str = "|".join(parts)
        return hashlib.md5(combined_str.encode('utf-8')).hexdigest()[:16]

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
