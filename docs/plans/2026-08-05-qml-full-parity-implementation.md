# QML Full Parity Implementation Plan

**Goal:** Make the QML workbench the default production UI with complete access to existing non-AI functionality.

**Architecture:** Keep common editing native QML and route mature advanced QWidget workflows through a document-aware compatibility bridge. Extend the QML session and workspace view models only for behavior that must be native to the shell, such as close safety, tab commands, clipboard commands, and per-document view state.

**Tech Stack:** Python 3, PySide6 Widgets/QML, pytest, PyInstaller, existing Document and export services.

---

### Task 1: Legacy feature bridge

**Files:**
- Create: `app/qml/legacy_feature_bridge.py`
- Create: `tests/test_qml_legacy_feature_bridge.py`
- Modify: `app/qml/qml_main.py`

1. Write bridge contract tests for active-document resolution, dialog reuse, AI hiding, clipboard, and legacy document-manager adaptation.
2. Implement tracked non-modal advanced properties, batch export, multi-tab export, preset manager, canvas preset, binding, size matching, and canvas resize commands.
3. Register the bridge as `legacyTools` and run the new tests.

### Task 2: Session parity and safe shutdown

**Files:**
- Modify: `app/qml/viewmodels/workspace_session_view_model.py`
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workspace_sessions.py`

1. Add failing tests for duplicate, rename, close-other, reorder, and sequential application close.
2. Implement session commands and application-close state.
3. Intercept QML window closing and reuse the existing save/discard/cancel dialog.
4. Run session and QML smoke tests.

### Task 3: Menus, shortcuts, and view parity

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

1. Add per-document zoom and complete blend-mode contracts; expose select-all through the compatibility bridge.
2. Replace placeholder top menus with real file, edit, layer, canvas, view, preset, and tools menus.
3. Restore standard shortcuts and connect advanced commands to `legacyTools`.
4. Expand blend modes to the full legacy list and wire the advanced properties entry.

### Task 4: Production entry and packaging

**Files:**
- Modify: `main.py`
- Modify: `build.py`
- Modify: `批图王.spec`
- Modify: `tests/test_qml_workbench_smoke.py`

1. Add tests asserting QML data and default entry dispatch.
2. Dispatch to QML by default and retain `--classic`.
3. Package QML files/assets and required Qt Quick modules.
4. Verify offscreen QML startup.

### Task 5: Regression and visual verification

**Files:**
- Modify: `app/qml/README.md`
- Modify: `docs/qml-functional-parity-audit.md`

1. Run QML tests and targeted legacy dialog tests.
2. Run the complete pytest suite and classify unrelated environment failures.
3. Capture and inspect 1280x760 and 1600x960 screenshots.
4. Update documentation with the compatibility architecture and `--classic` fallback.
5. Commit only files changed for this implementation.
