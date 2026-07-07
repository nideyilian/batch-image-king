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

from app.models.text_layer_font import TextLayerFontMixin
from app.models.text_layer_render import TextLayerRenderMixin
from app.models.text_layer_serialize import TextLayerSerializeMixin

class TextLayer(QObject):
    """文字图层模型类"""
class TextLayer(QObject, TextLayerFontMixin, TextLayerRenderMixin, TextLayerSerializeMixin):
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
        self._text_color_ranges = []
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
        self._clip_text_color_ranges_to_current_text()
        self._cached_image = None
        self._update_text_box_size_if_needed()
        self.text_changed.emit()
        self.changed.emit()

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
