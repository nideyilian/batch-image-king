# QML Option Tiles Follow-up Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将画布、文字、形状和质量策略四组互斥参数统一为可见的点击单选模块。

**Architecture:** 复用 `OptionTile.qml` 的 `exclusive` 模式，业务状态继续由现有对话框属性和 ViewModel 提供。创建对话框只新增最小临时属性，不改变 Python 接口或序列化格式。

**Tech Stack:** PySide6、Qt Quick/QML、pytest、离屏软件渲染。

---

### Task 1: 添加结构回归测试

**Files:**
- Create: `tests/test_qml_option_tile_followup.py`

**Step 1:** 断言画布调整区域包含三个互斥 `OptionTile`，且不再使用 `SegmentedControl` 和独立说明框。

**Step 2:** 断言文字内容模式包含两个互斥 `OptionTile`，提交参数使用对话框临时状态。

**Step 3:** 断言异形形状区域包含五个互斥 `OptionTile`，创建和参数显隐使用 `shapeType`。

**Step 4:** 断言质量策略区域包含四个互斥紧凑 `OptionTile`，继续绑定 `qualityProfile`。

### Task 2: 迁移创建与调整弹窗

**Files:**
- Modify: `app/qml/Main.qml`

**Step 1:** 迁移画布调整方式并移除独立说明框。

**Step 2:** 为文字图层对话框增加 `bindingEnabled`，迁移内容模式。

**Step 3:** 为异形图层对话框增加 `shapeType`，迁移五种形状并更新所有引用。

### Task 3: 迁移批量导出质量策略

**Files:**
- Modify: `app/qml/Main.qml`

**Step 1:** 用 `2×2` 紧凑单选网格替换质量策略下拉框。

**Step 2:** 保留性能模块、内存保护和异常阈值布局。

### Task 4: 验证与提交

**Files:**
- Test: `tests/test_qml_option_tile_followup.py`
- Test: `tests/test_qml_export_and_color_picker_layout.py`
- Test: `tests/test_qml_workbench_smoke.py`

**Step 1:** 运行目标单元测试并确认 QML 可加载。

**Step 2:** 生成四个界面截图并检查最小窗口布局。

**Step 3:** 运行布局检测和全量测试。

**Step 4:** 按补丁暂存 `Main.qml`，避免纳入用户已有修改，然后提交。

