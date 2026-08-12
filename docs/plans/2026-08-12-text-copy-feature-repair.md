# 文案相关功能完整修复实施方案

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**目标：** 修复批图王文案功能中字体解析、字体目录、局部颜色、局部字号、字符选区、双击编辑、绑定模式和旧版编辑器之间的不一致，确保编辑器、预览、单图导出和批量导出使用同一份文案与样式数据。

**架构：** 保留 `.cmp` 现有 pickle 数据格式和 `TextLayer` 的 `font_family`、`font_face`、`font_style`、`text_color_ranges`、`font_size_ranges` 字段。新增统一的字体解析服务和文本编辑变更适配层：字体家族在文档中保存跨平台名称，运行时由 Qt 与 Pillow 共同使用同一解析结果；局部样式始终使用 Python 字符索引的半开区间，所有 QML UTF-16 选区在进入模型前显式转换。QML 画布编辑和旧版 QWidget 编辑器都采用“草稿会话 + 一次性提交 + 一次历史记录”的方式。

**技术栈：** Python 3.12、PySide6、Qt Quick/QML、QTextDocument、Pillow、fontTools、pytest、pickle 兼容序列化。

---

## 1. 修复范围

| 编号 | 优先级 | 问题 | 当前证据 | 修复后行为 |
|---|---|---|---|---|
| T1 | P1 | `sans-serif` 在 Qt 中解析为 Tahoma，在 Pillow 中解析为微软雅黑 | [text_layer_font.py](../../app/models/text_layer_font.py) 与 [Main.qml](../../app/qml/Main.qml) 使用了不同解析路径；本机 `QFontInfo` 实测为 Tahoma | Qt 编辑器、Pillow 预览和导出统一使用同一真实字体家族/字重 |
| T2 | P1 | 侧栏改文案后局部颜色和字号不随字符移动 | [workspace_view_model.py](../../app/qml/viewmodels/workspace_view_model.py) 直接替换文本，仅按新长度裁剪区间 | 插入、删除、替换后，未修改字符的局部样式按字符内容位置迁移 |
| T3 | P1 | 表情等非 BMP 字符导致侧栏选区错位 | Qt 使用 UTF-16 位置，侧栏槽直接按 Python 索引处理 | 所有 QML 选区先转 Python 索引，`A😀BC` 选中 `B` 必须只影响 `B` |
| T4 | P2 | 旧版 QWidget 编辑器取消后文字仍被修改 | [canvas_text_editor.py](../../app/ui/canvas_text_editor.py) 实时写入图层，取消没有恢复快照 | Esc/取消完全恢复文字、局部颜色、局部字号、自动适配状态 |
| T5 | P2 | 双击编辑不支持竖排，固定文本框编辑时布局跳位 | [Main.qml](../../app/qml/Main.qml) 始终使用横排 `TextEdit.Wrap`，没有垂直对齐和竖排策略 | 横排支持画布原地编辑；竖排双击自动聚焦右侧文字编辑器，不产生错误的横排覆盖层 |
| T6 | P2 | 切换绑定模式只裁剪局部颜色，不裁剪局部字号 | [text_layer.py](../../app/models/text_layer.py) 未调用字号区间裁剪 | 绑定模式切换时两类局部样式都按明确策略清理或迁移，不留潜在越界区间 |
| T7 | P2 | 字体目录只显示中文分类，Arial 等当前字体无法重新选择 | [workspace_view_model.py](../../app/qml/viewmodels/workspace_view_model.py) 只加载 `chinese` 分类 | 目录覆盖所有可用家族，当前项目字体即使不在首选分类也始终可见 |
| T8 | P2 | 缺失字体静默回退，用户不知道布局已变化 | [text_layer_font.py](../../app/models/text_layer_font.py) 找不到字体后静默尝试中文字体 | 保留原始字体名，使用可追踪的运行时回退，并在属性面板/状态栏显示缺失提示 |
| T9 | P3 | 侧栏有局部颜色入口但没有局部字号入口，旧测试被删除 | [Main.qml](../../app/qml/Main.qml) 与已删除的字号范围测试 | 侧栏和画布工具条均提供局部字号；测试覆盖恢复且不依赖源码字符串断言 |

本方案只修复文案相关行为，不改变图层绑定、批量导出组合算法、普通图片图层或 `.cmp` 文件整体格式。

## 2. 必须保持的数据契约

### 2.1 字符索引

- 模型内部和 `.cmp` 中所有区间统一为 Python 字符索引，使用半开区间 `[start, end)`。
- QML `TextEdit.selectionStart`、`selectionEnd` 是 UTF-16 code unit 位置，不得直接传给模型范围 API。
- `app/utils/text_rich_format.py` 中的 `python_index_to_qt()`、`qt_index_to_python()` 作为唯一转换实现；侧栏和画布都调用同一适配函数。
- 代理对中间位置必须归一化到完整字符边界，不能产生半个表情的区间。

### 2.2 字体字段

- `font_family` 保存文档选择的家族名。新建文案默认保存 `sans-serif`，以保证跨平台语义稳定。
- `font_face` 保存扫描到的真实 face 名称；旧项目缺失该字段时使用空字符串。
- `font_style` 继续保存 `NORMAL`、`BOLD`、`ITALIC`、`BOLD_ITALIC`，作为旧项目和无真实 face 时的兼容回退。
- 运行时增加统一解析结果，不把解析后的平台字体名写回 `font_family`，避免 Windows 项目在其他平台失去通用性。
- Qt 编辑器和 Pillow 渲染必须接收同一个“解析后的家族 + face/weight/italic”结果。

### 2.3 局部样式字段

```text
text_color_ranges = [{"start": 0, "end": 3, "color": (r, g, b, a)}]
font_size_ranges  = [{"start": 0, "end": 3, "size": 60}]
```

- 区间必须被裁剪到当前文本的 Python 长度。
- 相邻且值相同的区间必须合并；空区间必须丢弃。
- 等于全局字号/全局颜色的局部样式应被清除，避免产生无意义范围。
- 绑定模式下局部样式不参与随机文案渲染。

### 2.4 编辑会话

每个编辑入口都必须有以下状态：

```text
original_text_lines
original_current_text
original_text_color_ranges
original_font_size_ranges
original_auto_fit_text_box
draft_html_or_plain_text
```

编辑过程中只修改草稿；提交时一次性写入模型、失效缓存、标记文档修改并保存一条历史记录；取消时恢复原快照且不新增历史记录。

## 3. 总体实施顺序

1. 先建立索引、字体和样式数据契约，并补失败测试。
2. 修复模型和 ViewModel，再接入 QML，避免先改界面导致数据错位。
3. 修复旧版 QWidget 入口，使新旧入口共享同一文本编辑提交逻辑。
4. 添加真实 QML 鼠标/键盘集成测试和离屏视觉探针。
5. 运行全量测试、人工验收和旧 `.cmp` 兼容性验证后再合并。

建议每个任务独立提交，提交信息使用：

```text
fix(text): unify font resolution
fix(text): preserve inline styles across edits
fix(text): normalize qml selection indices
fix(text): make inline editor cancelable
test(text): cover qml editing and legacy compatibility
```

## 4. 分任务修复计划

### Task 0：建立基线和测试夹具

**文件：**

- Test: `tests/test_text_layer_core.py`
- Test: `tests/test_qml_text_typography.py`
- Test: `tests/test_qml_rich_text_selection.py`
- Test: `tests/test_qml_canvas_double_click_edit.py`
- Create: `tests/helpers/text_edit_fixtures.py`

**步骤：**

1. 固定当前基线：

   ```powershell
   python -m pytest -q
   ```

   预期当前工作树为 `482 passed`；若基线变化，先记录，不把既存失败混入本次修复。

2. 创建统一夹具，能构造包含 `A😀BC`、换行、局部颜色和局部字号的非绑定文字图层。
3. 添加以下失败测试：侧栏插入字符后的样式迁移、UTF-16 选区、绑定模式字号清理、旧版取消恢复、缺失字体提示。
4. 单独运行新测试，确认它们确实因当前缺陷失败。

**完成标准：** 测试失败原因对应本方案的问题，而不是导入错误、Qt 环境错误或随机字体目录差异。

### Task 1：统一字体默认值和解析器

**文件：**

- Modify: `app/constants.py`
- Modify: `app/models/text_layer_font.py`
- Modify: `app/models/text_layer.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/Main.qml`
- Modify: `app/ui/add_text_layer_dialog_simple.py`
- Modify: `app/ui/canvas_text_editor.py`
- Modify: `app/ui/integrated_text_panel_handlers.py`
- Modify: `app/ui/integrated_text_panel_content.py`
- Modify: `app/ui/text_layer_properties.py`
- Test: `tests/test_text_layer_core.py`
- Test: `tests/test_qml_text_typography.py`

**实现要求：**

1. 在 `app/constants.py` 增加单一默认值，例如 `DEFAULT_TEXT_FONT_FAMILY = "sans-serif"`；所有新建、重置和兼容入口删除散落的默认字体字符串。
2. 在 `TextLayerFontMixin` 提供统一解析接口：

   ```python
   resolve_font_family(font_family) -> {
       "requested_family": str,
       "resolved_family": str,
       "available": bool,
       "fallback_family": str | None,
   }
   ```

3. `sans-serif` 在 Windows/macOS/Linux 分别解析到现有平台首选中文无衬线字体；解析规则必须同时供 Pillow 和 ViewModel 使用。
4. 增加 `resolvedTextFontFamily`、`selectedTextFontAvailable`、`selectedTextFontWarning` 等只读 ViewModel 属性。QML 编辑器使用解析后的家族，不直接使用 `sans-serif`。
5. `build_editor_html()` 的 `font_family` 参数传解析后的家族；Pillow `_get_font_object()` 使用同一解析结果和 face。
6. 缺失字体时：
   - 文档仍保存原始 `font_family`/`font_face`；
   - 渲染使用确定性回退；
   - 属性面板显示“字体不可用，当前使用回退字体”；
   - 用户选择新字体后清除警告。

**测试：**

```powershell
python -m pytest tests/test_text_layer_core.py tests/test_qml_text_typography.py -q
```

**完成标准：** 同一文字图层在 Qt 编辑器和 Pillow 测量中的字体家族、字重、斜体状态一致；新建对话框、QML、旧版 QWidget 面板和重置样式使用同一默认值。

### Task 2：补全字体目录和真实 face 选择

**文件：**

- Modify: `app/models/text_layer_font.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/components/FontSelectBox.qml`
- Modify: `app/qml/Main.qml`
- Test: `tests/test_font_categorization.py`
- Test: `tests/test_qml_text_typography.py`
- Test: `tests/test_qml_workbench_smoke.py`

**实现要求：**

1. 字体扫描保留所有家族，不再只发布 `chinese` 分类；可以按中文、英文字体、等宽、装饰字体排序，但当前项目家族必须置顶或至少可见。
2. 当前家族不在扫描结果时补充一个“项目字体（不可用）”项，不能让 `FontSelectBox` 默认为列表首项。
3. 当前 `font_face` 不在该家族 face 列表时显示为“原样式（不可用）”，不能静默提交空 face。
4. 手动输入未知字体时先校验字体目录；未知值不直接写入模型，显示错误状态并保留原选择。
5. 对真实 face 的选择仍写入 `font_face`，并将兼容 `font_style` 设为 `NORMAL`，防止 Pillow 再叠加合成粗体。
6. B/I/字重操作选择最接近的真实 face；没有真实 face 时才使用 `font_style` 合成。
7. 增加字体目录缓存版本校验，旧缓存缺 `faces` 时重新扫描，不使用半成品目录。

**完成标准：** 加载使用 Arial、英文装饰字体或缺失字体的项目时，属性面板仍显示当前值；用户能明确区分真实 face、合成样式和不可用字体。

### Task 3：实现文本修改后的局部样式迁移

**文件：**

- Modify: `app/models/text_layer_serialize.py`
- Create or modify: `app/utils/text_style_ranges.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/ui/integrated_text_panel_handlers.py`
- Test: `tests/test_text_layer_range_colors.py`
- Test: `tests/test_text_layer_mixed_font_size.py`
- Test: `tests/test_qml_rich_text_selection.py`
- Test: `tests/test_text_style_ranges.py`

**实现要求：**

1. 新增纯逻辑函数 `remap_text_style_ranges(old_text, new_text, color_ranges, font_size_ranges)`。
2. 使用 `difflib.SequenceMatcher` 或等价的确定性 diff，将旧文本字符映射到新文本字符；不能以“只裁剪到新长度”代替迁移。
3. 样式迁移策略固定如下：
   - `equal`：原字符样式原位保留；
   - `delete`：删除对应字符的样式；
   - `replace`：保留未被替换的公共前缀/后缀，替换内容使用替换起点左侧字符样式，左侧不存在时使用右侧样式，再不存在时使用全局样式；
   - `insert`：插入内容继承插入点左侧字符样式，文本开头插入时继承右侧样式；两侧都没有时使用全局样式。
4. 颜色和字号必须使用同一字符映射，不能出现颜色已迁移而字号未迁移。
5. `setTextContentForLayer()`、旧版面板 `_apply_text_content()` 和任何批量改单文案入口都调用同一函数，并在一次 `_change_text_layer()` 中保存一次历史。
6. 提交后重新执行区间合并、裁剪和缓存失效。

**必须覆盖的例子：**

```text
ABCD，B 为红色/60px，改为 XABCD -> B 仍为红色/60px
ABCD，B 为红色，删除 A -> B 仍为红色且区间变为 [0, 1)
A😀BC，B 变色 -> Python 区间必须是 [2, 3)
多行文本在换行前插入字符 -> 后续行样式索引正确迁移
```

**完成标准：** 侧栏纯文本编辑、旧版面板编辑和画布富文本提交对同一组文本变更产生相同的样式区间。

### Task 4：统一 QML UTF-16 选区处理

**文件：**

- Modify: `app/utils/text_rich_format.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_rich_text_selection.py`
- Test: `tests/test_qml_text_appearance.py`

**实现要求：**

1. 保留模型 API 的 Python 索引语义；新增明确命名的 Qt 入口，例如 `setSelectedTextColorRangeQt(start_qt, end_qt, value)`，避免调用方误用。
2. 侧栏 `ContentTextEditor` 的颜色、字号、清除样式动作全部调用 Qt 入口；入口内部读取当前编辑文本并调用 `qt_index_to_python()`。
3. 画布富文本路径继续使用 `apply_editor_style()` 和 `parse_editor_html()`，但所有选区检查统一走同一转换函数。
4. 选区为空、范围反向、落在代理对中间、超过文本长度时返回明确失败，不修改模型。
5. QML 工具条显示混合颜色/混合字号时，修改操作必须保持原 UTF-16 选区。

**测试命令：**

```powershell
python -m pytest tests/test_qml_rich_text_selection.py tests/test_qml_text_appearance.py -q
```

**完成标准：** `A😀BC`、中文、换行和组合局部样式的选区操作均只影响用户选中的字符。

### Task 5：修复绑定模式和局部样式生命周期

**文件：**

- Modify: `app/models/text_layer.py`
- Modify: `app/models/text_layer_serialize.py`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/ui/integrated_text_panel_handlers.py`
- Modify: `app/qml/Main.qml`
- Test: `tests/test_text_layer_core.py`
- Test: `tests/test_qml_text_typography.py`

**策略：** 局部颜色和局部字号只对“整段排版”有效；切换绑定模式时清除两类范围，而不是保留在无意义的候选文案索引上。该行为必须在界面上给出一次状态提示，并作为一次可撤销操作保存。

**实现要求：**

1. `text_binding_enabled` setter 同时调用 `_clip_text_color_ranges_to_current_text()` 和 `_clip_font_size_ranges_to_current_text()`。
2. 绑定模式切换由 ViewModel 统一执行，禁止 QML 或旧版面板直接写属性后绕过历史记录。
3. 开启绑定模式时清除局部样式；关闭绑定模式时以当前整段文本开始，不恢复已经失去语义的旧范围。
4. `selectedTextEditorHtml` 在绑定模式下不输出局部 HTML 样式，工具条保持禁用。
5. 文档加载后若发现绑定模式仍带局部范围，执行一次兼容清理并标记文档为已修改，不能在批量导出时静默改变源文档。

**完成标准：** 绑定模式切换、保存加载、复制图层和批量导出均不再出现潜在越界字号范围。

### Task 6：修复 QML 画布双击编辑和布局一致性

**文件：**

- Modify: `app/qml/Main.qml`
- Modify: `app/qml/viewmodels/workspace_view_model.py`
- Modify: `app/qml/components/FontSelectBox.qml`
- Test: `tests/test_qml_canvas_double_click_edit.py`
- Create: `tests/helpers/qml_canvas_double_click_probe.py`
- Modify: `tests/test_qml_workbench_smoke.py`
- Create: `tests/test_qml_canvas_text_edit_integration.py`

**实现要求：**

1. 真实集成测试加载 `Main.qml`，创建文字图层，通过 `QTest.mouseClick()` 或等价 Qt Quick 事件发送两次左键点击，验证覆盖层实际出现；不能只检查源码中存在 `onDoubleClicked`。
2. 双击前若第二次按下启动了移动手势，必须取消无效变换；锁定、裁剪、导出期间不得进入编辑。
3. 覆盖层绑定解析后的字体家族、真实字重、斜体、字号、字间距、行距、内边距和水平对齐。
4. 横排固定文本框使用与 Pillow 渲染相同的垂直居中规则；自动适配时使用相同的内边距锚点。
5. 竖排文字暂不伪造横排覆盖层：双击竖排文字时自动展开“文字内容”区并聚焦侧栏编辑器，同时显示状态提示“竖排文字请在右侧编辑”。这样保证可编辑性，不产生错误的几何预览。
6. 画布外点击提交，Esc 取消，Ctrl+Enter 提交；颜色/字号弹窗打开和关闭后保留原选区。
7. 编辑期间预览隐藏活动文字图层，避免 QML 覆盖层与 Pillow 预览重叠；提交或取消后恢复预览。

**视觉验证：**

```powershell
python tests/helpers/qml_canvas_double_click_probe.py --width 1280 --height 760
python tests/helpers/qml_canvas_double_click_probe.py --width 1600 --height 960
```

**完成标准：** 横排文字双击可稳定进入和退出编辑，覆盖层位置、字体、换行和基线与预览一致；竖排文字不会出现横排覆盖层错位。

### Task 7：修复旧版 QWidget 编辑器取消和提交一致性

**文件：**

- Modify: `app/ui/canvas_text_editor.py`
- Modify: `app/ui/canvas_events.py`
- Modify: `app/ui/canvas_view.py`
- Modify: `app/ui/integrated_text_panel_handlers.py`
- Test: `tests/test_text_layer_mixed_font_size.py`
- Create: `tests/test_canvas_text_editor.py`

**实现要求：**

1. `CanvasTextEditor.__init__()` 保存完整快照，包含文本、局部颜色、局部字号和自动适配状态。
2. 编辑时不要直接持久化 `current_text`；如必须实时预览，使用临时渲染快照或可回滚的编辑会话，不直接污染历史模型。
3. `_commit()` 调用统一文本变更服务，一次性写入文本和样式，恢复自动适配并保存一条历史。
4. `_cancel()` 恢复完整快照，清理缓存，发出一次预览刷新，不保存历史。
5. 失焦、Esc、画布切换、关闭文档和切换标签页都必须明确走提交或取消路径，不能出现编辑器悬挂。

**完成标准：** 旧版 QWidget 入口与 QML 入口对相同输入产生相同的模型数据；取消不会留下文字或局部样式变更。

### Task 8：恢复局部字号入口和测试覆盖

**文件：**

- Modify: `app/qml/Main.qml`
- Modify: `tests/test_qml_workbench_smoke.py`
- Restore or replace: `tests/test_qml_text_font_size_ranges.py`
- Restore or replace: `tests/test_text_layer_font_size_ranges.py`
- Create: `tests/test_text_style_ranges.py`

**实现要求：**

1. 侧栏文字内容区增加“选区字号”和“清除局部字号”，使用 Qt 选区入口。
2. 画布选区工具条继续提供字号输入和清除局部样式；两处都显示混合状态。
3. 恢复被删除测试的有效行为，不机械恢复已经淘汰的旧属性名；如果 API 改名，使用新 API 重写测试。
4. QML smoke 测试必须断言真实行为入口和对象名，不只断言任意字符串存在。

**完成标准：** 用户无需切换编辑入口即可完成局部颜色和局部字号设置、清除、撤销和重做。

### Task 9：序列化、渲染、批量导出回归

**文件：**

- Verify: `app/models/text_layer_serialize.py`
- Verify: `app/models/text_layer_render.py`
- Verify: `app/models/document_renderer.py`
- Verify: `app/utils/fast_renderer.py`
- Verify: `app/utils/fast_renderer_surface.py`
- Verify: `app/utils/optimized_batch_executor.py`
- Test: `tests/test_layer_serialize.py`
- Test: `tests/test_fast_renderer_smoke.py`
- Test: `tests/test_render_and_pickle_contracts.py`
- Test: `tests/test_qml_multi_tab_export.py`

**验证项目：**

1. 新建文字图层，设置字体、face、局部颜色、局部字号，保存 `.cmp` 后重新加载，所有字段和渲染结果保持一致。
2. 加载不含 `font_face`、不含局部范围的旧 `.cmp`，默认值和旧 `font_style` 行为保持兼容。
3. 加载带越界范围的旧数据时执行裁剪，不抛异常；若绑定模式带局部范围，按 Task 5 清理。
4. 单图 PNG/JPG、单文档批量导出、多标签批量导出分别验证随机文案不会因为缓存重复，局部样式不会串到下一张。
5. 检查 FastRenderer 和 surface cache key 同时包含 `font_family`、`font_face`、`font_style`、颜色范围和字号范围。

**完成标准：** 预览、导出和批量导出都调用同一 `TextLayer` 样式数据，不存在只在 QML 编辑器显示而导出丢失的样式。

## 5. 测试矩阵

### 5.1 单元测试

```powershell
python -m pytest -m unit -q
python -m pytest tests/test_text_style_ranges.py -q
python -m pytest tests/test_text_rich_format.py tests/test_text_layer_range_colors.py tests/test_text_layer_mixed_font_size.py -q
python -m pytest tests/test_text_layer_core.py tests/test_layer_serialize.py -q
```

覆盖：

- Python/Qt 索引互转和代理对边界；
- 插入、删除、替换后的颜色/字号范围迁移；
- 相邻区间合并、清除和越界裁剪；
- 绑定模式切换；
- 字体别名、真实 face、缺失字体和旧序列化兼容；
- duplicate、undo/redo 和保存加载。

### 5.2 QML 集成测试

```powershell
$env:QT_QPA_PLATFORM = "offscreen"
$env:QT_QUICK_BACKEND = "software"
python -m pytest tests/test_qml_canvas_text_edit_integration.py tests/test_qml_rich_text_selection_visual.py -q
python -m pytest tests/test_qml_workbench_smoke.py tests/test_qml_text_typography.py -q
```

覆盖：

- 真实双击事件命中顶层文字图层；
- 移动手势取消、锁定图层、空白区域和裁剪状态；
- 选区颜色/字号弹窗打开后选区恢复；
- Esc、Ctrl+Enter、失焦提交；
- 竖排文字降级到侧栏编辑器；
- 字体下拉当前值、缺失值和真实 face 显示。

### 5.3 人工验收

1. 新建画布，创建横排和竖排文字图层。
2. 选择微软雅黑、Arial、本地字体和不同真实字重，观察编辑器、预览和导出。
3. 在 `A😀BC` 中分别选择 `😀`、`B`、`BC` 设置颜色和字号。
4. 在已设置局部样式的文本开头、中间、结尾插入和删除字符。
5. 切换“按行随机/整段排版”，保存、关闭、重新打开。
6. 双击画布文字，验证输入、选区格式、取消、提交、撤销和重做。
7. 批量导出至少 20 张，确认随机文案、局部样式和字体没有跨图串值。

## 6. 兼容性和迁移策略

- 不修改现有 `.cmp` 顶层结构；新字段只使用现有可选字段 `font_face` 和范围字段。
- 旧文档没有 `font_face` 时按空字符串加载；旧 `font_style` 继续生效。
- 旧文档保存了平台字体名时不强制转换为 `sans-serif`，保证原项目视觉优先；只对新建图层使用统一默认值。
- 旧字体缓存缺少 face 数据时重新扫描，不删除用户缓存文件，扫描成功后原子替换缓存。
- 缺失字体不自动改写文档字体名；只有用户主动选择新字体才写入新值。
- 绑定模式中的局部范围清理必须进入历史记录；批量导出期间不得修改源文档状态。

## 7. 风险与处理

| 风险 | 影响 | 处理 |
|---|---|---|
| `SequenceMatcher` 对超长文案耗时 | 侧栏提交卡顿 | 对超长文本设置阈值；超过阈值使用分块 diff 或提示用户，常规海报文案保持精确迁移 |
| Qt 与 Pillow 对同一字体的字重命名不同 | 编辑器与导出粗细差异 | 使用扫描得到的 weight/italic 元数据，不依赖样式字符串；增加像素/字体信息回归 |
| 字体目录后台扫描晚于 QML 首屏 | 下拉内容短暂不完整 | 首屏显示当前值和 fallback；目录加载完成发 `fontCatalogChanged`，不重置当前选择 |
| 竖排无法由 QML TextEdit 原生表示 | 覆盖层布局错误 | 竖排双击明确降级到侧栏，不展示伪横排覆盖层 |
| 旧 QWidget 入口与 QML 同时修改模型 | 历史记录重复或互相覆盖 | 所有提交集中到一个文本变更服务，并在编辑期间锁定另一入口 |
| `.cmp` 中存在异常范围或异常颜色 | 加载失败 | 反序列化统一做类型、长度、颜色和字号校验，异常项跳过并记录日志 |

## 8. 发布前验收清单

- [ ] 所有新建和重置文字入口使用统一默认字体常量。
- [ ] Qt 编辑器和 Pillow 导出对默认字体、真实 face、粗体、斜体的解析一致。
- [ ] 当前字体为 Arial/英文/缺失字体时，字体选择器仍显示当前值。
- [ ] 侧栏和画布选区都正确处理 emoji、中文和换行。
- [ ] 文本插入、删除、替换后颜色和字号范围迁移正确。
- [ ] 绑定模式不携带有效的局部颜色/字号范围。
- [ ] QML 横排双击真实可进入编辑，锁定/裁剪/导出状态正确拒绝。
- [ ] 竖排双击聚焦右侧编辑器，不出现横排覆盖层错位。
- [ ] Esc/取消恢复完整快照，提交只产生一条历史记录。
- [ ] 局部颜色和局部字号均有侧栏入口与画布入口。
- [ ] 保存/加载、duplicate、undo/redo、单图导出、批量导出、多标签导出全部通过。
- [ ] `python -m pytest -q` 全量通过，`git diff --check` 无输出。
- [ ] 仅暂存本轮修复文件，不把现有用户改动和生成目录纳入提交。

## 9. 明确不在本次范围

- 不嵌入字体文件到 `.cmp`，不从网络下载字体。
- 不实现可变字体连续轴编辑器。
- 不改变批量绑定组合、图片图层和非文字图层的业务规则。
- 不把 QML `TextEdit` 强行改造成完整排版软件；竖排先使用侧栏编辑降级策略。

**建议执行顺序：** Task 0 -> Task 1 -> Task 3 -> Task 4 -> Task 5 -> Task 6 -> Task 7 -> Task 8 -> Task 9。Task 2 可在 Task 1 后并行，但合并前必须先通过字体解析一致性测试。
