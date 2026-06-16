import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from app.ui.layer_properties import LayerPropertiesPanel


class FakeLayer:
    name = "Product Layer"


class LayerPropertiesAIGenerationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        settings = QSettings("批图王", "AIAssetStudio")
        settings.clear()
        settings.setValue("base_url", "https://api.example.test")
        settings.setValue("endpoint", "/v1/images/generations")
        settings.setValue("api_key", "secret")
        settings.setValue("default_model", "gpt-image-1")
        settings.setValue("model_field", "model_name")
        self.panel = LayerPropertiesPanel(None)
        self.panel.current_layer = FakeLayer()

    def tearDown(self):
        self.panel.deleteLater()

    def test_ai_generation_group_builds_layer_request_from_global_api_settings(self):
        self.assertIn("ai_generation", self.panel._module_groups)
        self.assertTrue(hasattr(self.panel, "ai_prompt_edit"))

        self.panel.ai_prompt_edit.setPlainText("make product render")
        self.panel.ai_negative_prompt_edit.setPlainText("blurry")
        self.panel.ai_model_edit.setText("")
        self.panel.ai_count_spin.setValue(2)
        self.panel.ai_size_combo.setCurrentText("1024x1024")
        self.panel.ai_mode_combo.setCurrentIndex(self.panel.ai_mode_combo.findData("segments"))

        request = self.panel.build_ai_asset_request_for_current_layer()

        self.assertEqual(request.base_url, "https://api.example.test")
        self.assertEqual(request.endpoint, "/v1/images/generations")
        self.assertEqual(request.api_key, "secret")
        self.assertEqual(request.model, "gpt-image-1")
        self.assertEqual(request.model_field, "model_name")
        self.assertEqual(request.prompt, "make product render")
        self.assertEqual(request.negative_prompt, "blurry")
        self.assertEqual(request.count, 2)
        self.assertEqual(request.group_name, "Product Layer")
        self.assertEqual(request.process_mode, "segments")


if __name__ == "__main__":
    unittest.main()
