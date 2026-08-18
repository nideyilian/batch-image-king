# 预设商店化改造实施计划

**Goal:** 把当前预设列表升级为本地应用商店式预设中心，支持卡片瀑布流、缩略图、进入编辑、运行预设和常用管理操作。

**Architecture:** 预设数据仍由 `PresetManager` 管理，新增轻量摘要字段和使用记录。UI 新增独立 `PresetStoreDialog`，运行预设通过 `PresetRunDialog` 确认后复用现有 `BatchExportDialog.do_export()`，缩略图由独立服务按需生成并缓存。

**Tech Stack:** Python, PySide6, Pillow, existing Document/FastRenderer/BatchExport pipeline.

---

## Tasks

1. 扩展 `PresetManager`：补齐可选元数据、新增摘要、复制、使用记录接口。
2. 新增预设文档加载助手，供缩略图、进入编辑和运行预设复用。
3. 新增缩略图服务，按预设文件修改时间缓存正方形卡片图。
4. 新增运行确认对话框，确认输出目录后复用现有批量导出链路。
5. 新增预设中心对话框、卡片组件和瀑布流布局。
6. 重构 `MainWindow` 的加载/管理预设入口，统一打开预设中心。
7. 验证语法导入、旧索引兼容、预设加载和运行路径。
