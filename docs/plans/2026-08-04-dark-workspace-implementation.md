# Dark Workspace Component System Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a native PySide6 dark-workspace component system that unifies current UI and keeps future skins data-driven.

**Architecture:** Extend the existing semantic token layer with a skin registry, add an application-level semantic widget polisher for legacy screens, and expose thin native Qt component wrappers for new and migrated UI. Keep `CursorDarkTheme`, `DialogA2`, and existing primitives as compatibility adapters.

**Tech Stack:** Python 3.8, PySide6, Qt Style Sheets, pytest/unittest.

---

### Task 1: Add skin registry tests

**Files:**
- Create: `tests/test_theme_skin_registry.py`
- Modify: `app/ui/theme/tokens.py`

**Steps:**
1. Write tests for default skin, registration, validation, switching, callbacks, and compatibility aliases.
2. Run `python -m pytest tests/test_theme_skin_registry.py -v` and verify the new API fails.
3. Implement `register_skin`, `available_skins`, `skin`, and `set_skin` with defensive copies.
4. Run the focused tests and verify they pass.

### Task 2: Add semantic widget polisher

**Files:**
- Create: `app/ui/theme/polisher.py`
- Create: `tests/test_theme_polisher.py`
- Modify: `app/ui/theme/__init__.py`
- Modify: `app/ui/dark_theme.py`

**Steps:**
1. Write tests for default, accept, reject and destructive button roles plus progress and group roles.
2. Run the focused test and verify it fails because the polisher does not exist.
3. Implement an idempotent QApplication event filter and explicit `polish_widget_tree()` helper.
4. Install it from `CursorDarkTheme.apply_to_application()`.
5. Run the focused tests.

### Task 3: Complete action and form components

**Files:**
- Create: `app/ui/components/actions.py`
- Create: `app/ui/components/forms.py`
- Create: `tests/test_ui_components_actions_forms.py`
- Modify: `app/ui/components/__init__.py`
- Modify: `app/ui/theme/provider.py`

**Steps:**
1. Write construction/property/signal tests for IconButton, ButtonGroup, Toggle, ToggleGroup, SegmentedControl, Textarea, NumberInput, ComboBox, MultiSelect, RadioGroup, Field, InputGroup and ColorSwatch.
2. Run the focused tests and verify missing imports fail.
3. Implement thin Qt wrappers with stable sizing, accessible names and semantic properties.
4. Add global QSS selectors for the new roles and invalid states.
5. Run focused tests.

### Task 4: Complete layout and overlay components

**Files:**
- Create: `app/ui/components/layout.py`
- Create: `app/ui/components/overlays.py`
- Create: `tests/test_ui_components_layout_overlays.py`
- Modify: `app/ui/components/__init__.py`
- Modify: `app/ui/theme/provider.py`

**Steps:**
1. Write tests for ScrollArea, Resizable, Sidebar, AspectRatio, Accordion, AlertDialog, Popover, menu wrappers and CommandPalette filtering.
2. Run the focused tests and verify missing imports fail.
3. Implement wrappers using QScrollArea, QSplitter, QFrame, QDialog and QMenu.
4. Add role-based QSS.
5. Run focused tests.

### Task 5: Complete feedback and domain components

**Files:**
- Create: `app/ui/components/data.py`
- Create: `tests/test_ui_components_feedback_data.py`
- Modify: `app/ui/components/feedback.py`
- Modify: `app/ui/components/__init__.py`
- Modify: `app/ui/theme/provider.py`

**Steps:**
1. Write tests for Toast, Spinner, Skeleton, EmptyState, Table and FileDropZone properties/signals.
2. Run the focused tests and verify missing APIs fail.
3. Implement deterministic native wrappers and role-based QSS.
4. Run focused tests.

### Task 6: Apply explicit semantics to core workflow surfaces

**Files:**
- Modify: `app/main_window_ui.py`
- Modify: `app/ui/new_canvas_dialog.py`
- Modify: `app/ui/batch_export_dialog_ui.py`
- Modify: `app/ui/preset_manager_dialog.py`
- Modify: `app/ui/layer_properties_layout.py`

**Steps:**
1. Add semantic variants/roles without changing signal wiring or layout behavior.
2. Replace local chrome-only styles with dynamic properties where low-risk.
3. Run related UI and dialog tests.

### Task 7: Expand component showcase and documentation

**Files:**
- Modify: `app/ui/showcase.py`
- Modify: `docs/DESIGN_SYSTEM_SHADCN.md`
- Modify: `docs/设计规范覆盖审计.md`
- Modify: `docs/design_system_preview.html`

**Steps:**
1. Add showcase sections for action, form, layout, overlay, feedback and domain components.
2. Document the skin contract, component inventory, state rules, migration rules and exclusions.
3. Update the coverage audit with measured post-change status and remaining legacy work.
4. Generate desktop and compact screenshots and inspect them for clipping or overlap.

### Task 8: Verify and back up

**Files:**
- Test all files changed in Tasks 1-7.

**Steps:**
1. Run focused component and theme tests.
2. Run `python -m pytest`.
3. Start `main.py` and verify the process remains alive.
4. Review `git diff --check` and `git status`.
5. Stage only files changed by this implementation and create a local Git commit.
