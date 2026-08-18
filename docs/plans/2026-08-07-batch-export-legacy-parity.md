# Batch Export Legacy Parity Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** 让默认 QML 批量导出流程恢复旧版 QWidget 批量导出的用户可见能力和关键行为，同时保留新版后台执行与安全策略。

**Architecture:** 以现有 `BatchExportViewModel` 作为兼容层，继续调用 `Document.batch_export()`，不复制渲染或导出实现。ViewModel 负责把旧版命名、遍历、路径日期和图层唯一使用配置转换为现有导出参数及 `document.export_settings`，QML 只负责展示和编辑这些属性。

**Tech Stack:** Python、PySide6 QObject/Property/Slot、QML、pytest。

---

### Task 1: 固化旧版关键行为

**Files:**
- Modify: `tests/test_qml_batch_export_view_model.py`

**Step 1: Write the failing tests**

- 覆盖遍历模式使用 `Document._calculate_possible_combinations()`，不受普通数量输入限制。
- 覆盖旧版命名构建器生成日期、自定义文本、图层占位符与序号格式。
- 覆盖日期目录替换、最大文件大小和指定图层唯一使用写入 `document.export_settings`。
- 覆盖从已有文档导出设置恢复配置。

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_qml_batch_export_view_model.py -q`

Expected: 新增用例因缺少属性、遍历数量仍取 `count` 等原因失败。

### Task 2: 扩展 QML 批量导出 ViewModel

**Files:**
- Modify: `app/qml/viewmodels/batch_export_view_model.py`

**Step 1: Add legacy-compatible configuration properties**

- 增加日期、日期格式、自定义文本、图层文件名、序号格式、最大体积、日期路径与唯一使用图层配置。
- 提供文件名预览、有效导出数量、遍历数量提示和可选图层列表。

**Step 2: Restore legacy export semantics**

- 遍历模式启动时计算全部组合数量，并将该数量传给 `Document.batch_export()`。
- 导出前解析路径中的合法 `YYYYMMDD` 日期段。
- 将旧版配置键写入 `document.export_settings`，供预计算、编码和项目序列化继续使用。

**Step 3: Run focused tests**

Run: `python -m pytest tests/test_qml_batch_export_view_model.py -q`

Expected: PASS。

### Task 3: 对齐 QML 配置界面并回归

**Files:**
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Step 1: Update the drawer**

- 用旧版命名构建器替代单一模板输入，并显示文件名预览。
- 增加 BMP、最大文件大小、日期路径、智能采样、唯一使用图层配置。
- 遍历模式禁用普通数量输入并显示实际组合数。
- 增加“保存到当前标签页”操作。

**Step 2: Run focused and full tests**

Run: `python -m pytest tests/test_qml_batch_export_view_model.py tests/test_qml_workbench_smoke.py tests/test_batch_export_counts.py tests/test_batch_export_dialog.py -q`

Run: `python -m pytest`

Expected: PASS；若全量测试存在与本轮无关的环境失败，记录具体失败并确保相关测试通过。

### Task 4: 保存本轮改动

**Files:**
- Stage only files changed by this task.

**Step 1: Inspect changes**

Run: `git diff -- app/qml/viewmodels/batch_export_view_model.py app/qml/Main.qml tests/test_qml_batch_export_view_model.py tests/test_qml_workbench_smoke.py docs/plans/2026-08-07-batch-export-legacy-parity.md`

**Step 2: Commit**

Run: `git add <本轮文件> && git commit -m "feat(batch): 对齐旧版批量导出功能"`

Expected: 仅提交本轮文件，不包含工作区原有的 QML 双击编辑改动。
