# 05. UI 与控制器

## `MainWindow`

文件：`app/main_window.py`

`MainWindow` 是应用层协调中心，负责：

- 创建主界面、菜单栏、工具栏、状态栏和停靠面板。
- 管理多标签文档。
- 持有 `DocumentManager`、`DocumentController`、`LayerController`。
- 协调新建、打开、保存、另存为、导出、批量导出、多标签页导出、预设管理。
- 为每个文档隔离批量导出窗口和多标签导出窗口。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `setup_ui()` | 创建主界面布局 |
| `create_actions()` | 创建菜单/工具栏动作 |
| `create_menubar()` / `create_toolbar()` | 菜单和工具栏 |
| `create_dock_widgets()` | 图层、属性、预设等停靠面板 |
| `connect_signals()` | 连接文档、画布、面板信号 |
| `create_new_tab()` / `close_tab()` / `duplicate_tab()` | 多标签管理 |
| `active_document_changed(...)` | 同步当前活动文档 |
| `export_image()` | 单图导出 |
| `batch_export()` | 当前文档批量导出 |
| `multi_tab_export()` | 多标签页批量导出 |
| `_sync_document_view_settings_from_tab()` | 同步标签页视图状态 |

## 控制器

### `DocumentController`

文件：`app/controllers/document_controller.py`

职责：

- 新建文档。
- 打开 `.cmp`。
- 保存/另存为。
- 处理加载失败和异常提示。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `new_document()` | 弹出新画布对话框并创建文档 |
| `open_document()` | 选择并加载 `.cmp` |
| `save_document()` | 保存当前文档 |
| `save_document_as()` | 另存为 |

### `LayerController`

文件：`app/controllers/layer_controller.py`

职责：

- 添加图片/文字/异形图层。
- 删除、移动图层。
- 图层复制粘贴。
- 批量更新选中图层。
- 把样式应用到多个图层。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `add_layer()` | 添加普通图片图层 |
| `add_text_layer()` | 添加文字图层 |
| `delete_layer()` | 删除图层 |
| `move_layer_up()` / `move_layer_down()` | 调整层级 |
| `batch_update_layers(...)` | 批量更新 |
| `apply_style_to_selected(...)` | 多选样式应用 |
| `_serialize_layer_for_clipboard(...)` | 复制图层数据 |
| `_create_layer_from_clipboard_item(...)` | 粘贴图层 |

## 画布 `CanvasWidget`

文件：`app/ui/canvas.py`

职责：

- 绘制画布、背景、预览合成图。
- 处理缩放、平移、选择、拖拽、变换。
- 管理参考线、吸附、选择框。
- 调用 `FastRenderer` 做异步预览。
- 在批量导出冻结预览时减少 UI 干扰。

关键类与方法：

| 类/方法 | 说明 |
| --- | --- |
| `_CanvasPreviewRenderTask(QRunnable)` | 后台预览渲染任务 |
| `paintEvent(event)` | Qt 绘制入口 |
| `_build_async_render_snapshot()` | 为异步渲染构造快照 |
| `_render_composition_image_for_async()` | 后台合成图像 |
| `_composition_to_pixmap()` | PIL 图转 QPixmap |
| `_invalidate_composition_cache()` | 清理预览缓存 |
| `_persist_view_settings_to_document()` | 保存缩放/偏移等视图状态 |

## 图层面板 `LayerPanel`

文件：`app/ui/layer_panel.py`

职责：

- 展示图层列表与分组。
- 支持拖拽排序、选择、多选、可见性、锁定。
- 展示绑定状态、缩略信息。
- 批导运行中可冻结或跳过高频刷新。

关键类：

| 类 | 说明 |
| --- | --- |
| `DragDropLayerList` | 支持拖拽排序的列表 |
| `LayerItem` | 单个图层条目 |
| `LayerPanel` | 图层面板主体 |

关键方法：

| 方法 | 说明 |
| --- | --- |
| `update_layers()` | 更新图层列表 |
| `_incremental_update()` / `_full_rebuild()` | 增量或全量重建 |
| `layer_selected(...)` | 图层选择响应 |
| `_toggle_group_expanded_for_item(...)` | 分组展开/折叠 |
| `refresh_all_icons()` | 刷新缩略图/图标 |

## 属性面板 `LayerPropertiesPanel`

文件：`app/ui/layer_properties.py`

职责：

- 编辑普通图片图层和部分通用图层属性。
- 支持多选批量修改。
- 管理位置、尺寸、旋转、翻转、透明度、适配模式、描边、圆角、叠加、绑定等控件。
- 延迟保存历史，减少拖动和连续输入时的历史噪声。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `setup_ui()` | 构建属性面板控件 |
| `delayed_update_panel()` | 延迟刷新面板 |
| `_apply_to_selected_layers(...)` | 多选批量应用 |
| `_save_state_deferred(...)` | 延迟历史保存 |
| `_emit_document_change()` | 通知文档和 UI 刷新 |
| `_on_layers_selection_changed(...)` | 多选状态切换 |

## 批量导出窗口

文件：`app/ui/batch_export_dialog.py`

职责：

- 收集输出目录、数量、格式、文件名规则、质量策略、内存保护、遍历/随机模式、唯一使用等设置。
- 保存和恢复导出设置。
- 启动后台导出任务。
- 展示进度、阶段、速度、剩余时间和导出诊断。

关键类与方法：

| 类/方法 | 说明 |
| --- | --- |
| `_BatchExportTask(QRunnable)` | 后台批导任务包装 |
| `BatchExportDialog.setup_ui()` | 构建导出参数 UI |
| `update_layer_list()` | 刷新“使用图层文件名”可选图层 |
| `get_filename_template()` | 构造文件名模板，支持 `{layer:N}` |
| `build_export_request()` | 捕获 UI 设置为纯 dict，避免后台线程读 QWidget |
| `execute_export_request(document, request, cancel_callback)` | 执行导出请求 |
| `start_export()` | 校验参数并启动导出 |
| `do_export()` | 无独立进度弹窗的导出执行入口 |
| `save_settings()` / `load_settings()` | 保存/恢复设置 |

## 多标签批量导出

文件：`app/ui/multi_tab_export_dialog.py`

职责：

- 展示所有打开的标签页。
- 选择参与导出的文档。
- 配置线程数和统一导出参数。
- 为每个标签页构建导出请求。
- 使用 `ExportWorker(QRunnable)` 并行执行。
- 汇总成功/失败状态。

关键类与方法：

| 类/方法 | 说明 |
| --- | --- |
| `ExportWorkerSignals` | worker 完成信号 |
| `ExportWorker.run()` | 执行单个文档导出 |
| `MultiTabExportDialog._build_tab_export_request()` | 在 GUI 线程构造导出请求 |
| `update_tab_list()` | 刷新标签列表 |
| `get_selected_tabs()` | 获取用户选择 |
| `start_export()` | 启动多标签导出 |
| `_handle_export_finished(...)` | 处理单个标签完成 |

## UI 修改注意

- PySide6 的 `stateChanged` 传出通常是整数状态；如果只需要 bool，优先用 `toggled(bool)`。
- 后台线程不应直接读取或修改 QWidget；先在 GUI 线程捕获纯数据请求。
- 批量导出运行中，部分 UI 面板会跳过刷新，避免跨线程和高频重绘问题。
- 修改模型属性后要配套触发文档修改、历史保存、缓存失效和 UI 信号。
