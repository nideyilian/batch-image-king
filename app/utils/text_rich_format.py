from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Sequence

from PySide6.QtCore import Qt
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextFormat,
)


@dataclass(frozen=True)
class EditorTextState:
    text: str
    color_ranges: list[dict]
    font_size_ranges: list[dict]


def _rgba(value) -> tuple[int, int, int, int]:
    if isinstance(value, QColor):
        color = value
    elif isinstance(value, str):
        color = QColor(value)
    else:
        values = list(value or ())
        values += [255] * max(0, 4 - len(values))
        color = QColor(*(max(0, min(255, int(item))) for item in values[:4]))
    if not color.isValid():
        return 0, 0, 0, 255
    return color.red(), color.green(), color.blue(), color.alpha()


def _qcolor(value) -> QColor:
    return QColor(*_rgba(value))


def _hex_color(value) -> str:
    red, green, blue, alpha = _rgba(value)
    result = f"#{red:02X}{green:02X}{blue:02X}"
    return result if alpha == 255 else f"{result}{alpha:02X}"


def python_index_to_qt(text: str, index: int) -> int:
    index = max(0, min(len(text), int(index)))
    return len(text[:index].encode("utf-16-le")) // 2


def qt_index_to_python(text: str, index: int) -> int:
    target = max(0, int(index))
    units = 0
    for position, character in enumerate(text):
        next_units = units + (2 if ord(character) > 0xFFFF else 1)
        if target < next_units:
            return position
        units = next_units
        if target == units:
            return position + 1
    return len(text)


def _normalized_model_range(text: str, item: dict) -> tuple[int, int] | None:
    start = max(0, min(len(text), int(item.get("start", 0))))
    end = max(0, min(len(text), int(item.get("end", 0))))
    if end < start:
        start, end = end, start
    return (start, end) if end > start else None


def _select_python_range(cursor: QTextCursor, text: str, start: int, end: int) -> bool:
    start_qt = python_index_to_qt(text, start)
    end_qt = python_index_to_qt(text, end)
    if end_qt <= start_qt:
        return False
    cursor.setPosition(start_qt)
    cursor.setPosition(end_qt, QTextCursor.MoveMode.KeepAnchor)
    return True


def _base_format(
    *,
    font_family: str,
    font_size: int,
    text_color,
    font_weight: int,
    italic: bool,
    letter_spacing: int,
) -> QTextCharFormat:
    font = QFont(str(font_family or "sans-serif"))
    font.setPixelSize(max(1, int(font_size)))
    font.setWeight(QFont.Weight(max(1, min(1000, int(font_weight)))))
    font.setItalic(bool(italic))
    font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, float(letter_spacing))
    char_format = QTextCharFormat()
    char_format.setFont(font)
    char_format.setForeground(QBrush(_qcolor(text_color)))
    return char_format


def build_editor_html(
    text: str,
    *,
    font_family: str,
    font_size: int,
    text_color,
    font_weight: int = 400,
    italic: bool = False,
    letter_spacing: int = 0,
    line_spacing: float = 1.0,
    color_ranges: Iterable[dict] = (),
    font_size_ranges: Iterable[dict] = (),
) -> str:
    text = str(text or "")
    document = QTextDocument()
    document.setUndoRedoEnabled(False)
    document.setPlainText(text)

    cursor = QTextCursor(document)
    cursor.select(QTextCursor.SelectionType.Document)
    cursor.mergeCharFormat(
        _base_format(
            font_family=font_family,
            font_size=font_size,
            text_color=text_color,
            font_weight=font_weight,
            italic=italic,
            letter_spacing=letter_spacing,
        )
    )
    block_format = QTextBlockFormat()
    block_format.setLineHeight(
        max(0.01, float(line_spacing)) * 100.0,
        QTextBlockFormat.LineHeightTypes.ProportionalHeight.value,
    )
    cursor.mergeBlockFormat(block_format)

    for item in color_ranges or ():
        selected = _normalized_model_range(text, item)
        if selected is None or not _select_python_range(cursor, text, *selected):
            continue
        char_format = QTextCharFormat()
        char_format.setForeground(QBrush(_qcolor(item.get("color"))))
        cursor.mergeCharFormat(char_format)

    for item in font_size_ranges or ():
        selected = _normalized_model_range(text, item)
        if selected is None or not _select_python_range(cursor, text, *selected):
            continue
        char_format = QTextCharFormat()
        char_format.setProperty(
            QTextFormat.Property.FontPixelSize,
            max(1, int(item.get("size", font_size))),
        )
        cursor.mergeCharFormat(char_format)

    return document.toHtml()


def apply_editor_style(
    html: str,
    start: int,
    end: int,
    *,
    font_size: int | None = None,
    color=None,
) -> str:
    document = QTextDocument()
    document.setHtml(str(html or ""))
    text = document.toPlainText()
    max_position = python_index_to_qt(text, len(text))
    start = max(0, min(max_position, int(start)))
    end = max(0, min(max_position, int(end)))
    if end < start:
        start, end = end, start
    if start >= end:
        return document.toHtml()

    cursor = QTextCursor(document)
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    char_format = QTextCharFormat()
    if font_size is not None:
        char_format.setProperty(
            QTextFormat.Property.FontPixelSize,
            max(1, int(font_size)),
        )
    if color is not None:
        char_format.setForeground(QBrush(_qcolor(color)))
    cursor.mergeCharFormat(char_format)
    return document.toHtml()


def _format_at(document: QTextDocument, text: str, index: int) -> QTextCharFormat:
    start = python_index_to_qt(text, index)
    end = python_index_to_qt(text, index + 1)
    cursor = QTextCursor(document)
    cursor.setPosition(start)
    cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
    return cursor.charFormat()


def _effective_size(char_format: QTextCharFormat, fallback: int) -> int:
    size = char_format.property(QTextFormat.Property.FontPixelSize)
    try:
        size = float(size)
    except (TypeError, ValueError):
        size = -1
    if size <= 0:
        size = char_format.font().pixelSize()
    return max(1, int(round(size))) if size > 0 else int(fallback)


def _effective_color(char_format: QTextCharFormat, fallback) -> tuple[int, int, int, int]:
    brush = char_format.foreground()
    if brush.style() == Qt.BrushStyle.NoBrush:
        return _rgba(fallback)
    return _rgba(brush.color())


def _append_range(ranges: list[dict], start: int, end: int, key: str, value) -> None:
    if ranges and ranges[-1]["end"] == start and ranges[-1][key] == value:
        ranges[-1]["end"] = end
        return
    ranges.append({"start": start, "end": end, key: value})


def parse_editor_html(
    html: str,
    *,
    base_font_size: int,
    base_text_color,
) -> EditorTextState:
    document = QTextDocument()
    document.setHtml(str(html or ""))
    text = document.toPlainText()
    base_size = max(1, int(base_font_size))
    base_color = _rgba(base_text_color)
    color_ranges: list[dict] = []
    font_size_ranges: list[dict] = []

    for index in range(len(text)):
        char_format = _format_at(document, text, index)
        size = _effective_size(char_format, base_size)
        color = _effective_color(char_format, base_color)
        if size != base_size:
            _append_range(font_size_ranges, index, index + 1, "size", size)
        if color != base_color:
            _append_range(color_ranges, index, index + 1, "color", color)

    return EditorTextState(
        text=text,
        color_ranges=color_ranges,
        font_size_ranges=font_size_ranges,
    )


def _value_for_index(ranges: Sequence[dict], index: int, key: str, fallback):
    for item in ranges:
        if int(item["start"]) <= index < int(item["end"]):
            return item[key]
    return fallback


def inspect_editor_selection(
    html: str,
    start: int,
    end: int,
    *,
    base_font_size: int,
    base_text_color,
) -> dict:
    state = parse_editor_html(
        html,
        base_font_size=base_font_size,
        base_text_color=base_text_color,
    )
    start_py = qt_index_to_python(state.text, start)
    end_py = qt_index_to_python(state.text, end)
    if end_py < start_py:
        start_py, end_py = end_py, start_py

    sizes = {
        int(_value_for_index(state.font_size_ranges, index, "size", base_font_size))
        for index in range(start_py, end_py)
    }
    colors = {
        tuple(_value_for_index(state.color_ranges, index, "color", _rgba(base_text_color)))
        for index in range(start_py, end_py)
    }
    default_size = max(1, int(base_font_size))
    default_color = _rgba(base_text_color)
    return {
        "characterCount": max(0, end_py - start_py),
        "fontSize": next(iter(sizes), default_size),
        "mixedFontSize": len(sizes) > 1,
        "color": _hex_color(next(iter(colors), default_color)),
        "mixedColor": len(colors) > 1,
    }
