import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.workers.export_worker import ManifestWriter, _replace_with_retry
from app.utils.optimized_batch_executor import (
    OptimizedBatchExecutor,
    _should_retry_with_default_runtime,
)


class ExportWorkerManifestTests(unittest.TestCase):
    def test_replace_retries_transient_windows_access_denied(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "manifest.json.tmp"
            target = Path(directory) / "manifest.json"
            source.write_text('{"ok": true}', encoding="utf-8")
            real_replace = os.replace
            attempts = 0

            def flaky_replace(src, dst):
                nonlocal attempts
                attempts += 1
                if attempts < 3:
                    error = PermissionError(13, "denied", str(dst))
                    error.winerror = 5
                    raise error
                return real_replace(src, dst)

            with patch("app.workers.export_worker.os.replace", side_effect=flaky_replace), \
                    patch("app.workers.export_worker.time.sleep"):
                _replace_with_retry(source, target, max_attempts=4, delay_seconds=0.01)

            self.assertEqual(attempts, 3)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), {"ok": True})

    def test_manifest_publication_failure_is_recorded_without_raising(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / "manifest.json")
            writer = ManifestWriter(path, {"count": 1})
            denied = PermissionError(13, "denied", path)
            denied.winerror = 5

            with patch(
                "app.workers.export_worker._replace_with_retry",
                side_effect=denied,
            ):
                writer.update(status="running")

            self.assertIn("denied", writer.last_write_error)


class ExportWorkerResumeOrderTests(unittest.TestCase):
    def test_main_loads_resume_state_before_first_manifest_update(self):
        events = []

        class FakeManifest:
            def __init__(self, path, request):
                pass

            def load_resume_state(self):
                events.append("load_resume")
                return 1

            def update(self, **kwargs):
                events.append("update")

            def finish(self, *args, **kwargs):
                events.append("finish")

        fake_document = type("FakeDocument", (), {"export_settings": {}})()

        with tempfile.TemporaryDirectory() as directory:
            request_path = Path(directory) / "request.json"
            request_path.write_text(
                json.dumps(
                    {
                        "manifest_path": str(Path(directory) / "manifest.json"),
                        "document_snapshot": "unused.cmp",
                        "directory": directory,
                        "count": 1,
                        "start_index": 1,
                    }
                ),
                encoding="utf-8",
            )
            with patch("app.workers.export_worker.ManifestWriter", FakeManifest), \
                    patch("app.workers.export_worker._load_document", return_value=fake_document):
                from app.workers.export_worker import main
                result = main([str(request_path)])

        self.assertEqual(result, 0)
        self.assertLess(events.index("load_resume"), events.index("update"))


class OptimizedExecutorReliabilityTests(unittest.TestCase):
    def test_completed_task_is_counted_when_observer_callback_raises(self):
        executor = object.__new__(OptimizedBatchExecutor)
        executor._lock = Lock()
        executor.stats = {"completed_count": 0, "callback_error_count": 0}
        executor.file_completed_callback = lambda message: (_ for _ in ()).throw(
            RuntimeError("observer failed")
        )

        executor._record_completed_task(1, SimpleNamespace(filename="image-1.jpg"))

        self.assertEqual(executor.stats["completed_count"], 1)
        self.assertEqual(executor.stats["callback_error_count"], 1)

    def test_progress_callback_failure_is_recorded_without_raising(self):
        executor = object.__new__(OptimizedBatchExecutor)
        executor._lock = Lock()
        executor.stats = {"callback_error_count": 0}
        executor.progress_callback = lambda current: (_ for _ in ()).throw(
            RuntimeError("progress failed")
        )

        executor._notify_progress(1)

        self.assertEqual(executor.stats["callback_error_count"], 1)

    def test_default_runtime_retry_is_blocked_after_any_completed_file(self):
        tuning = {"enabled": True, "derived_workers": 6, "derived_io_profile": None}

        self.assertFalse(
            _should_retry_with_default_runtime(
                success=False,
                runtime_tuning=tuning,
                completed_count=1,
                canceled=False,
            )
        )
        self.assertTrue(
            _should_retry_with_default_runtime(
                success=False,
                runtime_tuning=tuning,
                completed_count=0,
                canceled=False,
            )
        )


if __name__ == "__main__":
    unittest.main()
