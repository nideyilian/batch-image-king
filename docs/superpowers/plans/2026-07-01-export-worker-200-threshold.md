# Export Worker 200-Image Threshold Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route every batch of 200 or more images through the disposable export worker without changing render throughput.

**Architecture:** Keep existing environment-variable and enable/disable gates. Clamp the effective configured threshold to 200 and change the new-document default to 200.

**Tech Stack:** Python 3.11, unittest.

---

### Task 1: Threshold regression tests

**Files:**
- Create: `tests/test_export_worker_threshold.py`

- [ ] Write tests proving 199 images stay internal, 200 images use worker, legacy threshold 500 is clamped, a lower custom threshold is preserved, and disable/child environment variables remain authoritative.
- [ ] Run `python -m unittest tests.test_export_worker_threshold -v`.
- [ ] Verify RED because 200 images with a legacy 500 threshold currently stay internal.

### Task 2: Minimal implementation

**Files:**
- Modify: `app/utils/export_worker_client.py`
- Modify: `app/models/document.py`

- [ ] Change the fallback/default threshold to 200.
- [ ] Clamp valid configured thresholds with `min(configured_threshold, 200)`, while keeping a minimum of 1.
- [ ] Change the document default from 500 to 200.
- [ ] Re-run the focused tests and verify GREEN.

### Task 3: Verification and commit

- [ ] Run:

```powershell
python -m unittest tests.test_export_worker_threshold tests.test_export_worker_reliability tests.test_batch_export_counts -v
python -m py_compile app/utils/export_worker_client.py app/models/document.py tests/test_export_worker_threshold.py
git diff --check
```

- [ ] Commit only the two production files and the new test:

```powershell
git add -- app/utils/export_worker_client.py app/models/document.py tests/test_export_worker_threshold.py
git commit -m "fix: isolate exports from 200 images"
```
