import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.ui.ai_asset_studio_dialog import AIAssetStudioDialog


class AIAssetStudioDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        QSettings("批图王", "AIAssetStudio").clear()

    def test_dialog_saves_global_api_settings_without_layer_prompt_fields(self):
        dialog = AIAssetStudioDialog()
        try:
            dialog.base_url_edit.setText("https://api.example.test")
            dialog.endpoint_edit.setText("/v1/images/generations")
            dialog.api_key_edit.setText("secret")
            dialog.default_model_edit.setText("gpt-image-1")
            dialog.model_field_combo.setCurrentText("model_name")

            dialog.save_settings()
            settings = QSettings("批图王", "AIAssetStudio")

            self.assertEqual(settings.value("base_url"), "https://api.example.test")
            self.assertEqual(settings.value("endpoint"), "/v1/images/generations")
            self.assertEqual(settings.value("api_key"), "secret")
            self.assertEqual(settings.value("default_model"), "gpt-image-1")
            self.assertEqual(settings.value("model_field"), "model_name")
            self.assertFalse(hasattr(dialog, "prompt_edit"))
            self.assertFalse(hasattr(dialog, "generate_button"))
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
