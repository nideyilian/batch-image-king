import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.services.ai_provider_config import AIProviderStore
from app.ui.ai_asset_studio_dialog import AIAssetStudioDialog


class AIAssetStudioDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.settings = QSettings("批图王", "AIAssetStudio")
        self.saved_settings = {key: self.settings.value(key) for key in self.settings.allKeys()}
        self.settings.clear()

    def tearDown(self):
        self.settings.clear()
        for key, value in self.saved_settings.items():
            self.settings.setValue(key, value)

    def test_dialog_saves_custom_provider_and_manual_models(self):
        dialog = AIAssetStudioDialog()
        try:
            dialog.add_profile("Custom API")
            dialog.profile_name_edit.setText("Custom API")
            dialog.base_url_edit.setText("https://api.example.test")
            dialog.generation_endpoint_edit.setText("/v2/images/create")
            dialog.models_endpoint_edit.setText("/v2/models")
            dialog.api_key_edit.setText("secret")
            dialog.auth_mode_combo.setCurrentIndex(dialog.auth_mode_combo.findData("x-api-key"))
            dialog.model_field_combo.setCurrentText("model_name")
            dialog.add_custom_model("manual-image-v1")
            dialog.save_current_profile()

            store = AIProviderStore(QSettings("批图王", "AIAssetStudio"))
            profiles = store.load_profiles()

            self.assertEqual(len(profiles), 1)
            profile = profiles[0]
            self.assertEqual(profile.name, "Custom API")
            self.assertEqual(profile.base_url, "https://api.example.test")
            self.assertEqual(profile.generation_endpoint, "/v2/images/create")
            self.assertEqual(profile.models_endpoint, "/v2/models")
            self.assertEqual(profile.auth_mode, "x-api-key")
            self.assertEqual(profile.model_field, "model_name")
            self.assertEqual(profile.models, ["manual-image-v1"])
            self.assertFalse(hasattr(dialog, "prompt_edit"))
            self.assertFalse(hasattr(dialog, "generate_button"))
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
