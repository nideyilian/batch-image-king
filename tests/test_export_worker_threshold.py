import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.export_worker_client import should_use_export_worker


def _document(settings=None, visible_layers=1):
    return SimpleNamespace(
        export_settings={
            "export_external_worker_enabled": True,
            **(settings or {}),
        },
        layers=[SimpleNamespace(visible=True) for _ in range(visible_layers)],
    )


class ExportWorkerThresholdTests(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(
            os.environ,
            {
                "BTPW_EXPORT_WORKER_CHILD": "0",
                "BTPW_DISABLE_EXPORT_WORKER": "0",
                "BTPW_FORCE_EXPORT_WORKER": "0",
            },
        )
        self.environment.start()

    def tearDown(self):
        self.environment.stop()

    def test_199_images_stay_in_main_process(self):
        self.assertFalse(should_use_export_worker(_document(), 199))

    def test_200_images_use_worker(self):
        self.assertTrue(should_use_export_worker(_document(), 200))

    def test_legacy_500_threshold_is_clamped_to_200(self):
        document = _document({"export_worker_min_count": 500})

        self.assertTrue(should_use_export_worker(document, 200))

    def test_lower_custom_threshold_is_preserved(self):
        document = _document({"export_worker_min_count": 100})

        self.assertTrue(should_use_export_worker(document, 100))

    def test_explicit_disable_remains_authoritative(self):
        document = _document({"export_external_worker_enabled": False})

        self.assertFalse(should_use_export_worker(document, 2000))

    def test_worker_child_never_starts_nested_worker(self):
        os.environ["BTPW_EXPORT_WORKER_CHILD"] = "1"
        os.environ["BTPW_FORCE_EXPORT_WORKER"] = "1"

        self.assertFalse(should_use_export_worker(_document(), 2000))


if __name__ == "__main__":
    unittest.main()
