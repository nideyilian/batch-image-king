# 02. 整体架构

## 分层视图

```mermaid
flowchart LR
    Entry["main.py / application.py"]
    UI["UI 层\nMainWindow / Canvas / Panels / Dialogs"]
    Controllers["控制器层\nDocumentController / LayerController"]
    Models["模型层\nDocument / Layer / TextLayer / Binding"]
    Services["服务层\nRenderService / ExportService / QualityPolicy"]
    Render["渲染层\nFastRenderer / DocumentRenderer"]
    Engines["合成引擎\nUnifiedAlpha / ProfessionalBlend / Photoshop"]
    Utils["工具层\nBatchPrecomputer / BatchExecutor / Cache / Preset"]
    Files["文件\n.cmp / presets / exported images"]

    Entry --> UI
    UI --> Controllers
    UI --> Models
    Controllers --> Models
    Models --> Services
    Services --> Render
    Render --> Engines
    Models --> Utils
    Utils --> Render
    Services --> Files
    Models --> Files
```

## 主要职责边界

| 层 | 代表模块 | 职责 |
| --- | --- | --- |
| 入口 | `main.py` | 流重定向、日志、依赖检查、QApplication、主题、主窗口、退出清理 |
| UI | `app/main_window.py`、`app/ui/*` | 展示与交互、菜单工具栏、画布、面板、对话框、状态反馈 |
| 控制器 | `app/controllers/*` | 把菜单/按钮动作转为文档和图层操作 |
| 模型 | `app/models/*` | 文档状态、图层状态、绑定、历史、序列化、导出协调 |
| 服务 | `app/services/*` | 渲染/导出门面、质量策略、格式归一 |
| 渲染 | `app/utils/fast_renderer.py`、`app/models/document_renderer.py` | 图层合成、缓存、预览、批量导出渲染 |
| 批导工具 | `batch_export_precomputer.py`、`optimized_batch_executor.py` | 预计算组合、生成任务、并发渲染保存、报告 |
| 资源与预设 | `preset_manager.py`、`resources/`、`presets` | 内置资源、用户预设、预设索引 |

## 主数据流

### 编辑与预览

```mermaid
flowchart TD
    A["用户操作 UI"] --> B["Controller 或 UI 面板"]
    B --> C["修改 Document / Layer 属性"]
    C --> D["发出 changed / layer_changed / document_changed"]
    D --> E["CanvasWidget 请求预览刷新"]
    E --> F["FastRenderer.render_preview()"]
    F --> G["PIL Image / QPixmap"]
    G --> H["画布 paintEvent 显示"]
```

### 单图导出

```mermaid
flowchart TD
    A["MainWindow.export_image()"] --> B["Document.export_image(file_path)"]
    B --> C["RenderService.render(mode=export)"]
    C --> D["FastRenderer.render_batch(document)"]
    D --> E["ExportService.save_image()"]
    E --> F["pyvips 可用时尝试"]
    F --> G["失败或不可用回退 Pillow"]
    E --> H["写入目标文件"]
```

### 批量导出

```mermaid
flowchart TD
    A["BatchExportDialog"] --> B["Document.batch_export(...)"]
    B --> C["_analyze_document_for_export()"]
    C --> D["BatchExportPrecomputerV2.create_export_plan()"]
    D --> E["LayerCombination / ExportTask"]
    E --> F["OptimizedBatchExecutor"]
    F --> G["worker 文档快照"]
    G --> H["FastRenderer.render_batch()"]
    H --> I["ExportService / Pillow / pyvips"]
    I --> J["ExportReport / 进度 / 诊断"]
```

## 关键依赖关系

```mermaid
flowchart TD
    Main["main.py"] --> MainWindow["app/main_window.py"]
    MainWindow --> DocumentManager["models/document_manager.py"]
    MainWindow --> DocumentController["controllers/document_controller.py"]
    MainWindow --> LayerController["controllers/layer_controller.py"]
    MainWindow --> Canvas["ui/canvas.py"]
    MainWindow --> LayerPanel["ui/layer_panel.py"]
    MainWindow --> LayerProperties["ui/layer_properties.py"]

    DocumentController --> Document["models/document.py"]
    LayerController --> Document
    Document --> Layer["models/layer_new.py"]
    Document --> TextLayer["models/text_layer.py"]
    Document --> ShapedLayer["models/shaped_layer_new.py"]
    Document --> Serializer["models/document_serializer.py"]
    Document --> Binding["models/binding_manager.py"]
    Document --> SizeMatch["models/layer_size_match_manager.py"]
    Document --> BatchCoordinator["models/batch_export_coordinator.py"]

    Canvas --> FastRenderer["utils/fast_renderer.py"]
    Document --> RenderService["services/render_service.py"]
    Document --> ExportService["services/export_service.py"]
    RenderService --> FastRenderer
    ExportService --> RenderQuality["services/render_quality.py"]

    Document --> BatchExecutor["utils/optimized_batch_executor.py"]
    BatchExecutor --> Precomputer["utils/batch_export_precomputer.py"]
    BatchExecutor --> FastRenderer
    BatchExecutor --> ExportService
    FastRenderer --> Alpha["utils/unified_alpha_compositor.py"]
    FastRenderer --> Engines["engines/*"]
```

## 状态同步与信号

`Document` 是状态中心。常用信号包括：

| 信号 | 作用 |
| --- | --- |
| `document_changed` | 文档内容或保存状态变化，驱动标题、保存状态、画布刷新 |
| `layer_changed` / `layers_changed` | 图层列表或图层内容变化 |
| `layer_updated(int)` | 单个图层更新 |
| `layer_selected(int)` | 单选图层变化 |
| `layers_selection_changed(list)` | 多选图层变化 |
| `history_changed` | 撤销/重做状态变化 |
| `export_progress_updated(int)` | 批量导出进度 |
| `file_exported(str)` | 单个导出文件完成 |
| `export_stage_updated(str)` | 批量导出阶段文案 |

UI 面板修改模型属性后通常需要：

1. 清理相关缓存。
2. 标记文档修改。
3. 保存历史快照。
4. 发出对应信号。
5. 请求画布或面板刷新。

## 重要架构原则

- `Document` 当前仍是中心化模型，许多新旧入口都经过它。
- 新功能优先复用 `DocumentSerializer`、`FastRenderer`、`ExportService`、`PresetManager` 等已有接口。
- 批量导出阶段应使用预计算结果驱动渲染，不应在执行阶段引入新的不可控随机。
- 渲染缓存必须区分预览模式和批量模式。
