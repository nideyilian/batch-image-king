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

_TEXT_LAYER_DEBUG = os.environ.get("BTPW_TEXT_LAYER_DEBUG") == "1"


class TextAlign(Enum):
    """文字对齐方式枚举"""
    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()


class FontStyle(Enum):
    """字体样式枚举"""
    NORMAL = auto()
    BOLD = auto()
    ITALIC = auto()
    BOLD_ITALIC = auto()


class GradientType(Enum):
    """渐变类型枚举"""
    NONE = auto()           # 无渐变（纯色）
    LINEAR = auto()         # 线性渐变
    RADIAL = auto()         # 径向渐变
    ANGULAR = auto()        # 角度渐变


class GradientDirection(Enum):
    """线性渐变方向枚举"""
    HORIZONTAL = auto()     # 水平
    VERTICAL = auto()       # 垂直
    DIAGONAL_LR = auto()    # 左上到右下
    DIAGONAL_RL = auto()    # 右上到左下


class TextLayer(QObject):
    """文字图层模型类"""
    
    # 信号定义
    changed = Signal()
    text_changed = Signal()
    
    def __init__(self, name="文字图层", x=0, y=0, width=200, height=100, parent=None):
        """
        初始化文字图层
        
        Args:
            name: 图层名称
            x: X坐标
            y: Y坐标
            width: 宽度
            height: 高度
            parent: 父对象
        """
        super().__init__(parent)
        
        # 基本属性
        self._name = name
        self._x = x
        self._y = y
        self._width = width
        self._height = height
        self._visible = True
        self._opacity = 1.0
        self._locked = False
        self._use_original_size = False  # 文字图层不使用原始尺寸
        
        # 兼容性属性（文字图层不使用，但需要存在以兼容普通图层接口）
        self.image_source = None  # 文字图层没有图像源
        self.is_folder = False  # 文字图层不是文件夹
        self.current_image_path = None  # 文字图层没有图像路径
        self.cached_image = None  # 使用自己的缓存机制
        
        # 文字内容
        self._text_lines = ["示例文字"]  # 文字行列表
        self._current_text = "示例文字"  # 当前显示的文字
        self._random_mode = False  # 是否启用随机模式
        # 是否启用“按换行拆分为绑定条目”的模式
        # True: 兼容旧逻辑，每一行是一个候选文案
        # False: 整个文本作为单条文案，换行仅用于排版
        self._text_binding_enabled = True
        
        # 字体属性
        self._font_family = self._get_default_font()  # 字体名称
        self._font_size = 24  # 字体大小
        self._font_style = FontStyle.NORMAL  # 字体样式
        
        # 文字样式
        self._text_color = (0, 0, 0, 255)  # 文字颜色 RGBA
        self._text_align = TextAlign.LEFT  # 对齐方式
        self._line_spacing = 1.2  # 行间距倍数
        self._letter_spacing = 0  # 字间距（像素），0表示正常间距，正值增加间距，负值减少间距
        self._text_box_padding = 5  # 文字与图层边框的内边距（px）
        self._auto_fit_text_box = True  # 自动按文字内容调整图层边框
        self._vertical_layout = False  # 竖排模式

        # 渐变设置
        self._gradient_enabled = False  # 是否启用渐变
        self._gradient_type = GradientType.LINEAR  # 渐变类型
        self._gradient_direction = GradientDirection.HORIZONTAL  # 渐变方向
        self._gradient_start_color = (255, 0, 0, 255)  # 渐变起始颜色
        self._gradient_end_color = (0, 0, 255, 255)  # 渐变结束颜色
        self._gradient_angle = 0  # 自定义角度（度）
        self._gradient_center_x = 0.5  # 径向渐变中心X（0-1）
        self._gradient_center_y = 0.5  # 径向渐变中心Y（0-1）
        
        # 描边设置
        self._stroke_enabled = False
        self._stroke_width = 2
        self._stroke_color = (255, 255, 255, 255)  # 描边颜色 RGBA
        
        # 背景设置
        self._background_enabled = False
        self._background_color = (255, 255, 255, 128)  # 背景颜色 RGBA
        self._background_padding = 5  # 背景内边距
        
        # 缓存
        self._cached_image = None
        self._font_cache = {}  # 字体对象缓存
        self._fonts_cache_file = "fonts_cache.json"  # 字体缓存文件

        # 渲染质量优化
        self._supersample_enabled = True
        self._supersample_scale = 2
        
        # 渲染锁：避免批量导出与预览并发时，超采样临时参数互相污染
        self._render_lock = threading.RLock()
        self._auto_fit_lock = False
        
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
                continue
        
        # 尝试从Windows注册表获取字体
        try:
            registry_fonts = self._get_windows_registry_fonts()
            fonts.extend(registry_fonts)
        except:
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
                        continue
                        
        except Exception:
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
                continue
        
        return None

    def _create_gradient_image(self, width: int, height: int) -> Image.Image:
        """创建渐变图像"""
        if not self._gradient_enabled or self._gradient_type == GradientType.NONE:
            # 返回纯色图像
            return Image.new('RGBA', (width, height), self._text_color)

        # 创建渐变图像
        gradient_img = Image.new('RGBA', (width, height))
        pixels = gradient_img.load()

        start_r, start_g, start_b, start_a = self._gradient_start_color
        end_r, end_g, end_b, end_a = self._gradient_end_color

        if self._gradient_type == GradientType.LINEAR:
            return self._create_linear_gradient(width, height, start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a)
        elif self._gradient_type == GradientType.RADIAL:
            return self._create_radial_gradient(width, height, start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a)
        elif self._gradient_type == GradientType.ANGULAR:
            return self._create_angular_gradient(width, height, start_r, start_g, start_b, start_a,
                                               end_r, end_g, end_b, end_a)

        return Image.new('RGBA', (width, height), self._text_color)

    def _create_linear_gradient(self, width, height, start_r, start_g, start_b, start_a,
                               end_r, end_g, end_b, end_a):
        """创建线性渐变"""
        gradient_img = Image.new('RGBA', (width, height))
        pixels = gradient_img.load()

        # 根据方向计算渐变
        if self._gradient_direction == GradientDirection.HORIZONTAL:
            for x in range(width):
                ratio = x / (width - 1) if width > 1 else 0
                color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a, ratio)
                for y in range(height):
                    pixels[x, y] = color
        elif self._gradient_direction == GradientDirection.VERTICAL:
            for y in range(height):
                ratio = y / (height - 1) if height > 1 else 0
                color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a, ratio)
                for x in range(width):
                    pixels[x, y] = color
        elif self._gradient_direction == GradientDirection.DIAGONAL_LR:
            diagonal_length = math.sqrt(width * width + height * height)
            for x in range(width):
                for y in range(height):
                    distance = math.sqrt(x * x + y * y)
                    ratio = distance / diagonal_length if diagonal_length > 0 else 0
                    ratio = min(1.0, ratio)
                    color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                                  end_r, end_g, end_b, end_a, ratio)
                    pixels[x, y] = color
        elif self._gradient_direction == GradientDirection.DIAGONAL_RL:
            diagonal_length = math.sqrt(width * width + height * height)
            for x in range(width):
                for y in range(height):
                    distance = math.sqrt((width - x) * (width - x) + y * y)
                    ratio = distance / diagonal_length if diagonal_length > 0 else 0
                    ratio = min(1.0, ratio)
                    color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                                  end_r, end_g, end_b, end_a, ratio)
                    pixels[x, y] = color

        return gradient_img

    def _create_radial_gradient(self, width, height, start_r, start_g, start_b, start_a,
                               end_r, end_g, end_b, end_a):
        """创建径向渐变"""
        gradient_img = Image.new('RGBA', (width, height))
        pixels = gradient_img.load()

        center_x = int(width * self._gradient_center_x)
        center_y = int(height * self._gradient_center_y)
        max_radius = max(
            math.sqrt(center_x * center_x + center_y * center_y),
            math.sqrt((width - center_x) * (width - center_x) + center_y * center_y),
            math.sqrt(center_x * center_x + (height - center_y) * (height - center_y)),
            math.sqrt((width - center_x) * (width - center_x) + (height - center_y) * (height - center_y))
        )

        for x in range(width):
            for y in range(height):
                distance = math.sqrt((x - center_x) * (x - center_x) + (y - center_y) * (y - center_y))
                ratio = distance / max_radius if max_radius > 0 else 0
                ratio = min(1.0, ratio)
                color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a, ratio)
                pixels[x, y] = color

        return gradient_img

    def _create_angular_gradient(self, width, height, start_r, start_g, start_b, start_a,
                                end_r, end_g, end_b, end_a):
        """创建角度渐变"""
        gradient_img = Image.new('RGBA', (width, height))
        pixels = gradient_img.load()

        center_x = width / 2
        center_y = height / 2

        for x in range(width):
            for y in range(height):
                angle = math.atan2(y - center_y, x - center_x)
                # 将角度转换为0-1的比例
                ratio = (angle + math.pi) / (2 * math.pi)
                color = self._interpolate_color(start_r, start_g, start_b, start_a,
                                              end_r, end_g, end_b, end_a, ratio)
                pixels[x, y] = color

        return gradient_img

    def _interpolate_color(self, start_r, start_g, start_b, start_a,
                          end_r, end_g, end_b, end_a, ratio):
        """颜色插值"""
        ratio = max(0.0, min(1.0, ratio))
        r = int(start_r + (end_r - start_r) * ratio)
        g = int(start_g + (end_g - start_g) * ratio)
        b = int(start_b + (end_b - start_b) * ratio)
        a = int(start_a + (end_a - start_a) * ratio)
        return (r, g, b, a)

    def _draw_text_with_style(self, draw, x, y, text, font, color_or_image):
        """绘制带样式的文字，支持渐变"""
        # 如果启用了渐变，使用渐变图像作为填充
        if self._gradient_enabled and isinstance(color_or_image, Image.Image):
            # 创建文字蒙版
            text_mask = Image.new('L', (self._width, self._height), 0)
            mask_draw = ImageDraw.Draw(text_mask)

            # 根据字体样式绘制蒙版
            if self._font_style == FontStyle.NORMAL:
                mask_draw.text((x, y), text, font=font, fill=255)
            elif self._font_style == FontStyle.BOLD:
                offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]
                for dx, dy in offsets:
                    mask_draw.text((x + dx, y + dy), text, font=font, fill=255)
            elif self._font_style == FontStyle.ITALIC:
                mask_draw.text((x, y), text, font=font, fill=255)
                text_mask = self._apply_italic_shear(text_mask)
            elif self._font_style == FontStyle.BOLD_ITALIC:
                offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]
                for dx, dy in offsets:
                    mask_draw.text((x + dx, y + dy), text, font=font, fill=255)
                text_mask = self._apply_italic_shear(text_mask)

            # 将渐变图像应用到文字区域
            # 创建临时图像用于合成
            temp_img = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
            temp_img.paste(color_or_image, (0, 0))

            # 使用蒙版将渐变应用到文字
            result_img = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
            result_img.paste(temp_img, (0, 0), text_mask)

            return result_img
        else:
            # 普通颜色填充
            if self._font_style == FontStyle.NORMAL:
                draw.text((x, y), text, font=font, fill=color_or_image)
            elif self._font_style == FontStyle.BOLD:
                offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]
                for dx, dy in offsets:
                    draw.text((x + dx, y + dy), text, font=font, fill=color_or_image)
            elif self._font_style == FontStyle.ITALIC:
                # 使用蒙版实现斜体
                text_mask = Image.new('L', (self._width, self._height), 0)
                mask_draw = ImageDraw.Draw(text_mask)
                mask_draw.text((x, y), text, font=font, fill=255)
                text_mask = self._apply_italic_shear(text_mask)
                colored = Image.new('RGBA', (self._width, self._height), color_or_image if isinstance(color_or_image, tuple) else (0,0,0,0))
                result_img = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                result_img.paste(colored, (0, 0), text_mask)
                # 合成到主图像
                draw_image = Image.new('RGBA', (self._width, self._height))
                draw_image.paste(result_img, (0, 0))
                # 将生成的图层与当前图像合成
                # 注意：这里无法直接用draw对象合成，调用者在上层会alpha合成
                return result_img
            elif self._font_style == FontStyle.BOLD_ITALIC:
                text_mask = Image.new('L', (self._width, self._height), 0)
                mask_draw = ImageDraw.Draw(text_mask)
                offsets = [(0, 0), (1, 0), (0, 1), (1, 1)]
                for dx, dy in offsets:
                    mask_draw.text((x + dx, y + dy), text, font=font, fill=255)
                text_mask = self._apply_italic_shear(text_mask)
                colored = Image.new('RGBA', (self._width, self._height), color_or_image if isinstance(color_or_image, tuple) else (0,0,0,0))
                result_img = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                result_img.paste(colored, (0, 0), text_mask)
                return result_img

            return None

    def _draw_text_background(self, draw: ImageDraw.Draw, lines: list, font, start_y: int, line_widths: list, line_heights: list, max_line_height: int) -> None:
        """绘制文字背景 - 基于实际文字像素边界的完全居中算法，支持±距离控制"""
        if not self._background_enabled or not lines:
            return
            
        # 创建一个临时图像来获取文字的实际像素边界（包含所有效果）
        temp_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_image)
        
        # 准备渐变图像（如果启用）
        gradient_image = None
        if self._gradient_enabled:
            gradient_image = self._create_gradient_image(self._width, self._height)
        
        # 渲染文字到临时图像（包含所有效果：描边、渐变等）
        current_y = start_y
        for i, line in enumerate(lines):
            if i >= len(line_widths):
                break
                
            line_width = line_widths[i]
            line_height = line_heights[i] if i < len(line_heights) else max_line_height
            
            # 计算X位置
            if self._text_align == TextAlign.CENTER:
                x = max(0, (self._width - line_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                x = max(0, self._width - line_width)
            else:  # LEFT
                x = 0
            
            # 渲染描边（如果启用）
            if self._stroke_enabled and self._stroke_width > 0:
                if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
                    # 斜体描边：创建描边蒙版并应用斜体变换
                    stroke_mask = Image.new('L', (self._width, self._height), 0)
                    stroke_draw = ImageDraw.Draw(stroke_mask)
                    
                    # 绘制描边蒙版
                    for dx in range(-self._stroke_width, self._stroke_width + 1):
                        for dy in range(-self._stroke_width, self._stroke_width + 1):
                            if dx != 0 or dy != 0:
                                stroke_draw.text((x + dx, current_y + dy), line, font=font, fill=255)
                    
                    # 应用斜体变换
                    stroke_mask = self._apply_italic_shear(stroke_mask)
                    
                    # 创建描边颜色图像并应用蒙版
                    stroke_colored = Image.new('RGBA', (self._width, self._height), self._stroke_color)
                    stroke_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                    stroke_result.paste(stroke_colored, (0, 0), stroke_mask)
                    
                    # 合成描边到临时图像
                    temp_image = Image.alpha_composite(temp_image, stroke_result)
                else:
                    # 普通描边：直接绘制
                    for dx in range(-self._stroke_width, self._stroke_width + 1):
                        for dy in range(-self._stroke_width, self._stroke_width + 1):
                            if dx != 0 or dy != 0:
                                temp_draw.text(
                                    (x + dx, current_y + dy),
                                    line,
                                    font=font,
                                    fill=self._stroke_color
                                )
            
            # 渲染主文字，考虑渐变和字体样式
            if self._gradient_enabled and gradient_image:
                # 使用渐变绘制
                gradient_result = self._draw_text_with_style(temp_draw, x, current_y, line, font, gradient_image)
                if gradient_result:
                    # 将渐变文字合成到临时图像
                    temp_image = Image.alpha_composite(temp_image, gradient_result)
            else:
                # 使用纯色绘制（可能返回合成图像用于斜体）
                color_result = self._draw_text_with_style(temp_draw, x, current_y, line, font, self._text_color)
                if color_result:
                    temp_image = Image.alpha_composite(temp_image, color_result)
                else:
                    temp_draw.text((x, current_y), line, font=font, fill=self._text_color)
            
            # 移动到下一行
            if i < len(line_heights) - 1 and line_heights:
                current_y += line_heights[i] + int(max_line_height * (self._line_spacing - 1))
        
        # 扫描像素找到文字的实际边界（包含所有效果）
        pixels = temp_image.load()
        text_left = self._width
        text_top = self._height
        text_right = 0
        text_bottom = 0
        found_text = False
        
        for y in range(self._height):
            for x in range(self._width):
                r, g, b, a = pixels[x, y]
                if a > 10:  # 检测到文字像素（包含描边等效果）
                    text_left = min(text_left, x)
                    text_top = min(text_top, y)
                    text_right = max(text_right, x)
                    text_bottom = max(text_bottom, y)
                    found_text = True
        
        if not found_text:
            return
        
        # 计算文字的中心位置
        text_center_x = (text_left + text_right) // 2
        text_center_y = (text_top + text_bottom) // 2
        text_width = text_right - text_left + 1
        text_height = text_bottom - text_top + 1
        
        # 根据背景内边距参数计算背景尺寸
        # 正数：背景大于文字（向外扩展），负数：背景小于文字（向内收缩）
        bg_width = max(1, text_width + 2 * self._background_padding)  # 确保最小宽度
        bg_height = max(1, text_height + 2 * self._background_padding)  # 确保最小高度
        
        # 计算背景位置（以文字中心为基准，实现完全居中）
        bg_left = text_center_x - bg_width // 2
        bg_top = text_center_y - bg_height // 2
        bg_right = bg_left + bg_width
        bg_bottom = bg_top + bg_height
        
        # 确保背景不超出图层边界
        bg_left = max(0, bg_left)
        bg_right = min(self._width, bg_right)
        bg_top = max(0, bg_top)
        bg_bottom = min(self._height, bg_bottom)
        
        # 绘制背景矩形
        draw.rectangle(
            [bg_left, bg_top, bg_right, bg_bottom],
            fill=self._background_color
        )

    def _apply_italic_shear(self, mask_img: Image.Image) -> Image.Image:
        """对文字蒙版应用水平斜切以模拟斜体"""
        # 典型斜体角度约12度
        shear_angle = 12.0
        shear = math.tan(math.radians(shear_angle))
        # 仿射变换：x' = x + shear*y
        a, b, c = 1, shear, 0
        d, e, f = 0, 1, 0
        try:
            return mask_img.transform(mask_img.size, Image.AFFINE, (a, b, c, d, e, f), resample=Image.BILINEAR)
        except Exception:
            return mask_img
    
    def _draw_text_with_letter_spacing(self, draw: ImageDraw.Draw, x: int, y: int, text: str, font, fill,
                                      stroke_width: int = 0, stroke_fill=None, bold: bool = False) -> tuple:
        """绘制带字间距的文本，返回实际绘制的宽度和高度
        
        Args:
            draw: ImageDraw对象
            x: 起始X坐标
            y: 起始Y坐标
            text: 要绘制的文本
            font: 字体对象
            fill: 填充颜色
            
        Returns:
            tuple: (实际宽度, 实际高度)
        """
        if self._letter_spacing == 0:
            # 没有字间距，使用标准绘制
            draw.text((x, y), text, font=font, fill=fill)
            bbox = draw.textbbox((x, y), text, font=font)
            return (bbox[2] - bbox[0], bbox[3] - bbox[1])
        
        # 有字间距，逐字符绘制
        current_x = x
        max_height = 0
        
        bold_offsets = [(0, 0), (1, 0), (0, 1), (1, 1)] if bold else [(0, 0)]
        for char in text:
            # 绘制当前字符
            for dx, dy in bold_offsets:
                draw.text(
                    (current_x + dx, y + dy),
                    char,
                    font=font,
                    fill=fill,
                    stroke_width=stroke_width,
                    stroke_fill=stroke_fill
                )
            
            # 获取字符的宽度
            bbox = draw.textbbox((0, 0), char, font=font)
            char_width = bbox[2] - bbox[0]
            char_height = bbox[3] - bbox[1]
            max_height = max(max_height, char_height)
            
            # 移动到下一个字符位置（字符宽度 + 字间距）
            current_x += char_width + self._letter_spacing
        
        # 返回总宽度（不包括最后的字间距）
        total_width = current_x - x - self._letter_spacing if text else 0
        return (total_width, max_height)

    def _create_text_mask_with_spacing(self, x: int, y: int, text: str, font,
                                      stroke_width: int = 0, bold: bool = False) -> Image.Image:
        """创建带字间距的文字蒙版（支持斜体/粗体）"""
        mask = Image.new('L', (self._width, self._height), 0)
        mask_draw = ImageDraw.Draw(mask)
        temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))

        current_x = x
        bold_offsets = [(0, 0), (1, 0), (0, 1), (1, 1)] if bold else [(0, 0)]

        for char in text:
            for dx, dy in bold_offsets:
                mask_draw.text(
                    (current_x + dx, y + dy),
                    char,
                    font=font,
                    fill=255,
                    stroke_width=stroke_width,
                    stroke_fill=255
                )
            bbox = temp_draw.textbbox((0, 0), char, font=font)
            char_width = bbox[2] - bbox[0]
            current_x += char_width + self._letter_spacing

        if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
            mask = self._apply_italic_shear(mask)

        return mask
    
    def _get_text_width_with_spacing(self, text: str, font) -> int:
        """计算带字间距的文本宽度
        
        Args:
            text: 文本内容
            font: 字体对象
            
        Returns:
            int: 文本宽度（像素）
        """
        if not text:
            return 0
            
        if self._letter_spacing == 0:
            # 没有字间距，使用标准计算
            temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            bbox = temp_draw.textbbox((0, 0), text, font=font)
            return bbox[2] - bbox[0]
        
        # 有字间距，逐字符计算
        temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
        total_width = 0
        
        for char in text:
            bbox = temp_draw.textbbox((0, 0), char, font=font)
            char_width = bbox[2] - bbox[0]
            total_width += char_width + self._letter_spacing
        
        # 减去最后一个字符后多余的字间距
        if text:
            total_width -= self._letter_spacing
            
        return total_width

    def _measure_horizontal_text(self, lines: List[str], font, draw: ImageDraw.Draw) -> Tuple[int, int]:
        """测量横排文字内容尺寸（不含外边距）"""
        if not lines:
            return 0, 0

        stroke_for_measure = self._stroke_width if self._stroke_enabled else 0
        italic_shear_extra = 0
        if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
            italic_shear_extra = int(math.tan(math.radians(12.0)) * max(1, self._font_size))

        line_widths = []
        line_heights = []
        for line in lines:
            line_text = line if line else " "
            line_width = self._get_text_width_with_spacing(line_text, font)
            bbox = draw.textbbox((0, 0), line_text, font=font, stroke_width=stroke_for_measure)
            bbox_width = max(0, bbox[2] - bbox[0])
            line_height = max(0, bbox[3] - bbox[1])
            render_width = max(line_width, bbox_width) + italic_shear_extra
            line_widths.append(max(0, render_width))
            line_heights.append(max(0, line_height))

        max_line_height = max(line_heights) if line_heights else 0
        line_gap = int(max_line_height * (self._line_spacing - 1)) if max_line_height else 0
        content_width = max(line_widths) if line_widths else 0
        content_height = sum(line_heights) + max(0, len(line_heights) - 1) * line_gap
        return content_width, content_height

    def _measure_vertical_text(self, lines: List[str], font, draw: ImageDraw.Draw) -> Tuple[int, int]:
        """测量竖排文字内容尺寸（不含外边距）"""
        if not lines:
            return 0, 0

        stroke_for_measure = self._stroke_width if self._stroke_enabled else 0
        italic_shear_extra = 0
        if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
            italic_shear_extra = int(math.tan(math.radians(12.0)) * max(1, self._font_size))

        column_widths = []
        column_heights = []

        for line in lines:
            chars = list(line) if line else [" "]
            char_heights = []
            char_widths = []
            for ch in chars:
                bbox = draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_for_measure)
                cw = max(0, bbox[2] - bbox[0])
                chh = max(0, bbox[3] - bbox[1])
                char_widths.append(cw)
                char_heights.append(chh)

            column_width = (max(char_widths) if char_widths else 0) + italic_shear_extra
            base_gap = int((max(char_heights) if char_heights else 0) * (self._line_spacing - 1))
            char_gap = base_gap + self._letter_spacing
            column_height = sum(char_heights) + max(0, len(char_heights) - 1) * char_gap

            column_widths.append(column_width)
            column_heights.append(column_height)

        max_col_width = max(column_widths) if column_widths else 0
        col_gap = int(max_col_width * (self._line_spacing - 1)) if max_col_width else 0
        content_width = sum(column_widths) + max(0, len(column_widths) - 1) * col_gap
        content_height = max(column_heights) if column_heights else 0
        return content_width, content_height

    def _update_text_box_size_if_needed(self) -> bool:
        """根据文字内容自动调整边框尺寸。返回是否发生尺寸变化。"""
        if not self._auto_fit_text_box or self._auto_fit_lock:
            return False

        try:
            self._auto_fit_lock = True
            font = self._get_font_object()
            temp_draw = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
            lines = (self._current_text or "").split('\n')
            if not lines:
                lines = [""]

            if self._vertical_layout:
                content_width, content_height = self._measure_vertical_text(lines, font, temp_draw)
            else:
                content_width, content_height = self._measure_horizontal_text(lines, font, temp_draw)

            # content_width/content_height 已包含描边测量，不再重复叠加 stroke_extra
            target_width = max(1, int(content_width + self._text_box_padding * 2))
            target_height = max(1, int(content_height + self._text_box_padding * 2))

            changed = (target_width != self._width or target_height != self._height)
            if changed:
                self._width = target_width
                self._height = target_height
            return changed
        except Exception:
            return False
        finally:
            self._auto_fit_lock = False

    def randomize_text(self):
        """随机选择文字内容，增强随机性避免重复"""
        if self._text_lines and len(self._text_lines) > 0:
            rng = random.SystemRandom()
            
            # 如果只有一个文字选项，在批量导出时也要触发变化通知
            if len(self._text_lines) == 1:
                self.set_current_text(self._text_lines[0], force=True)
                return
            
            # 多个文字选项时，确保选择的文字与当前不同（如果可能）
            available_texts = [text for text in self._text_lines if text != self._current_text]
            
            if available_texts:
                # 从不同于当前文字的选项中随机选择
                selected_text = rng.choice(available_texts)
            else:
                # 如果所有文字都相同或只有当前文字，随机选择任意一条
                selected_text = rng.choice(list(self._text_lines))

            self.set_current_text(selected_text)
    
    def get_image(self):
        """获取当前文字的渲染图像（遍历模式专用）
        
        直接使用当前设置的文字进行渲染，不进行随机选择
        """
        safe_print(f"文字图层 '{self._name}' 渲染当前文字: '{self._current_text}'")
        return self.render_text()

    def _get_rendered_text_bounds(self, lines, font, line_widths, line_heights) -> tuple:
        """获取渲染后文字的实际像素边界（ink bounds）
        
        Returns:
            tuple: (left, top, right, bottom) - 实际像素边界
        """
        # 创建临时图像用于渲染和测量
        temp_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_image)
        
        # 计算基础布局（使用当前逻辑）
        if not line_heights:
            return (0, 0, 0, 0)
            
        max_line_height = max(line_heights)
        total_height = sum(line_heights) + (len(lines) - 1) * int(max_line_height * (self._line_spacing - 1))
        
        # 基础居中位置
        if total_height > 0:
            start_y = (self._height - total_height) // 2 + 2  # 使用当前的偏移
        else:
            start_y = (self._height - total_height) // 2
        
        # 准备渐变图像（如果启用）
        gradient_image = None
        if self._gradient_enabled:
            gradient_image = self._create_gradient_image(self._width, self._height)
        
        # 渲染文字到临时图像
        current_y = start_y
        for i, line in enumerate(lines):
            if i >= len(line_widths):
                break
                
            line_width = line_widths[i]
            line_height = line_heights[i] if i < len(line_heights) else max_line_height
            
            # 计算X位置
            if self._text_align == TextAlign.CENTER:
                x = max(0, (self._width - line_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                x = max(0, self._width - line_width)
            else:  # LEFT
                x = 0
            
            current_line_y = current_y
            
            # 绘制描边
            if self._stroke_enabled and self._stroke_width > 0:
                if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
                    # 斜体描边：创建描边蒙版并应用斜体变换
                    stroke_mask = Image.new('L', (self._width, self._height), 0)
                    stroke_draw = ImageDraw.Draw(stroke_mask)
                    
                    # 绘制描边蒙版
                    for dx in range(-self._stroke_width, self._stroke_width + 1):
                        for dy in range(-self._stroke_width, self._stroke_width + 1):
                            if dx != 0 or dy != 0:
                                stroke_draw.text((x + dx, current_line_y + dy), line, font=font, fill=255)
                    
                    # 应用斜体变换
                    stroke_mask = self._apply_italic_shear(stroke_mask)
                    
                    # 创建描边颜色图像并应用蒙版
                    stroke_colored = Image.new('RGBA', (self._width, self._height), self._stroke_color)
                    stroke_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                    stroke_result.paste(stroke_colored, (0, 0), stroke_mask)
                    
                    # 合成描边到主图像
                    temp_image = Image.alpha_composite(temp_image, stroke_result)
                else:
                    # 普通描边：直接绘制
                    for dx in range(-self._stroke_width, self._stroke_width + 1):
                        for dy in range(-self._stroke_width, self._stroke_width + 1):
                            if dx != 0 or dy != 0:
                                temp_draw.text(
                                    (x + dx, current_line_y + dy),
                                    line,
                                    font=font,
                                    fill=self._stroke_color
                                )
            
            # 绘制主文字，考虑渐变和字体样式
            if self._gradient_enabled and gradient_image:
                # 使用渐变绘制
                gradient_result = self._draw_text_with_style(temp_draw, x, current_line_y, line, font, gradient_image)
                if gradient_result:
                    # 将渐变文字合成到主图像
                    temp_image = Image.alpha_composite(temp_image, gradient_result)
            else:
                # 使用纯色绘制（可能返回合成图像用于斜体）
                color_result = self._draw_text_with_style(temp_draw, x, current_line_y, line, font, self._text_color)
                if color_result:
                    temp_image = Image.alpha_composite(temp_image, color_result)
            
            # 移动到下一行
            if i < len(line_heights) - 1 and line_heights:
                current_y += line_heights[i] + int(max_line_height * (self._line_spacing - 1))
        
        # 扫描像素获取实际边界
        pixels = temp_image.load()
        left = self._width
        top = self._height
        right = 0
        bottom = 0
        found_pixels = False
        
        for y in range(self._height):
            for x in range(self._width):
                r, g, b, a = pixels[x, y]
                # 检测非透明像素（文字或描边）
                if a > 5:  # 使用阈值5来忽略抗锯齿的轻微透明
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)
                    found_pixels = True
        
        if not found_pixels:
            return (0, 0, 0, 0)
            
        return (left, top, right + 1, bottom + 1)  # +1 转换为exclusive边界
    
    def _calculate_visual_center_y(self, lines: list, font, temp_draw: ImageDraw.Draw) -> int:
        """基于实际渲染像素计算视觉居中Y位置"""
        if not lines:
            return self._height // 2
            
        # 创建一个临时图像来渲染文字并分析实际像素边界
        test_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        test_draw = ImageDraw.Draw(test_image)
        
        # 先使用字体度量计算基础位置
        line_heights = []
        line_widths = []
        
        for line in lines:
            # 使用字间距计算宽度
            line_width = self._get_text_width_with_spacing(line, font)
            bbox = temp_draw.textbbox((0, 0), line, font=font)
            line_height = bbox[3] - bbox[1]
            line_widths.append(line_width)
            line_heights.append(line_height)
        
        if not line_heights:
            return self._height // 2
            
        max_line_height = max(line_heights)
        total_height = sum(line_heights) + (len(lines) - 1) * int(max_line_height * (self._line_spacing - 1))
        base_start_y = (self._height - total_height) // 2
        
        # 在临时图像上渲染文字（使用基础位置）
        current_y = base_start_y
        for i, line in enumerate(lines):
            if i >= len(line_widths):
                break
                
            line_width = line_widths[i]
            line_height = line_heights[i] if i < len(line_heights) else max_line_height
            
            # 计算X位置
            if self._text_align == TextAlign.CENTER:
                x = max(0, (self._width - line_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                x = max(0, self._width - line_width)
            else:  # LEFT
                x = 0
            
            # 渲染文字到临时图像
            test_draw.text((x, current_y), line, font=font, fill=(255, 255, 255, 255))
            
            # 移动到下一行
            if i < len(line_heights) - 1 and line_heights:
                current_y += line_heights[i] + int(max_line_height * (self._line_spacing - 1))
        
        # 分析实际像素边界
        pixels = test_image.load()
        left = self._width
        top = self._height
        right = 0
        bottom = 0
        found_pixels = False
        
        for y in range(self._height):
            for x in range(self._width):
                r, g, b, a = pixels[x, y]
                if a > 10:  # 检测到文字像素
                    left = min(left, x)
                    top = min(top, y)
                    right = max(right, x)
                    bottom = max(bottom, y)
                    found_pixels = True
        
        if not found_pixels:
            return base_start_y
        
        # 计算实际文字中心
        actual_text_center = (top + bottom) // 2
        layer_center = self._height // 2
        
        # 计算需要调整的偏移量
        center_offset = layer_center - actual_text_center
        
        # 返回调整后的Y位置
        return max(0, min(self._height - total_height, base_start_y + center_offset))

    def render_text(self) -> Image.Image:
        """渲染文字为图像（基于实际像素边界的智能居中算法）"""
        with self._render_lock:
            if self._cached_image:
                return self._cached_image
    
            if self._should_supersample():
                image = self._render_text_supersampled()
            else:
                image = self._render_text_internal()
    
            self._cached_image = image
            return image

    def _should_supersample(self) -> bool:
        """判断是否启用超采样渲染以提升质量"""
        scale = max(2, int(getattr(self, '_supersample_scale', 2)))
        enabled = getattr(self, '_supersample_enabled', True)
        if not enabled or scale <= 1:
            return False

        # 避免超大图层导致性能问题
        max_pixels = 4_000_000  # 约4MP
        return (self._width * self._height) <= max_pixels

    def _render_text_supersampled(self) -> Image.Image:
        """使用超采样渲染文字，再缩放回目标尺寸"""
        scale = max(2, int(getattr(self, '_supersample_scale', 2)))
        prev_auto_fit_lock = self._auto_fit_lock

        # 先在基准尺度完成自动适配，避免超采样阶段再次触发自适配导致
        # “大尺寸渲染后缩回旧尺寸”的非等比压缩。
        if self._auto_fit_text_box and not self._auto_fit_lock:
            self._update_text_box_size_if_needed()

        # 保存原始参数
        original = {
            'width': self._width,
            'height': self._height,
            'font_size': self._font_size,
            'stroke_width': self._stroke_width,
            'letter_spacing': self._letter_spacing,
            'text_box_padding': self._text_box_padding,
            'background_padding': self._background_padding
        }

        try:
            # 放大参数
            self._width = int(self._width * scale)
            self._height = int(self._height * scale)
            self._font_size = int(self._font_size * scale)
            self._stroke_width = int(self._stroke_width * scale)
            self._letter_spacing = int(self._letter_spacing * scale)
            self._text_box_padding = int(self._text_box_padding * scale)
            self._background_padding = int(self._background_padding * scale)

            # 锁住自适配，避免在放大参数下重算图层尺寸
            self._auto_fit_lock = True

            # 重新渲染为大图
            large_image = self._render_text_internal()
            # 缩回目标尺寸
            image = large_image.resize((original['width'], original['height']), Image.Resampling.LANCZOS)
        finally:
            # 还原参数
            self._width = original['width']
            self._height = original['height']
            self._font_size = original['font_size']
            self._stroke_width = original['stroke_width']
            self._letter_spacing = original['letter_spacing']
            self._text_box_padding = original['text_box_padding']
            self._background_padding = original['background_padding']
            self._auto_fit_lock = prev_auto_fit_lock

        return self._normalize_auto_fit_padding(image)

    def _normalize_auto_fit_padding(self, image: Image.Image) -> Image.Image:
        """自动适配时按真实非透明像素统一四边内边距。"""
        if not self._auto_fit_text_box or self._auto_fit_lock or self._background_enabled:
            return image

        try:
            bbox = image.getchannel('A').getbbox()
            if not bbox:
                return image

            pad = max(0, int(self._text_box_padding))
            left, top, right, bottom = bbox
            content_width = max(1, right - left)
            content_height = max(1, bottom - top)
            target_width = max(1, content_width + pad * 2)
            target_height = max(1, content_height + pad * 2)

            already_normalized = (
                image.width == target_width
                and image.height == target_height
                and left == pad
                and top == pad
            )
            if already_normalized:
                return image

            cropped = image.crop(bbox)
            normalized = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
            normalized.paste(cropped, (pad, pad))
            self._width = target_width
            self._height = target_height
            return normalized
        except Exception:
            return image

    def _render_text_internal(self) -> Image.Image:
        """内部渲染实现（不写缓存）"""
        # 自动适配边框：在渲染前保证尺寸与当前文字一致
        self._update_text_box_size_if_needed()

        # 获取字体
        font = self._get_font_object()

        # 处理多行文字
        lines = self._current_text.split('\n')

        # 计算基础布局
        temp_image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        temp_draw = ImageDraw.Draw(temp_image)

        line_heights = []
        line_widths = []
        line_left_offsets = []
        line_top_offsets = []
        stroke_for_measure = self._stroke_width if self._stroke_enabled else 0
        italic_shear_extra = 0
        if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
            italic_shear_extra = int(math.tan(math.radians(12.0)) * max(1, self._font_size))

        for line in lines:
            # 使用字间距计算宽度
            line_text = line if line else " "
            line_width = self._get_text_width_with_spacing(line_text, font)
            bbox = temp_draw.textbbox((0, 0), line_text, font=font, stroke_width=stroke_for_measure)
            bbox_width = max(0, bbox[2] - bbox[0])
            bbox_height = max(0, bbox[3] - bbox[1])

            render_width = max(line_width, bbox_width) + italic_shear_extra
            line_widths.append(render_width)
            line_heights.append(bbox_height)
            # 关键修复：必须完整使用 -bbox 偏移（含正负），否则中文字体 top>0 时会整体下移
            line_left_offsets.append(int(-bbox[0]))
            line_top_offsets.append(int(-bbox[1]))

        # 计算总高度
        if not line_heights:
            total_height = 0
            max_line_height = 0
        else:
            max_line_height = max(line_heights)
            total_height = sum(line_heights) + (len(lines) - 1) * int(max_line_height * (self._line_spacing - 1))

        # 竖排：单独布局渲染
        if self._vertical_layout:
            return self._render_text_vertical_internal(font, lines, temp_draw)

        # 自动适配边框时，以边距为锚点；否则沿用原视觉居中算法
        if self._auto_fit_text_box:
            final_start_y = max(0, self._text_box_padding)
        else:
            # 非自动适配时，使用与测量一致的几何居中，避免视觉中心算法与bbox口径不一致
            final_start_y = max(0, (self._height - total_height) // 2)

        # 准备渐变图像（如果启用）
        gradient_image = None
        if self._gradient_enabled:
            gradient_image = self._create_gradient_image(self._width, self._height)

        # 创建最终图像（单遍渲染）
        image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # 绘制文字背景（如果启用）
        if self._background_enabled:
            self._draw_text_background(draw, lines, font, final_start_y, line_widths, line_heights, max_line_height)

        # 使用调整后的位置进行最终渲染
        current_y = final_start_y
        for i, line in enumerate(lines):
            if i >= len(line_widths):
                break

            line_width = line_widths[i]
            line_height = line_heights[i] if i < len(line_heights) else max_line_height
            x_offset = line_left_offsets[i] if i < len(line_left_offsets) else 0
            y_offset = line_top_offsets[i] if i < len(line_top_offsets) else 0

            # 计算X位置 - 改进水平居中
            if self._text_align == TextAlign.CENTER:
                x = max(0, (self._width - line_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                if self._auto_fit_text_box:
                    x = max(0, self._width - self._text_box_padding - line_width)
                else:
                    x = max(0, self._width - line_width)
            else:  # LEFT
                if self._auto_fit_text_box:
                    x = max(0, self._text_box_padding)
                else:
                    x = 0

            # 垂直位置 - 使用调整后的Y位置
            current_line_y = current_y
            draw_x = x + x_offset
            draw_y = current_line_y + y_offset

            # 绘制描边
            if self._stroke_enabled and self._stroke_width > 0:
                if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
                    stroke_mask = self._create_text_mask_with_spacing(
                        draw_x,
                        draw_y,
                        line,
                        font,
                        stroke_width=self._stroke_width,
                        bold=self._font_style == FontStyle.BOLD_ITALIC
                    )
                    stroke_colored = Image.new('RGBA', (self._width, self._height), self._stroke_color)
                    stroke_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                    stroke_result.paste(stroke_colored, (0, 0), stroke_mask)
                    image = Image.alpha_composite(image, stroke_result)
                else:
                    if self._letter_spacing != 0:
                        self._draw_text_with_letter_spacing(
                            draw,
                            draw_x,
                            draw_y,
                            line,
                            font,
                            self._stroke_color,
                            stroke_width=self._stroke_width,
                            stroke_fill=self._stroke_color,
                            bold=self._font_style == FontStyle.BOLD
                        )
                    else:
                        draw.text(
                            (draw_x, draw_y),
                            line,
                            font=font,
                            fill=self._stroke_color,
                            stroke_width=self._stroke_width,
                            stroke_fill=self._stroke_color
                        )

            # 绘制主文字，考虑渐变和字体样式
            if self._gradient_enabled and gradient_image:
                if self._letter_spacing != 0:
                    text_mask = self._create_text_mask_with_spacing(
                        draw_x,
                        draw_y,
                        line,
                        font,
                        stroke_width=0,
                        bold=self._font_style in (FontStyle.BOLD, FontStyle.BOLD_ITALIC)
                    )
                    gradient_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                    gradient_result.paste(gradient_image, (0, 0), text_mask)
                    image = Image.alpha_composite(image, gradient_result)
                else:
                    gradient_result = self._draw_text_with_style(draw, draw_x, draw_y, line, font, gradient_image)
                    if gradient_result:
                        image = Image.alpha_composite(image, gradient_result)
            else:
                if self._letter_spacing != 0:
                    if self._font_style in (FontStyle.ITALIC, FontStyle.BOLD_ITALIC):
                        text_mask = self._create_text_mask_with_spacing(
                            draw_x,
                            draw_y,
                            line,
                            font,
                            stroke_width=0,
                            bold=self._font_style == FontStyle.BOLD_ITALIC
                        )
                        colored = Image.new('RGBA', (self._width, self._height), self._text_color)
                        color_result = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
                        color_result.paste(colored, (0, 0), text_mask)
                        image = Image.alpha_composite(image, color_result)
                    else:
                        self._draw_text_with_letter_spacing(
                            draw,
                            draw_x,
                            draw_y,
                            line,
                            font,
                            self._text_color,
                            stroke_width=0,
                            stroke_fill=None,
                            bold=self._font_style == FontStyle.BOLD
                        )
                else:
                    color_result = self._draw_text_with_style(draw, draw_x, draw_y, line, font, self._text_color)
                    if color_result:
                        image = Image.alpha_composite(image, color_result)

            # 移动到下一行
            if i < len(line_heights) - 1 and line_heights:
                current_y += line_heights[i] + int(max_line_height * (self._line_spacing - 1))

        # 应用透明度
        if self._opacity < 1.0:
            alpha = image.split()[-1]
            alpha = alpha.point(lambda p: int(p * self._opacity))
            image.putalpha(alpha)

        return self._normalize_auto_fit_padding(image)

    def _render_text_vertical_internal(self, font, lines: List[str], temp_draw: ImageDraw.Draw) -> Image.Image:
        """竖排渲染实现。"""
        image = Image.new('RGBA', (self._width, self._height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)

        # 计算列宽和列高
        column_data = []
        stroke_for_measure = self._stroke_width if self._stroke_enabled else 0
        for line in lines:
            chars = list(line) if line else [" "]
            char_sizes = []
            for ch in chars:
                bbox = temp_draw.textbbox((0, 0), ch, font=font, stroke_width=stroke_for_measure)
                char_sizes.append((
                    max(0, bbox[2] - bbox[0]),
                    max(0, bbox[3] - bbox[1]),
                    int(-bbox[0]),
                    int(-bbox[1]),
                    ch
                ))
            col_width = max((w for w, _, _, _, _ in char_sizes), default=0)
            base_gap = int(max((h for _, h, _, _, _ in char_sizes), default=0) * (self._line_spacing - 1))
            char_gap = base_gap + self._letter_spacing
            col_height = sum(h for _, h, _, _, _ in char_sizes) + max(0, len(char_sizes) - 1) * char_gap
            column_data.append((col_width, col_height, char_sizes, char_gap))

        total_width = 0
        if column_data:
            max_col_width = max(w for w, _, _, _ in column_data)
            col_gap = int(max_col_width * (self._line_spacing - 1))
            total_width = sum(w for w, _, _, _ in column_data) + max(0, len(column_data) - 1) * col_gap
        else:
            col_gap = 0

        max_height = max((h for _, h, _, _ in column_data), default=0)

        # 起始位置
        if self._auto_fit_text_box:
            start_x = max(0, self._text_box_padding)
            start_y = max(0, self._text_box_padding)
        else:
            if self._text_align == TextAlign.CENTER:
                start_x = max(0, (self._width - total_width) // 2)
            elif self._text_align == TextAlign.RIGHT:
                start_x = max(0, self._width - total_width)
            else:
                start_x = 0
            start_y = max(0, (self._height - max_height) // 2)

        gradient_image = self._create_gradient_image(self._width, self._height) if self._gradient_enabled else None

        current_x = start_x
        for col_width, col_height, char_sizes, char_gap in column_data:
            current_y = start_y
            for char_width, char_height, char_left_off, char_top_off, ch in char_sizes:
                char_x = current_x + max(0, (col_width - char_width) // 2) + char_left_off
                char_y = current_y + char_top_off

                if self._stroke_enabled and self._stroke_width > 0:
                    draw.text(
                        (char_x, char_y),
                        ch,
                        font=font,
                        fill=self._stroke_color,
                        stroke_width=self._stroke_width,
                        stroke_fill=self._stroke_color
                    )

                if self._gradient_enabled and gradient_image is not None:
                    gradient_result = self._draw_text_with_style(draw, char_x, char_y, ch, font, gradient_image)
                    if gradient_result:
                        image = Image.alpha_composite(image, gradient_result)
                else:
                    color_result = self._draw_text_with_style(draw, char_x, char_y, ch, font, self._text_color)
                    if color_result:
                        image = Image.alpha_composite(image, color_result)
                    else:
                        draw.text((char_x, char_y), ch, font=font, fill=self._text_color)

                current_y += char_height + char_gap

            current_x += col_width + col_gap

        if self._opacity < 1.0:
            alpha = image.split()[-1]
            alpha = alpha.point(lambda p: int(p * self._opacity))
            image.putalpha(alpha)

        return self._normalize_auto_fit_padding(image)
    
    # 属性访问器
    @Property(str)
    def name(self):
        return self._name
    
    @name.setter
    def name(self, value):
        if self._name != value:
            self._name = value
            self.changed.emit()
    
    @Property(int)
    def x(self):
        return self._x
    
    @x.setter
    def x(self, value):
        if self._x != value:
            self._x = value
            self.changed.emit()
    
    @Property(int)
    def y(self):
        return self._y
    
    @y.setter
    def y(self, value):
        if self._y != value:
            self._y = value
            self.changed.emit()
    
    @Property(int)
    def width(self):
        return self._width
    
    @width.setter
    def width(self, value):
        if self._width != value and value > 0:
            self._width = value
            self._cached_image = None
            self.changed.emit()
    
    @Property(int)
    def height(self):
        return self._height
    
    @height.setter
    def height(self, value):
        if self._height != value and value > 0:
            self._height = value
            self._cached_image = None
            self.changed.emit()
    
    @Property(bool)
    def visible(self):
        return self._visible
    
    @visible.setter
    def visible(self, value):
        if self._visible != value:
            self._visible = value
            self.changed.emit()
    
    @Property(float)
    def opacity(self):
        return self._opacity
    
    @opacity.setter
    def opacity(self, value):
        if self._opacity != value:
            self._opacity = max(0.0, min(1.0, value))
            self._cached_image = None
            self.changed.emit()
    
    @Property(bool)
    def locked(self):
        return self._locked
    
    @locked.setter
    def locked(self, value):
        if self._locked != value:
            self._locked = value
            self.changed.emit()
    
    @Property(bool)
    def use_original_size(self):
        return self._use_original_size
    
    @use_original_size.setter
    def use_original_size(self, value):
        if self._use_original_size != value:
            self._use_original_size = value
            self.changed.emit()
    
    @Property(str)
    def font_family(self):
        return self._font_family
    
    @font_family.setter
    def font_family(self, value):
        if self._font_family != value:
            self._font_family = value
            self._cached_image = None
            self._update_text_box_size_if_needed()
            self.changed.emit()
    
    @Property(int)
    def font_size(self):
        return self._font_size
    
    @font_size.setter
    def font_size(self, value):
        if self._font_size != value and value > 0:
            self._font_size = value
            self._cached_image = None
            self._update_text_box_size_if_needed()
            self.changed.emit()
    
    @Property(str)
    def font_style(self):
        return self._font_style.name
    
    @font_style.setter
    def font_style(self, value):
        """设置字体样式，接受FontStyle枚举或字符串"""
        try:
            if isinstance(value, str):
                new_style = FontStyle[value]
            elif isinstance(value, FontStyle):
                new_style = value
            else:
                # 如果是其他类型，尝试转换为字符串再处理
                new_style = FontStyle[str(value)]

            if self._font_style != new_style:
                self._font_style = new_style
                self._cached_image = None
                self._update_text_box_size_if_needed()
                self.changed.emit()
        except (KeyError, ValueError):
            # 如果转换失败，保持原有样式不变
            safe_print(f"警告：无效的字体样式值: {value}")
            pass
    
    @Property(str)
    def current_text(self):
        return self._current_text

    @current_text.setter
    def current_text(self, value):
        self.set_current_text(value)

    def set_current_text(self, value, emit_signals: bool = True, force: bool = False):
        """设置当前显示文字。

        批量导出会频繁切换文字内容，调用方可用 emit_signals=False 避免触发 UI 刷新；
        force=True 用于单候选文案等场景，即使文字未变化也清理缓存并通知。
        """
        value = "" if value is None else str(value)
        if not force and self._current_text == value:
            return False

        self._current_text = value
        self._cached_image = None
        self._update_text_box_size_if_needed()

        should_emit_signals = bool(emit_signals)
        if should_emit_signals:
            parent_doc = None
            if hasattr(self, '_parent') and self._parent:
                parent_doc = self._parent
            elif hasattr(self, 'parent') and self.parent():
                parent_doc = self.parent()

            if parent_doc and hasattr(parent_doc, '_is_batch_export_running'):
                should_emit_signals = not parent_doc._is_batch_export_running

        if should_emit_signals:
            self.text_changed.emit()
            self.changed.emit()

        return True

    def set_current_text_silent(self, value):
        """批量/后台任务专用：更新文字并清缓存，但不发射 UI 信号。"""
        return self.set_current_text(value, emit_signals=False)

    # 文字样式属性
    @Property(tuple)
    def text_color(self):
        return self._text_color

    @text_color.setter
    def text_color(self, value):
        if self._text_color != value:
            # 确保颜色值在有效范围内
            if isinstance(value, (tuple, list)) and len(value) >= 3:
                r = max(0, min(255, int(value[0])))
                g = max(0, min(255, int(value[1])))
                b = max(0, min(255, int(value[2])))
                a = max(0, min(255, int(value[3]))) if len(value) > 3 else 255
                self._text_color = (r, g, b, a)
                self._cached_image = None
                self.changed.emit()

    @Property(str)
    def text_align(self):
        return self._text_align.name

    @text_align.setter
    def text_align(self, value):
        """设置文字对齐方式，接受TextAlign枚举或字符串"""
        if isinstance(value, str):
            new_align = TextAlign[value]
        else:
            new_align = value

        if self._text_align != new_align:
            self._text_align = new_align
            self._cached_image = None
            self.changed.emit()

    @Property(float)
    def line_spacing(self):
        return self._line_spacing

    @line_spacing.setter
    def line_spacing(self, value):
        if self._line_spacing != value and value > 0:
            self._line_spacing = value
            self._cached_image = None
            self._update_text_box_size_if_needed()
            self.changed.emit()

    @Property(int)
    def letter_spacing(self):
        return self._letter_spacing

    @letter_spacing.setter
    def letter_spacing(self, value):
        if self._letter_spacing != value:
            self._letter_spacing = value
            self._cached_image = None
            self._update_text_box_size_if_needed()
            self.changed.emit()

    @Property(int)
    def text_box_padding(self):
        return self._text_box_padding

    @text_box_padding.setter
    def text_box_padding(self, value):
        value = max(0, int(value))
        if self._text_box_padding != value:
            self._text_box_padding = value
            self._cached_image = None
            self._update_text_box_size_if_needed()
            self.changed.emit()

    @Property(bool)
    def auto_fit_text_box(self):
        return self._auto_fit_text_box

    @auto_fit_text_box.setter
    def auto_fit_text_box(self, value):
        value = bool(value)
        if self._auto_fit_text_box != value:
            self._auto_fit_text_box = value
            self._cached_image = None
            self._update_text_box_size_if_needed()
            self.changed.emit()

    @Property(bool)
    def vertical_layout(self):
        return self._vertical_layout

    @vertical_layout.setter
    def vertical_layout(self, value):
        value = bool(value)
        if self._vertical_layout != value:
            self._vertical_layout = value
            self._cached_image = None
            self._update_text_box_size_if_needed()
            self.changed.emit()

    # 描边属性
    @Property(bool)
    def stroke_enabled(self):
        return self._stroke_enabled

    @stroke_enabled.setter
    def stroke_enabled(self, value):
        if self._stroke_enabled != value:
            self._stroke_enabled = value
            self._cached_image = None
            self._update_text_box_size_if_needed()
            self.changed.emit()

    @Property(int)
    def stroke_width(self):
        return self._stroke_width

    @stroke_width.setter
    def stroke_width(self, value):
        if self._stroke_width != value and value > 0:
            self._stroke_width = value
            self._cached_image = None
            self._update_text_box_size_if_needed()
            self.changed.emit()

    @Property(tuple)
    def stroke_color(self):
        return self._stroke_color

    @stroke_color.setter
    def stroke_color(self, value):
        if self._stroke_color != value:
            # 确保颜色值在有效范围内
            if isinstance(value, (tuple, list)) and len(value) >= 3:
                r = max(0, min(255, int(value[0])))
                g = max(0, min(255, int(value[1])))
                b = max(0, min(255, int(value[2])))
                a = max(0, min(255, int(value[3]))) if len(value) > 3 else 255
                self._stroke_color = (r, g, b, a)
                self._cached_image = None
                self.changed.emit()

    # 背景属性
    @Property(bool)
    def background_enabled(self):
        return self._background_enabled

    @background_enabled.setter
    def background_enabled(self, value):
        if self._background_enabled != value:
            self._background_enabled = value
            self._cached_image = None
            self.changed.emit()

    @Property(tuple)
    def background_color(self):
        return self._background_color

    @background_color.setter
    def background_color(self, value):
        if self._background_color != value:
            # 确保颜色值在有效范围内
            if isinstance(value, (tuple, list)) and len(value) >= 3:
                r = max(0, min(255, int(value[0])))
                g = max(0, min(255, int(value[1])))
                b = max(0, min(255, int(value[2])))
                a = max(0, min(255, int(value[3]))) if len(value) > 3 else 255
                self._background_color = (r, g, b, a)
                self._cached_image = None
                self.changed.emit()

    @Property(int)
    def background_padding(self):
        return self._background_padding

    @background_padding.setter
    def background_padding(self, value):
        """设置背景内边距，支持正负值
        
        正值：背景大于文字（向外扩展）
        负值：背景小于文字（向内收缩）
        零值：背景与文字完全贴合
        """
        if self._background_padding != value:  # 移除value >= 0的限制，允许负值
            self._background_padding = value
            self._cached_image = None
            self.changed.emit()

    # 渐变属性
    @Property(bool)
    def gradient_enabled(self):
        return self._gradient_enabled

    @gradient_enabled.setter
    def gradient_enabled(self, value):
        if self._gradient_enabled != value:
            self._gradient_enabled = value
            self._cached_image = None
            self.changed.emit()

    @Property(str)
    def gradient_type(self):
        return self._gradient_type.name

    @gradient_type.setter
    def gradient_type(self, value):
        if isinstance(value, str):
            new_type = GradientType[value]
        else:
            new_type = value

        if self._gradient_type != new_type:
            self._gradient_type = new_type
            self._cached_image = None
            self.changed.emit()

    @Property(str)
    def gradient_direction(self):
        return self._gradient_direction.name

    @gradient_direction.setter
    def gradient_direction(self, value):
        if isinstance(value, str):
            new_direction = GradientDirection[value]
        else:
            new_direction = value

        if self._gradient_direction != new_direction:
            self._gradient_direction = new_direction
            self._cached_image = None
            self.changed.emit()

    @Property(tuple)
    def gradient_start_color(self):
        return self._gradient_start_color

    @gradient_start_color.setter
    def gradient_start_color(self, value):
        if self._gradient_start_color != value:
            if isinstance(value, (tuple, list)) and len(value) >= 3:
                r = max(0, min(255, int(value[0])))
                g = max(0, min(255, int(value[1])))
                b = max(0, min(255, int(value[2])))
                a = max(0, min(255, int(value[3]))) if len(value) > 3 else 255
                self._gradient_start_color = (r, g, b, a)
                self._cached_image = None
                self.changed.emit()

    @Property(tuple)
    def gradient_end_color(self):
        return self._gradient_end_color

    @gradient_end_color.setter
    def gradient_end_color(self, value):
        if self._gradient_end_color != value:
            if isinstance(value, (tuple, list)) and len(value) >= 3:
                r = max(0, min(255, int(value[0])))
                g = max(0, min(255, int(value[1])))
                b = max(0, min(255, int(value[2])))
                a = max(0, min(255, int(value[3]))) if len(value) > 3 else 255
                self._gradient_end_color = (r, g, b, a)
                self._cached_image = None
                self.changed.emit()

    @Property(float)
    def gradient_center_x(self):
        return self._gradient_center_x

    @gradient_center_x.setter
    def gradient_center_x(self, value):
        if self._gradient_center_x != value:
            self._gradient_center_x = max(0.0, min(1.0, value))
            self._cached_image = None
            self.changed.emit()

    @Property(float)
    def gradient_center_y(self):
        return self._gradient_center_y

    @gradient_center_y.setter
    def gradient_center_y(self, value):
        if self._gradient_center_y != value:
            self._gradient_center_y = max(0.0, min(1.0, value))
            self._cached_image = None
            self.changed.emit()
    
    def get_text_lines(self) -> List[str]:
        """获取文字行列表"""
        return self._text_lines.copy()
    
    def set_text_lines(self, lines: List[str]):
        """设置文字行列表"""
        self._text_lines = lines.copy()
        if self._text_lines and (self._current_text is None or str(self._current_text).strip() == ""):
            self._current_text = self._text_lines[0]
        self._cached_image = None
        self._update_text_box_size_if_needed()
        self.text_changed.emit()
        self.changed.emit()

    def parse_text_input_to_lines(self, text: str) -> List[str]:
        """根据当前绑定模式解析编辑器输入"""
        raw_text = "" if text is None else str(text)
        if self._text_binding_enabled:
            lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
            return lines

        # 非绑定模式：整个文本作为一条文案，保留真实换行
        if raw_text.strip() == "":
            return []
        return [raw_text]
    
    def add_text_line(self, text: str):
        """添加新的文字行 - 确保绑定管理器能正确响应"""
        if text and text not in self._text_lines:
            self._text_lines.append(text)
            self._cached_image = None
            safe_print(f"[文字图层] 添加新文案: '{text}'")
            self.text_changed.emit()
            self.changed.emit()
            return True
        return False
    
    def insert_text_line(self, index: int, text: str):
        """在指定位置插入文字行"""
        if text and 0 <= index <= len(self._text_lines):
            if text not in self._text_lines:
                self._text_lines.insert(index, text)
                self._cached_image = None
                safe_print(f"[文字图层] 在位置 {index} 插入新文案: '{text}'")
                self.text_changed.emit()
                self.changed.emit()
                return True
        return False
    
    def remove_text_line(self, text: str):
        """移除指定的文字行"""
        if text in self._text_lines:
            self._text_lines.remove(text)
            # 如果移除的是当前显示的文字，切换到第一个可用的
            if self._current_text == text and self._text_lines:
                self._current_text = self._text_lines[0]
            elif not self._text_lines:
                self._current_text = ""
            self._cached_image = None
            safe_print(f"[文字图层] 移除文案: '{text}'")
            self.text_changed.emit()
            self.changed.emit()
            return True
        return False

    @Property(str)
    def text_content(self):
        """获取所有文字内容，以换行符分隔（兼容性属性）"""
        if not self._text_lines:
            return ""
        if self._text_binding_enabled:
            return "\n".join(self._text_lines)
        return str(self._text_lines[0])

    @text_content.setter
    def text_content(self, value):
        """设置文字内容"""
        parsed_lines = self.parse_text_input_to_lines(value)
        self.set_text_lines(parsed_lines)

    @Property(bool)
    def text_binding_enabled(self):
        """是否启用按行绑定模式"""
        return self._text_binding_enabled

    @text_binding_enabled.setter
    def text_binding_enabled(self, enabled):
        enabled = bool(enabled)
        if self._text_binding_enabled == enabled:
            return

        # 切换模式时保持可见内容不丢失
        if self._text_binding_enabled:
            source_text = "\n".join(self._text_lines) if self._text_lines else str(self._current_text or "")
        else:
            source_text = str(self._text_lines[0]) if self._text_lines else str(self._current_text or "")

        self._text_binding_enabled = enabled
        parsed_lines = self.parse_text_input_to_lines(source_text)
        self._text_lines = parsed_lines
        self._current_text = parsed_lines[0] if parsed_lines else ""
        self._cached_image = None
        self._update_text_box_size_if_needed()
        self.text_changed.emit()
        self.changed.emit()
    
    def serialize(self) -> dict:
        """序列化图层数据"""
        return {
            'type': 'text',
            'name': self._name,
            'x': self._x,
            'y': self._y,
            'width': self._width,
            'height': self._height,
            'visible': self._visible,
            'opacity': self._opacity,
            'locked': self._locked,
            'use_original_size': self._use_original_size,
            'text_lines': self._text_lines,
            'current_text': self._current_text,
            'random_mode': self._random_mode,
            'text_binding_enabled': self._text_binding_enabled,
            'font_family': self._font_family,
            'font_size': self._font_size,
            'font_style': self._font_style.name,
            'text_color': self._text_color,
            'text_align': self._text_align.name,
            'line_spacing': self._line_spacing,
            'letter_spacing': self._letter_spacing,
            'text_box_padding': self._text_box_padding,
            'auto_fit_text_box': self._auto_fit_text_box,
            'vertical_layout': self._vertical_layout,
            'stroke_enabled': self._stroke_enabled,
            'stroke_width': self._stroke_width,
            'stroke_color': self._stroke_color,
            'background_enabled': self._background_enabled,
            'background_color': self._background_color,
            'background_padding': self._background_padding,
            'gradient_enabled': self._gradient_enabled,
            'gradient_type': self._gradient_type.name,
            'gradient_direction': self._gradient_direction.name,
            'gradient_angle': self._gradient_angle,
            'gradient_start_color': self._gradient_start_color,
            'gradient_end_color': self._gradient_end_color,
            'gradient_center_x': self._gradient_center_x,
            'gradient_center_y': self._gradient_center_y,
            'supersample_enabled': self._supersample_enabled,
            'supersample_scale': self._supersample_scale,
            'shadow_enabled': getattr(self, 'shadow_enabled', False),
            'shadow_offset_x': getattr(self, 'shadow_offset_x', 2),
            'shadow_offset_y': getattr(self, 'shadow_offset_y', 2),
            'shadow_blur': getattr(self, 'shadow_blur', 4),
            'shadow_color': getattr(self, 'shadow_color', (0, 0, 0, 128)),
            'glow_enabled': getattr(self, 'glow_enabled', False),
            'glow_strength': getattr(self, 'glow_strength', 50),
            'glow_radius': getattr(self, 'glow_radius', 6)
        }
    
    @classmethod
    def deserialize(cls, data: dict, parent=None):
        """反序列化图层数据"""
        layer = cls(
            name=data.get('name', '文字图层'),
            x=data.get('x', 0),
            y=data.get('y', 0),
            width=data.get('width', 200),
            height=data.get('height', 100),
            parent=parent
        )
        
        layer._visible = data.get('visible', True)
        layer._opacity = data.get('opacity', 1.0)
        layer._locked = data.get('locked', False)
        layer._use_original_size = data.get('use_original_size', False)
        layer._text_lines = data.get('text_lines', ['示例文字'])
        layer._current_text = data.get('current_text', '示例文字')
        layer._random_mode = data.get('random_mode', False)
        layer._text_binding_enabled = data.get('text_binding_enabled', True)
        layer._font_family = data.get('font_family', layer._get_default_font())
        layer._font_size = data.get('font_size', 24)
        layer._font_style = FontStyle[data.get('font_style', 'NORMAL')]
        layer._text_color = tuple(data.get('text_color', (0, 0, 0, 255)))
        layer._text_align = TextAlign[data.get('text_align', 'LEFT')]
        layer._line_spacing = data.get('line_spacing', 1.2)
        layer._letter_spacing = data.get('letter_spacing', 0)
        layer._text_box_padding = max(0, int(data.get('text_box_padding', 5)))
        layer._auto_fit_text_box = bool(data.get('auto_fit_text_box', True))
        layer._vertical_layout = bool(data.get('vertical_layout', False))
        layer._stroke_enabled = data.get('stroke_enabled', False)
        layer._stroke_width = data.get('stroke_width', 2)
        layer._stroke_color = tuple(data.get('stroke_color', (255, 255, 255, 255)))
        layer._background_enabled = data.get('background_enabled', False)
        layer._background_color = tuple(data.get('background_color', (255, 255, 255, 128)))
        layer._background_padding = data.get('background_padding', 5)
        layer._gradient_enabled = data.get('gradient_enabled', False)
        layer._gradient_type = GradientType[data.get('gradient_type', 'LINEAR')]
        layer._gradient_direction = GradientDirection[data.get('gradient_direction', 'HORIZONTAL')]
        layer._gradient_angle = data.get('gradient_angle', 0)
        layer._gradient_start_color = tuple(data.get('gradient_start_color', (255, 0, 0, 255)))
        layer._gradient_end_color = tuple(data.get('gradient_end_color', (0, 0, 255, 255)))
        layer._gradient_center_x = data.get('gradient_center_x', 0.5)
        layer._gradient_center_y = data.get('gradient_center_y', 0.5)
        layer._supersample_enabled = bool(data.get('supersample_enabled', True))
        layer._supersample_scale = max(1, int(data.get('supersample_scale', 2)))
        layer.shadow_enabled = bool(data.get('shadow_enabled', False))
        layer.shadow_offset_x = int(data.get('shadow_offset_x', 2))
        layer.shadow_offset_y = int(data.get('shadow_offset_y', 2))
        layer.shadow_blur = int(data.get('shadow_blur', 4))
        layer.shadow_color = tuple(data.get('shadow_color', (0, 0, 0, 128)))
        layer.glow_enabled = bool(data.get('glow_enabled', False))
        layer.glow_strength = int(data.get('glow_strength', 50))
        layer.glow_radius = int(data.get('glow_radius', 6))
        layer._update_text_box_size_if_needed()

        return layer
    
    def apply_effects(self, image):
        """应用图层特效（简化版本，适用于文字图层）"""
        if image is None:
            return None
        
        # 文字图层暂时不支持复杂特效，直接返回渲染的图像
        # 这是为了保持与普通图层接口的兼容性
        return image
    
    def generate_random_transform_params(self):
        """生成随机变换参数（空实现，保持接口兼容性）"""
        # 文字图层暂时不支持随机变换
        # 这个方法主要是为了保持与普通图层接口的兼容性
        pass
    
    def get_effective_position(self):
        """获取有效位置（简单返回当前位置）"""
        return (self._x, self._y)
    
    def get_effective_clone_positions(self):
        """获取分身位置（简单返回当前位置）"""
        return [self.get_effective_position()]
    
    def duplicate(self, parent=None):
        """创建文字图层的副本"""
        # 创建新的图层实例
        new_layer = TextLayer(
            name=self._name,
            x=self._x,
            y=self._y,
            width=self._width,
            height=self._height,
            parent=parent
        )
        
        # 复制所有属性
        new_layer._visible = self._visible
        new_layer._opacity = self._opacity
        new_layer._locked = self._locked
        new_layer._use_original_size = self._use_original_size
        
        # 复制文字内容
        new_layer._text_lines = self._text_lines.copy()
        new_layer._current_text = self._current_text
        new_layer._random_mode = self._random_mode
        new_layer._text_binding_enabled = self._text_binding_enabled
        
        # 复制字体属性
        new_layer._font_family = self._font_family
        new_layer._font_size = self._font_size
        new_layer._font_style = self._font_style
        
        # 复制文字样式
        new_layer._text_color = self._text_color
        new_layer._text_align = self._text_align
        new_layer._line_spacing = self._line_spacing
        new_layer._letter_spacing = self._letter_spacing
        new_layer._text_box_padding = self._text_box_padding
        new_layer._auto_fit_text_box = self._auto_fit_text_box
        new_layer._vertical_layout = self._vertical_layout
        
        # 复制渐变设置
        new_layer._gradient_enabled = self._gradient_enabled
        new_layer._gradient_type = self._gradient_type
        new_layer._gradient_direction = self._gradient_direction
        new_layer._gradient_start_color = self._gradient_start_color
        new_layer._gradient_end_color = self._gradient_end_color
        new_layer._gradient_angle = self._gradient_angle
        new_layer._gradient_center_x = self._gradient_center_x
        new_layer._gradient_center_y = self._gradient_center_y
        
        # 复制描边设置
        new_layer._stroke_enabled = self._stroke_enabled
        new_layer._stroke_width = self._stroke_width
        new_layer._stroke_color = self._stroke_color
        
        # 复制背景设置
        new_layer._background_enabled = self._background_enabled
        new_layer._background_color = self._background_color
        new_layer._background_padding = self._background_padding
        
        # 清空缓存（新图层需要重新生成）
        new_layer._cached_image = None
        new_layer._font_cache = {}
        
        return new_layer

def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    if not _TEXT_LAYER_DEBUG:
        return
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except:
            # 最后的备选方案
            print("[DEBUG] Message encoding failed")
