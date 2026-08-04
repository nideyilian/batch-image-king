# 批图王设计系统（shadcn/ui 规范）

> 本文档定义批图王（PySide6 桌面端）的**统一设计规范与组件库**。设计语言对齐
> [shadcn/ui](https://ui.shadcn.com) 的默认规范（zinc 中性色 + 蓝色 primary），令牌命名与语义
> 与其保持一致，便于团队理解、降低认知成本。
>
> 相关文档：`docs/UI设计规范.md`（既有交互/布局细则，本文档在其之上把「令牌与组件」规范化）。

---

## 1. 架构与单一事实来源

```
app/ui/design_tokens.py    运行期真值（画布色、控件尺寸）—— 暗色调色板由它派生
app/ui/theme/tokens.py     shadcn/ui 语义令牌（背景/前景/主色/…）、间距、圆角、字体、图表色、暗/亮双主题
app/ui/theme/provider.py   由令牌生成全局 QSS（按钮变体/尺寸、卡片、输入、徽章、警示、分割线、进度条、抽屉）
app/ui/dark_theme.py        既有基础样式（画布色、滚动条、复选/滑块/标签页），末尾叠加 provider 的 shadcn 层
app/ui/components/          可复用组件库（见第 4 节）
```

- **令牌是唯一的颜色/尺寸真值**。`design_tokens.py` 仍是画布绘制的权威；`theme/tokens.py` 的暗色令牌
  直接复用它，因此两套不漂移。
- **所有界面自动继承**：`dark_theme.py` 在 `get_complete_style()` 末尾追加 `build_global_stylesheet()`，
  全局 QSS 经 `QApplication.setStyleSheet` 应用后，每个窗口/对话框无需逐个设置样式即可获得 shadcn 外观。
- **零侵入**：shadcn 层全部以「属性选择器 / 角色（role）」作用，仅影响主动设置 `variant/size/role` 的控件，
  历史对话框既有的 `variant="primary/secondary/ghost"` 按钮与现有样式完全兼容，不会被破坏。

---

## 2. 设计令牌（Design Tokens）

通过 `from app.ui.theme import Theme` 访问，**禁止在业务代码写死色值**。

### 2.1 语义颜色（Semantic Colors）

| 令牌 | 含义 | 暗色值 | 亮色值 |
|---|---|---|---|
| `background` | 主背景 / 面板 | `#181818` | `#FFFFFF` |
| `foreground` | 主文本 | `#F4F4F5` | `#09090B` |
| `card` | 卡片 / 分组面 | `#1F1F1F` | `#FFFFFF` |
| `card-foreground` | 卡片内文本 | `#F4F4F5` | `#09090B` |
| `popover` | 弹层 / 下拉 | `#151515` | `#FFFFFF` |
| `primary` | 品牌主色（蓝） | `#2F9CF4` | `#2F9CF4` |
| `primary-foreground` | 主色上的文本 | `#FFFFFF` | `#FFFFFF` |
| `secondary` | 次级面 | `#2A2A2A` | `#F4F4F5` |
| `secondary-foreground` | 次级面文本 | `#F4F4F5` | `#09090B` |
| `muted` | 弱化面 | `#2A2A2A` | `#F4F4F5` |
| `muted-foreground` | 次要文本 | `#8E8E93` | `#71717A` |
| `accent` | hover / 选中面 | `#242B33` | `#F4F4F5` |
| `accent-foreground` | 选中面文本 | `#F4F4F5` | `#09090B` |
| `destructive` | 破坏性操作 | `#FF453A` | `#EF4444` |
| `destructive-foreground` | 破坏性文本 | `#FFFFFF` | `#FAFAFA` |
| `border` | 卡片 / 面板描边 | `#303033` | `#E4E4E7` |
| `input` | 输入框 / 按钮描边 | `#3A3A3D` | `#E4E4E7` |
| `ring` | 焦点环 | `#2F9CF4` | `#2F9CF4` |
| `success` / `warning` / `info` | 状态色 | `#30D158` / `#FF8A3D` / `#55B2FF` | 对应亮色 |

辅助令牌：`primary-hover`(`#55B2FF`)、`primary-pressed`(`#1F7EC8`)、`hover`(`#303236`)。

### 2.2 间距（Spacing，px）

`Theme.spacing(key)`：`xs=4` `sm=8` `md=12` `lg=16` `xl=20` `2xl=24` `3xl=32`

### 2.3 圆角（Radius，px）

`Theme.radius(key)`：`sm=4` `md=6` `lg=8` `xl=12`；基础 `--radius=5`。

### 2.4 字体（Typography）

- 字体族：`Segoe UI, -apple-system, sans-serif`（Windows 下呈现 Segoe UI）
- 字号：`xs=10` `sm=11` `base/md=13` `lg=15` `xl=18` `title=13` `2xl=22`
- 字重：`regular=400` `medium=600` `bold=700`
- 取用：`Theme.font_size("base")` / `Theme.font_weight("medium")`

### 2.5 布局 / 控件尺寸

`Theme.layout("control_height")=30`、`icon_button=36`、`switch_w=52`、`switch_h=30`、
`indicator=16`、`label_width=58`、`motion_ms=150`、`section_gap=8`、`row_gap=6`、`panel_margin=8`。

### 2.6 图表色（Chart Colors）

`Theme.chart_color(i)` 循环取 8 色（蓝/绿/橙/红/灰/浅蓝/紫/黄），用于批量导出报告、统计可视化。

### 2.7 暗 / 亮双主题

```python
from app.ui.theme import Theme
Theme.set_mode("dark")     # 默认
Theme.toggle_mode()        # 暗 <-> 亮
# 切换后需重新应用样式：
from app.ui.theme import apply_theme
apply_theme(app)           # 重新生成全局 QSS + Palette
```

---

## 3. 全局样式如何覆盖所有界面

`main.py` 在启动时调用 `CursorDarkTheme().apply_to_application(app)`。该函数内部：

1. 生成既有基础 QSS（`design_tokens` 派生）；
2. **追加** `build_global_stylesheet()`（shadcn 层）；
3. 应用 `QPalette` 与 Fusion 风格。

因此任何新窗口/对话框只要使用 `QWidget` 体系，即自动获得统一字体、输入框外观、
焦点环、以及「设置了 `variant/role` 的组件」的 shadcn 视觉——**无需逐界面写样式**。

---

## 4. 组件库（app/ui/components）

统一从 `from app.ui.components import ...` 取件。所有视觉由全局 QSS 驱动，组件本身只设置语义属性。

### 4.1 Button（按钮）

变体 `variant`：`default`(主色) / `secondary` / `outline` / `ghost` / `destructive` / `link`
尺寸 `size`：`sm` / `default` / `lg` / `icon`

```python
from app.ui.components import Button, button

ok = Button("确定", variant="default")                 # 或 button("确定", variant="default")
cancel = Button("取消", variant="ghost")
del = Button("删除", variant="destructive")
icon = Button("", variant="ghost", size="icon", icon=QIcon(...))
```

**既有对话框迁移**：原 `QPushButton(text); btn.setProperty("variant","ghost")` 可直接替换为
`Button(text, variant="ghost")`，行为完全一致。

### 4.2 Card（卡片）

```python
from app.ui.components import Card, CardHeader, CardTitle, CardDescription, CardContent, CardFooter

card = Card()
card.add_widget(CardHeader().add_widget(CardTitle("导出设置"))
                             .add_widget(CardDescription("配置批量导出的尺寸与格式")))
card.add_widget(CardContent().add_widget(some_widget))
card.add_widget(CardFooter().add_widget(Button("应用", variant="default")))
```

### 4.3 Input / Label

所有 `QLineEdit / QSpinBox / QDoubleSpinBox / QComboBox / QTextEdit` 已由全局 QSS 统一外观。
提供语义化辅助：

```python
from app.ui.components import Input, Label, field, form_layout

name = Input(placeholder="未命名文档")
lbl = Label("文档名称")                 # role=label（加粗、小号）
muted = Label("可选", muted=True)       # role=muted（弱化）
row = field("宽度", spin_box)           # 「标签 + 控件」单行布局
fl = form_layout()                      # 统一间距的表单布局
```

### 4.4 Tabs / Select

```python
from app.ui.components import Tabs, Select
tabs = Tabs(); tabs.add_tab(widget, "基础")
sel = Select(items=["PNG", "JPG", "WEBP"])
```

### 4.5 基础控件（Controls）

```python
from app.ui.components import Checkbox, RadioButton, Slider, Switch

cb = Checkbox("启用随机位置")
rb = RadioButton("居中")
sl = Slider()                       # 滑块外观由 dark_theme 统一
sw = Switch()                       # 全程序统一开关（复用 PropertySwitch / A2Switch）
sw.set_checked(True)
```

> 开关**必须**用 `Switch`（即现有 `A2Switch` 风格），禁止用原生 `QCheckBox` 当开关，保证全程序同源。

### 4.6 反馈类（Feedback）

```python
from app.ui.components import Badge, Alert, Separator, ProgressBar

Badge("NEW", variant="primary")
Badge("已废弃", variant="outline")
Alert("无法导出", "磁盘空间不足，请清理后重试", variant="destructive")
Alert("已保存", "预设已写入本地", variant="success")
Separator()                                    # 水平分割线
Separator(Qt.Vertical)                         # 垂直分割线
prog = ProgressBar(); prog.set_progress(40)    # 圆角进度条
```

### 4.7 Dialog / Sheet

```python
from app.ui.components import Dialog, Sheet, Button

class MyDialog(Dialog):
    def __init__(self, parent):
        super().__init__(parent, title="设置")
        ...
        self.layout().addWidget(self.button_row([
            Button("取消", variant="ghost"),
            Button("确定", variant="default"),
        ]))

panel = Sheet()    # 右侧抽屉容器（role=sheet）
```

---

## 5. 使用准则（Do / Don't）

**Do**
- 新界面一律从 `app.ui.components` 取件，颜色/尺寸只经 `Theme` 取值。
- 主操作用 `variant="default"`，次要操作用 `ghost`/`secondary`，危险操作用 `destructive`。
- 分组用 `Card`，状态提示用 `Alert`/`Badge`，分隔用 `Separator`。

**Don't**
- 不要在业务代码写死十六进制色值或像素尺寸（破坏令牌体系）。
- 不要新建第三套 QSS / 样式表；全局样式已统一。
- 不要用原生 `QCheckBox` 充当开关；用 `Switch`。
- 不要在对话框里重新实现按钮/卡片样式，复用组件即可。

---

## 6. 迁移清单（历史界面）

1. 顶部加 `from app.ui.components import Button, Input, Card, ...`。
2. `QPushButton(text)` + `setProperty("variant", x)` → `Button(text, variant=x)`。
3. `QLineEdit()` → `Input(placeholder=...)`，行布局用 `field()`。
4. 分组容器 `QFrame(role="section")` → `Card()`。
5. 状态提示 `QMessageBox` 模态框 → `Alert` 行内提示（参考 new_canvas_dialog）。
6. 运行 `python main.py` 验证外观与行为无回归。

> 试点已落地：`app/ui/new_canvas_dialog.py` 已全面采用 `Button / Input / Card`。

## 7. 可视化组件画廊（Showcase）

为方便设计评审与组件验收，提供了可独立运行的可视化画廊，实时展示全部组件与令牌取值，
并支持暗 / 亮主题一键切换。

文件：`app/ui/showcase.py` —— `ComponentShowcase` 窗口类，含 `open_showcase(parent)` 工厂。

### 运行方式

```powershell
# 方式一：独立预览（无需启动主程序）
cd <项目根目录>
python app/ui/showcase.py

# 方式二：在程序内打开（可在主窗口菜单 / 快捷键中接入）
from app.ui.showcase import open_showcase
showcase = open_showcase(parent=self)   # 调用方需保活引用
```

### 画廊内容

| 区块 | 展示内容 |
|------|----------|
| Buttons | 6 变体 × 4 尺寸的完整矩阵，外加禁用态、图标按钮、链接样式 |
| Card | `CardHeader / CardTitle / CardDescription / CardContent / CardFooter` 结构示例 |
| Inputs & Forms | `Input / Select / Label / field()` 表单行 |
| Controls | `Checkbox / RadioButton / Slider / Switch`（统一开关） |
| Feedback | `Badge`(6 变体) / `Alert`(5 变体) / `Separator` / `ProgressBar` |
| Tabs | `Tabs` 多页签容器 |
| Icons | 基于 lucide 风格内嵌 SVG 的 `IconLabel / Icon / icon`，颜色取自主题令牌，主题切换自动重绘；并展示全部 41 个内置图标与 5 种令牌配色 |
| Typography | `Heading(H1/H2/H3) / Text / Lead / Muted / Small / Code / Blockquote / Kbd`，由全局 QSS 的 role 驱动 |
| Colors | 语义令牌色板 + 8 色图表配色，随主题实时刷新 |

顶部工具条提供「切换到亮色 / 暗色」按钮，点击后整个画廊（含色板）立即换肤，
用于验证令牌系统的双主题一致性。

