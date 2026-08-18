from app.models.text_layer import TextLayer


def test_font_size_ranges_merge_and_clear():
    layer = TextLayer()
    layer.set_text_lines(["abcdef"])
    layer.set_current_text("abcdef", force=True)
    layer.set_font_size_range(0, 3, 40)
    layer.set_font_size_range(3, 5, 40)
    layer.set_font_size_range(2, 4, 60)
    assert layer.get_font_size_ranges() == [
        {"start": 0, "end": 2, "size": 40},
        {"start": 2, "end": 4, "size": 60},
        {"start": 4, "end": 5, "size": 40},
    ]
    assert layer.clear_font_size_range(2, 4) is True
    assert layer.get_font_size_ranges() == [
        {"start": 0, "end": 2, "size": 40},
        {"start": 4, "end": 5, "size": 40},
    ]


def test_font_size_ranges_clip_when_text_shortens():
    layer = TextLayer()
    layer.set_text_lines(["abcdef"])
    layer.set_current_text("abcdef", force=True)
    layer.set_font_size_range(2, 6, 60)
    layer.set_current_text("abc", force=True)
    assert layer.get_font_size_ranges() == [{"start": 2, "end": 3, "size": 60}]
