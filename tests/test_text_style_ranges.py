from app.utils.text_style_ranges import remap_text_style_ranges


def test_insert_at_start_moves_existing_style():
    colors, sizes = remap_text_style_ranges(
        "ABCD", "XABCD",
        [{"start": 1, "end": 2, "color": (255, 0, 0, 255)}],
        [{"start": 1, "end": 2, "size": 60}],
    )
    assert colors == [{"start": 2, "end": 3, "color": (255, 0, 0, 255)}]
    assert sizes == [{"start": 2, "end": 3, "size": 60}]


def test_delete_before_styled_character_moves_style_left():
    colors, sizes = remap_text_style_ranges(
        "ABCD", "BCD",
        [{"start": 1, "end": 2, "color": (255, 0, 0, 255)}],
        [{"start": 1, "end": 2, "size": 60}],
    )
    assert colors == [{"start": 0, "end": 1, "color": (255, 0, 0, 255)}]
    assert sizes == [{"start": 0, "end": 1, "size": 60}]


def test_color_and_size_share_the_same_replace_mapping():
    colors, sizes = remap_text_style_ranges(
        "ABCD", "ABXD",
        [{"start": 1, "end": 2, "color": (255, 0, 0, 255)}],
        [{"start": 1, "end": 2, "size": 60}],
    )
    assert colors == [{"start": 1, "end": 3, "color": (255, 0, 0, 255)}]
    assert sizes == [{"start": 1, "end": 3, "size": 60}]


def test_multiline_insert_keeps_following_line_indices():
    colors, sizes = remap_text_style_ranges(
        "AB\nCD", "AB\nXCD",
        [{"start": 3, "end": 5, "color": (1, 2, 3, 255)}],
        [{"start": 3, "end": 5, "size": 44}],
    )
    assert colors == [{"start": 4, "end": 6, "color": (1, 2, 3, 255)}]
    assert sizes == [{"start": 4, "end": 6, "size": 44}]
