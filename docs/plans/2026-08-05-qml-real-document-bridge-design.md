# QML 真实文档桥接设计

## 目标

把已确认的 QML 工作台原型提升为独立的下一代入口，并打通 `Document -> 图层列表 -> RenderService -> QML 画布` 的真实链路。现有 `main.py`、QWidget 界面、`.cmp` 格式和导出管线保持不变。

## 范围

第一阶段支持新建、打开、保存、另存为、单图导出、选择图层、切换可见/锁定、修改位置/尺寸/不透明度以及撤销/重做。文字、异形和普通图片图层都通过同一属性适配层显示基础属性。

暂不实现画布直接拖拽、多选、参考线编辑、高级效果、绑定、尺寸匹配和批量导出。这些能力依赖本阶段建立的命令边界，后续按纵向切片接入。

## 架构

QML 只访问 `WorkspaceViewModel` 和 `LayerListModel`，不直接持有 `Document` 或图层对象。ViewModel 将文件操作、选择和属性修改转换为明确命令；命令执行前保存历史状态，执行后统一标记文档、刷新列表并请求预览。

`PreviewImageProvider` 持有当前已渲染的 `QImage`。ViewModel 调用 `app.services.preview_render_service` 获取 PIL 图像，复制为 QImage 后递增预览版本。QML 使用带版本参数的 `image://documentPreview/current` URL，确保缓存不会复用旧画面。

第一阶段在主线程同步渲染，以保证 `Document` 不在属性修改过程中被后台线程并发读取。ViewModel 使用短延迟定时器合并连续修改。完成画布拖拽阶段时，再引入文档快照与后台渲染请求序号。

## 数据模型

`LayerListModel` 提供 `name`、`typeName`、`glyph`、`accent`、`shown`、`locked` 六个角色。类型判断集中在 Python，QML 不通过类名或序列化字段猜测。

`WorkspaceViewModel` 暴露文档标题、路径、修改状态、画布尺寸、选择索引、选择图层基础属性、历史能力、忙碌状态、状态消息和预览 URL。无选择时返回稳定默认值，禁止把 Python 异常传播到 QML。

## 错误与安全

打开 `.cmp` 继续调用现有 `Document.load_document()` 和受信 pickle 加载器，不增加新的反序列化路径。QML 文件选择器只把本地路径交给 ViewModel，不执行动态 QML 或远程脚本。

文件操作失败时 ViewModel 保留当前文档，设置中文状态消息并发出非阻塞通知。无效索引、锁定图层和非法尺寸不修改模型。渲染失败时保留上一帧并显示错误，不把画布替换为空白。

## 验证

- 单元测试覆盖图层角色、选择、属性修改、撤销/重做和保存/加载。
- 集成测试覆盖真实 `RenderService` 到 `PreviewImageProvider` 的非空图像。
- QML 离屏测试生成 1600×960 与 1280×760 截图。
- 手动验证两个入口可独立启动，现有 `main.py` 不受影响。
