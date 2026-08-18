import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QGroupBox

from app.ui.shaped_layer_panel import ShapedLayerPanel


class ShapedLayerPanelQuickRotationUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_quick_rotation_module_is_not_created(self):
        panel = ShapedLayerPanel()
        try:
            self.assertFalse(hasattr(panel, "rotate_0_btn"))
            self.assertFalse(hasattr(panel, "rotate_90_btn"))
            self.assertFalse(hasattr(panel, "rotate_180_btn"))
            self.assertFalse(hasattr(panel, "rotate_270_btn"))
            self.assertFalse(hasattr(panel, "current_rotation_label"))
            self.assertNotIn(
                "快速旋转",
                [group.title() for group in panel.findChildren(QGroupBox)],
            )
        finally:
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
