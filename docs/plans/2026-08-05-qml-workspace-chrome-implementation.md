# QML Workspace Chrome Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a complete top alignment tool group, launch into a real no-document state, and pin adaptive rulers to the canvas viewport edges.

**Architecture:** Session ownership determines whether a document is open, while the workspace keeps a dormant internal `Document` for compatibility. QML gates document-specific chrome with `workspaceSessions.count`, and viewport rulers derive their origin from the transformed artboard position without changing document coordinates.

**Tech Stack:** Python 3, PySide6 QAbstractListModel, Qt Quick/QML Canvas, pytest.

---

### Task 1: Add failing workspace chrome contracts

**Files:**
- Create: `tests/test_qml_workspace_chrome.py`
- Modify: `tests/test_qml_workspace_sessions.py`

1. Test session construction with `include_initial_document=False`.
2. Test that creating a document from zero sessions activates index zero.
3. Assert all eight top alignment/distribution modes are present.
4. Assert the no-document empty state and viewport ruler structure exist.
5. Run focused tests and confirm failure.

### Task 2: Support zero-document startup

**Files:**
- Modify: `app/qml/viewmodels/workspace_session_view_model.py`
- Modify: `app/qml/qml_main.py`
- Modify: `app/qml/Main.qml`

1. Add the backward-compatible optional initial-session parameter.
2. Skip default `workspace.newDocument()` during an ordinary production launch.
3. Keep explicit blank/demo/screenshot workflows deterministic.
4. Gate canvas content and document-specific commands with `hasOpenDocument`.
5. Add the central new/open empty state.

### Task 3: Add the complete alignment tool group

**Files:**
- Modify: `app/qml/Main.qml`

1. Add reusable compact alignment button and glyph components.
2. Replace the three existing commands with six alignment commands.
3. Add horizontal and vertical distribution commands.
4. Preserve single-layer canvas alignment and multi-layer selection alignment.
5. Verify disabled states for no selection, locked layers, and fewer than three layers.

### Task 4: Move rulers to the viewport edges

**Files:**
- Modify: `app/qml/Main.qml`

1. Remove rulers from `artboardFrame`.
2. Add fixed top ruler, left ruler, and origin corner under `canvasWorkspace`.
3. Paint adaptive 1/2/5-step ticks from the artboard origin.
4. Convert ruler clicks from viewport coordinates to document guide coordinates.
5. Verify pan, zoom, hide/show, and no-document behavior.

### Task 5: Verify, commit, and restart

**Files:**
- Verify: `app/qml/Main.qml`
- Verify: `app/qml/qml_main.py`
- Verify: `app/qml/viewmodels/workspace_session_view_model.py`

1. Run focused and all QML tests.
2. Compile changed Python files.
3. Capture no-document and ruler/alignment screenshots at two window sizes.
4. Run the layout detector once and run the full pytest suite.
5. Stage only this task's files and create the required local commit.
6. Restart the visible QML frontend and confirm its window handle.
