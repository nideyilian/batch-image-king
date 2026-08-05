# QML Canvas Editing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add direct canvas selection, move, resize, zoom, naming, rotation, and alignment to the real QML document workflow.

**Architecture:** QML owns transient pointer geometry while `WorkspaceViewModel` owns hit testing and atomic model commands. A gesture commits once on release so history and preview rendering remain bounded.

**Tech Stack:** Python 3.8, PySide6, Qt Quick/QML, pytest, Pillow.

---

### Task 1: Lock direct-editing contracts with tests

**Files:**
- Modify: `tests/test_qml_document_bridge.py`

**Steps:**

1. Add a topmost-layer hit-test case and a rotated-layer hit-test case.
2. Add a blank-canvas clear-selection case.
3. Add an atomic geometry command test that restores all four fields with one undo.
4. Add locked-layer rejection, rename, rotation, and alignment assertions.
5. Run the new tests and verify they fail because the commands do not exist.

### Task 2: Implement canvas commands

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/viewmodels/layer_list_model.py`

**Steps:**

1. Expose selected rotation capability and value.
2. Implement rotation-aware geometric hit testing from top to bottom.
3. Implement selection clearing and atomic multi-attribute mutation.
4. Implement rename, rotation, geometry, and canvas alignment commands.
5. Invalidate hit/render caches and emit the minimum stable QML notifications.
6. Run `python -m pytest tests/test_qml_document_bridge.py -v` and verify the bridge tests pass.

### Task 3: Add direct manipulation to QML

**Files:**
- Modify: `app/qml/Main.qml`

**Steps:**

1. Add transient geometry and gesture mode state to the canvas workspace.
2. Add a canvas-wide pointer handler for selection, move, and four-corner resize.
3. Keep control points at a stable screen size and rotate the selection overlay with supported layers.
4. Add wheel zoom and make the percentage control restore fit zoom.
5. Bind layer name and rotation fields to the real ViewModel.
6. Connect the three alignment toolbar buttons to real commands.

### Task 4: Verify behavior and visuals

**Files:**
- Test: `tests/test_qml_document_bridge.py`
- Test: `tests/test_qml_workbench_smoke.py`
- Update: `app/qml/preview.png`

**Steps:**

1. Run QML bridge and offscreen smoke tests.
2. Run Python compile checks and `git diff --check`.
3. Generate and inspect 1280x760 and 1600x960 screenshots.
4. Run `python -m pytest -m unit` and record the known unrelated failure separately.
5. Stage only second-stage files and commit with `feat(qml): add direct canvas editing`.
