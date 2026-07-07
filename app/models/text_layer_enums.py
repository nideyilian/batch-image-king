# -*- coding: utf-8 -*-
"""TextLayer 共享枚举与工具：由拆分脚本从 text_layer.py 提取。"""
import os
from enum import Enum, auto

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

