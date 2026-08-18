# Rich Text Selection Editing Implementation Plan

**Goal:** 在画布文字编辑状态中支持 Photoshop 式字符选区，直接修改局部颜色和字号，并保证撤销、保存、预览与导出一致。

**Architecture:** 使用 Qt `QTextDocument` 作为编辑期富文本适配层，在 QML `TextEdit.RichText` 与现有 `text_color_ranges` / `font_size_ranges` 之间双向转换。HTML 不进入 `.cmp`，提交时仍写回现有字符区间；QML 选区索引按 UTF-16 与 Python 字符索引显式转换，避免 emoji 等代理对破坏范围。

**Tech Stack:** Python 3.12、PySide6 / Qt Quick、QTextDocument、Pillow、pytest。

---

### Task 1: 富文本区间适配器

**Files:**
- Create: `app/utils/text_rich_format.py`
- Create: `tests/test_text_rich_format.py`

**Step 1:** 编写失败测试，覆盖颜色与字号组合、换行、重叠区间、emoji UTF-16 索引和 HTML 往返。

**Step 2:** 运行 `python -m pytest tests/test_text_rich_format.py -q`，确认适配器尚不存在。

**Step 3:** 使用 `QTextDocument` / `QTextCursor` 实现 `build_editor_html()`、`parse_editor_html()`、`apply_editor_style()` 与 `inspect_editor_selection()`，不手写 HTML 解析。

**Step 4:** 再次运行测试，确认模型区间往返不丢失。

### Task 2: ViewModel 编辑会话

**Files:**
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/models/text_layer_serialize.py`
- Create: `tests/test_qml_rich_text_selection.py`

**Step 1:** 增加失败测试，断言 ViewModel 能发布编辑器 HTML、检查选区混合状态、应用临时颜色/字号，并在提交时写回纯文本与区间。

**Step 2:** 为文字模型增加一次性替换局部样式区间的公开接口，统一缓存失效和信号通知。

**Step 3:** 增加编辑草稿、富文本提交与自动提交逻辑；取消编辑不修改模型，切换图层时提交最后草稿。

**Step 4:** 运行 ViewModel 与模型测试，检查撤销记录只有一次完整编辑操作。

### Task 3: 画布字符选区交互

**Files:**
- Modify: `app/qml/Main.qml`
- Create: `tests/test_qml_rich_text_selection_visual.py`
- Create: `tests/helpers/qml_rich_text_selection_probe.py`
- Verify: `tests/test_qml_canvas_double_click_edit.py`
- Verify: `tests/test_qml_workbench_smoke.py`

**Step 1:** 增加 QML 契约测试，覆盖 `TextEdit.RichText`、格式化提交、选区工具条、颜色弹窗回调、完成和取消命令。

**Step 2:** 将画布编辑器改为富文本显示，失焦时保持编辑状态；画布外点击提交，颜色弹窗和属性操作不丢选区。

**Step 3:** 增加紧凑选区工具条：选区计数、颜色色块、字号输入、清除局部样式、完成与取消。混合值明确显示“混合”，无字符选区时禁用局部样式命令。

**Step 4:** 让颜色与字号操作返回新的编辑期 HTML，保持选区和光标，不提前修改项目模型。

### Task 4: 回归与交付

**Files:**
- Verify: `app/models/text_layer_render.py`
- Verify: `app/utils/fast_renderer.py`
- Verify: `app/utils/fast_renderer_surface.py`
- Verify: `app/qml/Main.qml`

**Step 1:** 运行相关测试及 `python -m py_compile`。

**Step 2:** 离屏加载 `Main.qml`，验证 1280x760 与 1600x960 下工具条不遮挡文字或越界，并确认 50%-300% 行距在编辑器中不被错误截断。

**Step 3:** 渲染包含混合颜色、混合字号和 emoji 的文字图层，比较序列化前后像素与区间。

**Step 4:** 运行 `git diff --check`，执行反方复核，只暂存并提交本轮新增改动。
