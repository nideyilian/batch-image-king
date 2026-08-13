---
name: 批图王 Hermes Desktop 工作台
description: 以 Hermes Agent 桌面端工作台为唯一视觉基准的浅色 Qt Quick 图像生产界面
mode: Operate
sourceOfTruth: docs/hermes-desktop-design-system.md
---

# Design System: 批图王 Hermes Desktop 工作台

批图王当前界面完全采用 Hermes 桌面端的浅色工作台语言。旧的深色、玻璃、渐变和装饰卡片方向不再是设计权威；已有业务能力、数据格式和编辑器操作保持不变。

## Creative North Star

**“把复杂生产任务放进一张清晰的桌面工作台。”**

工作区使用暖白表面、近黑文字和细边界。黑色负责主操作，绿色只表示运行状态和健康状态。顶部使用品牌区、编号导航、搜索/命令入口、档案和设置；侧栏、画布和属性区通过表面色与 1 px 分隔线建立关系。

## Visual Rules

- 默认浅色，不以深色为主主题。
- 主操作为黑底白字，状态为绿色点或绿色文字。
- 页面区段不使用卡片包裹；面板使用平面表面和分隔线。
- 矩形组件圆角统一为 0；状态点、色轮手柄和开关滑块等圆形几何元素在组件内单独定义。
- 字体使用 HarmonyOS Sans SC、MiSans 和 Cascadia Mono。
- 编号、英文眉标、状态和文件数据使用等宽字体。
- 图标统一来自 `AppIcons.qml` 的 Lucide 语义注册表。
- 不使用渐变装饰、发光、玻璃模糊、Emoji 或 Unicode 图标。

## Layout

```text
顶部品牌与编号导航 66 px
命令工具栏 44-54 px
文档标签栏 36 px
左侧工具轨 48 px
图层面板 246-276 px
中央画布 弹性区域
属性检查器 368-408 px
底部状态栏 28 px
```

## Tokens

令牌唯一实现位于 `app/qml/components/Theme.qml`。组件库和详细规则位于 `docs/hermes-desktop-design-system.md`。

关键令牌：

- 表面：`bgApp`、`bgBar`、`bgPanel`、`bgRaised`、`bgControl`、`bgHover`、`bgCanvas`
- 边界：`border`、`borderStrong`、`focusRing`
- 文字：`textPrimary`、`textSecondary`、`textMuted`、`textDisabled`
- 操作：`accent`、`accentHover`、`accentPressed`
- 状态：`success`、`warning`、`danger`、`info`
- 尺寸：`controlHeight`、`commandHeight`、`toolButtonSize`、`sectionHeaderHeight`
- Field：`inspectorLabelColWidth`、`inspectorColSpacing`、`compactControlHeight`、`comfortableControlHeight`

## Component Library

基础组件：

`AppButton`、`IconButton`、`AppTextField`、`AppTextArea`、`ValueBox`、`SelectBox`、`SegmentedControl`、`ToggleSwitch`、`AppProgressBar`、`StatusBanner`、`AppDialog`、`AppDrawer`、`AppMenu`、`OptionTile`、`PropertySection`

Hermes 专用组件：

`HermesNavItem`、`HermesPanelHeader`、`HermesSectionLabel`、`HermesStatusDot`

## Accessibility

- 纯图标按钮必须有 tooltip 和 `Accessible.name`。
- 焦点用清晰的黑色边界表达。
- 选中、错误、运行、完成和禁用状态必须同时有文字、图标或空间上下文。
- 最小窗口和 Windows 125%/150% 缩放下，底部操作和错误说明必须可见。

## Engineering Boundary

视觉重做不得改变：

- `Document`、ViewModel、快捷键和导出契约。
- `.cmp` pickle 数据格式。
- 预览、单图导出、批量导出和多标签导出的行为。
- 用户未提交的渲染、图像优化和其他无关改动。
