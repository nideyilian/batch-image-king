import unittest

import numpy as np

from app.models.text_layer import TextLayer


class TextLayerFontSizeRangeTests(unittest.TestCase):
    def test_set_range_overwrites_overlap_and_merges_same_size(self):
        layer = TextLayer()
        layer.current_text = "abcdef"

        layer.set_font_size_range(0, 3, 40)
        layer.set_font_size_range(3, 5, 40)
        layer.set_font_size_range(2, 4, 60)

        self.assertEqual(
            layer.get_font_size_ranges(),
            [
                {"start": 0, "end": 2, "size": 40},
                {"start": 2, "end": 4, "size": 60},
                {"start": 4, "end": 5, "size": 40},
            ],
        )

    def test_clear_range_removes_only_selected_overlap(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_font_size_range(0, 6, 40)

        layer.clear_font_size_range(2, 4)

        self.assertEqual(
            layer.get_font_size_ranges(),
            [
                {"start": 0, "end": 2, "size": 40},
                {"start": 4, "end": 6, "size": 40},
            ],
        )

    def test_current_text_change_clips_ranges_to_new_text_length(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_font_size_range(2, 6, 60)

        layer.current_text = "abc"

        self.assertEqual(
            layer.get_font_size_ranges(),
            [{"start": 2, "end": 3, "size": 60}],
        )

    def test_serialize_deserialize_and_duplicate_preserve_ranges(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_font_size_range(1, 4, 60)

        restored = TextLayer.deserialize(layer.serialize())
        duplicate = layer.duplicate()

        expected = [{"start": 1, "end": 4, "size": 60}]
        self.assertEqual(restored.get_font_size_ranges(), expected)
        self.assertEqual(duplicate.get_font_size_ranges(), expected)

    def test_font_size_for_text_index_returns_range_size(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_font_size_range(1, 4, 60)

        self.assertIsNone(layer._font_size_for_text_index(0))
        self.assertEqual(layer._font_size_for_text_index(1), 60)
        self.assertEqual(layer._font_size_for_text_index(3), 60)
        self.assertIsNone(layer._font_size_for_text_index(4))

    def test_render_uses_range_font_size_for_selected_char(self):
        layer = TextLayer(width=320, height=110)
        layer.auto_fit_text_box = False
        layer.supersample_enabled = False
        layer.current_text = "AB"
        layer.font_size = 30
        layer.text_color = (0, 0, 0, 255)

        base = np.asarray(layer.render_text())

        layer.set_font_size_range(1, 2, 60)
        ranged = np.asarray(layer.render_text())

        def glyph_height(image, start_x, end_x):
            mask = image[:, start_x:end_x, 3] > 64
            rows = np.any(mask, axis=1)
            if not rows.any():
                return 0
            idx = np.where(rows)[0]
            return idx[-1] - idx[0] + 1

        cols = np.any(ranged[:, :, 3] > 64, axis=0)
        xs = np.where(cols)[0]
        mid = (xs.min() + xs.max()) // 2
        h_a = glyph_height(ranged, xs.min(), mid)
        h_b = glyph_height(ranged, mid, xs.max() + 1)

        self.assertGreater(h_b, h_a, "局部放大字号的字符应明显更高")


if __name__ == "__main__":
    unittest.main()
