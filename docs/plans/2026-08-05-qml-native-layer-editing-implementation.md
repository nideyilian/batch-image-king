# QML Native Layer Editing Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Preserve current values in every QML parameter editor and replace legacy layer creation/rename windows with native dark QML interactions.

**Architecture:** Shared QML editor components own a focus-time edit buffer while the Python view model remains the only layer-construction boundary. Native QML dialogs pass validated configuration maps into `WorkspaceViewModel`, which creates existing model classes and publishes the standard history, selection, and preview updates.

**Tech Stack:** Python 3, PySide6 Qt Quick/QML, existing `Document`, `TextLayer`, `ShapedLayer`, pytest.

---

### Task 1: Lock the interaction contract with tests

**Files:**
- Create: `tests/test_qml_native_layer_editing.py`
- Modify: `tests/test_qml_workbench_smoke.py`
- Modify: `tests/test_qml_legacy_feature_bridge.py`

1. Assert all shared focus-sensitive editors use `Binding.RestoreNone` and preserve their current value on focus.
2. Assert `Main.qml` contains native text/shape dialogs and inline F2 rename routing.
3. Assert the three legacy layer UI calls are absent.
4. Add ViewModel tests for configured text and shaped-layer creation.
5. Run the focused tests and confirm they fail before implementation.

### Task 2: Harden shared parameter editors

**Files:**
- Modify: `app/qml/components/ValueBox.qml`
- Modify: `app/qml/components/FontSelectBox.qml`
- Modify: `app/qml/Main.qml`

1. Add `beginEdit()` to single-line components.
2. Synchronize the current model value before selecting text on focus.
3. Change conditional bindings to `Binding.RestoreNone`.
4. Preserve current text in `ContentTextEditor` while entering edit mode.
5. Run the component contract tests.

### Task 3: Add configured layer creation commands

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Test: `tests/test_qml_native_layer_editing.py`

1. Add a `QVariantMap` command for the classic text-layer creation fields.
2. Add a `QVariantMap` command for shaped layers with optional empty, file, or folder sources.
3. Validate inputs and apply shape-specific parameters.
4. Reuse the normal document history, selection, cache, and preview notification flow.
5. Run the ViewModel unit tests.

### Task 4: Replace legacy layer windows with native QML

**Files:**
- Modify: `app/qml/Main.qml`
- Modify: `app/qml/legacy_feature_bridge.py`
- Modify: `tests/test_qml_workbench_smoke.py`
- Modify: `tests/test_qml_legacy_feature_bridge.py`

1. Add dark QML text and shaped-layer creation dialogs using existing theme tokens and controls.
2. Route shortcuts, menus, toolbar buttons, and tool rail buttons to these dialogs.
3. Route F2 and the layer menu rename command to the right inspector name editor.
4. Remove the obsolete bridge methods for text creation, shaped creation, and layer rename.
5. Run all QML tests.

### Task 5: Verify and preserve a rollback point

**Files:**
- Verify: `app/qml/Main.qml`
- Verify: `app/qml/components/ValueBox.qml`
- Verify: `app/qml/components/FontSelectBox.qml`

1. Compile changed Python files.
2. Run the full pytest suite and record any pre-existing failures separately.
3. Run the Impeccable detector once over changed QML targets.
4. Capture and inspect 1280x760 and 1600x960 screenshots.
5. Stage only this task's files and create a local git commit.
6. Restart the QML frontend and report its process and launch command.
