# 批图王 · 全局 UI / UX 统一设计规范（v1.0）

> 适用范围：批图王（图像批量合成工具）全部桌面端界面，尤其是右侧「属性面板」体系
> （普通图层 / 文字图层 / 异形图层 / 预设面板 / 绑定面板等）。
> 目标：消除当前「文字图层属性」与「普通图层属性」在尺寸、样式、间距、控件风格上的不一致，
> 建立**单一事实来源（Single Source of Truth）**的设计令牌（Design Tokens）与组件规范，
> 供后续所有界面开发 / 重构统一遵循。

---

## 一、问题诊断：为什么两套属性面板不一致？

经代码核查，根因不是「某个控件写错了」，而是**存在两套互不引用、各自硬编码的设计系统**
同时挂载在同一个 `properties_dock` 容器里（见 `app/ui/layer_properties_layout.py`
`self.text_layer_panel` 与普通分组共存于同一 `main_layout`，由
`app/ui/layer_properties_refresh.py` 通过 `show()/hide()` 切换）。

| # | 根因 | 代码位置 | 后果 |
|---|------|----------|------|
| 1 | **两套平行的令牌系统** | 普通面板用 `CursorDarkTheme` + `LayerPropertiesBase._layer_panel_stylesheet()`（混合 `pt`/`px`，控件 24px）；文字面板用 `PropertyPanelA2`（`px`，控件 30px）。两者互不引用。 | 同一容器内控件高度差 6px，肉眼明显不齐 |
| 2 | **卡片/分组组件未统一** | 普通面板用 `CollapsibleGroupBox`（`ui/collapsible_group.py`，标题 32px、圆角 6、边框 `#3A3A3D`、头 `#2A2A2C`）；文字面板用 `QFrame[role="section"]`（`PropertyPanelA2`：圆角 7、边框 `#303033`、头 `#2A2B2E`、标题 36px） | 分组标题高低错落、圆角与描边颜色不同 |
| 3 | **颜色字面量散落硬编码** | `CollapsibleGroupBox` 写死 `#202123/#2A2A2C/#34363A/#3A3A3D`；`_layer_panel_stylesheet` 写死 `#111214/#34363A/#52555B/#151618`；`PropertyPanelA2` 写死 `#2F2F2F/#58636F/#111315/#3A3A3D` | 同样的「输入框边框」出现 `#34363A` 与 `#3A3A3D` 两种色值，细微但割裂 |
| 4 | **开关控件样式完全分裂** | 普通面板用原生 `QCheckBox`（指示器 18px）；文字面板用自绘 `A2Switch`（`QCheckBox` + `QPainter`，52×30） | 同样的「启用/禁用」语义，视觉语言完全不同 |
| 5 | **字号单位不统一** | 全局主题用 `pt`（9pt/8pt）；`_layer_panel_stylesheet` 用 `px`（13px/11px）；`PropertyPanelA2` 用 `px`（12px/13px） | 不同 DPI 下缩放不一致，对比关系漂移 |
| 6 | **作用域互相覆盖** | 文字面板对 `#IntegratedTextPanel` 应用**私有作用域 QSS** 完全覆盖全局主题；普通面板只对 `#layerPropertiesContent` 局部覆盖 | 两者对同类型控件（`QPushButton`/`QSpinBox`）的定义互相冲突 |

> 关键结论：**两套面板的「内容宽度」是一致的（共用 dock + scroll），但「内部控件高度 / 圆角 / 颜色 / 字体 / 开关组件」各自为政**，这是用户感知到的「大小、样式不一致」的直接来源。

---

## 二、设计原则（全局必须遵守）

1. **单一事实来源**：所有颜色、尺寸、间距、圆角、字体都必须来自 `app/ui/design_tokens.py`（新建），禁止在业务文件中写死色值/像素。
2. **同一容器内零差异**：所有「右侧属性面板」子类必须外观一致，切换图层类型时不应出现高度/圆角/配色跳变。
3. **令牌而非字面量**：组件只引用令牌（`TOKENS.input_bg`），不直接写 `#111214`。
4. **px 优先、统一单位**：全程序统一使用 `px`（不混用 `pt`），保障 DPI 下比例稳定。
5. **可访问性下限**：正文/标签对比度 ≥ 4.5:1；所有可点击控件 ≥ 24×24px 命中区；焦点态可见。
6. **状态反馈完整**：hover / pressed / checked / disabled / focus 五种状态在每种控件上都必须定义。
7. **一致性优于新奇**：新面板复用既有组件（统一的 `PropertySection`、`PropertySwitch`、`SegmentButton`），不另起炉灶。
8. **动效克制**：交互过渡 120–200ms，仅用 `color/background/border/opacity`，避免改变布局的位移。

---

## 三、设计令牌（Design Tokens）— 统一取值

> 下列值为**最终裁定值**（已对齐两套系统的优点，取较大一致值），后续全部改引用此处。
> 常量命名沿用现有习惯，便于最小改动迁移。

### 3.1 色彩（对齐既有 `CursorDarkTheme`，统一补全覆盖）

| 令牌 | 值 | 用途 | 原两系统差异（已统一） |
|------|-----|------|------------------------|
| `bg.primary` | `#181818` | 面板/主背景 | 两系统一致 ✅ |
| `bg.secondary` | `#202123` | 卡片/分组背景 | A2 `CARD_BG` ✅ |
| `bg.tertiary` | `#2A2B2E` | 分组标题/表头 | 取 A2 `HEADER_BG`（原 `#2A2A2C` 差 1，统一为 `#2A2B2E`） |
| `bg.elevated` | `#111315` | 输入框/下拉背景 | 取 A2 `CONTROL_BG`（原 `#111214` 统一） |
| `bg.control_alt` | `#242526` | 按钮默认底 | A2 `CONTROL_BG_ALT` ✅ |
| `bg.hover` | `#303236` | 控件 hover 底 | A2 `CONTROL_BG_HOVER` ✅ |
| `border.primary` | `#303033` | 卡片/面板描边 | A2 `BORDER`（原 `#3A3A3D` 统一） |
| `border.soft` | `#34383B` | 次级描边/分割线 | A2 `BORDER_SOFT`（原 `#34363A` 统一） |
| `border.control` | `#3A3A3D` | 输入框/按钮描边 | A2 `BORDER_CONTROL` ✅ |
| `text.primary` | `#F4F4F5` | 主文本 | 一致 ✅ |
| `text.muted` | `#8E95A3` | 次要/提示文本 | 一致 ✅ |
| `text.disabled` | `#606064` | 禁用文本 | 一致 ✅ |
| `accent` | `#2F9CF4` | 主强调（选中/激活） | 一致 ✅ |
| `accent.hover` | `#55B2FF` | 强调 hover | 一致 ✅ |
| `accent.pressed` | `#1F7EC8` | 强调 pressed | 一致 ✅ |
| `success`/`warning`/`error` | `#30D158`/`#FF8A3D`/`#FF453A` | 状态色 | 沿用 `CursorDarkTheme` |

### 3.2 字体与字号（统一 `px`，字体族沿用 `Segoe UI` 栈）

| 令牌 | 值 | 用途 |
|------|-----|------|
| `font.family` | `Segoe UI, -apple-system, sans-serif` | 全局 |
| `font.size.base` | `13px` | 正文/标签（统一为 13，放弃 9pt/12px 混用） |
| `font.size.small` | `11px` | 提示/副标题/section 副标 |
| `font.size.title` | `13px` | 分组标题（**加粗 700**） |
| `font.weight.regular` | `400` | 普通文本 |
| `font.weight.medium` | `600` | 按钮/字段标签 |
| `font.weight.bold` | `700` | 分组标题/强调 |

### 3.3 尺寸 / 间距 / 圆角（统一控件高度 = **30px**）

| 令牌 | 值 | 用途 |
|------|-----|------|
| `control.height` | `30px` | **所有** 输入框/按钮/下拉/分段按钮统一高度（原普通面板 24px → 统一 30px） |
| `control.radius` | `5px` | 输入框/按钮圆角（取原普通面板 5，A2 为 4，统一 5） |
| `card.radius` | `7px` | 卡片/分组圆角（A2 `CARD_RADIUS`） |
| `card.padding` | `10px 8px` | 卡片内边距 |
| `section.gap` | `8px` | 分组之间的垂直间距 |
| `row.gap` | `6px` | 表单项行间距 |
| `panel.margin` | `8px` | 面板整体外边距 |
| `label.width` | `58px` | 字段标签固定宽度（A2 `LABEL_WIDTH`） |
| `switch.size` | `52×30px` | 开关控件尺寸（统一为自绘 `A2Switch` 风格） |
| `indicator.size` | `16px` | 复选/单选指示器（原 15/18 统一为 16） |
| `check.size`（段落 checkbox 命中区） | 高度 30px，指示器 16px | 与普通控件等高 |

### 3.4 动效 / 层级

| 令牌 | 值 | 用途 |
|------|-----|------|
| `motion.duration` | `150ms` | 微交互过渡 |
| `motion.easing` | `ease-out` | 过渡曲线 |
| `z.scrollbar` | 局部 | 滚动条宽度 `9px` |

---

## 四、组件规范（每种控件只此一种实现）

> 建议落地为 `app/ui/property_widgets.py`（统一组件库），普通面板与文字面板**都从它取件**。

### 4.1 属性分组 `PropertySection`（替代 `CollapsibleGroupBox` 与 A2 `section`）
- 容器：`QFrame[role="section"]`，背景 `bg.secondary`，边框 `border.primary`，圆角 `card.radius`。
- 标题栏：高 **36px**，背景 `bg.tertiary`，底部 `1px` `border.soft`，标题 `font.size.title` + 加粗 + `text.primary`。
- 折叠箭头：右侧 `⌄/⌃`，hover 变 `accent.hover`。
- 内容内边距 `card.padding`，行距 `row.gap`。
- **普通面板与文字面板使用同一组件**（原 `CollapsibleGroupBox` 标题 32px / 圆角 6 的差异消除）。

### 4.2 表单项 `PropertyRow`（标签 + 控件）
- 标签：固定宽 `label.width`，`text.primary`，`font.weight.medium`，右对齐。
- 控件占满剩余宽度；多控件同一行时水平间距 `row.gap`。
- 禁用态：控件底色 `bg.secondary`，文字 `text.disabled`。

### 4.3 输入框 `QLineEdit` / `QSpinBox` / `QDoubleSpinBox` / `QComboBox`
- 高度 `control.height`(30)，背景 `bg.elevated`，边框 `border.control`，圆角 `control.radius`，文字 `text.primary`。
- focus：边框变 `accent`。
- 上下调节按钮宽度 18px、透明底。

### 4.4 按钮
- 默认按钮：高 30，底 `bg.control_alt`，边框 `border.control`，圆角 5，hover 底 `bg.hover` + 边框 `accent.hover`，pressed 底 `accent.pressed`。
- 主按钮 `variant="primary"`：底 `accent`，文字白，加粗。
- 分段按钮 `SegmentButton`（对齐/粗体斜体等）：等高 30，checked 态底 `accent` + 文字白。

### 4.5 开关 `PropertySwitch`（统一为自绘开关）
- **全程序统一使用自绘 `A2Switch` 风格**（52×30，`QPainter` 绘制），废弃原生 `QCheckBox` 当开关。
- 轨道：`accent`（开）/ `#3A3C3F`（关）；圆钮白；禁用态灰。

### 4.6 复选 / 单选 `QCheckBox` / `QRadioButton`
- 指示器 **16px**，圆角 4（check）/ 8（radio），边框 `#52555B`，底 `bg.elevated`；checked 底 `accent` + 边框 `accent.hover`。
- 文本 `text.primary`，行高命中区 ≥ 30px。

### 4.7 滑块 `QSlider`
- 轨道高 4px，`border.control` 底；已选段 `accent`；手柄 16px 圆，`accent.hover`，`margin -6px 0`。

### 4.8 颜色样本 `ColorIndicator`
- 固定 30×30，圆角 4，描边 `border.control`，hover 描边 `accent.hover`，点击唤起 `color_picker_dialog_a2`。

### 4.9 分割线 / 滚动条
- 分割线：`1px` `border.soft`，无边距。
- 滚动条：宽 9px，圆角 4，滑块 `border.soft`，hover `text.muted`（沿用 `CursorDarkTheme`）。

---

## 五、属性面板布局统一规则

1. 所有属性面板统一挂在 `properties_dock` 的同一 `QScrollArea` 内，内容宽度跟随 dock（不自行撑宽）。
2. 纵向顺序固定：`基本属性 → 源/内容 → 变换 → 外观/效果 → 高级`，分组可折叠，默认仅展开当前最相关 1–2 组。
3. 同一行多个控件时右对齐、等间距；数值输入右侧可附带单位或重置小按钮（重置按钮高 30、宽 ≤ 42）。
4. 空状态（无选中图层/无内容）：显示居中 muted 提示，不显示残缺控件。
5. 文字图层面板删除「自绘私有 QSS 覆盖」做法，改为引用全局 `design_tokens` + 统一组件，使其与普通面板视觉同源。

---

## 六、落地与迁移方案（给后续开发）

**第一步：建立令牌模块**（新建 `app/ui/design_tokens.py`）
```python
class Tokens:
    BG_PRIMARY="#181818"; BG_SECONDARY="#202123"; BG_TERTIARY="#2A2B2E"
    BG_ELEVATED="#111315"; BG_CONTROL_ALT="#242526"; BG_HOVER="#303236"
    BORDER_PRIMARY="#303033"; BORDER_SOFT="#34383B"; BORDER_CONTROL="#3A3A3D"
    TEXT_PRIMARY="#F4F4F5"; TEXT_MUTED="#8E95A3"; TEXT_DISABLED="#606064"
    ACCENT="#2F9CF4"; ACCENT_HOVER="#55B2FF"; ACCENT_PRESSED="#1F7EC8"
    FONT_FAMILY="Segoe UI, -apple-system, sans-serif"
    FONT_SIZE_BASE=13; FONT_SIZE_SMALL=11
    CONTROL_HEIGHT=30; CONTROL_RADIUS=5; CARD_RADIUS=7
    SECTION_GAP=8; ROW_GAP=6; PANEL_MARGIN=8; LABEL_WIDTH=58
    SWITCH_W=52; SWITCH_H=30; INDICATOR=16
    MOTION_MS=150
```
并把 `CursorDarkTheme` 改为从 `Tokens` 取值（避免双份真值）。

**第二步：统一组件库**（新建 `app/ui/property_widgets.py`）
- `PropertySection`（折叠分组）、`PropertyRow`、`SegmentButton`、`PropertySwitch`、`ColorIndicator`。
- `CollapsibleGroupBox` 与文字面板的 section 构建逻辑收敛到 `PropertySection`。

**第三步：消除私有作用域覆盖**
- 文字面板 `IntegratedTextPanel._panel_stylesheet()` 不再以 `#IntegratedTextPanel` 私有覆盖，改为引用 `Tokens` + 全局主题；其控件高度从 30 保持（已是目标值），但颜色/圆角/边框须与 `Tokens` 一致。
- 普通面板 `LayerPropertiesBase._layer_panel_stylesheet()` 中所有 `#111214/#34363A/#52555B/#151618` 等字面量替换为 `Tokens`；控件高度由 24 升到 30。

**第四步：开关统一**
- 普通面板中所有「用 `QCheckBox` 当开关」的位置，替换为 `PropertySwitch`（即 `A2Switch` 风格）。

**第五步：回归校验**（见第七节）。

---

## 七、一致性校验清单（每次涉及属性面板改动后）

- [ ] 同一 `properties_dock` 下，普通图层 / 文字图层切换时，分组标题高度、圆角、描边颜色无跳变
- [ ] 所有输入框 / 按钮 / 下拉高度均为 30px
- [ ] 输入框描边统一为 `border.control`，focus 变 `accent`
- [ ] 所有「开关」均为自绘 `PropertySwitch` 风格（无原生 checkbox 当开关）
- [ ] 正文/标签对比度 ≥ 4.5:1（`text.muted` 仅用于次要提示）
- [ ] 无硬编码色值／像素（全部来自 `Tokens`）
- [ ] hover / pressed / checked / disabled / focus 五态均已定义
- [ ] 字号统一 `px`，无 `pt` 残留
- [ ] 滚动条 9px、分割线 1px `border.soft`

---

## 八、UX 行为准则（补充）

1. **即时反馈**：参数改动后 150ms 内给出视觉反馈（焦点/数值更新/画布预览），不静默。
2. **防错**：破坏性操作（删除图层、清空）需二次确认；批量导出给出进度与失败率。
3. **空状态与加载态**：无数据有提示；异步生成（AI 生图）期间按钮禁用并显示进度。
4. **键盘可达**：Tab 顺序与视觉顺序一致；可聚焦控件均有可见焦点环（`accent` 描边）。
5. **一致性文案**：同类操作按钮命名统一（如一律「重置」而非混用「复位/重设」）。
6. **不引起布局跳动**：切换面板 / 展开折叠不改变整体宽度，避免内容横向滚动。

---

> 本规范为「当前两套系统」的**收敛裁定**。后续新增任何面板（绑定、预设、批量导出设置等）
> 必须引用 `app/ui/design_tokens.py` 与 `app/ui/property_widgets.py`，不得再引入第三套硬编码样式。
