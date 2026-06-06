# Dialog A2 Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish a reusable Dialog A2 design layer and apply it to the high-frequency color and font selection dialogs.

**Architecture:** Add a focused `DialogA2` token/style helper, build a custom `ColorPickerDialogA2`, and wrap the existing `EnhancedFontSelector` in a consistent Dialog A2 shell. Keep the first phase limited to shared dialog infrastructure plus text-layer color/font entry points.

**Tech Stack:** Python, PySide6, unittest, existing app UI modules.

---

### Task 1: Dialog A2 Tokens And Spec

**Files:**
- Create: `app/ui/dialog_a2.py`
- Create: `docs/ui/dialog-a2-spec.md`
- Test: `tests/test_dialog_a2.py`

- [ ] **Step 1: Write failing token/style tests**

Add tests that import `DialogA2`, assert fixed margins/control sizes, and check stylesheet roles such as `QDialog[dialogA2="true"]`, `QFrame[role="dialogCard"]`, `QLabel[role="dialogTitle"]`, and `QPushButton[primaryButton="true"]`.

- [ ] **Step 2: Run red test**

Run: `python -m unittest discover -s tests -p "test_dialog_a2.py" -v`

Expected: FAIL because `app.ui.dialog_a2` does not exist.

- [ ] **Step 3: Implement `DialogA2`**

Create `DialogA2` with dialog margins, content spacing, control sizes, color tokens, and `stylesheet()` / `apply()` helpers.

- [ ] **Step 4: Run green test**

Run: `python -m unittest discover -s tests -p "test_dialog_a2.py" -v`

Expected: PASS.

### Task 2: Color Picker Dialog A2

**Files:**
- Create: `app/ui/color_picker_dialog_a2.py`
- Modify: `app/ui/integrated_text_panel.py`
- Modify: `app/ui/add_text_layer_dialog_simple.py`
- Test: `tests/test_dialog_a2.py`

- [ ] **Step 1: Write failing color dialog tests**

Add tests that instantiate `ColorPickerDialogA2`, verify Chinese labels, initial RGB/alpha synchronization, swatch click updates color, and accepted color remains valid.

- [ ] **Step 2: Run red test**

Run: `python -m unittest discover -s tests -p "test_dialog_a2.py" -v`

Expected: FAIL because `ColorPickerDialogA2` does not exist.

- [ ] **Step 3: Implement custom color picker**

Build a compact dark dialog with preset swatches, selected/current preview, RGB/alpha spin boxes, hex field, and OK/Cancel buttons using `DialogA2`.

- [ ] **Step 4: Replace high-frequency color entry points**

Use `get_color_a2()` in text layer color indicators and the add-text-layer dialog instead of `QColorDialog.getColor()`.

- [ ] **Step 5: Run green tests**

Run: `python -m unittest discover -s tests -p "test_dialog_a2.py" -v`

Expected: PASS.

### Task 3: Font Picker Dialog A2 Shell

**Files:**
- Create: `app/ui/font_picker_dialog_a2.py`
- Modify: `app/ui/integrated_text_panel.py`
- Test: `tests/test_dialog_a2.py`

- [ ] **Step 1: Write failing font dialog tests**

Add tests that instantiate `FontPickerDialogA2`, verify it contains `EnhancedFontSelector`, uses Dialog A2 margins, and exposes `selected_font()`.

- [ ] **Step 2: Run red test**

Run: `python -m unittest discover -s tests -p "test_dialog_a2.py" -v`

Expected: FAIL because `FontPickerDialogA2` does not exist.

- [ ] **Step 3: Implement font dialog shell**

Wrap `EnhancedFontSelector` in a Dialog A2 container and keep existing font search/preview/favorite behavior unchanged.

- [ ] **Step 4: Replace text panel font entry**

Update `IntegratedTextPanel.on_open_font_selector()` to use `FontPickerDialogA2`.

- [ ] **Step 5: Run verification**

Run the dialog tests, text panel UI tests, `py_compile`, and `git diff --check`.

Expected: all pass.
