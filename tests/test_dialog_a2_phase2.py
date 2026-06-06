import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QFrame, QPushButton

from app.ui.add_text_layer_dialog_simple import AddTextLayerDialog
from app.ui.binding_manager_dialog import LayerBindingManagerDialog
from app.ui.dialog_a2 import DialogA2
from app.ui.layer_size_match_dialog import LayerSizeMatchDialog


class FakeLayer:
    def __init__(self, name, width=100, height=80):
        self.name = name
        self.width = width
        self.height = height
        self.image_source = ""


class FakeBindingManager:
    def __init__(self):
        self.global_enabled = True
        self.binding_groups = {}

    def get_layer_binding_info(self, _layer):
        return None

    def get_binding_groups_info(self):
        return []

    def set_global_enabled(self, enabled):
        self.global_enabled = bool(enabled)

    def is_layer_bound(self, _layer):
        return False


class FakeSizeMatchManager:
    def __init__(self):
        self.global_enabled = False
        self.relations = []

    def set_global_enabled(self, enabled):
        self.global_enabled = bool(enabled)


class FakeDocument:
    def __init__(self):
        self.layers = [FakeLayer("图层 1"), FakeLayer("图层 2", 120, 90)]
        self.binding_manager = FakeBindingManager()
        self.layer_size_match_manager = FakeSizeMatchManager()


class DialogA2Phase2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_add_text_layer_dialog_uses_a2_creation_layout(self):
        dialog = AddTextLayerDialog()

        self.assertEqual(dialog.property("dialogA2"), True)
        self.assertEqual(dialog.title_label.property("role"), "dialogTitle")
        self.assertEqual(dialog.content_card.property("role"), "dialogCard")
        self.assertEqual(dialog.core_card.property("role"), "dialogCard")
        self.assertEqual(dialog.footer_frame.property("role"), "dialogFooter")
        self.assertEqual(dialog.ok_button.property("primaryButton"), True)
        self.assertEqual(dialog.cancel_button.property("secondaryButton"), True)
        self.assertEqual(dialog.ok_button.size().width(), DialogA2.BUTTON_WIDTH)
        self.assertEqual(dialog.ok_button.size().height(), DialogA2.BUTTON_HEIGHT)

        old_rail_widgets = [
            frame for frame in dialog.findChildren(QFrame)
            if frame.property("role") == "rail"
        ]
        self.assertEqual(old_rail_widgets, [])

    def test_binding_manager_dialog_uses_a2_manager_layout(self):
        dialog = LayerBindingManagerDialog(FakeDocument())

        self.assertEqual(dialog.property("dialogA2"), True)
        self.assertEqual(dialog.title_label.text(), "图层绑定管理器")
        self.assertEqual(dialog.left_card.property("role"), "dialogCard")
        self.assertEqual(dialog.right_card.property("role"), "dialogCard")
        self.assertEqual(dialog.preview_card.property("role"), "dialogSubPanel")
        self.assertEqual(dialog.footer_frame.property("role"), "dialogFooter")
        self.assertIsInstance(dialog.refresh_btn, QPushButton)
        self.assertEqual(dialog.refresh_btn.property("secondaryButton"), True)
        self.assertEqual(dialog.close_btn.property("secondaryButton"), True)

    def test_size_match_dialog_uses_a2_manager_layout(self):
        dialog = LayerSizeMatchDialog(FakeDocument())

        self.assertEqual(dialog.property("dialogA2"), True)
        self.assertEqual(dialog.title_label.text(), "图层大小匹配管理器")
        self.assertEqual(dialog.left_card.property("role"), "dialogCard")
        self.assertEqual(dialog.right_card.property("role"), "dialogCard")
        self.assertEqual(dialog.footer_frame.property("role"), "dialogFooter")
        self.assertEqual(dialog.refresh_btn.property("secondaryButton"), True)
        self.assertEqual(dialog.close_btn.property("secondaryButton"), True)


if __name__ == "__main__":
    unittest.main()
