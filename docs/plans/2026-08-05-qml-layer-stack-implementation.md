# QML Layer Stack Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 QML 工作台中实现可撤销的图层复制和层级移动，并接入底栏按钮与快捷键。

**Architecture:** `WorkspaceViewModel` 负责原子复制、唯一命名、新 ID、相邻层级移动和状态属性；QML 只绑定可用状态并调用命令。底层图层序列化和渲染顺序保持不变。

**Tech Stack:** Python 3、PySide6 QObject/QML、Qt Quick、pytest。

---

### Task 1: 图层复制合约

**Files:**
- Create: `tests/test_qml_layer_stack.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1:** 编写图片与文字复制、唯一名称、独立对象、新 ID 和单次撤销测试。

**Step 2:** 运行测试确认新接口缺失。

**Step 3:** 实现原子插入、信号连接、缓存失效和历史保存。

**Step 4:** 运行测试确认通过。

### Task 2: 层级移动合约

**Files:**
- Modify: `tests/test_qml_layer_stack.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1:** 编写前移、后移、边界、相邻锁定和撤销测试。

**Step 2:** 实现可用状态属性和移动 Slot。

**Step 3:** 验证选中对象、图层顺序和预览刷新。

### Task 3: QML 命令入口

**Files:**
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Step 1:** 替换图层底栏占位按钮，接入复制、后移、前移和删除。

**Step 2:** 增加 `Ctrl+D`、`Ctrl+[`、`Ctrl+]` 快捷键，并在文字编辑时禁用。

**Step 3:** 扩充 QML 源码合约和离屏加载测试。

### Task 4: 验证与提交

**Files:**
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`

**Step 1:** 更新能力说明。

**Step 2:** 运行图层栈、内容源、批量导出、文档桥接和 QML 烟雾测试。

**Step 3:** 在 1280x760 与 1600x960 下检查底栏按钮、禁用态和面板宽度。

**Step 4:** 运行单元测试，精确暂存并提交 `feat(qml): add layer stack operations`。

**Step 5:** 重启可见 QML 工作台并确认窗口标题。
