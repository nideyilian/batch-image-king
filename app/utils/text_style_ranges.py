"""文字编辑时局部颜色/字号区间的字符级迁移。"""

from __future__ import annotations

from difflib import SequenceMatcher


def _expand_ranges(ranges, text_length: int, key: str) -> list:
    values = [None] * max(0, int(text_length))
    for item in ranges or ():
        try:
            start = max(0, min(len(values), int(item.get("start", 0))))
            end = max(0, min(len(values), int(item.get("end", 0))))
            value = item.get(key)
        except (AttributeError, TypeError, ValueError):
            continue
        for index in range(min(start, end), max(start, end)):
            values[index] = value
    return values


def _compress(values: list, key: str) -> list[dict]:
    result = []
    start = None
    current = None
    for index, value in enumerate(values + [None]):
        if value != current:
            if current is not None and start is not None and index > start:
                result.append({"start": start, "end": index, key: current})
            start = index if value is not None else None
            current = value
    return result


def remap_text_style_ranges(
    old_text: str,
    new_text: str,
    color_ranges=None,
    font_size_ranges=None,
) -> tuple[list[dict], list[dict]]:
    """按文本 diff 迁移局部颜色和字号，返回新的半开 Python 字符区间。"""
    old_text = str(old_text or "")
    new_text = str(new_text or "")
    old_colors = _expand_ranges(color_ranges, len(old_text), "color")
    old_sizes = _expand_ranges(font_size_ranges, len(old_text), "size")
    new_colors = [None] * len(new_text)
    new_sizes = [None] * len(new_text)

    matcher = SequenceMatcher(a=old_text, b=new_text, autojunk=False)
    for tag, old_start, old_end, new_start, new_end in matcher.get_opcodes():
        if tag == "equal":
            for offset in range(new_end - new_start):
                new_colors[new_start + offset] = old_colors[old_start + offset]
                new_sizes[new_start + offset] = old_sizes[old_start + offset]
            continue

        if tag == "delete":
            continue

        # Inserted/replaced characters inherit the nearest existing style.
        if old_start > 0:
            anchor = old_start - 1
        elif old_end < len(old_text):
            anchor = old_end
        else:
            anchor = None
        color = old_colors[anchor] if anchor is not None else None
        size = old_sizes[anchor] if anchor is not None else None
        for index in range(new_start, new_end):
            new_colors[index] = color
            new_sizes[index] = size

    return _compress(new_colors, "color"), _compress(new_sizes, "size")
