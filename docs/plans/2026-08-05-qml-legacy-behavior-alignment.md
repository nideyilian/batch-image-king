# QML Legacy Behavior Alignment Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Restore the complete non-AI QWidget behavior contract in the QML workbench without maintaining a second set of business rules.

**Architecture:** QML remains the production shell and high-frequency canvas surface. Object creation and mature multi-step workflows reuse the existing QWidget dialogs through `LegacyFeatureBridge`; native QML view models preserve the same document, layer, source, hit-test, transform, view-state, and tab semantics as the classic UI.

**Tech Stack:** Python 3, PySide6 Widgets/QML, Pillow, pytest, existing `Document` and controller APIs.

---

### Task 1: Restore layer lifecycle contracts

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/legacy_feature_bridge.py`
- Modify: `app/qml/Main.qml`
- Test: `tests/test_qml_legacy_behavior_contract.py`

1. Add a failing test that creates a `200x200` empty image layer at `(0, 0)` in folder mode.
2. Add a failing test that switches source mode without requiring or replacing a path.
3. Implement empty image-layer creation and independent source-mode switching.
4. Route text and shaped-layer creation through the original dialogs.
5. Run the focused contract and bridge tests.

### Task 2: Restore canvas and layer-stack contracts

**Files:**
- Modify: `app/qml/viewmodels/layer_list_model.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/Main.qml`
- Test: `tests/test_qml_legacy_behavior_contract.py`

1. Add failing tests for top-to-bottom panel order, negative coordinates, locked-layer picking, alpha-aware picking, and group bounds.
2. Use `display_entries()` for panel order while retaining document indices in all commands.
3. Remove canvas-bound clamping and restore a 10-pixel minimum transform size.
4. Restore eight handles, rotated-layer handles, and aggregate selection scaling.
5. Implement shape, alpha, clone, group, and overlap-aware hit testing.

### Task 3: Restore view and document-session contracts

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/viewmodels/workspace_session_view_model.py`
- Modify: `app/qml/Main.qml`
- Test: `tests/test_qml_legacy_behavior_contract.py`
- Test: `tests/test_qml_workspace_sessions.py`

1. Add failing tests for `0.1-10.0` actual zoom, persisted offsets, duplicate-path tabs, tab-name synchronization, classic duplicate scope, and closing the last tab.
2. Store QML view state in `zoom_factor`, `offset_x`, and `offset_y`.
3. Implement hand-tool/middle-button panning and restore `Ctrl+0` to 100 percent.
4. Restore `Ctrl+D` tab duplication and `Ctrl+L` empty-layer creation.
5. Align open, duplicate, rename, and final-close behavior with the classic tab manager.

### Task 4: Make classic workflows authoritative

**Files:**
- Modify: `app/qml/legacy_feature_bridge.py`
- Modify: `app/qml/Main.qml`
- Test: `tests/test_qml_legacy_feature_bridge.py`
- Test: `tests/test_qml_workbench_smoke.py`

1. Route new canvas, project presets, single-document batch export, multi-tab export, binding, and size matching main actions to mature workflows.
2. Open `PresetStoreDialog`, save every open tab, and preserve unsaved/replace-or-append decisions.
3. Add the export-window recovery command to tab context menus.
4. Expose every legacy alignment command from the layer menu.
5. Keep experimental QML drawers available only as explicit optional previews.

### Task 5: Regression and UI verification

**Files:**
- Modify: `docs/qml-functional-parity-audit.md`

1. Run all focused QML unit tests.
2. Run `python -m pytest`.
3. Start the QML workbench and capture desktop/mobile-equivalent window screenshots supported by this desktop UI.
4. Inspect the screenshot for clipping, overlap, blank canvas, incorrect layer order, and inaccessible controls.
5. Commit only files changed in this repair.
