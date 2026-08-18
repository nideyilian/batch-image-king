# 批图王深色工作台设计系统

> 适用范围：PySide6 桌面端主窗口、停靠面板、属性面板、弹窗、菜单、状态反馈和开发工具。

## 1. 设计目标

批图王采用安静、紧凑、适合长时间工作的深色工作台。设计语言参考 shadcn/ui 的语义令牌、组件变体和可访问状态，但所有实现均为 Qt 原生控件，不引入 React、Tailwind 或 WebView。

本阶段只交付 `dark` 皮肤。后续皮肤通过注册语义令牌扩展，不修改业务窗口。

核心原则：

1. 业务代码表达语义，不表达具体颜色。
2. 全局 QSS 负责一致的基础状态，公共组件负责稳定 API。
3. 图像内容色、用户选择色和导出色值不属于界面主题色。
4. 历史窗口可由语义适配器覆盖，新代码必须显式使用公共组件或动态属性。
5. 深色工作台不等于单一色相；中性色、蓝色主操作、绿/橙/红状态色必须职责分明。

## 2. 架构

```text
app/ui/design_tokens.py
        |
        v
app/ui/theme/tokens.py        语义令牌、皮肤注册表
        |
        +--> provider.py      QPalette + 全局 QSS
        +--> polisher.py      历史 Qt 控件语义适配
        |
        v
app/ui/components/*           公共组件
        |
        v
主窗口 / 面板 / 弹窗 / Showcase
```

兼容入口：

- `CursorDarkTheme.apply_to_application(app)`：应用默认深色主题并安装语义适配器。
- `DialogA2`：仅保留布局常量、属性标记和兼容方法，颜色来自 `Theme`。
- `app/ui/ui_primitives.py`：历史反馈组件，新增代码优先使用 `app.ui.components`。

## 3. 皮肤契约

### 3.1 默认皮肤

```python
from app.ui.theme import Theme

Theme.skin()               # "dark"
Theme.available_skins()    # 已注册皮肤
Theme.color("primary")
```

`Theme.mode()` 和 `Theme.set_mode()` 是历史兼容别名。新增代码使用 `skin()` 和 `set_skin()`。

### 3.2 注册新皮肤

```python
from app.ui.theme import Theme, apply_theme

colors = Theme.colors()
colors.update({
    "background": "#101214",
    "card": "#171A1D",
    "primary": "#37A5FF",
})

Theme.register_skin("graphite", colors)
Theme.set_skin("graphite")
apply_theme(app)
```

注册数据会被复制，外部字典后续修改不会污染主题。缺少必需语义色时注册会失败；切换未知皮肤会抛出 `KeyError`，避免界面静默进入混合状态。

### 3.3 必需语义色

| 类别 | 令牌 |
| --- | --- |
| 基础表面 | `background`、`card`、`popover` |
| 文本 | `foreground`、`card-foreground`、`popover-foreground` |
| 操作 | `primary`、`primary-hover`、`primary-pressed`、`primary-foreground` |
| 次级表面 | `secondary`、`muted`、`accent` 及对应 foreground |
| 边界 | `border`、`input`、`ring`、`hover` |
| 状态 | `destructive`、`success`、`warning`、`info` |

## 4. 结构令牌

### 4.1 间距

| 名称 | 像素 | 用途 |
| --- | ---: | --- |
| `xs` | 4 | 图标与短标签 |
| `sm` | 8 | 紧凑控件间距 |
| `md` | 12 | 默认内容间距 |
| `lg` | 16 | 区块内边距 |
| `xl` | 20 | 大区块间距 |
| `2xl` | 24 | 页面级留白 |
| `3xl` | 32 | 稀疏展示页 |

属性面板优先使用 `xs/sm/md`；业务工作台不得使用营销页式大留白。

### 4.2 圆角与尺寸

| 令牌 | 值 |
| --- | ---: |
| `radius.sm` | 4 px |
| `radius.md` | 6 px |
| `radius.lg` | 8 px |
| 默认控件高度 | 30 px |
| 大控件高度 | 36 px |
| 图标按钮 | 36 x 36 px |

卡片圆角不得超过 8 px；徽章和状态点可使用胶囊圆角。

### 4.3 排版

- 正文：13 px，常规字重。
- 辅助文字：10-11 px，仅用于状态、脚注和字段说明。
- 紧凑面板标题：13-15 px，中等或粗体。
- Showcase 一级标题：22 px；不得用于业务面板。
- 字体优先使用 Segoe UI / Microsoft YaHei 系统回退。
- 字距固定为 0，不随窗口宽度缩放字体。

## 5. 组件清单

组件从 `app.ui.components` 导入。包当前公开 72 个类、工厂、常量和兼容别名。

### 5.1 操作

| 组件 | Qt 基础 | 用途 |
| --- | --- | --- |
| `Button` | `QPushButton` | 明确命令 |
| `IconButton` | `QPushButton` | 熟悉图标工具，必须有 tooltip |
| `ButtonGroup` | `QFrame` | 相邻命令集合 |
| `Toggle` | `QToolButton` | 单个可保持状态的工具 |
| `ToggleGroup` | `QButtonGroup` | 多个工具状态 |
| `SegmentedControl` | `QButtonGroup` | 互斥模式 |
| `Kbd` | `QLabel` | 快捷键展示 |

Button 变体：

- `default`：当前上下文的唯一主操作。
- `secondary`：普通次级操作。
- `outline`：取消、返回或低强调命令。
- `ghost`：工具栏、行内图标操作。
- `destructive`：删除、覆盖、取消正在执行的任务。
- `link`：跳转或文档链接。

`primary` 是历史别名，新增代码使用 `default`。

按钮尺寸通过 `uiSize` 动态属性实现：`sm/default/lg/icon`。不要使用 `size`，它与 Qt 内建 `QWidget.size` 冲突。

### 5.2 表单

`Input`、`Textarea`、`NumberInput`、`Select`、`ComboBox`、`MultiSelect`、`Checkbox`、`RadioGroup`、`Switch`、`Slider`、`Field`、`InputGroup`、`ColorSwatch`。

规则：

- 二元功能开关使用 `Switch`；多项独立选择使用 `Checkbox`。
- 互斥的 2-4 个模式优先使用 `SegmentedControl`；长选项使用 `RadioGroup`。
- 数字值使用 `NumberInput`/SpinBox，不用文本框模拟。
- `Field.set_error()` 同时展示错误文案并设置 `invalid` 状态。
- 颜色选择入口显示真实色样；色值属于用户内容，可以动态绘制。

### 5.3 布局

`Card`、`Tabs`、`Accordion`、`ScrollArea`、`Resizable`、`Sidebar`、`Separator`、`AspectRatio`、`Sheet`。

- 工作台主区域使用 `Resizable/QSplitter`，允许用户调整面板宽度。
- 属性分组使用 Accordion/Collapsible；默认只展开当前高频区块。
- 页面区段保持无框；Card 只用于确实需要边界的独立对象。
- 禁止 Card 内再放装饰性 Card。

### 5.4 弹层与菜单

`Dialog`、`AlertDialog`、`Popover`、`DropdownMenu`、`ContextMenu`、`CommandPalette`。

- 不可逆操作使用 `AlertDialog`。
- 小型上下文设置使用 `Popover`，复杂设置使用 `Dialog` 或侧边 `Sheet`。
- 菜单和命令面板必须保留 Qt 原生键盘导航。
- 不用弹窗展示普通成功结果；使用 Toast 或状态栏。

### 5.5 反馈与数据

`Badge`、`Alert`、`Toast`、`ProgressBar`、`Spinner`、`Skeleton`、`EmptyState`、`Table`、`FileDropZone`。

- `Toast`：非阻塞、短暂结果。
- `Alert`：需要留在当前上下文中的说明或错误。
- `Spinner/Skeleton`：未知时长或内容加载。
- `ProgressBar`：已知完成比例。
- `EmptyState`：标题、原因和最多一个主操作。
- `FileDropZone`：只筛选和发出文件路径，不处理图层业务。

## 6. 状态规范

所有交互组件必须覆盖：

| 状态 | 要求 |
| --- | --- |
| normal | 对比清楚，不抢夺画布注意力 |
| hover | 表面或边界发生变化，不改变布局尺寸 |
| pressed | 比 hover 更明确 |
| focus | 可见 `ring` 边界，支持键盘导航 |
| disabled | 文本和表面弱化，仍可辨认用途 |
| invalid | 使用 destructive 边界并提供文字原因 |
| loading | 禁止重复提交，显示 Spinner/Progress |

状态色不能单独承担含义。错误、警告和成功必须同时有文字、图标或上下文标签。

## 7. 语义适配器

`app/ui/theme/polisher.py` 在历史控件首次显示时补齐：

- `QDialog -> role=dialog`
- 默认确认按钮 -> `variant=default`
- 取消按钮 -> `variant=outline`
- 破坏性按钮 -> `variant=destructive`
- 普通按钮 -> `variant=secondary`
- 工具按钮 -> `variant=ghost`
- `QProgressBar -> role=progress`
- `QGroupBox -> role=section`
- `QTabWidget -> role=tabs`

显式设置的属性优先，适配器不会覆盖。适配器是迁移保障，不是新增界面继续直接使用裸控件的理由。

## 8. 可访问性

- 图标按钮必须设置 `toolTip` 和 `accessibleName`。
- 表单标签必须紧邻或关联控件。
- 默认按钮每个 Dialog 最多一个。
- Tab 顺序应与视觉阅读顺序一致。
- 焦点态不得被局部 QSS 删除。
- 文本与背景以 WCAG AA 对比度为目标。
- 最长中文标签和 125%/150% Windows 缩放下不得截断或重叠。

## 9. 使用示例

```python
from app.ui.components import Button, Field, Input, SegmentedControl

name_field = Field("文档名称", Input(placeholder="未命名文档"))
mode = SegmentedControl(items=[("fit", "适应"), ("fill", "填充")])

cancel = Button("取消", variant="outline")
save = Button("保存", variant="default")
delete = Button("删除", variant="destructive")
```

动态属性迁移：

```python
legacy_button.setProperty("variant", "secondary")
progress_bar.setProperty("role", "progress")
hint_label.setProperty("role", "muted")
```

## 10. 禁止事项

- 不在业务文件写固定界面色，如 `color: #8E8E93`。
- 不创建第四套主题或弹窗 QSS。
- 不用绿色普通按钮代替主操作语义。
- 不用 Checkbox 表示应当即时生效的开关。
- 不为工具栏熟悉图标额外添加文字胶囊按钮。
- 不把 Web 组件包安装进 Python 桌面运行时。
- 不为了统一视觉改变信号连接、模型状态或导出行为。

## 11. 上游筛选说明

参考项目：[awesome-shadcn-ui](https://github.com/birobirobiro/awesome-shadcn-ui)。

采用的是适合桌面图像工具的交互模式，而不是源码依赖。Avatar、Calendar、Carousel、Breadcrumb、Pagination、OTP、Marquee、NavigationMenu 等组件在当前程序没有明确工作流，不进入运行时组件库。若未来出现真实需求，应先补用户流程和状态设计，再增加组件。

## 12. 验证

```powershell
# 公共组件与主题测试
python -m pytest tests/test_theme_skin_registry.py `
  tests/test_theme_polisher.py `
  tests/test_ui_components_actions_forms.py `
  tests/test_ui_components_layout_overlays.py `
  tests/test_ui_components_feedback_data.py

# 组件画廊
python app/ui/showcase.py

# 全量回归
python -m pytest
```

视觉验收至少覆盖 1280 x 800 和 900 x 700，检查深色背景、焦点、长文本、禁用态、空状态、进度状态和弹层层级。
