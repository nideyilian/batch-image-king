"""


"""

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
import threading
from app.utils.print_utils import safe_print as _safe_print
from app.utils.text_layer_virtual_path import build_text_layer_virtual_path

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print


@dataclass
class LayerCombination:
    """图层组合 - 完整预计算版本
    
    包含所有必要的参数，确保执行时不再有任何随机性
    """
    index: int
    layer_states: Dict[int, str]  # 图层索引 -> 图片文件路径
    layer_clone_settings: Dict[int, Dict]  # 图层索引 -> 分身设置
    combination_hash: str  # 组合的唯一哈希（基于完整参数）
    is_unique: bool
    
    # 🔧 强化预计算：添加完整的随机变换参数
    random_transforms: Dict[int, Dict] = None  # 图层索引 -> 随机变换参数
    # 随机变换参数包括：
    # - random_offset_x, random_offset_y: 随机位置偏移
    # - random_scale: 随机缩放比例
    # - random_rotation: 随机旋转角度
    
    # 添加图层的其他必要参数
    layer_parameters: Dict[int, Dict] = None  # 图层索引 -> 完整图层参数
    # 图层参数包括：
    # - opacity: 不透明度
    # - blend_mode: 混合模式
    # - x, y, width, height: 位置和尺寸
    # - fit_mode, crop_direction: 适配和裁剪
    # - corner_radius: 圆角
    # - stroke相关: 描边参数
    
    def __post_init__(self):
        """初始化时确保所有字典都存在"""
        if self.random_transforms is None:
            self.random_transforms = {}
        if self.layer_parameters is None:
            self.layer_parameters = {}


@dataclass
class ExportTask:
    """"""
    combination: LayerCombination
    filename: str
    file_path: str
    file_number: int


@dataclass
class PrecomputedExportPlan:
    """"""
    tasks: List[ExportTask]
    total_count: int
    unique_combinations: int
    estimated_time: float
    memory_requirement_mb: float
    optimization_suggestions: List[str]
    precompute_diagnostics: Optional[Dict[str, Any]] = None


class BatchExportPrecomputer:
    """"""
    
    def __init__(self, document):
        self.document = document
        self.visible_layers = []
        self.layer_image_pools = {}  # 
        self.combination_cache = {}  # 
        self.filename_cache = {}     # 

        #  
        self._clear_all_caches()

    def _clear_all_caches(self):
        """"""
        self.combination_cache.clear()
        self.filename_cache.clear()
        self.layer_image_pools.clear()

        # 
        if hasattr(self, 'binding_categories'):
            delattr(self, 'binding_categories')
        if hasattr(self, 'binding_combinations'):
            delattr(self, 'binding_combinations')
        if hasattr(self, 'non_binding_layer_selectors'):
            delattr(self, 'non_binding_layer_selectors')

        # 
        self.stats = {
            'combinations_generated': 0,
            'duplicates_avoided': 0,
            'cache_hits': 0,
            'precompute_time': 0.0
        }

        print("[] ")

        # 
        self.stats = {
            'precompute_time': 0.0,
            'combinations_generated': 0,
            'duplicates_avoided': 0,
            'cache_hits': 0
        }

        self._lock = threading.Lock()

    def _get_avoid_repeat_manager(self):
        """获取当前文档专属的避重管理器，避免不同打开文件互相污染导出参考。"""
        from app.utils.global_avoid_repeat_manager import GlobalAvoidRepeatManager
        doc_path = str(getattr(self.document, "file_path", "") or "")
        if doc_path:
            scope_key = os.path.abspath(doc_path)
        else:
            scope_key = f"unsaved_{id(self.document)}"
        return GlobalAvoidRepeatManager(scope_key=scope_key)
    
    def analyze_document(self):
        """"""
        print("[] ...")

        # 
        self.visible_layers = [layer for layer in self.document.layers if layer.visible]

        #  
        self.binding_enabled = False  # 

        # 
        if (hasattr(self.document, 'binding_manager') and
            self.document.binding_manager and
            self.document.binding_manager.global_enabled):

            # 
            binding_groups = getattr(self.document.binding_manager, 'binding_groups', {})
            if binding_groups:
                #  
                has_bound_layers = False
                bound_layer_count = 0

                for layer in self.visible_layers:
                    #  is_layer_bound 
                    if self.document.binding_manager.is_layer_bound(layer):
                        has_bound_layers = True
                        bound_layer_count += 1
                        print(f"[] : {layer.name}")

                if has_bound_layers:
                    self.binding_enabled = True
                    print("[]  ")
                    print(f"[] : {len(binding_groups)}")
                    print(f"[] : {bound_layer_count}")
                else:
                    print("[]   ")
                    print(f"[]  {len(self.visible_layers)} ")
            else:
                print("[]   ")
        else:
            print("[] ℹ  ")

        if self.binding_enabled:
            return self._analyze_document_with_binding()
        else:
            return self._analyze_document_standard()

    def _analyze_document_standard(self):
        """"""
        #  
        self._initialize_layer_image_pools()

        # 
        total_combinations = 1
        for pool in self.layer_image_pools.values():
            if pool:
                total_combinations *= len(pool)

        print(f"[]  {len(self.visible_layers)} ")
        print(f"[] : {total_combinations:,}")

        return total_combinations

    def _initialize_layer_image_pools(self):
        """"""
        self.layer_image_pools = {}

        # 
        for i, layer in enumerate(self.visible_layers):
            image_pool = []

            # _test_image_pool
            if hasattr(layer, '_test_image_pool') and layer._test_image_pool:
                image_pool = layer._test_image_pool.copy()

            # image_source
            elif hasattr(layer, 'image_source') and layer.image_source:
                if hasattr(layer, 'is_folder') and layer.is_folder:
                    # 
                    try:
                        if os.path.isdir(layer.image_source):
                            image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp']
                            for file in os.listdir(layer.image_source):
                                ext = os.path.splitext(file)[1].lower()
                                if ext in image_extensions:
                                    image_pool.append(os.path.join(layer.image_source, file))
                    except Exception as e:
                        print(f"[]  {layer.name} : {e}")
                else:
                    # 
                    if os.path.isfile(layer.image_source):
                        image_pool.append(layer.image_source)

            # _image_source
            elif hasattr(layer, '_image_source') and layer._image_source:
                if hasattr(layer, '_is_folder') and layer._is_folder:
                    # 
                    try:
                        if os.path.isdir(layer._image_source):
                            image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff', '.webp']
                            for file in os.listdir(layer._image_source):
                                ext = os.path.splitext(file)[1].lower()
                                if ext in image_extensions:
                                    image_pool.append(os.path.join(layer._image_source, file))
                    except Exception as e:
                        print(f"[]  {layer.name} : {e}")
                else:
                    # 
                    if os.path.isfile(layer._image_source):
                        image_pool.append(layer._image_source)

            # image_paths
            elif hasattr(layer, 'image_paths') and layer.image_paths:
                image_pool = layer.image_paths.copy()

            # current_image_path
            elif hasattr(layer, 'current_image_path') and layer.current_image_path:
                image_pool = [layer.current_image_path]

            # 
            self.layer_image_pools[i] = image_pool
            print(f"[]  '{layer.name}': {len(image_pool)} ")

    def _analyze_document_with_binding(self):
        """"""
        binding_manager = self.document.binding_manager

        #  
        self._initialize_layer_image_pools()

        # 
        self.binding_categories = []
        self.binding_combinations = {}

        print(f"[]  {len(binding_manager.binding_groups)} ")

        # 计算所有绑定组的公共分类，限制导出只使用公共分类
        common_categories = []
        try:
            if hasattr(self.document, '_get_binding_common_categories') and callable(getattr(self.document, '_get_binding_common_categories', None)):
                common_categories = self.document._get_binding_common_categories()
                print(f"[预计算] 公共分类: {common_categories}")
        except Exception as e:
            print(f"[预计算] 获取公共分类失败: {e}")

        for group_id, group in binding_manager.binding_groups.items():
            print(f"[] : {group.name}")

            # 
            group._rebuild_file_categories()

            # 
            available_categories = group.get_available_categories()
            print(f"[]  {group.name} : {available_categories}")

            # 
            for category in available_categories:
                # 若存在公共分类限制，则仅处理公共分类
                if common_categories and category not in common_categories:
                    continue
                if category not in self.binding_combinations:
                    self.binding_combinations[category] = {}

                # 分析阶段不启用避重
                matched_files = group.get_matched_files(category, avoid_duplicates=False)

                # 
                for layer_index_in_group, file_path in matched_files.items():
                    if layer_index_in_group < len(group.layers):
                        group_layer = group.layers[layer_index_in_group]

                        # 
                        for doc_layer_idx, doc_layer in enumerate(self.visible_layers):
                            if doc_layer.name == group_layer.name:
                                self.binding_combinations[category][doc_layer_idx] = file_path
                                break

        # 设置绑定导出使用的分类列表：优先公共分类
        if common_categories:
            # 仅保留存在于组合映射中的公共分类
            self.binding_categories = [c for c in common_categories if c in self.binding_combinations]
        else:
            self.binding_categories = list(self.binding_combinations.keys())
        print(f"[]  {len(self.binding_categories)} : {self.binding_categories}")

        #  
        if not self.binding_categories:
            print(f"[] ")
            self.binding_enabled = False  # 
            return self._analyze_document_standard()

        total_combinations = 0
        for category in self.binding_categories:
            current_category_combinations = 1
            has_valid_group = False
            
            for group in binding_manager.binding_groups.values():
                if category in group.file_categories:
                    has_valid_group = True
                    group_combinations = 1
                    layer_indices = sorted(group.file_categories[category].keys())
                    
                    if not layer_indices:
                        group_combinations = 0
                    else:
                        for layer_idx in layer_indices:
                            file_count = len(group.file_categories[category][layer_idx])
                            if file_count == 0:
                                group_combinations = 0
                                break
                            group_combinations *= file_count
                    
                    current_category_combinations *= group_combinations
            
            if has_valid_group:
                total_combinations += current_category_combinations
        
        if total_combinations == 0 and self.binding_categories:
            print(f"[预计算] ⚠️ 组合数计算为0，回退到分类数量")
            total_combinations = len(self.binding_categories)

        print(f"[]  -  {len(self.visible_layers)} ")
        print(f"[]  - : {total_combinations}")

        return total_combinations

    def _initialize_non_binding_layer_selectors(self, count: int):
        """"""
        self.non_binding_layer_selectors = {}

        # 
        binding_layer_names = set()
        if hasattr(self.document, 'binding_manager') and self.document.binding_manager:
            for group in self.document.binding_manager.binding_groups.values():
                for layer in group.layers:
                    binding_layer_names.add(layer.name)

        # 
        for layer_idx, layer in enumerate(self.visible_layers):
            if layer.name not in binding_layer_names:
                # 
                if layer_idx in self.layer_image_pools and self.layer_image_pools[layer_idx]:
                    image_pool = self.layer_image_pools[layer_idx]
                    selector = self._create_smart_file_selector(image_pool, count)
                    self.non_binding_layer_selectors[layer_idx] = selector
                    print(f"[]  '{layer.name}' : {len(image_pool)} ")

    def _create_smart_file_selector(self, image_pool: list, total_count: int):
        """"""
        import random

        if not image_pool:
            return []

        # 
        if len(image_pool) >= total_count:
            shuffled_pool = image_pool.copy()
            random.shuffle(shuffled_pool)
            return shuffled_pool

        # 
        base_count = total_count // len(image_pool)
        extra_count = total_count % len(image_pool)

        # 
        file_sequence = []
        for i, file_path in enumerate(image_pool):
            repeat_count = base_count + (1 if i < extra_count else 0)
            file_sequence.extend([file_path] * repeat_count)

        # 
        return self._smart_shuffle_files(file_sequence)

    def _smart_shuffle_files(self, file_sequence: list):
        """"""
        import random

        if len(file_sequence) <= 1:
            return file_sequence

        # 
        best_sequence = None
        best_score = float('inf')

        for attempt in range(10):  # 10
            sequence = file_sequence.copy()
            random.shuffle(sequence)

            # 
            score = 0
            for i in range(len(sequence) - 1):
                if sequence[i] == sequence[i + 1]:
                    score += 1

            if score < best_score:
                best_score = score
                best_sequence = sequence.copy()

                # 
                if score == 0:
                    break

        # 
        if best_score > 0 and best_sequence:
            best_sequence = self._optimize_file_sequence(best_sequence)

        return best_sequence or file_sequence

    def _optimize_file_sequence(self, sequence: list):
        """"""
        sequence = sequence.copy()

        # 
        for _ in range(5):
            improved = False

            # 
            for i in range(len(sequence) - 1):
                if sequence[i] == sequence[i + 1]:
                    # 
                    for j in range(i + 2, len(sequence)):
                        if (sequence[j] != sequence[i] and
                            (i == 0 or sequence[j] != sequence[i - 1]) and
                            (j == len(sequence) - 1 or sequence[i + 1] != sequence[j + 1])):
                            # 
                            sequence[i + 1], sequence[j] = sequence[j], sequence[i + 1]
                            improved = True
                            break

                    if improved:
                        break

            if not improved:
                break

        return sequence

    def generate_smart_combinations(self, count: int, avoid_duplicates: bool = True) -> List[LayerCombination]:
        """"""
        print(f"[]  {count} ...")

        #  
        if (hasattr(self, 'binding_enabled') and self.binding_enabled and
            hasattr(self, 'binding_categories') and self.binding_categories):
            print(f"[]  {len(self.binding_categories)} ")
            return self._generate_binding_combinations(count, avoid_duplicates)
        else:
            if hasattr(self, 'binding_enabled') and self.binding_enabled:
                print(f"[]   ")
            else:
                print(f"[] ℹ  ")

        # 
        theoretical_max = 1
        for pool in self.layer_image_pools.values():
            if pool:
                theoretical_max *= len(pool)

        # 
        actual_count = min(count, theoretical_max)
        if actual_count < count:
            print(f"[]  {count}  {theoretical_max} {actual_count}")

        # 
        if actual_count <= theoretical_max * 0.8:
            # 
            return self._generate_random_combinations(actual_count, avoid_duplicates)
        else:
            # 
            return self._generate_exhaustive_combinations(actual_count)

    def _generate_binding_combinations(self, count: int, avoid_duplicates: bool) -> List[LayerCombination]:
        """ - """
        print(f"[]   {count} ")
        print(f"[]    avoid_duplicates={avoid_duplicates}")

        if not hasattr(self, 'binding_categories') or not self.binding_categories:
            print(f"[]  ")
            return self._generate_random_combinations(count, avoid_duplicates)

        combinations = []
        import random
        import time
        import hashlib

        # 
        global_avoid_manager = self._get_avoid_repeat_manager()
        print(f"[]  : {len(global_avoid_manager.combination_history)}")

        #  
        seen_hashes = set() if avoid_duplicates else None
        max_attempts = count * 15  # 
        attempts = 0
        
        #  
        duplicate_attempts = 0
        consecutive_duplicates = 0  # 连续重复次数
        MAX_CONSECUTIVE_DUPLICATES = 20  # 降低阈值，更快判定唯一组合耗尽

        #  
        binding_manager = self.document.binding_manager
        if not binding_manager:
            print(f"[] ")
            return self._generate_random_combinations(count, avoid_duplicates)

        #  
        for group_id, group in binding_manager.binding_groups.items():
            if hasattr(group, '_matched_files_cache'):
                group._matched_files_cache.clear()
            if hasattr(group, '_session_seed'):
                delattr(group, '_session_seed')
            if hasattr(group, 'layer_image_usage'):
                for layer_usage in group.layer_image_usage.values():
                    layer_usage.clear()

        #  
        self._initialize_non_binding_layer_selectors(count)

        #  3
        print(f"[]  3")
        
        #  
        # 
        print(f"[]   + ")

        #  
        optimized_non_binding_pools = {}
        for layer_idx, pool in self.layer_image_pools.items():
            # 
            is_bound = False
            for group in binding_manager.binding_groups.values():
                for i, layer in enumerate(group.layers):
                    for j, visible_layer in enumerate(self.visible_layers):
                        if visible_layer.name == layer.name and j == layer_idx:
                            is_bound = True
                            break
                if is_bound:
                    break
            if is_bound:
                break
        
        # 
        if not is_bound and pool:
            optimized_non_binding_pools[layer_idx] = pool

        # 
        if optimized_non_binding_pools:
            optimized_non_binding_pools = global_avoid_manager.optimize_image_pools(optimized_non_binding_pools)
            print(f"[] : {len(optimized_non_binding_pools)} ")

        i = 0
        invalid_categories = set()
        unique_combinations_exhausted = False
        
        while len(combinations) < count and attempts < max_attempts:
            attempts += 1
            
            #  
            selected_category = self._select_optimal_category_dynamic(binding_manager, invalid_categories)
            if not selected_category:
                print(f"[] ")
                break

            print(f"[]  {len(combinations)+1}:  '{selected_category}' ( {attempts})")

            # 🔧 终极修复：如果连续多次无法生成新的唯一组合（可能分类可用组合已耗尽）
            # 强制重置当前分类的使用历史，允许复用
            if consecutive_duplicates > 10 and selected_category:
                print(f"[预计算] ⚠️ 分类 '{selected_category}' 连续重复 {consecutive_duplicates} 次，尝试强制重置其使用历史")
                for group in binding_manager.binding_groups.values():
                    if hasattr(group, '_category_usage_history') and selected_category in group._category_usage_history:
                        group._category_usage_history[selected_category].clear()
                        print(f"[预计算] 已清空绑定组 '{group.name}' 分类 '{selected_category}' 的使用历史")
            
            #  
            layer_states = {}
            combination_files = []  # 

            # 
            binding_selections = {}  # 
            
            for group_id, group in binding_manager.binding_groups.items():
                #  
                if hasattr(group, '_matched_files_cache'):
                    group._matched_files_cache.clear()
                # 
                if hasattr(group, '_session_seed'):
                    delattr(group, '_session_seed')

                #  
                microsecond_time = int(time.time() * 1000000) % 10000000  # 7
                thread_id = threading.get_ident() % 10000  # ID
                process_id = os.getpid() % 10000  # ID
                memory_addr = id(group) % 100000  # 
                combination_entropy = (i * 9973) % 1000000  # 
                random_boost = random.randint(100000, 999999)  # 
                
                # 
                super_random_seed = (
                    microsecond_time + 
                    thread_id * 1000 +
                    process_id * 10000 +
                    memory_addr +
                    combination_entropy +
                    random_boost +
                    attempts * 7919  # 
                ) % 2**31
                
                group._session_seed = super_random_seed
                print(f"[]  {group_id} : {super_random_seed}")

                # 
                if selected_category in group.file_categories:
                    #  
                    #  get_matched_files 
                    category_files = group.file_categories[selected_category]
                    layer_indices = sorted(category_files.keys())
                    
                    # 
                    import itertools
                    layer_file_lists = []
                    for layer_idx in layer_indices:
                        files = category_files[layer_idx]
                        if files:
                            layer_file_lists.append(files)
                        else:
                            print(f"[]  {group_id}  {layer_idx}  '{selected_category}' ")
                            layer_file_lists = []  # 
                            invalid_categories.add(selected_category)
                            print(f"[预计算] 标记分类 '{selected_category}' 为无效（因缺少文件）")
                            break
                    
                    if layer_file_lists:
                        # 
                        all_possible_combinations = []
                        for combo_tuple in itertools.product(*layer_file_lists):
                            combo_dict = {}
                            for idx, file_path in enumerate(combo_tuple):
                                combo_dict[layer_indices[idx]] = file_path
                            all_possible_combinations.append(combo_dict)
                        
                        print(f"[]  {group_id}  '{selected_category}' : {len(all_possible_combinations)}")
                        
                        #  
                        optimal_combination = None
                        if avoid_duplicates:
                            optimal_combination = global_avoid_manager.get_diverse_binding_combination(
                                group_id, selected_category, all_possible_combinations, layer_indices
                            )
                        else:
                            # 允许重复：完全随机选择
                            import random
                            if all_possible_combinations:
                                optimal_combination = random.choice(all_possible_combinations)
                                # 确保 key 是 int (如果 key 是 str)
                                optimal_combination = {int(k): v for k, v in optimal_combination.items()}
                        
                        if optimal_combination:
                            binding_selections[group_id] = optimal_combination
                            print(f"[]  {group_id} ")
                            
                            # 
                            for layer_index_in_group, file_path in optimal_combination.items():
                                if layer_index_in_group < len(group.layers):
                                    group_layer = group.layers[layer_index_in_group]
                                    # 
                                    for doc_layer_idx, doc_layer in enumerate(self.visible_layers):
                                        if doc_layer.name == group_layer.name:
                                            layer_states[doc_layer_idx] = file_path
                                            combination_files.append(file_path)
                                            print(f"[]  {doc_layer_idx} ({doc_layer.name}) <- {os.path.basename(file_path)}")
                                            break
                        else:
                            print(f"[]  {group_id} ")
                            # 
                            continue
                    else:
                        print(f"[]  {group_id}  '{selected_category}' ")
                        continue

            #  
            non_binding_layer_pools = {}
            for layer_idx in range(len(self.visible_layers)):
                if layer_idx not in layer_states:
                    if layer_idx in optimized_non_binding_pools:
                        non_binding_layer_pools[layer_idx] = optimized_non_binding_pools[layer_idx]

            if non_binding_layer_pools:
                # 
                non_binding_selections = global_avoid_manager.get_diverse_combination(non_binding_layer_pools)
                for layer_idx, file_path in non_binding_selections.items():
                    layer_states[layer_idx] = file_path
                    combination_files.append(file_path)
            else:
                # 
                for layer_idx in range(len(self.visible_layers)):
                    if layer_idx not in layer_states:
                        if (hasattr(self, 'non_binding_layer_selectors') and
                            layer_idx in self.non_binding_layer_selectors):
                            # 
                            selector = self.non_binding_layer_selectors[layer_idx]
                            if i < len(selector):
                                selected_file = selector[i]
                            else:
                                selected_file = selector[i % len(selector)]
                            layer_states[layer_idx] = selected_file
                            combination_files.append(selected_file)
                        elif (hasattr(self, 'layer_image_pools') and
                              layer_idx in self.layer_image_pools and
                              self.layer_image_pools[layer_idx]):
                            # 
                            selected_file = random.choice(self.layer_image_pools[layer_idx])
                            layer_states[layer_idx] = selected_file
                            combination_files.append(selected_file)

            # 
            layer_clone_settings = {}
            combination_parts = []

            for layer_idx, file_path in layer_states.items():
                #  使用确定性组合键：图层索引 + 文件名（不含路径）
                combination_parts.append(f"L{layer_idx}:{os.path.basename(file_path)}")

                # 
                if layer_idx < len(self.visible_layers):
                    layer = self.visible_layers[layer_idx]
                    clone_settings = self._capture_clone_settings(layer)
                    layer_clone_settings[layer_idx] = clone_settings

            #  
            # 按图层索引排序，确保组合键稳定
            combination_str = "|".join(sorted(combination_parts))
            combination_hash = hashlib.md5(combination_str.encode()).hexdigest()[:16]
            combination_hash_sha = hashlib.sha256(combination_str.encode()).hexdigest()[:16]
            full_hash = f"{combination_hash}_{combination_hash_sha}"

            #  
            if avoid_duplicates:
                # 本地集合去重（会话内唯一）
                is_locally_unique = (seen_hashes is None or 
                                     (combination_hash not in seen_hashes and full_hash not in seen_hashes))
                if not is_locally_unique:
                    if unique_combinations_exhausted:
                        # 已判定耗尽，直接允许，不再计数
                        duplicate_attempts += 1
                        pass
                    else:
                        duplicate_attempts += 1
                        consecutive_duplicates += 1
                        
                        if attempts % 10 == 0:
                            print(f"[预计算调试] 尝试#{attempts}: 重复! 连续重复={consecutive_duplicates}, 阈值={MAX_CONSECUTIVE_DUPLICATES}")
                        
                        # 🔧 修复：如果连续重复次数过多，说明唯一组合已耗尽，允许重复
                        if consecutive_duplicates > MAX_CONSECUTIVE_DUPLICATES:
                            if consecutive_duplicates % 10 == 0:  # 减少日志输出频率
                                print(f"[预计算] ⚠️ 连续重复 {consecutive_duplicates} 次，判定唯一组合已耗尽，允许使用重复组合")
                            unique_combinations_exhausted = True
                            # 允许通过，不 continue
                            pass
                        else:
                            i += 1
                            continue
                else:
                    consecutive_duplicates = 0  # 重置计数器

            if seen_hashes is not None:
                seen_hashes.add(combination_hash)
                seen_hashes.add(full_hash)  # 

            # 
            combination = LayerCombination(
                index=len(combinations),
                layer_states=layer_states,
                layer_clone_settings=layer_clone_settings,
                combination_hash=combination_hash,
                is_unique=True
            )

            combinations.append(combination)
            #  10
            if len(combinations) % 10 == 0 or len(combinations) == count:
                print(f"[]  {len(combinations)}/{count} ")
            
            # 记录到全局避重历史，避免跨批次重复
            if hasattr(global_avoid_manager, 'record_combination_usage'):
                global_avoid_manager.record_combination_usage(combination_files)

            # 记录唯一使用消耗
            if self.unique_use_enabled and self.unique_use_layers:
                for doc_layer_idx, file_path in layer_states.items():
                    if doc_layer_idx in self.unique_use_layers:
                        self._unique_used_map.setdefault(doc_layer_idx, set()).add(file_path)
            
            i += 1

        if len(combinations) < count:
            print(f"[]   {len(combinations)}  {count} ")
            print(f"[]    : {attempts}/{max_attempts}")
            print(f"[]    : {duplicate_attempts} ")
            print(f"[]    : {len(seen_hashes) if seen_hashes else 0}")
            print(f"[]    : {len(global_avoid_manager.combination_history)}")
            print(f"[] ⚠  可用唯一组合不足，已按最大唯一组合返回")

        print(f"[]  : {len(combinations)} ")
        print(f"[]     {len(global_avoid_manager.combination_history)} ")
        return combinations
    
        
    def _select_optimal_category_dynamic(self, binding_manager, invalid_categories: set = None) -> Optional[str]:
        """ - """
        if not hasattr(self, 'binding_categories') or not self.binding_categories:
            return None
        
        # 
        category_scores = {}
        global_mgr = binding_manager.global_combination_manager
        
        for category in self.binding_categories:
            # 过滤无效分类
            if invalid_categories and category in invalid_categories:
                continue
            total_score = 0
            total_combinations = 0
            
            # 
            category_usage = 0
            if global_mgr:
                for group_id in binding_manager.binding_groups.keys():
                    category_usage += global_mgr.get_category_usage_count(group_id, category)
            
            #  
            pattern_score = 1.0
            if global_mgr:
                pattern_score = global_mgr.get_pattern_aware_category_score(category)
            
            # 
            for group_id, group in binding_manager.binding_groups.items():
                if category in group.file_categories:
                    # 
                    diversity_info = group.analyze_category_diversity()
                    if category in diversity_info:
                        info = diversity_info[category]
                        diversity_score = info['diversity_score']
                        combinations_count = info['total_combinations']
                        
                        #  +  +  + 
                        # 1) 2) 3) 4)
                        score = (
                            diversity_score * 100 * pattern_score +  #  + 
                            min(50, combinations_count / 100) +  # 50
                            max(0, 20 - category_usage)  # 
                        )
                        
                        total_score += score
                        total_combinations += combinations_count
            
            if total_combinations > 0:
                category_scores[category] = {
                    'score': total_score,
                    'total_combinations': total_combinations,
                    'usage_count': category_usage,
                    'pattern_score': pattern_score,
                    'avg_score': total_score / len(binding_manager.binding_groups)
                }
        
        if not category_scores:
            # 
            # 如果所有分类都被排除，尝试清空无效集合重试（避免死锁）
            if invalid_categories and len(invalid_categories) == len(self.binding_categories):
                print(f"[预计算] ⚠️ 所有分类均被标记为无效，重置无效列表并随机选择")
                invalid_categories.clear()
                import random
                return random.choice(self.binding_categories)
            
            # 如果还有未被标记无效的分类，从剩余中随机选
            remaining_categories = [c for c in self.binding_categories if not invalid_categories or c not in invalid_categories]
            if remaining_categories:
                import random
                return random.choice(remaining_categories)
            
            return None
        
        # 
        sorted_categories = sorted(
            category_scores.items(),
            key=lambda x: x[1]['score'],
            reverse=True
        )
        
        # 3
        top_categories = sorted_categories[:min(3, len(sorted_categories))]
        weights = [item[1]['score'] for item in top_categories]
        
        # 
        import random
        selected_category = random.choices(
            [item[0] for item in top_categories],
            weights=weights,
            k=1
        )[0]
        
        # 
        selected_info = category_scores[selected_category]
        print(f"[] : {selected_category}, : {selected_info['score']:.1f}, : {selected_info['total_combinations']}, : {selected_info['usage_count']}, : {selected_info['pattern_score']:.2f}")
        
        return selected_category

    def _generate_smart_category_sequence(self, count: int) -> List[str]:
        """"""
        if not self.binding_categories:
            return []

        import random

        # 
        if count <= len(self.binding_categories):
            categories = self.binding_categories.copy()
            random.shuffle(categories)
            return categories[:count]

        # 
        print(f"[] : {count} , {len(self.binding_categories)} ")

        # 
        base_count = count // len(self.binding_categories)
        extra_count = count % len(self.binding_categories)

        # 
        category_distribution = {}
        for i, category in enumerate(self.binding_categories):
            category_distribution[category] = base_count + (1 if i < extra_count else 0)

        print(f"[] : {category_distribution}")

        # 
        sequence = []

        # 
        category_pool = []
        for category, freq in category_distribution.items():
            category_pool.extend([category] * freq)

        # 
        sequence = self._smart_shuffle_categories(category_pool)

        print(f"[] : {sequence[:10]}{'...' if len(sequence) > 10 else ''}")

        return sequence

    def _smart_shuffle_categories(self, category_pool: List[str]) -> List[str]:
        """"""
        import random

        if len(category_pool) <= 1:
            return category_pool

        # 
        best_sequence = None
        best_score = float('inf')

        for attempt in range(10):  # 10
            sequence = category_pool.copy()
            random.shuffle(sequence)

            # 
            score = self._calculate_adjacency_score(sequence)

            if score < best_score:
                best_score = score
                best_sequence = sequence.copy()

                # 
                if score == 0:
                    break

        # 
        if best_score > 0:
            best_sequence = self._optimize_sequence(best_sequence)

        return best_sequence

    def _calculate_adjacency_score(self, sequence: List[str]) -> int:
        """"""
        score = 0
        for i in range(len(sequence) - 1):
            if sequence[i] == sequence[i + 1]:
                score += 1
        return score

    def _optimize_sequence(self, sequence: List[str]) -> List[str]:
        """"""
        sequence = sequence.copy()

        # 
        for _ in range(5):
            improved = False

            # 
            for i in range(len(sequence) - 1):
                if sequence[i] == sequence[i + 1]:
                    # 
                    for j in range(i + 2, len(sequence)):
                        if sequence[j] != sequence[i] and sequence[j] != sequence[i - 1] if i > 0 else True:
                            # 
                            sequence[i + 1], sequence[j] = sequence[j], sequence[i + 1]
                            improved = True
                            break

                    if improved:
                        break

            if not improved:
                break

        return sequence

    def _analyze_category_types(self) -> dict:
        """"""
        category_types = {}

        if not hasattr(self, 'binding_categories'):
            return category_types

        # 
        for category in self.binding_categories:
            # 
            category_lower = category.lower()

            if 'person' in category_lower or 'character' in category_lower or 'figure' in category_lower:
                category_types[category] = 'person'
            elif 'background' in category_lower or 'bg' in category_lower or 'scene' in category_lower:
                category_types[category] = 'background'
            elif 'object' in category_lower or 'item' in category_lower or 'prop' in category_lower:
                category_types[category] = 'object'
            else:
                # 
                category_types[category] = self._infer_category_type_from_files(category)

        print(f"[] : {category_types}")
        return category_types

    def _infer_category_type_from_files(self, category: str) -> str:
        """"""
        # 
        # 
        return 'general'

    def _generate_smart_category_sequence_by_type(self, count: int, category_types: dict) -> List[str]:
        """"""
        if not self.binding_categories:
            return []

        import random

        #  
        base_category_groups = {}
        for category in self.binding_categories:
            # 
            if '_' in category:
                base_category = category.split('_')[-1]  # 
            else:
                base_category = category

            if base_category not in base_category_groups:
                base_category_groups[base_category] = []
            base_category_groups[base_category].append(category)

        print(f"[] : {base_category_groups}")

        # 
        if count <= len(self.binding_categories):
            return self._generate_alternating_base_categories(count, base_category_groups)

        # 
        sequence = []

        # 
        base_categories = list(base_category_groups.keys())
        base_count_per_base = count // len(base_categories)
        extra_count = count % len(base_categories)

        # 
        base_category_counts = {}
        for i, base_category in enumerate(base_categories):
            base_category_counts[base_category] = base_count_per_base + (1 if i < extra_count else 0)

        print(f"[] : {base_category_counts}")

        # 
        base_category_pool = []
        for base_category, freq in base_category_counts.items():
            base_category_pool.extend([base_category] * freq)

        # 
        base_sequence = self._smart_shuffle_base_categories(base_category_pool)

        #  
        sequence = []
        base_category_indices = {base: 0 for base in base_categories}

        # 
        base_category_cycles = {}
        for base_category, categories in base_category_groups.items():
            # 
            cycle_length = max(base_category_counts[base_category], len(categories))
            cycle_sequence = []
            for i in range(cycle_length):
                cycle_sequence.append(categories[i % len(categories)])
            # 
            random.shuffle(cycle_sequence)
            base_category_cycles[base_category] = cycle_sequence

        for base_category in base_sequence:
            #  
            cycle_sequence = base_category_cycles[base_category]
            current_index = base_category_indices[base_category]
            selected_category = cycle_sequence[current_index % len(cycle_sequence)]
            sequence.append(selected_category)
            base_category_indices[base_category] += 1

        print(f"[] : {sequence[:10]}{'...' if len(sequence) > 10 else ''}")

        return sequence

    def _generate_alternating_base_categories(self, count: int, base_category_groups: dict) -> List[str]:
        """"""
        import random

        base_categories = list(base_category_groups.keys())
        sequence = []

        for i in range(count):
            # 
            if i == 0:
                selected_base = random.choice(base_categories)
            else:
                last_category = sequence[-1]
                last_base = last_category.split('_')[-1] if '_' in last_category else last_category

                # 
                different_bases = [base for base in base_categories if base != last_base]
                if different_bases:
                    selected_base = random.choice(different_bases)
                else:
                    selected_base = random.choice(base_categories)

            # 
            available_categories = base_category_groups[selected_base]
            selected_category = random.choice(available_categories)
            sequence.append(selected_category)

        return sequence

    def _smart_shuffle_base_categories(self, base_category_pool: List[str]) -> List[str]:
        """"""
        import random

        if len(base_category_pool) <= 1:
            return base_category_pool

        # 
        best_sequence = None
        best_score = float('inf')

        for attempt in range(10):  # 10
            sequence = base_category_pool.copy()
            random.shuffle(sequence)

            # 
            score = self._calculate_adjacency_score(sequence)

            if score < best_score:
                best_score = score
                best_sequence = sequence.copy()

                # 
                if score == 0:
                    break

        # 
        if best_score > 0:
            best_sequence = self._optimize_base_category_sequence(best_sequence)

        return best_sequence

    def _optimize_base_category_sequence(self, sequence: List[str]) -> List[str]:
        """"""
        sequence = sequence.copy()

        # 
        for _ in range(5):
            improved = False

            # 
            for i in range(len(sequence) - 1):
                if sequence[i] == sequence[i + 1]:
                    # 
                    for j in range(i + 2, len(sequence)):
                        if (sequence[j] != sequence[i] and
                            (i == 0 or sequence[j] != sequence[i - 1]) and
                            (j == len(sequence) - 1 or sequence[i + 1] != sequence[j + 1])):
                            # 
                            sequence[i + 1], sequence[j] = sequence[j], sequence[i + 1]
                            improved = True
                            break

                    if improved:
                        break

            if not improved:
                break

        return sequence

    def _smart_shuffle_with_type_awareness(self, category_pool: List[str], category_types: dict) -> List[str]:
        """"""
        import random

        if len(category_pool) <= 1:
            return category_pool

        # 
        type_pools = {}
        for category in category_pool:
            category_type = category_types.get(category, 'general')
            if category_type not in type_pools:
                type_pools[category_type] = []
            type_pools[category_type].append(category)

        # 
        for type_name in type_pools:
            random.shuffle(type_pools[type_name])

        # 
        sequence = []
        type_names = list(type_pools.keys())
        type_indices = {type_name: 0 for type_name in type_names}

        while len(sequence) < len(category_pool):
            # 
            available_types = [t for t in type_names if type_indices[t] < len(type_pools[t])]

            if not available_types:
                break

            # 
            if len(sequence) > 0:
                last_category = sequence[-1]
                last_type = category_types.get(last_category, 'general')
                different_types = [t for t in available_types if t != last_type]

                if different_types:
                    selected_type = random.choice(different_types)
                else:
                    selected_type = random.choice(available_types)
            else:
                selected_type = random.choice(available_types)

            # 
            category = type_pools[selected_type][type_indices[selected_type]]
            sequence.append(category)
            type_indices[selected_type] += 1

        return sequence

    def _generate_random_combinations(self, count: int, avoid_duplicates: bool) -> List[LayerCombination]:
        """ -  """
        print(f"[] ")

        combinations = []
        seen_hashes = set() if avoid_duplicates else None
        max_attempts = count * 30  #  
        attempts = 0

        import random
        import time
        import hashlib

        # 
        global_manager = self._get_avoid_repeat_manager()

        #  
        optimized_pools = global_manager.optimize_image_pools(self.layer_image_pools)
        print(f"[]  {count} ")

        while len(combinations) < count and attempts < max_attempts:
            attempts += 1

            #  
            if attempts % 5 == 0:  # 5
                layer_states = global_manager.get_diverse_combination(optimized_pools)
                print(f"[]  ( {attempts})")
            else:
                # 
                layer_states = {}
                for layer_idx, image_pool in optimized_pools.items():
                    if image_pool:
                        #  30%
                        priority_count = max(1, int(len(image_pool) * 0.3))
                        selected_image = random.choice(image_pool[:priority_count])
                        layer_states[layer_idx] = selected_image

            if not layer_states:
                continue

            # 
            layer_clone_settings = {}
            combination_parts = []
            combination_files = []

            for layer_idx, file_path in layer_states.items():
                #  ++
                timestamp = int(time.time() * 1000000) % 1000000
                random_factor1 = random.randint(10000, 99999)
                random_factor2 = random.randint(100000, 999999)
                attempt_factor = attempts * 1000 + random.randint(1, 999)
                combination_parts.append(f"L{layer_idx}:{file_path}:{timestamp}:{random_factor1}:{random_factor2}:{attempt_factor}")
                combination_files.append(file_path)

                # 
                if layer_idx < len(self.visible_layers):
                    layer = self.visible_layers[layer_idx]
                    clone_settings = self._capture_clone_settings(layer)
                    layer_clone_settings[layer_idx] = clone_settings

            # 
            combination_str = "|".join(combination_parts)
            combination_hash = hashlib.md5(combination_str.encode()).hexdigest()[:12]

            # 
            if avoid_duplicates and seen_hashes is not None and combination_hash in seen_hashes:
                self.stats['duplicates_avoided'] += 1
                print(f"[] : {combination_hash}")
                continue

            if seen_hashes is not None:
                seen_hashes.add(combination_hash)

            # 
            combination = LayerCombination(
                index=len(combinations),
                layer_states=layer_states,
                layer_clone_settings=layer_clone_settings,
                combination_hash=combination_hash,
                is_unique=True
            )

            combinations.append(combination)
            print(f"[]  {len(combinations)}/{count}: {combination_hash}")
            self.stats['combinations_generated'] += 1

            #  
            global_manager.record_combination_usage(combination_files)

        if len(combinations) < count:
            print(f"[]  {len(combinations)}  {count} ")
            print(f"[] : {attempts}, : {self.stats['duplicates_avoided']}")

        return combinations

    def _generate_exhaustive_combinations(self, count: int) -> List[LayerCombination]:
        """生成穷举组合（遍历模式），仅按需生成 count 个不重复组合"""
        print(f"[] ")

        import itertools

        layer_pools = []
        layer_indices = []

        for layer_idx in sorted(self.layer_image_pools.keys()):
            image_pool = self.layer_image_pools[layer_idx]
            if image_pool:
                unique_pool = list(dict.fromkeys(image_pool))
                layer_pools.append(unique_pool)
                layer_indices.append(layer_idx)

        if not layer_pools:
            return []

        # 仅迭代前 count 个笛卡尔组合，避免全量列表化
        print(f"[]  (count={count})")
        product_iter = itertools.product(*layer_pools)
        limited_iter = itertools.islice(product_iter, count)

        combinations = []
        for i, combo_tuple in enumerate(limited_iter):
            layer_states = {}
            layer_clone_settings = {}

            for j, selected_image in enumerate(combo_tuple):
                layer_idx = layer_indices[j]
                layer_states[layer_idx] = selected_image

                if layer_idx < len(self.visible_layers):
                    layer = self.visible_layers[layer_idx]
                    clone_settings = self._capture_clone_settings(layer)
                    layer_clone_settings[layer_idx] = clone_settings

            combination_hash = self._generate_deterministic_hash(layer_states)

            combination = LayerCombination(
                index=i,
                layer_states=layer_states,
                layer_clone_settings=layer_clone_settings,
                combination_hash=combination_hash,
                is_unique=True
            )

            combinations.append(combination)
            self.stats['combinations_generated'] += 1

        print(f"[]  {len(combinations)} ")
        return combinations

    def precompute_filenames(self, combinations: List[LayerCombination],
                           filename_template: str, directory: str, 
                           file_format: str, start_index: int = 1) -> List[ExportTask]:
        """"""
        print("[] ...")
        
        tasks = []
        
        # 
        clean_template = self._sanitize_filename_template(filename_template)
        
        for i, combination in enumerate(combinations):
            file_number = start_index + i
            
            # 
            filename = self._process_filename_template(
                clean_template, combination, file_number, len(combinations)
            )
            
            # 
            if not filename.lower().endswith(f'.{file_format}'):
                filename += f'.{file_format}'
            
            file_path = os.path.join(directory, filename)
            
            # 
            task = ExportTask(
                combination=combination,
                filename=filename,
                file_path=file_path,
                file_number=file_number
            )
            
            tasks.append(task)
        
        print(f"[]  {len(tasks)} ")
        return tasks
    
    def create_export_plan(self, directory: str, count: int,
                          filename_template: str = "image_{number:04d}",
                          file_format: str = "png", start_index: int = 1,
                          avoid_duplicates: bool = True,
                          traverse_mode: bool = False) -> PrecomputedExportPlan:
        """"""
        start_time = time.time()

        #  
        self._clear_all_caches()

        print(f"[] : {count} ")
        
        # 1. 
        total_possible = self.analyze_document()
        
        # 2. 生成组合
        if traverse_mode:
            combinations = self._generate_exhaustive_combinations(count)
        else:
            combinations = self.generate_smart_combinations(count, avoid_duplicates)
        
        # 3. 
        tasks = self.precompute_filenames(
            combinations, filename_template, directory, file_format, start_index
        )
        
        # 4. 
        estimated_time = self._estimate_export_time(len(tasks))
        memory_requirement = self._estimate_memory_requirement(len(tasks))
        suggestions = self._generate_optimization_suggestions(len(tasks), total_possible)
        
        # 5. 
        plan = PrecomputedExportPlan(
            tasks=tasks,
            total_count=len(tasks),
            unique_combinations=len(set(t.combination.combination_hash for t in tasks)),
            estimated_time=estimated_time,
            memory_requirement_mb=memory_requirement,
            optimization_suggestions=suggestions
        )
        
        self.stats['precompute_time'] = time.time() - start_time
        
        print(f"[] :")
        print(f"  - : {plan.total_count}")
        print(f"  - : {plan.unique_combinations}")
        print(f"  - : {plan.estimated_time:.1f}")
        print(f"  - : {plan.memory_requirement_mb:.1f}MB")
        print(f"  - : {self.stats['precompute_time']:.3f}")
        
        return plan
    
    def _sanitize_filename_template(self, template: str) -> str:
        """"""
        if template in self.filename_cache:
            self.stats['cache_hits'] += 1
            return self.filename_cache[template]
        
        # 
        illegal_chars = '<>:"/\\|?*'
        clean_template = template
        for char in illegal_chars:
            clean_template = clean_template.replace(char, '_')
        
        self.filename_cache[template] = clean_template
        return clean_template
    
    def _process_filename_template(self, template: str, combination: LayerCombination, 
                                 file_number: int, total_count: int) -> str:
        """"""
        result = template
        
        # 
        number_pattern = r'\{number(?::([^}]+))?\}'
        def replace_number(match):
            format_spec = match.group(1)
            if format_spec:
                try:
                    return format(file_number, format_spec)
                except:
                    return str(file_number)
            return str(file_number)

        result = re.sub(number_pattern, replace_number, result)

        #  {number_d} -> {number:d}
        result = result.replace("{number_d}", str(file_number))
        result = result.replace("{number_04d}", f"{file_number:04d}")
        result = result.replace("{number_03d}", f"{file_number:03d}")
        result = result.replace("{number_02d}", f"{file_number:02d}")

        # 
        result = result.replace("{index}", str(file_number))
        result = result.replace("{count}", str(total_count))
        result = result.replace("{combo}", combination.combination_hash)
        
        # 
        layer_names = []
        layer_names_by_index = {}

        # 
        for layer_idx, image_path in combination.layer_states.items():
            if image_path:
                basename = os.path.basename(image_path)
                name = os.path.splitext(basename)[0]
                clean_name = self._clean_filename(name)
                layer_names.append(clean_name)
                layer_names_by_index[layer_idx] = clean_name

        # 
        if "{layer}" in result:
            first_layer = layer_names[0] if layer_names else "layer"
            result = result.replace("{layer}", first_layer)

        if "{layers}" in result:
            layers_str = "_".join(layer_names[:3])  # 3
            result = result.replace("{layers}", layers_str)

        #  {layer_0}, {layer_1}, {layer_2} 
        layer_index_pattern = r'\{layer_(\d+)\}'
        def replace_layer_index(match):
            index = int(match.group(1))
            if index in layer_names_by_index:
                return layer_names_by_index[index]
            elif index < len(layer_names):
                return layer_names[index]
            else:
                return f"layer_{index}"

        result = re.sub(layer_index_pattern, replace_layer_index, result)
        
        return result
    
    def _clean_filename(self, filename: str) -> str:
        """"""
        # 
        cleaned = re.sub(r'[_\-]\d+$', '', filename)
        cleaned = re.sub(r'[_\-](copy|)$', '', cleaned, flags=re.IGNORECASE)
        return cleaned[:50]  # 
    
    def _estimate_export_time(self, task_count: int) -> float:
        """"""
        # 
        base_time_per_image = 0.1  # 
        
        # 
        canvas_pixels = self.document.canvas_width * self.document.canvas_height
        size_factor = canvas_pixels / (1920 * 1080)  # 1080p
        
        # 
        layer_factor = len(self.visible_layers) / 5  # 5
        
        adjusted_time = base_time_per_image * size_factor * layer_factor
        return task_count * adjusted_time
    
    def _estimate_memory_requirement(self, task_count: int) -> float:
        """"""
        #  (RGBA)
        single_image_mb = (self.document.canvas_width * self.document.canvas_height * 4) / (1024 * 1024)
        
        # 
        parallel_factor = min(4, task_count)  # 4
        cache_factor = 1.5  # 
        
        return single_image_mb * parallel_factor * cache_factor
    
    def _generate_optimization_suggestions(self, task_count: int, total_possible: int) -> List[str]:
        """"""
        suggestions = []
        
        if task_count > total_possible:
            suggestions.append(f"({task_count})({total_possible})")
        
        if task_count > 100:
            suggestions.append("")
        
        if len(self.visible_layers) > 10:
            suggestions.append("GPU")
        
        return suggestions

    def _capture_clone_settings(self, layer) -> Dict:
        """"""
        clone_settings = {}

        # 
        if hasattr(layer, 'clone_enabled'):
            clone_settings['clone_enabled'] = layer.clone_enabled
        elif hasattr(layer, '_clone_enabled'):
            clone_settings['clone_enabled'] = layer._clone_enabled
        else:
            clone_settings['clone_enabled'] = False

        if hasattr(layer, 'clone_rows'):
            clone_settings['clone_rows'] = layer.clone_rows
        elif hasattr(layer, '_clone_rows'):
            clone_settings['clone_rows'] = layer._clone_rows
        else:
            clone_settings['clone_rows'] = 1

        if hasattr(layer, 'clone_columns'):
            clone_settings['clone_columns'] = layer.clone_columns
        elif hasattr(layer, '_clone_columns'):
            clone_settings['clone_columns'] = layer._clone_columns
        else:
            clone_settings['clone_columns'] = 1

        if hasattr(layer, 'clone_row_spacing'):
            clone_settings['clone_row_spacing'] = layer.clone_row_spacing
        elif hasattr(layer, '_clone_row_spacing'):
            clone_settings['clone_row_spacing'] = layer._clone_row_spacing
        else:
            clone_settings['clone_row_spacing'] = 0

        if hasattr(layer, 'clone_column_spacing'):
            clone_settings['clone_column_spacing'] = layer.clone_column_spacing
        elif hasattr(layer, '_clone_column_spacing'):
            clone_settings['clone_column_spacing'] = layer._clone_column_spacing
        else:
            clone_settings['clone_column_spacing'] = 0

        return clone_settings


def get_batch_precomputer_v2(document, document_analysis: dict) -> 'BatchExportPrecomputerV2':
    """V2 - """
    print("[V2] ")
    return BatchExportPrecomputerV2(document, document_analysis)


# 向后兼容：V2 实现已拆分到独立模块，这里重新导出以保持公开 API 不变
from app.utils.batch_export_precomputer_v2 import BatchExportPrecomputerV2

__all__ = [
    'LayerCombination',
    'ExportTask',
    'PrecomputedExportPlan',
    'BatchExportPrecomputer',
    'BatchExportPrecomputerV2',
    'get_batch_precomputer_v2',
]
