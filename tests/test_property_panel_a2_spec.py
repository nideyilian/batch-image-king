import unittest

from app.ui.property_panel_a2 import PropertyPanelA2


class PropertyPanelA2SpecTest(unittest.TestCase):
    def test_core_dimension_tokens_match_a_v2_spec(self):
        self.assertEqual(PropertyPanelA2.PANEL_MARGIN, 8)
        self.assertEqual(PropertyPanelA2.CARD_GAP, 6)
        self.assertEqual(PropertyPanelA2.CARD_RADIUS, 7)
        self.assertEqual(PropertyPanelA2.HEADER_HEIGHT, 36)
        self.assertEqual(PropertyPanelA2.CONTROL_HEIGHT, 30)
        self.assertEqual(PropertyPanelA2.TEXT_AREA_HEIGHT, 96)
        self.assertEqual(PropertyPanelA2.LABEL_WIDTH, 58)
        self.assertEqual(PropertyPanelA2.POSITION_LABEL_WIDTH, 22)
        self.assertEqual(PropertyPanelA2.SWITCH_SIZE, (52, 30))

    def test_stylesheet_exposes_reusable_roles(self):
        stylesheet = PropertyPanelA2.stylesheet("#ExamplePanel")
        for selector in (
            '#ExamplePanel',
            'QFrame[role="section"]',
            'QFrame[role="sectionHeader"]',
            'QFrame[role="sectionBody"]',
            'QLabel[role="fieldLabel"]',
            'QPushButton[segmentButton="true"]',
            'QPushButton[compactValue="true"]',
        ):
            self.assertIn(selector, stylesheet)


if __name__ == "__main__":
    unittest.main()
