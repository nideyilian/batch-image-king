# QML Shaped Layers Implementation Plan

**Goal:** 在 QML 工作台中实现基于真实图片内容的异形图层创建、形状切换和专用参数编辑。

**Architecture:** 复用 `ShapedLayer`、`ShapeType`、`Document.add_shaped_layer()` 和统一渲染管线；`WorkspaceViewModel` 提供能力属性与原子命令，QML 只负责菜单、文件选择和属性绑定。

**Tech Stack:** Python 3、PySide6 QObject/QML、Pillow、pytest。

---

### Task 1: 异形图层创建合约

**Files:**
- Create: `tests/test_qml_shaped_layers.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Steps:**
1. 编写真实图片创建、几何尺寸、默认参数和非法输入测试。
2. 实现形状 ID 映射、图片校验和居中创建命令。
3. 验证图层类型、当前选择、历史和文档修改状态。

### Task 2: 形状属性合约

**Files:**
- Modify: `tests/test_qml_shaped_layers.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Steps:**
1. 编写五种形状切换、梯形参数、多边形参数、锁定和撤销测试。
2. 实现 capability 属性、当前值属性和验证 Slot。
3. 验证缓存失效、撤销/重做和选择状态。

### Task 3: 持久化与真实渲染

**Files:**
- Modify: `tests/test_qml_shaped_layers.py`

**Steps:**
1. 编写 `.cmp` 保存加载后类型和参数保持测试。
2. 编写圆形蒙版真实预览像素测试。
3. 确认现有序列化与渲染管线无需格式变更。

### Task 4: QML 创建入口与属性面板

**Files:**
- Modify: `app/qml/Main.qml`
- Modify: `app/qml/qml_main.py`
- Modify: `tests/test_qml_workbench_smoke.py`

**Steps:**
1. 将禁用异形按钮替换为形状菜单和图片选择流程。
2. 让异形图层复用图片内容源面板。
3. 增加形状分段网格、梯形和多边形参数控件。
4. 增加稳定的异形演示启动参数和源码合约测试。

### Task 5: 验证与提交

**Files:**
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`
- Modify: `docs/qml-functional-parity-audit.md`

**Steps:**
1. 运行异形、文档桥接、图层效果和 QML 烟雾测试。
2. 运行单元测试并记录既有失败。
3. 在 1280x760 与 1600x960 检查创建入口和属性面板。
4. 精确暂存并提交本阶段文件，重启可见工作台。
