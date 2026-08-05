# QML Locked And Random Transform Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 在 QML 工作台中实现可持久化、可撤销的比例锁定和真实随机位置/缩放/旋转功能。

**Architecture:** `WorkspaceViewModel` 统一暴露能力、状态和原子命令，QML 负责紧凑属性控件与锁定比例拖拽反馈。现有 `Layer` 配置和批量随机化链保持不变，只在当前实际使用的变换 mixin 中恢复遗漏的随机缩放与旋转像素处理。

**Tech Stack:** Python 3、PySide6 QObject/QML、Pillow、pytest。

---

### Task 1: 比例锁定业务合约

**Files:**
- Create: `tests/test_qml_transform_controls.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1: Write failing tests**

覆盖能力状态、锁定切换、按宽度/高度等比修改、锁定图层拒绝、撤销重做与 `.cmp` 往返。

**Step 2: Verify failures**

Run: `python -m pytest tests/test_qml_transform_controls.py -v`

Expected: FAIL，缺少比例锁定 Property 和 Slot。

**Step 3: Implement atomic geometry rules**

新增：

```python
@Property(bool, notify=selectionChanged)
def selectedSupportsAspectRatioLock(self) -> bool: ...

@Property(bool, notify=selectionChanged)
def selectedAspectRatioLocked(self) -> bool: ...

@Slot(bool, result=bool)
def setSelectedAspectRatioLocked(self, enabled: bool) -> bool: ...
```

修改 `setSelectedWidth()` 和 `setSelectedHeight()`，锁定时用 `_set_layer_attrs()` 一次写入宽高。

**Step 4: Verify focused tests**

Run: `python -m pytest tests/test_qml_transform_controls.py -v`

Expected: 比例锁定测试 PASS。

### Task 2: 随机配置与预览合约

**Files:**
- Modify: `tests/test_qml_transform_controls.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1: Write failing tests**

覆盖三类启用状态、范围钳制、缩放上下限联动、运行时重新抽样、文字/锁定拒绝、撤销和持久化。

**Step 2: Implement properties and commands**

暴露配置值、当前运行时值和摘要；实现独立开关、位置范围、缩放最小/最大、旋转范围与 `regenerateSelectedRandomTransform()`。

**Step 3: Verify focused tests**

Run: `python -m pytest tests/test_qml_transform_controls.py -v`

Expected: ViewModel 与持久化测试 PASS。

### Task 3: 恢复真实随机缩放与旋转

**Files:**
- Modify: `app/models/layer_transform_mixin.py`
- Modify: `tests/test_qml_transform_controls.py`

**Step 1: Write pixel-level failing tests**

构造不对称 RGBA 图片，固定运行时随机值，验证 50% 缩放产生透明边缘、90 度随机旋转改变象限方向。

**Step 2: Restore the rendering stage**

在 `_apply_transformations()` 末尾调用 `_apply_random_transformations()`；使用 `resize_rgba_premultiplied` 和 `rotate_rgba_premultiplied(expand=False)`，保持输出画布尺寸不变。

**Step 3: Verify pixel and renderer tests**

Run: `python -m pytest tests/test_qml_transform_controls.py tests/test_fast_renderer_smoke.py -v`

Expected: PASS。

### Task 4: QML 控件与等比拖拽

**Files:**
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`
- Modify: `tests/helpers/qml_canvas_interaction_probe.py`

**Step 1: Add source and interaction tests**

断言比例锁按钮、随机变换控件和刷新命令存在；交互探针增加锁定后四角拖拽并验证宽高比。

**Step 2: Build the inspector controls**

尺寸行加入锁链图标；将隐藏随机变换占位替换为三个真实开关、范围输入和预览刷新按钮。

**Step 3: Implement proportional drag feedback**

在 `canvasWorkspace.updateTransform()` 中依据初始宽高比和固定对角计算统一缩放倍数，并约束到画布边界。

**Step 4: Run QML tests**

Run: `python -m pytest tests/test_qml_workbench_smoke.py tests/test_qml_transform_controls.py -v`

Expected: PASS。

### Task 5: 文档、视觉和完整回归

**Files:**
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`
- Modify: `docs/qml-functional-parity-audit.md`

**Step 1: Update status documentation**

将比例锁定与随机变换标记为已接入，并记录文字图层暂不支持随机变换。

**Step 2: Run regression suites**

Run: `$qmlTestFiles = Get-ChildItem tests -Filter 'test_qml*.py' | Select-Object -ExpandProperty FullName; python -m pytest $qmlTestFiles`

Run: `python -m pytest tests/test_document_core.py tests/test_layer_serialize.py tests/test_fast_renderer_smoke.py -v`

Run: `python -m pytest`

Expected: 新增测试全部通过；完整测试只保留已记录的既有失败。

**Step 3: Capture and inspect screenshots**

在 1280x760 与 1600x960 展开随机变换区，检查文字、图标、输入框和滚动区域。

**Step 4: Commit and launch**

精确暂存本阶段文件，提交 `feat(qml): add locked and random transforms`，确认工作区干净并启动最新 QML 窗口。

