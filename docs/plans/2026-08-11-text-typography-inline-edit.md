# Text Typography And Inline Edit Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将新文字图层默认字体设为 `sans-serif`，显式提供真实字重选择，并恢复画布双击文字直接编辑。

**Architecture:** `TextLayerFontMixin` 负责把通用 `sans-serif` 别名解析为各平台系统无衬线字体，文档仍保存通用家族名。`WorkspaceViewModel` 从现有字体 face 目录发布当前可选字重并选择最接近的真实 face；QML 属性面板只增加一个紧凑下拉框。旧版画布编辑覆盖层按现有提交、撤销和锁定规则恢复。

**Tech Stack:** Python 3.12、PySide6、Qt Quick/QML、Pillow、pytest。

---

### Task 1: 默认无衬线字体

**Files:**
- Modify: `app/models/text_layer_font.py`
- Modify: `app/qml/Main.qml`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Test: `tests/test_text_layer_core.py`
- Test: `tests/test_qml_text_typography.py`

**Step 1: Write the failing test**

断言 `TextLayer().font_family == "sans-serif"`，并断言新建文字弹窗与 `addConfiguredTextLayer()` 的缺省值均为 `sans-serif`。

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_text_layer_core.py tests/test_qml_text_typography.py -q`

Expected: FAIL，当前默认值为 `Microsoft YaHei`。

**Step 3: Write minimal implementation**

让 `_get_default_font()` 返回 `sans-serif`，新增平台别名解析，并让 `_find_font_path()` 使用解析后的真实家族查找字体文件；同步 QML 新建弹窗与 ViewModel 配置缺省值。

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_text_layer_core.py tests/test_qml_text_typography.py -q`

Expected: PASS。

### Task 2: 真实字重选择

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/Main.qml`
- Test: `tests/test_qml_text_typography.py`
- Test: `tests/test_qml_workbench_smoke.py`

**Step 1: Write the failing test**

为确定性字体目录提供 300、400、700 face，断言 `selectedTextFontWeightOptions` 发布这些字重，`setSelectedTextFontWeight(650)` 选择 700 face，并验证 QML 存在字重控件。

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_qml_text_typography.py -q`

Expected: FAIL，属性和槽尚不存在。

**Step 3: Write minimal implementation**

新增 `selectedTextFontWeight`、`selectedTextFontWeightOptions` 与 `setSelectedTextFontWeight()`；只选择当前字体与斜体状态下最接近的真实 face，没有 face 时回退到 400/700 合成样式。QML 使用现有 `SelectBox`。

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_qml_text_typography.py tests/test_qml_workbench_smoke.py -q`

Expected: PASS。

### Task 3: 恢复画布双击直接编辑

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/Main.qml`
- Test: `tests/test_qml_canvas_double_click_edit.py`

**Step 1: Write the failing test**

恢复对 `startTextEditOverlay()`、`commitTextEditOverlay()`、`cancelTextEditOverlay()`、`canvasTextEditOverlay` 和焦点转移的契约断言，并验证锁定图层拒绝进入编辑。

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_qml_canvas_double_click_edit.py -q`

Expected: FAIL，工作区当前删改移除了旧覆盖层。

**Step 3: Write minimal implementation**

从已提交旧版恢复 ViewModel 编辑状态与 QML 覆盖层；双击命中后选中图层、展开文字内容区并聚焦覆盖层。覆盖层同步字体家族、字号、字重和斜体。

**Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_qml_canvas_double_click_edit.py -q`

Expected: PASS。

### Task 4: 集成验证与提交

**Files:**
- Verify: `app/qml/Main.qml`
- Verify: `tests/`

**Step 1:** 运行相关单元测试和 QML 离屏截图。

**Step 2:** 检查 1280×760 截图中的字体、字重控件、双击编辑覆盖层与键盘焦点。

**Step 3:** 运行 `git diff --check`，只暂存本轮文件/代码块并提交。
