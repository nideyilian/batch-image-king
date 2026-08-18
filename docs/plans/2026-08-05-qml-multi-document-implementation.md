# QML Multi-document Implementation Plan

**Goal:** 为 QML 工作台实现真实多标签文档、新建画布、切换、关闭确认和会话状态隔离。

**Architecture:** 使用 `WorkspaceSessionViewModel` 管理多个真实 `Document`，`WorkspaceViewModel` 仅桥接当前活动文档，`BatchExportViewModel` 按文档保存和恢复配置/结果状态。QML 通过模型角色渲染标签，并通过信号驱动保存确认。

**Tech Stack:** Python 3、PySide6 QObject/QAbstractListModel/QML、Qt Quick Controls、pytest。

---

### Task 1: 会话模型合约

**Files:**
- Create: `tests/test_qml_workspace_sessions.py`
- Create: `app/qml/viewmodels/workspace_session_view_model.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Steps:**
1. 编写新建、尺寸校验、切换和最后标签关闭规则测试。
2. 为 `WorkspaceViewModel` 增加安全公开的活动文档切换入口。
3. 实现会话列表角色、文档信号连接和活动索引更新。
4. 验证每个文档的图层选择、历史和画布尺寸独立。

### Task 2: 打开与关闭确认

**Files:**
- Modify: `tests/test_qml_workspace_sessions.py`
- Modify: `app/qml/viewmodels/workspace_session_view_model.py`

**Steps:**
1. 编写打开新标签、重复路径激活、关闭确认、保存失败和放弃关闭测试。
2. 实现独立加载后插入、规范化路径去重和待关闭索引。
3. 实现保存后关闭、另存为后关闭、放弃和取消分支。

### Task 3: 批量导出会话隔离

**Files:**
- Modify: `tests/test_qml_batch_export_view_model.py`
- Modify: `app/qml/viewmodels/batch_export_view_model.py`

**Steps:**
1. 编写两个文档之间配置和完成状态独立的测试。
2. 在文档切换前保存状态快照，切换后恢复目标状态。
3. 保持导出运行期间工作区和会话操作阻塞。

### Task 4: QML 标签和对话框

**Files:**
- Modify: `app/qml/qml_main.py`
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Steps:**
1. 注册 `workspaceSessions` 上下文模型并迁移打开项目入口。
2. 将静态标签替换为横向真实标签列表和关闭按钮。
3. 增加新建画布弹窗、常用尺寸、自定义输入与错误提示。
4. 增加未保存确认和无路径保存对话框衔接。
5. 增加多标签启动参数，用于视觉验收。

### Task 5: 验证和交付

**Files:**
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`

**Steps:**
1. 运行会话、文档桥接、批量导出和 QML 烟雾测试。
2. 运行 `python -m pytest -m unit`，记录既有失败但不扩散修复。
3. 在 1280x760 和 1600x960 下检查标签溢出、对话框、长文件名和修改标记。
4. 更新说明与预览，精确暂存本阶段文件并创建本地 Git 提交。
5. 重启可见 QML 工作台，报告 PID、标题和窗口句柄。
