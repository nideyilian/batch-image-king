# 预设工作台设计说明

> 记录预设中心从「右侧抽屉」升级为「整页三栏工作台」的设计依据、数据契约与已知取舍。
> 最后更新：2026-10-30

## 一、为什么要改

改造前的预设中心是 `AppDrawer` 右侧抽屉（`app/qml/Main.qml` 的 `projectPresetDrawer`）：

- 宽度上限 460px，`ListView` 单行 66px，纯文字（名称 + 尺寸 + 图层数 + 描述）
- 浏览和编辑（名称/描述输入框）挤在同一列
- 生命周期内只有 4 个图标按钮

问题不在「不好看」，在**无法快速识别**：预设是视觉资产，用户靠画面认，不靠名字认。

## 二、对标依据（均为实际查阅的产品文档）

| 参考 | 采取的做法 | 来源 |
|---|---|---|
| **Figma 文件浏览器** | 侧栏固定「最近 / 收藏」入口；卡片带文件缩略图 | Figma Help《Guide to files and folders》 |
| **Canva 首页** | 网格/列表**双视图**；筛选（类型/归属）+ 排序（最近编辑/名称/最相关） | Canva Help《Filter and sort your designs》 |
| **Photoshop 预设管理器** | 五种显示模式（纯文字/小·大缩略图/小·大列表）；拖拽排序跨会话持久；Shift 多选、内联改名 | Adobe Learn《Manage presets with the Preset Manager》 |
| **Eagle 素材库** | 中央**尺寸滑杆**调节预览大小；左侧文件夹树 + 智能文件夹；悬停出操作 | Eagle 支持文档《资源库与界面总览》 |
| **稿定「批量套版」** | 「我的工作台 → 批量创作」流程：模板 → 添加替换项 → 批量替换 → 导出全部 | 稿定帮助《智能设计-批量套版》 |

### 一条反向证据（决定性的）

Figma 在 2026-08 把「带缩略图的项目卡片」改成「扁平文件夹行」后，论坛出现大量抗议：

> 「Designers are highly visual people. Losing the preview is frustrating... The scanability is just not there.」

原话来自 Figma Community Forum《Figma folders》主题。这直接证明：**预设/文件类界面不能退化成纯文字列表**。改造前的抽屉正是被诟病的形态，因此缩略图是本轮的第一优先级，而不是可选项。

## 三、布局

```
┌────────────┬───────────────────────────────────────┬──────────────┐
│ 左侧导航    │  顶部工具条：搜索 / 排序 / 尺寸滑杆 / 视图 │  右侧检查器   │
│ 208px      │                                       │ 300px        │
│            │  ┌────┐┌────┐┌────┐┌────┐            │  大预览       │
│ 全部预设 14 │  │缩略││缩略││缩略││缩略│            │  名称/描述    │
│ 最近使用  2 │  └────┘└────┘└────┘└────┘            │  画布/图层    │
│ 收藏      0 │  悬停浮出：打开/批量/收藏/复制/删除     │  使用记录     │
│ ─────────  │                                       │  主操作按钮   │
│ 分类（动态）│                                       │              │
└────────────┴───────────────────────────────────────┴──────────────┘
```

选择**整页覆盖层**而非继续用抽屉，理由是实测 460px 放不下两列 208px 卡片（含 14px 间距需要 430px + 内边距），三列更不可能。抽屉加宽到能放卡片会挤掉画布，得不偿失。

实现上是 `PresetWorkbench` 作为 `anchors.fill: parent` + `z: 900` 的浮层，**不移除原编辑器结构**，关闭时只隐藏，退出后编辑器状态零重建。

## 四、数据契约

### `PresetManagerViewModel` 新增（`app/qml/viewmodels/preset_manager_view_model.py`）

| 成员 | 类型 | 说明 |
|---|---|---|
| `visiblePresets` | Property QVariantList | 经 scope + category + 搜索 + 排序后的结果 |
| `visibleCount` | Property int | 可见数量 |
| `searchText` / `setSearchText` | str | 搜名称、描述、分类、标签、画布尺寸 |
| `sortMode` / `setSortMode` | str | `recent` / `created` / `name` / `layers` / `used` |
| `scope` / `setScope` | str | `all` / `recent` / `favorite` |
| `category` / `setCategory` | str | 空串表示不限 |
| `categories` | Property QVariantList | `[{name, count}]`，由实际预设聚合，不写死 |
| `favoriteCount` / `recentCount` | Property int | 侧栏计数 |
| `toggleFavorite` | Slot | 写回索引 |
| `requestThumbnail` / `requestAllThumbnails` | Slot | 请求缩略图 |
| `thumbnailReady` | Signal(str) | 单张就绪 |

`presets` 每项新增字段：`modifiedAt`、`category`、`tags`、`favorite`、`lastUsedAt`、`runCount`、`thumbnailUrl`、`thumbnailRevision`。

### 缩略图（`app/utils/preset_thumbnail.py`）

- 路径：`<presets_dir>/thumbs/<preset_id>.png`，长边 512
- 有效性：缩略图存在、非 0 字节、且 mtime 不旧于源 `.cmp`（容差 1s 防文件系统精度抖动）
- 渲染：复用唯一渲染出口 `render_document_to_image(..., quality_profile="speed")`
- 并发：`PresetThumbnailService` 固定 4 worker。实测 6 张串行 4.58s、并发(4) 1.76s（**2.59x**）。不按 CPU 核数放大，因为会互相挤掉渲染器的图层 surface 缓存（默认预算 512MB）
- 写入：先写 `.tmp` 再 `os.replace` 原子替换，避免并发读到半张图

## 五、踩过的坑（都已修，勿回退）

1. **`PresetWorkbench` 必须放在 `ColumnLayout` 外面**。放里面会被当成一个布局子项，只占底部一条，编辑器露在上面。
2. **GridView 的 `cellWidth/cellHeight` 必须按同一公式推导**。原先 `cellHeight` 用 `cardSize * 0.72` 另加常数，和卡片内部 `Layout` 高度不一致，导致列高参差。
3. **缩略图就绪后必须 emit `viewChanged`**。`visiblePresets` 只监听 `viewChanged`，只发 `presetsChanged` 会出现「磁盘有图、界面还是骨架」。
4. **Document 要挂受控父对象**。`Document(parent=None)` 的生命周期由 Python 引用计数决定，工作线程渲染时可能被 GC 提前回收，报 `libshiboken: Internal C++ object (Document) already deleted`。现在挂到函数内的 `QObject()` 上。
5. **后台回调要做存活检测**。`PresetThumbnailService` 的回调在工作线程执行，应用退出后 VM 可能已析构。现在用 `self._shutdown_flag` + `shiboken6.isValid(self)` 双重防护，且 `qml_main` 在 `app.exec()` 返回后主动 `shutdown()`。
6. **侧栏计数要显式给宽度**。`RowLayout` 优先压缩没有宽度约束的子项，计数会被 `fillWidth` 的标签挤掉。
7. **不要用原生 `Slider`**。当前 Qt 样式不支持自定义 `handle`，会刷警告且轨道颜色不跟主题。尺寸滑杆已改为自绘。
8. **QML 根对象的普通 function 不一定能被 `QMetaObject.invokeMethod` 调用**。调试入口 `--select-preset` 因此改用属性 `selectPresetIndex` 触发——属性读写一定可用。

## 六、分类与标签

第二版补上了分类/标签的编辑能力——否则左侧分类树永远只有一个「未分类」，等于摆设。

### 数据层（`app/utils/preset_manager.py`）

| 方法 | 说明 |
|---|---|
| `set_category(preset_id, category)` | 空串/空白归一为「未分类」，不产生空分类节点 |
| `set_tags(preset_id, tags)` | 去空、去重、保序；存成列表以便搜索直接 join |
| `rename_category(old, new)` | 批量改挂所有成员，返回受影响条数 |

分类**没有独立实体**，只存在于预设的 `category` 字段上。这是有意的：维护一张可能悬空的分类表（改名要级联、删除要处理孤儿）成本高于收益，而聚合出分类树的代价可以忽略（预设数量级是百不是百万）。

### 交互

- **右侧检查器**：分类输入框 + 应用按钮；下方 `Flow` 芯片列出所有已有分类，点一下即归类，不用手打。标签输入框支持中英文逗号。
- **左侧栏底部**：新建分类输入框。因为分类不是实体，「新建」= 直接把该名字作为当前筛选，用户随后把预设归入即可。
- **卡片**：底部信息行右侧显示分类角标；「未分类」不显示，避免每张卡都挂一个无信息量的标签。

### 一个易漏的边界

`renameCategory` 必须让**当前筛选条件跟随重命名**。否则用户正停在「女装」分类上点重命名，改完后 `category` 还指着旧名，列表会突然空掉，看起来像数据丢了。实现里已处理并有测试锁定。

## 七、遗留问题

- ~~预设无法拖拽排序~~（**已修**，见第十节）
- ~~多标签预设只取第一个文档做封面~~（**已修**，见第十节）
- ~~老预设的 `blend_mode` 存的是中文~~（**已修**，见下节）。
- ~~分类删除未做~~（**已修**，见第十节）

## 八、`blend_mode` 历史中文值兼容（已修）

### 问题

早期版本把 `blend_mode` 存成中文名（`'正常'` / `'正片叠底'` …），后来改为 0-15 的 int。
`LayerPropertyManager._validate_and_convert_type` 没有 `blend_mode` 专用分支，落到通用
`int(value)` 上，`int('正常')` 抛 `ValueError`，整条属性被吞掉并保留默认值 0。

**这类 bug 不报错、不崩溃，只会让画面悄悄不对**——比崩溃更难发现。

实测存量：28 个图层是中文值，58 个图层根本没有该字段，其余是 int。

### 修复（两层）

1. **读取侧**：在 `_validate_and_convert_type` 加 `blend_mode` 分支，交给
   `app/utils/blend_modes.blend_mode_to_int()` 归一。它是混合模式的唯一权威源，
   已能处理中文名、英文名、`BlendMode.XXX` 形式、int 和未知值（回退 normal）——
   **不在属性层重新实现一套映射**，避免第二份真值来源漂移。

2. **存量侧**：`tools/migrate_blend_mode.py` 把历史文件洗净。约束：
   - 默认 **dry-run**，加 `--apply` 才写
   - 写前自动复制 `.bak-<时间戳>`
   - 只动 `blend_mode` 一个键，不塞入原本不存在的字段
   - 幂等（跑第二遍零改动）

### 验证

- 迁移前先整目录备份到 `presets_backup_<时间戳>`
- 迁移 4 个文件 / 28 个图层；复扫残留 0
- 14 个预设 / 37 个文档 / 162 个图层全部可加载、可渲染
- **像素级对比**：固定随机种子 + 锁定图片源后，迁移前后渲染结果**完全一致**

### 一个容易误判的坑

`快手`、`保险锁头` 两个预设直接对比渲染哈希会不一致，但**这不是迁移造成的**：
这两个预设的图片源是文件夹随机抽图（`current_image_path` 是上次抽中的文件），
每次重新加载 Document 都会重新抽一张。判断迁移是否改变渲染结果，必须
固定随机种子并锁定 `current_image_path`，否则会得到假阳性。

## 九、实机验证发现的两个数据缺陷（已修，2026-10-31）

跑真实入口 `python main.py --show-project-presets` 并截图后，发现两个只有
「真跑起来看」才会暴露的问题——单元测试全绿也发现不了。

### 1. 卡片全部显示「未知画布」

`PresetManagerViewModel.presets` 里写着 `summary = preset`，把
`get_all_presets()` 的索引项当摘要用。但索引项**没有** `canvas_sizes` 和
`total_layers`——这两个只在 `get_preset_summary()` 解析 `.cmp` 后才产生。

修法：合并两者，索引优先（`category` / `favorite` / `last_used_at` 是用户
刚改过的最新值），缺的字段用 summary 补。已加回归测试锁定。

**通用教训**：`summary = preset` 这种「别名赋值」是代码味道——它意味着下游
读取的字段名和上游实际提供的对不上，只是 `dict.get` 的默认值把错误藏住了。

### 2. 素材缺失时缩略图变空且零提示

4 个预设（月亮图 / 快手 / 快手购物 / 分省版式）引用的源素材已被用户删除。
程序不崩溃、能打开，但缩略图几乎全透明，用户会以为程序坏了。

修法：新增 `check_missing_sources()` 扫描首个文档各图层的 `image_source`
是否仍存在；卡片左下角显示红底「素材缺失 N」角标。

注意：`TextLayer` 不接收 `image_source`（反序列化后为 `None`），所以这个
探测只对图片图层有意义——测试里必须用 `document.add_layer(..., image_source=...)`
构造场景，不能用文本图层。

### 3. 顺带修掉的既有偶发测试失败

`test_qml_canvas_drag_updates_real_layer_geometry` 约 1/8 概率失败
（`resize mismatch: before=(354,94)`）。探针的 `wait_stable` 只等图层
`x/y`，没等 `width/height` 和 `artboard.scale`；`setZoomFactor(0.4)` 之后
尺寸要若干帧才重算完，提前算手柄坐标就会超调。

修法：把 `(width, height, artboard.scale)` 一并纳入稳定性判据。
压测 15/15 通过。

## 十、拖拽排序 / 指定封面 / 删除分类（2026-10-31）

三项遗留补齐。设计上都遵循同一条原则：**不引入独立实体，只丰富索引字段**。

### 1. 拖拽排序

- 索引加 `order` 字段（int）。用 `None` 而非 `0` 表示「未参与过排序」，
  才能区分「排第一位」和「还没排过」。
- **只在「手动排序」模式下允许拖拽**。其它排序模式拖完会被排序规则立刻覆盖，
  看起来像"拖了没反应"，比不给拖更让人困惑。
- `setSortMode("manual")` 会先调 `ensure_order()`：按当前展示顺序播种，
  保证用户切过去时看到的顺序**和刚才完全一致**，不会突然重排。
- `movePreset` 以「全部预设」的手动顺序为基准重排，避免受当前筛选影响
  而把不在视图里的预设顺序打乱。
- QML 侧：网格用 `mapToItem` + `cellWidth/cellHeight` 算目标格，
  列表用行高算目标行；插入位置画竖线/横线指示，拖拽中的卡片降透明度浮起。

### 2. 指定封面

- 索引加 `cover_index`（int），缩略图渲染时按它取文档，越界回退首页
  （旧索引没这字段，默认 0 即首页，完全向后兼容）。
- 只有多文档预设才给 `coverCandidates`（单文档返回空列表），
  QML 据此决定是否显示「卡片封面」选择器——没有可选项就不占位。
- 换封面后强制重渲染缩略图并清掉缺失探测缓存。

### 3. 删除分类

- `delete_category(category)` 把成员全改挂「未分类」，**不删任何预设**。
- 「未分类」是兜底桶，不允许删除。
- 正停在被删分类上时，筛选退回全部——否则会停在空列表，看起来像数据丢了。
- UI 上用确认对话框（用户可能只是想改名），删除按钮只在悬停/选中分类行时露出，
  避免侧栏一片叉子。

### 顺带修的布局缺陷

`cellWidth` 原本写死成 `cardSize`（208），中间区域宽度除不尽时会露出半张残卡
（实测 1600 宽 + 右栏展开时最后一列被切一半）。

改成：先按期望宽度算列数 `floor(available / cardSize)`，再把宽度均分给这些列。
`cardSize` 从「卡片宽度」变成「期望列宽」，滑杆仍能控制列数。

## 十一、卡片信息密度升级（2026-11-01）

杰哥反馈「卡片太过简陋，没有快捷按钮」。实测诊断后确认**按钮其实都在**，
但有两个真实缺陷。

### 缺陷 1：所有操作都藏在悬停浮层里

原实现在封面底部叠了一条 `opacity: hovered ? 1 : 0` 的操作条，5 个按钮
（打开/批量/收藏/复制/删除）全部只在该层里。鼠标一移开，卡片只剩图和名字，
用户自然会认为"没有按钮"。

修法：把高频动作**常驻**在信息区第三行。布局取舍：

- 「打开」「批量」用带文字的按钮（主操作 + 次主操作，主色填充 vs 描边）
- 「收藏」保留图标态（状态需要一眼可见，文字反而占地方）
- 「复制 / 导出 / 删除」收进「更多」菜单，避免一行挤 5 个按钮

### 缺陷 2：多页预设只展示首页

14 个预设里有 9 个是多标签（2~9 页），只显示首页等于丢掉 70% 的信息。
「分省版式」「月亮图」这类卡片看起来是空图，实际是封面页恰好缺素材。

修法：

1. **缩略图按页渲染**。`thumb_path_for(presets_dir, id, page)`：
   第 0 页沿用 `<id>.png`（旧缓存不失效），其余 `__pN.png`。
   `render_preset_thumbnails()` 一次渲染全部页，返回 `{页号: 路径}`。
2. **卡片页码圆点**。REPEATER 画点，当前页实心白、其余半透明。
3. **悬停轮播**。900ms 换一页，只在 `hovered && 多页` 时跑
   （不给 14 张卡常驻定时器，避免无谓解码）。

### 两个走了弯路又退回的设计

**堆叠边（Figma 文件卡片那种层叠感）—— 放弃。**

试了两轮：
- 放封面顶部：被「N 页 / 收藏」信息条整条盖住，只剩 1px 灰线（像素级验证出来的）
- 放封面底部：直接压住缩略图内容，很脏

结论：卡片尺寸下（约 200×110 的封面）没有空间表达"层叠"。圆点更合适。

**4px 圆点 —— 太小。**

实测 1x 屏上放大 4 倍才认得出。改成 5px + 半透明深底垫片，任何底图都能分辨。

### 一个被自己误删的函数

重构 `render_preset_thumbnail` 时用 `s.index(...)` 到 `s.index(...)` 整段替换，
把夹在中间的 `check_missing_sources()` 一起删了，启动直接 ImportError。
教训：**按标记位置做整段替换前，先确认区间内还有没有别的定义**。
