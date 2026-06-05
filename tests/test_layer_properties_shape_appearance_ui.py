import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.layer_properties import LayerPropertiesPanel


class LayerPropertiesShapeAppearanceUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = LayerPropertiesPanel(None)

    def tearDown(self):
        self.panel.deleteLater()

    def test_shape_segment_buttons_replace_visible_combo_entry(self):
        self.assertEqual(self.panel.shape_group.title_label.text(), "形状")
        self.assertTrue(hasattr(self.panel, "shape_type_buttons"))
        self.assertEqual(
            [button.text() for button in self.panel.shape_type_buttons],
            ["矩形", "梯形", "圆形", "五边", "六边"],
        )
        self.assertTrue(self.panel.shape_type_combo.isHidden())

    def test_appearance_group_uses_fill_mode_and_visibility_helpers(self):
        self.assertEqual(self.panel.appearance_group.title_label.text(), "外观")
        self.assertTrue(hasattr(self.panel, "fill_mode_buttons"))
        self.assertEqual(
            [button.text() for button in self.panel.fill_mode_buttons],
            ["无", "纯色", "渐变"],
        )
        self.assertTrue(hasattr(self.panel, "_sync_appearance_visibility"))

        self.panel._set_fill_mode("none", update_layer=False)
        self.assertTrue(self.panel.fill_solid_controls_widget.isHidden())
        self.assertTrue(self.panel.fill_gradient_controls_widget.isHidden())

        self.panel._set_fill_mode("solid", update_layer=False)
        self.assertFalse(self.panel.fill_solid_controls_widget.isHidden())
        self.assertTrue(self.panel.fill_gradient_controls_widget.isHidden())

        self.panel._set_fill_mode("gradient", update_layer=False)
        self.assertTrue(self.panel.fill_solid_controls_widget.isHidden())
        self.assertFalse(self.panel.fill_gradient_controls_widget.isHidden())


if __name__ == "__main__":
    unittest.main()
