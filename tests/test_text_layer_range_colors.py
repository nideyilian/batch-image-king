import unittest

from app.models.text_layer import TextLayer


class TextLayerRangeColorTests(unittest.TestCase):
    def test_set_range_overwrites_overlap_and_merges_same_color(self):
        layer = TextLayer()
        layer.current_text = "abcdef"

        layer.set_text_color_range(0, 3, (255, 0, 0, 255))
        layer.set_text_color_range(3, 5, (255, 0, 0, 255))
        layer.set_text_color_range(2, 4, (0, 0, 255, 255))

        self.assertEqual(
            layer.get_text_color_ranges(),
            [
                {"start": 0, "end": 2, "color": (255, 0, 0, 255)},
                {"start": 2, "end": 4, "color": (0, 0, 255, 255)},
                {"start": 4, "end": 5, "color": (255, 0, 0, 255)},
            ],
        )

    def test_clear_range_removes_only_selected_overlap(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_text_color_range(0, 6, (255, 0, 0, 255))

        layer.clear_text_color_range(2, 4)

        self.assertEqual(
            layer.get_text_color_ranges(),
            [
                {"start": 0, "end": 2, "color": (255, 0, 0, 255)},
                {"start": 4, "end": 6, "color": (255, 0, 0, 255)},
            ],
        )

    def test_current_text_change_clips_ranges_to_new_text_length(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_text_color_range(2, 6, (255, 0, 0, 255))

        layer.current_text = "abc"

        self.assertEqual(
            layer.get_text_color_ranges(),
            [{"start": 2, "end": 3, "color": (255, 0, 0, 255)}],
        )

    def test_serialize_deserialize_and_duplicate_preserve_ranges(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_text_color_range(1, 4, (10, 20, 30, 255))

        restored = TextLayer.deserialize(layer.serialize())
        duplicate = layer.duplicate()

        expected = [{"start": 1, "end": 4, "color": (10, 20, 30, 255)}]
        self.assertEqual(restored.get_text_color_ranges(), expected)
        self.assertEqual(duplicate.get_text_color_ranges(), expected)

    def test_render_uses_range_color_for_selected_text_only(self):
        layer = TextLayer(width=260, height=90)
        layer.auto_fit_text_box = False
        layer.current_text = "AB"
        layer.font_size = 48
        layer.text_color = (0, 0, 0, 255)
        layer.set_text_color_range(1, 2, (255, 0, 0, 255))

        image = layer.render_text()
        pixels = [pixel for pixel in image.getdata() if pixel[3] > 64]
        red_pixels = [
            pixel for pixel in pixels
            if pixel[0] > 180 and pixel[1] < 80 and pixel[2] < 80
        ]
        dark_pixels = [
            pixel for pixel in pixels
            if pixel[0] < 80 and pixel[1] < 80 and pixel[2] < 80
        ]

        self.assertGreater(len(red_pixels), 10)
        self.assertGreater(len(dark_pixels), 10)


if __name__ == "__main__":
    unittest.main()
