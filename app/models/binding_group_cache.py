#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BindingGroup 子 mixin 1: 持久化文件夹分类索引 + 目录扫描 + 缓存失效

从原 binding_group.py 拆分。所有方法保持原签名，依赖 self 上的类级
文件夹索引缓存（_folder_category_index_*）和实例属性（_binding_manager、
layers、file_categories）由主 BindingGroup 持有。
"""

import os
import json
import time
import logging
from typing import Dict, List

from app.utils.print_utils import safe_print as _safe_print

logger = logging.getLogger(__name__)

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print


class BindingGroupCache:
    """文件夹分类索引 + 目录扫描相关方法（拆分自 BindingGroup）。"""

    # 类级缓存键名（必须在主类上保持一致）
    _supported_image_ext = ('.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp')

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
            logger.warning("静默异常已忽略: except Exception: in binding_group.py", exc_info=True)
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
            logger.warning("静默异常已忽略: except Exception: in binding_group.py", exc_info=True)
            pass

    @staticmethod
    def _get_directory_mtime_ns(directory: str) -> int:
        try:
            return int(os.stat(directory).st_mtime_ns)
        except Exception:
            return -1

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
                        logger.warning("静默异常已忽略: except Exception: in binding_group.py", exc_info=True)
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