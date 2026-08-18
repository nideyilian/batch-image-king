# Export Worker Manifest Race Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent Windows manifest-file contention from aborting or repeating batch exports, preserve resume state, and report the real completed count.

**Architecture:** Keep the existing JSON polling protocol. Harden atomic manifest replacement with bounded retries, make manifest publication best-effort, read resume state before the first publication, and update executor success counters before invoking non-critical callbacks so the existing fallback gate sees durable progress.

**Tech Stack:** Python 3, standard-library `unittest`, `unittest.mock`, `pathlib`, existing worker and optimized batch executor.

---

## File Structure

- Create `tests/test_export_worker_reliability.py`: focused regression coverage for Windows replacement contention, best-effort publication, resume ordering, callback isolation, and fallback gating.
- Modify `app/workers/export_worker.py`: bounded atomic-replace retry, non-fatal manifest publication, and corrected resume initialization order.
- Modify `app/utils/optimized_batch_executor.py`: immediate completion accounting, safe observer callbacks, and an explicit fallback predicate.

### Task 1: Manifest replacement and best-effort publication

**Files:**
- Create: `tests/test_export_worker_reliability.py`
- Modify: `app/workers/export_worker.py:14-116`

- [ ] **Step 1: Write failing replacement tests**

```python
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.workers.export_worker import ManifestWriter, _replace_with_retry


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
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m unittest tests.test_export_worker_reliability.ExportWorkerManifestTests -v
```

Expected: import failure for missing `_replace_with_retry`, proving the contention behavior is not yet implemented.

- [ ] **Step 3: Implement bounded replacement retry and best-effort publication**

Add the helper near `ManifestWriter`:

```python
def _replace_with_retry(
    source: Path,
    target: Path,
    *,
    max_attempts: int = 8,
    delay_seconds: float = 0.05,
) -> None:
    attempts = max(1, int(max_attempts))
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(max(0.0, float(delay_seconds)))
```

Initialize `self.last_write_error = ""` in `ManifestWriter.__init__()`. Change `_write_locked()` to return `bool`, call `_replace_with_retry(temp, target)`, clear `last_write_error` on success, and on failure set `last_write_error`, print one warning to `stderr`, and return `False`. Keep JSON serialization errors visible through the same diagnostic path but do not raise them into image-export callbacks.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_export_worker_reliability.ExportWorkerManifestTests -v
```

Expected: 2 tests pass.

### Task 2: Preserve resume state before publishing startup status

**Files:**
- Modify: `tests/test_export_worker_reliability.py`
- Modify: `app/workers/export_worker.py:119-153`

- [ ] **Step 1: Write a failing main-order test**

Append:

```python
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

        fake_document = type(
            "FakeDocument",
            (),
            {"export_settings": {}, "_analyze_document_for_export": lambda self: {}},
        )()

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
```

- [ ] **Step 2: Run the test and verify RED**

Run:

```powershell
python -m unittest tests.test_export_worker_reliability.ExportWorkerResumeOrderTests -v
```

Expected: assertion failure because the current first event is `update`.

- [ ] **Step 3: Move resume loading before startup publication**

In `main()`, calculate `requested_count` and call `manifest.load_resume_state()` immediately after constructing `ManifestWriter`, before `manifest.update(status="loading", ...)`. Retain the existing request validation, remaining count, and adjusted start index.

- [ ] **Step 4: Run the test and verify GREEN**

Run:

```powershell
python -m unittest tests.test_export_worker_reliability.ExportWorkerResumeOrderTests -v
```

Expected: 1 test passes.

### Task 3: Isolate callbacks and expose real completion to fallback

**Files:**
- Modify: `tests/test_export_worker_reliability.py`
- Modify: `app/utils/optimized_batch_executor.py:1277-1598`
- Modify: `app/utils/optimized_batch_executor.py:3267-3287`

- [ ] **Step 1: Write failing callback and retry-gate tests**

Append:

```python
from threading import Lock
from types import SimpleNamespace

from app.utils.optimized_batch_executor import (
    OptimizedBatchExecutor,
    _should_retry_with_default_runtime,
)


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
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```powershell
python -m unittest tests.test_export_worker_reliability.OptimizedExecutorReliabilityTests -v
```

Expected: import failure for `_should_retry_with_default_runtime` or missing `_record_completed_task`.

- [ ] **Step 3: Implement safe completion publication**

Add `callback_error_count` to initial executor stats. Add:

```python
def _record_completed_task(self, completed_count: int, task) -> None:
    with self._lock:
        self.stats["completed_count"] = max(
            int(self.stats.get("completed_count", 0) or 0),
            int(completed_count),
        )
    if not self.file_completed_callback:
        return
    try:
        self.file_completed_callback(f": {task.filename}")
    except Exception as exc:
        with self._lock:
            self.stats["callback_error_count"] = (
                int(self.stats.get("callback_error_count", 0) or 0) + 1
            )
        print(f"[批处理] 进度通知失败，导出继续: {exc}")
```

Replace the inline file callback at the successful-save branch with `_record_completed_task(completed_count, task)`. Move progress-callback invocation outside the lock and wrap it in the same non-fatal pattern, incrementing `callback_error_count`. Continue setting `current_progress` even when notification fails.

- [ ] **Step 4: Implement and use the explicit fallback predicate**

Add:

```python
def _should_retry_with_default_runtime(
    *,
    success: bool,
    runtime_tuning: dict,
    completed_count: int,
    canceled: bool,
) -> bool:
    return (
        not success
        and bool(runtime_tuning.get("enabled", False))
        and (
            runtime_tuning.get("derived_workers") is not None
            or runtime_tuning.get("derived_io_profile")
        )
        and int(completed_count or 0) == 0
        and not canceled
    )
```

Use it at the current `can_retry` assignment. Since completion stats now update after every successful save, a callback or later pipeline failure cannot cause a full-plan retry after files have reached disk.

- [ ] **Step 5: Run tests and verify GREEN**

Run:

```powershell
python -m unittest tests.test_export_worker_reliability.OptimizedExecutorReliabilityTests -v
```

Expected: 2 tests pass.

### Task 4: Full verification and local backup commit

**Files:**
- Verify: `tests/test_export_worker_reliability.py`
- Verify: `app/workers/export_worker.py`
- Verify: `app/utils/optimized_batch_executor.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```powershell
python -m unittest tests.test_export_worker_reliability -v
```

Expected: all 5 reliability tests pass.

- [ ] **Step 2: Run existing batch-export tests**

Run:

```powershell
python -m unittest tests.test_batch_export_counts tests.test_batch_export_dialog -v
```

Expected: all existing tests pass.

- [ ] **Step 3: Compile changed Python files**

Run:

```powershell
python -m py_compile app/workers/export_worker.py app/utils/optimized_batch_executor.py tests/test_export_worker_reliability.py
```

Expected: exit code 0 with no output.

- [ ] **Step 4: Review the exact diff**

Run:

```powershell
git diff --check
git status --short
git diff -- app/workers/export_worker.py app/utils/optimized_batch_executor.py tests/test_export_worker_reliability.py
```

Expected: no whitespace errors and no unrelated files included.

- [ ] **Step 5: Commit only this implementation**

```powershell
git add -- app/workers/export_worker.py app/utils/optimized_batch_executor.py tests/test_export_worker_reliability.py
git commit -m "fix: prevent repeated worker batch exports"
```

Expected: one commit containing only the two production files and regression test.
