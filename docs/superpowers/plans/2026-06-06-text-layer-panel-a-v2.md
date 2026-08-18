# Text Layer Panel A v2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the text layer properties panel into content, font, typography, appearance, and position/size modules.

**Architecture:** Keep `IntegratedTextPanel` as the single owner of the UI. Reuse existing controls and signal handlers, adding only small layout helpers, mode buttons, visibility sync, and summary labels.

**Tech Stack:** Python, PySide6, `unittest`, existing project UI widgets.

---

## File Structure

- Modify: `app/ui/integrated_text_panel.py`
  - Rebuild the top-level section order.
  - Split core controls into font, typography, and appearance cards.
  - Replace background/gradient default block with mode-driven visibility.
  - Rename and restructure position controls as position and size.
- Create: `tests/test_integrated_text_panel_a_v2_ui.py`
  - Instantiate `IntegratedTextPanel` with Qt offscreen mode.
  - Verify approved sections and visibility helpers exist.

## Task 1: Add Failing UI Structure Test

- [ ] **Step 1: Create the test**

```python
import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from app.ui.integrated_text_panel import IntegratedTextPanel


class IntegratedTextPanelA2UiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = IntegratedTextPanel()

    def tearDown(self):
        self.panel.deleteLater()

    def test_approved_sections_exist(self):
        self.assertEqual(self.panel.content_card_title.text(), "文字内容")
        self.assertEqual(self.panel.font_card_title.text(), "字体")
        self.assertEqual(self.panel.typography_card_title.text(), "排版")
        self.assertEqual(self.panel.appearance_card_title.text(), "外观")
        self.assertEqual(self.panel.pos_group.title_label.text(), "位置和尺寸")

    def test_mode_buttons_and_visibility_helpers_exist(self):
        self.assertEqual(
            [button.text() for button in self.panel.text_fill_mode_buttons],
            ["无", "纯色", "渐变"],
        )
        self.assertEqual(
            [button.text() for button in self.panel.background_mode_buttons],
            ["无", "纯色", "渐变"],
        )
        self.assertTrue(hasattr(self.panel, "_sync_appearance_visibility"))
        self.assertTrue(hasattr(self.panel, "_sync_position_summary"))

    def test_position_controls_are_grouped_with_summary(self):
        self.assertTrue(hasattr(self.panel, "position_box"))
        self.assertTrue(hasattr(self.panel, "size_box"))
        self.panel.x_spin.setValue(50)
        self.panel.y_spin.setValue(51)
        self.panel.width_spin.setValue(106)
        self.panel.height_spin.setValue(34)
        self.panel._sync_position_summary()
        self.assertIn("X 50", self.panel.position_summary_label.text())
        self.assertIn("106 × 34", self.panel.position_summary_label.text())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run and confirm RED**

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -p "test_integrated_text_panel_a_v2_ui.py" -v
```

Expected: fail because new card title attributes and mode buttons do not exist.

## Task 2: Implement the Layout

- [ ] **Step 1: Add reusable helpers**

Add helper methods for cards, segmented buttons, control containers, and section labels. These methods only create widgets and do not touch `TextLayer`.

- [ ] **Step 2: Replace the top-level section creation order**

In `setup_ui()`, create sections in this order:

1. `create_text_content_card`
2. `create_font_card`
3. `create_typography_card`
4. `create_appearance_card`
5. `create_advanced_settings`

- [ ] **Step 3: Split old core controls**

Move existing font controls into `create_font_card()`, size/alignment/spacing/text box controls into `create_typography_card()`, and color/stroke/opacity/background/gradient controls into `create_appearance_card()`.

- [ ] **Step 4: Rework position group**

Rename `pos_group` to `位置和尺寸`, add `position_summary_label`, `position_box`, and `size_box`, then place X/Y and W/H controls into the two boxes.

- [ ] **Step 5: Wire sync helpers**

Add `_sync_appearance_visibility()` and `_sync_position_summary()`. Call them from `update_ui()`, `on_position_changed()`, `on_size_changed()`, `on_stroke_enabled_changed()`, `on_background_enabled_changed()`, and `on_gradient_enabled_changed()`.

## Task 3: Verify and Commit

- [ ] **Step 1: Run focused test**

```powershell
$env:QT_QPA_PLATFORM='offscreen'; python -m unittest discover -s tests -p "test_integrated_text_panel_a_v2_ui.py" -v
```

Expected: pass.

- [ ] **Step 2: Compile edited UI file**

```powershell
python -m py_compile app/ui/integrated_text_panel.py
```

Expected: exit code 0 with no output.

- [ ] **Step 3: Commit only this task's files**

```powershell
git add -- app/ui/integrated_text_panel.py tests/test_integrated_text_panel_a_v2_ui.py docs/superpowers/plans/2026-06-06-text-layer-panel-a-v2.md
git commit -m "feat: reorganize text layer properties panel"
```
