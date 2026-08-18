# -*- coding: utf-8 -*-
"""TextLayer 方法 mixin：本文件由拆分脚本生成，方法原属于 TextLayer。"""
import logging
from PySide6.QtCore import QObject, Signal, Property
from PIL import Image, ImageDraw, ImageFont
import os
import random
import platform
import math
import threading
from typing import List, Tuple, Dict, Set, Optional
from enum import Enum, auto
import json
from pathlib import Path
from app.models.text_layer_enums import (
    TextAlign, FontStyle, GradientType, GradientDirection, safe_print
)

logger = logging.getLogger(__name__)


# —— 字体扫描结果的进程级全局缓存（所有 TextLayer 共享，避免每个图层都扫描磁盘）
_GLOBAL_FONT_LOCK = threading.RLock()
# _GLOBAL_FONT_CACHE: {fonts, cn_names, paths, faces}  或 None
_GLOBAL_FONT_CACHE: Optional[Dict[str, object]] = None


def _get_user_data_dir() -> str:
    """获取用户数据目录（与 PresetManager 保持一致：%APPDATA%\\批图王 或 ~/.config/批图王）。"""
    try:
        if os.name == 'nt':
            base_dir = os.environ.get('APPDATA', os.path.expanduser('~'))
            app_data_dir = os.path.join(base_dir, '批图王')
        else:
            base_dir = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), '.config'))
            app_data_dir = os.path.join(base_dir, '批图王')
        os.makedirs(app_data_dir, exist_ok=True)
        return app_data_dir
    except Exception:
        import tempfile
        tmp = os.path.join(tempfile.gettempdir(), '批图王')
        os.makedirs(tmp, exist_ok=True)
        return tmp


class TextLayerFontMixin:

    @property
    def _fonts_cache_file(self) -> str:
        """字体列表缓存文件路径：默认位于用户数据目录（写入安全且全进程共享）。

        允许通过 setter 覆盖为指定路径（主要用于单元测试，或运行时把缓存定位到别处）。
        """
        override = getattr(self, '_fonts_cache_file_override', None)
        if override:
            return override
        return os.path.join(_get_user_data_dir(), "fonts_cache.json")

    @_fonts_cache_file.setter
    def _fonts_cache_file(self, value) -> None:
        if value:
            self._fonts_cache_file_override = str(value)
            # 清理进程级全局缓存，避免新路径被旧缓存误导
            global _GLOBAL_FONT_CACHE
            with _GLOBAL_FONT_LOCK:
                _GLOBAL_FONT_CACHE = None
            # 同时重置实例级字体缓存（让下次 get_system_fonts 重新加载）
            self._cached_fonts = [] if getattr(self, '_cached_fonts', None) else None
            self._cached_cn_names = None
            self._cached_font_paths = None
            self._cached_font_faces = None
        else:
            self._fonts_cache_file_override = None

    def _ensure_fonts_cache_dir(self) -> None:
        """确保字体缓存所在的用户数据目录存在。"""
        try:
            _get_user_data_dir()
        except Exception:
            pass

    def _get_default_font(self):
        """获取跨平台默认无衬线字体别名。"""
        return "sans-serif"

    @staticmethod
    def _get_platform_sans_font():
        """返回适合当前平台且支持中文的系统无衬线字体。"""
        system = platform.system()
        if system == "Windows":
            return "Microsoft YaHei"  # 微软雅黑
        elif system == "Darwin":  # macOS
            return "PingFang SC"  # 苹方
        else:  # Linux
            return "Noto Sans CJK SC"  # 思源黑体

    def _resolve_font_family(self, font_name: str) -> str:
        """把通用字体家族解析为渲染器可定位的真实系统家族。"""
        family = str(font_name or "").strip()
        if family.casefold() in {"sans-serif", "sans serif", "sans_serif"}:
            return self._get_platform_sans_font()
        return family

    def resolve_font_family(self, font_name: str) -> dict:
        """返回文档字体名对应的运行时家族和可用状态。"""
        requested = str(font_name or "").strip()
        resolved = self._resolve_font_family(requested)
        try:
            available = bool(self._find_font_path(requested))
        except Exception:
            logger.debug("检查文字字体可用性失败", exc_info=True)
            available = False
        fallback = None if available else self._get_platform_sans_font()
        return {
            "requested_family": requested,
            "resolved_family": resolved if available or requested.casefold() in {"sans-serif", "sans serif", "sans_serif"} else fallback,
            "available": available,
            "fallback_family": fallback,
        }

    def get_system_fonts(self) -> List[str]:
        """获取系统可用字体列表（增强版：全局内存缓存 + 用户目录文件缓存）。"""
        global _GLOBAL_FONT_CACHE

        # 1) 实例内存缓存
        if hasattr(self, '_cached_fonts') and self._cached_fonts:
            return self._cached_fonts

        # 2) 进程级全局内存缓存（避免每个文字图层重复扫描/解析）
        with _GLOBAL_FONT_LOCK:
            if _GLOBAL_FONT_CACHE is not None:
                self._cached_fonts = list(_GLOBAL_FONT_CACHE['fonts'])
                self._cached_cn_names = dict(_GLOBAL_FONT_CACHE.get('cn_names') or {})
                self._cached_font_paths = dict(_GLOBAL_FONT_CACHE.get('paths') or {})
                faces_src = _GLOBAL_FONT_CACHE.get('faces') or {}
                self._cached_font_faces = {
                    fam: [dict(face) for face in faces]
                    for fam, faces in faces_src.items()
                }
                return self._cached_fonts

        # 3) 从文件缓存加载（缓存内包含字体名、中文名与文件路径）
        cached = self._load_fonts_from_cache()
        if cached:
            fonts, cn_map, paths, faces = cached
            self._cached_fonts = fonts
            self._cached_cn_names = cn_map or {}
            self._cached_font_paths = paths or {}
            self._cached_font_faces = faces or {}
            # 回填全局缓存
            with _GLOBAL_FONT_LOCK:
                if _GLOBAL_FONT_CACHE is None:
                    _GLOBAL_FONT_CACHE = {
                        'fonts': list(fonts),
                        'cn_names': dict(cn_map or {}),
                        'paths': dict(paths or {}),
                        'faces': {
                            fam: [dict(face) for face in face_list]
                            for fam, face_list in (faces or {}).items()
                        },
                    }
            return fonts

        # 4) 扫描系统字体
        fonts = []
        cn_map = {}
        path_map = {}
        all_fonts_info = self._scan_all_system_fonts()

        # 按家族聚合所有实际 face，避免不同字重被家族名去重丢失。
        cjk_re = self._get_cjk_re()
        family_names = {}
        face_map = {}
        for font_info in all_fonts_info:
            family = str(font_info.get('family') or font_info.get('name') or '').strip()
            if not family:
                continue
            family_key = family.casefold()
            canonical_family = family_names.setdefault(family_key, family)
            if canonical_family not in face_map:
                face_map[canonical_family] = []
                fonts.append(canonical_family)

            cn_name = str(font_info.get('cn_name') or '').strip()
            if cn_name and cn_name != canonical_family and cjk_re.search(cn_name):
                cn_map.setdefault(canonical_family, cn_name)

            font_path = str(font_info.get('path') or '').strip()
            if not font_path:
                continue
            style = str(font_info.get('style') or 'Regular').strip() or 'Regular'
            if any(face['style'].casefold() == style.casefold() for face in face_map[canonical_family]):
                continue
            weight, italic = self._font_face_metadata(style)
            face_map[canonical_family].append({
                'style': style,
                'path': font_path,
                'weight': weight,
                'italic': italic,
            })

        fonts.sort(key=str.casefold)
        for family in fonts:
            faces = face_map.get(family, [])
            faces.sort(key=lambda face: (face['weight'], face['italic'], face['style'].casefold()))
            if faces:
                default_face = min(
                    faces,
                    key=lambda face: (face['italic'], abs(face['weight'] - 400)),
                )
                path_map[family] = default_face['path']

        # 缓存结果（实例 + 文件 + 全局）
        self._cached_fonts = fonts
        self._cached_cn_names = cn_map
        self._cached_font_paths = path_map
        self._cached_font_faces = face_map

        with _GLOBAL_FONT_LOCK:
            if _GLOBAL_FONT_CACHE is None:
                _GLOBAL_FONT_CACHE = {
                    'fonts': list(fonts),
                    'cn_names': dict(cn_map),
                    'paths': dict(path_map),
                    'faces': {
                        fam: [dict(face) for face in faces]
                        for fam, faces in face_map.items()
                    },
                }

        # 保存到文件缓存（失败不影响结果）
        try:
            self._save_fonts_to_cache(fonts, cn_map, path_map, face_map)
        except Exception:
            logger.debug("写入字体文件缓存失败", exc_info=True)

        return fonts

    @staticmethod
    def _font_face_metadata(style: str) -> Tuple[int, bool]:
        """把字体子样式规整为 CSS 风格字重和斜体标记。"""
        normalized = str(style or 'Regular').replace('-', ' ').replace('_', ' ').casefold()
        italic = 'italic' in normalized or 'oblique' in normalized or 'slanted' in normalized
        if any(token in normalized for token in ('thin', 'hairline')):
            weight = 100
        elif any(token in normalized for token in ('extra light', 'extralight', 'ultra light', 'ultralight')):
            weight = 200
        elif 'light' in normalized:
            weight = 300
        elif 'medium' in normalized:
            weight = 500
        elif any(token in normalized for token in ('semi bold', 'semibold', 'demi bold', 'demibold')):
            weight = 600
        elif any(token in normalized for token in ('extra bold', 'extrabold', 'ultra bold', 'ultrabold')):
            weight = 800
        elif any(token in normalized for token in ('black', 'heavy')):
            weight = 900
        elif 'bold' in normalized:
            weight = 700
        else:
            weight = 400
        return weight, italic

    def get_font_faces(self) -> Dict[str, List[Dict[str, object]]]:
        """返回字体家族到实际 face 的映射，供精确字重选择和渲染。"""
        if not getattr(self, '_cached_font_faces', None):
            self.get_system_fonts()
        return {
            family: [dict(face) for face in faces]
            for family, faces in (getattr(self, '_cached_font_faces', {}) or {}).items()
        }

    def get_font_cn_names(self) -> Dict[str, str]:
        """返回字体名 -> 中文名 的映射（仅包含确有中文名的字体）"""
        if not hasattr(self, '_cached_cn_names') or not self._cached_cn_names:
            self.get_system_fonts()
        return dict(getattr(self, '_cached_cn_names', {}) or {})

    def _scan_all_system_fonts(self) -> List[Dict[str, str]]:
        """扫描系统中所有字体文件（增强版）"""
        fonts = []
        system = platform.system()

        if system == "Windows":
            fonts = self._scan_windows_fonts()
        elif system == "Darwin":  # macOS
            fonts = self._scan_macos_fonts()
        else:  # Linux
            fonts = self._scan_linux_fonts()

        return fonts

    def _scan_windows_fonts(self) -> List[Dict[str, str]]:
        """扫描Windows系统所有字体"""
        fonts = []

        # 标准Windows字体目录
        font_dirs = [
            "C:/Windows/Fonts/",
            os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/"),
            "C:/Program Files/Microsoft Office/root/vfs/Fonts/",
            "C:/Program Files (x86)/Microsoft Office/root/vfs/Fonts/",
            "C:/Program Files/Adobe/Adobe Photoshop 2023/Required/",
            "C:/Program Files/Common Files/Adobe/Fonts/",
        ]

        # 添加可能的字体目录（使用glob匹配）
        import glob
        possible_patterns = [
            "C:/Program Files (x86)/Common Files/Adobe/Fonts/",
            "C:/Program Files/Autodesk/*/Fonts/",
            "C:/Program Files/Corel/*/Fonts/",
        ]

        for pattern in possible_patterns:
            try:
                matched_dirs = glob.glob(pattern.replace("/", "\\"))
                font_dirs.extend(matched_dirs)
            except Exception:
                logger.warning("静默异常已忽略: except: in text_layer_font.py", exc_info=True)
                pass

        font_extensions = {'.ttf', '.otf', '.ttc', '.fon', '.fnt'}
        # 位图字体后缀：fontTools 无法解析，直接走文件名回退以节省 try/except 时间
        bitmap_extensions = {'.fon', '.fnt'}
        processed_files = set()

        def _norm_path(p: str) -> str:
            try:
                return os.path.normcase(os.path.realpath(p))
            except Exception:
                return os.path.normcase(p)

        # 收集待解析的字体路径：位图字体立即回退，其余（TTF/OTF/TTC）放到列表里
        # 然后用线程池并行解析（name table 解析是磁盘 I/O 密集，并行显著缩短首扫时间）
        pending_paths: List[str] = []

        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue

            try:
                for root, dirs, files in os.walk(font_dir):
                    for file in files:
                        file_lower = file.lower()
                        if not any(file_lower.endswith(ext) for ext in font_extensions):
                            continue
                        file_path = os.path.join(root, file)
                        key = _norm_path(file_path)
                        if key in processed_files:
                            continue
                        processed_files.add(key)

                        ext = os.path.splitext(file)[1].lower()
                        if ext in bitmap_extensions:
                            fallback = self._fallback_font_info_from_filename(file_path)
                            if fallback:
                                fonts.append(fallback)
                            continue
                        pending_paths.append(file_path)
            except (PermissionError, OSError):
                logger.warning("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py", exc_info=True)
                continue

        # 尝试从Windows注册表获取字体（补漏：用户级字体、Office 安装字体、安装器写入绝对路径字体等）
        try:
            registry_font_paths = self._get_windows_registry_font_paths()
            for font_path in registry_font_paths:
                if not font_path:
                    continue
                key = _norm_path(font_path)
                if key in processed_files:
                    continue
                processed_files.add(key)

                ext = os.path.splitext(font_path)[1].lower()
                if ext in bitmap_extensions:
                    fallback = self._fallback_font_info_from_filename(font_path)
                    if fallback:
                        fonts.append(fallback)
                    continue
                pending_paths.append(font_path)
        except Exception:
            logger.warning("静默异常已忽略: except: in text_layer_font.py", exc_info=True)

        # 并行解析 pending_paths 中的 TTF/OTF/TTC；失败时退回顺序扫描以保证安全
        if pending_paths:
            def _safe_extract(path: str) -> List[Dict[str, str]]:
                try:
                    return self._extract_font_info_all(path)
                except Exception:
                    return []

            extracted_ok = False
            try:
                from concurrent.futures import ThreadPoolExecutor, as_completed
                max_workers = min(16, max(2, (os.cpu_count() or 4)))
                with ThreadPoolExecutor(max_workers=max_workers) as pool:
                    future_map = {pool.submit(_safe_extract, p): p for p in pending_paths}
                    for fut in as_completed(future_map):
                        try:
                            res = fut.result()
                        except Exception:
                            res = []
                        if res:
                            fonts.extend(res)
                extracted_ok = True
            except Exception as exc:
                logger.debug("并行字体解析失败，回退到顺序解析: %s", exc)
                extracted_ok = False

            if not extracted_ok:
                for p in pending_paths:
                    fonts.extend(_safe_extract(p))

        return fonts

    def _fallback_font_info_from_filename(self, file_path: str) -> Dict[str, str]:
        """仅从文件名推断字体信息（用于 fontTools 无法处理的位图字体或扫描兜底）。"""
        try:
            file_name = os.path.basename(file_path)
            name_without_ext = os.path.splitext(file_name)[0]
            style_name = 'Regular'
            family_name = name_without_ext or 'Unknown'
            # 粗扫常见样式后缀，把 "Arial Bold" -> family=Arial, style=Bold
            lower = family_name.lower()
            suffixes = [
                (' bold italic', 'Bold Italic'),
                (' bold oblique', 'Bold Oblique'),
                (' italic', 'Italic'),
                (' oblique', 'Oblique'),
                (' bold', 'Bold'),
                (' black', 'Black'),
                (' heavy', 'Heavy'),
                (' medium', 'Medium'),
                (' light', 'Light'),
                (' thin', 'Thin'),
                (' regular', 'Regular'),
            ]
            for suf, style in suffixes:
                if lower.endswith(suf):
                    family_name = family_name[:-len(suf)].strip(' -_') or family_name
                    style_name = style
                    break
            return {
                'name': family_name,
                'cn_name': '',
                'style': style_name,
                'path': file_path,
            }
        except Exception:
            return {}

    def _scan_macos_fonts(self) -> List[Dict[str, str]]:
        """扫描macOS系统所有字体"""
        fonts = []

        font_dirs = [
            "/System/Library/Fonts/",
            "/Library/Fonts/",
            os.path.expanduser("~/Library/Fonts/"),
            "/Network/Library/Fonts/",
            "/System/Library/Fonts/Supplemental/",
        ]

        font_extensions = {'.ttf', '.otf', '.ttc', '.dfont'}
        processed_files = set()

        def _norm_path(p: str) -> str:
            try:
                return os.path.normcase(os.path.realpath(p))
            except Exception:
                return os.path.normcase(p)

        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue

            try:
                for root, dirs, files in os.walk(font_dir):
                    for file in files:
                        file_lower = file.lower()
                        if any(file_lower.endswith(ext) for ext in font_extensions):
                            file_path = os.path.join(root, file)
                            key = _norm_path(file_path)
                            if key in processed_files:
                                continue
                            processed_files.add(key)
                            # 对 TTC 会返回多份，每份对应一个字体成员
                            fonts.extend(self._extract_font_info_all(file_path))
            except (PermissionError, OSError):
                logger.warning("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py", exc_info=True)
                continue

        return fonts

    def _scan_linux_fonts(self) -> List[Dict[str, str]]:
        """扫描Linux系统所有字体"""
        fonts = []

        font_dirs = [
            "/usr/share/fonts/",
            "/usr/local/share/fonts/",
            os.path.expanduser("~/.fonts/"),
            os.path.expanduser("~/.local/share/fonts/"),
            "/opt/local/share/fonts/",  # MacPorts
            "/usr/share/texmf/fonts/",
        ]

        font_extensions = {'.ttf', '.otf', '.ttc', '.pfb', '.pfa'}
        processed_files = set()

        def _norm_path(p: str) -> str:
            try:
                return os.path.normcase(os.path.realpath(p))
            except Exception:
                return os.path.normcase(p)

        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue

            try:
                for root, dirs, files in os.walk(font_dir):
                    for file in files:
                        file_lower = file.lower()
                        if any(file_lower.endswith(ext) for ext in font_extensions):
                            file_path = os.path.join(root, file)
                            key = _norm_path(file_path)
                            if key in processed_files:
                                continue
                            processed_files.add(key)
                            # 对 TTC 会返回多份，每份对应一个字体成员
                            fonts.extend(self._extract_font_info_all(file_path))
            except (PermissionError, OSError):
                logger.warning("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py", exc_info=True)
                continue

        return fonts

    _CJK_RE = None  # 延迟初始化的中文字符正则

    def _get_cjk_re(self):
        if self._CJK_RE is None:
            import re
            type(self)._CJK_RE = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\uf900-\ufaff]')
        return self._CJK_RE

    def _extract_font_info(self, file_path: str) -> Dict[str, str]:
        """从字体文件提取信息（保留单返回：返回第一个/主要字体，用于注册表等单次解析场景）。"""
        results = self._extract_font_info_all(file_path)
        return results[0] if results else {
            'name': os.path.splitext(os.path.basename(file_path))[0],
            'cn_name': '',
            'family': os.path.splitext(os.path.basename(file_path))[0],
            'style': 'Regular',
            'path': file_path,
            'filename': os.path.basename(file_path),
        }

    def _extract_font_info_all(self, file_path: str) -> List[Dict[str, str]]:
        """从字体文件提取信息列表；TTC/TTCollection 会返回多份（一份对应一个 fontNumber）。"""
        results: List[Dict[str, str]] = []
        try:
            embedded_list = self._read_embedded_font_names_all(file_path)
            if embedded_list:
                for embedded in embedded_list:
                    name = embedded.get('name') or ''
                    if not name:
                        continue
                    results.append({
                        'name': name,
                        'cn_name': embedded.get('cn_name') or '',
                        'family': name,
                        'style': embedded.get('style') or 'Regular',
                        'path': file_path,
                        'filename': os.path.basename(file_path),
                    })
                if results:
                    return results
        except Exception:
            logger.debug("读取字体内嵌名称失败: %s", file_path, exc_info=True)

        # 回退：从文件名提取信息（仅 1 条）
        file_name = os.path.basename(file_path)
        name_without_ext = os.path.splitext(file_name)[0]
        font_name = name_without_ext
        font_family = name_without_ext
        font_style = "Regular"
        name_lower = name_without_ext.lower()
        if 'bold' in name_lower or 'bd' in name_lower:
            font_style = "Bold"
        elif 'italic' in name_lower or 'it' in name_lower:
            font_style = "Italic"
        elif 'light' in name_lower or 'lt' in name_lower:
            font_style = "Light"
        elif 'medium' in name_lower or 'md' in name_lower:
            font_style = "Medium"
        elif 'black' in name_lower or 'bk' in name_lower:
            font_style = "Black"
        elif 'thin' in name_lower:
            font_style = "Thin"
        elif 'heavy' in name_lower:
            font_style = "Heavy"

        results.append({
            'name': font_name,
            'cn_name': '',
            'family': font_family,
            'style': font_style,
            'path': file_path,
            'filename': file_name,
        })
        return results

    @staticmethod
    def _read_embedded_font_names(file_path: str) -> Optional[Dict[str, str]]:
        """读取字体文件内嵌的名称表（兼容旧调用：返回第一个字体的结果）。"""
        all_results = TextLayerFontMixin._read_embedded_font_names_all(file_path)
        return all_results[0] if all_results else None

    @staticmethod
    def _read_embedded_font_names_all(file_path: str) -> List[Dict[str, str]]:
        """读取字体文件内嵌的名称表，TTC 会遍历所有成员；返回 [ {name, cn_name, style} ]。

        中文名判定优先使用 name table 中的简体中文记录（langID 0x804/0x1004）。
        """
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            return []

        results: List[Dict[str, str]] = []
        seen: Set[Tuple[str, str, str]] = set()

        def _collect_from_one(font_one) -> None:
            try:
                name_table = font_one.get('name')
                if name_table is None:
                    return

                # 分类收集 nameID=16 / 1 / 17 / 2 的候选，按置信度加权
                fam16_en: List[Tuple[int, str]] = []   # (priority, value) for nameID=16 English
                fam16_zh: List[Tuple[int, str]] = []   # nameID=16 CJK
                fam1_en: List[Tuple[int, str]] = []    # nameID=1 English
                fam1_zh: List[Tuple[int, str]] = []    # nameID=1 CJK
                subfamily: List[Tuple[int, str]] = []  # nameID=17 / 2

                def _is_cjk_lang(lid: int) -> bool:
                    # 简体/繁体/香港/新加坡/澳门 中文、日文、韩文等都视为含中文名候选
                    return lid in (
                        0x0404, 0x0804, 0x0C04, 0x1004, 0x1404, 0x7C04,
                        0x0411, 0x0412,
                    )

                for record in name_table.names:
                    try:
                        value = record.toUnicode().strip()
                    except Exception:
                        continue
                    if not value:
                        continue
                    nid = record.nameID
                    lid = record.langID
                    pid = record.platformID
                    # 按 platform/lang 计算一个基础优先级（越大越可信）：Win > Mac > Unicode
                    base = {3: 300, 1: 200, 0: 100}.get(pid, 0)
                    en_ok = (lid == 0x0409)
                    cjk_ok = _is_cjk_lang(lid)
                    if nid == 16:
                        if en_ok:
                            fam16_en.append((base + 90, value))
                        elif cjk_ok:
                            fam16_zh.append((base + 90, value))
                        elif pid in (0, 1, 3):
                            fam16_en.append((base + 20, value))
                    elif nid == 1:
                        if en_ok:
                            fam1_en.append((base + 80, value))
                        elif cjk_ok:
                            fam1_zh.append((base + 80, value))
                        elif pid in (0, 1, 3):
                            fam1_en.append((base + 10, value))
                    elif nid == 17:
                        subfamily.append((base + 50, value))
                    elif nid == 2:
                        subfamily.append((base + 40, value))

                def _pick(pool: List[Tuple[int, str]]) -> Optional[str]:
                    if not pool:
                        return None
                    pool.sort(key=lambda x: x[0], reverse=True)
                    return pool[0][1]

                family_zh = _pick(fam16_zh) or _pick(fam1_zh)
                # 家族英文名：nameID=16 优先（Typographic Family 更干净，不含字重）
                family_en = _pick(fam16_en) or _pick(fam1_en)

                style_name = 'Regular'
                sf = _pick(subfamily)
                if sf and sf.strip():
                    s = sf.strip()
                    if s.lower() not in ('regular', 'normal', 'book', ''):
                        style_name = s

                # 最终兜底：如果没有 nameID=1/16 的优先语言命中，尝试任何 nameID=1/16 的值
                if not family_en and not family_zh:
                    any16 = None
                    any1 = None
                    for record in name_table.names:
                        if record.nameID not in (1, 16):
                            continue
                        try:
                            v = record.toUnicode().strip()
                        except Exception:
                            continue
                        if not v:
                            continue
                        if record.nameID == 16 and not any16:
                            any16 = v
                        elif record.nameID == 1 and not any1:
                            any1 = v
                    family_en = any16 or any1
                    if not family_en and family_zh:
                        family_en = family_zh

                if not family_en:
                    return
                key = (str(family_en), str(family_zh or ''), str(style_name))
                if key in seen:
                    return
                seen.add(key)
                results.append({
                    'name': family_en,
                    'cn_name': family_zh or '',
                    'style': style_name,
                })
            except Exception:
                return

        # 策略：先尝试 fontNumber=0,1,2,... 直到抛异常；若单字体文件 fontNumber>0 首次打开
        # 就异常，我们再 fallback 到不带 fontNumber 参数的打开方式（至少取 1 份）。
        any_opened = False
        try:
            max_font_numbers = 64  # 安全上限：一个 TTC 通常不会超过几十个成员
            for idx in range(max_font_numbers):
                font = None
                try:
                    font = TTFont(file_path, fontNumber=idx, lazy=True)
                    any_opened = True
                except Exception:
                    if idx == 0:
                        # 第一个就失败：可能不是 TTC，或者 fontNumber 参数不被接受；break 后走 fallback
                        break
                    # idx>0：说明已经读完了 TTC 的全部成员
                    break
                try:
                    _collect_from_one(font)
                finally:
                    try:
                        font.close()
                    except Exception:
                        pass
        except Exception:
            pass

        if not any_opened:
            # Fallback：非 TTC 的单字体文件打开方式
            font = None
            try:
                font = TTFont(file_path, lazy=True)
            except Exception:
                logger.debug("无法用 fontTools 打开字体文件: %s", file_path, exc_info=True)
                return results
            try:
                _collect_from_one(font)
            finally:
                try:
                    font.close()
                except Exception:
                    pass

        return results

    def _get_windows_registry_font_paths(self) -> List[str]:
        """从Windows注册表获取字体文件路径（HKLM + HKCU 两处）。

        修复点：
        - 同时读取系统字体（HKLM）和用户安装字体（HKCU），避免"为我安装"的字体漏掉。
        - 注册表值若为完整绝对路径，直接使用而不再拼接目录。
        - 不再内部解析 name table：调用方统一解析，避免目录+注册表重复打开字体文件浪费时间。
        """
        paths: List[str] = []
        try:
            import winreg
        except ImportError:
            return paths

        reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"
        # 用户字体搜索顺序：先用户本地字体目录，再系统字体目录
        default_font_dirs = [
            os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/"),
            "C:/Windows/Fonts/",
        ]
        seen: Set[str] = set()

        def _norm(p: str) -> str:
            try:
                return os.path.normcase(os.path.realpath(p))
            except Exception:
                return os.path.normcase(p)

        def _collect_from_root(root_hive) -> None:
            try:
                with winreg.OpenKey(root_hive, reg_path) as key:
                    num_fonts = winreg.QueryInfoKey(key)[1]
                    for i in range(num_fonts):
                        try:
                            font_name, font_file_raw, _ = winreg.EnumValue(key, i)
                            font_file = str(font_file_raw or '').strip()
                            if not font_file:
                                continue

                            resolved = None
                            if os.path.isabs(font_file):
                                if os.path.exists(font_file):
                                    resolved = font_file
                            else:
                                for d in default_font_dirs:
                                    candidate = os.path.join(d, font_file)
                                    if os.path.exists(candidate):
                                        resolved = candidate
                                        break
                            if not resolved:
                                continue

                            k = _norm(resolved)
                            if k in seen:
                                continue
                            seen.add(k)
                            paths.append(resolved)
                        except Exception:
                            logger.debug("枚举注册表字体条目失败", exc_info=True)
                            continue
            except FileNotFoundError:
                # 该根键下可能不存在 Fonts 项（尤其 HKCU 若无用户安装字体则可能缺失）
                return
            except OSError:
                return
            except Exception:
                logger.debug("读取注册表字体失败 hive=%s", root_hive, exc_info=True)
                return

        # 系统级 + 用户级；用户级放前面，这样用户自定义字体在同家族情况下优先
        _collect_from_root(winreg.HKEY_CURRENT_USER)
        _collect_from_root(winreg.HKEY_LOCAL_MACHINE)
        return paths

    def _load_fonts_from_cache(self) -> Optional[Tuple[List[str], Dict[str, str], Dict[str, str], Dict[str, List[Dict[str, object]]]]]:
        """从文件缓存加载字体列表、名称、默认路径与 face 目录。"""
        try:
            if os.path.exists(self._fonts_cache_file):
                with open(self._fonts_cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # 检查缓存是否过期（7天）
                import time
                cache_time = cache_data.get('timestamp', 0)
                current_time = time.time()

                # 如果缓存时间超过7天，认为过期
                if current_time - cache_time > 7 * 24 * 60 * 60:
                    return None

                # v3 开始保留同一家族的全部 face；旧缓存必须重新扫描。
                if cache_data.get('cache_version', 1) < 3:
                    return None

                # 验证缓存文件中的字体是否仍然存在（优先用缓存路径，其次按名字反查）
                cached_fonts = cache_data.get('fonts', [])
                cached_cn_names = cache_data.get('cn_names', {}) or {}
                cached_paths = cache_data.get('paths', {}) or {}
                cached_faces = cache_data.get('faces', {}) or {}
                valid_fonts = []
                valid_cn_names = {}
                valid_paths = {}
                valid_faces = {}

                for font_name in cached_fonts:
                    faces = []
                    for face in cached_faces.get(font_name, []) or []:
                        path = str(face.get('path') or '')
                        if not path or not os.path.exists(path):
                            continue
                        style = str(face.get('style') or 'Regular')
                        weight, italic = self._font_face_metadata(style)
                        faces.append({
                            'style': style,
                            'path': path,
                            'weight': int(face.get('weight', weight)),
                            'italic': bool(face.get('italic', italic)),
                        })
                    if not faces:
                        continue
                    faces.sort(key=lambda face: (face['weight'], face['italic'], face['style'].casefold()))
                    valid_fonts.append(font_name)
                    valid_faces[font_name] = faces
                    if font_name in cached_cn_names:
                        valid_cn_names[font_name] = cached_cn_names[font_name]
                    default_path = cached_paths.get(font_name) or ''
                    valid_paths[font_name] = default_path if os.path.exists(default_path) else min(
                        faces,
                        key=lambda face: (face['italic'], abs(face['weight'] - 400)),
                    )['path']

                if valid_fonts:
                    return valid_fonts, valid_cn_names, valid_paths, valid_faces
                return None

        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            logger.warning("静默异常已忽略: except (FileNotFoundError, json.JSONDecodeError, KeyError): in text_layer_font.py", exc_info=True)
            pass

        return None

    def _save_fonts_to_cache(self, fonts: List[str], cn_names: Optional[Dict[str, str]] = None,
                             font_paths: Optional[Dict[str, str]] = None,
                             font_faces: Optional[Dict[str, List[Dict[str, object]]]] = None) -> None:
        """保存字体列表到文件缓存"""
        try:
            import time
            cache_data = {
                'timestamp': time.time(),
                'cache_version': 3,
                'fonts': fonts,
                'cn_names': cn_names or {},
                'paths': font_paths or {},
                'faces': font_faces or {},
                'count': len(fonts),
                'system': platform.system()
            }

            with open(self._fonts_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

        except (IOError, OSError):
            # 如果无法写入文件，静默失败
            pass

    def get_categorized_fonts(self) -> Dict[str, List[str]]:
        """获取分类后的字体列表（中文字体优先用内嵌中文名判据）"""
        all_fonts = self.get_system_fonts()
        cn_names = self.get_font_cn_names()

        categories = {
            'chinese': [],      # 中文字体
            'english': [],      # 英文字体
            'monospace': [],    # 等宽字体
            'decorative': [], # 装饰字体
            'other': []         # 其他字体
        }

        chinese_keywords = [
            '中文', 'Chinese', 'CN', 'SC', 'TC', 'Han', 'Song', 'Kai', 'Hei', 'Fang',
            'Sim', 'Microsoft YaHei', 'PingFang', 'Source Han', 'Noto CJK',
            '思源', '苹方', '微软雅黑', '宋体', '黑体', '楷体', '仿宋'
        ]

        monospace_keywords = [
            'Mono', 'Courier', 'Consolas', 'Lucida Console', 'DejaVu Sans Mono',
            'Menlo', 'Monaco', 'Fira Code', 'Source Code', '等宽'
        ]

        decorative_keywords = [
            'Decorative', 'Script', 'Hand', 'Calligraphy', 'Brush', 'Art',
            'Fancy', 'Ornamental', 'Display', 'Blackletter', '哥特', '手写', '书法'
        ]

        cjk_re = self._get_cjk_re()

        def is_chinese_font(font_name):
            # 有内嵌中文名 => 中文字体
            if cn_names.get(font_name):
                return True
            # 字体名本身含中文字符
            if cjk_re.search(font_name):
                return True
            # 关键词兜底
            font_lower = font_name.lower()
            for keyword in chinese_keywords:
                if keyword.lower() in font_lower:
                    return True
            return False

        for font_name in all_fonts:
            font_lower = font_name.lower()

            # 中/英是主分类：中文字体优先归入 chinese，其余归入 english
            if is_chinese_font(font_name):
                categories['chinese'].append(font_name)
            else:
                categories['english'].append(font_name)

            # 等宽 / 装饰字体作为补充标签（同时保留在两个主分类下）
            if any(keyword.lower() in font_lower for keyword in monospace_keywords):
                categories['monospace'].append(font_name)
            elif any(keyword.lower() in font_lower for keyword in decorative_keywords):
                categories['decorative'].append(font_name)

        # 对每个分类排序
        for category in categories:
            categories[category].sort()

        return categories

    def _validate_font_exists(self, font_name: str) -> bool:
        """验证字体是否仍然存在"""
        try:
            # 尝试找到字体文件
            font_path = self._find_font_path(font_name)
            return font_path is not None and os.path.exists(font_path)
        except Exception:
            return False

    def _get_font_object(self, size=None):
        """获取PIL字体对象，使用缓存（增强中文与斜体支持）

        Args:
            size: 指定字号；为 None 时使用全局字号（支持混合字号渲染）
        """
        if size is None:
            size = self._font_size
        size = max(1, int(size))
        resolution = self.resolve_font_family(self._font_family)
        resolved_family = str(resolution.get("resolved_family") or self._resolve_font_family(self._font_family))
        cache_key = (
            f"{resolved_family}_{getattr(self, '_font_face', '')}_"
            f"{size}_{self._font_style.name}"
        )

        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        # 优先根据字体家族定位文件路径
        font_path = self._find_font_path(
            resolved_family,
            getattr(self, '_font_face', ''),
        )

        # 如果按家族找不到，针对常见中文字体进行映射尝试
        if not font_path:
            system = platform.system()
            family_candidates = []
            if system == "Windows":
                family_candidates = ["Microsoft YaHei", "SimHei", "SimSun", "KaiTi", "FangSong"]
            elif system == "Darwin":
                family_candidates = ["PingFang SC", "Heiti SC", "Songti SC"]
            else:
                family_candidates = ["Noto Sans CJK SC", "WenQuanYi Zen Hei"]

            for fam in family_candidates:
                font_path = self._find_font_path(fam)
                if font_path:
                    break

        # 最后的回退：加载默认可用的中文字体或系统默认
        font = None
        try:
            if font_path:
                font = ImageFont.truetype(font_path, size)
            else:
                # 尝试一些常见字体文件名（绝对路径由_find_font_path处理）
                for fallback_family in ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei", "SimSun"]:
                    fp = self._find_font_path(fallback_family)
                    if fp:
                        font = ImageFont.truetype(fp, size)
                        break
                if font is None:
                    # 仍找不到时使用系统默认（可能不支持中文）
                    font = ImageFont.load_default()
        except Exception:
            font = ImageFont.load_default()

        self._font_cache[cache_key] = font
        return font

    def _find_font_path(self, font_name: str, face_style: str = '') -> str:
        """查找字体文件路径；显式 face 优先于旧版合成样式。"""
        font_name = self._resolve_font_family(font_name)
        requested_face = str(face_style or '').strip().casefold()
        if requested_face:
            cached_faces = getattr(self, '_cached_font_faces', None)
            if not cached_faces:
                try:
                    self.get_system_fonts()
                except Exception:
                    cached_faces = {}
                else:
                    cached_faces = getattr(self, '_cached_font_faces', None)
            for face in (cached_faces or {}).get(font_name, []) or []:
                if str(face.get('style') or '').strip().casefold() != requested_face:
                    continue
                path = str(face.get('path') or '')
                if path and os.path.exists(path):
                    return path

        # 优先使用扫描时记录的字体文件路径缓存
        cached_paths = getattr(self, '_cached_font_paths', None)
        if cached_paths:
            p = cached_paths.get(font_name)
            if p and os.path.exists(p):
                return p

        system = platform.system()
        font_extensions = ['.ttf', '.otf', '.ttc']

        if system == "Windows":
            font_dirs = [
                "C:/Windows/Fonts/",
                os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/")
            ]
        elif system == "Darwin":  # macOS
            font_dirs = [
                "/Library/Fonts/",
                "/System/Library/Fonts/",
                os.path.expanduser("~/Library/Fonts/")
            ]
        else:  # Linux
            font_dirs = [
                "/usr/share/fonts/",
                "/usr/local/share/fonts/",
                os.path.expanduser("~/.fonts/")
            ]

        # 先尝试家族到文件的常见映射（提高中文字体命中率）
        common_map = {}
        if system == "Windows":
            common_map = {
                "Microsoft YaHei": ["msyh.ttc", "msyh.ttf"],
                "SimHei": ["simhei.ttf"],
                "SimSun": ["simsun.ttc", "simsun.ttf"],
                "KaiTi": ["simkai.ttf", "kaiti.ttf"],
                "FangSong": ["simfang.ttf"],
            }
        elif system == "Darwin":
            common_map = {
                "PingFang SC": ["PingFang.ttc"],
                "Heiti SC": ["STHeiti Light.ttf", "STHeiti Medium.ttf"],
                "Songti SC": ["Songti.ttc"],
            }
        else:
            common_map = {
                "Noto Sans CJK SC": ["NotoSansCJK-Regular.ttc", "NotoSansCJK-Regular.otf"],
                "WenQuanYi Zen Hei": ["wqy-zenhei.ttc", "wqy-zenhei.ttf"],
            }

        mapped_files = common_map.get(font_name, [])
        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue
            for mf in mapped_files:
                candidate = os.path.join(font_dir, mf)
                if os.path.exists(candidate):
                    return candidate

        # 根据字体样式构造搜索关键词
        style_keywords = []
        if self._font_style == FontStyle.BOLD:
            style_keywords = ['bold', 'b']
        elif self._font_style == FontStyle.ITALIC:
            style_keywords = ['italic', 'oblique', 'i']
        elif self._font_style == FontStyle.BOLD_ITALIC:
            style_keywords = ['bolditalic', 'bold italic', 'bi']

        # 首先尝试查找包含样式关键词的字体文件
        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue

            try:
                for font_file in os.listdir(font_dir):
                    file_name_no_ext = os.path.splitext(font_file)[0].lower()
                    font_name_lower = font_name.lower()

                    # 检查是否包含字体名称
                    if font_name_lower not in file_name_no_ext:
                        continue

                    # 检查文件扩展名
                    if not any(font_file.lower().endswith(ext) for ext in font_extensions):
                        continue

                    # 如果需要特殊样式，检查是否包含样式关键词
                    if style_keywords:
                        if any(keyword in file_name_no_ext for keyword in style_keywords):
                            return os.path.join(font_dir, font_file)
                    else:
                        # 普通样式，优先选择不包含样式关键词的文件
                        style_indicators = ['bold', 'italic', 'oblique', 'light', 'thin', 'black', 'heavy']
                        if not any(indicator in file_name_no_ext for indicator in style_indicators):
                            return os.path.join(font_dir, font_file)
            except (PermissionError, OSError):
                logger.warning("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py", exc_info=True)
                continue

        # 如果没有找到特殊样式的字体，回退到普通字体
        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue

            try:
                for font_file in os.listdir(font_dir):
                    file_name_no_ext = os.path.splitext(font_file)[0]
                    if (font_name.lower() in file_name_no_ext.lower() and 
                        any(font_file.lower().endswith(ext) for ext in font_extensions)):
                        return os.path.join(font_dir, font_file)
            except (PermissionError, OSError):
                logger.warning("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py", exc_info=True)
                continue

        return None
