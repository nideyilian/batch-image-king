# QML Text Appearance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 QML 工作台中实现可撤销、可持久化并作用于真实渲染的文字填充、渐变、背景和局部颜色控制。

**Architecture:** `WorkspaceViewModel` 将 QML 稳定标识和十六进制颜色映射到 `TextLayer` 正式属性，所有修改复用 `_change_selected_text()`。QML 在效果标签页集中放置全局文字外观，局部颜色操作放在文字编辑器选区旁。

**Tech Stack:** Python 3、PySide6 QObject/QML、Pillow、pytest。

---

### Task 1: 文字外观业务合约

**Files:**
- Create: `tests/test_qml_text_appearance.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1: Write failing tests**

覆盖文字纯色、渐变启用、类型、方向、起止色、径向中心、背景颜色/透明度/扩展距离和局部颜色属性。

**Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_qml_text_appearance.py -v`

Expected: FAIL，缺少文字外观 Property 和 Slot。

**Step 3: Implement ViewModel properties and commands**

新增文字渐变类型/方向映射、RGBA 颜色映射、背景 Alpha 合并和局部颜色范围命令。所有写操作使用 `_change_selected_text()`，并复用锁定与导出状态检查。

**Step 4: Run focused tests**

Run: `python -m pytest tests/test_qml_text_appearance.py tests/test_text_layer_range_colors.py -v`

Expected: PASS。

### Task 2: 历史、持久化与真实渲染

**Files:**
- Modify: `tests/test_qml_text_appearance.py`

**Step 1: Add round-trip and rendering tests**

验证撤销/重做、`.cmp` 保存加载，以及纯色、渐变、背景、局部颜色改变真实输出像素。

**Step 2: Run model and renderer tests**

Run: `python -m pytest tests/test_qml_text_appearance.py tests/test_text_layer_core.py tests/test_text_layer_range_colors.py -v`

Expected: PASS。

### Task 3: QML 外观面板与选区动作

**Files:**
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Step 1: Add source assertions**

断言填充模式、颜色、渐变类型/方向/中心、背景和局部颜色命令均已连接。

**Step 2: Extend the shared color dialog**

为文字纯色、渐变端点、背景和局部颜色增加目标路由，同时保留已有描边与图层叠加行为。

**Step 3: Build text appearance sections**

在效果标签页新增“文字填充”和“文字背景”，使用现有色块、`SelectBox`、`ValueBox` 与 `ToggleSwitch`。

**Step 4: Add selection-aware local color actions**

让 `ContentTextEditor` 暴露选区起止位置，并在文字内容区加入设置/清除局部颜色命令。

**Step 5: Run QML tests**

Run: `python -m pytest tests/test_qml_workbench_smoke.py tests/test_qml_text_appearance.py -v`

Expected: PASS。

### Task 4: 文档、视觉与完整回归

**Files:**
- Modify: `app/qml/qml_main.py`
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`
- Modify: `docs/qml-functional-parity-audit.md`

**Step 1: Add `--show-text-appearance`**

选中演示文字，应用真实渐变、背景和描边，并自动打开效果标签页定位到文字填充。

**Step 2: Update status documentation**

记录文字填充、渐变、背景、描边和局部颜色已接入，阴影仍需先补渲染能力。

**Step 3: Run regression suites**

Run: `$qmlTestFiles = Get-ChildItem tests -Filter 'test_qml*.py' | Select-Object -ExpandProperty FullName; python -m pytest $qmlTestFiles`

Run: `python -m pytest tests/test_document_core.py tests/test_text_layer_core.py tests/test_text_layer_range_colors.py tests/test_fast_renderer_smoke.py -v`

Run: `python -m pytest`

Expected: 新增测试通过；完整测试只保留已记录的 4 项既有失败。

**Step 4: Capture and inspect screenshots**

在 1280x760 与 1600x960 检查填充模式、颜色色块、渐变参数、背景、描边和滚动区域。

**Step 5: Commit and launch**

精确暂存本阶段文件，提交 `feat(qml): add text appearance controls`，确认工作区干净并启动文字外观验收窗口。
