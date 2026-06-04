import os
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.document import Document
from app.models.binding_manager import BindingGroup
from app.utils.batch_export_precomputer import get_batch_precomputer_v2


def _touch_images(directory, prefix, extensions):
    for index, ext in enumerate(extensions, start=1):
        path = os.path.join(directory, f"{prefix}_{index:02d}{ext}")
        with open(path, "wb"):
            pass


def _folder_layer(name, directory):
    return SimpleNamespace(
        name=name,
        visible=True,
        image_source=directory,
        is_folder=True,
        _is_folder=True,
        parent_group_id=None,
        type="layer",
    )


class BatchExportCountTest(unittest.TestCase):
    def test_v2_precomputer_counts_webp_and_tiff_folder_images(self):
        with tempfile.TemporaryDirectory() as directory:
            _touch_images(directory, "asset", [".jpg", ".webp", ".tif", ".tiff"])
            layer = _folder_layer("素材层", directory)
            document = SimpleNamespace(
                layers=[layer],
                export_settings={},
                file_path="",
                binding_manager=None,
            )
            analysis = {
                "binding_enabled": False,
                "binding_categories": [],
                "layer_analysis": {
                    "visible_layers": [layer],
                    "bound_layers": [],
                    "unbound_layers": [layer],
                },
                "export_mode": "standard",
            }

            precomputer = get_batch_precomputer_v2(document, analysis)

            self.assertEqual(precomputer.analyze_document_with_context(), 4)

    def test_binding_group_category_scan_accepts_webp_and_tif_images(self):
        with tempfile.TemporaryDirectory() as directory:
            _touch_images(directory, "cat", [".jpg", ".webp", ".tif", ".tiff"])
            group = BindingGroup("group-1", "测试绑定组")

            entries = group._scan_folder_category_entries(directory)

            self.assertEqual(len(entries), 4)

    def test_traverse_count_respects_unique_use_layer_cap(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            _touch_images(first_dir, "unique", [".jpg", ".jpg", ".jpg"])
            _touch_images(second_dir, "variant", [".jpg", ".jpg"])
            unique_layer = _folder_layer("唯一素材层", first_dir)
            variant_layer = _folder_layer("搭配素材层", second_dir)
            document = SimpleNamespace(
                layers=[unique_layer, variant_layer],
                export_settings={
                    "unique_use_enabled": True,
                    "unique_use_layers": [0],
                },
            )

            self.assertEqual(Document._calculate_possible_combinations(document), 3)

    def test_unique_use_cap_still_applies_when_raw_combinations_hit_display_limit(self):
        with tempfile.TemporaryDirectory() as first_dir, tempfile.TemporaryDirectory() as second_dir:
            for index in range(1001):
                open(os.path.join(first_dir, f"variant_{index:04d}.jpg"), "wb").close()
                open(os.path.join(second_dir, f"unique_{index:04d}.jpg"), "wb").close()
            variant_layer = _folder_layer("搭配素材层", first_dir)
            unique_layer = _folder_layer("唯一素材层", second_dir)
            document = SimpleNamespace(
                layers=[variant_layer, unique_layer],
                export_settings={
                    "unique_use_enabled": True,
                    "unique_use_layers": [1],
                },
            )

            self.assertEqual(Document._calculate_possible_combinations(document), 1001)


if __name__ == "__main__":
    unittest.main()
