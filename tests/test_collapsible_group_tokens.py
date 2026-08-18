import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.collapsible_group import CollapsibleGroupBox
from app.ui.design_tokens import Tokens


class CollapsibleGroupTokensTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_group_layout_uses_design_tokens(self):
        group = CollapsibleGroupBox("测试")
        try:
            self.assertEqual(group.title_frame.minimumHeight(), Tokens.HEADER_HEIGHT)
            self.assertEqual(group.title_frame.maximumHeight(), Tokens.HEADER_HEIGHT)
            self.assertEqual(group.title_layout.getContentsMargins(), Tokens.HEADER_MARGINS)
            self.assertEqual(group.title_layout.spacing(), Tokens.SEGMENT_GAP)
            self.assertEqual(group.toggle_button.minimumWidth(), Tokens.COLLAPSE_BUTTON_SIZE)
            self.assertEqual(group.toggle_button.maximumWidth(), Tokens.COLLAPSE_BUTTON_SIZE)
            self.assertEqual(group.container_layout.getContentsMargins(), Tokens.GROUP_CONTENT_MARGINS)
            self.assertEqual(group.container_layout.spacing(), Tokens.ROW_GAP)
        finally:
            group.deleteLater()


if __name__ == "__main__":
    unittest.main()
