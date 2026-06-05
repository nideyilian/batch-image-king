import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.integrated_text_panel import IntegratedTextPanel


class IntegratedTextPanelA2UiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = IntegratedTextPanel()

    def tearDown(self):
        self.panel.deleteLater()

    def test_approved_sections_exist(self):
        self.assertEqual(self.panel.content_card_title.text(), "文字内容")
        self.assertEqual(self.panel.font_card_title.text(), "字体")
        self.assertEqual(self.panel.typography_card_title.text(), "排版")
        self.assertEqual(self.panel.appearance_card_title.text(), "外观")
        self.assertEqual(self.panel.pos_group.title_label.text(), "位置和尺寸")

    def test_mode_buttons_and_visibility_helpers_exist(self):
        self.assertEqual(
            [button.text() for button in self.panel.text_fill_mode_buttons],
            ["无", "纯色", "渐变"],
        )
        self.assertEqual(
            [button.text() for button in self.panel.background_mode_buttons],
            ["无", "纯色", "渐变"],
        )
        self.assertTrue(hasattr(self.panel, "_sync_appearance_visibility"))
        self.assertTrue(hasattr(self.panel, "_sync_position_summary"))

    def test_position_controls_are_grouped_with_summary(self):
        self.assertTrue(hasattr(self.panel, "position_box"))
        self.assertTrue(hasattr(self.panel, "size_box"))
        self.panel.x_spin.setValue(50)
        self.panel.y_spin.setValue(51)
        self.panel.width_spin.setValue(106)
        self.panel.height_spin.setValue(34)
        self.panel._sync_position_summary()
        self.assertIn("X 50", self.panel.position_summary_label.text())
        self.assertIn("106 × 34", self.panel.position_summary_label.text())


if __name__ == "__main__":
    unittest.main()
