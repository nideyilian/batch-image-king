# 04. 核心模型

## `Document`

文件：`app/models/document.py`

`Document(QObject)` 是核心文档模型，也是多数新旧调用链的中心。它持有画布、图层、选择状态、导出设置、视图设置、历史记录、序列化器、渲染器、批量导出协调器、绑定管理器和尺寸匹配管理器。

### 主要状态

| 状态 | 说明 |
| --- | --- |
| `canvas_width` / `canvas_height` | 画布尺寸 |
| `layers` | 图层列表，包含图片、文字、异形、分组 |
| `selected_layer_index` / `selected_layer_indices` | 单选和多选状态 |
| `current_file_path` | 当前 `.cmp` 文件路径 |
| `is_modified` | 修改状态 |
| `export_settings` | 批导、质量、路径、文件名等设置 |
| `view_settings` | 缩放、偏移、参考线、吸附等视图状态 |
| `binding_manager` | 图层绑定管理 |
| `layer_size_match_manager` | 图层尺寸匹配管理 |

### 关键方法

| 方法 | 说明 |
| --- | --- |
| `create_new(width, height)` | 初始化新文档 |
| `add_layer(...)` | 添加普通图片图层 |
| `add_text_layer(text_layer)` | 添加文字图层 |
| `add_shaped_layer(shaped_layer)` | 添加异形图层 |
| `remove_layer(index)` | 删除图层 |
| `move_layer(...)` / `move_layer_up()` / `move_layer_down()` | 图层排序 |
| `select_layer(index)` / `select_layers(indices, primary_index)` | 维护选择状态 |
| `save_state(action_name)` | 保存历史快照 |
| `undo()` / `redo()` | 撤销/重做 |
| `save_document(file_path)` | 保存 `.cmp` |
| `load_document(file_path)` | 加载 `.cmp` |
| `render_document()` | 通用渲染入口 |
| `export_image(file_path)` | 单图导出入口 |
| `batch_export(...)` | 单文档批量导出入口 |
| `_analyze_document_for_export()` | 批量导出前分析 |
| `_cleanup_layers_after_export()` | 批量导出后清理临时状态 |
| `create_layer_from_data(layer_data)` | 反序列化兼容入口 |

### 维护注意

- `Document` 保留大量旧接口，新增功能需要检查新旧路径。
- `.cmp` 是 pickle 二进制格式，不要用文本方式处理。
- 批导期间会设置 `_is_batch_export_running`，UI 和渲染缓存会据此改变行为。
- 加载旧项目后会清理图层临时状态，避免旧路径污染当前预览和导出。

## 普通图片图层 `Layer`

主要文件：

- `app/models/layer_new.py`：当前主要实现。
- `app/models/layer.py`：旧版兼容实现。
- `app/models/layer_properties.py`：属性管理和通用操作。

`layer_new.Layer(QObject)` 使用 `LayerPropertyManager` 维护大量属性，并提供图片加载、裁剪缩放、效果、随机变换、克隆、矢量路径和序列化能力。

### 核心属性组

| 属性组 | 代表字段 |
| --- | --- |
| 基础 | `name`、`x`、`y`、`width`、`height`、`visible`、`opacity`、`locked` |
| 图片源 | `image_source`、`is_folder`、`current_image_path`、`use_original_size` |
| 适配裁剪 | `fit_mode`、`crop_direction` |
| 变换 | `rotation`、`flip_horizontal`、`flip_vertical`、`aspect_ratio_locked` |
| 随机变换 | `random_position_enabled`、`random_scale_enabled`、`random_rotation_enabled` |
| 克隆/分身 | 行列数、间距、镜像、填充模式、自定义尺寸 |
| 效果 | 圆角、描边、混合模式、颜色叠加、渐变叠加 |
| 矢量 | `vector_path_enabled`、路径点、贝塞尔节点、闭合、控制柄模式 |
| 绑定 | `bind_enabled`、`bind_group`、`bind_strategy` |

### 关键方法

| 方法 | 说明 |
| --- | --- |
| `get_random_image(force_random=False, restrict_to_bound_files=None)` | 从文件夹随机取图或加载单文件 |
| `get_image()` | 获取当前图层图像 |
| `_load_and_process_image(image_path)` | 加载源图并进入处理管线 |
| `_process_image(original_image)` | 裁剪、缩放、适配目标尺寸 |
| `_scale_and_crop(image)` | cover 模式缩放裁剪 |
| `_scale_to_fit(image)` | contain 模式缩放居中 |
| `_apply_effects(image)` / `apply_effects(image)` | 圆角、描边、叠加、矢量等效果 |
| `generate_random_transform_params()` | 生成随机变换参数 |
| `reset_random_transforms()` | 清理随机变换状态 |
| `get_effective_position()` | 获取考虑随机偏移后的真实位置 |
| `get_effective_clone_positions()` | 获取克隆实例位置 |
| `serialize()` / `deserialize(data)` | 图层序列化 |
| `duplicate(parent=None)` | 深拷贝图层 |

## 文字图层 `TextLayer`

文件：`app/models/text_layer.py`

`TextLayer(QObject)` 负责文字内容、字体、排版、描边、渐变、背景、超采样渲染和随机文案。它在批量导出中还承担“文字候选项”的角色。

### 主要能力

- 多行文字候选：`text_lines`
- 当前渲染文案：`current_text`
- 文字绑定模式：`text_binding_enabled`
- 字体扫描与 `fonts_cache.json`
- 字号、字重/斜体、对齐、行距、字距、内边距
- 自动适配文本框：`auto_fit_text_box`
- 横排/竖排：`vertical_layout`
- 描边、背景、线性/径向/角度渐变
- 超采样渲染：`_supersample_enabled`、`_supersample_scale`
- 渲染锁：`_render_lock`

### 关键方法

| 方法 | 说明 |
| --- | --- |
| `get_system_fonts()` | 获取系统字体并使用缓存 |
| `parse_text_input_to_lines(text)` | 根据绑定模式解析候选文案 |
| `randomize_text()` | 随机选择候选文案 |
| `render_text()` | 文字渲染主入口 |
| `_render_text_supersampled()` | 超采样渲染后缩回 |
| `_render_text_internal()` | 横排文字渲染 |
| `_render_text_vertical_internal(...)` | 竖排文字渲染 |
| `_update_text_box_size_if_needed()` | 自动调整文本框 |
| `_normalize_auto_fit_padding(image)` | 统一真实像素边距 |
| `set_current_text(value, emit_signals=True, force=False)` | 更新当前文字，批导可静默 |
| `serialize()` / `deserialize(data)` | 保存/恢复 |
| `duplicate(parent=None)` | 复制文字图层 |

### 维护注意

- 修改文字内容或字体相关属性后要清理 `_cached_image`。
- 批导与预览可能并发触发文字渲染，注意 `_render_lock` 和静默更新。
- 绑定模式开启时，换行会拆成候选文案；关闭时整体多行文本作为一条文案。

## 异形图层 `ShapedLayer`

主要文件：

- `app/models/shaped_layer_new.py`
- `app/models/shaped_layer.py`
- `app/models/layer_properties.py`
- `app/utils/vector_layer_geometry.py`
- `app/utils/vector_layer_effects.py`

`ShapedLayer` 继承普通图片图层，并扩展形状遮罩能力。支持矩形、直角梯形、圆形、多边形等形状，也复用普通图层的效果、变换、克隆和序列化能力。

| 组件 | 说明 |
| --- | --- |
| `ShapeType` | 形状类型枚举 |
| `ShapedLayer` | 异形图层模型 |
| `LayerPropertyManager` | 属性注册、校验、序列化 |
| `CommonLayerOperations` | 变换和克隆等通用操作 |
| `vector_layer_geometry` | 圆角、多边形、贝塞尔路径几何 |
| `vector_layer_effects` | 矢量路径填充、描边、遮罩和效果 |

关键方法：

| 方法 | 说明 |
| --- | --- |
| `get_shape_description()` | 形状说明 |
| `_apply_effects(image)` | 应用形状遮罩与图层效果 |
| `duplicate(parent=None)` | 复制异形图层 |
| `serialize()` / `deserialize()` | 保存/恢复异形参数 |

## 图层分组与图层树

主要文件：

- `app/models/layer_group.py`
- `app/utils/layer_tree.py`

运行时图层列表仍以线性列表为主，`LayerGroup` 作为非渲染节点存在，子图层通过 `parent_group_id` 建立关系。

`layer_tree.py` 提供：

| 函数 | 说明 |
| --- | --- |
| `is_layer_group(node)` | 判断是否为组 |
| `get_parent_group_id(layer)` / `set_parent_group_id(layer, group_id)` | 读写父组 |
| `is_effectively_visible(layer, nodes)` | 同时考虑自身和父组可见性 |
| `is_effectively_locked(layer, nodes)` | 同时考虑自身和父组锁定 |

## 图层绑定

文件：`app/models/binding_manager.py`

绑定用于让多个图层按同一分类/核心文件名同步取图或取文案，保证批量导出组合一致。

### `BindingGroup`

职责：

- 保存绑定图层列表。
- 分析图片文件名分类。
- 分析文字图层候选文案并构造 `text_layer://` 虚拟路径。
- 按分类获取匹配文件。
- 维护分类使用历史，减少重复组合。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `_analyze_layer_files(layer, layer_index)` | 分析图片文件或文字候选 |
| `get_available_categories()` | 获取可用分类 |
| `get_matched_files(category, avoid_duplicates=False)` | 获取分类下每层匹配文件 |

### `LayerBindingManager`

职责：

- 创建/删除绑定组。
- 添加/移除图层到绑定组。
- 全局启用/禁用绑定。
- 批导时随机化绑定图层。
- 为 `FastRenderer` 提供文件限制。
- 序列化/反序列化绑定数据。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `create_binding_group(...)` | 创建绑定组 |
| `add_layer_to_group(...)` | 添加图层到组 |
| `randomize_bound_layers(all_layers)` | 随机绑定组合并应用到图层 |
| `analyze_and_restrict_layer_files(all_layers)` | 生成文件限制 |
| `serialize()` / `deserialize(data, layers)` | 保存/恢复绑定组 |

## 尺寸匹配

文件：

- `app/models/layer_size_match_manager.py`
- `app/ui/layer_size_match_dialog.py`
- `app/utils/fast_renderer.py`

尺寸匹配用于配置“源图层透明孔位 -> 目标图层位置尺寸匹配”的关系。

`LayerSizeMatchManager` 字段：

| 字段 | 说明 |
| --- | --- |
| `global_enabled` | 全局开关 |
| `relations` | 匹配关系列表 |
| `source_layer_name` | 源图层名 |
| `target_layer_names` | 目标图层名列表 |
| `padding` | 匹配矩形内边距 |
| `one_to_many` | 一个源图多个孔位匹配多个目标 |
| `auto_rotate` | 根据孔位角度自动旋转 |

渲染时 `FastRenderer._build_size_match_overrides(...)` 会读取 active relations，检测源图层内部孔位，并为目标图层生成临时位置、尺寸和旋转覆盖参数。
