import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt
from PySide6 import QtTest
from PySide6.QtWidgets import QApplication, QSizePolicy

from app.models.text_layer import TextLayer
from app.ui.integrated_text_panel import A2Switch, IntegratedTextPanel
from app.ui.property_panel_a2 import PropertyPanelA2


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
        self.assertEqual(self.panel.position_summary_label.text(), "X 50 · Y 51 · 106 × 34")

    def test_a_v2_cards_have_header_summaries(self):
        self.assertEqual(self.panel.content_summary_label.text(), "0 条 · 绑定模式开启")
        self.assertIn("24px", self.panel.font_summary_label.text())
        self.assertIn("左对齐", self.panel.typography_summary_label.text())
        self.assertIn("纯色文字", self.panel.appearance_summary_label.text())

    def test_a_v2_uses_compact_full_width_controls(self):
        self.assertTrue(all(
            button.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding
            for button in self.panel.quick_font_buttons
        ))
        for button in (
            self.panel.font_settings_btn,
            self.panel.prev_text_btn,
            self.panel.next_text_btn,
            self.panel.random_text_btn,
        ):
            self.assertTrue(button.property("actionButton"))
            self.assertEqual(button.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
            self.assertEqual(button.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
        self.assertEqual(self.panel.stroke_enable_check.text(), "")
        self.assertEqual(self.panel.stroke_title_label.text(), "启用描边")
        self.assertTrue(self.panel.background_controls.isHidden())

    def test_a_v2_dimensions_follow_property_panel_spec(self):
        self.assertEqual(self.panel.layout().getContentsMargins(), (
            PropertyPanelA2.PANEL_MARGIN,
            PropertyPanelA2.PANEL_MARGIN,
            PropertyPanelA2.PANEL_MARGIN,
            PropertyPanelA2.PANEL_MARGIN,
        ))
        self.assertEqual(self.panel.layout().spacing(), PropertyPanelA2.CARD_GAP)

        for card in (
            self.panel.content_card,
            self.panel.font_card,
            self.panel.typography_card,
            self.panel.appearance_card,
        ):
            self.assertEqual(card.header_frame.minimumHeight(), PropertyPanelA2.HEADER_HEIGHT)
            self.assertEqual(card.header_frame.maximumHeight(), PropertyPanelA2.HEADER_HEIGHT)
            self.assertEqual(card.body_layout.getContentsMargins(), PropertyPanelA2.BODY_MARGINS)
            self.assertEqual(card.body_layout.spacing(), PropertyPanelA2.SECTION_GAP)

        self.assertEqual(self.panel.inline_text_edit.minimumHeight(), PropertyPanelA2.TEXT_AREA_HEIGHT)
        self.assertEqual(self.panel.inline_text_edit.maximumHeight(), PropertyPanelA2.TEXT_AREA_HEIGHT)
        for button in self.panel.text_fill_mode_buttons + self.panel.background_mode_buttons:
            self.assertEqual(button.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
            self.assertEqual(button.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
        self.assertEqual(
            (self.panel.stroke_enable_check.minimumWidth(), self.panel.stroke_enable_check.minimumHeight()),
            PropertyPanelA2.SWITCH_SIZE,
        )

    def test_typography_module_uses_a2_grid_and_segment_geometry(self):
        self.assertEqual(self.panel.typography_size_row.spacing(), PropertyPanelA2.ROW_GAP)
        self.assertEqual(self.panel.typography_align_row.spacing(), PropertyPanelA2.ROW_GAP)
        self.assertEqual(self.panel.align_group.layout().spacing(), PropertyPanelA2.SEGMENT_GAP)

        for button in (
            self.panel.align_group.left_btn,
            self.panel.align_group.center_btn,
            self.panel.align_group.right_btn,
        ):
            self.assertTrue(button.property("segmentButton"))
            self.assertEqual(button.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
            self.assertEqual(button.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
            self.assertEqual(button.minimumWidth(), PropertyPanelA2.ALIGN_BUTTON_MIN_WIDTH)
            self.assertGreater(button.maximumWidth(), PropertyPanelA2.ALIGN_BUTTON_MIN_WIDTH)
            self.assertEqual(button.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)

        self.assertEqual(self.panel.vertical_layout_check.property("role"), "inlineCheck")
        self.assertEqual(self.panel.vertical_layout_check.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
        self.assertEqual(self.panel.vertical_layout_check.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)

        for row in (self.panel.spacing_params_row, self.panel.text_box_params_row):
            self.assertEqual(row.property("role"), "parameterGrid")
            self.assertEqual(row.layout().getContentsMargins(), (0, 0, 0, 0))
            self.assertEqual(row.layout().horizontalSpacing(), PropertyPanelA2.ROW_GAP)
            self.assertEqual(row.layout().verticalSpacing(), PropertyPanelA2.ROW_GAP)

    def test_appearance_inner_panels_and_switch_follow_a2_spec(self):
        self.assertEqual(self.panel.text_color_controls.property("role"), "subPanel")
        self.assertEqual(self.panel.stroke_toggle_panel.property("role"), "subPanel")
        self.assertEqual(self.panel.stroke_controls.property("role"), "subPanel")
        self.assertEqual(self.panel.background_advanced_row.property("role"), "subPanel")

        self.assertEqual(self.panel.stroke_toggle_panel.minimumHeight(), PropertyPanelA2.FEATURE_TOGGLE_HEIGHT)
        self.assertEqual(self.panel.stroke_title_label.property("role"), "featureTitle")
        self.assertIsInstance(self.panel.stroke_enable_check, A2Switch)
        self.assertEqual(self.panel.stroke_enable_check.property("role"), "switch")
        self.assertEqual(
            (self.panel.stroke_enable_check.minimumWidth(), self.panel.stroke_enable_check.minimumHeight()),
            PropertyPanelA2.SWITCH_SIZE,
        )

        for swatch in (self.panel.text_color, self.panel.stroke_color, self.panel.bg_color):
            self.assertEqual(swatch.minimumWidth(), PropertyPanelA2.COLOR_SWATCH_SIZE)
            self.assertEqual(swatch.maximumWidth(), PropertyPanelA2.COLOR_SWATCH_SIZE)
            self.assertEqual(swatch.minimumHeight(), PropertyPanelA2.COLOR_SWATCH_SIZE)
            self.assertEqual(swatch.maximumHeight(), PropertyPanelA2.COLOR_SWATCH_SIZE)

    def test_stroke_switch_click_area_enables_stroke(self):
        layer = TextLayer()
        self.panel.set_text_layer(layer)
        switch = self.panel.stroke_enable_check
        center = QPoint(switch.width() // 2, switch.height() // 2)

        self.assertTrue(switch.hitButton(center))
        QtTest.QTest.mouseClick(switch, Qt.LeftButton, pos=center)
        QApplication.processEvents()

        self.assertTrue(switch.isChecked())
        self.assertTrue(layer.stroke_enabled)
        self.assertTrue(self.panel.stroke_width_spin.isEnabled())
        self.assertTrue(self.panel.stroke_color_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
