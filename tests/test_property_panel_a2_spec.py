import unittest

from app.ui.property_panel_a2 import PropertyPanelA2


class PropertyPanelA2SpecTest(unittest.TestCase):
    def test_core_dimension_tokens_match_a_v2_spec(self):
        self.assertEqual(PropertyPanelA2.PANEL_MARGIN, 8)
        self.assertEqual(PropertyPanelA2.CARD_GAP, 6)
        self.assertEqual(PropertyPanelA2.CARD_RADIUS, 7)
        self.assertEqual(PropertyPanelA2.HEADER_HEIGHT, 36)
        self.assertEqual(PropertyPanelA2.HEADER_MARGINS, (8, 4, 7, 4))
        self.assertEqual(PropertyPanelA2.GROUP_CONTENT_MARGINS, (8, 8, 8, 9))
        self.assertEqual(PropertyPanelA2.CONTROL_HEIGHT, 30)
        self.assertEqual(PropertyPanelA2.TEXT_AREA_HEIGHT, 96)
        self.assertEqual(PropertyPanelA2.LABEL_WIDTH, 58)
        self.assertEqual(PropertyPanelA2.POSITION_LABEL_WIDTH, 22)
        self.assertEqual(PropertyPanelA2.ACTION_BUTTON_WIDTH, 56)
        self.assertEqual(PropertyPanelA2.ALIGN_BUTTON_MIN_WIDTH, 56)
        self.assertEqual(PropertyPanelA2.FEATURE_TOGGLE_HEIGHT, 48)
        self.assertEqual(PropertyPanelA2.COLLAPSE_BUTTON_SIZE, 18)
        self.assertEqual(PropertyPanelA2.SWITCH_SIZE, (52, 30))

    def test_type_scale_tokens_match_a_v2_spec(self):
        self.assertEqual(PropertyPanelA2.SECTION_TITLE_FONT_SIZE, 13)
        self.assertEqual(PropertyPanelA2.FIELD_LABEL_FONT_SIZE, 12)
        self.assertEqual(PropertyPanelA2.SUMMARY_FONT_SIZE, 11)
        self.assertEqual(PropertyPanelA2.FEATURE_TITLE_FONT_SIZE, 15)

    def test_stylesheet_exposes_reusable_roles(self):
        stylesheet = PropertyPanelA2.stylesheet("#ExamplePanel")
        for selector in (
            '#ExamplePanel',
            'QFrame[role="section"]',
            'QFrame[role="sectionHeader"]',
            'QFrame[role="sectionBody"]',
            'QFrame[role="parameterGrid"]',
            'QLabel[role="fieldLabel"]',
            'QLabel[role="featureTitle"]',
            'QPushButton[segmentButton="true"]',
            'QToolButton[segmentButton="true"]',
            'QAbstractButton[actionButton="true"]',
            'QPushButton[compactValue="true"]',
            'QCheckBox[role="inlineCheck"]',
        ):
            self.assertIn(selector, stylesheet)
        self.assertIn(f"max-height: {PropertyPanelA2.CONTROL_HEIGHT}px", stylesheet)


if __name__ == "__main__":
    unittest.main()
