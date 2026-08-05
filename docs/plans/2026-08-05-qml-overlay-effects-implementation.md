# QML Overlay Effects Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 QML 工作台中实现可撤销、可序列化的颜色叠加与双端线性渐变叠加。

**Architecture:** `WorkspaceViewModel` 暴露通用叠加 capability、状态和原子命令，并复用现有颜色转换与属性修改管线。QML 在现有效果页中按需显示颜色、透明度、渐变端点和角度控件，不直接读取底层图层对象。

**Tech Stack:** Python 3、PySide6 QObject/QML、Qt Quick、pytest、Pillow。

---

### Task 1: 锁定叠加效果合约

**Files:**
- Modify: `tests/test_qml_layer_effects.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1:** 编写颜色叠加与渐变叠加 capability、默认值和修改测试。

**Step 2:** 运行 `python -m pytest tests/test_qml_layer_effects.py -v`，确认新接口缺失。

**Step 3:** 实现状态属性、颜色端点修改、强度和角度命令。

**Step 4:** 运行专项测试并确认通过。

### Task 2: 互斥、历史和序列化

**Files:**
- Modify: `tests/test_qml_layer_effects.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1:** 编写颜色/渐变互斥、单次撤销、锁定保护和非法输入测试。

**Step 2:** 编写 `.cmp` 保存加载往返测试。

**Step 3:** 使用 `_set_layer_attrs()` 实现原子模式切换并运行测试。

### Task 3: 接入专业效果面板

**Files:**
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Step 1:** 增加颜色叠加启用、颜色和强度控件。

**Step 2:** 增加渐变启用、双端颜色、强度、角度和方向预设控件。

**Step 3:** 使用系统 `ColorDialog` 处理三种颜色目标，并保持 `#RRGGBBAA` 转换正确。

**Step 4:** 扩充 QML 源码合约与离屏加载测试。

### Task 4: 渲染与视觉验收

**Files:**
- Modify: `app/qml/qml_main.py`
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`

**Step 1:** 扩展 `--demo-effects`，为示例图片预置渐变叠加。

**Step 2:** 增加真实预览像素测试，确认颜色和渐变进入渲染管线。

**Step 3:** 运行全部 QML 专项测试和单元测试。

**Step 4:** 生成 1280x760 与 1600x960 截图，集中检查效果面板和画布。

**Step 5:** 精确暂存本阶段文件并提交 `feat(qml): add color and gradient overlays`，随后重启可见 QML 工作台。
