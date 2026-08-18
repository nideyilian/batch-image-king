# Font Family Weight Tree Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a Photoshop-style Chinese font picker that groups installed font families and lets users select the real installed weight/style used by preview and export.

**Architecture:** Preserve every scanned font face in the versioned font cache instead of collapsing a family to one path. Add an optional `font_face` field to `TextLayer`, resolve that face to its exact file during Pillow rendering, and expose grouped family/face data through `WorkspaceViewModel`. Replace the flat QML popup rows with expandable family rows and face children while keeping old `.cmp` files compatible.

**Tech Stack:** Python 3.8, PySide6/QML, Pillow, fontTools, pytest, pickle-compatible dictionaries.

---

### Task 1: Preserve font faces in the catalog cache

**Files:**
- Modify: `app/models/text_layer_font.py`
- Modify: `requirements.txt`
- Test: `tests/test_font_categorization.py`

**Steps:**

1. Add failing tests that provide multiple files for one family and assert `get_font_faces()` retains Regular, Light, Bold, and Italic entries with independent paths and normalized weight/italic metadata.
2. Run `python -m pytest tests/test_font_categorization.py -q` and confirm the new catalog API is missing.
3. Add `fonttools` as an explicit runtime dependency, bump the cache schema to version 3, save a `faces` mapping, validate cached face paths, and keep the legacy family/path APIs available.
4. Run the font categorization tests and verify old cache data causes a rescan rather than a partial face catalog.

### Task 2: Persist and render the selected face

**Files:**
- Modify: `app/models/text_layer.py`
- Modify: `app/models/text_layer_serialize.py`
- Modify: `app/models/text_layer_font.py`
- Modify: `app/utils/fast_renderer.py`
- Modify: `app/utils/fast_renderer_surface.py`
- Test: `tests/test_text_layer_core.py`
- Test: `tests/test_layer_serialize.py`

**Steps:**

1. Add failing tests for `font_face` property invalidation, serialization/deserialization/duplicate behavior, and exact face-path selection.
2. Run the targeted model tests and confirm the property and serialized field are absent.
3. Add optional `font_face` state. Old documents without the field must load with an empty face and keep legacy `font_style` rendering.
4. Resolve an explicit face before legacy bold/italic filename heuristics, add it to font/render cache keys, and ensure a missing face falls back to the family default.
5. Run the model, serializer, and renderer smoke tests.

### Task 3: Expose grouped family/face options and commands

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Test: `tests/test_qml_text_typography.py`

**Steps:**

1. Add failing tests for Chinese-only tree groups, localized face labels, exact face selection, and B/I mapping to the nearest installed weight/style.
2. Add `textFontTreeOptions`, `selectedTextFontFace`, and `setSelectedTextFontFace(family, face)` while retaining flat family options for compatibility.
3. When a real face is selected, set legacy `font_style` to NORMAL to avoid synthetic double-bold rendering.
4. Make B/I commands choose the closest installed face; use the old synthetic style only when no matching face exists.
5. Run `python -m pytest tests/test_qml_text_typography.py -q`.

### Task 4: Build the expandable QML font picker

**Files:**
- Modify: `app/qml/components/FontSelectBox.qml`
- Modify: `app/qml/Main.qml`
- Test: `tests/test_qml_native_layer_editing.py`
- Test: `tests/test_qml_workbench_smoke.py`

**Steps:**

1. Add failing source/behavior tests for family rows, expandable face rows, search across family and face names, selected-face display, and the two-argument activation signal.
2. Load the Impeccable craft floor before editing QML.
3. Implement a stable flattened row model derived from grouped options. Family rows toggle with a chevron; face rows select a leaf and preview the actual family/style.
4. Keep keyboard focus, filtering, scroll dimensions, accessibility names, and the existing compact dark-theme tokens.
5. Add `fontFace` to the new-text dialog config and wire the selected-layer picker to the new ViewModel slot.
6. Run QML unit tests and an offscreen visual probe at the minimum and common desktop sizes.

### Task 5: Verify compatibility and commit

**Files:**
- Test: `tests/test_updater.py` and full `tests/` suite as regression coverage

**Steps:**

1. Save/load a new document using a non-Regular face and verify the face survives.
2. Load legacy serialized text data without `font_face` and verify it still renders.
3. Run `python -m pytest` and report any pre-existing baseline failures separately.
4. Inspect `git diff --check`, stage only files changed for this feature, and commit with a scoped message.

**Explicit non-goals:** Variable-font continuous axes, embedding font files in `.cmp`, downloading fonts, and changing existing project file format away from pickle.
