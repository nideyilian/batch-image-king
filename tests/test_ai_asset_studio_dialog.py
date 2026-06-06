import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.ai_asset_studio_dialog import AIAssetStudioDialog


class FakeDocument:
    def __init__(self):
        self.canvas_width = 640
        self.canvas_height = 480
        self.added_layers = []

    def add_layer(self, *args):
        self.added_layers.append(args)
        return object()


class AIAssetStudioDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_build_request_uses_dialog_fields(self):
        dialog = AIAssetStudioDialog(FakeDocument())
        try:
            dialog.base_url_edit.setText("https://api.example.test")
            dialog.endpoint_edit.setText("/v1/images/generations")
            dialog.api_key_edit.setText("secret")
            dialog.model_edit.setText("gpt-image-1")
            dialog.model_field_combo.setCurrentText("model_name")
            dialog.prompt_edit.setPlainText("make icons")
            dialog.negative_prompt_edit.setPlainText("blur")
            dialog.count_spin.setValue(3)
            dialog.size_combo.setCurrentText("1024x1024")
            dialog.group_name_edit.setText("icon set")
            dialog.mode_combo.setCurrentIndex(dialog.mode_combo.findData("segments"))

            request = dialog.build_request()

            self.assertEqual(request.base_url, "https://api.example.test")
            self.assertEqual(request.endpoint, "/v1/images/generations")
            self.assertEqual(request.api_key, "secret")
            self.assertEqual(request.model, "gpt-image-1")
            self.assertEqual(request.model_field, "model_name")
            self.assertEqual(request.prompt, "make icons")
            self.assertEqual(request.negative_prompt, "blur")
            self.assertEqual(request.count, 3)
            self.assertEqual(request.size, "1024x1024")
            self.assertEqual(request.group_name, "icon set")
            self.assertEqual(request.process_mode, "segments")
        finally:
            dialog.deleteLater()

    def test_import_output_folder_adds_random_image_layer(self):
        document = FakeDocument()
        dialog = AIAssetStudioDialog(document)
        try:
            dialog.group_name_edit.setText("icon set")
            dialog._last_output_dir = "C:/tmp/ai-assets/segments"

            dialog.import_output_folder()

            self.assertEqual(len(document.added_layers), 1)
            args = document.added_layers[0]
            self.assertEqual(args[0], "AI素材-icon set")
            self.assertEqual(args[1:5], (0, 0, 640, 480))
            self.assertEqual(args[5], "C:/tmp/ai-assets/segments")
            self.assertFalse(args[6])
            self.assertTrue(args[7])
        finally:
            dialog.deleteLater()


if __name__ == "__main__":
    unittest.main()
