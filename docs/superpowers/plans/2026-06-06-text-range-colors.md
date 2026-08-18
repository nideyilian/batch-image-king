# Text Range Colors Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-range fill colors to text layers while keeping text content as plain text.

**Architecture:** `TextLayer` owns a plain `text_color_ranges` list and exposes small range-editing methods. Rendering maps each drawn character back to the current plain text index and uses local colors only for the fill layer. `IntegratedTextPanel` writes colors from the selected text range in the existing plain `QTextEdit`.

**Tech Stack:** Python, PySide6, Pillow, standard-library `unittest`.

---

### Task 1: TextLayer Range Data API

**Files:**
- Create: `tests/test_text_layer_range_colors.py`
- Modify: `app/models/text_layer.py`

- [ ] **Step 1: Write failing tests**

Add tests for setting, replacing, clearing, serializing, deserializing, duplicating, and clipping color ranges:

```python
import unittest

from app.models.text_layer import TextLayer


class TextLayerRangeColorTests(unittest.TestCase):
    def test_set_range_overwrites_overlap_and_merges_same_color(self):
        layer = TextLayer()
        layer.current_text = "abcdef"

        layer.set_text_color_range(0, 3, (255, 0, 0, 255))
        layer.set_text_color_range(3, 5, (255, 0, 0, 255))
        layer.set_text_color_range(2, 4, (0, 0, 255, 255))

        self.assertEqual(
            layer.get_text_color_ranges(),
            [
                {"start": 0, "end": 2, "color": (255, 0, 0, 255)},
                {"start": 2, "end": 4, "color": (0, 0, 255, 255)},
                {"start": 4, "end": 5, "color": (255, 0, 0, 255)},
            ],
        )

    def test_clear_range_removes_only_selected_overlap(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_text_color_range(0, 6, (255, 0, 0, 255))

        layer.clear_text_color_range(2, 4)

        self.assertEqual(
            layer.get_text_color_ranges(),
            [
                {"start": 0, "end": 2, "color": (255, 0, 0, 255)},
                {"start": 4, "end": 6, "color": (255, 0, 0, 255)},
            ],
        )

    def test_current_text_change_clips_ranges_to_new_text_length(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_text_color_range(2, 6, (255, 0, 0, 255))

        layer.current_text = "abc"

        self.assertEqual(
            layer.get_text_color_ranges(),
            [{"start": 2, "end": 3, "color": (255, 0, 0, 255)}],
        )

    def test_serialize_deserialize_and_duplicate_preserve_ranges(self):
        layer = TextLayer()
        layer.current_text = "abcdef"
        layer.set_text_color_range(1, 4, (10, 20, 30, 255))

        restored = TextLayer.deserialize(layer.serialize())
        duplicate = layer.duplicate()

        expected = [{"start": 1, "end": 4, "color": (10, 20, 30, 255)}]
        self.assertEqual(restored.get_text_color_ranges(), expected)
        self.assertEqual(duplicate.get_text_color_ranges(), expected)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_text_layer_range_colors -v`

Expected: fail because `TextLayer` has no `set_text_color_range`.

- [ ] **Step 3: Implement the range API**

In `TextLayer.__init__`, initialize `self._text_color_ranges = []`.

Add helper methods near the existing text properties:

```python
def _normalize_color_tuple(self, color):
    if not isinstance(color, (tuple, list)) or len(color) < 3:
        return self._text_color
    r = max(0, min(255, int(color[0])))
    g = max(0, min(255, int(color[1])))
    b = max(0, min(255, int(color[2])))
    a = max(0, min(255, int(color[3]))) if len(color) > 3 else 255
    return (r, g, b, a)
```

Add public methods:

```python
def get_text_color_ranges(self):
    return [{"start": r["start"], "end": r["end"], "color": tuple(r["color"])} for r in self._text_color_ranges]

def set_text_color_range(self, start, end, color):
    color = self._normalize_color_tuple(color)
    start, end = self._clamp_text_range(start, end)
    if start >= end:
        return False
    ranges = self._subtract_color_range(self._text_color_ranges, start, end)
    ranges.append({"start": start, "end": end, "color": color})
    self._text_color_ranges = self._merge_text_color_ranges(ranges)
    self._cached_image = None
    self.changed.emit()
    return True

def clear_text_color_range(self, start, end):
    start, end = self._clamp_text_range(start, end)
    if start >= end:
        return False
    next_ranges = self._subtract_color_range(self._text_color_ranges, start, end)
    changed = next_ranges != self._text_color_ranges
    if changed:
        self._text_color_ranges = next_ranges
        self._cached_image = None
        self.changed.emit()
    return changed
```

Also add `_clamp_text_range`, `_subtract_color_range`, `_merge_text_color_ranges`, `_set_text_color_ranges`, and `_clip_text_color_ranges_to_current_text`.

Update `set_current_text`, `set_text_lines`, `text_binding_enabled`, `serialize`, `deserialize`, and `duplicate` to preserve and clip the range list.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_text_layer_range_colors -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- tests/test_text_layer_range_colors.py app/models/text_layer.py
git commit -m "feat: store text color ranges"
```

### Task 2: Render Local Colors

**Files:**
- Modify: `tests/test_text_layer_range_colors.py`
- Modify: `app/models/text_layer.py`

- [ ] **Step 1: Write failing render test**

Add:

```python
    def test_render_uses_range_color_for_selected_text_only(self):
        layer = TextLayer(width=260, height=90)
        layer.auto_fit_text_box = False
        layer.current_text = "AB"
        layer.font_size = 48
        layer.text_color = (0, 0, 0, 255)
        layer.set_text_color_range(1, 2, (255, 0, 0, 255))

        image = layer.render_text()
        pixels = [pixel for pixel in image.getdata() if pixel[3] > 64]
        red_pixels = [pixel for pixel in pixels if pixel[0] > 180 and pixel[1] < 80 and pixel[2] < 80]
        dark_pixels = [pixel for pixel in pixels if pixel[0] < 80 and pixel[1] < 80 and pixel[2] < 80]

        self.assertGreater(len(red_pixels), 10)
        self.assertGreater(len(dark_pixels), 10)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_text_layer_range_colors.TextLayerRangeColorTests.test_render_uses_range_color_for_selected_text_only -v`

Expected: fail because all rendered pixels use the global color.

- [ ] **Step 3: Implement local-color rendering**

Add helper methods to `TextLayer`:

```python
def _color_for_text_index(self, index):
    for item in self._text_color_ranges:
        if item["start"] <= index < item["end"]:
            return tuple(item["color"])
    return None

def _iter_colored_text_segments(self, line, line_start_index):
    ...
```

Update `_render_text_internal` so the main fill branch draws each segment with either local color or the existing global/gradient behavior. Preserve existing stroke rendering.

Update `_render_text_vertical_internal` so each character checks `_color_for_text_index`.

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_text_layer_range_colors -v`

Expected: all tests pass.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- tests/test_text_layer_range_colors.py app/models/text_layer.py
git commit -m "feat: render text range colors"
```

### Task 3: Wire Property Panel Selection Actions

**Files:**
- Modify: `app/ui/integrated_text_panel.py`

- [ ] **Step 1: Add selection buttons**

In `create_text_content_card`, add `range_color_btn` and `clear_range_color_btn` beside the existing text navigation actions.

- [ ] **Step 2: Connect selection handlers**

In `connect_signals`, connect:

```python
self.inline_text_edit.selectionChanged.connect(self._sync_range_color_actions)
self.range_color_btn.clicked.connect(self.on_apply_range_text_color)
self.clear_range_color_btn.clicked.connect(self.on_clear_range_text_color)
```

- [ ] **Step 3: Implement handlers**

Use the cursor selection start/end from `inline_text_edit.textCursor()`, call `set_text_color_range` or `clear_text_color_range`, emit `property_changed`, and refresh action enabled state.

- [ ] **Step 4: Syntax-check UI file**

Run: `python -m py_compile app/ui/integrated_text_panel.py`

Expected: no output and exit code 0.

- [ ] **Step 5: Commit**

Run:

```powershell
git add -- app/ui/integrated_text_panel.py
git commit -m "feat: add text range color controls"
```

### Task 4: Cache Key and Final Verification

**Files:**
- Modify: `app/utils/fast_renderer.py`

- [ ] **Step 1: Add cache key coverage**

Add `text_color_ranges` to the text layer cache key near the existing `text_color` entry.

- [ ] **Step 2: Run focused tests**

Run:

```powershell
python -m unittest tests.test_text_layer_range_colors -v
python -m py_compile app/models/text_layer.py app/ui/integrated_text_panel.py app/utils/fast_renderer.py
```

Expected: tests pass and compile commands produce no output.

- [ ] **Step 3: Commit**

Run:

```powershell
git add -- app/utils/fast_renderer.py
git commit -m "fix: invalidate cache for text range colors"
```

## Self-Review

- Spec coverage: data model, UI, rendering, serialization, duplicate, cache, tests, and compatibility are covered.
- Placeholder scan: no incomplete tasks or deferred requirements remain.
- Type consistency: the planned API uses `text_color_ranges`, `set_text_color_range`, `clear_text_color_range`, and `get_text_color_ranges` consistently.
