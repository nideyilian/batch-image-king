import os
import sys
import unittest
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtWidgets import QApplication

from app.ui.batch_export_dialog import BatchExportDialog


class FakeDocument:
    def __init__(self):
        self.layers = [
            SimpleNamespace(name="Layer A", current_image_path="", image_source=""),
            SimpleNamespace(name="Layer B", current_image_path="", image_source=""),
        ]
        self.export_settings = {
            "batch_export_settings_saved": True,
            "use_layer_name": False,
            "use_date": True,
            "traverse_export": False,
            "smart_sampling": True,
        }

    def _calculate_possible_combinations(self):
        return 1


class BatchExportDialogTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_layer_combo_stays_enabled_when_layer_filename_is_checked(self):
        dialog = BatchExportDialog(FakeDocument())
        try:
            self.assertGreaterEqual(dialog.layer_combo.count(), 2)

            dialog.use_layer_name.setChecked(True)
            self.assertTrue(dialog.use_layer_name.isChecked())

            self.assertTrue(dialog.layer_combo.isEnabled())
            dialog.layer_combo.setCurrentIndex(1)
            self.assertEqual(dialog.layer_combo.currentData(), 1)
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
