#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全局图像组合避重管理器
确保在所有情况下都能避免使用相同的图片组合，无论是否使用绑定组
"""


import os as _os
_BTPW_VERBOSE = _os.environ.get("BTPW_VERBOSE_LOG", "0").strip().lower() in ("1", "true", "yes", "on")
_ALWAYS_PRINT_KW = ("[ERROR]", "[CRITICAL]", "[严重错误]", "错误", "失败", "Exception", "Traceback", "[WARNING]")
def print(*args, **kwargs):
    if _BTPW_VERBOSE:
        __builtins__["print"](*args, **kwargs)
        return
    try:
        msg = " ".join(str(a) for a in args)
    except Exception:
        msg = ""
    if any(kw in msg for kw in _ALWAYS_PRINT_KW):
        __builtins__["print"](*args, **kwargs)

import os
import hashlib
import time
import random
import json
import threading
import re
from typing import Dict, List, Set, Tuple, Optional, Union, Any, Callable
from collections import defaultdict, Counter


class GlobalAvoidRepeatManager:
    """图像组合避重管理器。

    默认仍保留全局实例；批量导出可传入 scope_key，按文档隔离避重历史。
    """
    _instance = None
    _instances = {}
    _lock = threading.Lock()
    
    # 🚀 性能优化：日志级别控制（默认关闭详细日志）
    VERBOSE_LOGGING = False  # 设为True启用详细日志（调试用）
    MAX_SIMILARITY_FILTER_POOL_SIZE = 80
    ENABLE_SIMILARITY_FILTER_DEFAULT = False
    
    def __new__(cls, scope_key: Optional[str] = None):
        scope = str(scope_key or "global")
        with cls._lock:
            if scope not in cls._instances:
                instance = super(GlobalAvoidRepeatManager, cls).__new__(cls)
                instance._scope_key = scope
                cls._instances[scope] = instance
                if scope == "global":
                    cls._instance = instance
            return cls._instances[scope]
    
    def __init__(self, scope_key: Optional[str] = None):
        if getattr(self, "_initialized", False):
            return
            
        self._initialized = True
        self.scope_key = getattr(self, "_scope_key", str(scope_key or "global"))
        self.image_usage_history = {}  # 图像使用历史：{图像路径: 使用次数}
        self.combination_history = {}  # 组合使用历史：{组合哈希: 使用次数}
        self.recent_combinations = []  # 最近使用的组合哈希列表
        self.image_similarity_cache = {}  # 图像相似度缓存：{(img1, img2): 相似度}
        self.max_recent_combinations = 100  # 最近组合记录的最大数量
        self.max_history_size = 10000  # 历史记录的最大数量
        self.similarity_threshold = 0.8  # 图像相似度阈值，高于此值被视为相似
        self.persistence_path = None  # 持久化存储路径
        
        # 🚀 增强功能：绑定组特定的组合管理
        self.binding_group_combinations = {}  # {group_id: {category: [组合哈希列表]}}
        self.binding_group_usage = {}  # {group_id: {category: {组合哈希: 使用次数}}}
        self.category_recent_combinations = {}  # {group_id_category: [最近使用的组合哈希]}
        
        # 🚀 性能优化：延迟保存标记
        self._pending_save = False
        self._last_save_time = time.time()
        
        # 尝试加载历史记录
        self._load_history()
        
        if self.VERBOSE_LOGGING:
            print("[全局避重] 全局图像组合避重管理器初始化完成")
    
    def set_persistence_path(self, path: str):
        """设置持久化存储路径"""
        self.persistence_path = path
        
        # 尝试加载历史记录
        self._load_history()
    
    def _load_history(self):
        """加载历史记录"""
        if not self.persistence_path:
            # 尝试使用默认路径
            app_data_path = os.path.expanduser("~/.batch_image_processor")
            if not os.path.exists(app_data_path):
                try:
                    os.makedirs(app_data_path)
                except Exception as e:
                    print(f"[全局避重] 无法创建数据目录: {e}")
                    return
            
            if self.scope_key == "global":
                filename = "avoid_repeat_history.json"
            else:
                safe_scope = re.sub(r"[^A-Za-z0-9_.-]+", "_", self.scope_key).strip("_")[:120] or "document"
                filename = f"avoid_repeat_history_{safe_scope}.json"
            self.persistence_path = os.path.join(app_data_path, filename)
        
        if os.path.exists(self.persistence_path):
            try:
                with open(self.persistence_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    
                    # 加载图像使用历史
                    if 'image_usage_history' in data:
                        self.image_usage_history = data['image_usage_history']
                        
                    # 加载组合使用历史
                    if 'combination_history' in data:
                        self.combination_history = data['combination_history']
                    
                    # 加载最近组合
                    if 'recent_combinations' in data:
                        self.recent_combinations = data['recent_combinations']
                    
                    # 🚀 加载绑定组相关数据
                    if 'binding_group_combinations' in data:
                        self.binding_group_combinations = data['binding_group_combinations']
                    if 'binding_group_usage' in data:
                        self.binding_group_usage = data['binding_group_usage']
                    if 'category_recent_combinations' in data:
                        self.category_recent_combinations = data['category_recent_combinations']
                        
                    if self.VERBOSE_LOGGING:
                        print(f"[全局避重] 成功加载历史: {len(self.image_usage_history)} 图像, {len(self.combination_history)} 组合")
            except Exception as e:
                if self.VERBOSE_LOGGING:
                    print(f"[全局避重] ❌ 加载失败: {e}")
    
    def _save_history(self):
        """保存历史记录 - 性能优化版"""
        if not self.persistence_path:
            return
            
        try:
            # 清理过大的历史记录
            self._cleanup_history()
            
            # 准备保存的数据
            data = {
                'image_usage_history': self.image_usage_history,
                'combination_history': self.combination_history,
                'recent_combinations': self.recent_combinations,
                'binding_group_combinations': self.binding_group_combinations,
                'binding_group_usage': self.binding_group_usage,
                'category_recent_combinations': self.category_recent_combinations
            }
            
            # 保存到文件
            with open(self.persistence_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # 重置保存标记
            self._pending_save = False
            self._last_save_time = time.time()
                
            if self.VERBOSE_LOGGING:
                print(f"[全局避重] 历史记录已保存: {self.persistence_path}")
        except Exception as e:
            print(f"[全局避重] ❌ 保存失败: {e}")
    
    def force_save_if_needed(self):
        """如果有待保存的数据，则强制保存 - 性能优化版"""
        if self._pending_save:
            self._save_history()
            if self.VERBOSE_LOGGING:
                print(f"[全局避重] ✅ 批量保存完成")
    
    def _cleanup_history(self):
        """清理历史记录，保持合理大小"""
        # 清理图像使用历史
        if len(self.image_usage_history) > self.max_history_size:
            # 保留使用次数最多的图像记录
            sorted_images = sorted(self.image_usage_history.items(), key=lambda x: x[1], reverse=True)
            keep_count = int(self.max_history_size * 0.8)  # 保留80%
            self.image_usage_history = dict(sorted_images[:keep_count])
            print(f"[全局避重] 清理图像历史记录, 保留 {keep_count} 条记录")
        
        # 清理组合使用历史
        if len(self.combination_history) > self.max_history_size:
            # 保留使用次数最多的组合记录
            sorted_combos = sorted(self.combination_history.items(), key=lambda x: x[1], reverse=True)
            keep_count = int(self.max_history_size * 0.8)  # 保留80%
            self.combination_history = dict(sorted_combos[:keep_count])
            print(f"[全局避重] 清理组合历史记录, 保留 {keep_count} 条记录")
        
        # 清理最近组合记录
        if len(self.recent_combinations) > self.max_recent_combinations:
            # 保留最近的记录
            self.recent_combinations = self.recent_combinations[-self.max_recent_combinations:]
        
        # 🚀 清理绑定组相关记录
        for group_id in list(self.binding_group_usage.keys()):
            for category in list(self.binding_group_usage[group_id].keys()):
                usage_data = self.binding_group_usage[group_id][category]
                if len(usage_data) > self.max_history_size // 10:  # 每个分类最多保留1000条记录
                    # 保留使用次数最多的记录
                    sorted_usage = sorted(usage_data.items(), key=lambda x: x[1], reverse=True)
                    keep_count = self.max_history_size // 20
                    self.binding_group_usage[group_id][category] = dict(sorted_usage[:keep_count])
        
        # 清理分类最近组合记录
        for category_key in self.category_recent_combinations:
            if len(self.category_recent_combinations[category_key]) > 50:
                self.category_recent_combinations[category_key] = \
                    self.category_recent_combinations[category_key][-50:]
    
    def generate_combination_hash(self, file_paths: List[str]) -> str:
        """生成文件组合的唯一哈希值"""
        # 过滤掉None和空字符串，使用文件名（不含路径）生成哈希，确保相同组合总是产生相同哈希
        valid_paths = [path for path in file_paths if path and isinstance(path, str)]
        if not valid_paths:
            return "empty_combination"
        file_names = [os.path.basename(path) for path in sorted(valid_paths)]
        combination_str = '|'.join(file_names)
        return hashlib.md5(combination_str.encode()).hexdigest()[:16]
    
    def is_combination_fresh(self, file_paths: List[str]) -> bool:
        """检查组合是否是全新的（从未使用过）"""
        combo_hash = self.generate_combination_hash(file_paths)
        return combo_hash not in self.combination_history
    
    def get_combination_usage_count(self, file_paths: List[str]) -> int:
        """获取组合的使用次数"""
        combo_hash = self.generate_combination_hash(file_paths)
        return self.combination_history.get(combo_hash, 0)
    
    def is_combination_recent(self, file_paths: List[str]) -> bool:
        """检查组合是否是最近使用过的"""
        combo_hash = self.generate_combination_hash(file_paths)
        return combo_hash in self.recent_combinations
    
    def record_combination_usage(self, file_paths: List[str]):
        """记录组合使用情况 - 性能优化版：减少日志，延迟保存"""
        try:
            if not file_paths:
                if self.VERBOSE_LOGGING:
                    print(f"[全局避重] ⚠️ 警告：尝试记录空组合")
                return
                
            # 生成组合哈希
            combo_hash = self.generate_combination_hash(file_paths)
            
            # 记录组合使用
            old_count = self.combination_history.get(combo_hash, 0)
            self.combination_history[combo_hash] = old_count + 1
            
            # 📊 只在检测到重复时输出警告
            if old_count > 0 and self.VERBOSE_LOGGING:
                print(f"[全局避重] ⚠️ 重复: {combo_hash[:8]}, 次数={old_count + 1}")
            
            # 记录到最近使用列表
            if combo_hash in self.recent_combinations:
                self.recent_combinations.remove(combo_hash)
            self.recent_combinations.append(combo_hash)
            
            # 记录各图像使用
            for file_path in file_paths:
                if file_path:
                    self.image_usage_history[file_path] = self.image_usage_history.get(file_path, 0) + 1
            
            # 🚀 性能优化：不再实时保存，改为批量保存
            self._pending_save = True
            # self._save_history()  # ❌ 移除实时保存，严重影响性能
            
        except Exception as e:
            if self.VERBOSE_LOGGING:
                print(f"[全局避重] ❌ 记录失败: {e}")
            # 不抛出异常，避免影响批量导出进程
    
    def get_image_usage_count(self, file_path: str) -> int:
        """获取图像的使用次数"""
        return self.image_usage_history.get(file_path, 0)
    
    def get_least_used_images(self, image_pool: List[str], count: int = 1) -> List[str]:
        """获取使用次数最少的图像"""
        if not image_pool:
            return []
            
        count = max(1, min(int(count), len(image_pool)))
        # 按使用次数排序（先看次数，再看路径，保证结果稳定可复现）
        image_usage = [(img, self.get_image_usage_count(img)) for img in image_pool]
        image_usage.sort(key=lambda x: (x[1], str(x[0])))

        # 关键修复：同使用次数时不要总取固定前几个，避免视觉重复
        threshold_usage = image_usage[count - 1][1]
        tied_candidates = [img for img, usage in image_usage if usage <= threshold_usage]
        if len(tied_candidates) > count:
            random.shuffle(tied_candidates)
        return tied_candidates[:count]
    
    def get_diverse_combination(self, layer_pools: Dict[int, List[str]]) -> Dict[int, str]:
        """获取多样性最高的组合 - 性能优化版：简化日志"""
        if not layer_pools:
            if self.VERBOSE_LOGGING:
                print(f"[全局避重] ⚠️ 图层池为空")
            return {}
        
        if self.VERBOSE_LOGGING:
            print(f"[全局避重] 选择多样性组合，{len(layer_pools)} 层")
            
        # 尝试生成未使用过的组合
        max_attempts = 50
        for attempt in range(max_attempts):
            combination = {}
            combination_files = []
            
            # 为每个图层选择使用次数最少的图像
            for layer_idx, pool in layer_pools.items():
                if not pool:
                    continue
                    
                # 获取使用次数最少的3个图像（如果可能）
                candidate_count = min(3, len(pool))
                candidates = self.get_least_used_images(pool, candidate_count)
                
                # 随机选择一个
                selected = random.choice(candidates)
                combination[layer_idx] = selected
                combination_files.append(selected)
            
            # 检查是否是新组合
            if self.is_combination_fresh(combination_files):
                if self.VERBOSE_LOGGING:
                    file_names = [os.path.basename(f) for f in combination_files]
                    print(f"[全局避重] ✅ 全新组合 (尝试{attempt+1}): {file_names[:2]}...")
                return combination
                
            # 检查是否是最近使用过的组合
            if not self.is_combination_recent(combination_files):
                if self.VERBOSE_LOGGING:
                    print(f"[全局避重] ✅ 非最近组合 (尝试{attempt+1})")
                return combination
        
        # 如果无法找到理想的组合，使用使用次数最少的图像
        combination = {}
        for layer_idx, pool in layer_pools.items():
            if not pool:
                continue
                
            least_used = self.get_least_used_images(pool, 1)[0]
            combination[layer_idx] = least_used
        
        if self.VERBOSE_LOGGING:
            print(f"[全局避重] ⚠️ 回退到最少使用组合")
        return combination
    
    def calculate_image_similarity(self, img1_path: str, img2_path: str) -> float:
        """计算两张图像的相似度（0-1，1表示完全相同）"""
        # 检查缓存
        cache_key = tuple(sorted([img1_path, img2_path]))
        if cache_key in self.image_similarity_cache:
            return self.image_similarity_cache[cache_key]
            
        try:
            # 虚拟路径（如文字图层）或空路径不参与图像相似度比较
            if not img1_path or not img2_path:
                similarity = 0.0
                self.image_similarity_cache[cache_key] = similarity
                return similarity
            if str(img1_path).startswith("text_layer://") or str(img2_path).startswith("text_layer://"):
                similarity = 0.0
                self.image_similarity_cache[cache_key] = similarity
                return similarity
            if not os.path.isfile(img1_path) or not os.path.isfile(img2_path):
                similarity = 0.0
                self.image_similarity_cache[cache_key] = similarity
                return similarity

            # 首先比较文件大小，如果差异很大，可以快速判定为不相似
            size1 = os.path.getsize(img1_path)
            size2 = os.path.getsize(img2_path)
            
            size_ratio = min(size1, size2) / max(size1, size2)
            if size_ratio < 0.5:  # 如果大小差异超过一半，判定为不相似
                similarity = 0.0
                self.image_similarity_cache[cache_key] = similarity
                return similarity
                
            # 尝试导入并使用OpenCV进行相似度计算
            try:
                import cv2
                import numpy as np
                from PIL import Image

                def _read_image_unicode_safe(path: str):
                    """兼容 Windows 中文路径/UNC 的读图。"""
                    # 优先使用 numpy.fromfile + imdecode，避免 cv2.imread 中文路径失败
                    try:
                        data = np.fromfile(path, dtype=np.uint8)
                        if data.size > 0:
                            decoded = cv2.imdecode(data, cv2.IMREAD_COLOR)
                            if decoded is not None:
                                return decoded
                    except Exception:
                        pass
                    # 回退：PIL 读取后转 BGR
                    try:
                        with Image.open(path) as pil_img:
                            rgb = pil_img.convert("RGB")
                            arr = np.array(rgb)
                            return cv2.cvtColor(arr, cv2.COLOR_RGB2BGR)
                    except Exception:
                        return None
                
                # 读取图像
                img1 = _read_image_unicode_safe(img1_path)
                img2 = _read_image_unicode_safe(img2_path)
                
                # 如果无法读取图像，返回0
                if img1 is None or img2 is None:
                    similarity = 0.0
                    self.image_similarity_cache[cache_key] = similarity
                    return similarity
                
                # 调整大小以加速比较
                size = (64, 64)
                img1 = cv2.resize(img1, size)
                img2 = cv2.resize(img2, size)
                
                # 转换为灰度图
                gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
                gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
                
                # 计算直方图
                hist1 = cv2.calcHist([gray1], [0], None, [256], [0, 256])
                hist2 = cv2.calcHist([gray2], [0], None, [256], [0, 256])
                
                # 归一化直方图
                cv2.normalize(hist1, hist1, 0, 1, cv2.NORM_MINMAX)
                cv2.normalize(hist2, hist2, 0, 1, cv2.NORM_MINMAX)
                
                # 计算相似度
                similarity = cv2.compareHist(hist1, hist2, cv2.HISTCMP_CORREL)
                
                # 缓存结果
                self.image_similarity_cache[cache_key] = similarity
                return similarity
                
            except ImportError:
                # 如果没有OpenCV，使用简化方法
                similarity = 0.5 if os.path.basename(img1_path) == os.path.basename(img2_path) else 0.0
                self.image_similarity_cache[cache_key] = similarity
                return similarity
                
        except Exception as e:
            print(f"[全局避重] 计算图像相似度失败: {e}")
            self.image_similarity_cache[cache_key] = 0.0
            return 0.0
    
    def filter_similar_images(self, image_pool: List[str], max_similar_count: int = 2,
                              cancel_callback: Optional[Callable[[], bool]] = None) -> List[str]:
        """过滤掉相似的图像，保留多样性最高的子集"""
        if cancel_callback and cancel_callback():
            return image_pool

        if len(image_pool) <= max_similar_count:
            return image_pool

        if len(image_pool) > self.MAX_SIMILARITY_FILTER_POOL_SIZE:
            return image_pool
            
        # 计算图像之间的相似度
        similarity_groups = defaultdict(list)
        image_assignments = {}
        
        # 第一步：为每张图像分配一个初始组
        for i, img in enumerate(image_pool):
            similarity_groups[i].append(img)
            image_assignments[img] = i
        
        # 第二步：合并相似的组
        for i in range(len(image_pool)):
            if cancel_callback and cancel_callback():
                return image_pool
            for j in range(i + 1, len(image_pool)):
                if cancel_callback and cancel_callback():
                    return image_pool
                img1 = image_pool[i]
                img2 = image_pool[j]
                
                # 如果图像已经在同一组，跳过
                if image_assignments[img1] == image_assignments[img2]:
                    continue
                    
                # 计算相似度
                similarity = self.calculate_image_similarity(img1, img2)
                
                # 如果相似度超过阈值，合并组
                if similarity >= self.similarity_threshold:
                    group1 = image_assignments[img1]
                    group2 = image_assignments[img2]
                    
                    # 将group2的所有图像合并到group1
                    for img in similarity_groups[group2]:
                        similarity_groups[group1].append(img)
                        image_assignments[img] = group1
                    
                    # 清空group2
                    similarity_groups[group2] = []
        
        # 第三步：从每个组中选择使用次数最少的图像
        selected_images = []
        for group in similarity_groups.values():
            if not group:
                continue
                
            # 按使用次数排序
            group_usage = [(img, self.get_image_usage_count(img)) for img in group]
            group_usage.sort(key=lambda x: x[1])  # 按使用次数升序
            
            # 选择使用次数最少的前max_similar_count个
            for img, _ in group_usage[:max_similar_count]:
                if img not in selected_images:
                    selected_images.append(img)
        
        return selected_images
    
    def optimize_image_pools(self, layer_pools: Dict[int, List[str]],
                             cancel_callback: Optional[Callable[[], bool]] = None) -> Dict[int, List[str]]:
        """优化图层图像池，过滤相似图像并保持多样性"""
        optimized_pools = {}
        enable_similarity_filter = bool(self.ENABLE_SIMILARITY_FILTER_DEFAULT)
        try:
            env_val = str(os.environ.get("BTPW_ENABLE_SIMILARITY_FILTER", "") or "").strip().lower()
            if env_val in ("1", "true", "yes", "on"):
                enable_similarity_filter = True
            elif env_val in ("0", "false", "no", "off"):
                enable_similarity_filter = False
        except Exception:
            pass
        
        for layer_idx, pool in layer_pools.items():
            if cancel_callback and cancel_callback():
                return optimized_pools
            # 默认不做相似过滤，避免把 20 张素材压缩成少量候选导致导出重复感加重。
            # 如确需开启可通过环境变量 BTPW_ENABLE_SIMILARITY_FILTER=1。
            if enable_similarity_filter:
                optimized_pool = self.filter_similar_images(pool, cancel_callback=cancel_callback)
            else:
                optimized_pool = list(pool)
            
            # 按使用次数排序
            usage_sorted_pool = sorted(optimized_pool, key=lambda img: self.get_image_usage_count(img))
            
            optimized_pools[layer_idx] = usage_sorted_pool

            if self.VERBOSE_LOGGING:
                print(
                    f"[全局避重] 图层 {layer_idx} 池优化: {len(pool)} -> {len(optimized_pool)} 张图片 "
                    f"(相似过滤={'开' if enable_similarity_filter else '关'})"
                )
        
        return optimized_pools
    
    def get_diverse_binding_combination(self, group_id: str, category: str, 
                                      available_combinations: List[Dict[int, str]],
                                      layer_indices: List[int]) -> Optional[Dict[int, str]]:
        """🚀 为绑定组获取多样性最高的分类内组合
        
        Args:
            group_id: 绑定组ID
            category: 分类名称
            available_combinations: 该分类下所有可用的图片组合
            layer_indices: 图层索引列表
            
        Returns:
            选中的图片组合，如果没有合适的返回None
        """
        if not available_combinations:
            return None
        
        print(f"[绑定组避重] 为绑定组 {group_id} 分类 '{category}' 选择多样性组合，可选组合数: {len(available_combinations)}")
        
        # 初始化绑定组数据结构
        if group_id not in self.binding_group_combinations:
            self.binding_group_combinations[group_id] = {}
            self.binding_group_usage[group_id] = {}
        
        if category not in self.binding_group_combinations[group_id]:
            self.binding_group_combinations[group_id][category] = []
            self.binding_group_usage[group_id][category] = {}
        
        category_key = f"{group_id}_{category}"
        if category_key not in self.category_recent_combinations:
            self.category_recent_combinations[category_key] = []
        
        # 为所有组合生成哈希
        combination_hashes = []
        combination_map = {}
        for combo in available_combinations:
            file_paths = [combo[idx] for idx in sorted(combo.keys())]
            combo_hash = self.generate_combination_hash(file_paths)
            combination_hashes.append(combo_hash)
            combination_map[combo_hash] = combo
        
        # 🔧 分类组合：全新、已用但非最近、最近使用
        fresh_combinations = []  # 从未使用过的组合
        used_combinations = []   # 已使用但不是最近的组合
        recent_combinations = []  # 最近使用的组合
        
        category_usage = self.binding_group_usage[group_id][category]
        recent_hashes = set(self.category_recent_combinations[category_key][-10:])  # 最近10个
        
        for combo_hash in combination_hashes:
            combo = combination_map[combo_hash]
            
            if combo_hash not in category_usage:
                # 全新组合
                if combo_hash not in recent_hashes:
                    fresh_combinations.append((combo, combo_hash, 0))
                else:
                    recent_combinations.append((combo, combo_hash, 0))
            else:
                # 已使用组合
                usage_count = category_usage[combo_hash]
                if combo_hash not in recent_hashes:
                    used_combinations.append((combo, combo_hash, usage_count))
                else:
                    recent_combinations.append((combo, combo_hash, usage_count))
        
        print(f"[绑定组避重] 组合分类: 全新 {len(fresh_combinations)} 个, 已用非最近 {len(used_combinations)} 个, 最近 {len(recent_combinations)} 个")
        
        # 🎯 超级优化策略：智能均匀分布 + 轮转机制
        selected_combo = None
        selected_hash = None
        selected_usage = 0
        
        if fresh_combinations:
            # 🚀 策略1：优先选择全新组合，但引入轮转机制确保均匀使用
            if len(fresh_combinations) >= 5:  # 如果有足够多的全新组合，使用轮转策略
                # 根据当前已选择的组合数量决定轮转位置
                current_selections = len(self.binding_group_combinations.get(group_id, {}).get(category, []))
                rotation_index = current_selections % len(fresh_combinations)
                selected_combo, selected_hash, selected_usage = fresh_combinations[rotation_index]
                print(f"[绑定组避重] 使用轮转策略选择全新组合 (位置: {rotation_index})")
            else:
                # 全新组合不多时，随机选择
                selected_combo, selected_hash, selected_usage = random.choice(fresh_combinations)
                print(f"[绑定组避重] 随机选择全新组合")
        elif used_combinations:
            # 🚀 策略2：选择使用次数最少的已用组合，但引入均匀分布机制
            used_combinations.sort(key=lambda x: (x[2], random.random()))  # 按使用次数排序，同次数时随机
            min_usage = used_combinations[0][2]
            min_usage_combos = [combo for combo in used_combinations if combo[2] == min_usage]
            
            # 在使用次数最少的组合中进行智能选择
            if len(min_usage_combos) > 1:
                # 使用基于哈希的确定性选择，确保相同条件下选择一致但不同条件下多样化
                selection_seed = hash(f"{group_id}_{category}_{len(category_usage)}") % len(min_usage_combos)
                selected_combo, selected_hash, selected_usage = min_usage_combos[selection_seed]
                print(f"[绑定组避重] 智能选择最少使用组合 (使用次数: {selected_usage}, 选择种子: {selection_seed})")
            else:
                selected_combo, selected_hash, selected_usage = min_usage_combos[0]
                print(f"[绑定组避重] 选择唯一最少使用组合 (使用次数: {selected_usage})")
        elif recent_combinations:
            # 🚀 策略3：在最近使用的组合中选择使用次数最少的，但避免连续重复
            recent_combinations.sort(key=lambda x: (x[2], random.random()))
            
            # 尝试避免选择刚才使用的组合
            recent_list = self.category_recent_combinations.get(f"{group_id}_{category}", [])
            last_used = recent_list[-1] if recent_list else None
            
            # 优先选择不是最后使用的组合
            non_last_combos = [combo for combo in recent_combinations if combo[1] != last_used]
            if non_last_combos:
                selected_combo, selected_hash, selected_usage = non_last_combos[0]
                print(f"[绑定组避重] 选择非最后使用的最近组合 (使用次数: {selected_usage})")
            else:
                selected_combo, selected_hash, selected_usage = recent_combinations[0]
                print(f"[绑定组避重] 选择最近使用组合中次数最少的 (使用次数: {selected_usage})")
        
        if selected_combo is None or selected_hash is None:
            print(f"[绑定组避重] 警告：未能选择到合适的组合")
            return None
        
        # 记录使用情况
        self._record_binding_combination_usage(group_id, category, selected_hash, selected_combo)
        
        return selected_combo
    
    def _record_binding_combination_usage(self, group_id: str, category: str, 
                                        combo_hash: str, combination: Dict[int, str]):
        """记录绑定组组合使用情况"""
        try:
            # 更新分类内使用计数
            if group_id not in self.binding_group_usage:
                self.binding_group_usage[group_id] = {}
            if category not in self.binding_group_usage[group_id]:
                self.binding_group_usage[group_id][category] = {}
            
            self.binding_group_usage[group_id][category][combo_hash] = \
                self.binding_group_usage[group_id][category].get(combo_hash, 0) + 1
            
            # 更新分类最近使用列表
            category_key = f"{group_id}_{category}"
            if category_key not in self.category_recent_combinations:
                self.category_recent_combinations[category_key] = []
            
            recent_list = self.category_recent_combinations[category_key]
            if combo_hash in recent_list:
                recent_list.remove(combo_hash)
            recent_list.append(combo_hash)
            
            # 限制最近列表大小
            if len(recent_list) > 20:
                self.category_recent_combinations[category_key] = recent_list[-20:]
            
            # 记录单个图像使用
            file_paths = list(combination.values())
            for file_path in file_paths:
                if file_path:
                    self.image_usage_history[file_path] = self.image_usage_history.get(file_path, 0) + 1
            
            # 记录全局组合使用
            self.combination_history[combo_hash] = self.combination_history.get(combo_hash, 0) + 1
            
            # 更新全局最近组合
            if combo_hash in self.recent_combinations:
                self.recent_combinations.remove(combo_hash)
            self.recent_combinations.append(combo_hash)
            if len(self.recent_combinations) > self.max_recent_combinations:
                self.recent_combinations = self.recent_combinations[-self.max_recent_combinations:]
            
            usage_count = self.binding_group_usage[group_id][category].get(combo_hash, 0)
            file_names = [os.path.basename(fp) for fp in file_paths if fp]
            print(f"[绑定组避重] 记录组合使用: 组 {group_id} 分类 '{category}' 组合 {file_names} (分类内使用次数: {usage_count})")
            
        except Exception as e:
            print(f"[绑定组避重] 警告: 记录绑定组合使用失败: {e}")
            # 不抛出异常，避免影响批量导出进程
    
    def get_category_diversity_score(self, group_id: str, category: str) -> float:
        """获取分类的多样性评分 (0-1，1表示最高多样性)"""
        if group_id not in self.binding_group_usage or category not in self.binding_group_usage[group_id]:
            return 1.0  # 未使用过的分类具有最高多样性
        
        category_usage = self.binding_group_usage[group_id][category]
        if not category_usage:
            return 1.0
        
        # 计算使用分布的均匀性
        usage_counts = list(category_usage.values())
        total_usage = sum(usage_counts)
        max_usage = max(usage_counts)
        unique_combinations = len(usage_counts)
        
        # 多样性评分：考虑使用总数、最大使用次数、组合数量
        diversity_score = 1.0 / (1.0 + max_usage / max(1, unique_combinations))
        
        return diversity_score
    
    def get_binding_group_statistics(self, group_id: str) -> Dict[str, Any]:
        """获取绑定组的统计信息"""
        if group_id not in self.binding_group_usage:
            return {'categories': 0, 'total_combinations': 0, 'total_usage': 0}
        
        stats = {
            'categories': len(self.binding_group_usage[group_id]),
            'total_combinations': 0,
            'total_usage': 0,
            'category_stats': {}
        }
        
        for category, usage_data in self.binding_group_usage[group_id].items():
            category_combinations = len(usage_data)
            category_usage = sum(usage_data.values())
            diversity_score = self.get_category_diversity_score(group_id, category)
            
            stats['total_combinations'] += category_combinations
            stats['total_usage'] += category_usage
            
            stats['category_stats'][category] = {
                'combinations': category_combinations,
                'usage': category_usage,
                'diversity_score': diversity_score
            }
        
        return stats
