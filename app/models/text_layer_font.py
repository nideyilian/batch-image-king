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

        # 尝试从文件缓存加载
        cached_fonts = self._load_fonts_from_cache()
        if cached_fonts:
            self._cached_fonts = cached_fonts
            return cached_fonts

        # 扫描系统字体
        fonts = []
        all_fonts_info = self._scan_all_system_fonts()

        # 提取字体名称并去重
        seen_fonts = set()
        for font_info in all_fonts_info:
            font_name = font_info.get('name', '')
            if font_name and font_name not in seen_fonts:
                seen_fonts.add(font_name)
                fonts.append(font_name)

        # 按字母顺序排序
        fonts.sort()

        # 缓存结果
        self._cached_fonts = fonts

        # 保存到文件缓存
        self._save_fonts_to_cache(fonts)

        return fonts

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
            except:
                logger.debug("静默异常已忽略: except: in text_layer_font.py")
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
                logger.debug("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py")
                continue

        # 尝试从Windows注册表获取字体
        try:
            registry_fonts = self._get_windows_registry_fonts()
            fonts.extend(registry_fonts)
        except:
            logger.debug("静默异常已忽略: except: in text_layer_font.py")
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
                logger.debug("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py")
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
                logger.debug("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py")
                continue

        return fonts

    def _extract_font_info(self, file_path: str) -> Dict[str, str]:
        """从字体文件提取信息"""
        try:
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
                'family': font_family,
                'style': font_style,
                'path': file_path,
                'filename': file_name
            }
        except Exception:
            return {
                'name': os.path.splitext(os.path.basename(file_path))[0],
                'family': os.path.splitext(os.path.basename(file_path))[0],
                'style': 'Regular',
                'path': file_path,
                'filename': os.path.basename(file_path)
            }

    def _get_windows_registry_fonts(self) -> List[Dict[str, str]]:
        """从Windows注册表获取字体信息"""
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

                        if font_paths:
                            fonts.append({
                                'name': font_name,
                                'family': font_name.split()[0] if ' ' in font_name else font_name,
                                'style': 'Regular',
                                'path': font_paths[0],
                                'filename': font_file
                            })
                    except:
                        logger.debug("静默异常已忽略: except: in text_layer_font.py")
                        continue

        except Exception:
            logger.debug("静默异常已忽略: except Exception: in text_layer_font.py")
            pass

        return fonts

    def _load_fonts_from_cache(self) -> Optional[List[str]]:
        """从文件缓存加载字体列表"""
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

                # 验证缓存文件中的字体是否仍然存在
                cached_fonts = cache_data.get('fonts', [])
                valid_fonts = []

                for font_name in cached_fonts:
                    # 简单验证字体是否可用
                    if self._validate_font_exists(font_name):
                        valid_fonts.append(font_name)

                return valid_fonts if valid_fonts else None

        except (FileNotFoundError, json.JSONDecodeError, KeyError):
            logger.debug("静默异常已忽略: except (FileNotFoundError, json.JSONDecodeError, KeyError): in text_layer_font.py")
            pass

        return None

    def _save_fonts_to_cache(self, fonts: List[str]) -> None:
        """保存字体列表到文件缓存"""
        try:
            import time
            cache_data = {
                'timestamp': time.time(),
                'fonts': fonts,
                'count': len(fonts),
                'system': platform.system()
            }

            with open(self._fonts_cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f, ensure_ascii=False, indent=2)

        except (IOError, OSError):
            # 如果无法写入文件，静默失败
            pass

    def get_categorized_fonts(self) -> Dict[str, List[str]]:
        """获取分类后的字体列表"""
        all_fonts = self.get_system_fonts()

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

        for font_name in all_fonts:
            font_lower = font_name.lower()
            categorized = False

            # 检查中文字体
            for keyword in chinese_keywords:
                if keyword.lower() in font_lower:
                    categories['chinese'].append(font_name)
                    categorized = True
                    break

            if categorized:
                continue

            # 检查等宽字体
            for keyword in monospace_keywords:
                if keyword.lower() in font_lower:
                    categories['monospace'].append(font_name)
                    categorized = True
                    break

            if categorized:
                continue

            # 检查装饰字体
            for keyword in decorative_keywords:
                if keyword.lower() in font_lower:
                    categories['decorative'].append(font_name)
                    categorized = True
                    break

            if categorized:
                continue

            # 默认分类为英文或其他
            if any(char.isascii() and char.isalpha() for char in font_name):
                categories['english'].append(font_name)
            else:
                categories['other'].append(font_name)

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
        except:
            return False

    def _get_font_object(self):
        """获取PIL字体对象，使用缓存（增强中文与斜体支持）"""
        cache_key = f"{self._font_family}_{self._font_size}_{self._font_style.name}"

        if cache_key in self._font_cache:
            return self._font_cache[cache_key]

        # 优先根据字体家族定位文件路径
        font_path = self._find_font_path(self._font_family)

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

    def _find_font_path(self, font_name: str) -> str:
        """查找字体文件路径，考虑字体样式"""
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
                logger.debug("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py")
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
                logger.debug("静默异常已忽略: except (PermissionError, OSError): in text_layer_font.py")
                continue

        return None
