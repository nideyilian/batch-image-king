# 卡片内标签页管理 · 交互设计说明

> 补齐「预设卡片 → 标签页」这一层缺失的交互契约：**卡片内一次性关闭全部标签页**、
> **重命名单个标签页**、**变更写回卡片**。
>
> 最后更新：2026-11-02
>
> 范围：`PresetCard`（网格卡片）/ `PresetListRow`（列表行）暴露的「标签页」操作，
> 以及 `PresetManagerViewModel`（下称 PMVM）、`PresetManager`（下称 PM）、
> `WorkspaceSessionViewModel`（下称 WSVM）三者在这条链路上的职责边界。
> **本文只定义契约与流程，不含实现代码。**

---

## 零、先明确「卡片 / 标签页」到底指什么

写方案前必须先钉死名词，否则「关闭标签页」会被误解成关工作区的编辑标签。

| 概念 | 代码实体 | 说明 |
|---|---|---|
| **卡片** | `app/qml/components/PresetCard.qml`（网格）、`PresetListRow.qml`（列表） | 一张卡 = 一个预设（`preset_id`）。它**不是**文档，不含可编辑图层。 |
| **卡片内的标签页** | `.cmp` 文件里的 `documents[]` 数组，一项一页 | 存盘时由 `PM.save_preset_documents()` 写入，每项带 `index` / `name` / `original_tab_name` / `canvas_width` / `canvas_height` / `layers[]`。 |
| **卡片上的页数** | `summary.document_count` = `len(documents)` | 工作台右侧「标签页 N 个」读的就是它（`PresetWorkbench.qml:806`）。 |
| **编辑区标签页** | `WorkspaceSessionViewModel._sessions[]` | 卡片「打开」后加载进工作区的编辑会话。**与卡片内的 documents 是两份数据**，方向单向：卡片 → 工作区。 |

### 现状能力盘点（实测 2026-11-02）

| 能力 | 现状 | 证据位置 |
|---|---|---|
| 卡片显示页数 | 有 | `MetaRow { label: "标签页" }`，`PresetWorkbench.qml:805-811` |
| 卡片封面选第几页 | **有** | `setCoverDocument()` → `PM.set_cover_index()`，只改索引不改内容 |
| 卡片列出页名 | **无**。`tab_names` 在 `get_preset_summary()` 里算出来了（`preset_manager.py:321`），但 PMVM 的 `presets()`（第 53-91 行）**没有把它放进返回给 QML 的字典**，详情面板也没有页列表 UI | 实测：QML 侧只用到 `documentCount` 与 `coverCandidates` |
| 卡片内关闭某一页 / 关闭全部页 | **无** | `presets()` 只透出 `document_count`，QML 无从操作 |
| 卡片内重命名单页 | **无** | 同上；`renamePreset()` 改的是**卡片名**，不是页名 |
| 原地改写已有 `.cmp` | **无**。全仓 4 处 `pickle.dump` 全是**新建**：`save_preset`（205）、`save_preset_from_document`（415）、`save_preset_documents`（499）、`import_preset`（987）。前三个是新建 .cmp，第四个是导入新 id。**没有任何方法能改写已存在 preset 的 documents** | `preset_manager.py` |

> 最后一条是硬缺口：**不改 PM 就没有任何合法路径把页名/页数写回磁盘。**
> 好消息：`import_preset`（`preset_manager.py:976-994`）已经在用 `mkstemp` + `os.replace`
> 的原子写盘写法，新增的写回方法直接照这个模板做即可，不用重新设计。

> 表中后三行就是本次要补的三块。

---

## 一、场景 1：卡片内一次性关闭所有标签页

### 1.1 功能定义

「关闭全部标签页」= 把该预设的 `documents[]` 清空，卡片退化为**空预设**状态。

它**不是**删除预设：`.cmp` 文件保留、索引保留、分类/标签/封面/使用次数全部保留。理由：

- 用户想清掉的是「这套模板的内容」，不是「这个模板在库里的位置」。删了再建，分类和标签要重打一遍。
- Eagle / Photoshop 预设管理器的语义一致：清空内容 ≠ 删除条目。

**空预设是合法终态**，但必须显式呈现，不能装作正常卡片——否则用户点「打开」得到 0 个标签页，会以为坏了。

### 1.2 作用范围（必须写清，否则用户会误伤）

| 维度 | 是否受影响 |
|---|---|
| 该预设的 `documents[]` | **被清空** |
| 该预设的 `.cmp` 文件 | 保留（改写为 0 documents） |
| 索引里的 name / category / tags / favorite / cover_index / run_count | 保留 |
| 缩略图文件 | **删除**（没有内容就没有封面） |
| 其它预设 | 完全不受影响 |
| 当前工作区已打开的标签页 | **完全不受影响**（卡片与工作区是两份数据，见零节表格） |

> 最后一行最容易误解，必须在确认弹窗里明写。

### 1.3 操作入口（三处，语义一致）

| 入口 | 位置 | 可见条件 |
|---|---|---|
| **A. 卡片操作条按钮** | `PresetCard` 悬停/选中时操作条最右，`AppIcons.trash` 变体「清空标签页」 | `documentCount > 1` |
| **B. 卡片右键菜单** | `卡片菜单 → 标签页 → 关闭全部标签页…` | `documentCount > 1` |
| **C. 工作台右侧「标签页」元数据行** | 行尾小图标按钮 + 文字「N 个」可点 | `documentCount > 1` |

`documentCount <= 1` 时三处都**隐藏而非禁用**：只有一页时说「关闭全部」在语义上等于清空整卡，
和「删除预设」容易混淆，不给这个入口。要清空单页预设，用删除预设。

### 1.4 完整交互流程

```
[点击入口 A/B/C]
      │
      ├─ 前置校验 ────────────────────────────────────────┐
      │   ① preset 是否还存在？  否 → Toast「预设已不存在，列表已刷新」+ 刷新卡片，结束
      │   ② documentCount > 1？  否 → （入口本不该出现）静默 return
      │   ③ PMVM.lastBusy？      是 → Toast「正在处理其它操作，请稍候」，结束
      └────────────────────────────────────────────────────┘
      │
      ▼
[确认弹窗 AppDialog，模态]
   标题：关闭全部标签页
   正文：将清空「{预设名}」中的 {N} 个标签页，此操作不可撤销。
        预设本身、分类与标签会保留。
        （正文下方第二行，次要色）
        已打开到工作区的标签页不受影响。
   勾选项（默认不勾）：同时关闭工作区中来自此预设的 {M} 个标签页
   ─────────────────────────────────
   [取消]  [清空 N 个标签页]（危险色按钮）
      │
      ├─ 取消 / Esc / 点遮罩 ──→ 关闭弹窗，不做任何写入，卡片状态零变化
      │                          （不发 presetsChanged，不产生副作用）
      ▼
[执行]
   PMVM.closeAllDocuments(presetId, alsoCloseInWorkspace=false) -> dict
      │
      ├─ 成功 ──→ ① 按 1.6 刷新卡片与工作台
      │           ② Toast「已清空 {N} 个标签页」+「撤销」按钮（30s 内可点）
      │           ③ 弹窗关闭
      │
      └─ 失败 ──→ 弹窗**不关闭**，正文下方显示红字错误
                  按钮由「清空」变为「重试」
                  错误文案按 1.7 分类
```

### 1.5 方法职责

新增于 `PresetManagerViewModel`：

```
closeAllDocuments(preset_id: str, *, also_close_in_workspace: bool = False) -> dict
```

返回结构（沿用项目里已有的 dict 返回风格，便于 QML 判分支）：

```
成功: {"ok": True,  "cleared": N, "workspace_closed": M, "undo_token": "<str>"}
失败: {"ok": False, "reason": "preset_missing|io_failed|busy|no_documents",
        "message": "<可直接展示的中文>"}
```

职责边界：

- **做**：前置校验 → 调 `PM.clear_preset_documents()` → 删缩略图 → 刷新索引与信号 → 生成 undo token → 需要时调 WSVM 关闭会话
- **不做**：不弹窗、不做二次确认（QML 的职责）、不拼 UI 文案（只给 `reason` + 兜底 `message`）
- **不做**：不自己改 `documents` 数组（必须走 PM，见 1.8 的写盘约束）

新增于 `PresetManager`：

```
clear_preset_documents(preset_id) -> bool     # 读 .cmp → documents=[] → 原子写回
```

### 1.6 关闭后的状态处理（三种可见后果，缺一不可）

| 对象 | 处理 |
|---|---|
| **卡片本身** | ① `documentCount = 0`，页数元数据行显示「0 个」并用 `Theme.textMuted`；② 卡片进入 `empty` 视觉态：封面位置显示虚线框 + `AppIcons.fileX` + 文字「没有标签页」，**不显示破图**；③ 封面轮播点、页码角标全部隐藏；④ 「打开」按钮变禁用并 tooltip「该预设没有内容」 |
| **排序位置** | **保持不变**。不清空 `order`、不移动到列表末尾——用户清空内容不代表想让它在库里跳位。 |
| **工作台右侧详情** | 若当前选中的正是这张卡：详情面板保留（名称/描述/分类/标签仍可编辑），「封面选择」区块隐藏，「打开」主按钮变禁用。选中态**不跳走**到别的卡，避免用户以为误删。 |
| **缩略图** | 立即从 `_thumb_service` 撤掉该 preset 的排队任务，删除磁盘上的 `.thumb.png`（含所有页），`_missing_cache` 清该 key。否则下次打开工作台会闪一下旧图。<br>⚠️ **`PresetThumbnailService` 目前没有取消接口**（只有 `request` / `request_many` / `pending_count`，实测 `preset_thumbnail.py:330-372`），需新增 `cancel(preset_id)`：从 `self._pending` 集合移除 + 置一个 `_cancelled` 标记，让 `_run` 在取到该 id 时直接跳过。若不新增，最小可行做法是**不取消、只删文件**——本次结果会被写回一个已删除的缩略图路径，下次 `request()` 因 `is_cache_valid` 失效而重算，功能上可接受，只是多一次无用渲染。 |
| **工作区（默认不勾）** | 不动。已打开的标签页继续存在，用户可继续编辑；它们与卡片此后的内容无关联。 |
| **工作区（勾选时）** | 对每个来自该 preset 的会话调 `WSVM.requestClose(index)`；其中若有 `is_modified=True` 的，**在同一个弹窗内**追加一行「{M} 个标签页有未保存修改」并列出页名，用户再确认一次；任一页关闭失败则整体回滚（不执行清空）。 |
| **撤销** | `undo_token` 保留被清空前的 `documents[]` 深拷贝 30s。点 Toast「撤销」→ `restoreDocuments(preset_id, undo_token)` 原样写回，卡片回到清理前状态。超时或页面切换即丢弃 token。 |

> 撤销按钮不是锦上添花：一次性清空 N 页，误点代价很高，而 `.cmp` 被覆盖后没有系统级回收站。

### 1.7 异常与提示

| 失败点 | reason | 展示 | 后续 |
|---|---|---|---|
| 预设已被其它入口删掉 | `preset_missing` | Toast「预设已不存在，列表已刷新」 | 关闭弹窗 → `presetsChanged` 强制刷新 |
| 写盘失败（磁盘满 / 只读 / 权限） | `io_failed` | 弹窗内红字「保存失败：{errno 中文说明}。已取消操作，预设内容未改动。」 | 弹窗保持，按钮变「重试」 |
| 正在导出，`operationsBlocked` | `busy` | Toast「请先结束正在运行的导出任务」 | 不执行 |
| `documents` 本来就是空 | `no_documents` | 静默 return（入口不该出现） | — |
| 缩略图删除失败 | —（不阻断） | 无提示，写日志 | 继续完成清空；下次 `requestThumbnail` 会因无 documents 直接跳过 |
| 工作区关闭被用户中断（勾选路径） | `workspace_close_aborted` | 弹窗内红字「已取消：部分标签页未能关闭，预设内容未改动。」 | **回滚**：不执行清空 |

**关键约束：写盘失败必须回滚内存状态。** `PM.clear_preset_documents()` 内部先改内存副本、
再原子写盘、写盘失败则丢弃副本——不允许出现「界面显示 0 页、磁盘还是 3 页」的劈叉。

### 1.8 写盘约束（这是本次最容易被做错的一处）

`.cmp` 是 **pickle**，且项目已经上了 `load_trusted_pickle` 白名单（防 RCE）。
回写时必须：

1. 用**已在内存里的** `preset_data`（`load_preset()` 的返回值）改写，**不要**重新构造，
   否则会丢掉 `global_settings` / `version` / 其它未知字段。
2. 写临时文件 + `os.replace()` 原子替换（同 `_save_index()` 的既有做法）。
3. **不重新 pickle 文档对象**：`documents[]` 里存的是 `prepare_document_data()` 产出的纯 dict，
   清空时只是把 `preset_data['documents'] = []`，不触碰其余字段，天然安全。
4. 写完后**同步更新索引**里的 `document_count` / `total_layers` / `canvas_sizes` / `type`，
   否则卡片显示的页数与实际不符（索引是卡片的数据源）。

---

## 一·补：页列表 UI 必须新建（场景 2 / 3 的共同前置）

场景 2 和场景 3 都依赖一个能"逐页操作"的地方，而现状里**没有**：

- PMVM 的 `presets()` 没把 `tab_names` 传给 QML（只给了 `documentCount`）
- `PresetWorkbench.qml` 详情面板只有「标签页 N 个」这一行文字 + 「卡片封面」选择器
- 没有任何地方列出「第 1 页 / 第 2 页……叫什么名」

所以本节先定这个容器，否则后面的双击改名、右键菜单都无处安放。

### 位置与尺寸

放在详情面板「标签页 N 个」元数据行**下方**，与「卡片封面」区块**合并成一个「标签页」区块**：

```
标签页 (3)                      [清空全部]
┌──────────────────────────────────────┐
│ ▣ 第 1 页  主图              ⋮        │  行高 28
│ ▣ 第 2 页  细节图            ⋮        │
│ ▣ 第 3 页  场景图            ⋮        │
└──────────────────────────────────────┘
卡片封面  [第1页] [第2页] [第3页]
```

- 容器：`ListView`，`implicitHeight = min(3, count) * 28 + 4`，超过 3 页内部滚动
  （不无限撑高详情面板，避免挤压下方的分类/标签区块）。
- 行：左侧 16px 页序号徽标（不是缩略图——详情面板宽度约 300px，缩略图会挤掉名字），
  中间页名（`elide`），右侧 `⋮` 菜单按钮。
- 原来独立的「卡片封面」区块保留，但移进这个区块下方，用 4px 间距贴合——
  它本质上是"选哪页当封面"，属于同一组语义。

### 为什么不放在卡片上

卡片封面 200×110，叠一个 3 行列表会完全盖住缩略图。参考 Figma 文件卡与 Eagle 素材卡：
**卡片负责"认出是哪个"，详情面板负责"改它"**。页列表放详情面板是这两者的自然分工。

### 页列表的数据来源

新增 `PMVM.tabTitles(preset_id) -> list[dict]`，返回：

```
[{"index": 0, "title": "主图", "isCover": true},
 {"index": 1, "title": "细节图", "isCover": false}, ...]
```

复用 `get_preset_summary()['tab_names']`（它已经处理了 `original_tab_name or tab_name or name or "标签页 N"` 的兜底链），
**不重新写一遍取名逻辑**——两处取名规则一旦分叉，就会出现"卡片和列表显示不同名"。

---

## 二、场景 2：重命名单个标签页

### 2.1 功能定义

修改**某一个页**的显示名，写入 `documents[i].name` 与 `original_tab_name`。

命名澄清（必须写进代码注释，否则后人必犯错）：

- `renamePreset(preset_id, name)` 改的是**卡片名**（索引里的 `name`），已存在。
- 本文的 `renameDocument(preset_id, page_index, title)` 改的是**页名**（`.cmp` 里的 documents[i].name）。
- 两者**互不影响**，UI 上也不能共用同一个输入框。

### 2.2 触发方式（三处，全部走同一个校验函数）

| 入口 | 交互 |
|---|---|
| **A. 双击页名**（工作台右侧页列表） | 原地进入编辑态，等价 Photoshop 图层面板的双击改名 |
| **B. 右键页 → 重命名** | 同上 |
| **C. 键盘 F2**（页列表有焦点且恰好选中一页时） | 同上 |

> 为什么不做成「双击整行」：整行双击在网格视图里会命中卡片的 `activated()`（打开），
> 两个手势会打架。热区限定在**页名文字本身 + 其左右各 6px**。

### 2.3 编辑状态（完整生命周期）

```
idle
 │ 双击 / F2 / 右键
 ▼
editing（原地内联 AppTextField 覆盖页名，自动全选原文）
 │
 ├─ Enter ──────────→ validating
 ├─ 失焦(blur) ─────→ validating（与 Enter 同路，不改行为）
 ├─ Esc ────────────→ idle（还原原文，零写入，不发任何信号）
 └─ 再次双击同页 ───→ 保持 editing（不重复进入）
      │
      ▼
validating
 ├─ 通过 ──→ saving ──→ idle（显示新名 + Toast）
 └─ 不通过 → editing + 行下方红字（不退出编辑态，焦点留在输入框）
```

编辑态的具体规则：

- **原文预填并全选**，用户直接打字即替换（参考 Figma 图层改名、macOS Finder 重命名）。
- 输入框宽度 = 页名区宽度，**不撑开卡片**；超长文本横向滚动，不换行。
- 编辑期间：
  - 该页的拖拽排序**禁用**（避免"正在改名却被拖走"）；
  - 卡片轮播暂停在当前页；
  - 卡片「打开」按钮**不禁用**，但点了先提交改名再打开（commit-then-act）。
- **同一时刻只允许一页处于编辑态**。切到另一页编辑时，前一页按「失焦」处理（即提交）。

### 2.4 校验规则（按顺序短路，命中即返回）

| 序 | 规则 | 失败提示 |
|---|---|---|
| 1 | 去首尾空白后非空 | 「标签页名称不能为空」 |
| 2 | 长度 ≤ 40 **字符**（非字节；按 Unicode 码点算，中文与 emoji 各算 1） | 「名称最多 40 个字符（当前 {n}）」 |
| 3 | 不含控制字符 `\x00-\x1F` 与换行 | 「名称不能包含换行或控制字符」 |
| 4 | 不与**同一预设内**其它页重名（大小写不敏感，`casefold()` 比较，忽略自身） | 「该预设内已有同名标签页」 |
| 5 | 与原值相同（仅首尾空白差异也算相同） | **直接退出编辑态，不报错、不写盘**（视作无操作） |

设计取舍说明：

- **允许跨预设重名**。页名只是给人看的标签，不是主键（真正的主键是页的 `index`）。加跨预设唯一约束会让「第 1 页」这种通用名几乎不可用。
- **不做非法文件名字符校验**。页名不参与文件路径（`.cmp` 以 `preset_id` 命名，缩略图以 `preset_id + 页号` 命名），所以 `/\:*?"<>|` 都合法。这一点与"图层名"不同，别照抄那边的规则。
- 长度上限取 40 而非 255：卡片与详情面板的页名区约 220px，11px 字号下约 20 个中文字。40 已经会截断显示（见 2.6），再放宽没有意义。

### 2.5 取消逻辑（三种"取消"，行为必须区分）

| 用户动作 | 行为 | 是否写盘 | 是否发信号 |
|---|---|---|---|
| **Esc** | 还原原文，退出编辑态 | 否 | 否 |
| **点其它页 / 点画布** | 视作失焦 = **提交**（不是取消） | 视情况（见 2.4 第 5 条） | 视情况 |
| **点弹窗外部 / 切走工作台** | 同失焦 = 提交 | 同上 | 同上 |
| **保存失败后点「取消」** | 还原原文，退出编辑态 | 否 | 否（但需回滚内存副本） |

> 「失焦=提交」是刻意的。改成"失焦=取消"会让用户在改完名后习惯性点空白处，
> 结果白改一遍——Figma、macOS 文件重命名都是失焦即提交。

### 2.6 长文本与显示

- 页名区 `elide: Text.ElideRight`，`maximumLineCount: 1`。
- 悬浮 tooltip 显示完整名称。
- 编辑态**不省略**，改为横向滚动保证可见光标位置。

### 2.7 方法职责

新增于 `PresetManagerViewModel`：

```
validateDocumentTitle(preset_id, page_index, title) -> dict
    # {"ok": bool, "reason": "...", "message": "...", "normalized": "<去空白后>"}
    # 纯函数式：只读校验，不写任何状态。QML 在每次 submit 时调用。

renameDocument(preset_id, page_index, title) -> dict
    # {"ok": True,  "title": "<最终名>", "changed": bool}
    # {"ok": False, "reason": "validate_failed|preset_missing|page_missing|io_failed",
    #  "message": "...", "detail": {...}}
    # 内部先调 validateDocumentTitle，通过才写盘。
```

新增于 `PresetManager`：

```
rename_document(preset_id, page_index, title) -> bool
    # 读 .cmp → documents[i]['name'] = title
    #        → documents[i]['original_tab_name'] = title   ← 两个字段一起改
    #        → 原子写回
```

> **两个字段必须同时改**：`get_preset_summary()` 取页名的表达式是
> `original_tab_name or tab_name or name`（`preset_manager.py:321`）。
> 只改 `name` 而 `original_tab_name` 还是旧值，卡片读到的永远是旧名——
> 这是最容易出现"改了没生效"的地方，必须写进契约。

---

## 三、场景 3：把变更保存回卡片

### 3.1 数据流向（一张图说清）

```
            ┌──────────────────────────────────────────────┐
            │  磁盘 .cmp（唯一事实来源）                    │
            │  documents[i].name / original_tab_name        │
            └───────────────▲──────────────┬───────────────┘
                            │ 写回          │ 读取
                  ┌─────────┴───────┐  ┌──▼──────────────────┐
                  │ PresetManager   │  │ PresetManager       │
                  │ （原子写盘）     │  │ .load_preset()      │
                  └─────────▲───────┘  └──┬──────────────────┘
                            │              │
                  ┌─────────┴──────────────▼──────┐
                  │ PresetManagerViewModel         │
                  │ presetsChanged / viewChanged   │
                  └─────────▲──────────────┬──────┘
                            │              │ 属性重算
                  ┌─────────┴──────────────▼──────┐
                  │ QML：PresetCard / 详情面板      │
                  └───────────────────────────────┘
```

**核心原则：卡片不持有状态，只渲染 VM 算出来的值。**
改完名必须让 VM 发信号触发属性重算，卡片不需要（也不能）自己去改本地 `presetData` 副本。

### 3.2 保存时机（四档，明确到"什么时候一定落盘"）

| 时机 | 触发 | 写盘粒度 |
|---|---|---|
| **T1 提交即写** | Enter / 失焦 / 关闭全部确认 | **一次操作一次写盘**（默认路径） |
| **T2 删除页后重排** | 后续实现「关闭单页」时 | 跟着 T1 一起写（同一事务） |
| **T3 批量改名** | 一次多选重命名（当前不做） | 合并成一次写盘 |
| **T4 离开工作台** | 切到别的页面 / 关闭工作台 | **不补写**：T1 已经保证落盘，这里只做「若有未提交编辑态则提交」 |

**不做防抖（debounce）**，理由：

- 页名是离散的、一次改一个，不是滑块那种连续输入；防抖只会让"改了立刻关程序"丢数据。
- 写盘成本：单个 `.cmp` 实测 1~3MB，pickle 落盘 + `os.replace` 约 5~15ms，可接受。

**不做脏标记 + 手动保存**，理由：卡片是"库"，不是"编辑器"。用户对库的心智是"改了就生效"，
加一个"保存"按钮反而制造"我是不是忘了保存"的焦虑。

### 3.3 数据同步方式（谁刷新、刷什么）

`PMVM` 在每次成功写盘后，按这个顺序发信号（顺序不能乱）：

```
1. presetsChanged.emit()      # 卡片列表重建（documentCount / tabNames / thumbnailUrl 都挂在它上面）
2. viewChanged.emit()         # visiblePresets 重算（筛选/排序依赖它）
3. documentTitlesChanged.emit()  # 新增，仅页名变化时发；详情面板页列表订阅它做局部刷新
```

为什么要第 3 个独立信号：`presetsChanged` 会让 `GridView` 整体重建，
一次改名如果只发它，用户会看到**整屏卡片闪一下**才生效——这正是我们上一轮刚修掉的
「图层面板整表重建」同类问题。详情面板的页列表用 `documentTitlesChanged` 做行级刷新。

> 补充：如果页名不在卡片上直接展示（当前设计就是只在详情面板展示），
> 那么 `presetsChanged` 其实**不必须**发，只发第 3 个信号更省。
> 但 `document_count` 变化（场景 1）必须发 `presetsChanged`。

### 3.4 失败处理（三层，逐层兜底）

| 层 | 失败情形 | 处理 |
|---|---|---|
| **L1 校验失败** | 空 / 超长 / 重名 | 留在编辑态，红字提示，**不写盘、不发信号**。用户可继续改或 Esc |
| **L2 写盘失败** | 磁盘满 / 只读 / 权限 / 文件被占用 | ① 内存副本回滚到写前值；② 编辑态**保持**，输入框内容保留（不清空用户输入）；③ 显示红字「保存失败：{原因}，请检查磁盘后用 Ctrl+S 重试」；④ **不发** `documentTitlesChanged`（因为没成功） |
| **L3 文件已损坏/缺失** | `load_preset()` 返回 None 或格式不合法 | ① 报 `preset_missing` / `preset_corrupt`；② 卡片标红角标「预设损坏」，点击提示修复；③ **禁止**写回（避免把损坏文件写成更坏的东西） |
| **L4 并发冲突** | 同一 `.cmp` 同时被两个入口改写（如两个窗口、或导出线程读同一 preset） | 用**写前 mtime 比对**做乐观锁：读盘时记 `mtime`，写回前再取一次，不一致则中止并提示「预设已被其它操作修改，请刷新后重试」（见 3.5） |

### 3.5 并发与一致性（容易被忽略但一定会踩）

`PM` 实例**只有一个**，但以下路径都可能同一时刻操作同一个 preset：

- 缩略图后台线程读 `.cmp`（`preset_thumbnail` 走独立线程）
- 导出线程读 `.cmp`（`exportPreset`）
- 用户在 UI 上改名

因此写回必须满足：

1. `PresetManager` 内加一把 **`threading.RLock`**（`self._preset_write_lock`），
   所有「读—改—写」整段持锁，不能只锁写。
2. 写回用 **mtime 乐观锁**：

```
expected_mtime = os.path.getmtime(path)   # 在 load 时记录
...
current_mtime = os.path.getmtime(path)
if current_mtime != expected_mtime:
    return {"ok": False, "reason": "stale", "message": "预设已被其它操作修改，请刷新后重试"}
```

3. 缩略图线程读到的若是旧版本（mtime 变了），**不重试**，直接丢弃本次结果并重新入队一次。
   避免"读到半新半旧"的中间态。

### 3.6 写回后的关联刷新（三件必须做的事）

改名会连带影响这些缓存，漏一个就出现"名字看着改了，别处还是老的"：

| 关联物 | 处理 |
|---|---|
| 缩略图 | 页名不进图，**无需重生成**。但若改的是**封面页**的名字，仍无需重生成（封面按 `cover_index` 取页，不看名字）。所以这里**什么都不用做**——写进契约是为了防止后人过度刷新。 |
| `_missing_cache` | 不涉及素材路径，无需清 |
| `tab_names` 摘要 | `presets()` 每次现算（`get_preset_summary` 里有 `tab_names`），只要在写盘后发 `presetsChanged`（或 `documentTitlesChanged`）就会重算。**不要**额外缓存它。 |
| 搜索索引 | 当前搜索的字段是 `name` / `description` / `category` / `tags` / `canvasSizes`（`_sorted_presets`，实测第 492-500 行），**不含页名**。所以改名**不需要**更新搜索索引。若将来要支持按页名搜，必须在这里补字段——现在**不涉及，不做**。 |

---

## 三·补：三个场景的咬合点（单独看不出来，一起用才暴露）

上面三节分开看都成立，合起来有三处必须一致，否则会出现"每个功能都实现了但一起用就出错"：

| 咬合点 | 冲突表现 | 统一规则 |
|---|---|---|
| 清空 vs 改名 | 正在改名时点「清空全部」 | 清空前**先强制提交**当前编辑态（commit-then-act）；清空成功后页列表为空，编辑态必须一并销毁，不能让输入框悬在空列表上 |
| 清空 vs 封面选择 | 清空后 `cover_index` 仍指向第 3 页，第 3 页已不存在 | 清空时把 `cover_index` 归 0；重建 `documents` 后若 `cover_index >= len`，读取端（`get_preset_summary`）必须钳到 0，不能返回越界值让卡片取不到封面 |
| 改名 vs 封面 | 改的是封面页名字，卡片封面还对不对 | 封面按 `cover_index`（页序号）取，与名字无关，**不需要重算缩略图**。但页列表里封面徽标要跟着 `cover_index` 走，不是跟着名字走 |
| 改名 vs 清空 undo | 清空后 30s 内点撤销，但期间改过某个页名 | undo 恢复的是**清空那一刻的完整快照**，期间的改名一并被覆盖。提示文案要写「撤销将恢复到清空前的状态」，避免用户以为只撤销清空 |

> 这张表的价值：实现时最容易各写各的，最后联调才发现清空后的 `cover_index` 越界。
> 建议把"钳位"写在读取端（`get_preset_summary`）而不是写入端——
> 因为老版本存下来的 `.cmp` 也可能有越界 `cover_index`，读取端兜底能一并救掉。

---

## 四、三个场景共用：状态机与信号契约

### 4.1 PMVM 新增的状态位

```
busy: bool            # 任一写操作进行中；为真时三处入口全部禁用
busyReason: str       # 用于 tooltip：「正在清空标签页…」/「正在保存名称…」
```

`busy` 是**必要**的：清空 N 页 + 删 N 个缩略图可能占几百 ms，
期间用户再点一次「清空」会造成两次写盘竞争。加一个全局位比给每个方法各写一遍幂等判断更省。

### 4.2 信号契约

| 信号 | 何时发 | 订阅方 |
|---|---|---|
| `presetsChanged` | 卡片维度数据变了：名称/描述/分类/标签/收藏/`document_count`/缩略图 | `PresetWorkbench` 的 GridView、计数徽标 |
| `viewChanged` | 可见集合或顺序变了：筛选/排序/搜索 | `visiblePresets` 绑定 |
| `documentTitlesChanged(preset_id)` **新增** | 仅页名变（不动 `document_count`） | 详情面板页列表（行级刷新） |
| `documentsCleared(preset_id)` **新增** | 场景 1 成功后 | 详情面板（切空态）、卡片（空态） |
| `errorChanged` | 已有 | 各处红字 |

### 4.3 三处入口的启用条件（统一表，避免各处判断漂移）

| 操作 | 启用条件 |
|---|---|
| 关闭全部标签页 | `documentCount > 1 && !busy && !operationsBlocked && !presetCorrupt` |
| 重命名页 | `documentCount >= 1 && !busy && !presetCorrupt && pageIndex 有效` |
| 打开卡片 | `documentCount >= 1 && !busy && !operationsBlocked` |

`presetCorrupt` 是新增位：`load_preset()` 失败时置真，此时**只允许删除预设**，其余全部禁用。
比"操作了再报错"体验好得多。

---

## 五、实现顺序建议（依赖关系）

```
① PM 层：clear_preset_documents / rename_document / _write_preset_atomic / mtime 乐观锁 / 写锁
        ↓（没有这层，上面全是空转）
② PMVM 层：busy 位、validateDocumentTitle、renameDocument、closeAllDocuments、新信号
        ↓
③ QML 层：页列表（详情面板内）、原地编辑态、三处入口、空态样式、确认弹窗
        ↓
④ 测试：见第六节
```

**不建议跳过 ①** 直接在 QML 里"改一下 `presetData` 就当保存了"：
`presetData` 是 VM 每次 `presets()` 现算的，本地改会在下一次刷新时被冲掉，表现为"改名后闪回旧名"。

---

## 六、必须补的测试（每条都对应一个曾经踩过的坑）

| 测试 | 断言要点 | 防的是哪种退化 |
|---|---|---|
| 改名后**重新读盘** | `load_preset()` 的 `documents[i].name` **与** `original_tab_name` **都**是新值 | 只改一个字段 → 卡片显示旧名 |
| 改名写盘失败回滚 | 注入 `os.replace` 抛异常，内存里仍是旧名，且未发 `documentTitlesChanged` | 界面与磁盘劈叉 |
| 清空后索引同步 | `preset.document_count == 0`、`total_layers == 0`、`canvas_sizes == []`、`type` 正确 | 卡片页数不更新 |
| 清空保序 | `order` 连续、且该 preset 位置不变 | 清空后被挤到列表末尾 |
| 清空不动工作区 | 已打开的同源会话数量不变 | 误关用户正在编辑的标签 |
| 空预设打开被拒 | `loadPreset()` 返回 0 且 lastError 非空 | 点开得到空白工作区 |
| 校验：40 字符边界 | 40 通过、41 拒绝；中文与 emoji 各按 1 算 | 用 `len(bytes)` 算长度 |
| 校验：同预设内重名 | 大小写不同也判重；跨预设同名**允许** | 约束过宽或过严 |
| 校验：控制字符 | `"a\nb"` 被拒 | 换行把卡片行高撑坏 |
| 写锁并发 | 两个线程同时改名，最终文件是**其中一个完整结果**，不是拼接 | 半写 |
| mtime 乐观锁 | 读后外部改文件，写回返回 `stale` 且不覆盖 | 覆盖别人的修改 |
| 信号粒度 | 只改名时 `presetsChanged` **不**发（或至少 `document_count` 不变时卡片不重建） | 整屏卡片闪 |

---

## 七、明确不做的事（避免后续反复讨论）

| 不做 | 理由 |
|---|---|
| 卡片上的页码圆点支持"点击关闭单页" | 圆点直径 6px，命中区太小；误触代价是删内容。单页关闭走详情面板列表（行高 28px，带确认） |
| 卡片内直接编辑页名 | 卡片封面区域 200×110，塞输入框会挤掉缩略图。就地改名只在详情面板页列表做 |
| 页名参与文件命名 | 现有命名用 `preset_id + 页号`，稳定且无非法字符问题。改成人读的名字会引入转义地狱 |
| 清空后自动补齐默认页 | 「清空」的语义就是清空。自动补一页会让用户以为没清干净 |
| 跨预设页名唯一 | 见 2.4 |
| 防抖保存 | 见 3.2 |
| 页级撤销栈 | 只有「清空全部」提供 30s 撤销（代价高），单页改名靠重新改名即可，不值得为此维护栈 |

---

## 八、与现有文档的关系

- 本文件**补充** `docs/preset-workbench-design.md`：那篇讲的是工作台「怎么摆」，
  本文讲的是「卡片内标签页怎么操作」。两者无冲突。
- 「重命名标签页」在 `Main.qml:2907` 已有一份实现，那是**工作区编辑标签**的重命名，
  与本文的**卡片页名**是两回事，不要合并。
- 交互原则沿用项目既有做法：危险操作二次确认、Toast 带撤销、能禁用就别隐藏。
  本文唯一的例外是 `documentCount <= 1` 时**隐藏**「关闭全部标签页」，
  理由见 1.3（语义上等同删除预设，不该给入口）。
  > 注：`docs/canvas-interaction-spec.md` 只覆盖画布内手势，**不含**通用危险操作约定，
  > 所以这里不引用它，避免张冠李戴。

---

## 九、实现落地记录（2026-11-02）

本文定义的三块已全部实现，以下记录**实际做法**与设计稿的差异，供后续维护对照。

### 9.1 落地清单

| 层 | 文件 | 新增内容 |
|---|---|---|
| PM | `app/utils/preset_manager.py` | `_preset_write_lock`、`_preset_file_path`、`_read_preset_for_write`、`_commit_preset_write`、`rename_document`、`clear_preset_documents`、`close_document`、`restore_document_payloads` |
| PMVM | `app/qml/viewmodels/preset_manager_view_model.py` | `busy`/`busyReason`、`documentTitlesChanged`/`documentsCleared` 信号、`tabTitles`、`validateDocumentTitle`、`renameDocument`、`closeAllDocuments`、`undoClearDocuments`、`_drop_thumbnails`、`_close_workspace_tabs_for_preset`；`presets()` 补 `tabTitles`/`corrupt` |
| QML | `app/qml/components/PresetWorkbench.qml` | 详情面板「标签页」区块（页列表 / 就地改名 / 清空全部）、`tabRowMenu`、`clearTabsDialog`、带撤销的 `undoToast`、`MetaRow` 下方「还有 N 页」提示 |
| 测试 | `tests/test_preset_tab_management.py` | 36 项 |

### 9.2 实现中发现并修掉的两个真问题

**① `documentCount` 的 `or 1` 把 0 吃掉了。**
`presets()` 原本写 `int(summary.get("document_count") or 1)`，而 0 是清空后的合法值，
`or` 把它兜成 1 → 页列表空白、卡片却显示「1 个」。改成只在字段**缺失**（None）时兜底。
这类「0 当假值」的写法在计数类字段上都会出错，不只是这一处。

**② `cover_index` 钳位不能一律归零。**
`_commit_preset_write` 里原本写「越界就归 0」。但 `close_document` 已经算好了
「删第 N 页时让后一页接上来」（cover=N），随后被归 0 覆盖，表现为「删个中间页，封面跳回首图」。
改成 `max(0, min(cover, count - 1))`，两个逻辑才不打架。

### 9.3 与设计稿的差异（都是实现时才发现的）

| 设计稿 | 实际做法 | 原因 |
|---|---|---|
| 页行 ⋮ 菜单含「关闭本页」 | **已实现**（第二批） | 见 9.5 |
| 三处入口（卡片按钮 / 卡片右键 / 元数据行） | **已做两处**：详情面板「清空全部」+ 卡片右键菜单（2026-11-03 补，见第十一节）。卡片常驻按钮仍未加 | 卡片操作条已满（打开/批量/收藏/复制/删除），再加会挤掉视觉呼吸空间；右键菜单不占版面 |
| `tabTitles()` 返回 list[dict] | 同 | ✓ 按设计实现 |
| QML 函数供调试入口调用 | **改用可写属性桥**（`requestTabRenameIndex` 等） | 实测 `QMetaObject.invokeMethod` **找不到** QML 根对象上的普通 `function`；属性读写一定可用。与既有 `selectPresetIndex` 同一套路子 |
| 缩略图取消接口 `cancel()` | **已新增**（见第十二节） | 原判断「不取消也能工作」是**错的**，实测该路径会让卡片继续显示已清空的旧图 |

### 9.4 验证结果

```
tests/test_preset_tab_management.py   36 passed
```

**故意注入 4 个退化，确认测试能抓到**（只跑绿不算验证）：

| 注入的退化 | 被抓到的测试 |
|---|---|
| 只写 `name` 不写 `original_tab_name` | `test_rename_writes_both_name_fields` 等 3 项 |
| `documentCount` 改回 `or 1` | `test_card_document_count_becomes_zero` |
| 改名额外发 `presetsChanged` | `test_rename_emits_titles_signal_not_presets` |
| 去掉 mtime 乐观锁 | `test_stale_write_is_rejected` |

另有三个实机探针（可复现，在 `docs/audit/`）：
- `_verify_pm_writeback.py` —— PM 层 30 项（双字段 / 覆盖 / 让位 / 清空 / 恢复 / 无 .tmp 残留）
- `_verify_pmvm.py` —— PMVM 层 48 项（校验规则 / 信号粒度 / busy / 撤销）
- `_verify_qml_tabs.py` —— QML 层 18 项（真实加载 PresetWorkbench，走完整交互链路）

---

## 十、单页关闭（2026-11-03 补做）

设计稿把这列入「本次范围未含」，第二批补上。**它不是「清空全部」的子集**，
有自己的语义决定，单独记一节。

### 10.1 与「清空全部」的关系

| | 清空全部 | 关闭本页 |
|---|---|---|
| 影响范围 | 全部 `documents[]` | 单个 `documents[i]` |
| 入口 | 详情面板「清空全部」按钮 | 页行 `⋮` → 「关闭本页」 |
| 关到 0 页后 | 预设进入空态（不删预设） | **同上**，语义保持一致 |
| 撤销 | 30s，全量快照 | **同上**，共用 `_undo_tokens` |

关键一致点：**关掉最后一页 == 清空**，所以两条路径必须走同一套撤销机制、
同一个 `documentsCleared` 信号、同一种空态。否则会出现「清空能撤销、关单页不能」的割裂。

### 10.2 PM 层返回值的必要变更

`close_document` 原来返回 `(ok, remaining, reason)` —— **不够**。
被删页的图层内容只有 PM 内部那一份，删完就没了，撤销只能还原一个空壳。

改成 `(ok, remaining, reason, removed_payload)`，`removed` 是 `copy.deepcopy` 掉的完整页：

```python
removed = copy.deepcopy(documents.pop(index))
```

> ⚠️ 这里的 `deepcopy` 不能省。直接 `documents.pop(index)` 返回原对象虽然内容正确，
> 但该对象与磁盘上那份共享引用，后续对返回值做任何修改都会污染已删数据
> （当前无用例，但这是「能不改就不改」的原则问题）。

### 10.3 撤销为什么用「关闭前全量快照」而不是 `removed`

`PresetManagerViewModel.closeDocument` 在调 PM **之前**先 `load_preset` 存一份
`before_documents`，撤销时整体写回。理由：

- 单页撤销的语义是「回到关闭前」，不是「把这一页插回去」——后者要处理插入位置、
  封面下标、`index` 字段重排，容易出错。
- `removed` 是**双保险**：万一 `load_preset` 在关闭前那一刻失败（极端），
  仍可退化为「只把这一页插回」。当前实现没用这条退路，但 PM 层保留返回值是必要的。

`tests/test_preset_tab_management.py::test_close_document_undo_uses_full_snapshot_not_removed_payload`
锁住了「撤销不依赖 removed」这一点。

### 10.4 交互细节

- 菜单里「关闭本页」与上面两项之间加 `MenuSeparator`，且用危险语义排在最后。
- 关闭前若正在改名，**先提交编辑态**再关 —— 否则用户刚打的字会被连带删掉。
- 关的是最后一页时，确认弹窗文案切换为「这是该预设的最后一页。关闭后预设会变为空状态，
  但预设本身、分类与标签都会保留」。同一句「其余标签页与预设本身不受影响」在此时是错的，
  会误导用户以为还有别的页。
- 关到空后 Toast 变成带「撤销」的版本（`requestToastWithUndo`），而不是普通 Toast。

### 10.5 验证

```
tests/test_preset_tab_management.py   45 passed（新增 9 项）
docs/audit/_verify_close_tab.py       28 项全过（含 QML 真实交互）
```

注入退化「removed 返回空壳」→ `test_close_document_returns_removed_payload` 立刻失败。

---

## 十一、卡片右键菜单（2026-11-03 补做）

设计稿原计划三处入口，实际只做了详情面板一处。这次补上**卡片右键**这一路。
选右键而不是常驻按钮，理由很简单：卡片操作条已经有 5 个按钮
（打开/批量/收藏/复制/删除），再加会挤掉视觉呼吸空间；右键菜单零版面占用。

### 11.1 菜单结构

```
打开
─────────
重命名预设
复制预设
─────────
清空全部标签页…      ← documentCount > 1 才可用
─────────
删除预设…
```

### 11.2 三个必须做对的点

**① 右键必须先选中，再弹菜单。**
不选中就会出现「右键 A 卡片 → 菜单操作作用于之前选中的 B」。这是右键菜单最经典的坑。
实现里 `card.activated()` 在 `contextMenuRequested` **之前**执行，
测试用语句**先后顺序**断言（`index()` 比较），不是「包含某字符串」——后者保证不了顺序。

**② 坐标要用窗口坐标，不是卡片内局部坐标。**
`eventPoint.position` 是卡片局部坐标，直接传给 `popup(x, y)` 会让菜单弹到左上角。
必须先 `card.mapToItem(null, 0, 0)` 拿到卡片原点再相加。

**③ 「重命名预设」不复用弹窗，改为聚焦详情面板的名称框。**
卡片名与页名只差两个字，两个重命名弹窗并存时用户极易改错对象。
走「选中卡片 + `presetNameField.forceActiveFocus()` + `selectAll()`」这条路，
改的一定是卡片名，而且用户能看到完整的上下文（描述、分类、标签都在旁边）。

### 11.3 命名一致性（防混淆）

| 位置 | 菜单项名称 |
|---|---|
| 卡片右键 | 重命名**预设** |
| 页行 ⋮ | 重命名**标签页** |

两个名字必须字面不同。测试 `test_card_menu_and_tab_menu_names_do_not_collide`
直接断言「卡片菜单里出现『重命名预设』、页菜单里不出现」，防以后有人统一措辞时抹平差异。

### 11.4 全部复用既有流程

菜单项不另写一套逻辑，全部调工作台已有方法：

```qml
onTriggered: root.requestLoad(...)          // 打开
onTriggered: root.requestDuplicate(...)     // 复制
onTriggered: root.requestClearAllTabs()     // 清空（走同一个确认弹窗）
onTriggered: root.requestDelete(...)        // 删除
```

自己再实现一遍会立刻漂移——最典型的是清空时忘了二次确认。
测试 `test_card_menu_reuses_existing_flows` 逐个断言这四个调用存在。

### 11.5 验证

```
tests/test_preset_card_context_menu.py   9 passed
```

用「读 QML 源码断言结构」的方式，因为 offscreen 下 Popup 无法枚举。
真实点击行为另有两个探针：

| 探针 | 验证内容 |
|---|---|
| `docs/audit/_verify_card_context_menu.py` | 17 项：信号声明、右键分支顺序、菜单项启用条件、命名不冲突、清空走同一流程 |
| `docs/audit/_verify_context_menu_real.py` | 真实 `QQuickWindow` + `QTest.mouseClick(RightButton)`，确认右键后 `contextMenuPresetId` 与 `selectedId` 都正确指向该卡片 |

注入退化「把 `activated()` 移到发信号之后」→
`test_right_click_selects_before_opening_menu` 立刻失败。

---

## 十二、缩略图取消接口（2026-11-03 补做）

设计稿最初把 `PresetThumbnailService.cancel()` 列为「不做也行」，理由是
「不取消时本次结果会写回已删除路径，下次 request 因缓存失效重算」。

**这个判断是错的。** 写回的不是「一个待重算的临时状态」，而是**一张内容正确的旧图**：
清空标签页后 `_drop_thumbnails` 删掉文件，后台任务几百毫秒后把它写回来，
`is_cache_valid` 一看「文件在、mtime 比 .cmp 新」直接判定有效 ——
**卡片于是永远显示已清空的内容**，且不会再触发重算。用户视角：清空没生效。

### 12.1 接口

| 方法 | 语义 |
|---|---|
| `cancel(preset_id) -> bool` | 取消该预设待处理任务，返回是否确有待处理任务。幂等。 |
| `cancel_all() -> int` | 取消全部待处理任务，返回数量。 |

`_drop_thumbnails`（清空全部 / 关闭单页 / 删除预设都走它）原本就已经
`getattr(service, "cancel", None)` 探测调用，所以补上方法即自动生效，**调用方无需改动**。

### 12.2 为什么用「代数」而不是「cancelled 集合」

最直觉的写法是维护一个 `_cancelled: set[str]`。它有两个必错点：

**① 取消后重新请求会被误伤。**
典型路径：清空 → 用户点撤销（`undoClearDocuments` 会 `request(force=True)` 重生成）。
旧队列项还在队列里，新任务带着同一个 id 进来；若用集合判断，
新任务一进工作线程就被判定为「已取消」，缩略图再也不出来。

**② 旧任务的收尾会清掉新任务的 `_pending`。**
`_run` 的 `finally` 原本无条件 `self._pending.discard(preset_id)`。
旧任务结束时，新任务还在队列或正在渲染，`pending` 却被清成 0 ——
UI 侧以为任务已结束，结果永远不来，卡片停在占位图。

因此实现给每个 preset 一个**代数**（`_epochs[preset_id]`），`cancel` 时 +1，
入队时把当时的代数写进队列项，工作线程比对世代：对不上即视为作废。
`finally` 里只清「代数仍是自己那一代」的 pending。

### 12.3 三道防护（刻意冗余）

| 位置 | 作用 | 去掉后的表现 |
|---|---|---|
| `_run` 出队后 `_is_stale` → `continue` | 一次渲染都不做，最省 CPU | 白跑约 1.2s/预设，挤占画布预览 |
| `render_preset_thumbnails` 每页开始前 `should_cancel` | 多页只渲染到取消点 | 4 页全渲染完才停 |
| 每页**落盘前** `should_cancel` | 守住唯一会让旧图复活的窗口 | 旧图被写回，卡片显示已清空内容 |

`should_cancel()` 返回真时 `render_preset_thumbnails` 返回 **`{}`**，
不返回半批结果 —— 半批会被调用方当作「已就绪」缓存，其中可能含刚被删掉的文件。

### 12.4 验证

```
tests/test_preset_thumbnail_cancel.py    9 passed
docs/audit/_verify_thumb_cancel.py      16 项全过
```

**注入退化，确认测试能抓**（只跑绿不算验证）：

| 注入的退化 | 被抓到的测试 |
|---|---|
| `finally` 无条件 `discard pending` | `test_request_after_cancel_keeps_new_pending_state` |
| 去掉渲染中的 `should_cancel` 钩子 | `test_cancel_during_render_blocks_writeback` |
| 两道防护同时去掉 | 3 项同时失败（含 `..._prevents_stale_thumbnail_writeback`） |

> 单独去掉 `_run` 的出队检查**不会**让测试失败 —— 逐页钩子仍会拦住。
> 这是刻意的冗余，`test_cancelled_task_skips_rendering_entirely` 锁的是
> **组合行为**（取消后零渲染尝试），不是单条防线。测试注释里写明了这点，
> 避免以后有人单独删掉一条防线而误以为测试失效。

### 12.5 端到端实测

真实 `PresetManagerViewModel` + 真实缩略图服务，4 页预设：

```
1) 缩略图已生成: True            （759 字节）
2) 清空结果: True cleared=4
3) 缩略图已删除: True
4) 清空 3 秒后仍不存在: True     ← 关键：后台任务没有把旧图写回
5) 卡片页数: 0
```

---

## 十三、两个被漏掉的实现（2026-11-03 补做）

用户反馈「一次关闭通过预设卡片的所有标签功能没有实现，修改后保存的功能似乎也没实现」。
核实后确认：**前者实现了一半，后者根本没做**。

### 13.1 清空全部：后端通了，界面没通

`closeAllDocuments(also_close_in_workspace=True)` 的后端逻辑一直是好的
（单测 `test_close_last_document_enters_empty_state` 等都过），但 QML 层有一个致命断点：

```qml
property bool requestConfirmClearTabs: false
onRequestConfirmClearTabsChanged: {
    performClearAllTabs(false)      // ← 写死 false
}
```

对话框里的「同时关闭工作区」开关值**永远传不下去**。用户勾了也没用：
卡片清空了、工作区标签页还在，看起来就是「清空没生效」。

修复：改成 `performClearAllTabs(clearTabsDialog.alsoCloseWorkspace)`。

#### 为什么上一轮没发现
那条桥接属性是给自动化测试用的入口，我上一轮只验到「对话框能打开、确认能执行」，
**没有验证勾选后的实际效果**。而且 Popup 不在 item 树里，`findChild` 找不到它，
连「开关状态」都读不到，于是测试只能测到「点得动」这一层。

这次补了两样：
1. 对话框加 `objectName: "presetClearTabsDialog"`（Popup 需要它才能被 findChild 定位）
2. 根对象加 `alsoCloseWorkspaceOnClear` 镜像属性，与对话框内真值双向同步 ——
   让「开关状态」变成外部可观测、可断言的量

验证：`docs/audit/_verify_clear_all_workspace.py` 6 项。
注入退化（改回写死 `false`）→ `工作区标签页已关闭` 立刻 FAIL（count=3）。

### 13.2 保存：只有「另存为」，没有「存回原卡片」

原有能力：
- `saveCurrent()` / `saveAll()` —— 都走 `save_preset_documents`，**每次生成新 id**
- `renamePreset()` —— 只改名称/描述

所以用户在工作区改完图层后，**没有任何路径把内容存回原来那张卡片**，
只能「另存为」，于是库里堆出一堆重复预设。这就是「保存没实现」的实质。

#### 新增的能力

| 层 | 方法 | 职责 |
|---|---|---|
| PM | `update_preset_documents(preset_id, documents)` | 走 `prepare_document_data` 序列化后覆盖写回**同一个** `.cmp`；mtime 乐观锁 + 原子写；页数变少时把 `cover_index` 重新钳位 |
| PMVM | `savePresetFromWorkspace(preset_id)` | 收集工作区里 `source_preset_id` 匹配的页，按页号排序后交给 PM |
| PMVM | `canSavePresetFromWorkspace()` / `openPageCount()` | 供 QML 判断按钮可用性与文案 |
| QML | 详情面板「保存改动回此预设（N 页）」 | 未打开时禁用并给出 tooltip 说明原因 |

#### 三条设计约束（都不是随手写的）

**① 只收 `source_preset_id` 匹配的页。**
工作区可能同时开着 A 和 B，甚至手动新建的页。一并写回会把别人的内容塞进这张卡。

**② 页名要同时写 `name` 和 `original_tab_name`。**
摘要取名走 `original_tab_name or tab_name or name`，只写一个的话卡片永远显示旧名
——这是本文档 2.3 节就记过的坑，保存路径同样适用。

**③ 页数变少时 `cover_index` 必须重新钳位。**
用户关掉几页再保存，旧封面下标会越界，卡片封面取到不存在的页，缩略图变空白。

#### 验证
```
tests/test_preset_save_from_workspace.py    9 passed
docs/audit/_verify_save_button.py           6 passed（真实 QML，含"改动确实写盘"）
```
注入两处退化，确认测试能抓：
| 注入 | 被抓到 |
|---|---|
| 不按 `source_preset_id` 过滤 | 2 项失败（含 `test_save_does_not_mix_pages_from_other_presets`）|
| 保存改成 `save_preset_documents`（另存为）| 5 项失败 |

### 13.3 为什么这两个漏洞能活到「交付完成」

两次都是同一个原因：**后端单测通过就当成功能完成，没有走界面链路。**
- 清空全部：后端 45 项测试都过，QML 那条「勾选 → 传参 → 关标签」从没验过
- 保存：压根没有对应测试，因为功能不存在

所以现在补的标准是：**凡是要用户在界面上点的功能，必须有真实 QML 探针**
（`docs/audit/_verify_*.py` 里用真实 `QQuickWindow` + 真实 VM），
单测只作为补充，不作为「完成」的依据。
