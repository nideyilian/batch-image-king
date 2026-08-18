# Layer Properties Shape Appearance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the shape and appearance sections in the right-side layer properties panel to match the approved A v3 layout.

**Architecture:** Keep the existing `LayerPropertiesPanel` and `CollapsibleGroupBox` structure. Add small internal helper widgets and visibility methods in `app/ui/layer_properties.py` while preserving existing update methods and model properties.

**Tech Stack:** Python, PySide6, `unittest`, existing project UI utilities.

---

## File Structure

- Modify: `app/ui/layer_properties.py`
  - Add segmented shape buttons that call existing `update_shape_type()`.
  - Rename the appearance group title and reorganize fill/stroke controls.
  - Add helper methods for fill mode selection and control visibility.
- Create: `tests/test_layer_properties_shape_appearance_ui.py`
  - Instantiate `LayerPropertiesPanel(None)` with Qt offscreen mode.
  - Verify the approved UI structure exists and visibility helpers work.

## Task 1: Add Failing UI Structure Test

- [ ] **Step 1: Create the test file**

```python
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.layer_properties import LayerPropertiesPanel


class LayerPropertiesShapeAppearanceUiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = LayerPropertiesPanel(None)

    def tearDown(self):
        self.panel.deleteLater()

    def test_shape_segment_buttons_replace_visible_combo_entry(self):
        self.assertEqual(self.panel.shape_group.title_label.text(), "形状")
        self.assertTrue(hasattr(self.panel, "shape_type_buttons"))
        self.assertEqual(
            [button.text() for button in self.panel.shape_type_buttons],
            ["矩形", "梯形", "圆形", "五边", "六边"],
        )
        self.assertFalse(self.panel.shape_type_combo.isVisible())

    def test_appearance_group_uses_fill_mode_and_visibility_helpers(self):
        self.assertEqual(self.panel.appearance_group.title_label.text(), "外观")
        self.assertTrue(hasattr(self.panel, "fill_mode_buttons"))
        self.assertEqual(
            [button.text() for button in self.panel.fill_mode_buttons],
            ["无", "纯色", "渐变"],
        )
        self.assertTrue(hasattr(self.panel, "_sync_appearance_visibility"))

        self.panel._set_fill_mode("none", update_layer=False)
        self.assertFalse(self.panel.fill_solid_controls_widget.isVisible())
        self.assertFalse(self.panel.fill_gradient_controls_widget.isVisible())

        self.panel._set_fill_mode("solid", update_layer=False)
        self.assertTrue(self.panel.fill_solid_controls_widget.isVisible())
        self.assertFalse(self.panel.fill_gradient_controls_widget.isVisible())

        self.panel._set_fill_mode("gradient", update_layer=False)
        self.assertFalse(self.panel.fill_solid_controls_widget.isVisible())
        self.assertTrue(self.panel.fill_gradient_controls_widget.isVisible())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and confirm RED**

Run:

```powershell
python -m unittest discover -s tests -p "test_layer_properties_shape_appearance_ui.py" -v
```

Expected: fail because `shape_type_buttons`, `fill_mode_buttons`, or `_set_fill_mode()` do not exist yet.

## Task 2: Implement the Approved Layout

- [ ] **Step 1: Add internal UI helpers**

Add helper methods in `LayerPropertiesPanel`:

```python
def _make_segment_button(self, text, checked=False):
    button = QPushButton(text)
    button.setCheckable(True)
    button.setChecked(checked)
    button.setProperty("segmentButton", True)
    return button

def _make_control_group(self):
    widget = QWidget()
    layout = QVBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(6)
    return widget, layout
```

- [ ] **Step 2: Replace the visible shape combo with segmented buttons**

In `setup_ui()`, keep `self.shape_type_combo` hidden for compatibility. Add `self.shape_type_buttons` and connect each button to `update_shape_type()` with the full existing Chinese text values.

- [ ] **Step 3: Rebuild appearance group internals**

Rename the group title to `外观`. Add `self.fill_mode_buttons`, `self.fill_solid_controls_widget`, `self.fill_gradient_controls_widget`, `self.stroke_controls_widget`, and `self.stroke_advanced_group`. Move existing controls into these containers without changing their signal connections.

- [ ] **Step 4: Add fill and stroke visibility synchronization**

Add `_set_fill_mode()`, `_current_fill_mode()`, `_sync_appearance_visibility()`, and `_sync_shape_segment_buttons()` to keep segmented controls, hidden compatibility checkboxes, and visible containers in sync.

- [ ] **Step 5: Wire existing update methods to visibility sync**

After `update_fill_solid_enabled()`, `update_fill_gradient_enabled()`, `pick_fill_solid_color()`, `_pick_gradient_color()`, and `update_stroke_enabled()`, call `_sync_appearance_visibility()` so the UI reacts immediately.

## Task 3: Verify and Commit

- [ ] **Step 1: Run the focused UI test**

Run:

```powershell
python -m unittest discover -s tests -p "test_layer_properties_shape_appearance_ui.py" -v
```

Expected: pass.

- [ ] **Step 2: Compile the edited UI file**

Run:

```powershell
python -m py_compile app/ui/layer_properties.py
```

Expected: no output and exit code 0.

- [ ] **Step 3: Inspect git status**

Run:

```powershell
git status --short
```

Expected: only this task's files plus pre-existing unrelated user edits.

- [ ] **Step 4: Commit only this task's files**

Run:

```powershell
git add -- app/ui/layer_properties.py tests/test_layer_properties_shape_appearance_ui.py docs/superpowers/plans/2026-06-05-layer-properties-shape-appearance.md
git commit -m "feat: streamline layer shape appearance properties"
```
