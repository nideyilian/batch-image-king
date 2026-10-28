"""文件夹图片索引缓存相关 mixin（从 BatchExportPrecomputerV2 抽取，方法体原样迁移）。

方法仅访问主类实例属性（self._folder_index_cache 等）与同组方法，调用点均为 self._xxx，
迁移后由主类实例兜底，行为零变化。

编码安全契约：主模块顶部有 `print = _safe_print` 与模块级 `logger`；本组方法使用
`logger.warning(..., exc_info=True)`，故在此镜像主模块契约，避免退化。
"""
import json
import logging
import os
import time
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


class BatchExportFolderCacheMixin:
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
            logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
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
            logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
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
                        logger.warning("静默异常已忽略: except in utils/batch_export_precomputer_v2.py", exc_info=True)
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
            # 目录不存在（被删除 / 改名 / 外接盘没插）时返回空列表，
            # 上层拿到空池就会「这一层没有素材可放」→ 静默导出缺内容。
            # 这是用户最难自查的一类故障：图出来了，但某个位置是空的。
            self._note_degradation("素材目录.目录不存在", abs_dir)
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
        filtered = [p for p in base_files if cat in os.path.basename(p).lower()]
        if base_files and not filtered:
            # 目录有图但按分类关键词一张都匹配不上（分类名写错 / 文件名命名不符），
            # 该绑定组会整块缺失。
            self._note_degradation(
                "素材目录.分类筛选后为空",
                f"{abs_dir} 分类={category} 目录内={len(base_files)}",
            )
        return filtered

    def _note_degradation(self, key, detail=None):
        """向主类的降级计数器记一笔（mixin 里没有该属性时安全跳过）。"""
        counter = getattr(self, 'degradations', None)
        if counter is not None:
            counter.note(key, detail)
