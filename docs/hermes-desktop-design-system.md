# 批图王 Hermes Desktop Design System

> 版本：1.0
> 适用范围：`app/qml/` 的桌面工作台、编辑器、侧栏、抽屉、对话框和状态反馈
> 设计基准：Hermes-CN-Desktop `packages/shared-ui` 的 `light-modern` / `dark-modern` 双主题桌面语言
> 实现基准：Qt Quick / QML，共享组件位于 `app/qml/components/`
> 上游适配与许可证：见 `THIRD_PARTY_NOTICES.md`

## 1. 设计结论

批图王的新界面完全采用 Hermes 桌面端的工作台语言，同时提供中性浅色和碳黑暗色主题，**默认深色**（`Theme.qml` 的 `darkMode: true`，2026-10-28 起；此前为默认浅色）；不再沿用旧的蓝绿色深色、玻璃态、渐变、发光和装饰卡片方向。

核心印象是：

- 浅色使用纸白与浅灰工作区，暗色使用碳黑分层表面。
- 浅色以近黑色、暗色以近白色承担主操作和标题文字。
- 细、平、克制的 1 px 边界。
- 方正的控件轮廓，像桌面工具而不是营销卡片。
- 绿色只表示运行状态、健康状态和完成状态。
- 顶部只保留品牌、真实功能导航和单按钮主题切换。
- 信息组织使用英文数据眉标、紧凑标题和可扫描状态；`01 / 02 / 03` 编号仅用于存在先后顺序且有当前步骤反馈的流程，并列导航与动作按钮不显示编号（见 6.2）。
- 图标使用统一的 Lucide 线性图标，不使用 Emoji、Unicode 图标或混合图标字体。

这是一套“工作台”系统，不是官网落地页。视觉必须服务于新建画布、组织图层、调整属性、预览和批量导出。

## 2. 颜色令牌

### 2.1 表面

| 令牌 | 浅色 | 暗色 | 用途 |
| --- | --- | --- | --- |
| `Theme.bgApp` | `#f4f4f3` | `#111111` | 应用最底层、窗口背景 |
| `Theme.bgBar` | `#ffffff` | `#181818` | 顶栏、标签栏、工具轨、状态栏 |
| `Theme.bgPanel` | `#ffffff` | `#181818` | 侧栏、属性面板、抽屉 |
| `Theme.bgRaised` | `#f7f7f6` | `#202020` | 菜单、浮层、次级表面 |
| `Theme.bgControl` | `#ffffff` | `#242424` | 输入框、选择框、普通按钮 |
| `Theme.bgHover` | `#ececeb` | `#2a2a2a` | hover、键盘导航和临时高亮 |
| `Theme.bgCanvas` | `#f7f7f5` | `#111111` | 画布周边工作区 |
| `Theme.bgSelected` | `#e9e9e5` | `#2a2a2a` | 选中对象和当前项的弱底色 |

### 2.2 边界与文字

| 令牌 | 浅色 | 暗色 | 用途 |
| --- | --- | --- | --- |
| `Theme.border` | `#e8e8e5` | `#292929` | 普通分隔线 |
| `Theme.borderStrong` | `#d5d5d2` | `#3a3a3a` | 控件、弹窗和面板边界 |
| `Theme.focusRing` | `#171716` | `#f1f1ef` | 键盘焦点 |
| `Theme.textPrimary` | `#171716` | `#f1f1ef` | 标题、主文案、当前对象 |
| `Theme.textSecondary` | `#3f3f3d` | `#cececa` | 普通正文、按钮和字段值 |
| `Theme.textMuted` | `#656562` | `#a1a19d` | 辅助说明、单位和元数据 |
| `Theme.textDisabled` | `#73736f` | `#a1a19d` | 禁用态，保持可辨识但不参与交互 |

### 2.3 状态

| 令牌 | 浅色 | 暗色 | 语义 |
| --- | --- | --- | --- |
| `Theme.accent` | `#171716` | `#f1f1ef` | 主操作和当前导航 |
| `Theme.accentForeground` | `#ffffff` | `#111111` | 主操作上的内容 |
| `Theme.success` | `#16825d` | `#89d185` | 运行健康、完成和在线 |
| `Theme.warning` | `#9d6b00` | `#cca700` | 运行中、未保存和注意 |
| `Theme.danger` | `#d13438` | `#f48771` | 失败、删除和校验错误 |
| `Theme.info` | `#5c7890` | `#b8b8b4` | 信息、参考线和说明 |

**颜色规则：**

1. 黑色承担主操作，不用绿色做品牌按钮。
2. 绿色只能表达状态，不能与主操作竞争。
3. 错误、警告和成功必须同时有文字或图标，不能只靠颜色。
4. 不使用大面积渐变、霓虹边缘、玻璃模糊或装饰发光。
5. 主题由右上角太阳/月亮按钮直接切换并持久化；两套主题只改变语义令牌，不改变布局、密度和信息结构。
6. 文本选区统一使用 `Theme.selectionBackground / Theme.selectionForeground`，确保浅色与暗色始终成对反色；禁用态直接使用禁用语义色，不再叠加整控件透明度造成二次衰减。

## 3. 字体与排版

| 层级 | 字体 | 大小 | 字重 | 用途 |
| --- | --- | --- | --- | --- |
| Display | `HarmonyOS Sans SC` | 15-17 px | DemiBold | 工作台标题、对话框标题 |
| Body | `MiSans` | 11-12 px | Normal | 正文、菜单、按钮和字段 |
| Label | `MiSans` | 10 px | Normal | 辅助信息、单位和说明 |
| Data | `Cascadia Mono` | 9-11 px | Normal/DemiBold | 编号、版本、坐标、文件名和状态数值 |

字体回退顺序：

```text
HarmonyOS Sans SC -> MiSans -> Microsoft YaHei UI
MiSans -> Microsoft YaHei UI
Cascadia Mono -> Consolas -> monospace
```

排版规则：

- 字距保持 `0`，不使用负字距。
- 工作台不使用网页 Hero 级字号。
- 标题通过字号、字重和位置建立层级，不依赖颜色渐变。
- 数据、版本、快捷键和尺寸使用等宽字体。
- 长名称优先省略，中等长度说明允许换行。

## 4. 尺寸与布局

### 4.1 空间阶梯

```text
4 / 6 / 8 / 10 / 12 / 16 / 20 / 24 px
```

### 4.2 控件

| 控件 | 尺寸 |
| --- | --- |
| Field 紧凑密度 | 24 px |
| Field 舒适密度 | 32 px |
| 标准命令 | 34 px |
| 图标按钮 | 32 x 32 px |
| 左侧工具按钮 | 32 x 32 px |
| 属性分区标题 | 38 px |
| 普通分隔线 | 1 px |
| 矩形组件圆角 | 0 px |
| 圆形几何元素 | 在组件局部定义 |

### 4.3 工作台结构

```text
顶部品牌与导航区       54 px
命令工具栏             44-54 px
文档标签栏             36 px
左侧工具轨             48 px
图层面板               默认 246-276 px，可调 200-420 px
中央画布               弹性区域
属性检查器             默认 320-352 px，可调 288-560 px
底部状态栏             28 px
```

中央画布始终获得剩余空间。图层面板和属性检查器之间分别提供 8 px 宽的拖拽命中区，视觉上只显示 1 px 分隔线；拖动可调整宽度，双击恢复默认，用户选择会在下次启动时保留。侧栏不能制造横向滚动；对话框和抽屉不能遮住自身的确认、错误或取消路径。

## 5. 工作台结构

### 5.1 顶部

顶部从左到右固定为：

1. 产品标识和名称，不显示重复的英文副标题。
2. 编号导航：`01 画布`、`02 预设`、`03 导出`。
3. `04 命令`，打开完整命令菜单。
4. 主题按钮：月亮表示可切换到暗色，太阳表示可切换到浅色；点击直接切换并持久化，不使用下拉菜单。

编号不是装饰，它用于保持复杂工作台的空间记忆和键盘导航顺序。

### 5.2 左侧工具轨

左侧工具轨只放高频工具。工具图标 18 px，命中区 32 px，当前工具使用黑色或浅灰底，不使用彩色发光。

### 5.3 图层面板

图层行保留可见性、缩略图、名称、类型和锁定状态。当前行使用浅灰背景、1 px 边界或左侧细强调线，不能使用大面积绿色。

### 5.4 属性面板

属性区不使用嵌套卡片，也不折叠分区。页签承担一级导航，具体分区标题承担二级导航，不再插入“对象 / 内容 / 外观”等重复模块标题。标准 `HermesField` 对应上游 Field 的 160 px 标签列与 16 px 间距；属性检查器启用 compact 适配，主标签列为 64 px，双参数字段使用 52 px 子标签列。章节标题与字段标签统一左对齐到分区边线；标签始终单行完整显示，禁止使用省略号。属性检查器统一采用 28 px 控件行，并以 8 px 行距和 12 px 分区内边距建立稳定节奏。字段默认单列；当字段网格实际宽度达到 320 px 时，只有短值和明确成对的参数切换成双列，低于阈值立即恢复单列。分区边距、字段间距、标签列和输入框隐式尺寸全部落在 4 px 栅格上；侧栏变宽时扩展控件列，不改变标签列基线。控件区的实际隐式高度决定字段高度，不能被固定行高截断。

## 6. 组件库

组件均位于 `app/qml/components/`，并已注册到 `qmldir`。

### 6.1 基础组件

| 组件 | 用途 |
| --- | --- |
| `AppButton` | 主按钮、次按钮、Ghost、危险操作 |
| `IconButton` | 工具按钮、纯图标命令、关闭和设置 |
| `AppTextField` | 单行输入 |
| `AppTextArea` | 多行输入 |
| `ValueBox` | 数字、尺寸、颜色和带单位字段 |
| `SelectBox` | 下拉选择 |
| `SegmentedControl` | 2-4 个模式切换 |
| `ToggleSwitch` | 二元开关 |
| `AppProgressBar` | 批量任务和下载进度 |
| `StatusBanner` | 常驻运行、成功、错误反馈 |
| `AppDialog` | 模态任务 |
| `AppDrawer` | 保留工作区上下文的侧抽屉 |
| `AppMenu` | 菜单和命令列表 |
| `OptionTile` | 少量互斥或可选配置项 |
| `PropertySection` | 属性面板分区 |

### 6.2 Hermes 专用组件

| 组件 | 上游契约映射 |
| --- | --- |
| `HermesField` | `shared-ui/components/field` 的 label / hint / error / required / orientation |
| `HermesPageTabs` | `shared-ui/components/page-tabs` 的 40 px 页签、底边选中态与方向键导航 |
| `HermesAdaptiveFieldGrid` | 属性检查器双列阈值适配；不改变字段业务语义 |


#### `HermesNavItem`

用于顶部导航项；**默认不显示编号**。`index` 只在「存在先后顺序且有当前步骤反馈的流程」里配
`showIndex: true` 使用——并列导航和动作按钮显示 `01/02/03` 会被误读成必须依次完成的步骤
（TDesign / Ant Design 的 Steps 都限定在有先后关系的任务流程）。`description` 用于 tooltip，
必须写清「点了会发生什么」，不要复读 `text`。

并列入口保持一点直达：高频动作不折叠到「更多操作」之类的一级菜单里，否则每次操作都要
多一次展开点击；顶层只收纳真正的低频命令。`HermesNavItem` 的 `onClicked` 直接绑定动作，
不再套一层菜单。

去重靠**删重复项**，不靠**加折叠层**：同一个功能同屏只留一个可见主按钮（顶栏 / 工具栏 /
空态首页各按上下文归属，标签栏 `+` 例外）；命令菜单只收录「能标注真实快捷键」或
「别处没有按钮入口」的命令，用来查命令和学快捷键，不做第二个工具栏。0 引用的菜单
（曾经同时存在 6 个 `AppMenu`，无一 `.popup()`）直接删除，删除前先把只在里面可达的命令迁出。

```qml
HermesNavItem {
    text: "新建画布"
    iconName: AppIcons.image
    description: "设置尺寸后打开一张空白画布（Ctrl+N）"
    onClicked: window.openNewCanvasDialog()
}
```

状态：

- 默认：透明背景、主文字。
- hover：`Theme.bgHover`。
- active：`Theme.accent` 黑底白字。
- disabled：透明度降低，但仍保持可读。

#### `LabeledToolButton`

用于工具栏里「图标语义容易误解」的动作。纯图标按钮的作用只能靠 tooltip 才知道，
所以易混淆的高频动作用「图标 + 短文案」。

**按窗口宽度收起**：`showLabel: window.toolbarLabelsVisible`（阈值 1480）。
窗口最小宽度是 1180，全部带文案约需 1500px，硬塞会裁切或换行；窄窗口退回纯图标，
`tooltip` 始终保留，所以不会丢失信息。

**禁用态仍可悬停**：`IconButton` 的 `MouseArea` 跟着 `enabled` 一起关，禁用时看不到
tooltip。按钮置灰时更需要知道它能干什么，所以这里 `hoverEnabled` 常开，只在 `onClicked`
里判断 `enabled`。

```qml
LabeledToolButton {
    iconName: AppIcons.link
    text: "图层绑定"
    tooltip: "图层绑定管理：设定批量出图时哪几层一起换图"
    showLabel: window.toolbarLabelsVisible
    enabled: window.hasOpenDocument && !workspace.operationsBlocked
    onClicked: window.openDataRelations(0)
}
```

工具栏分组（从左到右，组间 `Divider` 分隔）：

| 组 | 内容 | 后续文案策略 |
| --- | --- | --- |
| ~~新增~~ | **已上提到顶栏**（图层 / 文字 / 异形） | 见下方「顶栏 vs 工具栏」 |
| 文件 | 打开、保存 | 纯图标（通用语义） |
| 历史 | 撤销、重做 | 纯图标（PS/Figma 通用） |
| 数据 | 图层绑定、尺寸匹配 | **带文案**：决定批量出图换图与孔位贴合，不是排版动作 |
| 对齐 | 对齐/分布/居中/匹配画板 | 紧凑图标组（图标即语义，且数量多） |
| 输出 | 重绘预览、导出单张、跨标签导出、批量导出、检查更新 | 三种导出**必须带文案**区分作用域 |

**顶栏 vs 工具栏的分界判据**（2026-11-05）：按「是否依赖选中态」分，不按「重要程度」分。

- **顶栏** = 全局动作。任何时候都可用、结果不取决于当前选了什么：新建画布、图层、文字、异形，
  以及导航（预设中心、更多命令）。顶栏 6 个入口在 1180px 最小宽度下约占 790px，装得下。
- **工具栏** = 依赖选中图层的编辑动作（撤销、对齐、分布）+ 数据配置 + 输出。
  这些按钮 disabled 的频率高，靠近画布更合理；放进顶栏会被一堆置灰按钮淹没。

依据：Figma 顶栏放的是创建类工具（带文字标签），属性类放右侧面板；Photoshop 顶部选项栏
是**当前工具的属性**而非全局动作，全局动作在菜单。共同点是「第一行放创建与输出，第二行放针对选中的编辑」。

品牌标识兼作导航：LOGO 点击 = 打开预设工作台（首页），**不是**关闭文档。
关闭标签会触发未保存确认并丢掉编辑状态，首页属于导航、不应有销毁语义。
预设工作台是 `z: 900` 整页覆盖层，会盖住顶栏，所以工作台顶部必须自带同一套品牌标识，
否则「LOGO 在两种模式下都存在」不成立。

#### `HermesPanelHeader`

用于图层面板、属性面板、抽屉和工作区工具标题。

```qml
HermesPanelHeader {
    eyebrow: "LAYER STACK"
    title: "图层"
    detail: "当前文档中的素材和文字"
    iconName: AppIcons.layers

    IconButton {
        iconName: AppIcons.more
        tooltip: "更多操作"
    }
}
```

#### `HermesSectionLabel`

用于局部内容的编号、英文眉标、标题和说明。

```qml
HermesSectionLabel {
    index: "03"
    eyebrow: "EXPORT SETTINGS"
    title: "批量导出"
    detail: "为当前文档设置输出格式和目录"
}
```

#### `HermesStatusDot`

用于顶部运行状态、底部状态栏和任务列表状态。

```qml
HermesStatusDot {
    tone: "success"
    label: "快速预览"
    compact: true
}
```

## 7. 交互状态

### Button

- 默认：白底、1 px 灰边界。
- hover：浅灰底。
- pressed：黑色或深灰底。
- primary：黑底白字。
- destructive：浅红底、红字、红边界。
- focus：黑色 1 px 边界。
- disabled：降低透明度，不改变布局尺寸。

### Input

- 默认：白底、1 px `borderStrong`。
- focus：1 px 黑色焦点边界。
- error：浅红底或红色边界。
- placeholder：`textMuted`。
- 不使用阴影扩大焦点面积。

### Dialog / Drawer

固定结构：

```text
标题区
分隔线
内容区
错误/说明区
底部操作区
```

一个任务最多一个主操作。取消、关闭和删除都必须有明确文字或可访问名称。

### Loading / Progress

已知比例使用线性进度条。未知比例使用状态文案和旋转图标。批量导出必须同时展示任务状态、完成数量和取消入口。

## 8. 图标与可访问性

- 所有图标从 `AppIcons.qml` 语义注册表取用。
- 普通图标 15-16 px，工具轨 18 px，状态图标 13-17 px。
- 纯图标按钮必须设置 `tooltip` 和 `Accessible.name`。
- 所有输入、开关、分段控件和弹窗操作支持键盘。
- 选中、错误、运行和禁用状态不能只靠颜色表达。

## 9. 禁止项

- 深色渐变玻璃卡片。
- 大面积发光、霓虹、阴影光晕。
- 非圆形业务控件使用圆角。
- 嵌套卡片。
- Emoji、Unicode 图标和无语义图标字形。
- 用绿色替代所有主操作。
- 在业务 QML 中新增硬编码颜色。
- 为了视觉改造修改 `.cmp`、渲染、导出、快捷键和 ViewModel 契约。

## 10. 迁移清单

1. 所有新 QML 页面优先使用 `HermesPanelHeader`、`HermesSectionLabel` 和 `HermesStatusDot`。
2. 新按钮统一使用 `AppButton` 或 `IconButton`。
3. 新输入统一使用 `AppTextField`、`AppTextArea`、`ValueBox` 和 `SelectBox`。
4. 新状态统一使用 `StatusBanner`、`AppProgressBar` 和 `HermesStatusDot`。
5. 任何新增颜色先进入 `Theme.qml`，业务界面不得直接写色值。
6. 每次修改工作台后检查 `1180 x 720`、`1280 x 760`、`1600 x 960`。
7. Windows 125% 和 150% 缩放下，检查长文件名、长图层名、错误文案和弹窗底部操作。
