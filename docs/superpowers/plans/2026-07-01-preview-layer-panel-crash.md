# Preview and Layer Panel Crash Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate the observed native access-violation risk by serializing shared preview rendering and tying layer-panel refresh timers to the panel lifecycle.

**Architecture:** Add one reusable instance-lock decorator to the three `FastRenderer` preview entry points without touching batch rendering. Simplify `LayerPanel.set_document()` to one connection lifecycle and parent its timers to the widget.

**Tech Stack:** Python 3.11, PySide6, standard-library `unittest`, threading.

---

### Task 1: Serialize preview entry points

**Files:**
- Create: `tests/test_preview_crash_safety.py`
- Modify: `app/utils/fast_renderer.py`

- [ ] **Step 1: Write failing tests**

Create tests that import `_serialized_preview`, decorate a dummy renderer method, run it from two threads, and assert the guarded body never exceeds one concurrent call. Add a nested decorated call and assert it completes, proving the lock is reentrant. Assert `FastRenderer.render_preview`, `render_preview_incremental`, and `render_preview_live` expose `__wrapped__`, while `render_batch` does not.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m unittest tests.test_preview_crash_safety.PreviewSerializationTests -v
```

Expected: import failure because `_serialized_preview` does not exist.

- [ ] **Step 3: Implement the minimum lock**

Add a `functools.wraps` decorator:

```python
def _serialized_preview(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._preview_render_lock:
            return method(self, *args, **kwargs)
    return wrapper
```

Initialize `self._preview_render_lock = threading.RLock()` in `FastRenderer.__init__()` and decorate only the three preview methods.

- [ ] **Step 4: Verify GREEN**

Run the Task 1 test command and expect all preview serialization tests to pass.

### Task 2: Fix layer-panel timer and document lifecycle

**Files:**
- Modify: `tests/test_preview_crash_safety.py`
- Modify: `app/ui/layer_panel.py`

- [ ] **Step 1: Write failing UI tests**

Create an offscreen `QApplication`, instantiate `LayerPanel(None)`, and assert:

```python
self.assertIs(panel._update_timer.parent(), panel)
self.assertIs(panel._binding_debug_timer.parent(), panel)
```

Use a minimal `QObject` fake document with the five panel signals and an empty `layers` list. Replace `_schedule_update` with a counter, switch from an old document to a new document, and assert exactly one schedule call. Start the update timer before switching and assert it is stopped before the patched schedule point.

- [ ] **Step 2: Verify RED**

Run:

```powershell
python -m unittest tests.test_preview_crash_safety.LayerPanelLifecycleTests -v
```

Expected: timer-parent assertions fail and the schedule counter reports two calls.

- [ ] **Step 3: Implement the minimum lifecycle fix**

Construct both timers as `QTimer(self)`. At the beginning of `set_document()`, stop `_update_timer` and clear `_update_pending`. Keep the first existing disconnect/connect/update block and delete the duplicated legacy block after it.

- [ ] **Step 4: Verify GREEN**

Run the Task 2 test command and expect all lifecycle tests to pass.

### Task 3: Verify and commit

**Files:**
- Verify: `app/utils/fast_renderer.py`
- Verify: `app/ui/layer_panel.py`
- Verify: `tests/test_preview_crash_safety.py`

- [ ] Run focused regression tests:

```powershell
python -m unittest tests.test_preview_crash_safety -v
```

- [ ] Run existing related tests:

```powershell
python -m unittest tests.test_layer_properties_shape_appearance_ui tests.test_batch_export_counts tests.test_batch_export_dialog tests.test_export_worker_reliability -v
```

- [ ] Compile changed Python files:

```powershell
python -m py_compile app/utils/fast_renderer.py app/ui/layer_panel.py tests/test_preview_crash_safety.py
```

- [ ] Review and commit only the implementation:

```powershell
git diff --check
git add -- app/utils/fast_renderer.py app/ui/layer_panel.py tests/test_preview_crash_safety.py
git commit -m "fix: serialize preview and panel refresh lifecycle"
```
