# QML Layer Effects Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 QML 工作台中接入可撤销、可序列化的混合模式、描边和圆角编辑。

**Architecture:** `WorkspaceViewModel` 将 QML 使用的稳定混合模式 ID 和十六进制颜色转换为现有模型属性，并复用统一属性命令完成历史、缓存与预览刷新。QML 使用新增的暗色 `SelectBox` 和现有 `ValueBox`、`ToggleSwitch` 构建紧凑效果面板。

**Tech Stack:** Python 3、PySide6 QObject/QML、Qt Quick Controls、pytest、Pillow。

---

### Task 1: 锁定效果命令合约

**Files:**
- Create: `tests/test_qml_layer_effects.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1:** 编写图片图层混合模式、描边、圆角属性读取和修改测试。

**Step 2:** 运行 `python -m pytest tests/test_qml_layer_effects.py -v`，确认新接口缺失。

**Step 3:** 实现混合模式映射、颜色解析、能力属性与修改 Slot。

**Step 4:** 验证数值边界、非法输入和相同值不产生额外历史记录。

### Task 2: 文字图层与文档生命周期

**Files:**
- Modify: `tests/test_qml_layer_effects.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1:** 编写文字描边、锁定保护、撤销/重做测试。

**Step 2:** 编写 `.cmp` 保存加载往返测试。

**Step 3:** 运行专项测试，验证类型能力和序列化保持正确。

### Task 3: 构建专业效果面板

**Files:**
- Create: `app/qml/components/SelectBox.qml`
- Modify: `app/qml/components/qmldir`
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Step 1:** 实现稳定 30 px 高度的暗色下拉选择器，包括悬停、焦点、禁用和弹出列表状态。

**Step 2:** 启用“效果”标签，将静态描边与圆角占位替换为真实绑定。

**Step 3:** 在外观区接入混合模式，在效果区接入描边开关、宽度、色板、颜色选择器和圆角预设。

**Step 4:** 扩充 QML 源码合约和离屏加载测试。

### Task 4: 渲染与视觉验证

**Files:**
- Modify: `app/qml/qml_main.py`
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`

**Step 1:** 增加截图启动参数，使示例图片图层可预置描边、圆角和混合模式。

**Step 2:** 运行效果、图层栈、内容源、文档桥接和 QML 烟雾测试。

**Step 3:** 生成 1280x760 与 1600x960 截图，检查效果页的密度、弹出层、文字截断和画布差异。

**Step 4:** 运行 `python -m pytest -m unit`，记录与本阶段无关的既有失败。

**Step 5:** 精确暂存本阶段文件并提交 `feat(qml): add layer appearance effects`，随后重启可见 QML 工作台。
