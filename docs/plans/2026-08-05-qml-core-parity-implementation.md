# QML Core Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 将 QML 工作台补齐到可承担批图王核心编辑、编排、数据组合和批量导出工作的真实功能水平。

**Architecture:** 复用现有 `Document`、图层、分组、参考线、预设、绑定、尺寸匹配与导出模型；由 QML ViewModel 提供稳定、可测试的命令合约。文档内容修改统一进入历史和渲染失效流程，列表型管理与长任务使用独立 ViewModel。

**Tech Stack:** Python 3、PySide6 QObject/QML、Pillow、pytest、现有 FastRenderer 与批量导出执行器。

---

### Task 1: 文字阴影、发光与图层样式剪贴板

**Files:**
- Modify: `app/models/text_layer.py`
- Modify: `app/models/text_layer_render.py`
- Modify: `app/models/text_layer_serialize.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/Main.qml`
- Create: `tests/test_qml_text_effects.py`
- Modify: `tests/test_qml_workbench_smoke.py`

**Steps:**
1. 写失败测试，覆盖阴影/发光属性、输入边界、撤销、`.cmp` 往返和真实渲染像素。
2. 为 `TextLayer` 添加正式属性与缓存失效，在文字蒙版之后使用 Pillow 模糊滤镜合成阴影和发光。
3. 在 `WorkspaceViewModel` 暴露效果属性、修改命令和按图层类型过滤的样式复制/粘贴。
4. 在效果页加入阴影/发光区，在图层工具区加入复制样式和粘贴样式命令。
5. 运行 `python -m pytest tests/test_qml_text_effects.py tests/test_text_layer_core.py tests/test_qml_workbench_smoke.py -v`。
6. 截图验收并提交 `feat(qml): add text effects and style clipboard`。

### Task 2: 自由裁剪与矢量路径节点

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/Main.qml`
- Modify: `app/qml/qml_main.py`
- Create: `tests/test_qml_crop_and_vector_path.py`
- Modify: `tests/test_qml_workbench_smoke.py`

**Steps:**
1. 测试现有图片裁剪和 `layer_vector_mixin.py` 路径 API 的 ViewModel 映射、历史与序列化。
2. 接入自由裁剪矩形的开始、更新、确认和取消命令。
3. 接入矩形转路径、节点选择/移动/插入/删除、节点类型和闭合切换。
4. 在画布叠层绘制裁剪框、节点和控制柄，并实现鼠标命中。
5. 运行专项测试与渲染回归，视觉验收后提交 `feat(qml): add crop and vector path editing`。

### Task 3: 多选、分组与批量编排

**Files:**
- Modify: `app/qml/viewmodels/layer_list_model.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/Main.qml`
- Create: `tests/test_qml_layer_arrangement.py`

**Steps:**
1. 测试 `Document.selected_layer_indices`、`LayerGroup` 序列化和批量命令。
2. 支持 Ctrl/Shift 多选、画布框选、选区主图层及多选边界。
3. 接入组/解组、批量显隐/锁定、删除、复制、对齐与等距分布。
4. 接入拖拽排序和图层右键菜单，保持组内层级语义。
5. 验证撤销、保存加载和预览，提交 `feat(qml): add multi-layer arrangement`。

### Task 4: 标尺、参考线与画布预设

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Create: `app/qml/viewmodels/canvas_preset_view_model.py`
- Modify: `app/qml/Main.qml`
- Create: `tests/test_qml_guides_and_canvas_presets.py`

**Steps:**
1. 测试 `view_settings`、参考线和 `CanvasPresetManager` 合约。
2. 接入标尺显示、参考线新增/拖动/删除、吸附和显示开关。
3. 接入画布预设列表、创建、重命名、删除和应用。
4. 验证多标签隔离与 `.cmp` 往返，提交 `feat(qml): add guides and canvas presets`。

### Task 5: 项目预设管理

**Files:**
- Create: `app/qml/viewmodels/preset_manager_view_model.py`
- Modify: `app/qml/Main.qml`
- Create: `tests/test_qml_preset_manager.py`

**Steps:**
1. 测试 `PresetManager` 的列表、保存、加载、重命名和删除合约。
2. 用独立 ViewModel 包装二进制 `.cmp` 预设和索引操作。
3. 在工作台增加预设浏览与管理抽屉，并处理名称冲突和删除确认。
4. 验证加载后文档、绑定和尺寸匹配状态完整，提交 `feat(qml): add project preset management`。

### Task 6: 绑定组与尺寸匹配

**Files:**
- Create: `app/qml/viewmodels/binding_manager_view_model.py`
- Create: `app/qml/viewmodels/size_match_view_model.py`
- Modify: `app/qml/Main.qml`
- Create: `tests/test_qml_binding_and_size_match.py`

**Steps:**
1. 测试绑定组、全局组合和尺寸匹配关系的创建、更新、删除及序列化。
2. 为 `LayerBindingManager` 和 `LayerSizeMatchManager` 建立列表模型与参数校验。
3. 接入绑定分组、候选来源、组合预览、全局开关和尺寸匹配自动遮罩设置。
4. 用 FastRenderer 验证组合一致性与尺寸匹配真实生效，提交 `feat(qml): add binding and size matching`。

### Task 7: 高级单文档批量导出

**Files:**
- Modify: `app/qml/viewmodels/batch_export_view_model.py`
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_batch_export_view_model.py`

**Steps:**
1. 测试起始序号、遍历模式、预计算、采样去重、性能和安全参数。
2. 将参数传给现有优化执行器，不在 QML 线程循环渲染。
3. 接入高级设置、阶段进度、失败摘要、取消和重试状态。
4. 运行随机图片/文案、绑定和停滞保护回归，提交 `feat(qml): complete batch export controls`。

### Task 8: 多标签批量导出

**Files:**
- Create: `app/qml/viewmodels/multi_tab_export_view_model.py`
- Modify: `app/qml/viewmodels/workspace_session_view_model.py`
- Modify: `app/qml/Main.qml`
- Create: `tests/test_qml_multi_tab_export.py`

**Steps:**
1. 测试多文档选择、独立参数、总量计算、串行执行、取消和失败隔离。
2. 复用每个文档的批量导出能力，建立队列状态机与统一进度。
3. 接入多标签导出抽屉、文档勾选、逐文档配置和结果摘要。
4. 验证文档关闭/切换、部分失败和取消，提交 `feat(qml): add multi-tab batch export`。

### Task 9: 完整验收与审计收口

**Files:**
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`
- Modify: `docs/qml-functional-parity-audit.md`

**Steps:**
1. 逐项将审计矩阵更新为已完成或写明仍存在的底层限制。
2. 运行所有 `test_qml*.py`、核心模型/渲染测试和 `python -m pytest`。
3. 在 1280x760 与 1600x960 验收编辑、编排、预设、绑定和导出工作流。
4. 运行 QML 检测器、检查 Git 差异并提交 `docs(qml): complete core parity audit`。
