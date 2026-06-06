import os
import tempfile
import unittest

from PIL import Image, ImageDraw

from app.services.ai_asset_service import AIAssetService


class AIAssetServiceTests(unittest.TestCase):
    def test_extract_image_sources_from_common_response_shapes(self):
        response = {
            "data": [
                {"url": "https://example.test/a.png"},
                {"b64_json": "ZmFrZS1pbWFnZQ=="},
            ],
            "images": [
                {"image_url": "https://example.test/b.png"},
                "https://example.test/c.png",
            ],
        }

        sources = AIAssetService.extract_image_sources(response)

        self.assertEqual(
            [(source.kind, source.value) for source in sources],
            [
                ("url", "https://example.test/a.png"),
                ("base64", "ZmFrZS1pbWFnZQ=="),
                ("url", "https://example.test/b.png"),
                ("url", "https://example.test/c.png"),
            ],
        )

    def test_create_asset_workspace_sanitizes_group_name_and_creates_subdirs(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AIAssetService(asset_root=temp_dir)

            workspace = service.create_asset_workspace(
                "lock/key:asset",
                timestamp="20260607_010203",
            )

            self.assertTrue(workspace.endswith("lock_key_asset_20260607_010203"))
            self.assertTrue(os.path.isdir(os.path.join(workspace, "raw")))
            self.assertTrue(os.path.isdir(os.path.join(workspace, "cutout")))
            self.assertTrue(os.path.isdir(os.path.join(workspace, "segments")))

    def test_process_local_image_segments_black_background_components(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            service = AIAssetService(asset_root=temp_dir)
            workspace = service.create_asset_workspace("segments", timestamp="20260607_010203")
            source_path = os.path.join(temp_dir, "source.png")

            image = Image.new("RGBA", (120, 80), (0, 0, 0, 255))
            draw = ImageDraw.Draw(image)
            draw.rectangle((10, 10, 35, 45), fill=(255, 0, 0, 255))
            draw.rectangle((70, 20, 105, 55), fill=(0, 255, 0, 255))
            image.save(source_path)

            result = service.process_local_image(source_path, workspace, mode="segments")

            self.assertEqual(len(result.output_paths), 2)
            for path in result.output_paths:
                self.assertTrue(os.path.isfile(path))
                with Image.open(path) as segment:
                    self.assertEqual(segment.mode, "RGBA")
                    self.assertLess(segment.width, 60)
                    self.assertLess(segment.height, 60)


if __name__ == "__main__":
    unittest.main()
