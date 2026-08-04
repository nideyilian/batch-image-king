# QML Real Document Bridge Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Promote the approved QML prototype into `app/qml` and connect it to real `Document`, layer, preview, persistence, history, and single-export workflows.

**Architecture:** QML binds only to a `WorkspaceViewModel` and a `QAbstractListModel`. The ViewModel delegates persistence and rendering to the existing `Document` and preview/render services, while an image provider exposes copied QImages to Qt Quick.

**Tech Stack:** Python 3.8, PySide6 6.6+, Qt Quick/QML, Pillow, pytest.

---

### Task 1: Lock bridge contracts with tests

**Files:**
- Create: `tests/test_qml_document_bridge.py`

**Steps:**

1. Write tests for layer roles and model reset against image and text layers.
2. Write tests for selection and base property mutation through the ViewModel.
3. Write tests for undo/redo after a property command.
4. Write a save/load round-trip test using a temporary `.cmp`.
5. Run `python -m pytest tests/test_qml_document_bridge.py -v` and confirm imports fail before implementation.

### Task 2: Implement image provider and layer list model

**Files:**
- Create: `app/qml/__init__.py`
- Create: `app/qml/preview_image_provider.py`
- Create: `app/qml/viewmodels/__init__.py`
- Create: `app/qml/viewmodels/layer_list_model.py`

**Steps:**

1. Implement a thread-safe `QQuickImageProvider` that returns a copied current image or a neutral placeholder.
2. Implement stable role IDs and role names for QML.
3. Reset the list model when the document changes and emit row changes after property commands.
4. Run the bridge tests and confirm model tests pass.

### Task 3: Implement workspace commands

**Files:**
- Create: `app/qml/viewmodels/workspace_view_model.py`

**Steps:**

1. Implement document and selection properties with Qt notify signals.
2. Implement new/open/save/save-as/export slots using existing `Document` methods.
3. Implement selection, visibility, lock, transform, opacity, undo, and redo commands.
4. Convert PIL RGBA output into an owned QImage and publish a revisioned preview URL.
5. Run `python -m pytest tests/test_qml_document_bridge.py -v` and confirm all bridge tests pass.

### Task 4: Promote the prototype to the application namespace

**Files:**
- Move: `prototypes/qml_workbench/*` to `app/qml/`
- Rename: `app/qml/main.py` to `app/qml/qml_main.py`
- Modify: `tests/test_qml_workbench_prototype.py`

**Steps:**

1. Move the approved visual files without changing `main.py`.
2. Register `WorkspaceViewModel`, `LayerListModel`, and `PreviewImageProvider` before loading QML.
3. Keep screenshot arguments for deterministic visual tests.
4. Update README commands and screenshot test paths.

### Task 5: Bind QML to real state

**Files:**
- Modify: `app/qml/Main.qml`

**Steps:**

1. Replace the static `ListModel` with `layerModel` context data.
2. Bind titles, selection, basic fields, visibility, lock, history actions, and document commands to `workspace`.
3. Replace the static poster composition with `workspace.previewSource` and a geometry selection overlay.
4. Preserve the approved layout, tokens, tooltips, and responsive constraints.
5. Add a compact empty/loading/error state without adding nested cards.

### Task 6: Verify and commit

**Files:**
- Test: `tests/test_qml_document_bridge.py`
- Test: `tests/test_qml_workbench_prototype.py`

**Steps:**

1. Run both QML tests and Python compile checks.
2. Generate 1600×960 and 1280×760 screenshots and inspect them for nonblank canvas, overflow, and overlap.
3. Run `python -m pytest -m unit` and record unrelated baseline failures separately.
4. Run `git diff --check` and review the exact staged file list.
5. Commit only this task's files with `feat(qml): connect real document workflow`.
