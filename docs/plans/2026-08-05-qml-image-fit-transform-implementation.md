# QML Image Fit And Flip Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use executing-plans to implement this plan task-by-task.

**Goal:** 在 QML 工作台中接入真实图片适配、裁剪方向和水平/垂直翻转功能。

**Architecture:** 复用 `Layer` 与 `ShapedLayer` 已有属性、缓存失效逻辑、序列化和统一渲染管线；`WorkspaceViewModel` 将稳定字符串 ID 映射为模型整数常量，QML 只负责能力感知、状态展示和命令调用。

**Tech Stack:** Python 3、PySide6 QObject/QML、Pillow、pytest。

---

### Task 1: ViewModel 图片属性合约

**Files:**
- Create: `tests/test_qml_image_fit_transform.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1: Write the failing tests**

覆盖 `selectedSupportsImageFit`、模式/方向 ID、翻转状态，以及普通图片、异形图片和文字图层的能力差异。

**Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_qml_image_fit_transform.py -v`

Expected: FAIL，缺少 ViewModel 属性和 Slot。

**Step 3: Write the minimal implementation**

新增 `_FIT_MODES`、`_CROP_DIRECTIONS` 映射，暴露只读 `Property`，并实现：

```python
@Slot(str, result=bool)
def setSelectedFitMode(self, mode_id: str) -> bool:
    ...

@Slot(str, result=bool)
def setSelectedCropDirection(self, direction_id: str) -> bool:
    ...

@Slot(bool, result=bool)
def setSelectedFlipHorizontal(self, enabled: bool) -> bool:
    ...

@Slot(bool, result=bool)
def setSelectedFlipVertical(self, enabled: bool) -> bool:
    ...
```

**Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_qml_image_fit_transform.py -v`

Expected: PASS。

### Task 2: 历史、校验与持久化

**Files:**
- Modify: `tests/test_qml_image_fit_transform.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`

**Step 1: Write the failing tests**

覆盖非法 ID、文字图层、锁定图层、同值写入、撤销/重做和 `.cmp` 保存加载。

**Step 2: Run the focused tests**

Run: `python -m pytest tests/test_qml_image_fit_transform.py -v`

Expected: 新测试在实现前失败。

**Step 3: Implement validation and atomic history**

所有命令复用 `_set_layer_attr()`，只对同时具有目标属性的图片图层生效；无效请求不得产生历史。

**Step 4: Verify focused tests**

Run: `python -m pytest tests/test_qml_image_fit_transform.py -v`

Expected: PASS。

### Task 3: 真实预览像素验证

**Files:**
- Modify: `tests/test_qml_image_fit_transform.py`

**Step 1: Create asymmetric fixtures**

用 Pillow 创建左右、上下颜色不同的图片，避免只验证属性而未验证渲染结果。

**Step 2: Verify crop and flip output**

调用 `renderPreviewNow()` 并读取 `PreviewImageProvider` 像素，确认顶部/底部裁剪和水平/垂直翻转改变正确区域。

**Step 3: Run rendering tests**

Run: `python -m pytest tests/test_qml_image_fit_transform.py -v`

Expected: PASS。

### Task 4: QML 属性面板

**Files:**
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`

**Step 1: Add source contract assertions**

断言 QML 包含适配下拉菜单、五向裁剪控件、翻转按钮和对应 ViewModel 命令。

**Step 2: Add the image layout section**

在内容源与基础变换之间加入紧凑的“图片布局”区，只在图片能力存在时显示；按钮禁用规则与现有属性面板一致。

**Step 3: Run QML smoke tests**

Run: `python -m pytest tests/test_qml_workbench_smoke.py tests/test_qml_image_fit_transform.py -v`

Expected: PASS。

### Task 5: 文档、全量验证与提交

**Files:**
- Modify: `app/qml/README.md`
- Modify: `app/qml/preview.png`
- Modify: `docs/qml-functional-parity-audit.md`

**Step 1: Update feature status**

将图片适配/裁剪和翻转标记为已接入，保持比例锁定和随机变换仍留在后续阶段。

**Step 2: Run focused and QML suites**

Run: `python -m pytest tests/test_qml_image_fit_transform.py -v`

Run: `$qmlTestFiles = Get-ChildItem tests -Filter 'test_qml*.py' | Select-Object -ExpandProperty FullName; python -m pytest $qmlTestFiles`

Expected: 全部 PASS。

**Step 3: Run broader regression tests**

Run: `python -m pytest tests/test_document_core.py tests/test_layer_serialize.py tests/test_fast_renderer_smoke.py -v`

Expected: 全部 PASS。

**Step 4: Visually verify and commit**

在 1280x760 与 1600x960 检查属性面板，更新验收截图；精确暂存本阶段文件并提交 `feat(qml): add image fit and flip controls`。

