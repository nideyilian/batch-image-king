# 预览与图层面板原生崩溃修复设计

## 背景

`crash_20260701_094625.log` 记录了 `Windows fatal exception: access violation`。崩溃线程正在 `LayerPanel._full_rebuild()` 中创建 `LayerItem` 的 Qt 布局；同时两个后台画布任务都在通过同一个全局 `FastRenderer` 执行 RGBA 预览缩放。`LayerPanel` 的防抖与绑定调试定时器没有父对象，`set_document()` 还残留了一段重复的断连、重连和刷新逻辑。

普通 Python 异常捕获不了 Qt、Pillow 或 NumPy 原生层的非法内存访问，因此需要在进入原生代码前消除并发和对象生命周期风险。

## 目标

- 同一个全局 `FastRenderer` 不再同时执行多个预览入口。
- 批量导出的独立 worker renderer 不受预览锁影响。
- 图层面板销毁时，其定时器随面板一起销毁。
- 切换文档时不执行旧文档遗留的待处理刷新。
- `set_document()` 每次只断开一次旧文档、连接一次新文档并安排一次刷新。
- 不改变渲染结果、批量导出并发或图层选择行为。

## 方案

### 预览渲染串行化

`FastRenderer` 增加实例级可重入锁 `_preview_render_lock`。`render_preview()`、`render_preview_incremental()` 和 `render_preview_live()` 都通过同一锁保护完整预览调用。

锁必须可重入，因为增量预览失败时会回退调用 `render_preview()`。锁只覆盖预览入口，不包围 `render_batch()`，避免降低批量导出的 worker 并发。

### 图层面板生命周期

`LayerPanel` 的 `_update_timer` 与 `_binding_debug_timer` 改为 `QTimer(self)`，由 Qt 父子对象树管理。`set_document()` 开始时停止待处理更新并清除 `_update_pending`，随后断开旧文档、设置新文档、连接信号并安排一次刷新。

删除当前 `set_document()` 末尾重复的旧实现。面板切换到空文档时只清空列表和禁用控件，不再进入第二轮清理。

### 错误边界

继续保留现有 Python 异常回退；本次不扩大异常吞噬范围。预览锁采用 `with` 自动释放，即使渲染失败也不会阻塞后续请求。

## 测试

新增或扩展轻量级测试：

1. 两个线程同时调用同一个 renderer 的预览临界区，断言最大并发数为 1。
2. 同一线程从增量预览回退到普通预览，断言可重入且不会死锁。
3. 创建 `LayerPanel`，断言两个定时器的父对象都是面板。
4. 为旧、新文档提供计数信号，调用 `set_document()`，断言旧连接断开、新连接仅一份且仅安排一次刷新。
5. 验证现有图层面板、画布与批量导出测试不新增失败。

## 完成标准

- 回归测试先在旧代码上失败，再在修复后通过。
- 相关 Python 文件通过编译。
- 现有批量导出和图层面板测试通过。
- git diff 只包含规格、测试及 `fast_renderer.py`、`layer_panel.py` 的必要修改。
