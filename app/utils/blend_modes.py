"""混合模式单一来源（P1-8 收敛）。

历史版本在 document_blend / unified_alpha_compositor / fast_renderer_composite /
document_render 中各自维护了一份 int -> 混合模式名 的映射，取值一致但分散，
存在将来漂移的风险。这里收拢为唯一来源：

- ``BLEND_MODE_NAMES``：0-15 的规范顺序。.cmp 序列化中 ``blend_mode`` 以 int
  存储，此列表的顺序即磁盘格式，**不允许随意增删或换序**。
- ``blend_mode_to_name`` / ``blend_mode_to_int``：int/Enum/str/None 与规范名互转。
- ``BlendMode``：英文值的规范枚举（含专业混合器扩展模式），供新代码使用。
"""

from __future__ import annotations

from enum import Enum
from typing import Union

# .cmp 序列化中 blend_mode 以 int 存储；此列表顺序即 int 值（0-15）。
BLEND_MODE_NAMES = (
    "normal",
    "multiply",
    "screen",
    "overlay",
    "soft_light",
    "hard_light",
    "color_dodge",
    "color_burn",
    "darken",
    "lighten",
    "difference",
    "exclusion",
    "hue",
    "saturation",
    "color",
    "luminosity",
)

_BLEND_MODE_INT_TO_NAME = {i: name for i, name in enumerate(BLEND_MODE_NAMES)}
_BLEND_MODE_NAME_TO_INT = {name: i for i, name in enumerate(BLEND_MODE_NAMES)}

# 中文名 -> 规范英文名（兼容历史中文值，如 document_blend.BlendMode 常量）。
_ZH_TO_NAME = {
    "正常": "normal",
    "正片叠底": "multiply",
    "滤色": "screen",
    "叠加": "overlay",
    "柔光": "soft_light",
    "强光": "hard_light",
    "颜色减淡": "color_dodge",
    "颜色加深": "color_burn",
    "变暗": "darken",
    "变亮": "lighten",
    "差值": "difference",
    "排除": "exclusion",
    "色相": "hue",
    "饱和度": "saturation",
    "颜色": "color",
    "明度": "luminosity",
}


class BlendMode(Enum):
    """规范混合模式枚举（英文值），含专业混合器扩展模式。"""

    # 标准 16 模式（与 BLEND_MODE_NAMES 顺序对应 int 0-15）
    NORMAL = "normal"
    MULTIPLY = "multiply"
    SCREEN = "screen"
    OVERLAY = "overlay"
    SOFT_LIGHT = "soft_light"
    HARD_LIGHT = "hard_light"
    COLOR_DODGE = "color_dodge"
    COLOR_BURN = "color_burn"
    DARKEN = "darken"
    LIGHTEN = "lighten"
    DIFFERENCE = "difference"
    EXCLUSION = "exclusion"
    HUE = "hue"
    SATURATION = "saturation"
    COLOR = "color"
    LUMINOSITY = "luminosity"
    # 专业扩展（photoshop_compositor / professional_blends）
    DISSOLVE = "dissolve"
    LINEAR_BURN = "linear_burn"
    LINEAR_DODGE = "linear_dodge"
    VIVID_LIGHT = "vivid_light"
    LINEAR_LIGHT = "linear_light"
    PIN_LIGHT = "pin_light"
    HARD_MIX = "hard_mix"
    DARKER_COLOR = "darker_color"
    LIGHTER_COLOR = "lighter_color"
    SUBTRACT = "subtract"
    DIVIDE = "divide"


def blend_mode_to_name(value: Union[int, str, Enum, None]) -> str:
    """归一为规范英文小写名。

    - int：按 0-15 磁盘映射转换（未知回退 normal）。
    - Enum：取 ``.value`` 后按字符串处理。
    - 字符串：去除首尾空白并转小写；兼容 ``BlendMode.NORMAL`` 前缀形式；
      中文名映射到英文；未知扩展名原样返回（如 linear_burn）。
    - None：返回 normal。
    """
    if value is None:
        return "normal"
    if isinstance(value, Enum):
        value = value.value
    if isinstance(value, int):
        return _BLEND_MODE_INT_TO_NAME.get(value, "normal")
    text = str(value).strip().lower()
    if text.startswith("blendmode."):
        text = text.split(".", 1)[1]
    return _ZH_TO_NAME.get(text, text)


def blend_mode_to_int(value: Union[int, str, Enum, None]) -> int:
    """归一为 0-15 的磁盘 int；仅标准 16 模式可映射，未知回退 0（normal）。"""
    name = blend_mode_to_name(value)
    return _BLEND_MODE_NAME_TO_INT.get(name, 0)
