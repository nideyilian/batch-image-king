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


def get_user_data_dir() -> str:
    """返回用户数据目录（打包安装后程序目录只读，必须写入用户目录）。"""
    try:
        if os.name == 'nt':  # Windows
            base_dir = os.environ.get('APPDATA', os.path.expanduser('~'))
        else:  # Linux/Mac
            base_dir = os.environ.get('XDG_CONFIG_HOME', os.path.join(os.path.expanduser('~'), '.config'))
        app_data_dir = os.path.join(base_dir, '批图王')
        os.makedirs(app_data_dir, exist_ok=True)
        return app_data_dir
    except Exception:
        logger.warning("获取用户数据目录失败，回退到临时目录", exc_info=True)
        import tempfile
        return tempfile.gettempdir()


def get_fonts_cache_file() -> str:
    """字体缓存文件路径：优先用户数据目录，避免安装到 Program Files 后只读写失败。"""
    return os.path.join(get_user_data_dir(), 'fonts_cache.json')


class TextLayerFontMixin:

    def _get_default_font(self):
        """获取系统默认字体"""
        system = platform.system()
        if system == "Windows":
            return "Microsoft YaHei"  # 微软雅黑
        elif system == "Darwin":  # macOS
            return "PingFang SC"  # 苹方
        else:  # Linux
            return "Noto Sans CJK SC"  # 思源黑体

    def get_system_fonts(self) -> List[str]:
        """获取系统可用字体列表（增强版，支持文件缓存）"""
        # 首先尝试从内存缓存获取
        if hasattr(self, '_cached_fonts') and self._cached_fonts:
            return self._cached_fonts

        # 尝试从文件缓存加载（缓存内包含字体名、中文名与文件路径）
        cached = self._load_fonts_from_cache()
        if cached:
            fonts, cn_map, paths, faces = cached
            self._cached_fonts = fonts
            self._cached_cn_names = cn_map or {}
            self._cached_font_paths = paths or {}
            self._cached_font_faces = faces or {}
            return fonts

        # 扫描系统字体
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

        # 缓存结果
        self._cached_fonts = fonts
        self._cached_cn_names = cn_map
        self._cached_font_paths = path_map
        self._cached_font_faces = face_map

        # 保存到文件缓存
        self._save_fonts_to_cache(fonts, cn_map, path_map, face_map)

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
        processed_files = set()

        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue

            try:
                for root, dirs, files in os.walk(font_dir):
                    for file in files:
                        file_lower = file.lower()
                        if any(file_lower.endswith(ext) for ext in font_extensions):
                            file_path = os.path.join(root, file)
                            if file_path not in processed_files:
                                processed_files.add(file_path)

                                font_info = self._extract_font_info(file_path)
                                if font_info:
                                    fonts.append(font_info)
            except (PermissionError, OSError):
                logger.warning("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py", exc_info=True)
                continue

        # 尝试从Windows注册表获取字体
        try:
            registry_fonts = self._get_windows_registry_fonts()
            fonts.extend(registry_fonts)
        except Exception:
            logger.warning("静默异常已忽略: except: in text_layer_font.py", exc_info=True)
            pass

        return fonts

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

        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue

            try:
                for root, dirs, files in os.walk(font_dir):
                    for file in files:
                        file_lower = file.lower()
                        if any(file_lower.endswith(ext) for ext in font_extensions):
                            file_path = os.path.join(root, file)
                            if file_path not in processed_files:
                                processed_files.add(file_path)

                                font_info = self._extract_font_info(file_path)
                                if font_info:
                                    fonts.append(font_info)
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

        for font_dir in font_dirs:
            if not os.path.exists(font_dir):
                continue

            try:
                for root, dirs, files in os.walk(font_dir):
                    for file in files:
                        file_lower = file.lower()
                        if any(file_lower.endswith(ext) for ext in font_extensions):
                            file_path = os.path.join(root, file)
                            if file_path not in processed_files:
                                processed_files.add(file_path)

                                font_info = self._extract_font_info(file_path)
                                if font_info:
                                    fonts.append(font_info)
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
        """从字体文件提取信息（优先读取字体文件内嵌的家族名，而非文件名）"""
        try:
            # 优先用 fontTools 读取内嵌名称表，得到真实家族名与中文名
            embedded = self._read_embedded_font_names(file_path)
            if embedded:
                name = embedded.get('name') or ''
                cn_name = embedded.get('cn_name') or ''
                font_style = embedded.get('style') or 'Regular'
                if name:
                    return {
                        'name': name,
                        'cn_name': cn_name,
                        'family': name,
                        'style': font_style,
                        'path': file_path,
                        'filename': os.path.basename(file_path)
                    }

            # 回退：从文件名提取信息
            file_name = os.path.basename(file_path)
            name_without_ext = os.path.splitext(file_name)[0]

            # 尝试获取更详细的字体信息
            font_name = name_without_ext
            font_family = name_without_ext
            font_style = "Regular"

            # 根据文件名推测样式
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

            return {
                'name': font_name,
                'cn_name': '',
                'family': font_family,
                'style': font_style,
                'path': file_path,
                'filename': file_name
            }
        except Exception:
            return {
                'name': os.path.splitext(os.path.basename(file_path))[0],
                'cn_name': '',
                'family': os.path.splitext(os.path.basename(file_path))[0],
                'style': 'Regular',
                'path': file_path,
                'filename': os.path.basename(file_path)
            }

    @staticmethod
    def _read_embedded_font_names(file_path: str) -> Optional[Dict[str, str]]:
        """读取字体文件内嵌的名称表，返回真实家族名与中文名。

        返回 {name, cn_name, style}；读取失败或无法解析时返回 None。
        中文名判定优先使用 name table 中的简体中文记录（langID 0x804/0x1004）。
        """
        try:
            from fontTools.ttLib import TTFont
        except ImportError:
            return None
        try:
            font = None
            try:
                font = TTFont(file_path, fontNumber=0, lazy=True)
            except Exception:
                try:
                    font = TTFont(file_path, lazy=True)
                except Exception:
                    return None
            try:
                name_table = font.get('name')
                if name_table is None:
                    return None

                family_en = None
                family_zh = None
                style_name = 'Regular'
                for record in name_table.names:
                    if record.nameID not in (1, 16):
                        continue
                    try:
                        value = record.toUnicode().strip()
                    except Exception:
                        continue
                    if not value:
                        continue
                    lang_id = record.langID
                    if lang_id in (0x0804, 0x1004):
                        family_zh = family_zh or value
                    elif lang_id == 0x0409:
                        family_en = family_en or value
                    elif family_en is None and lang_id in (0, 1) and record.platformID in (0, 1, 3):
                        family_en = family_en or value

                for record in name_table.names:
                    if record.nameID == 2:
                        try:
                            style_value = record.toUnicode().strip()
                        except Exception:
                            continue
                        if style_value and style_value.lower() not in ('regular', 'normal', 'book'):
                            style_name = style_value
                        break

                if not family_en:
                    family_en = family_zh
                if not family_en:
                    return None
                return {
                    'name': family_en,
                    'cn_name': family_zh or '',
                    'style': style_name,
                }
            finally:
                try:
                    font.close()
                except Exception:
                    pass
        except Exception:
            return None

    def _get_windows_registry_fonts(self) -> List[Dict[str, str]]:
        """从Windows注册表获取字体信息（优先读取字体文件内嵌名，去掉 (TrueType) 后缀）"""
        fonts = []

        try:
            import winreg

            # 打开字体注册表项
            reg_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"

            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, reg_path) as key:
                num_fonts = winreg.QueryInfoKey(key)[1]

                for i in range(num_fonts):
                    try:
                        font_name, font_file, _ = winreg.EnumValue(key, i)

                        # 查找字体文件
                        font_paths = []
                        for font_dir in ["C:/Windows/Fonts/", os.path.expanduser("~/AppData/Local/Microsoft/Windows/Fonts/")]:
                            font_path = os.path.join(font_dir, font_file)
                            if os.path.exists(font_path):
                                font_paths.append(font_path)
                                break

                        if not font_paths:
                            continue

                        # 优先读取字体文件内嵌的真实家族名
                        embedded = self._read_embedded_font_names(font_paths[0])
                        if embedded and embedded.get('name'):
                            fonts.append({
                                'name': embedded['name'],
                                'cn_name': embedded.get('cn_name') or '',
                                'family': embedded['name'],
                                'style': embedded.get('style') or 'Regular',
                                'path': font_paths[0],
                                'filename': font_file
                            })
                            continue

                        # 回退：使用注册表名，但去掉 "(TrueType)" / "(OpenType)" 后缀
                        clean_name = font_name
                        for suffix in (' (TrueType)', ' (OpenType)', ' (All res)'):
                            if clean_name.endswith(suffix):
                                clean_name = clean_name[:-len(suffix)]
                                break

                        fonts.append({
                            'name': clean_name,
                            'cn_name': '',
                            'family': clean_name.split()[0] if ' ' in clean_name else clean_name,
                            'style': 'Regular',
                            'path': font_paths[0],
                            'filename': font_file
                        })
                    except Exception:
                        logger.warning("静默异常已忽略: except: in text_layer_font.py", exc_info=True)
                        continue

        except Exception:
            logger.warning("静默异常已忽略: except Exception: in text_layer_font.py", exc_info=True)
            pass

        return fonts

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

    def _get_font_object(self):
        """获取PIL字体对象，使用缓存（增强中文与斜体支持）"""
        cache_key = (
            f"{self._font_family}_{getattr(self, '_font_face', '')}_"
            f"{self._font_size}_{self._font_style.name}"
        )

        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        # 优先根据字体家族定位文件路径
        font_path = self._find_font_path(
            self._font_family,
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
                font = ImageFont.truetype(font_path, self._font_size)
            else:
                # 尝试一些常见字体文件名（绝对路径由_find_font_path处理）
                for fallback_family in ["Microsoft YaHei", "PingFang SC", "Noto Sans CJK SC", "SimHei", "SimSun"]:
                    fp = self._find_font_path(fallback_family)
                    if fp:
                        font = ImageFont.truetype(fp, self._font_size)
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
