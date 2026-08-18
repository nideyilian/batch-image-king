from __future__ import annotations

import pytest
from PySide6.QtGui import QTextCursor, QTextDocument

from app.utils.text_rich_format import (
    apply_editor_style,
    build_editor_html,
    inspect_editor_selection,
    parse_editor_html,
)


pytestmark = pytest.mark.unit


def _base_html(text: str, *, color_ranges=(), font_size_ranges=()) -> str:
    return build_editor_html(
        text,
        font_family="Microsoft YaHei",
        font_size=24,
        text_color=(10, 20, 30, 255),
        font_weight=400,
        italic=False,
        letter_spacing=0,
        color_ranges=color_ranges,
        font_size_ranges=font_size_ranges,
    )


def test_editor_html_round_trip_preserves_mixed_color_and_size_ranges():
    html = _base_html(
        "甲乙\nAB",
        color_ranges=[{"start": 1, "end": 4, "color": (220, 30, 40, 255)}],
        font_size_ranges=[{"start": 2, "end": 5, "size": 48}],
    )

    state = parse_editor_html(
        html,
        base_font_size=24,
        base_text_color=(10, 20, 30, 255),
    )

    assert state.text == "甲乙\nAB"
    assert state.color_ranges == [
        {"start": 1, "end": 4, "color": (220, 30, 40, 255)}
    ]
    assert state.font_size_ranges == [{"start": 2, "end": 5, "size": 48}]


def test_editor_style_uses_qt_utf16_positions_for_emoji_selection():
    html = _base_html("A😀BC")

    # QML/QString positions: A=1 code unit, 😀=2 code units.
    html = apply_editor_style(html, 1, 3, font_size=60)
    html = apply_editor_style(html, 3, 5, color=(50, 160, 240, 255))
    state = parse_editor_html(
        html,
        base_font_size=24,
        base_text_color=(10, 20, 30, 255),
    )

    assert state.font_size_ranges == [{"start": 1, "end": 2, "size": 60}]
    assert state.color_ranges == [
        {"start": 2, "end": 4, "color": (50, 160, 240, 255)}
    ]


def test_inspect_editor_selection_reports_uniform_and_mixed_values():
    html = _base_html(
        "ABCD",
        color_ranges=[{"start": 1, "end": 3, "color": (255, 0, 0, 255)}],
        font_size_ranges=[{"start": 1, "end": 3, "size": 36}],
    )

    uniform = inspect_editor_selection(
        html,
        1,
        3,
        base_font_size=24,
        base_text_color=(10, 20, 30, 255),
    )
    mixed = inspect_editor_selection(
        html,
        0,
        4,
        base_font_size=24,
        base_text_color=(10, 20, 30, 255),
    )

    assert uniform == {
        "characterCount": 2,
        "fontSize": 36,
        "mixedFontSize": False,
        "color": "#FF0000",
        "mixedColor": False,
    }
    assert mixed["characterCount"] == 4
    assert mixed["mixedFontSize"] is True
    assert mixed["mixedColor"] is True


def test_clearing_editor_style_restores_base_values_only_inside_selection():
    html = _base_html(
        "ABCD",
        color_ranges=[{"start": 0, "end": 4, "color": (255, 0, 0, 255)}],
        font_size_ranges=[{"start": 0, "end": 4, "size": 36}],
    )

    html = apply_editor_style(
        html,
        1,
        3,
        font_size=24,
        color=(10, 20, 30, 255),
    )
    state = parse_editor_html(
        html,
        base_font_size=24,
        base_text_color=(10, 20, 30, 255),
    )

    expected_color = (255, 0, 0, 255)
    assert state.color_ranges == [
        {"start": 0, "end": 1, "color": expected_color},
        {"start": 3, "end": 4, "color": expected_color},
    ]
    assert state.font_size_ranges == [
        {"start": 0, "end": 1, "size": 36},
        {"start": 3, "end": 4, "size": 36},
    ]


def test_editor_html_preserves_alpha_and_shifts_styles_after_text_edits():
    html = build_editor_html(
        "ABCD",
        font_family="sans-serif",
        font_size=24,
        text_color=(10, 20, 30, 128),
        color_ranges=[{"start": 1, "end": 3, "color": (100, 120, 140, 96)}],
        font_size_ranges=[{"start": 1, "end": 3, "size": 40}],
    )
    document = QTextDocument()
    document.setHtml(html)
    cursor = QTextCursor(document)
    cursor.setPosition(2)
    cursor.insertText("X")

    state = parse_editor_html(
        document.toHtml(),
        base_font_size=24,
        base_text_color=(10, 20, 30, 128),
    )

    assert state.text == "ABXCD"
    assert state.color_ranges == [
        {"start": 1, "end": 4, "color": (100, 120, 140, 96)}
    ]
    assert state.font_size_ranges == [{"start": 1, "end": 4, "size": 40}]


@pytest.mark.parametrize("line_spacing", [0.5, 1.4])
def test_editor_html_carries_proportional_line_spacing_in_every_block(line_spacing):
    html = build_editor_html(
        "第一行\n第二行",
        font_family="sans-serif",
        font_size=24,
        text_color=(0, 0, 0, 255),
        line_spacing=line_spacing,
    )
    document = QTextDocument()
    document.setHtml(html)

    block = document.firstBlock()
    while block.isValid():
        assert block.blockFormat().lineHeight() == pytest.approx(line_spacing * 100.0)
        block = block.next()
