# 08. 依赖与维护指南

## 依赖矩阵

| 依赖 | 版本要求 | 主要使用位置 |
| --- | --- | --- |
| `PySide6` | `>=6.9.0` | `main.py`、`app/main_window.py`、`app/ui/*`、Qt 信号槽 |
| `Pillow` | `>=11.1.0` | 图层加载、文字渲染、合成输出、导出编码 |
| `numpy` | `>=2.2.0` | Alpha 合成、混合模式、遮罩处理 |
| `scipy` | `>=1.15.0` | 高级图像算法 |
| `opencv-python` | `>=4.12.0` | 高级图像处理、质量/几何相关逻辑 |
| `psutil` | `>=7.0.0` | 内存保护、性能监控 |
| `PyInstaller` | `>=6.14.1` | 打包 |

可选能力：

- `pyvips`：`app/utils/vips_export_engine.py` 会尝试使用，不可用时回退。
- GPU 相关模块：`app/utils/gpu_renderer.py`、`app/utils/gpu_render_integration.py`，当前仍偏可选/尝试路径。

## 缓存、线程和内存

主要模块：

| 模块 | 说明 |
| --- | --- |
| `app/utils/intelligent_render_cache.py` | 文档级智能渲染缓存 |
| `app/utils/advanced_image_cache.py` | 高级图像缓存 |
| `app/utils/intelligent_memory_manager.py` | 内存压力检测、图像追踪、强制优化 |
| `app/utils/intelligent_thread_pool_manager.py` | 智能线程池 |
| `app/utils/advanced_task_queue.py` | 优先级任务队列 |
| `app/utils/cache_optimization_manager.py` | 缓存监控和优化建议 |
| `app/utils/performance_optimizer.py` | 性能装饰器和批处理优化 |
| `app/utils/thread_pool_config.py` | 线程池配置 |

`main.py` 退出时会尝试清理：

- 智能线程池。
- 高级图像缓存。
- 任务队列。

新增全局资源时也应接入退出清理。

## 高风险修改区域

### 渲染/合成

同时检查：

- `FastRenderer.render_preview()`
- `FastRenderer.render_batch()`
- `DocumentRenderer.render_document()`
- `Document.render_composition()` legacy 回退
- `UnifiedAlphaCompositor`
- `ExportService`

重点验证：

- 半透明 PNG 是否出现黑边/白边。
- 混合模式预览和导出是否一致。
- 文字、异形、矢量、克隆、尺寸匹配是否仍正确。

### 图层属性

同步检查：

- `LayerPropertyManager` 默认值和校验。
- 图层自身 `serialize()` / `deserialize()`。
- `DocumentSerializer.serialize_layer()` 兜底字段。
- 属性面板 UI 读写。
- 历史记录保存。
- 缓存失效。
- `changed`、`layer_changed`、`document_changed` 信号。

### 文字图层

重点检查：

- 字体扫描与 `fonts_cache.json`。
- 自动文本框。
- 竖排。
- 换行绑定模式。
- 超采样临时参数是否还原。
- 批导和预览并发下 `_render_lock` 是否仍保护正确。

### 批量导出

重点检查：

- 预计算是否把随机图片、随机文字、随机变换固化到 `LayerCombination`。
- 绑定组合是否按分类保持一致。
- 非绑定图层是否仍能随机且不过度重复。
- 文件名模板是否使用实际随机选中的文件名。
- 批量模式是否绕开会导致重复的预览缓存。
- 取消、连续失败、内存保护、停滞超时是否生效。
- 导出报告和 UI 诊断是否仍能展示。

### 预设/文档格式

重点检查：

- `.cmp` pickle 版本兼容。
- 旧项目缺失字段时是否有默认值。
- 多标签页预设是否恢复标签名、视图设置、导出设置。
- 绑定组和尺寸匹配配置是否正确恢复。

## 快速排查入口

| 问题 | 优先查看 |
| --- | --- |
| 程序启动失败 | `main.py`、`app/utils/stream_redirector.py`、日志目录 |
| 标签页/窗口状态异常 | `app/main_window.py`、`DocumentManager` |
| 画布不刷新 | `CanvasWidget`、`Document` 信号、`FastRenderer.invalidate_cache()` |
| 预览和导出不一致 | `FastRenderer`、`ExportService`、`UnifiedAlphaCompositor` |
| 批导重复图 | `BatchExportPrecomputerV2`、`OptimizedBatchExecutor`、`FastRenderer` 批量缓存 |
| 绑定不一致 | `BindingGroup.get_matched_files()`、`LayerBindingManager.randomize_bound_layers()` |
| 文字渲染错位 | `TextLayer._render_text_internal()`、字体 bbox、自动适配 |
| PNG 边缘异常 | `rgba_resampler.py`、`unified_alpha_compositor.py`、图层效果管线 |
| `.cmp` 加载失败 | `Document.load_document()`、`DocumentSerializer.deserialize_layer()` |
| 预设不显示或打不开 | `PresetManager`、用户预设目录、`presets_index.json` |

## 常用命令

```powershell
# 查调用链
rg -n "batch_export|render_batch|serialize_layer" app

# 运行应用
python main.py

# 运行现有回归测试
python -m unittest tests.test_batch_export_dialog

# 打包
python build.py
```

## 提交与工作区注意

- 当前仓库经常存在未提交或生成文件，提交前先看 `git status --short`。
- 只暂存本轮修改的文件。
- 不要误提交 `build/`、`dist/`、`__pycache__/`。
- 不要回滚用户已有未提交改动。
- 对核心功能的改动结束前应至少保留一个本地 git 提交作为回退点。
