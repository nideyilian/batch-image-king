# 07. 持久化与预设

## `.cmp` 文件

项目文件和预设文件主要使用 `.cmp`。底层格式是 pickle 二进制，不是 JSON。

典型保存内容：

| 字段 | 说明 |
| --- | --- |
| `version` | 文档格式版本 |
| `canvas_width` / `canvas_height` | 画布尺寸 |
| `layers` | 图层数据 |
| `selected_layer_index` | 当前选中图层 |
| `export_settings` | 导出设置 |
| `view_settings` | 缩放、偏移、参考线等视图设置 |
| `layer_size_matches` | 尺寸匹配配置 |
| `binding_groups` | 绑定组数据 |

维护规则：

- 不要用文本方式读写 `.cmp`。
- 新增字段要有默认值和旧文件兼容。
- 修改图层属性时要同步序列化、反序列化、历史快照和 UI 面板。

## `DocumentSerializer`

文件：`app/models/document_serializer.py`

职责：

- 保存和加载 pickle。
- 准备文档数据。
- 序列化单个图层。
- 恢复文档数据。
- 反序列化图片/文字/异形/分组图层。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `serialize_document(document, file_path)` | 保存文档到文件 |
| `deserialize_document(file_path)` | 从文件读取文档数据 |
| `serialize_document_data(document)` | 序列化为 dict |
| `prepare_document_data(document)` | 准备保存数据 |
| `serialize_layer(layer)` | 序列化单个图层 |
| `restore_document_data(document, document_data)` | 恢复到 Document |
| `deserialize_layer(layer_data, parent=None)` | 反序列化单个图层 |

图层类型映射：

| `type` | 对应模型 |
| --- | --- |
| `group` | `LayerGroup` |
| `text` | `TextLayer` |
| `shaped` | `ShapedLayer` |
| `image` | `Layer` |

## 历史记录

主要文件：

- `app/models/document_history.py`
- `app/models/document.py`

`Document.save_state(action_name)` 会保存历史快照，用于撤销/重做。高频 UI 操作通常需要延迟保存历史，避免每个像素拖动都生成一个历史项。

维护图层属性时应检查：

- 属性是否进入图层 `serialize()`。
- `DocumentSerializer.serialize_layer()` 是否兜底保存。
- UI 修改是否调用 `save_state()` 或延迟历史保存。
- 撤销/重做后是否正确刷新画布和面板。

## 预设系统

主要文件：

- `app/utils/preset_manager.py`
- `app/utils/preset_document_loader.py`
- `app/utils/preset_thumbnail_service.py`
- `app/ui/preset_store_dialog.py`
- `app/ui/preset_panel.py`
- `app/ui/preset_run_dialog.py`

### 预设目录

根目录 `presets` 是初始预设文件，内容也是二进制。运行时用户预设保存在用户数据目录：

| 平台 | 路径 |
| --- | --- |
| Windows | `%APPDATA%\批图王\presets` |
| Linux/macOS | `~/.config/批图王/presets` |

预设索引：

```text
presets_index.json
```

### `PresetManager`

职责：

- 创建用户预设目录。
- 从根目录 `presets` 复制初始预设。
- 维护索引 JSON。
- 保存单文档预设和多文档预设。
- 加载、删除、重命名、复制、导入、导出预设。
- 提供预设中心摘要元数据。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `_get_user_data_dir()` | 获取用户数据目录 |
| `_copy_initial_presets()` | 复制初始预设 |
| `_load_index()` / `_save_index()` | 读取/保存索引 |
| `get_preset_list()` / `get_all_presets()` | 获取预设列表 |
| `get_preset_summary()` | 获取摘要 |
| `save_preset(...)` | 保存预设 |
| `save_preset_from_document(...)` | 从当前文档保存 |
| `save_preset_documents(...)` | 保存多文档预设 |
| `load_preset(...)` | 加载预设 |

## 字体缓存

文件：`fonts_cache.json`

`TextLayer` 会扫描系统字体并缓存结果。修改字体扫描逻辑时要考虑：

- Windows 字体目录和注册表。
- macOS/Linux 字体目录。
- 字体名称推断。
- 缓存失效和异常回退。

## 视图设置

`Document.view_settings` 保存：

- 画布缩放。
- 视图偏移。
- 参考线。
- 吸附设置。
- 其他 UI 视图状态。

`CanvasWidget` 负责从文档加载和回写视图设置，多标签切换时 `MainWindow` 会同步标签页状态。

## 导出设置

`Document.export_settings` 保存批量导出设置，例如：

- 输出目录。
- 数量。
- 文件名规则。
- 是否使用图层文件名。
- 选择的图层索引。
- 格式和质量策略。
- 内存保护。
- 遍历/随机模式。
- 智能采样。
- 唯一使用图层。

批导窗口会把设置保存到当前文档，同时也可能写入本机持久化配置，以便新窗口恢复默认值。
