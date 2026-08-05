# QML Batch Export Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 在 QML 工作台中加入复用现有高性能管线的异步批量导出工作流。

**Architecture:** 使用独立 `BatchExportViewModel` 管理参数、任务和状态，通过 `QThreadPool` 调用 `Document.batch_export()`。`WorkspaceViewModel` 提供文档切换信号、共享锁和导出期间的编辑保护，QML 以右侧抽屉承载完整导出交互。

**Tech Stack:** Python 3、PySide6 QObject/QML、Qt Quick Controls、pytest、Pillow。

---

### Task 1: 批量导出 ViewModel 合约

**Files:**
- Create: `tests/test_qml_batch_export_view_model.py`
- Create: `app/qml/viewmodels/batch_export_view_model.py`

**Step 1:** 编写参数校验、进度更新、成功、失败和取消传播的失败测试。

**Step 2:** 运行 `python -m pytest tests/test_qml_batch_export_view_model.py -v`，确认因模块缺失失败。

**Step 3:** 实现参数属性、文档信号连接、`QRunnable` 后台任务和状态归并。

**Step 4:** 再次运行同一测试文件，确认全部通过。

### Task 2: Workspace 导出互斥

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `tests/test_qml_batch_export_view_model.py`

**Step 1:** 增加文档跟随和运行期间拒绝编辑/切换的测试。

**Step 2:** 新增 `documentObjectChanged`、`exportRunning`、共享文档锁和统一编辑守卫。

**Step 3:** 运行批量导出与文档桥接测试，确认切换、锁定和旧功能均正常。

### Task 3: QML 导出抽屉

**Files:**
- Modify: `app/qml/qml_main.py`
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Step 1:** 在启动器注册 `batchExport` 上下文对象。

**Step 2:** 将顶部主按钮改为批量导出，保留单图图标按钮；实现目录、数量、模板、格式、智能采样、运行进度、取消及结果状态。

**Step 3:** 扩充离屏烟雾测试，确认抽屉对象存在且窗口可渲染。

### Task 4: 验证与视觉验收

**Files:**
- Modify: `app/qml/preview.png`

**Step 1:** 运行 `python -m compileall -q app/qml tests`。

**Step 2:** 运行批量导出 ViewModel、QML 桥接与 QML 烟雾测试。

**Step 3:** 运行 `python -m pytest -m unit`，记录任何与本轮无关的既有失败。

**Step 4:** 分别生成 1280x760 和 1600x960 截图，检查溢出、遮挡、空白和状态层级，并更新 `app/qml/preview.png`。

**Step 5:** 启动新版交互窗口，精确暂存本轮文件并提交 `feat(qml): add batch export workflow`。
