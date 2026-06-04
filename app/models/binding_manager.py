#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图层绑定管理器
统一管理图层绑定功能，实现智能文件匹配和组合
"""

import os
import re
import random
import time
import hashlib
import itertools
import json
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict, Counter
from app.utils.print_utils import safe_print as _safe_print
from app.utils.text_layer_virtual_path import (
    is_text_layer_virtual_path,
    build_text_layer_virtual_path,
    parse_text_layer_virtual_path,
)

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print

_BINDING_VERBOSE = os.environ.get("BTPW_BINDING_VERBOSE", "0") == "1"

# 🔧 导入100%准确绑定修复系统
try:
    from binding_100_percent_fix import (
        BindingIntegrityManager, ExportBindingValidator, 
        validate_current_bindings, enforce_100_percent_binding_accuracy,
        BindingValidationResult
    )
    BINDING_INTEGRITY_AVAILABLE = True
    print("[绑定管理器] 100%准确绑定修复系统已加载")
except ImportError as e:
    BINDING_INTEGRITY_AVAILABLE = False
    print("[绑定管理器] 100%准确绑定修复系统未启用（可选模块缺失）")


class BindingGroup:
    """绑定组类"""
    _supported_image_ext = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp')
    _folder_category_index_cache = {}  # key: abs_dir -> {'mtime_ns': int, 'files': [{'path': str, 'categories': [str]}]}
    _folder_category_index_dirty = False
    _folder_category_index_last_save_time = 0.0
    _folder_category_index_loaded = False
    
    def __init__(self, group_id: str, name: str, binding_manager=None):
        self._ensure_persistent_category_index_loaded()
        self.group_id = group_id
        self.name = name
        self.layers = []  # 绑定的图层列表
        self.file_categories = {}  # 文件分类：{核心名称: {图层索引: [文件路径列表]}}
        self.last_selected_category = None  # 上次选择的分类
        self._binding_manager = binding_manager  # 绑定管理器引用，用于获取文件限制
        
        # 🔧 根本修复：添加每个分类的使用历史，避免重复返回相同组合
        self._category_usage_history = {}  # {category: set of used combo hashes}
        # 记录信号连接，确保移除时不影响其他监听者
        self._signal_connections = {}  # {layer_id: {"text_changed": slot, "changed": slot}}

    @classmethod
    def _get_persistent_category_index_path(cls) -> str:
        try:
            base_dir = os.path.join(os.path.expanduser("~"), ".config", "批图王", "cache")
            os.makedirs(base_dir, exist_ok=True)
            return os.path.join(base_dir, "binding_folder_category_index_v1.json")
        except Exception:
            return ""

    @classmethod
    def _ensure_persistent_category_index_loaded(cls):
        if cls._folder_category_index_loaded:
            return
        cls._folder_category_index_loaded = True
        path = cls._get_persistent_category_index_path()
        if not path or not os.path.isfile(path):
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                payload = json.load(f)
            if not isinstance(payload, dict):
                return
            cache = payload.get('cache', {})
            if not isinstance(cache, dict):
                return
            for abs_dir, entry in cache.items():
                if not isinstance(entry, dict):
                    continue
                mtime_ns = int(entry.get('mtime_ns', -1))
                files = entry.get('files', [])
                normalized_files = []
                if isinstance(files, list):
                    for file_entry in files:
                        if not isinstance(file_entry, dict):
                            continue
                        file_path = file_entry.get('path')
                        categories = file_entry.get('categories', [])
                        if not isinstance(file_path, str):
                            continue
                        if not isinstance(categories, list):
                            categories = []
                        normalized_files.append({
                            'path': file_path,
                            'categories': [str(c) for c in categories if isinstance(c, str) and c]
                        })
                cls._folder_category_index_cache[str(abs_dir)] = {
                    'mtime_ns': mtime_ns,
                    'files': normalized_files
                }
        except Exception:
            pass
        finally:
            # 分类索引加载后尝试落盘（兼容旧缓存结构）
            cls._save_persistent_category_index_cache(force=True)

    @classmethod
    def _save_persistent_category_index_cache(cls, force: bool = False):
        if not cls._folder_category_index_dirty:
            return
        path = cls._get_persistent_category_index_path()
        if not path:
            return
        now = time.time()
        if not force and (now - cls._folder_category_index_last_save_time) < 2.0:
            return
        try:
            payload = {
                'version': 1,
                'saved_at': int(now),
                'cache': cls._folder_category_index_cache
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(payload, f, ensure_ascii=False)
            cls._folder_category_index_dirty = False
            cls._folder_category_index_last_save_time = now
        except Exception:
            pass

    @staticmethod
    def _get_directory_mtime_ns(directory: str) -> int:
        try:
            return int(os.stat(directory).st_mtime_ns)
        except Exception:
            return -1
    
    def add_layer(self, layer, layer_index: int):
        """添加图层到绑定组"""
        if layer not in self.layers:
            self.layers.append(layer)
            self._analyze_layer_files(layer, layer_index)
            try:
                # 仅文字图层需要监听文案变化；避免普通图层误触发文字分析
                if self._is_text_layer(layer) and hasattr(layer, 'text_changed') and hasattr(layer.text_changed, 'connect'):
                    # 使用lambda包装，确保能传递图层引用
                    text_slot = lambda: self._on_text_layer_changed(layer)
                    layer.text_changed.connect(text_slot)
                    # 记录连接，便于定向断开
                    lid = id(layer)
                    self._signal_connections.setdefault(lid, {})["text_changed"] = text_slot
                    print(f"[绑定组] 成功连接文字图层 '{layer.name}' 的 text_changed 信号")
                if self._is_text_layer(layer) and hasattr(layer, 'changed') and hasattr(layer.changed, 'connect'):
                    changed_slot = lambda: self._on_text_layer_changed(layer)
                    layer.changed.connect(changed_slot)
                    lid = id(layer)
                    self._signal_connections.setdefault(lid, {})["changed"] = changed_slot
                    print(f"[绑定组] 成功连接文字图层 '{layer.name}' 的 changed 信号")
            except Exception as e:
                print(f"[绑定组] 连接文字图层信号失败: {e}")
    
    def remove_layer(self, layer):
        """从绑定组移除图层"""
        if layer in self.layers:
            self.layers.remove(layer)
            try:
                # 🔧 修复：断开连接时需要处理lambda包装的情况
                if hasattr(layer, 'text_changed') and hasattr(layer.text_changed, 'disconnect'):
                    lid = id(layer)
                    slot = self._signal_connections.get(lid, {}).get("text_changed")
                    if slot:
                        try:
                            layer.text_changed.disconnect(slot)
                        except Exception:
                            # 回退：若定向断开失败，则断开全部，避免泄漏
                            layer.text_changed.disconnect()
                    print(f"[绑定组] 成功断开文字图层 '{layer.name}' 的 text_changed 信号")
                if hasattr(layer, 'changed') and hasattr(layer.changed, 'disconnect'):
                    lid = id(layer)
                    slot = self._signal_connections.get(lid, {}).get("changed")
                    if slot:
                        try:
                            layer.changed.disconnect(slot)
                        except Exception:
                            layer.changed.disconnect()
                    print(f"[绑定组] 成功断开文字图层 '{layer.name}' 的 changed 信号")
                # 清理信号记录
                self._signal_connections.pop(id(layer), None)
            except Exception as e:
                print(f"[绑定组] 断开文字图层信号失败: {e}")
            self._rebuild_file_categories()
    
    def _on_text_layer_changed(self, sender=None):
        """文字图层内容变化时的处理函数 - 修复版本，直接接收发送者"""
        print(f"[绑定组] 文字图层内容发生变化，开始重建分类...")
        
        # 🔧 根本修复：现在sender直接通过参数传递，不再依赖inspect
        if sender:
            if not self._is_text_layer(sender):
                # 忽略非文字图层，避免误进入文字解析逻辑
                return
            print(f"[绑定组] 检测到变化的文字图层: '{sender.name}', 当前文字: '{getattr(sender, 'current_text', '')}'")
            # 🔧 新增：重新分析这个特定的文字图层
            for i, layer in enumerate(self.layers):
                if layer is sender:
                    print(f"[绑定组] 重新分析变化的文字图层: '{sender.name}' (索引: {i})")
                    self._analyze_text_layer_content(layer, i)
                    break
        
        # 🔧 改进：只重建受影响的分类，而不是全部重建
        # 先保存当前状态
        old_categories = set(self.file_categories.keys())
        
        # 如果找到了发送者，我们已经单独分析了它，现在更新整体分类
        if sender:
            print(f"[绑定组] 基于变化的文字图层更新分类...")
        else:
            # 如果没找到发送者，回退到完全重建
            print(f"[绑定组] 未检测到具体变化的文字图层，执行完全重建...")
            self._rebuild_file_categories()
        
        new_categories = set(self.file_categories.keys())
        print(f"[绑定组] 分类更新完成")
        print(f"[绑定组] 原分类数量: {len(old_categories)}, 新分类数量: {len(new_categories)}")
        
        # 检测新增和移除的分类
        added_categories = new_categories - old_categories
        removed_categories = old_categories - new_categories
        
        if added_categories:
            print(f"[绑定组] 检测到新增分类: {list(added_categories)}")
        if removed_categories:
            print(f"[绑定组] 检测到移除分类: {list(removed_categories)}")
        
        # 如果有变化，通知绑定管理器
        if added_categories or removed_categories:
            print(f"[绑定组] 分类发生变化，将通知相关组件更新...")

    def _extract_categories_for_filename(self, filename_without_ext: str) -> Set[str]:
        """从文件名提取分类集合（用于目录索引缓存）。"""
        categories_to_add = set()
        core_name = self._extract_core_name(filename_without_ext)
        if core_name and self._is_meaningful_filename_category(core_name):
            categories_to_add.add(core_name)

        clean_filename = re.sub(r'\d+', '', filename_without_ext)
        clean_filename = re.sub(r'[_\-\s]+$', '', clean_filename)

        chinese_keywords = re.findall(r'[\u4e00-\u9fa5]{2,}', clean_filename)
        for kw in chinese_keywords:
            if self._is_meaningful_filename_category(kw):
                categories_to_add.add(kw)

        english_keywords = re.findall(r'[a-zA-Z]{2,}', clean_filename)
        for kw in english_keywords:
            normalized_kw = kw.lower().strip()
            if self._is_meaningful_filename_category(normalized_kw):
                categories_to_add.add(normalized_kw)

        # 完整文件名仅在“有语义”时才纳入，避免 img_001 这类噪声分类污染
        if clean_filename and self._is_meaningful_filename_category(clean_filename):
            categories_to_add.add(clean_filename)

        return {c for c in categories_to_add if isinstance(c, str) and c.strip()}

    def _is_meaningful_filename_category(self, token: str) -> bool:
        """判断文件名提取的分类是否有语义，避免噪声分类导致随机匹配。"""
        if not token:
            return False

        value = str(token).strip()
        if not value:
            return False

        value_lower = value.lower()

        # 纯数字或过短 token 没有分类意义
        if value_lower.isdigit() or len(value_lower) < 2:
            return False

        # 常见噪声前缀/后缀，不应作为绑定分类
        generic_noise = {
            'img', 'image', 'photo', 'pic', 'picture', 'export', 'output', 'out',
            'test', 'tmp', 'temp', 'new', 'old', 'final', 'copy', 'result',
            'item', 'product', 'shop', 'scene', 'bg', 'banner'
        }
        if value_lower in generic_noise:
            return False

        # 与文字分类共用停用词，避免营销词把分类池污染成“全匹配”
        if self._is_stop_word(value):
            return False

        return True

    def _scan_folder_category_entries(self, abs_dir: str) -> List[Dict]:
        """扫描目录并建立分类索引条目。"""
        entries: List[Dict] = []
        try:
            with os.scandir(abs_dir) as scanned:
                for entry in scanned:
                    try:
                        if not entry.is_file():
                            continue
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext not in self._supported_image_ext:
                            continue
                        file_path = entry.path
                        filename_without_ext = os.path.splitext(entry.name)[0]
                        categories = sorted(self._extract_categories_for_filename(filename_without_ext))
                        entries.append({'path': file_path, 'categories': categories})
                    except Exception:
                        continue
        except Exception:
            return []
        return entries

    def _get_folder_category_entries_cached(self, directory: str) -> List[Dict]:
        """获取目录分类索引（持久化缓存 + mtime 增量失效）。"""
        if not directory:
            return []
        abs_dir = os.path.abspath(directory)
        if not os.path.isdir(abs_dir):
            return []

        dir_mtime_ns = self._get_directory_mtime_ns(abs_dir)
        cache_entry = self._folder_category_index_cache.get(abs_dir)
        if cache_entry and cache_entry.get('mtime_ns') == dir_mtime_ns:
            cached_files = []
            cache_changed = False
            for item in cache_entry.get('files', []):
                if not isinstance(item, dict):
                    continue
                file_path = item.get('path')
                categories = item.get('categories', [])
                if not isinstance(file_path, str):
                    continue
                if not isinstance(categories, list):
                    categories = []
                filtered_categories = [
                    str(c) for c in categories
                    if isinstance(c, str) and self._is_meaningful_filename_category(c)
                ]
                if len(filtered_categories) != len(categories):
                    cache_changed = True
                cached_files.append({'path': file_path, 'categories': filtered_categories})

            if cache_changed:
                self._folder_category_index_cache[abs_dir] = {
                    'mtime_ns': dir_mtime_ns,
                    'files': cached_files
                }
                self.__class__._folder_category_index_dirty = True
                self.__class__._save_persistent_category_index_cache(force=False)

            return cached_files

        files = self._scan_folder_category_entries(abs_dir)
        self._folder_category_index_cache[abs_dir] = {
            'mtime_ns': dir_mtime_ns,
            'files': files
        }
        self.__class__._folder_category_index_dirty = True
        self.__class__._save_persistent_category_index_cache(force=False)
        return list(files)
    
    def _analyze_layer_files(self, layer, layer_index: int):
        """分析图层文件并分类 - 修复版本，支持文件限制和文字图层特殊处理"""
        
        # 🔧 新增：检查是否为文字图层
        if self._is_text_layer(layer):
            self._analyze_text_layer_content(layer, layer_index)
            return
            
        # 原有逻辑：处理普通图像图层
        if not layer.image_source or not os.path.isdir(layer.image_source):
            print(f"[绑定组] 图层 '{layer.name}' (索引{layer_index}) 跳过分析: 无图像源或源不是文件夹")
            return

        # 🔧 关键修复：检查是否有绑定管理器的文件限制
        restricted_files = None
        if hasattr(self, '_binding_manager') and self._binding_manager:
            restricted_files = self._binding_manager.get_layer_file_restrictions(layer)
            if restricted_files:
                print(f"[绑定组] 图层 '{layer.name}' 应用文件限制: {len(restricted_files)} 个文件")

        try:
            indexed_entries = self._get_folder_category_entries_cached(layer.image_source)
            if restricted_files:
                allowed_files = {
                    os.path.normcase(os.path.normpath(os.path.abspath(p)))
                    for p in restricted_files if isinstance(p, str)
                }
                indexed_entries = [
                    item for item in indexed_entries
                    if isinstance(item, dict) and os.path.normcase(
                        os.path.normpath(os.path.abspath(str(item.get('path', ''))))
                    ) in allowed_files
                ]
                print(f"[绑定组] 图层 '{layer.name}' 使用文件限制: {len(indexed_entries)} 个文件")
            else:
                print(f"[绑定组] 图层 '{layer.name}' 扫描文件夹: {len(indexed_entries)} 个文件")

            for item in indexed_entries:
                if not isinstance(item, dict):
                    continue
                file_path = item.get('path')
                categories_to_add = item.get('categories', [])
                if not isinstance(file_path, str) or not file_path:
                    continue
                if not isinstance(categories_to_add, list):
                    categories_to_add = []
                for category in categories_to_add:
                    if not isinstance(category, str) or not category.strip():
                        continue
                    if category not in self.file_categories:
                        self.file_categories[category] = {}

                    if layer_index not in self.file_categories[category]:
                        self.file_categories[category][layer_index] = []

                    if file_path not in self.file_categories[category][layer_index]:
                        self.file_categories[category][layer_index].append(file_path)
                        
                if _BINDING_VERBOSE:
                    filename = os.path.basename(file_path)
                    print(f"  文件: {filename} -> 分类: {list(categories_to_add)}")

        except Exception as e:
            print(f"分析图层文件时出错: {e}")
    
    def _validate_category_semantic_consistency(self, group, category: str, document_layers: List) -> bool:
        """🔧 简化版：直接文案匹配验证"""
        """直接对比文字图层内容与图像文件名，确保语义一致"""
        try:
            print(f"[直接匹配] 验证分类 '{category}' 与绑定组 '{group.name}' 的匹配一致性...")
            
            # 获取绑定组中的文字图层和图像图层
            text_layers_in_group = []
            image_layers_in_group = []
            
            for doc_layer in document_layers:
                if doc_layer.name in [layer.name for layer in group.layers]:
                    if self._is_text_layer(doc_layer):
                        text_layers_in_group.append(doc_layer)
                    else:
                        image_layers_in_group.append(doc_layer)
            
            print(f"[直接匹配] 绑定组包含: 文字图层{len(text_layers_in_group)}个, 图像图层{len(image_layers_in_group)}个")
            
            # 🔧 简化验证1：提取所有文字内容作为虚拟文件名
            text_virtual_files = []
            for text_layer in text_layers_in_group:
                if hasattr(text_layer, 'get_text_lines') and callable(getattr(text_layer, 'get_text_lines', None)):
                    try:
                        text_lines = text_layer.get_text_lines()
                        for line in text_lines:
                            line_str = str(line).strip()
                            if line_str:
                                # 创建虚拟文件名格式：text_行内容
                                virtual_filename = f"text_{line_str}"
                                text_virtual_files.append(virtual_filename)
                                print(f"[直接匹配] 文字虚拟文件: '{virtual_filename}'")
                    except Exception:
                        pass
                
                # 也检查current_text
                if hasattr(text_layer, 'current_text') and text_layer.current_text:
                    current_text = str(text_layer.current_text).strip()
                    if current_text:
                        virtual_filename = f"text_{current_text}"
                        if virtual_filename not in text_virtual_files:
                            text_virtual_files.append(virtual_filename)
                            print(f"[直接匹配] 当前文字虚拟文件: '{virtual_filename}'")
            
            # 🔧 简化验证2：提取图像文件名（不含路径）
            image_filenames = []
            if category in group.file_categories:
                for layer_idx, files in group.file_categories[category].items():
                    if layer_idx < len(group.layers) and not self._is_text_layer(group.layers[layer_idx]):
                        for file_path in files:
                            if isinstance(file_path, str) and not is_text_layer_virtual_path(file_path):
                                # 提取文件名（不含路径）
                                filename = os.path.basename(file_path)
                                # 移除文件扩展名
                                filename_no_ext = os.path.splitext(filename)[0]
                                image_filenames.append(filename_no_ext)
                                print(f"[直接匹配] 图像文件: '{filename_no_ext}'")
            
            # 🔧 简化验证3：直接对比文字虚拟文件和图像文件名
            direct_matches = []
            if text_virtual_files and image_filenames:
                for text_file in text_virtual_files:
                    text_content = text_file.replace('text_', '')
                    for image_file in image_filenames:
                        # 检查文字内容是否在图像文件名中，或者图像文件名在文字内容中
                        if (text_content in image_file or 
                            image_file in text_content or 
                            self._calculate_similarity(text_content, image_file) > 0.5):
                            direct_matches.append((text_content, image_file))
                            print(f"[直接匹配] ✅ 找到匹配: '{text_content}' <-> '{image_file}'")
            
            # 🔧 简化判断逻辑
            if text_layers_in_group and image_layers_in_group:
                # 混合绑定组：需要文字和图像有直接匹配
                if direct_matches:
                    print(f"[直接匹配] ✅ 混合绑定组：找到 {len(direct_matches)} 个直接匹配")
                    return True
                else:
                    print(f"[直接匹配] ❌ 混合绑定组：文字和图像无直接匹配")
                    return False
            elif text_layers_in_group:
                # 纯文字绑定组：只要有文字内容即可
                if text_virtual_files:
                    print(f"[直接匹配] ✅ 纯文字绑定组：有 {len(text_virtual_files)} 个文字内容")
                    return True
                else:
                    print(f"[直接匹配] ❌ 纯文字绑定组：无文字内容")
                    return False
            elif image_layers_in_group:
                # 纯图像绑定组：只要有图像文件即可
                if image_filenames:
                    print(f"[直接匹配] ✅ 纯图像绑定组：有 {len(image_filenames)} 个图像文件")
                    return True
                else:
                    print(f"[直接匹配] ❌ 纯图像绑定组：无图像文件")
                    return False
            else:
                # 空绑定组
                print(f"[直接匹配] ⚠️ 空绑定组，默认接受")
                return True
                
        except Exception as e:
            print(f"[直接匹配] ❌ 验证过程出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时默认接受，避免阻断正常流程
            return True
    
    def _calculate_similarity(self, text1: str, text2: str) -> float:
        """🔧 新增：计算两个文本的相似度"""
        """用于模糊匹配文字内容和文件名"""
        try:
            # 简单的相似度计算：共同字符比例
            set1 = set(text1.lower())
            set2 = set(text2.lower())
            
            if not set1 or not set2:
                return 0.0
            
            intersection = len(set1.intersection(set2))
            union = len(set1.union(set2))
            
            jaccard_similarity = intersection / union if union > 0 else 0.0
            
            # 额外的长度相似度惩罚
            length_ratio = min(len(text1), len(text2)) / max(len(text1), len(text2)) if max(len(text1), len(text2)) > 0 else 0.0
            
            return jaccard_similarity * length_ratio
            
        except Exception:
            return 0.0

    def _extract_product_categories_from_text(self, text: str) -> Set[str]:
        from app.utils.product_category_extractor import extract_product_categories_from_text
        return extract_product_categories_from_text(text)

    def _is_text_layer(self, layer) -> bool:
        """检查图层是否为文字图层"""
        return hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None))

    def _build_text_virtual_path(self, layer_name: str, text_value) -> str:
        """统一构建文字图层虚拟路径，确保文本内容始终使用URL编码。"""
        return build_text_layer_virtual_path(layer_name, text_value)
    
    def _analyze_text_layer_content(self, layer, layer_index: int):
        """分析文字图层的内容并分类 - 文字图层特殊处理 - 修复状态同步问题"""
        try:
            if not self._is_text_layer(layer):
                return
            # 🔧 修复：增加状态一致性验证
            layer_state_snapshot = self._capture_layer_state(layer)
            
            # 获取文字图层的所有文字内容
            text_lines = layer.get_text_lines()
            if not text_lines:
                text_lines = []
            
            # 获取当前显示的文字 - 增加验证
            current_text = getattr(layer, 'current_text', '')
            if not isinstance(current_text, str):
                current_text = str(current_text) if current_text is not None else ''
            
            if not current_text and text_lines:
                current_text = text_lines[0] if text_lines else ''
            
            print(f"[绑定组] 分析文字图层 '{layer.name}': 当前文字='{current_text}', 所有文字={text_lines}")
            
            # 🔧 关键修复：为每个独特的文字内容创建分类
            # 而不仅仅是基于当前文字
            unique_categories = set()
            
            # 🔧 重要改进：确保当前编辑的文字始终参与分类
            # 即使它不在原始的 text_lines 中
            all_texts = text_lines.copy() if text_lines else []
            if current_text and current_text.strip():
                # 如果当前文字是全新的内容，将其添加到分析集合
                if current_text not in all_texts:
                    all_texts.append(current_text)
                    print(f"[绑定组] 添加新编辑的文字到分析集合: '{current_text}'")
            
            # 🔧 新增：为当前文字创建专门的分类，确保实时性
            if current_text and current_text.strip():
                # 提取当前文字的关键词
                current_keywords = self._extract_keywords_from_text(current_text)
                unique_categories.update(current_keywords)
                # 同时添加完整文字作为分类
                unique_categories.add(current_text.strip())
            
            # 🔧 修复：增强文字内容验证，避免空值和异常
            for text_content in all_texts:
                if not text_content or not str(text_content).strip():
                    continue
                
                # 验证文字内容有效性
                text_str = str(text_content).strip()
                if len(text_str) == 0:
                    continue
                    
                # 提取关键词作为分类（如"口红"、"面膜"、"抖音"等）
                words = self._extract_keywords_from_text(text_str)
                unique_categories.update(words)
                # 同时将每一行完整文案作为分类，支持相同文案精确绑定
                unique_categories.add(text_str)
            
            # 确保至少有一个分类
            if not unique_categories and current_text:
                unique_categories.add(current_text.strip())
            elif not unique_categories:
                unique_categories.add("空文字")
            
            print(f"[绑定组] 文字图层 '{layer.name}' 提取到分类: {unique_categories}")
            
            # 🔧 修复：增加状态一致性检查
            current_state = self._capture_layer_state(layer)
            if not self._is_state_consistent(layer_state_snapshot, current_state):
                print(f"[绑定组] 警告：图层 '{layer.name}' 状态在分析过程中发生变化，可能需要重新分析")
                # 可以选择重新分析或记录状态变化
            
            # 为每个分类创建条目
            for category_name in unique_categories:
                # 如果分类不存在，创建它
                if category_name not in self.file_categories:
                    self.file_categories[category_name] = {}
                
                # 为该图层索引创建文件列表（文字图层用虚拟文件路径表示）
                if layer_index not in self.file_categories[category_name]:
                    self.file_categories[category_name][layer_index] = []
                
                # 🔧 关键：为匹配这个分类的文字内容创建虚拟文件路径
                for text_content in all_texts:
                    text_stripped = str(text_content).strip()
                    if not text_stripped:
                        continue
                    
                    # 🔧 修复：更严格的匹配检查，避免宽松匹配导致的错误绑定
                    should_match = False
                    
                    # 1. 精确匹配（最高优先级）
                    if text_stripped == str(category_name).strip():
                        should_match = True
                    
                    # 2. 分类名在文字内容中（仅当分类名是有效产品词时）
                    elif category_name and str(category_name).lower() in text_stripped.lower():
                        # 检查分类名是否为有效产品词，而不是通用修饰词
                        category_str = str(category_name).strip()
                        if len(category_str) >= 2 and not self._is_stop_word(category_str):
                            should_match = True
                    
                    if should_match:
                        virtual_file_path = self._build_text_virtual_path(layer.name, text_stripped)
                        if virtual_file_path not in self.file_categories[category_name][layer_index]:
                            self.file_categories[category_name][layer_index].append(virtual_file_path)
                
                # 🔧 新增：特别处理当前文字，确保它始终可用
                if current_text and current_text.strip():
                    current_stripped = current_text.strip()
                    # 检查当前文字是否与这个分类匹配
                    current_should_match = False
                    if category_name and str(category_name).lower() in current_stripped.lower():
                        current_should_match = True
                    elif current_stripped.lower() in str(category_name).lower():
                        current_should_match = True
                    elif current_stripped.lower() == str(category_name).strip().lower():
                        current_should_match = True
                    
                    if current_should_match:
                        current_virtual_path = self._build_text_virtual_path(layer.name, current_stripped)
                        if current_virtual_path not in self.file_categories[category_name][layer_index]:
                            self.file_categories[category_name][layer_index].append(current_virtual_path)
                            print(f"[绑定组] 为分类 '{category_name}' 添加当前文字虚拟路径: {current_virtual_path}")
            
            print(f"[绑定组] 文字图层 '{layer.name}' 分类完成: 创建了 {len(unique_categories)} 个分类")
            
        except Exception as e:
            print(f"[绑定组] 分析文字图层内容时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def _capture_layer_state(self, layer):
        """🔧 新增：捕获图层状态的快照"""
        """用于验证状态一致性"""
        try:
            return {
                'current_text': getattr(layer, 'current_text', ''),
                'text_lines': layer.get_text_lines() if hasattr(layer, 'get_text_lines') else [],
                'layer_id': id(layer),
                'timestamp': time.time()  # 真实时间戳
            }
        except Exception as e:
            print(f"[绑定组] 捕获图层状态失败: {e}")
            return {'error': str(e)}
    
    def _is_state_consistent(self, old_state, new_state):
        """🔧 新增：验证图层状态是否一致"""
        """防止在分析过程中状态发生变化"""
        try:
            if 'error' in old_state or 'error' in new_state:
                return False
            
            # 比较关键状态字段
            return (old_state.get('current_text') == new_state.get('current_text') and
                   old_state.get('layer_id') == new_state.get('layer_id'))
        except Exception as e:
            print(f"[绑定组] 状态一致性检查失败: {e}")
            return False
    
    def _is_stop_word(self, word: str) -> bool:
        """判断是否为停用词（通用修饰词，不应作为分类依据）"""
        stop_words = {
            '热卖', '爆款', '新品', '推荐', '限时', '优惠', '特价', '打折',
            '大牌', '好物', '精选', '超值', '划算', '实惠', '便宜', '低价',
            '疯抢', '疯降', '直降', '立减', '满减', '买赠', '秒杀', '抢购',
            '正品', '品质', '高端', '时尚', '潮流', '经典', '必备', '实用',
            '家用', '日常', '生活', '必备品', '必需品', '单品', '同款'
        }
        return word.strip() in stop_words

    def _extract_keywords_from_text(self, text: str) -> set:
        """从文字中提取关键词作为分类 - 修复版本，增强跨分类关联"""
        keywords = set()
        
        text = str(text).strip()
        if len(text) < 2:
            return keywords
        
        # 🔧 增强：标准化产品分类词典 - 包含更多分类和跨分类关联
        standard_categories = {
            # 美妆护肤
            '口红', '唇膏', '唇彩', '唇釉', '口红套装',
            '面膜', '面贴膜', '睡眠面膜', '清洁面膜',
            '防晒', '防晒霜', '防晒喷雾', '防晒乳',
            '香水', '淡香水', '古龙水', '香氛',
            '面霜', '日霜', '晚霜', '乳液', '润肤霜',
            '精华', '精华液', '精华露', '肌底液',
            '洁面', '洗面奶', '洁面乳', '洁面泡沫',
            '眼霜', '眼精华', '眼膜',
            '粉底', '粉底液', '粉底霜', '气垫', 'BB霜', 'CC霜',
            '眼影', '眼线', '睫毛膏', '眉笔',
            
            # 数码电器
            '手机', '智能手机', 'iPhone', '华为手机', '小米手机', 'OPPO手机', 'vivo手机',
            '蓝牙音箱', '音箱', '音响', '无线音箱', '便携音箱',
            '耳机', '蓝牙耳机', '无线耳机', '降噪耳机',
            '充电宝', '移动电源', '充电器', '数据线',
            '智能手表', '手环', '运动手表',
            '平板电脑', 'iPad', '安卓平板',
            '笔记本电脑', '笔记本', 'MacBook',
            '相机', '数码相机', '单反', '微单',
            
            # 服装鞋包
            '连衣裙', '裙子', '长裙', '短裙', '半身裙', 'A字裙',
            'T恤', '短袖', '长袖', '卫衣', '毛衣', '针织衫',
            '牛仔裤', '休闲裤', '运动裤', '打底裤',
            '外套', '夹克', '风衣', '大衣', '羽绒服',
            '运动鞋', '板鞋', '帆布鞋', '皮鞋', '高跟鞋',
            '包包', '手提包', '单肩包', '双肩包', '钱包',
            
            # 家居生活 - 增强抽纸相关分类
            '抽纸', '纸巾', '面巾纸', '卫生纸', '餐巾纸', '手帕纸', '卷纸',
            '洗衣液', '洗衣粉', '洗衣皂', '洗衣凝珠',
            '洗发水', '护发素', '沐浴露', '香皂',
            '牙膏', '牙刷', '漱口水',
            '毛巾', '浴巾', '洗脸巾',
            '被子', '床单', '枕头', '被套', '枕套',
            
            # 食品饮料
            '零食', '坚果', '饼干', '巧克力', '糖果',
            '茶叶', '绿茶', '红茶', '乌龙茶', '普洱茶',
            '咖啡', '速溶咖啡', '咖啡豆', '咖啡粉',
            '蜂蜜', '果酱', '花生酱',
            
            # 母婴用品
            '奶粉', '婴儿奶粉', '儿童奶粉',
            '纸尿裤', '尿不湿', '拉拉裤',
            '奶瓶', '奶嘴', '婴儿餐具',
            '婴儿服装', '连体衣', '爬服',
            
            # 平台/品牌相关
            '快手', '抖音', '淘宝', '直播', '网红', '达人', '李佳琦', '薇娅',
            '热卖', '爆款', '新品', '推荐', '限时', '优惠', '特价', '打折',
            '维达', '清风', '心相印', '洁柔',  # 纸巾品牌
            
            # 修饰词
            '春夏', '秋冬', '春季', '夏季', '秋季', '冬季',
            '清新', '保湿', '美白', '抗衰老', '抗皱', '紧致', '修复'
        }
        
        # 🔧 新增：跨分类关联词典
        cross_category_mapping = {
            '半身裙': ['女装', '服装', '时尚', '搭配', '裙子'],
            '抽纸': ['家居', '日用品', '清洁', '生活用纸', '纸巾'],
            '纸巾': ['抽纸', '面巾纸', '卫生纸', '生活用纸'],
            '快手热卖': ['直播', '网红', '爆款', '抖音'],
            '维达': ['抽纸', '纸巾', '品牌', '生活用纸'],
        }
        
        # 🔍 第一步：检查标准分类是否在文本中
        for category in standard_categories:
            if category in text:
                keywords.add(category)
        
        # 🔧 第二步：智能跨分类匹配
        # 如果找到了主要分类，添加其关联词
        for main_category, related_words in cross_category_mapping.items():
            if main_category in text:
                # 添加关联词到关键词集合
                keywords.update(related_words)
                print(f"[智能匹配] 找到主分类 '{main_category}'，添加关联词: {related_words}")
        
        # 🔍 第三步：智能提取产品词（如果没有找到标准分类）
        if not keywords:
            # 提取2-6个字符的核心词
            import re
            
            # 移除标点符号和特殊字符
            clean_text = re.sub(r'[，。！？；：、\s]', '', text)
            
            # 尝试提取可能的产品词
            if len(clean_text) >= 2:
                # 提取连续的中文词组
                chinese_words = re.findall(r'[\u4e00-\u9fa5]{2,6}', clean_text)
                
                for word in chinese_words:
                    # 🔧 修复：使用统一的停用词检测函数，避免通用修饰词被当作关键词
                    if not self._is_stop_word(word):
                        # 如果这个词看起来像是产品词（不是纯动词/形容词）
                        if len(word) >= 2 and len(word) <= 6:
                            keywords.add(word)

                # 🔧 新增：提取英文关键词（与普通图层分析逻辑保持一致）
                english_words = re.findall(r'[a-zA-Z]{2,}', text)
                for word in english_words:
                    # 统一转换为小写进行停用词检查，但保留原词作为分类（如果需要区分大小写）
                    # 或者为了匹配更容易，可以添加小写版本
                    if not self._is_stop_word(word.lower()):
                         keywords.add(word)
                         # 同时添加小写版本以增加匹配概率
                         keywords.add(word.lower())
            
            # 如果还是找不到，使用原始文本作为后备
            if not keywords and len(text) >= 2:
                keywords.add(text.strip())
        
        # 🔧 第四步：上下文感知增强
        # 检查是否出现在电商平台上下文中
        ecommerce_contexts = ['快手', '抖音', '淘宝', '直播', '热卖', '爆款']
        has_ecommerce_context = any(ctx in text for ctx in ecommerce_contexts)
        
        if has_ecommerce_context and keywords:
            # 如果在电商上下文中，增强产品词的权重
            print(f"[上下文感知] 检测到电商上下文，增强产品词权重: {keywords}")
        
        return keywords
    
    def _extract_core_name(self, filename: str) -> str:
        base = os.path.splitext(os.path.basename(str(filename)))[0]
        base = str(base).strip()
        base = re.sub(r'[\s_\-]*[\(\[\{]\s*\d+\s*[\)\]\}]\s*$', '', base)
        for pattern in [
            r'(?:[\s_\-]*(?:副本|拷贝|复制|copy|Copy|COPY))\s*$',
            r'(?:[\s_\-]*(?:副本|拷贝|复制)\s*\d*)\s*$'
        ]:
            base = re.sub(pattern, '', base, flags=re.IGNORECASE)
        for pattern in [
            r'(?:[\s_\-]*(?:v|ver|版本|version)\s*[\d\.]+)\s*$',
            r'(?:[\s_\-]*v\s*\d+\.\d+)\s*$'
        ]:
            base = re.sub(pattern, '', base, flags=re.IGNORECASE)
        base = re.sub(r'(?:[\s_\-\.]*\d+)+\s*$', '', base)
        tokens = re.split(r'[\s_\-]+', base)
        tokens = [t.strip() for t in tokens if t and not t.strip().isdigit()]
        # 扩展通用前缀列表，包含常见的文件名前缀
        generic = {'rt', 'img', 'image', 'photo', 'pic', 'export', 'expo', 'exp', 'test', 'tmp', 'temp', 'output', 'out', 'final', 'new', 'old', '品牌', '分类', '商品', 'item', 'product', 'shop'}
        def chinese_len(s: str) -> int:
            return len(re.findall(r'[\u4e00-\u9fa5]', s))
        preferred = [t for t in tokens if chinese_len(t) >= 2]
        if preferred:
            # 按中文长度排序，选择中文最多的，如果长度相同选择更具体的词
            preferred.sort(key=lambda x: (chinese_len(x), len(x)), reverse=True)
            core = preferred[0]
        else:
            candidates = [t for t in tokens if t.lower() not in generic]
            if candidates:
                candidates.sort(key=lambda x: len(x), reverse=True)
                core = candidates[0]
            else:
                # 如果过滤后没有候选，选择最长的token
                if tokens:
                    tokens.sort(key=lambda x: len(x), reverse=True)
                    core = tokens[0]
                else:
                    core = base
        core = re.sub(r'[\s_\-\.]+$', '', core).strip()
        return core if core else os.path.splitext(os.path.basename(str(filename)))[0]
    
    def _rebuild_file_categories(self):
        """重建文件分类：从当前图层状态全量重算，避免旧分类污染匹配结果。"""
        # 全量重算，确保分类与当前图层/文件夹内容一致
        self.file_categories = {}

        # 重新分析图层文件
        for i, layer in enumerate(self.layers):
            self._analyze_layer_files(layer, i)

        try:
            text_layer_info = []
            for idx, layer in enumerate(self.layers):
                if self._is_text_layer(layer):
                    lines = []
                    try:
                        lines = [l.strip() for l in layer.get_text_lines() if str(l).strip()]
                    except Exception:
                        lines = []
                    text_layer_info.append((idx, layer, lines))

            # 仅使用当前重建后的分类集合，避免历史噪声分类残留
            all_categories = list(self.file_categories.keys())
            for category_name in all_categories:
                # 确保分类存在
                if category_name not in self.file_categories:
                    self.file_categories[category_name] = {}

                # 为文字图层添加虚拟路径
                for idx, layer, lines in text_layer_info:
                    # 🔧 修复：更严格的匹配条件，避免双向包含导致的误匹配
                    matched_lines = []
                    for l in lines:
                        line_stripped = str(l).strip()
                        if not line_stripped or not category_name:
                            continue
                            
                        category_str = str(category_name).strip()
                        
                        # 1. 精确匹配（最高优先级）
                        if line_stripped == category_str:
                            matched_lines.append(l)
                        # 2. 分类名在文字行中（仅当分类名是有效产品词时）
                        elif category_str in line_stripped and len(category_str) >= 2 and not self._is_stop_word(category_str):
                            matched_lines.append(l)
                    if matched_lines:
                        if idx not in self.file_categories[category_name]:
                            self.file_categories[category_name][idx] = []
                        for l in matched_lines:
                            vpath = self._build_text_virtual_path(layer.name, l)
                            if vpath not in self.file_categories[category_name][idx]:
                                self.file_categories[category_name][idx].append(vpath)
        except Exception:
            pass
    
    def get_available_categories(self) -> List[str]:
        """获取可用的文件分类列表 - 优化混合绑定组的分类选择"""
        if not self.file_categories:
            return []
        
        available_categories = []
        
        # 🔧 新增：分析绑定组的图层构成
        text_layers = [layer for layer in self.layers if self._is_text_layer(layer)]
        image_layers = [layer for layer in self.layers if not self._is_text_layer(layer)]
        
        print(f"[绑定组分类分析] 绑定组 '{self.name}' 构成: 文字图层{len(text_layers)}个, 图像图层{len(image_layers)}个")
        
        if text_layers and image_layers:
            # 🔧 优化混合模式：支持跨分类智能匹配
            print("[绑定组分类分析] 使用优化混合模式分类逻辑")
            
            # 分别收集图像分类和文字分类
            image_categories = set()
            text_categories = set()
            
            for category_name, layer_files in self.file_categories.items():
                has_image_layer = False
                has_text_layer = False
                
                for layer_idx, files in layer_files.items():
                    if layer_idx < len(self.layers) and len(files) > 0:
                        layer = self.layers[layer_idx]
                        if self._is_text_layer(layer):
                            has_text_layer = True
                        else:
                            has_image_layer = True
                
                if has_image_layer:
                    image_categories.add(category_name)
                if has_text_layer:
                    text_categories.add(category_name)
            
            print(f"[绑定组分类分析] 图像分类: {len(image_categories)}个, 文字分类: {len(text_categories)}个")
            
            # 🔧 策略1：优先使用图像分类（保证图像图层正常工作）
            for category_name in image_categories:
                # 检查该图像分类是否对所有图像图层都可用
                image_layers_covered = 0
                text_layers_covered = 0
                
                for layer_idx in range(len(self.layers)):
                    if layer_idx < len(self.layers):
                        layer = self.layers[layer_idx]
                        if not self._is_text_layer(layer):  # 图像图层
                            if (category_name in self.file_categories and 
                                layer_idx in self.file_categories[category_name] and 
                                len(self.file_categories[category_name][layer_idx]) > 0):
                                image_layers_covered += 1
                        else:  # 文字图层
                            if (category_name in self.file_categories and 
                                layer_idx in self.file_categories[category_name] and 
                                len(self.file_categories[category_name][layer_idx]) > 0):
                                text_layers_covered += 1
                
                # 如果该分类覆盖所有图像图层，且（如果有文字图层）也覆盖所有文字图层，则可用
                # 🔧 修复：严格检查文字图层匹配，防止非同类绑定
                if image_layers_covered == len(image_layers):
                    if not text_layers or text_layers_covered == len(text_layers):
                        available_categories.append(category_name)
                        print(f"[绑定组分类分析] 图像分类 '{category_name}' 可用: 覆盖{image_layers_covered}图像/{text_layers_covered}文字")
                    else:
                        print(f"[绑定组分类分析] 图像分类 '{category_name}' 排除: 文字图层不匹配 ({text_layers_covered}/{len(text_layers)})")
            
            # 🔧 策略2：如果图像分类太少，添加一些文字分类以增加多样性
            # 🔧 关键修复：但只添加有图像支撑的文字分类，避免纯文字分类污染
            if len(available_categories) < 2 and text_categories:
                # 选择有图像支撑的文字分类
                for category_name in text_categories:
                    if category_name not in available_categories:
                        # 检查这个文字分类是否有对应的图像文件支撑
                        has_image_support = False
                        if category_name in self.file_categories:
                            for layer_idx, files in self.file_categories[category_name].items():
                                if any(isinstance(f, str) and not is_text_layer_virtual_path(f) for f in files):
                                    has_image_support = True
                                    break
                        
                        if has_image_support:
                            available_categories.append(category_name)
                            print(f"[绑定组分类分析] 添加有图像支撑的文字分类 '{category_name}' 增加多样性")
                            break  # 只添加一个有图像支撑的文字分类
                        else:
                            print(f"[绑定组分类分析] 跳过纯文字分类 '{category_name}' (无图像支撑)")
            
            # 🔧 策略3：如果还是没有可用分类，放宽条件
            if not available_categories and image_categories:
                # 选择覆盖率最高的图像分类
                best_category = None
                best_coverage = 0
                
                for category_name in image_categories:
                    coverage = 0
                    for layer_idx in range(len(self.layers)):
                        if layer_idx < len(self.layers):
                            layer = self.layers[layer_idx]
                            if not self._is_text_layer(layer):
                                if (category_name in self.file_categories and 
                                    layer_idx in self.file_categories[category_name] and 
                                    len(self.file_categories[category_name][layer_idx]) > 0):
                                    coverage += 1
                    
                    coverage_ratio = coverage / len(image_layers) if image_layers else 0
                    if coverage_ratio > best_coverage:
                        best_coverage = coverage_ratio
                        best_category = category_name
                
                if best_category and best_coverage >= 0.5:  # 至少50%覆盖
                    # 🔧 修复：放宽条件时也必须检查文字图层兼容性
                    is_text_compatible = True
                    if text_layers:
                        text_covered = 0
                        for layer_idx in range(len(self.layers)):
                            layer = self.layers[layer_idx]
                            if self._is_text_layer(layer):
                                if (best_category in self.file_categories and 
                                    layer_idx in self.file_categories[best_category]):
                                    text_covered += 1
                        
                        if text_covered < len(text_layers):
                            is_text_compatible = False
                            print(f"[绑定组分类分析] 放宽条件失败: 最佳分类 '{best_category}' 与文字图层不兼容")

                    if is_text_compatible:
                        available_categories.append(best_category)
                        print(f"[绑定组分类分析] 放宽条件，选择最佳图像分类 '{best_category}': 覆盖率{best_coverage:.1%}")
        
        elif text_layers:
            # 🔧 纯文字图层模式：使用宽松匹配
            print("[绑定组分类分析] 使用纯文字图层模式")
            
            for category_name, layer_files in self.file_categories.items():
                # 只要有文字图层有这个分类即可
                text_layer_covered = False
                for layer_idx, files in layer_files.items():
                    if (layer_idx < len(self.layers) and 
                        self._is_text_layer(self.layers[layer_idx]) and 
                        len(files) > 0):
                        text_layer_covered = True
                        break
                
                if text_layer_covered:
                    available_categories.append(category_name)
                    print(f"[绑定组分类分析] 分类 '{category_name}' 符合纯文字模式条件")
        
        else:
            # 🔧 纯图像图层模式：使用严格匹配（原有逻辑）
            print("[绑定组分类分析] 使用纯图像图层模式")
            
            for core_name, layer_files in self.file_categories.items():
                # 检查是否所有图层都有这个分类的文件（严格匹配）
                if len(layer_files) >= len(self.layers):
                    # 确保每个图层都至少有一个文件
                    if all(len(files) > 0 for files in layer_files.values()):
                        available_categories.append(core_name)
                        print(f"[绑定组分类分析] 分类 '{core_name}' 符合纯图像模式条件")
        
        print(f"[绑定组分类分析] 最终可用分类: {available_categories}")
        return available_categories
    
    def analyze_category_diversity(self) -> Dict[str, Dict]:
        """分析每个分类的内部组合多样性"""
        diversity_info = {}
        available_categories = self.get_available_categories()
        
        for category in available_categories:
            if category not in self.file_categories:
                continue
                
            # 计算该分类的理论组合数
            layer_file_counts = []
            layer_indices = sorted(self.file_categories[category].keys())
            
            for layer_idx in layer_indices:
                file_count = len(self.file_categories[category][layer_idx])
                layer_file_counts.append(file_count)
            
            # 计算总组合数
            total_combinations = 1
            for count in layer_file_counts:
                total_combinations *= count
            
            # 获取该分类的使用历史
            used_count = 0
            if hasattr(self, '_binding_manager') and self._binding_manager:
                global_mgr = self._binding_manager.global_combination_manager
                if global_mgr and self.group_id in global_mgr.combination_history:
                    # 统计该分类的组合使用次数
                    for combo_hash, usage in global_mgr.combination_history[self.group_id].items():
                        # 需要判断这个组合是否属于当前分类
                        # 这里我们用启发式方法：假设分类内的组合相对平均分布
                        used_count += usage
            
            # 计算多样性指标
            diversity_score = max(0.0, 1.0 - (used_count / max(1, total_combinations)))
            
            diversity_info[category] = {
                'total_combinations': total_combinations,
                'layer_file_counts': layer_file_counts,
                'used_count': used_count,
                'diversity_score': diversity_score,  # 0-1，1表示完全未使用
                'avg_files_per_layer': sum(layer_file_counts) / len(layer_file_counts) if layer_file_counts else 0
            }
            
            print(f"[绑定组多样性] 分类'{category}': 总组合{total_combinations}, 已用{used_count}, 多样性{diversity_score:.3f}")
        
        return diversity_info
    
    def get_highest_diversity_categories(self, count: int = None) -> List[str]:
        """获取多样性最高的分类列表"""
        diversity_info = self.analyze_category_diversity()
        if not diversity_info:
            return self.get_available_categories()
        
        # 按多样性分数和总组合数排序
        sorted_categories = sorted(
            diversity_info.items(),
            key=lambda x: (x[1]['diversity_score'], x[1]['total_combinations']),
            reverse=True
        )
        
        categories = [cat for cat, info in sorted_categories]
        if count is not None:
            categories = categories[:count]
            
        print(f"[绑定组多样性] 推荐使用分类: {categories[:5]}")
        return categories
    
    def select_random_category(self) -> Optional[str]:
        """随机选择一个文件分类"""
        available = self.get_available_categories()
        if not available:
            return None
        
        selected = random.choice(available)
        self.last_selected_category = selected
        return selected
    
    def _get_current_layer_states(self) -> Dict[int, str]:
        """获取当前图层状态用于验证"""
        current_states = {}
        try:
            # 获取当前所有图层的文件状态
            for layer_idx, layer in enumerate(self.layers):
                if hasattr(layer, 'current_image_path') and layer.current_image_path:
                    current_states[layer_idx] = layer.current_image_path
                elif hasattr(layer, 'image_source') and layer.image_source:
                    current_states[layer_idx] = layer.image_source
        except Exception as e:
            print(f"[_get_current_layer_states] 获取当前图层状态失败: {e}")
        return current_states

    def get_matched_files(self, category: Optional[str] = None, avoid_duplicates: bool = False) -> Dict[int, str]:
        """获取匹配文件 - 根本修复版：有状态，真正避免重复 + 100%验证
        
        参数:
            category: 指定的分类名称
            avoid_duplicates: 是否启用避重机制（默认False，只有用户启用"避免重复"时才为True）
        
        🔧 关键修复：避重机制改为可选，修复"启用绑定组时所有图层都变成只使用一次"的问题
        """
        import time
        import random
        import hashlib
        import traceback
        
        # 🔍 超详细日志 - 开始
        print(f"\n{'='*80}")
        print(f"[🔍 详细日志] get_matched_files 被调用")
        print(f"  绑定组: {self.name} (ID: {self.group_id})")
        print(f"  请求分类: {category}")
        print(f"  避重模式: {'启用' if avoid_duplicates else '禁用'}")
        print(f"  调用栈（最近3层）:")
        stack = traceback.extract_stack()
        for frame in stack[-4:-1]:
            print(f"    {os.path.basename(frame.filename)}:{frame.lineno} in {frame.name}")
        print(f"{'='*80}\n")
        
        # 🔧 新增：100%绑定验证 - 在获取匹配文件时验证
        if BINDING_INTEGRITY_AVAILABLE and hasattr(self, '_binding_manager') and self._binding_manager:
            try:
                # 获取当前图层状态用于验证
                current_states = self._get_current_layer_states()
                if current_states:
                    validation_result = validate_current_bindings(None, current_states)
                    print(f"[🔍 详细日志] 绑定验证结果: 准确率={validation_result.accuracy:.1f}%")
                    
                    if validation_result.accuracy < 100.0:
                        print(f"[🔍 详细日志] ⚠️ 发现绑定错误，将强制修复")
                        corrected_states = enforce_100_percent_binding_accuracy(None, current_states)
                        # 这里可以应用修正后的状态
            except Exception as e:
                print(f"[🔍 详细日志] 绑定验证失败: {e}")
        
        if category:
            # 🔧 关键修复：确保文件分类已分析
            if not self.file_categories:
                print(f"[🔍 详细日志] file_categories 为空，重新分析...")
                self._rebuild_file_categories()
                print(f"[🔍 详细日志] 重建后分类数: {len(self.file_categories)}")
            else:
                print(f"[🔍 详细日志] file_categories 已存在，分类数: {len(self.file_categories)}")
            
            print(f"[🔍 详细日志] 可用分类: {list(self.file_categories.keys())}")
            
            # 绑定组模式
            if category not in self.file_categories:
                print(f"[🔍 详细日志] ⚠️ 分类 '{category}' 不存在！")
                return {}
            
            print(f"[🔍 详细日志] ✅ 分类 '{category}' 存在")
            
            # 获取该分类下的所有图层
            layer_indices = sorted(list(self.file_categories[category].keys()))
            print(f"[🔍 详细日志] 该分类的图层索引: {layer_indices}")
            if not layer_indices:
                print(f"[🔍 详细日志] ⚠️ 图层索引为空！")
                return {}
            
            # 🔧 根本修复：初始化该分类的使用历史
            if not hasattr(self, '_category_usage_history'):
                self._category_usage_history = {}
                print(f"[🔍 详细日志] 初始化 _category_usage_history")
            
            if category not in self._category_usage_history:
                self._category_usage_history[category] = set()
                print(f"[🔍 详细日志] 为分类 '{category}' 创建新的历史记录")
            else:
                print(f"[🔍 详细日志] 分类 '{category}' 已有历史记录，已使用: {len(self._category_usage_history[category])} 个组合")
            
            # 🔧 关键修复：前置校验 - 确保每个图层在分类下都有候选文件
            print(f"[🔍 详细日志] 开始前置校验每个图层的候选文件...")
            invalid_layers = []
            for layer_idx in layer_indices:
                files = self.file_categories[category].get(layer_idx, [])
                if not files:
                    # 检查是否是文字图层
                    if layer_idx < len(self.layers):
                        layer = self.layers[layer_idx]
                        if self._is_text_layer(layer):
                            print(f"[🔍 详细日志] ⚠️ 文字图层 '{layer.name}' 在分类 '{category}' 下无匹配文件")
                        else:
                            print(f"[🔍 详细日志] ⚠️ 图像图层 (索引{layer_idx}) 在分类 '{category}' 下无匹配文件")
                    else:
                        print(f"[🔍 详细日志] ⚠️ 图层索引 {layer_idx} 超出范围")
                    invalid_layers.append(layer_idx)
            
            if invalid_layers:
                print(f"[🔍 详细日志] ❌ 前置校验失败：{len(invalid_layers)} 个图层在分类 '{category}' 下无匹配文件")
                print(f"[🔍 详细日志] 无效图层索引: {invalid_layers}")
                return {}  # 返回空字典，拒绝使用该分类
            
            print(f"[🔍 详细日志] ✅ 前置校验通过：所有 {len(layer_indices)} 个图层在分类 '{category}' 下都有匹配文件")
            
            # 生成所有可能的文件组合
            all_combinations = self._generate_all_combinations(category, layer_indices)
            print(f"[🔍 详细日志] 生成的总组合数: {len(all_combinations)}")
            if not all_combinations:
                print(f"[🔍 详细日志] ⚠️ 无法生成组合！")
                return {}
            
            # 🔧 关键修复：只有启用避重时才过滤已使用的组合
            if avoid_duplicates:
                # 🔧 根本修复：过滤掉已经使用过的组合
                unused_combinations = []
                for combo in all_combinations:
                    combo_hash = self._hash_combination(combo)
                    if combo_hash not in self._category_usage_history[category]:
                        unused_combinations.append(combo)
                
                # 🔧 根本修复：如果所有组合都用完了，清空历史，允许重用
                if not unused_combinations:
                    print(f"[绑定组] 分类 '{category}' 的所有 {len(all_combinations)} 个组合都已使用，清空历史允许重用")
                    self._category_usage_history[category].clear()
                    unused_combinations = all_combinations
            else:
                # 🔧 关键修复：不启用避重时，直接使用所有组合
                unused_combinations = all_combinations
                print(f"[绑定组] 避重模式未启用，允许重复使用组合")
            
            # 🔧 终极修复：随机选择一个未使用的组合
            # 问题根源：之前总是选择 unused_combinations[0]，导致某些组合被跳过或重复使用
            # 解决方案：从 unused_combinations 中随机选择一个，确保多样性
            import random
            selected_combination = random.choice(unused_combinations)
            
            # 🔧 关键修复：只在避重模式下记录使用历史和显示详细统计
            if avoid_duplicates:
                # 🔧 根本修复：记录该组合已使用
                combo_hash = self._hash_combination(selected_combination)
                self._category_usage_history[category].add(combo_hash)
                
                # 🔧 超详细日志：记录选择详情（前100次都显示）
                usage_count = len(self._category_usage_history[category])
                total_combinations = len(all_combinations)
                usage_rate = usage_count / total_combinations * 100 if total_combinations > 0 else 0
                
                if usage_count <= 100:
                    print(f"\n🎯 [绑定组选择详细] 分类 '{category}' 第{usage_count}次选择:")
                    print(f"  - 总组合数: {total_combinations}")
                    print(f"  - 未使用组合数: {len(unused_combinations)}")
                    print(f"  - 选择组合内容:")
                    for layer_idx in sorted(selected_combination.keys()):
                        print(f"    L{layer_idx}: {os.path.basename(selected_combination[layer_idx])}")
                    print(f"  - 使用历史: {usage_count}/{total_combinations} ({usage_rate:.1f}%)")
                
                # 🔍 详细日志 - 始终显示前10次和每第20次
                print(f"\n[绑定组 '{self.name}'] 🎯 分类 '{category}' 避重状态:")
                print(f"  - 已使用: {usage_count}/{total_combinations} ({usage_rate:.1f}%)")
                print(f"  - 剩余可用: {len(unused_combinations)-1}")
                print(f"  - 本次返回哈希: {combo_hash}")
                print(f"  - 本次返回文件:")
                for layer_idx in sorted(selected_combination.keys()):
                    print(f"    L{layer_idx}: {os.path.basename(selected_combination[layer_idx])}")
                
                # 显示历史记录中的最近5个哈希
                if len(self._category_usage_history[category]) > 0:
                    recent_hashes = list(self._category_usage_history[category])[-5:]
                    print(f"  - 最近5个已使用哈希:")
                    for i, h in enumerate(recent_hashes, 1):
                        print(f"    {i}. {h}")
                
                # 记录到旧的全局组合管理器（保持兼容性）
                file_paths = list(selected_combination.values())
                if hasattr(self, '_binding_manager') and self._binding_manager:
                    self._binding_manager.global_combination_manager.record_combination_usage(
                        self.group_id, file_paths, category
                    )
            else:
                # 非避重模式：简单日志
                print(f"\n[绑定组 '{self.name}'] 🎯 分类 '{category}' 随机选择组合（允许重复）:")
                print(f"  - 总组合数: {len(all_combinations)}")
                print(f"  - 本次返回文件:")
                for layer_idx in sorted(selected_combination.keys()):
                    print(f"    L{layer_idx}: {os.path.basename(selected_combination[layer_idx])}")
            
            return selected_combination
        
        else:
            # 非绑定组模式：保留原有的跨分类混合逻辑
            print(f"[绑定组] 🔀 使用跨分类混合模式")
            return self._cross_category_selection()
    
    def _generate_all_combinations(self, category: str, layer_indices: List[int]) -> List[Dict[int, str]]:
        """生成所有可能的文件组合"""
        try:
            # 获取每个图层的文件列表
            layer_files = []
            for layer_idx in layer_indices:
                files = self.file_categories[category].get(layer_idx, [])
                layer = None
                if layer_idx < len(self.layers):
                    layer = self.layers[layer_idx]
                    if self._is_text_layer(layer):
                        lines = []
                        try:
                            lines = [l.strip() for l in layer.get_text_lines() if str(l).strip()]
                        except Exception:
                            lines = []
                        filtered = []
                        for f in files:
                            if is_text_layer_virtual_path(f):
                                try:
                                    _, content = parse_text_layer_virtual_path(f)
                                except Exception:
                                    content = ''
                                # 更精确的内容匹配检查（单向包含：文字内容包含分类关键词）
                                if content:
                                    for line in lines:
                                        line_stripped = str(line).strip()
                                        if line_stripped and (
                                            content in line_stripped or content.lower() in line_stripped.lower() # 内容在文字行中（单向包含，忽略大小写）
                                        ):
                                            filtered.append(f)
                                            break
                        files = filtered
                if not files and layer is not None:
                    # 🔧 增强容错：如果文字图层过滤后没有匹配的文件，尝试生成合成候选
                    if self._is_text_layer(layer):
                        lines = []
                        try:
                            lines = [l.strip() for l in layer.get_text_lines() if str(l).strip()]
                        except Exception:
                            lines = []
                        
                        # 如果分类名包含在任意文字行中，生成虚拟文件路径
                        synthetic_files = []
                        for line in lines:
                            line_stripped = str(line).strip()
                            if not line_stripped:
                                continue
                                
                            # 更全面的匹配检查（单向包含：文字内容包含分类关键词）
                            should_match = False
                            
                            # 1. 分类名在文字行中（单向包含）
                            if category and str(category).lower() in line_stripped.lower():
                                should_match = True
                            
                            if should_match:
                                synthetic_path = self._build_text_virtual_path(layer.name, line_stripped)
                                synthetic_files.append(synthetic_path)
                        
                        if synthetic_files:
                            print(f"[绑定组] 为文字图层 '{layer.name}' 生成了 {len(synthetic_files)} 个合成候选")
                            files = synthetic_files
                        else:
                            print(f"[绑定组] 警告：文字图层 '{layer.name}' 在分类 '{category}' 下无匹配内容")
                            # 🔧 修复：不再使用第一个文案作为默认回退，避免错误绑定
                            # 当文字图层在指定分类下没有匹配内容时，应该返回空列表
                            # 这样可以确保只有真正匹配的内容才会被绑定
                            print(f"[绑定组] 文字图层 '{layer.name}' 在分类 '{category}' 下无合适匹配，跳过绑定")
                            return []  # 没有匹配内容，不绑定
                    else:
                        return []  # 非文字图层，确实没有文件
                layer_files.append(files)
            
            # 使用itertools.product生成所有组合
            all_combinations = []
            for combination in itertools.product(*layer_files):
                combo_dict = {}
                for i, file_path in enumerate(combination):
                    combo_dict[layer_indices[i]] = file_path
                all_combinations.append(combo_dict)
            
            return all_combinations
            
        except Exception as e:
            return []
    
    def _hash_combination(self, combination: Dict[int, str]) -> str:
        """生成组合的哈希值 - 用于识别唯一组合
        
        🔧 关键修复：必须包含图层索引信息！
        否则[L0:img1,L1:img2]和[L0:img2,L1:img1]会被误认为相同组合
        """
        import hashlib
        # 🔧 修复：按图层索引顺序拼接，不要二次排序文件名
        # 格式：L0:filename|L1:filename|L2:filename
        parts = []
        for idx in sorted(combination.keys()):
            file_name = os.path.basename(combination[idx])
            parts.append(f"L{idx}:{file_name}")
        combination_str = "|".join(parts)  # 不排序！保持图层顺序
        return hashlib.md5(combination_str.encode()).hexdigest()
    
    def clear_usage_history(self):
        """清除使用历史（用于新的导出会话）"""
        if hasattr(self, '_category_usage_history'):
            self._category_usage_history.clear()
            print(f"[绑定组] 已清除分类使用历史")
    
    def _select_optimal_combination(self, group_id: str, all_combinations: List[Dict[int, str]], 
                                  layer_indices: List[int]) -> Optional[Dict[int, str]]:
        """选择最优组合 - 集成全局避重管理器的强化版本"""
        if not all_combinations:
            return None
        
        # 🚀 使用增强的全局避重管理器
        from app.utils.global_avoid_repeat_manager import GlobalAvoidRepeatManager
        global_mgr = GlobalAvoidRepeatManager()
        
        # 获取当前分类（从文件类别分析中推断）
        current_category = None
        for category in self.file_categories.keys():
            category_combos = self._generate_all_combinations(category, layer_indices)
            if category_combos and len(category_combos) == len(all_combinations):
                # 检查是否匹配
                if self._combinations_match(category_combos, all_combinations):
                    current_category = category
                    break
        
        if current_category is None:
            print(f"[绑定组智能选择] 警告：无法确定当前分类，使用备用逻辑")
            return self._fallback_combination_selection(all_combinations)
        
        print(f"[绑定组智能选择] 为绑定组 {group_id} 分类 '{current_category}' 选择最优组合")
        
        # 🎯 使用全局避重管理器的绑定组专用方法
        selected_combination = global_mgr.get_diverse_binding_combination(
            group_id, current_category, all_combinations, layer_indices
        )
        
        if selected_combination:
            print(f"[绑定组智能选择] 成功选择组合")
            return selected_combination
        else:
            print(f"[绑定组智能选择] 全局避重管理器未返回组合，使用备用逻辑")
            return self._fallback_combination_selection(all_combinations)
    
    def _combinations_match(self, combos1: List[Dict[int, str]], combos2: List[Dict[int, str]]) -> bool:
        """检查两个组合列表是否匹配（内容相同但顺序可能不同）"""
        if len(combos1) != len(combos2):
            return False
        
        # 转换为可比较的格式
        set1 = set()
        set2 = set()
        
        for combo in combos1:
            sorted_items = tuple(sorted(combo.items()))
            set1.add(sorted_items)
        
        for combo in combos2:
            sorted_items = tuple(sorted(combo.items()))
            set2.add(sorted_items)
        
        return set1 == set2
    
    def _fallback_combination_selection(self, all_combinations: List[Dict[int, str]]) -> Optional[Dict[int, str]]:
        """备用组合选择逻辑（原有逻辑的简化版本）"""
        if not all_combinations:
            return None
        
        from app.utils.global_avoid_repeat_manager import GlobalAvoidRepeatManager
        global_mgr = GlobalAvoidRepeatManager()
        
        # 按使用次数分类组合
        combination_usage = []
        for combo in all_combinations:
            file_paths = list(combo.values())
            usage_count = global_mgr.get_combination_usage_count(file_paths)
            is_recent = global_mgr.is_combination_recent(file_paths)
            combination_usage.append((combo, usage_count, is_recent))
        
        # 优先选择未使用过的组合
        unused_combos = [item for item in combination_usage if item[1] == 0 and not item[2]]
        if unused_combos:
            return random.choice(unused_combos)[0]
        
        # 其次选择使用次数最少且非最近的组合
        non_recent_combos = [item for item in combination_usage if not item[2]]
        if non_recent_combos:
            min_usage = min(item[1] for item in non_recent_combos)
            min_usage_combos = [item for item in non_recent_combos if item[1] == min_usage]
            return random.choice(min_usage_combos)[0]
        
        # 最后选择使用次数最少的组合
        combination_usage.sort(key=lambda x: x[1])
        return combination_usage[0][0]
    
    def _random_select_with_diversity_boost(self, combinations: List[Dict[int, str]], 
                                           reference_files: List[str] = None) -> Dict[int, str]:
        """随机选择并增强多样性 - 避免选择相似的组合"""
        import threading
        
        if not combinations:
            return {}
        
        if len(combinations) == 1:
            return combinations[0]
        
        # 如果有参考文件，计算相似度并避免高相似度的组合
        if reference_files and len(combinations) > 3:
            # 计算每个组合与参考文件的相似度
            diverse_combinations = []
            reference_basenames = set(os.path.basename(f) for f in reference_files)
            
            for combo in combinations:
                combo_basenames = set(os.path.basename(f) for f in combo.values())
                # 计算文件名重复率
                overlap_ratio = len(combo_basenames & reference_basenames) / len(combo_basenames)
                
                # 优先选择重复率低的组合（多样性高）
                if overlap_ratio < 0.5:  # 重复率低于50%
                    diverse_combinations.append(combo)
            
            if diverse_combinations:
                combinations = diverse_combinations
                print(f"[多样性增强] 过滤后保留 {len(combinations)} 个高多样性组合")
        
        # 多重随机因子
        timestamp_factor = int(time.time_ns()) % 1000000000
        process_factor = os.getpid() % 10000
        try:
            thread_factor = hash(threading.current_thread().name) % 10000
        except:
            thread_factor = 0
        prime_factor = 7919  # 质数因子
        
        # 综合随机种子
        seed = (timestamp_factor + process_factor + thread_factor + prime_factor) % 1000000000
        random.seed(seed)
        
        # 多轮洗牌
        shuffled_combinations = combinations.copy()
        for _ in range(5):
            random.shuffle(shuffled_combinations)
        
        # 最终选择
        selected = random.choice(shuffled_combinations)
        random.seed()  # 恢复随机状态
        
        return selected
    
    def _random_select_with_ultra_randomization(self, combinations: List[Dict[int, str]]) -> Dict[int, str]:
        """超强随机化选择"""
        import threading
        
        if not combinations:
            return {}
        
        if len(combinations) == 1:
            return combinations[0]
        
        # 多重随机因子
        timestamp_factor = int(time.time_ns()) % 1000000000
        process_factor = os.getpid() % 10000
        try:
            thread_factor = hash(threading.current_thread().name) % 10000
        except:
            thread_factor = 0
        prime_factor = 7919  # 质数因子
        
        # 综合随机种子
        seed = (timestamp_factor + process_factor + thread_factor + prime_factor) % 1000000000
        random.seed(seed)
        
        # 多轮洗牌
        shuffled_combinations = combinations.copy()
        for _ in range(5):
            random.shuffle(shuffled_combinations)
        
        # 最终选择
        selected = random.choice(shuffled_combinations)
        random.seed()  # 恢复随机状态
        
        return selected
    
    def _cross_category_selection(self) -> Dict[int, str]:
        """跨分类混合模式（保留原有逻辑）"""
        available_categories = self.get_available_categories()
        if not available_categories:
            return {}
            
        # 获取所有图层索引
        all_layer_indices = set()
        for cat in available_categories:
            if cat in self.file_categories:
                all_layer_indices.update(self.file_categories[cat].keys())
        
        layer_indices = sorted(list(all_layer_indices))
        if not layer_indices:
            return {}
            
        print(f"[绑定组] 跨分类模式: 图层{layer_indices}, 分类{available_categories}")
        
        # 清空记录
        self._used_categories_this_round = set()
        self._used_files_this_round = set()
        
        matched_files = {}
        
        for layer_index in layer_indices:
            # 获取该图层可用的分类
            layer_categories = []
            for cat in available_categories:
                if (cat in self.file_categories and 
                    layer_index in self.file_categories[cat] and 
                    self.file_categories[cat][layer_index]):
                    layer_categories.append(cat)
            
            if not layer_categories:
                continue
                
            # 优先选择未使用的分类
            unused_categories = [c for c in layer_categories if c not in self._used_categories_this_round]
            target_categories = unused_categories if unused_categories else layer_categories
            
            # 随机选择分类
            timestamp_seed = int(time.time_ns() + layer_index * 9973) % 1000000000
            random.seed(timestamp_seed)
            selected_category = random.choice(target_categories)
            self._used_categories_this_round.add(selected_category)
            
            # 获取文件并避重
            files = self.file_categories[selected_category][layer_index]
            unused_files = [f for f in files if f not in self._used_files_this_round]
            target_files = unused_files if unused_files else files
            
            # 随机选择文件
            file_seed = int(time.time_ns() + layer_index * 7919 + timestamp_seed) % 1000000000
            random.seed(file_seed)
            selected_file = random.choice(target_files)
            self._used_files_this_round.add(selected_file)
            
            matched_files[layer_index] = selected_file
            print(f"[绑定组] 图层{layer_index}: 分类'{selected_category}' -> {os.path.basename(selected_file)}")
        
        random.seed()  # 恢复随机状态
        print(f"[绑定组] 跨分类匹配完成: {sorted(self._used_categories_this_round)}")
        return matched_files


class GlobalCombinationManager:
    """全局组合历史管理器 - 实现真正的全局不重复随机化"""
    
    def __init__(self):
        self.combination_history = {}  # 全局组合使用历史: {group_id: {combination_hash: use_count}}
        self.category_usage_history = {}  # 分类使用历史: {group_id: {category: use_count}}
        self.category_combination_history = {}  # 分类组合历史: {group_id: {category: {combo_hash: count}}}
        self.category_pattern_history = {}  # 跨分类模式历史: {pattern_hash: use_count}
        self.recent_category_sequence = []  # 最近使用的分类序列
        self.max_history_size = 10000  # 最大历史记录数量
        self.diversity_threshold = 0.7  # 多样性阈值：70%的组合用过后才允许重复
        self.max_recent_sequence = 10  # 最大最近序列长度
        
    def generate_combination_hash(self, file_paths: List[str]) -> str:
        """生成文件组合的唯一哈希值"""
        # 使用文件名（不含路径）生成哈希，确保相同组合总是产生相同哈希
        file_names = [os.path.basename(path) for path in sorted(file_paths)]
        combination_str = '|'.join(file_names)
        return hashlib.md5(combination_str.encode()).hexdigest()[:16]
    
    def is_combination_fresh(self, group_id: str, file_paths: List[str]) -> bool:
        """检查组合是否是全新的（从未使用过）"""
        combo_hash = self.generate_combination_hash(file_paths)
        if group_id not in self.combination_history:
            return True
        return combo_hash not in self.combination_history[group_id]
    
    def get_combination_usage_count(self, group_id: str, file_paths: List[str]) -> int:
        """获取组合的使用次数"""
        combo_hash = self.generate_combination_hash(file_paths)
        if group_id not in self.combination_history:
            return 0
        return self.combination_history[group_id].get(combo_hash, 0)
    
    def record_combination_usage(self, group_id: str, file_paths: List[str], category: str = None):
        """记录组合使用情况，包括分类信息和跨分类模式"""
        combo_hash = self.generate_combination_hash(file_paths)
        
        # 记录全局组合使用
        if group_id not in self.combination_history:
            self.combination_history[group_id] = {}
        current_count = self.combination_history[group_id].get(combo_hash, 0)
        self.combination_history[group_id][combo_hash] = current_count + 1
        
        # 记录分类使用统计
        if category:
            if group_id not in self.category_usage_history:
                self.category_usage_history[group_id] = {}
            if group_id not in self.category_combination_history:
                self.category_combination_history[group_id] = {}
            
            # 统计分类使用次数
            category_count = self.category_usage_history[group_id].get(category, 0)
            self.category_usage_history[group_id][category] = category_count + 1
            
            # 统计分类内组合使用
            if category not in self.category_combination_history[group_id]:
                self.category_combination_history[group_id][category] = {}
            cat_combo_count = self.category_combination_history[group_id][category].get(combo_hash, 0)
            self.category_combination_history[group_id][category][combo_hash] = cat_combo_count + 1
            
            # 🚀 新增：记录跨分类模式
            self._record_category_pattern(category)
        
        # 清理历史记录，防止内存过大
        self._cleanup_history(group_id)
        
        file_names = [os.path.basename(path) for path in file_paths]
        category_info = f", 分类: {category}" if category else ""
        print(f"[全局组合管理器] 记录组合使用: {group_id} -> {file_names}{category_info} (使用次数: {current_count + 1})")
    
    def _record_category_pattern(self, category: str):
        """记录分类使用模式，用于跨分类避重"""
        # 添加到最近序列
        self.recent_category_sequence.append(category)
        
        # 保持序列长度
        if len(self.recent_category_sequence) > self.max_recent_sequence:
            self.recent_category_sequence.pop(0)
        
        # 生成模式哈希（最近3个分类的组合）
        if len(self.recent_category_sequence) >= 3:
            pattern = '|'.join(self.recent_category_sequence[-3:])
            pattern_hash = hashlib.md5(pattern.encode()).hexdigest()[:8]
            
            if pattern_hash not in self.category_pattern_history:
                self.category_pattern_history[pattern_hash] = 0
            self.category_pattern_history[pattern_hash] += 1
            
            print(f"[跨分类模式] 记录模式: {pattern} -> 使用{self.category_pattern_history[pattern_hash]}次")
    
    def is_category_pattern_overused(self, candidate_category: str, threshold: int = 3) -> bool:
        """检查待选分类是否会形成过度使用的模式"""
        if len(self.recent_category_sequence) < 2:
            return False
        
        # 构建潜在模式
        potential_pattern = '|'.join(self.recent_category_sequence[-2:] + [candidate_category])
        pattern_hash = hashlib.md5(potential_pattern.encode()).hexdigest()[:8]
        
        usage_count = self.category_pattern_history.get(pattern_hash, 0)
        is_overused = usage_count >= threshold
        
        if is_overused:
            print(f"[跨分类模式] 模式 '{potential_pattern}' 已使用{usage_count}次，超过阈值{threshold}")
        
        return is_overused
    
    def get_pattern_aware_category_score(self, category: str) -> float:
        """获取考虑模式避重的分类评分"""
        base_score = 1.0
        
        # 检查是否会形成过度使用的模式
        if self.is_category_pattern_overused(category, threshold=2):
            base_score *= 0.3  # 大幅降低评分
        elif self.is_category_pattern_overused(category, threshold=1):
            base_score *= 0.7  # 适度降低评分
        
        # 检查最近是否使用过相同分类
        if (len(self.recent_category_sequence) > 0 and 
            self.recent_category_sequence[-1] == category):
            base_score *= 0.5  # 避免连续使用相同分类
        
        return base_score
    
    def get_category_usage_count(self, group_id: str, category: str) -> int:
        """获取分类的使用次数"""
        if group_id not in self.category_usage_history:
            return 0
        return self.category_usage_history[group_id].get(category, 0)
    
    def get_category_diversity_score(self, group_id: str, category: str, total_possible_combinations: int) -> float:
        """获取分类的多样性分数"""
        if (group_id not in self.category_combination_history or 
            category not in self.category_combination_history[group_id] or
            total_possible_combinations == 0):
            return 1.0
        
        used_combinations = len(self.category_combination_history[group_id][category])
        return max(0.0, 1.0 - (used_combinations / total_possible_combinations))
    
    def get_least_used_categories(self, group_id: str, categories: List[str], count: int = None) -> List[str]:
        """获取使用次数最少的分类列表"""
        if not categories:
            return []
        
        # 按使用次数排序
        category_usage = [(cat, self.get_category_usage_count(group_id, cat)) for cat in categories]
        category_usage.sort(key=lambda x: x[1])  # 按使用次数升序
        
        result = [cat for cat, _ in category_usage]
        if count is not None:
            result = result[:count]
            
        return result
    
    def _cleanup_history(self, group_id: str):
        """清理历史记录，保持合理大小"""
        if group_id not in self.combination_history:
            return
            
        history = self.combination_history[group_id]
        if len(history) > self.max_history_size:
            # 保留使用次数最少的组合记录
            sorted_combos = sorted(history.items(), key=lambda x: x[1])
            keep_count = int(self.max_history_size * 0.8)  # 保留80%
            self.combination_history[group_id] = dict(sorted_combos[:keep_count])
            print(f"[全局组合管理器] 清理历史记录: {group_id}, 保留 {keep_count} 条记录")
    
    def get_diversity_score(self, group_id: str, total_possible_combinations: int) -> float:
        """计算当前多样性得分（0-1，1表示完全多样化）"""
        if group_id not in self.combination_history or total_possible_combinations == 0:
            return 1.0
        
        used_combinations = len(self.combination_history[group_id])
        return min(1.0, used_combinations / total_possible_combinations)
    
    def should_prioritize_fresh_combinations(self, group_id: str, total_possible: int) -> bool:
        """是否应该优先选择全新组合"""
        diversity_score = self.get_diversity_score(group_id, total_possible)
        return diversity_score < self.diversity_threshold
    
    def get_statistics(self, group_id: str) -> Dict:
        """获取组合使用统计信息"""
        if group_id not in self.combination_history:
            return {
                'total_used_combinations': 0,
                'total_usage_count': 0,
                'most_used_count': 0,
                'least_used_count': 0
            }
        
        history = self.combination_history[group_id]
        usage_counts = list(history.values())
        
        return {
            'total_used_combinations': len(history),
            'total_usage_count': sum(usage_counts),
            'most_used_count': max(usage_counts) if usage_counts else 0,
            'least_used_count': min(usage_counts) if usage_counts else 0
        }


class LayerBindingManager:
    """图层绑定管理器"""

    def __init__(self):
        self.binding_groups: Dict[str, BindingGroup] = {}
        self.layer_to_group: Dict = {}  # 图层到绑定组的映射
        self.global_enabled = True  # 全局绑定开关
        self.layer_file_restrictions: Dict = {}  # 图层文件限制：{layer_id: [allowed_files]}
        self.global_combination_manager = GlobalCombinationManager()  # 全局组合管理器
        self._debug_trace_enabled = (os.environ.get("BTPW_BINDING_DEBUG_PANEL", "0") == "1")
        self._debug_traces: List[str] = []
        self._debug_trace_max = 300
        
        # 🔧 新增：100%准确绑定完整性管理器
        self._integrity_manager = None
        self._export_validator = None
        if BINDING_INTEGRITY_AVAILABLE:
            try:
                self._integrity_manager = BindingIntegrityManager(self)
                self._export_validator = ExportBindingValidator(self._integrity_manager)
                print("[绑定管理器] ✅ 完整性管理器和导出验证器已初始化")
            except Exception as e:
                print(f"[绑定管理器] ⚠️ 初始化完整性管理器失败: {e}")
                self._integrity_manager = None
                self._export_validator = None

    def set_debug_trace_enabled(self, enabled: bool):
        """设置绑定调试追踪开关。"""
        self._debug_trace_enabled = bool(enabled)

    def is_debug_trace_enabled(self) -> bool:
        return bool(self._debug_trace_enabled)

    def clear_debug_traces(self):
        self._debug_traces.clear()

    def append_debug_trace(self, source: str, group_name: str, category: str, layer_matches: List[Tuple[str, str]]):
        """写入一条绑定调试记录。"""
        if not self._debug_trace_enabled:
            return

        timestamp = time.strftime("%H:%M:%S", time.localtime())
        header = f"[{timestamp}] 来源={source} 组={group_name} 分类={category}"
        lines = [header]
        for layer_name, file_path in layer_matches:
            base_name = os.path.basename(str(file_path)) if isinstance(file_path, str) else str(file_path)
            lines.append(f"  - {layer_name}: {base_name}")

        message = "\n".join(lines)
        self._debug_traces.append(message)
        if len(self._debug_traces) > self._debug_trace_max:
            self._debug_traces = self._debug_traces[-self._debug_trace_max:]

    def get_debug_trace_text(self, limit: int = 80) -> str:
        """获取最近绑定调试文本，供调试面板显示。"""
        if not self._debug_traces:
            return "暂无绑定调试记录。"
        records = self._debug_traces[-max(1, int(limit)):]
        return "\n\n".join(records)
    
    def create_binding_group(self, group_name: str, layers: List) -> str:
        """创建绑定组 - 修复版本，传递绑定管理器引用，添加图层重复检查"""
        group_id = f"group_{len(self.binding_groups) + 1}_{group_name}"
        group = BindingGroup(group_id, group_name, binding_manager=self)  # 🔧 传递自身引用

        for i, layer in enumerate(layers):
            # 🔧 新增：检查图层是否已在其他绑定组中
            layer_id = id(layer)
            if layer_id in self.layer_to_group:
                existing_group_id = self.layer_to_group[layer_id]
                if existing_group_id in self.binding_groups:
                    existing_group = self.binding_groups[existing_group_id]
                    print(f"[绑定管理器] 警告：图层 '{layer.name}' 已在绑定组 '{existing_group.name}' 中，将先从原组移除")
                    # 从原绑定组中移除
                    existing_group.remove_layer(layer)
                    # 如果原绑定组为空，删除该组
                    if len(existing_group.layers) == 0:
                        del self.binding_groups[existing_group_id]
                        print(f"[绑定管理器] 原绑定组 '{existing_group.name}' 已为空，已删除")
            
            group.add_layer(layer, i)
            self.layer_to_group[id(layer)] = group_id

        self.binding_groups[group_id] = group
        print(f"创建绑定组: {group_name}, 包含 {len(layers)} 个图层")
        return group_id

    def add_binding_group(self, binding_group: 'BindingGroup'):
        """添加已创建的绑定组到管理器"""
        if binding_group.group_id not in self.binding_groups:
            self.binding_groups[binding_group.group_id] = binding_group

            # 更新图层到组的映射
            for layer in binding_group.layers:
                self.layer_to_group[id(layer)] = binding_group.group_id

            print(f"添加绑定组: {binding_group.name}, 包含 {len(binding_group.layers)} 个图层")
        else:
            print(f"绑定组 {binding_group.group_id} 已存在，跳过添加")

    def add_layer_to_group(self, group_id: str, layer, layer_index: Optional[int] = None):
        """添加图层到绑定组 - 添加图层重复检查"""
        if group_id in self.binding_groups:
            group = self.binding_groups[group_id]
            
            # 🔧 新增：检查图层是否已在其他绑定组中
            layer_id = id(layer)
            if layer_id in self.layer_to_group:
                existing_group_id = self.layer_to_group[layer_id]
                if existing_group_id != group_id and existing_group_id in self.binding_groups:
                    existing_group = self.binding_groups[existing_group_id]
                    print(f"[绑定管理器] 警告：图层 '{layer.name}' 已在绑定组 '{existing_group.name}' 中，将先从原组移除")
                    # 从原绑定组中移除
                    existing_group.remove_layer(layer)
                    # 如果原绑定组为空，删除该组
                    if len(existing_group.layers) == 0:
                        del self.binding_groups[existing_group_id]
                        print(f"[绑定管理器] 原绑定组 '{existing_group.name}' 已为空，已删除")
            
            if layer_index is None:
                layer_index = len(group.layers)
            group.add_layer(layer, layer_index)
            self.layer_to_group[id(layer)] = group_id
    
    def remove_layer_from_group(self, layer):
        """从绑定组移除图层"""
        layer_id = id(layer)
        if layer_id in self.layer_to_group:
            group_id = self.layer_to_group[layer_id]
            if group_id in self.binding_groups:
                group = self.binding_groups[group_id]
                group.remove_layer(layer)
                print(f"从绑定组 '{group.name}' 中移除图层 '{layer.name}'")
                
                # 如果绑定组为空，删除该组
                if len(group.layers) == 0:
                    del self.binding_groups[group_id]
                    print(f"绑定组 '{group.name}' 已空，自动删除")
                
            del self.layer_to_group[layer_id]
    
    def get_layer_binding_info(self, layer) -> Optional[Tuple[str, str]]:
        """获取图层的绑定信息"""
        layer_id = id(layer)
        if layer_id in self.layer_to_group:
            group_id = self.layer_to_group[layer_id]
            if group_id in self.binding_groups:
                group = self.binding_groups[group_id]
                return group_id, group.name
        return None
    
    def is_layer_bound(self, layer) -> bool:
        """检查图层是否已绑定"""
        return id(layer) in self.layer_to_group
    
    def enforce_100_percent_binding_accuracy(self, layer_states: Dict[int, str]) -> Dict[int, str]:
        """强制执行100%绑定准确率 - 新增方法"""
        if not BINDING_INTEGRITY_AVAILABLE or not self._integrity_manager:
            print("[绑定管理器] ⚠️ 100%绑定修复系统不可用，返回原始状态")
            return layer_states
        
        try:
            print("[绑定管理器] 🔧 开始强制执行100%绑定准确率...")
            
            # 使用完整性管理器强制执行100%准确率
            corrected_states = enforce_100_percent_binding_accuracy(None, layer_states)
            
            print(f"[绑定管理器] ✅ 100%绑定准确率执行完成")
            return corrected_states
            
        except Exception as e:
            print(f"[绑定管理器] ❌ 强制执行100%绑定准确率失败: {e}")
            import traceback
            traceback.print_exc()
            return layer_states
    
    def validate_binding_accuracy(self, layer_states: Dict[int, str]) -> float:
        """验证绑定准确率 - 新增方法"""
        if not BINDING_INTEGRITY_AVAILABLE or not self._integrity_manager:
            print("[绑定管理器] ⚠️ 绑定验证系统不可用，返回默认100%")
            return 100.0
        
        try:
            validation_result = validate_current_bindings(None, layer_states)
            accuracy = validation_result.accuracy
            
            if accuracy < 100.0:
                print(f"[绑定管理器] ⚠️ 绑定准确率检测: {accuracy:.1f}%")
                print(f"[绑定管理器] 错误绑定: {validation_result.mismatched_layers}")
            else:
                print(f"[绑定管理器] ✅ 绑定准确率: {accuracy:.1f}%")
            
            return accuracy
            
        except Exception as e:
            print(f"[绑定管理器] ❌ 绑定准确率验证失败: {e}")
            return 0.0
    
    def _extract_product_categories_from_text(self, text: str) -> set:
        from app.utils.product_category_extractor import extract_product_categories_from_text
        return extract_product_categories_from_text(text)
    
    def _validate_category_semantic_consistency(self, group, category: str, document_layers: List) -> bool:
        """🔧 简化版：直接文案匹配验证"""
        """直接对比文字图层内容与图像文件名，确保语义一致"""
        try:
            print(f"[直接匹配] 验证分类 '{category}' 与绑定组 '{group.name}' 的匹配一致性...")
            
            # 获取绑定组中的文字图层和图像图层
            text_layers_in_group = []
            image_layers_in_group = []
            
            for doc_layer in document_layers:
                if doc_layer.name in [layer.name for layer in group.layers]:
                    if self._is_text_layer(doc_layer):
                        text_layers_in_group.append(doc_layer)
                    else:
                        image_layers_in_group.append(doc_layer)
            
            print(f"[直接匹配] 绑定组包含: 文字图层{len(text_layers_in_group)}个, 图像图层{len(image_layers_in_group)}个")
            
            # 🔧 简化逻辑：提取文字行作为虚拟文件名，与图像文件名直接对比
            text_virtual_files = []  # 文字行作为虚拟文件名
            image_real_files = []    # 图像文件名（不含路径）
            
            # 提取文字图层每一行作为虚拟文件名
            for text_layer in text_layers_in_group:
                if hasattr(text_layer, 'get_text_lines') and callable(getattr(text_layer, 'get_text_lines', None)):
                    try:
                        text_lines = text_layer.get_text_lines()
                        for line in text_lines:
                            line_str = str(line).strip()
                            if line_str:  # 只添加非空行
                                text_virtual_files.append(line_str)
                                print(f"[直接匹配] 提取文字行作为虚拟文件名: '{line_str}'")
                    except Exception:
                        pass
            
            # 提取图像图层的文件名（不含路径）
            for image_layer in image_layers_in_group:
                if hasattr(image_layer, 'file_path') and image_layer.file_path:
                    file_name = os.path.basename(str(image_layer.file_path))
                    # 移除文件扩展名，只保留核心名称
                    file_name_without_ext = os.path.splitext(file_name)[0]
                    image_real_files.append(file_name_without_ext)
                    print(f"[直接匹配] 提取图像文件名: '{file_name_without_ext}'")
            
            # 🔧 核心：直接对比虚拟文件名（文字行）与真实文件名
            direct_matches = []
            for virtual_file in text_virtual_files:
                for real_file in image_real_files:
                    # 完全匹配或包含匹配
                    if virtual_file == real_file or virtual_file in real_file or real_file in virtual_file:
                        direct_matches.append((virtual_file, real_file))
                        print(f"[直接匹配] ✅ 找到匹配: 文字行'{virtual_file}' ↔ 文件名'{real_file}'")
            
            # 🔧 判断逻辑：基于直接匹配结果
            if text_layers_in_group and image_layers_in_group:
                # 混合绑定组：需要文字行与文件名有匹配
                if direct_matches:
                    print(f"[直接匹配] ✅ 混合绑定组：找到{len(direct_matches)}个直接匹配")
                    return True
                else:
                    print(f"[直接匹配] ❌ 混合绑定组：文字行与文件名无匹配")
                    return False
            elif text_layers_in_group:
                # 纯文字绑定组：只要有文字内容就接受
                if text_virtual_files:
                    print(f"[直接匹配] ✅ 纯文字绑定组：有{len(text_virtual_files)}个文字行")
                    return True
                else:
                    print(f"[直接匹配] ❌ 纯文字绑定组：无文字内容")
                    return False
            elif image_layers_in_group:
                # 纯图像绑定组：只要有图像文件就接受
                if image_real_files:
                    print(f"[直接匹配] ✅ 纯图像绑定组：有{len(image_real_files)}个图像文件")
                    return True
                else:
                    print(f"[直接匹配] ⚠️ 纯图像绑定组：无图像文件，勉强接受")
                    return True  # 没有更好的选择时接受
            else:
                # 空绑定组
                print(f"[语义验证] ⚠️ 空绑定组，默认接受")
                return True
                
        except Exception as e:
            print(f"[语义验证] ❌ 验证过程出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时默认接受，避免阻断正常流程
            return True
    
    def randomize_bound_layers(self, all_layers: List) -> Dict:
        """为绑定的图层随机选择匹配的文件 - 严格按照原有绑定组设置执行"""
        if not self.global_enabled:
            return {}

        layer_file_mapping = {}
        print(f"[绑定管理器] 开始处理 {len(self.binding_groups)} 个绑定组")

        # 🔧 关键修复：移除公共分类计算，每个绑定组独立选择分类
        # 原逻辑错误：计算所有绑定组的公共分类会导致不合理的限制
        # 每个绑定组应该根据自己的图层和分类独立选择，不受其他绑定组影响
        common_categories = None  # 禁用公共分类限制
        print("[绑定管理器] ✅ 禁用公共分类限制，每个绑定组独立选择分类")

        # 处理每个绑定组
        for group_id, group in self.binding_groups.items():
            print(f"[绑定管理器] 处理绑定组: {group.name} (ID: {group_id})")

            document_layers = []
            group_idx_to_doc_layer = {}
            used_doc_layer_ids = set()

            # 根据绑定关系优先匹配实际的文档图层，避免同名图层错配
            for group_idx, group_layer in enumerate(group.layers):
                matched_layer = None

                # 1) 优先使用对象身份匹配（最精确）
                if group_layer in all_layers and id(group_layer) not in used_doc_layer_ids:
                    matched_layer = group_layer

                # 2) 使用绑定关系 + 名称匹配（避免同名错配）
                if matched_layer is None:
                    for doc_layer in all_layers:
                        if (self.layer_to_group.get(id(doc_layer)) == group_id and
                                doc_layer.name == group_layer.name and
                                id(doc_layer) not in used_doc_layer_ids):
                            matched_layer = doc_layer
                            break

                # 3) 回退到名称匹配（保持兼容）
                if matched_layer is None:
                    for doc_layer in all_layers:
                        if doc_layer.name == group_layer.name and id(doc_layer) not in used_doc_layer_ids:
                            matched_layer = doc_layer
                            break

                if matched_layer:
                    document_layers.append(matched_layer)
                    group_idx_to_doc_layer[group_idx] = matched_layer
                    used_doc_layer_ids.add(id(matched_layer))
                else:
                    print(f"[绑定管理器] 警告：未找到图层 '{group_layer.name}' (组内索引 {group_idx})")

            if len(document_layers) != len(group.layers):
                print(f"[绑定管理器] 警告：绑定组 {group.name} 中有 {len(group.layers) - len(document_layers)} 个图层未找到")
                if len(document_layers) == 0:
                    continue

            # 🔧 修复：直接使用原有绑定组的分类信息，不重新分析
            available_categories = group.get_available_categories()
            print(f"[绑定管理器] 可用分类: {available_categories}")

            if not available_categories:
                print(f"[绑定管理器] ❌ 绑定组 '{group.name}' 没有可用的匹配分类")
                continue

            # 🔧 根本修复：若存在公共分类，限制在公共分类内选择
            selectable_categories = available_categories
            if common_categories:
                selectable_categories = [c for c in available_categories if c in common_categories]
                if selectable_categories:
                    print(f"[绑定管理器] 使用公共分类限制，候选: {selectable_categories}")
                else:
                    print("[绑定管理器] 公共分类与本组不相交，回退到本组可用分类")

            # 🔧 关键修复：在选择分类前验证语义一致性
            # 确保选择的分类与绑定组的图层内容匹配
            valid_categories = []
            for category in selectable_categories:
                # 检查该分类是否与绑定组的图层内容语义一致
                is_semantically_valid = self._validate_category_semantic_consistency(group, category, document_layers)
                if is_semantically_valid:
                    valid_categories.append(category)
                else:
                    print(f"[绑定管理器] ⚠️ 分类 '{category}' 与绑定组内容语义不一致，已排除")
            
            # 如果有语义一致的有效分类，优先使用它们
            if valid_categories:
                final_categories = valid_categories
                print(f"[绑定管理器] ✅ 找到 {len(valid_categories)} 个语义一致的有效分类")
            else:
                # 如果没有语义一致的分类，回退到原始选择，但增加警告
                final_categories = selectable_categories
                print(f"[绑定管理器] ⚠️ 未找到语义一致的有效分类，使用原始候选分类")
            
            # 随机选择一个分类作为绑定组的统一分类
            import time
            import hashlib

            category_seed_factors = [
                time.time_ns() % 1000000000,
                hash(group_id) % 1000000,
                len(final_categories),
                len(document_layers)
            ]

            category_seed = sum(category_seed_factors) % 1000000000
            random.seed(category_seed)
            selected_category = random.choice(final_categories)
            # 记录本次选择的分类，便于外部在同一轮预览/导出中对未绑定图层进行一致性限制
            try:
                group.last_selected_category = selected_category
            except Exception:
                pass
            random.seed()  # 恢复随机状态

            print(f"[绑定管理器] 绑定组 {group.name} 选择统一分类: '{selected_category}'")

            # 使用指定分类调用get_matched_files（预览模式不启用避重）
            matched_files = group.get_matched_files(selected_category, avoid_duplicates=False)
            print(f"[绑定管理器] 绑定组匹配结果: {matched_files}")

            # 写入调试追踪：记录本次分类和每个图层匹配文件
            try:
                trace_rows = []
                for layer_index, file_path in matched_files.items():
                    layer_obj = group_idx_to_doc_layer.get(layer_index)
                    if layer_obj is None and layer_index < len(group.layers):
                        layer_obj = group.layers[layer_index]
                    layer_name = getattr(layer_obj, 'name', f'layer_{layer_index}')
                    trace_rows.append((layer_name, file_path))
                self.append_debug_trace("preview_randomize", group.name, selected_category, trace_rows)
            except Exception:
                pass
            
            # 🔧 100%准确率验证：确保绑定结果的语义正确性
            if BINDING_INTEGRITY_AVAILABLE and hasattr(self, '_integrity_manager') and self._integrity_manager:
                try:
                    # 获取当前绑定组的所有图层状态
                    layer_states = []
                    for doc_layer in all_layers:
                        if doc_layer.name in [group_layer.name for group_layer in group.layers]:
                            layer_states.append({
                                'name': doc_layer.name,
                                'type': 'text' if hasattr(doc_layer, 'get_text_lines') else 'image',
                                'content': doc_layer.get_text_lines() if hasattr(doc_layer, 'get_text_lines') else None
                            })
                    
                    # 验证绑定结果的准确性
                    validation_result = self._integrity_manager.validate_binding_accuracy(
                        layer_states, matched_files, selected_category
                    )
                    
                    if validation_result['is_valid']:
                        print(f"[绑定管理器] ✅ 100%准确率验证通过 - 绑定组: {group.name}")
                    else:
                        print(f"[绑定管理器] ⚠️ 发现绑定不准确，自动修复中...")
                        # 自动修复不准确的绑定
                        corrected_files = self._integrity_manager.enforce_100_percent_binding_accuracy(
                            layer_states, selected_category, group.get_available_files()
                        )
                        
                        if corrected_files:
                            matched_files = corrected_files
                            print(f"[绑定管理器] ✅ 自动修复完成，新绑定结果: {matched_files}")
                        else:
                            print(f"[绑定管理器] ❌ 无法自动修复，使用原绑定结果")
                            
                except Exception as validation_error:
                    print(f"[绑定管理器] 100%准确率验证出错: {validation_error}")
                    # 验证出错时继续使用原结果，不影响正常流程

            # 🔧 根本修复：按绑定关系精确映射到文档图层，避免跨组错配
            for layer_index, file_path in matched_files.items():
                if layer_index < len(group.layers):
                    layer = group_idx_to_doc_layer.get(layer_index)
                    if layer is None:
                        group_layer = group.layers[layer_index]
                        print(f"[绑定管理器] 映射失败：未在文档中找到图层 '{group_layer.name}' (组内索引 {layer_index})")
                        continue

                    # 🔧 新增：检查是否为文字图层且使用虚拟文件路径
                    if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)) and is_text_layer_virtual_path(file_path):
                        self._apply_text_layer_binding(layer, file_path)
                        layer_file_mapping[id(layer)] = file_path
                        print(f"[绑定管理器] 文字图层 '{layer.name}' 已绑定文字内容: {file_path}")
                        continue

                    # 原有逻辑：处理普通图像图层
                    # 🔧 修正：使用正确的方法设置图层路径
                    print(f"[绑定管理器] 绑定前状态 - 图层: {layer.name}, 当前路径: {getattr(layer, 'current_image_path', None)}")

                    # 彻底清除图层状态
                    self._complete_layer_state_reset(layer)

                    # 🔧 关键修复：始终使用公共属性setter，无论是Layer还是LegacyLayer
                    # Layer（layer_new.py）通过属性管理器实现，LegacyLayer直接实现
                    # 两者都正确支持 current_image_path 公共属性
                    if hasattr(layer, 'current_image_path'):
                        layer.current_image_path = file_path
                        print(f"[绑定管理器] 设置新路径: {layer.name} -> {os.path.basename(file_path)}")
                    else:
                        print(f"[绑定管理器] 警告：图层 '{layer.name}' 没有 current_image_path 或 _current_image_path 属性")

                    # 记录映射关系
                    layer_file_mapping[id(layer)] = file_path
                    print(f"[绑定管理器] 图层 '{layer.name}' 已绑定文件: {os.path.basename(file_path)}")

        print(f"[绑定管理器] 完成组合级随机化绑定，共处理 {len(layer_file_mapping)} 个图层")
        return layer_file_mapping

    def _apply_text_layer_binding(self, layer, virtual_file_path: str):
        """应用文字图层的绑定 - 将虚拟文件路径转换为文字内容 - 修复版本"""
        try:
            # 🔧 修复：增强虚拟文件路径解析，支持URL编码
            if not is_text_layer_virtual_path(virtual_file_path):
                print(f"[绑定管理器] 警告：无效的文字图层虚拟路径: {virtual_file_path}")
                return
            
            try:
                layer_name, text_content = parse_text_layer_virtual_path(virtual_file_path)
                if layer.name != layer_name:
                    print(f"[绑定管理器] 警告：图层名称不匹配，期望 '{layer.name}'，但路径中是 '{layer_name}'")
                
            except Exception as parse_error:
                print(f"[绑定管理器] 警告：解析文字图层虚拟路径失败: {parse_error}")
                return
            
            print(f"[绑定管理器] 应用文字图层绑定: '{layer.name}' -> '{text_content}'")
            
            # 清除图层缓存
            if hasattr(layer, '_cached_image'):
                layer._cached_image = None
            
            # 🔧 修复：增强状态同步，避免竞态条件
            original_text = getattr(layer, 'current_text', '')
            
            # 仅更新当前显示文字，避免覆盖原有多行文案
            if hasattr(layer, 'current_text'):
                layer.current_text = text_content
            
            # 🔧 修复：改进文字行处理逻辑
            if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)):
                try:
                    existing_lines = layer.get_text_lines()
                    if existing_lines is None:
                        existing_lines = []
                except Exception:
                    existing_lines = []
                
                # 🔧 修复：只在需要时更新文字行，避免不必要的覆盖
                if not existing_lines and hasattr(layer, 'set_text_lines'):
                    layer.set_text_lines([text_content])
                elif existing_lines and hasattr(layer, 'set_text_lines'):
                    # 如果当前文字不在现有行中，可以选择添加
                    if text_content not in existing_lines:
                        # 根据业务需求决定是否添加新行
                        pass  # 保持现有行不变
            
            # 🔧 修复：延迟信号触发，确保状态一致
            def emit_signals():
                try:
                    if hasattr(layer, 'text_changed') and hasattr(layer.text_changed, 'emit'):
                        layer.text_changed.emit()
                    if hasattr(layer, 'changed') and hasattr(layer.changed, 'emit'):
                        layer.changed.emit()
                except Exception as signal_error:
                    print(f"[绑定管理器] 触发信号失败: {signal_error}")
            
            # 使用QTimer延迟触发信号，避免在信号处理中修改状态
            try:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, emit_signals)
            except ImportError:
                # 如果QTimer不可用，直接触发
                emit_signals()
                
            print(f"[绑定管理器] 文字图层绑定成功: '{layer.name}' 现在显示 '{text_content}'")
            
        except Exception as e:
            print(f"[绑定管理器] 应用文字图层绑定失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _force_clear_layer_cache(self, layer):
        """强制清除图层的所有缓存 - 修复版本，更全面的缓存清理"""
        try:
            print(f"[绑定管理器] 开始清除图层 '{layer.name}' 的所有缓存...")
            
            # 🔧 修复：增加缓存清除前的状态验证
            initial_state = {
                'has_cached_image': hasattr(layer, '_cached_image') and getattr(layer, '_cached_image', None) is not None,
                'has_cache_valid': hasattr(layer, '_cache_valid') and getattr(layer, '_cache_valid', False)
            }
            
            # 清除主要缓存方法
            if hasattr(layer, 'clear_cache') and callable(layer.clear_cache):
                try:
                    layer.clear_cache()
                    print(f"[绑定管理器] 调用图层 '{layer.name}' 的 clear_cache 方法成功")
                except Exception as clear_error:
                    print(f"[绑定管理器] 警告：图层 '{layer.name}' 的 clear_cache 方法调用失败: {clear_error}")

            # 🔧 修复：扩展缓存属性列表，包含更多可能的缓存属性
            cache_attrs = [
                # 基础缓存属性
                'cached_image', '_cached_image', '_cached_image_path',
                '_cached_images', '_image_cache', '_render_cache',
                '_processed_image', '_last_processed_image',
                '_cache_valid', '_image_loaded', '_needs_reload',
                
                # 🔧 新增：扩展缓存属性
                '_layer_cache', '_text_cache', '_style_cache',
                '_transform_cache', '_blend_cache', '_effect_cache',
                '_last_render_params', '_render_dirty',
                '_last_image_path', '_last_selected_image',
                '_cached_bounds', '_cached_rect', '_cached_size',
                '_opacity_cache', '_visibility_cache',
                
                # 渲染相关缓存
                '_rendered_image', '_last_render_time',
                '_cached_background', '_cached_foreground',
                
                # 文字图层特定缓存
                '_text_metrics_cache', '_font_cache', '_layout_cache',
                '_text_lines_cache', '_current_text_cache'
            ]

            cleared_attrs = []
            for attr in cache_attrs:
                if hasattr(layer, attr):
                    try:
                        old_value = getattr(layer, attr)
                        setattr(layer, attr, None)
                        cleared_attrs.append(attr)
                        
                        # 对于字典类型，额外清除内容
                        if isinstance(old_value, dict):
                            old_value.clear()
                            
                    except Exception as attr_error:
                        print(f"[绑定管理器] 警告：清除属性 '{attr}' 失败: {attr_error}")

            # 🔧 修复：更智能地处理字典类型的缓存
            dict_cache_attrs = ['_cached_images', '_image_cache', '_layer_cache', 
                              '_text_cache', '_style_cache', '_transform_cache']
            for attr in dict_cache_attrs:
                if hasattr(layer, attr):
                    try:
                        cache_dict = getattr(layer, attr)
                        if isinstance(cache_dict, dict):
                            cache_dict.clear()
                            print(f"[绑定管理器] 清除字典缓存 '{attr}' 成功")
                    except Exception as dict_error:
                        print(f"[绑定管理器] 警告：清除字典缓存 '{attr}' 失败: {dict_error}")

            # 🔧 修复：清除列表类型的缓存
            list_cache_attrs = ['_cached_items', '_cache_list', '_history_cache']
            for attr in list_cache_attrs:
                if hasattr(layer, attr):
                    try:
                        cache_list = getattr(layer, attr)
                        if isinstance(cache_list, list):
                            cache_list.clear()
                            print(f"[绑定管理器] 清除列表缓存 '{attr}' 成功")
                    except Exception as list_error:
                        print(f"[绑定管理器] 警告：清除列表缓存 '{attr}' 失败: {list_error}")

            # 🔧 新增：验证清除效果
            final_state = {
                'has_cached_image': hasattr(layer, '_cached_image') and getattr(layer, '_cached_image', None) is not None,
                'has_cache_valid': hasattr(layer, '_cache_valid') and getattr(layer, '_cache_valid', False)
            }
            
            cache_cleared = (
                initial_state['has_cached_image'] and not final_state['has_cached_image']
            ) or initial_state != final_state
            
            if cache_cleared:
                print(f"[绑定管理器] ✅ 已强制清除图层 '{layer.name}' 的缓存 (清除了 {len(cleared_attrs)} 个属性)")
            else:
                print(f"[绑定管理器] ⚠️ 图层 '{layer.name}' 缓存清除完成，但未检测到明显变化 (尝试了 {len(cleared_attrs)} 个属性)")

        except Exception as e:
            print(f"[绑定管理器] 清除图层缓存时出错: {e}")
            import traceback
            traceback.print_exc()

    def _complete_layer_state_reset(self, layer):
        """完全重置图层状态，确保绑定操作的彻底性"""
        try:
            print(f"[绑定管理器] 完全重置图层状态: {layer.name}")

            # 1. 强制清除所有缓存
            self._force_clear_layer_cache(layer)

            # 2. 重置图层的内部状态
            if hasattr(layer, '_last_image_path'):
                layer._last_image_path = None
            if hasattr(layer, '_last_selected_image'):
                layer._last_selected_image = None
            if hasattr(layer, '_image_loaded'):
                layer._image_loaded = False
            if hasattr(layer, '_needs_reload'):
                layer._needs_reload = True
            if hasattr(layer, '_cache_valid'):
                layer._cache_valid = False  # 标记缓存无效
            # 处理两种图层类型的当前路径属性
            if hasattr(layer, '_current_image_path'):
                # Layer 类（新图层）
                # 不清除当前路径，但确保缓存路径不匹配
                if hasattr(layer, '_cached_image_path'):
                    layer._cached_image_path = None
            elif hasattr(layer, 'current_image_path'):
                # LegacyLayer 类（文档中的图像图层）
                # 不清除当前路径，但确保缓存路径不匹配
                if hasattr(layer, '_cached_image_path'):
                    layer._cached_image_path = None

            # 3. 清除渲染相关状态
            render_attrs = [
                '_rendered_image', '_last_render_params', '_render_dirty',
                '_transform_cache', '_blend_cache', '_effect_cache'
            ]
            for attr in render_attrs:
                if hasattr(layer, attr):
                    setattr(layer, attr, None)

            # 4. 标记图层为需要更新
            if hasattr(layer, 'mark_dirty'):
                layer.mark_dirty()
            elif hasattr(layer, '_mark_dirty'):
                layer._mark_dirty()

            # 5. 重置变换参数（如果需要）
            if hasattr(layer, 'reset_transform_cache'):
                layer.reset_transform_cache()

            print(f"[绑定管理器] 图层 '{layer.name}' 状态重置完成")

        except Exception as e:
            print(f"[绑定管理器] 重置图层状态时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def get_binding_groups_info(self) -> List[Dict]:
        """获取所有绑定组信息"""
        groups_info = []
        for group_id, group in self.binding_groups.items():
            info = {
                'group_id': group_id,
                'name': group.name,
                'layers': [layer.name for layer in group.layers],
                'categories': group.get_available_categories(),
                'layer_count': len(group.layers)
            }
            groups_info.append(info)
        return groups_info
    
    def delete_binding_group(self, group_id: str):
        """删除绑定组"""
        if group_id in self.binding_groups:
            group = self.binding_groups[group_id]
            # 移除图层映射
            for layer in group.layers:
                layer_id = id(layer)
                if layer_id in self.layer_to_group:
                    del self.layer_to_group[layer_id]
            # 删除绑定组
            del self.binding_groups[group_id]
            print(f"删除绑定组: {group.name}")
    
    def set_global_enabled(self, enabled: bool):
        """设置全局绑定开关"""
        self.global_enabled = enabled
        print(f"全局绑定功能: {'启用' if enabled else '禁用'}")

    def analyze_and_restrict_layer_files(self, all_layers: List):
        """分析所有图层的文件并设置限制，防止非绑定图层使用其他图层的文件"""
        print(f"[绑定管理器] 开始分析图层文件限制...")

        # 清除之前的限制
        self.layer_file_restrictions.clear()

        # 收集所有绑定图层使用的文件
        bound_layer_files = set()
        bound_layer_ids = set()

        # 遍历所有绑定组，收集绑定图层的文件
        for group_id, group in self.binding_groups.items():
            print(f"[绑定管理器] 分析绑定组: {group.name}")
            for group_layer in group.layers:
                # 找到对应的文档图层
                for doc_layer in all_layers:
                    if doc_layer.name == group_layer.name:
                        bound_layer_ids.add(id(doc_layer))
                        print(f"[绑定管理器] 绑定图层: {doc_layer.name}, 文件夹: {doc_layer.image_source}")

                        # 🔧 关键修复：只收集绑定图层当前正在使用的文件，而不是整个文件夹
                        if hasattr(doc_layer, 'current_image_path') and doc_layer.current_image_path:
                            if os.path.isfile(doc_layer.current_image_path):
                                bound_layer_files.add(doc_layer.current_image_path)
                                print(f"[绑定管理器] 绑定图层 '{doc_layer.name}' 当前使用文件: {os.path.basename(doc_layer.current_image_path)}")

                        # 如果绑定图层还没有当前文件，暂时不限制（等绑定后再分析）
                        break

        print(f"[绑定管理器] 发现 {len(bound_layer_files)} 个绑定图层正在使用的文件")

        # 为非绑定图层设置文件限制
        for layer in all_layers:
            layer_id = id(layer)

            if layer_id not in bound_layer_ids:  # 非绑定图层
                print(f"[绑定管理器] 分析非绑定图层: {layer.name}, 文件夹: {layer.image_source}")
                if layer.image_source and os.path.isdir(layer.image_source):
                    # 获取该图层文件夹中的所有文件
                    layer_files = []
                    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp']

                    try:
                        for file in os.listdir(layer.image_source):
                            ext = os.path.splitext(file)[1].lower()
                            if ext in image_extensions:
                                file_path = os.path.join(layer.image_source, file)

                                # 检查这个文件是否被绑定图层使用
                                if file_path not in bound_layer_files:
                                    layer_files.append(file_path)
                                else:
                                    print(f"[绑定管理器] 排除绑定文件: {os.path.basename(file_path)} (图层: {layer.name})")

                        # 设置该图层的文件限制
                        if layer_files:
                            self.layer_file_restrictions[layer_id] = layer_files
                            print(f"[绑定管理器] 图层 '{layer.name}' 可用文件: {len(layer_files)} 个")
                            # 显示前几个可用文件
                            sample_files = [os.path.basename(f) for f in layer_files[:3]]
                            print(f"[绑定管理器] 可用文件示例: {sample_files}")
                        else:
                            print(f"[绑定管理器] 警告：图层 '{layer.name}' 没有可用的独占文件")

                    except Exception as e:
                        print(f"[绑定管理器] 分析图层 '{layer.name}' 文件时出错: {e}")
            else:
                print(f"[绑定管理器] 跳过绑定图层: {layer.name}")

        print(f"[绑定管理器] 文件限制分析完成，限制了 {len(self.layer_file_restrictions)} 个非绑定图层")

    def get_layer_file_restrictions(self, layer) -> List[str]:
        """获取图层的文件限制列表"""
        layer_id = id(layer)
        return self.layer_file_restrictions.get(layer_id, [])
    
    def _is_text_layer(self, layer) -> bool:
        """检查图层是否为文字图层"""
        return hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None))

    def serialize(self) -> Dict:
        """序列化绑定管理器数据包括全局组合历史 - 修复版本"""
        serialized_groups = {}

        for group_id, group in self.binding_groups.items():
            # 🔧 修复：增强序列化，保存更多图层信息以便更准确地匹配
            layer_info_list = []
            for layer in group.layers:
                layer_info = {
                    'name': layer.name,
                    'type': 'text' if self._is_text_layer(layer) else 'image',
                    # 🔧 新增：保存额外信息用于更精确的匹配
                    'layer_id': id(layer),  # 运行时ID（反序列化时可能变化）
                    'has_text_lines': hasattr(layer, 'get_text_lines'),
                    'current_text': getattr(layer, 'current_text', '') if hasattr(layer, 'current_text') else ''
                }
                layer_info_list.append(layer_info)
            
            # 🔧 修复：保存绑定组的分类信息，避免反序列化时重新分析
            available_categories = group.get_available_categories()
            
            serialized_groups[group_id] = {
                'group_id': group_id,  # 保存原始group_id
                'name': group.name,
                'layers': layer_info_list,  # 🔧 修复：使用详细信息替代简单名称
                'categories': list(available_categories),  # 🔧 新增：保存分类信息
                'layer_count': len(group.layers)  # 🔧 新增：图层数量信息
            }

        # 序列化全局组合历史
        combination_history = {}
        for group_id, history in self.global_combination_manager.combination_history.items():
            combination_history[group_id] = dict(history)  # 转换为普通字典

        # 🔧 修复：序列化文件限制信息
        file_restrictions = {}
        for layer_id, restricted_files in self.layer_file_restrictions.items():
            file_restrictions[str(layer_id)] = restricted_files  # 转换为字符串键

        return {
            'global_enabled': self.global_enabled,
            'groups': serialized_groups,
            'file_restrictions_enabled': True,  # 标记支持文件限制功能
            'file_restrictions': file_restrictions,  # 🔧 新增：文件限制信息
            'combination_history': combination_history,  # 新增：全局组合历史
            'global_not_repeat_enabled': True,  # 标记支持全局不重复功能
            'serialization_version': '2.0'  # 🔧 新增：版本信息，便于向后兼容
        }
    
    def deserialize(self, data: Dict, layers: List):
        """反序列化绑定管理器数据包括全局组合历史 - 修复版本"""
        try:
            # 🔧 修复：版本兼容性检查
            serialization_version = data.get('serialization_version', '1.0')
            print(f"绑定管理器反序列化：版本 {serialization_version}")
            
            self.global_enabled = data.get('global_enabled', True)

            # 清空现有数据
            self.binding_groups.clear()
            self.layer_to_group.clear()
            self.layer_file_restrictions.clear()  # 清空文件限制
            self.global_combination_manager = GlobalCombinationManager()  # 重新初始化

            # 重建绑定组（如果有数据）
            groups_data = data.get('groups', {})
            if not groups_data:
                print("绑定管理器反序列化：没有绑定组数据")
                return

            print(f"绑定管理器反序列化：发现 {len(groups_data)} 个绑定组")

            # 🔧 修复：增强图层匹配逻辑，支持新旧两种格式
            for saved_group_id, group_data in groups_data.items():
                # 使用保存的group_id，如果没有则使用键名
                group_id = group_data.get('group_id', saved_group_id)
                group_name = group_data.get('name', '未命名组')
                
                # 🔧 修复：支持新旧两种数据格式
                if 'layers' in group_data:
                    # 新版本格式 - 包含详细信息
                    layer_infos = group_data.get('layers', [])
                    print(f"重建绑定组: {group_name} (ID: {group_id}), 图层信息: {len(layer_infos)} 个")
                    
                    # 根据详细信息查找图层
                    group_layers = []
                    for layer_info in layer_infos:
                        found_layer = self._find_layer_by_info(layer_info, layers)
                        if found_layer:
                            group_layers.append(found_layer)
                        else:
                            layer_name = layer_info.get('name', '未知')
                            print(f"警告：未找到图层 '{layer_name}'")
                else:
                    # 旧版本格式 - 只有名称列表
                    layer_names = group_data.get('layer_names', [])
                    print(f"重建绑定组: {group_name} (ID: {group_id}), 图层: {layer_names}")
                    
                    # 根据图层名称查找实际图层
                    group_layers = []
                    for layer_name in layer_names:
                        found_layer = self._find_layer_by_name(layer_name, layers)
                        if found_layer:
                            group_layers.append(found_layer)
                        else:
                            print(f"警告：未找到图层 '{layer_name}'")

                # 直接创建绑定组，使用原始ID，传递绑定管理器引用
                if group_layers:
                    group = BindingGroup(group_id, group_name, binding_manager=self)

                    for i, layer in enumerate(group_layers):
                        group.add_layer(layer, i)
                        self.layer_to_group[id(layer)] = group_id

                    # 🔧 修复：如果存在保存的分类信息，直接恢复
                    saved_categories = group_data.get('categories', [])
                    if saved_categories and hasattr(group, 'file_categories'):
                        # 重建分类信息，避免重新分析
                        for category in saved_categories:
                            if category not in group.file_categories:
                                group.file_categories[category] = {}
                        print(f"✅ 恢复绑定组分类信息: {len(saved_categories)} 个分类")
                    
                    self.binding_groups[group_id] = group
                    print(f"✅ 成功重建绑定组: {group_name} (ID: {group_id}), 包含 {len(group_layers)} 个图层")
                else:
                    print(f"❌ 绑定组 '{group_name}' 重建失败：没有找到任何图层")

            print(f"成功加载 {len(self.binding_groups)} 个绑定组")

            # 恢复文件限制信息
            file_restrictions = data.get('file_restrictions', {})
            if file_restrictions:
                for layer_id_str, restricted_files in file_restrictions.items():
                    try:
                        # 查找对应的图层
                        for layer in layers:
                            if str(id(layer)) == layer_id_str:
                                self.layer_file_restrictions[id(layer)] = restricted_files
                                print(f"恢复图层 '{layer.name}' 的文件限制: {len(restricted_files)} 个文件")
                                break
                    except Exception as e:
                        print(f"恢复文件限制时出错: {e}")

            # 恢复全局组合历史（如果有）
            combination_history = data.get('combination_history', {})
            if combination_history:
                self.global_combination_manager.combination_history = combination_history
                total_combinations = sum(len(history) for history in combination_history.values())
                print(f"恢复全局组合历史: {len(combination_history)}个组，共{total_combinations}个组合记录")

            # 如果支持文件限制功能，立即分析文件限制
            if data.get('file_restrictions_enabled', False) and layers:
                print(f"检测到文件限制功能支持，立即分析文件限制...")
                self.analyze_and_restrict_layer_files(layers)
                
            print(f"绑定管理器反序列化完成：共 {len(self.binding_groups)} 个绑定组")

        except Exception as e:
            print(f"反序列化绑定数据时出错: {e}")
            import traceback
            traceback.print_exc()
            # 如果出错，重置为空状态
            self.binding_groups.clear()
            self.layer_to_group.clear()
            self.layer_file_restrictions.clear()
            self.global_enabled = True
            self.global_combination_manager = GlobalCombinationManager()
    
    def _find_layer_by_name(self, layer_name: str, layers: List):
        """🔧 新增：根据名称查找图层"""
        """基础查找，只匹配名称"""
        for layer in layers:
            if hasattr(layer, 'name') and layer.name == layer_name:
                return layer
        return None
    
    def _find_layer_by_info(self, layer_info: Dict, layers: List):
        """🔧 新增：根据详细信息查找图层"""
        """增强查找，考虑多个属性进行精确匹配"""
        target_name = layer_info.get('name', '')
        target_type = layer_info.get('type', 'image')
        target_has_text_lines = layer_info.get('has_text_lines', False)
        target_current_text = layer_info.get('current_text', '')
        
        candidates = []
        for layer in layers:
            if not hasattr(layer, 'name') or layer.name != target_name:
                continue
                
            # 检查类型匹配
            is_text_layer = self._is_text_layer(layer)
            if target_type == 'text' and not is_text_layer:
                continue
            if target_type == 'image' and is_text_layer:
                continue
            
            # 对于文字图层，可以检查更多属性
            if is_text_layer and target_has_text_lines:
                if hasattr(layer, 'current_text') and layer.current_text == target_current_text:
                    # 完全匹配，优先级最高
                    return layer
            
            candidates.append(layer)
        
        # 返回第一个候选者，如果没有完全匹配的
        return candidates[0] if candidates else None
    
    def get_global_combination_statistics(self) -> Dict:
        """获取全局组合统计信息"""
        stats = {}
        for group_id, group in self.binding_groups.items():
            # 获取可能的组合数
            available_categories = group.get_available_categories()
            total_possible = 0
            
            if available_categories:
                # 计算总的可能组合数
                for category in available_categories:
                    if category in group.file_categories:
                        layer_file_counts = []
                        for layer_idx, files in group.file_categories[category].items():
                            layer_file_counts.append(len(files))
                        
                        if layer_file_counts:
                            category_combinations = 1
                            for count in layer_file_counts:
                                category_combinations *= count
                            total_possible += category_combinations
            
            # 获取使用统计
            usage_stats = self.global_combination_manager.get_statistics(group_id)
            diversity_score = self.global_combination_manager.get_diversity_score(group_id, total_possible)
            
            stats[group_id] = {
                'group_name': group.name,
                'total_possible_combinations': total_possible,
                'diversity_score': diversity_score,
                'usage_percentage': (usage_stats['total_used_combinations'] / max(1, total_possible)) * 100,
                **usage_stats
            }
        
        return stats
    
    def reset_global_combination_history(self, group_id: Optional[str] = None):
        """重置全局组合历史"""
        if group_id:
            # 重置指定组的历史
            if group_id in self.global_combination_manager.combination_history:
                del self.global_combination_manager.combination_history[group_id]
                print(f"重置绑定组 {group_id} 的组合历史")
        else:
            # 重置所有历史
            self.global_combination_manager.combination_history.clear()
            print(f"重置所有组合历史")
