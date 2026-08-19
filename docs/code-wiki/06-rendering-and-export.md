# 06. 渲染与导出

## 渲染入口概览

| 场景 | 主要入口 | 说明 |
| --- | --- | --- |
| 画布预览 | `CanvasWidget` -> `FastRenderer.render_preview()` | 支持缓存、异步、低质量交互预览 |
| 单图导出 | `Document.export_image()` -> `RenderService` -> `FastRenderer.render_batch()` | 导出质量策略和格式处理由服务层负责 |
| 批量导出 | `Document.batch_export()` -> `OptimizedBatchExportManager` | 预计算组合后并发渲染保存 |
| 兼容渲染 | `DocumentRenderer.render_document()` | 通用/旧路径，部分回退仍使用 |

## `FastRenderer`

文件：`app/utils/fast_renderer.py`

`FastRenderer` 是当前高性能渲染核心之一，负责预览、导出、批量渲染、图层 surface 缓存、交互式增量预览、尺寸匹配覆盖、内存管理和合成。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `render_preview(document, force_refresh=False, interactive_low_quality=False)` | 预览渲染入口 |
| `render_preview_incremental(...)` | 增量预览 |
| `render_preview_live(...)` | 实时交互预览 |
| `render_batch(document)` | 导出/批量模式渲染入口 |
| `_fast_render(...)` | 核心渲染流程 |
| `get_layer_surface_cached(...)` | 获取图层 surface 缓存 |
| `_get_layer_image(layer, document, was_just_loaded=False)` | 获取图层图像 |
| `_build_size_match_overrides(...)` | 构造尺寸匹配临时覆盖 |
| `_fast_composite(...)` | 快速合成 |
| `_standard_composite_logic(...)` | 标准合成逻辑 |
| `_apply_opacity(...)` | 应用图层透明度 |
| `_apply_blend_mode(...)` | 应用混合模式 |
| `invalidate_cache()` / `invalidate_document_cache(document)` | 清理缓存 |
| `reset_batch_metrics()` / `get_batch_metrics()` | 批导指标 |
| `get_global_fast_renderer()` | 全局 renderer 实例 |

### 缓存边界

`FastRenderer` 明确区分：

- 预览缓存：提升交互性能。
- 图层 surface 缓存：按图层状态、尺寸、效果、文本状态等组成 key。
- 交互式缓存：拖拽/缩放/旋转时减少重绘成本。
- 批量导出会话缓存：受控复用原图/处理图，但不能导致随机组合重复。

重要环境变量：

| 变量 | 作用 |
| --- | --- |
| `BTPW_FAST_RENDERER_DEBUG=1` | 开启快速渲染器调试输出 |
| `BTPW_BATCH_RENDER_VERBOSE=1` | 开启批量渲染高频日志 |

## 合成与混合

主要文件：

- `app/utils/unified_alpha_compositor.py`
- `app/models/document_blend.py`
- `app/engines/professional_blends.py`
- `app/engines/photoshop_compositor.py`
- `app/engines/alpha_compositor.py`
- `app/engines/advanced_compositor_manager.py`
- `app/engines/quality_engine.py`

关键组件：

| 组件 | 说明 |
| --- | --- |
| `UnifiedAlphaCompositor` | sRGB Alpha 合成、常见混合模式、PNG 边缘优化 |
| `DocumentBlend.Blender` | 旧版混合模式兼容 |
| `ProfessionalBlender` | Photoshop 风格混合模式 |
| `AdvancedCompositorManager` | 聚合多种合成引擎 |
| `QualityEngine` | 缩放和增强质量策略 |

维护原则：

- 普通 alpha 合成应保持预览、单图导出、批量导出一致。
- 改混合模式时同时检查 `FastRenderer`、`DocumentRenderer`、`Document.render_composition()` 和 `unified_alpha_compositor`。
- 半透明 PNG 边缘问题通常要同时看预乘 Alpha、缩放、合成和导出编码。

## 服务层

### `RenderService`

文件：`app/services/render_service.py`

`RenderService.render(RenderRequest)` 是渲染服务门面，当前主要调用 `FastRenderer`。`RenderResult.ok()` 用于判断渲染是否成功。

### `ExportService`

文件：`app/services/export_service.py`

`ExportService.save_image(image, ExportJob)` 负责写盘：

- 输出格式归一化。
- JPEG 透明背景合成。
- PNG 保留 Alpha。
- 质量策略和压缩参数。
- 最大文件大小限制。
- 可选 pyvips 后端与 Pillow 回退。

相关数据类：

| 类 | 说明 |
| --- | --- |
| `ExportJob` | 保存路径、格式、质量策略、大小限制等参数 |
| `ExportReport` | 保存结果、耗时、字节数、后端等信息 |
| `QualityPolicy` | 质量策略配置 |

## 批量导出 V2

主入口：

- UI：`BatchExportDialog.start_export()`
- 模型：`Document.batch_export(...)`
- 执行：`export_batch_with_precomputation_v2(...)`

### 预计算

文件：`app/utils/batch_export_precomputer.py`

关键数据结构：

| 类 | 说明 |
| --- | --- |
| `LayerCombination` | 一张导出图对应的图层状态、随机参数、hash |
| `ExportTask` | 组合、文件名、路径、序号 |
| `PrecomputedExportPlan` | 批导任务计划、统计、诊断 |
| `BatchExportPrecomputerV2` | 当前主预计算器 |

`BatchExportPrecomputerV2` 职责：

- 分析文档是标准模式还是绑定模式。
- 初始化每个图层的图片池/文字候选。
- 处理唯一使用限制。
- 估算组合空间和尝试上限。
- 固化随机图片、随机文案、随机变换、图层参数。
- 生成文件名和导出任务。
- 输出诊断数据。

关键方法：

| 方法 | 说明 |
| --- | --- |
| `analyze_document_with_context(...)` | 分析文档并初始化上下文 |
| `create_export_plan(directory, count, filename_template, ...)` | 生成完整导出计划 |
| `_plan_combinations(...)` | 规划组合 |
| `_build_export_tasks(...)` | 生成导出任务 |
| `_generate_binding_combinations_v2(...)` | 绑定模式组合 |
| `_generate_standard_combinations_v2(...)` | 标准随机模式组合 |
| `_process_filename_template(...)` | 文件名模板处理，支持 `{layer:N}` |
| `_dedup_should_skip(...)` / `_dedup_record(...)` | 去重判断与记录 |
| `_build_combination_runtime_metadata(...)` | 固化随机变换和参数 |

### 执行器

文件：`app/utils/optimized_batch_executor.py`

关键类：

| 类/函数 | 说明 |
| --- | --- |
| `OptimizedBatchExecutor` | 并发渲染、保存、内存保护、取消、trace、报告 |
| `OptimizedBatchExportManager` | V2 批导总控 |
| `export_batch_with_precomputation_v2(document, document_analysis, **kwargs)` | 外部入口 |

执行器职责：

- 准备 worker 文档快照。
- 应用预计算好的图层状态、文本状态、随机变换、图层参数。
- 调用 `FastRenderer.render_batch()`。
- 使用 `ExportService` 或 Pillow 保存。
- 控制并发数和内存预算。
- 记录导出 trace、性能统计和失败原因。
- 支持取消、连续失败保护、停滞保护。

## 文件名模板

文件：`app/utils/filename_template_processor.py`

常用占位符：

| 占位符 | 说明 |
| --- | --- |
| `{number}` / `{number:04d}` | 序号 |
| `{index}` | 序号兼容字段 |
| `{count}` | 总数 |
| `{layer}` | 主要图层实际文件名 |
| `{layers}` | 多个图层文件名组合 |
| `{layer:N}` | 指定文档图层索引的实际文件名 |
| `{combo}` | 组合 hash |

关键方法：

| 方法 | 说明 |
| --- | --- |
| `process_template(template, context)` | 处理模板 |
| `create_context(...)` | 构造上下文 |
| `validate_template(template)` | 校验模板 |
| `_extract_layer_name(layer_info)` | 从路径、dict 或对象提取实际文件名 |
| `_extract_main_filename(filename)` | 移除序号等噪声 |
| `_clean_filename(filename)` | 清理非法字符 |

## 多标签批量导出

文件：`app/ui/multi_tab_export_dialog.py`

`MultiTabExportDialog` 会为每个选中标签页构造独立 request，再通过 `ExportWorker(QRunnable)` 调用 `BatchExportDialog.execute_export_request(...)`。这样后台线程不需要读取 QWidget 状态。

## 修改批导时的重点

- 预计算阶段是否已经固化所有随机状态。
- 绑定组是否保持同一分类/同一组合。
- 非绑定图层是否仍能随机且不过度重复。
- 文件名模板中的指定图层是否使用真实随机选中的文件名。
- 批量模式是否避开预览缓存。
- 内存保护、取消、连续失败、停滞超时是否仍生效。
- `_last_export_report`、`_last_export_perf_stats` 是否仍能供 UI 诊断展示。
