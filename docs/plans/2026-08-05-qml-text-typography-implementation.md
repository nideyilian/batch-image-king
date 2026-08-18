# QML Text Typography Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 QML 工作台中实现可搜索、可撤销、可持久化的文字字体与排版控制。

**Architecture:** `WorkspaceViewModel` 统一映射 QML 标识和 `TextLayer` 正式属性，所有修改复用 `_change_selected_text()` 的历史与缓存失效链。QML 新增可搜索字体选择器，并将字体和排版拆成两个高密度属性区块。

**Tech Stack:** Python 3、PySide6 QObject/QML、Pillow、pytest。

---

### Task 1: 文字排版业务合约

**Files:**
- Create: `tests/test_qml_text_typography.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1: Write failing tests**

覆盖字体列表与当前字体、粗体/斜体组合、三种对齐、横竖排、行距、字距、内边距和自动文本框属性。

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_qml_text_typography.py -v`

Expected: FAIL，缺少字体与排版 Property 和 Slot。

**Step 3: Implement ViewModel properties and commands**

新增字体选项缓存、样式组合映射、对齐映射和数值范围钳制。所有写操作使用 `_change_selected_text()`，非文字和锁定图层沿用现有拒绝逻辑。

**Step 4: Run focused tests**

Run: `python -m pytest tests/test_qml_text_typography.py -v`

Expected: PASS。

### Task 2: 历史、持久化与渲染合约

**Files:**
- Modify: `tests/test_qml_text_typography.py`

**Step 1: Add round-trip and rendering tests**

验证撤销/重做、`.cmp` 保存加载、自动文本框几何同步，以及粗体、斜体、间距和竖排作用于真实渲染。

**Step 2: Run model and renderer tests**

Run: `python -m pytest tests/test_qml_text_typography.py tests/test_text_layer_core.py -v`

Expected: PASS。

### Task 3: 可搜索字体控件与排版面板

**Files:**
- Create: `app/qml/components/FontSelectBox.qml`
- Modify: `app/qml/components/qmldir`
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Step 1: Add source assertions**

断言字体选择、样式切换、对齐、间距、竖排和自动文本框命令均已连接。

**Step 2: Build searchable font picker**

实现带过滤输入、弹出列表、当前值回显、键盘确认和长名称省略的 `FontSelectBox`。

**Step 3: Build typography sections**

将字号从“文字内容”区移到“字体”区，新增粗体/斜体图标按钮；“排版”区加入对齐分段控件、方向与自动文本框开关以及三个数值输入。

**Step 4: Run QML tests**

Run: `python -m pytest tests/test_qml_workbench_smoke.py tests/test_qml_text_typography.py -v`

Expected: PASS。

### Task 4: 文档、视觉与完整回归

**Files:**
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`
- Modify: `app/qml/qml_main.py`
- Modify: `docs/qml-functional-parity-audit.md`

**Step 1: Update status documentation**

记录文字字体与排版已接入，文字外观仍属于下一阶段。

**Step 2: Run regression suites**

Run: `$qmlTestFiles = Get-ChildItem tests -Filter 'test_qml*.py' | Select-Object -ExpandProperty FullName; python -m pytest $qmlTestFiles`

Run: `python -m pytest tests/test_document_core.py tests/test_text_layer_core.py tests/test_fast_renderer_smoke.py -v`

Run: `python -m pytest`

Expected: 新增测试通过；完整测试只保留已记录的既有失败。

**Step 3: Capture and inspect screenshots**

在 1280x760 与 1600x960 展开文字排版区，检查长字体名、按钮、后缀、滚动和禁用状态。

**Step 4: Commit and launch**

精确暂存本阶段文件，提交 `feat(qml): add text typography controls`，确认工作区干净并启动最新 QML 窗口。

