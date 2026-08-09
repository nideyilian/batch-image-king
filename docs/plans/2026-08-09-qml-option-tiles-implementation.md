# QML Option Tiles Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 用统一的点击选项模块替换四组混乱的 QML 开关布局，并保持全部现有业务行为。

**Architecture:** 新增无业务状态的 `OptionTile.qml`，由父级绑定现有 ViewModel 属性并处理点击。抽屉使用常规规格，窄属性区域使用紧凑规格；互斥和多选仅改变无障碍角色，不改变数据契约。

**Tech Stack:** PySide6、Qt Quick/QML、pytest、离屏软件渲染。

---

### Task 1: 建立组件结构测试

**Files:**
- Modify: `tests/test_qml_design_system.py`
- Modify: `tests/test_qml_export_and_color_picker_layout.py`

**Step 1:** 增加 `OptionTile` 组件注册、键盘触发和可访问角色断言。

**Step 2:** 增加组合策略、随机变换、尺寸匹配、多标签导出和高级性能区域的模块数量及状态绑定断言。

**Step 3:** 运行相关单元测试，确认新断言在实现前失败。

### Task 2: 新增通用 OptionTile

**Files:**
- Create: `app/qml/components/OptionTile.qml`
- Modify: `app/qml/components/qmldir`

**Step 1:** 实现常规和紧凑尺寸、选中/悬停/焦点/禁用状态。

**Step 2:** 实现鼠标、Space、Return 激活以及 CheckBox/RadioButton 可访问语义。

**Step 3:** 运行组件结构测试。

### Task 3: 迁移参数区域

**Files:**
- Modify: `app/qml/Main.qml`

**Step 1:** 将单文档组合策略迁移到 `OptionTile`，移除内联 `ExportStrategyTile`。

**Step 2:** 将随机变换改为三列紧凑模块，并把范围字段改为按启用状态展开。

**Step 3:** 将尺寸匹配的三个开关改为三列紧凑模块。

**Step 4:** 将多标签导出策略改为两列常规模块。

**Step 5:** 将高级导出性能选项改为三列常规模块。

### Task 4: 验证与提交

**Files:**
- Test: `tests/test_qml_design_system.py`
- Test: `tests/test_qml_export_and_color_picker_layout.py`
- Test: `tests/test_qml_workbench_smoke.py`

**Step 1:** 运行目标单元测试。

**Step 2:** 运行批量导出抽屉离屏渲染测试并检查截图像素有效。

**Step 3:** 运行 QML 布局检测。

**Step 4:** 检查差异，只暂存本轮文件和本轮修改片段后提交。

