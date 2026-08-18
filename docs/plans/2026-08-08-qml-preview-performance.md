# QML Preview Performance Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 消除 QML 启动、连续调参和预览刷新中的 GUI 线程阻塞，使交互保持即时响应并在空闲后恢复全质量画面。

**Architecture:** `WorkspaceViewModel` 负责快照和任务代际调度，`_PreviewTask` 只渲染独立文档快照；FastRenderer 继续作为唯一预览渲染核心。字体目录使用后台线程加载，图片提供器利用 QImage 隐式共享减少整帧复制。

**Tech Stack:** Python 3.8、PySide6/QML、QThreadPool、Pillow、FastRenderer、pytest。

---

### Task 1: Add Preview Scheduling Regression Tests

**Files:**
- Create: `tests/test_qml_preview_performance.py`
- Modify: `tests/helpers/qml_canvas_interaction_probe.py`

**Step 1: Write the failing tests**

新增测试验证：后台渲染开始后图层 setter 不被渲染锁阻塞；连续请求取消旧 token；旧 generation 结果不会发布；字体 getter 只启动后台加载而不调用同步扫描。

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_qml_preview_performance.py -v`

Expected: 当前实现因渲染任务持有 `_document_lock`、无 token 和同步字体扫描而失败。

### Task 2: Isolate Background Preview Rendering

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1: Build a snapshot on the GUI thread**

在短锁区间内调用 `DocumentSerializer.serialize_document_data()`，将字典交给 worker。

**Step 2: Restore and render in the worker**

worker 创建独立 `Document(parent=None)`，恢复快照，并把 `interactive_low_quality`、`active_layer_index` 和 `cancel_token` 传入 `render_preview_to_image()`。

**Step 3: Reject stale results**

任务结果携带 generation。只有 generation 等于当前内容代际时才能更新 provider。

**Step 4: Run focused tests**

Run: `python -m pytest tests/test_qml_preview_performance.py -v`

Expected: 快照隔离、取消和 stale-result 测试通过。

### Task 3: Add Two-Stage Preview Quality

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1: Queue interactive frame**

自动请求使用短防抖并渲染 `interactive_low_quality=True`，活动图层索引用于 FastRenderer 增量路径。

**Step 2: Queue idle high-quality frame**

独立单次定时器在用户停止修改后请求 `interactive_low_quality=False` 的最终帧。

**Step 3: Keep automatic rendering non-blocking**

自动预览不切换全局 `busy`，避免画布中央 BusyIndicator 闪烁；显式同步渲染仍保留 busy 状态。

**Step 4: Run focused tests**

Run: `python -m pytest tests/test_qml_document_bridge.py tests/test_qml_preview_performance.py -v`

Expected: 原有 provider 契约和两阶段调度测试通过。

### Task 4: Make Font Catalog Loading Non-Blocking

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/qml_main.py`

**Step 1: Return lightweight fallback options**

字体缓存为空时返回当前字体/常用字体列表，并启动后台扫描，不在 Property getter 内扫描系统字体。

**Step 2: Publish catalog on the GUI thread**

后台完成后通过 Qt signal 更新缓存并发出单一有效 notify 信号。

**Step 3: Start preload before QML loads**

入口创建 WorkspaceViewModel 后立即调用 `startFontCatalogPreload()`。

**Step 4: Run interaction probe**

Run: `python tests/helpers/qml_canvas_interaction_probe.py`

Expected: 输出 `dragged layer to ...` 并在 30 秒内退出 0。

### Task 5: Reduce Frame Copy and High-Frequency Notify Cost

**Files:**
- Modify: `app/qml/preview_image_provider.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1: Replace deep copies with implicit sharing**

使用 `QImage(image)` 保存和返回共享帧，只在实际修改时由 Qt 自动 detach。

**Step 2: Add an opacity-specific notify signal**

透明度变化仅发出外观信号；选择变化再转发该信号，保持 QML 切换图层时正确刷新。

**Step 3: Run focused tests**

Run: `python -m pytest tests/test_qml_preview_performance.py tests/test_qml_layer_effects.py -v`

Expected: provider 所有权和透明度刷新测试通过。

### Task 6: Full Verification and Commit

**Files:**
- Test: `tests/`

**Step 1: Run QML tests**

Run: `python -m pytest tests/test_qml_*.py -v`

**Step 2: Run full suite**

Run: `python -m pytest`

**Step 3: Launch the QML app**

Run: `python -m app.qml.qml_main --demo`

Expected: 窗口启动、拖动/缩放/透明度调节连续响应，交互帧快速出现，停手后画面变清晰。

**Step 4: Commit only this task's hunks**

只暂存本轮新增文档、测试和性能修复，不纳入用户已有删除或渲染器改动。
