"""文字图层虚拟路径工具：统一构建与解析 text_layer:// 协议。"""

from typing import Tuple
import urllib.parse


TEXT_LAYER_VIRTUAL_PREFIX = "text_layer://"


def is_text_layer_virtual_path(value) -> bool:
    """判断是否为文字图层虚拟路径。"""
    return isinstance(value, str) and value.startswith(TEXT_LAYER_VIRTUAL_PREFIX)


def build_text_layer_virtual_path(layer_name: str, text_value) -> str:
    """构建 text_layer:// 虚拟路径，并对文字内容进行 URL 编码。"""
    safe_layer_name = "" if layer_name is None else str(layer_name)
    raw_text = "" if text_value is None else str(text_value)
    encoded_text = urllib.parse.quote(raw_text, safe="")
    return f"{TEXT_LAYER_VIRTUAL_PREFIX}{safe_layer_name}/{encoded_text}"


def parse_text_layer_virtual_path(virtual_path: str) -> Tuple[str, str]:
    """解析 text_layer:// 虚拟路径，返回 (layer_name, decoded_text)。"""
    if not is_text_layer_virtual_path(virtual_path):
        raise ValueError(f"不是文字图层虚拟路径: {virtual_path}")

    path_content = virtual_path[len(TEXT_LAYER_VIRTUAL_PREFIX):]
    separator_pos = path_content.rfind("/")
    if separator_pos < 0:
        raise ValueError(f"虚拟路径缺少分隔符 '/': {virtual_path}")

    layer_name = path_content[:separator_pos]
    encoded_text = path_content[separator_pos + 1:]
    if encoded_text is None:
        encoded_text = ""
    decoded_text = urllib.parse.unquote(encoded_text.strip())
    return layer_name, decoded_text
