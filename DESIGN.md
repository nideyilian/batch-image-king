---
name: 批图王生产控制台
description: 面向电商运营与批量制图人员的高密度、低干扰 QML 工作台
colors:
  bg-app: "#0d1011"
  bg-bar: "#111516"
  bg-panel: "#151a1c"
  bg-raised: "#1a2022"
  bg-control: "#20272a"
  bg-hover: "#293235"
  bg-canvas: "#090c0d"
  bg-selected: "#17352e"
  border: "#2b3437"
  border-strong: "#3b474a"
  text-primary: "#f3f6f5"
  text-secondary: "#aab5b1"
  text-muted: "#84918c"
  text-disabled: "#74807c"
  accent: "#3bd5aa"
  accent-hover: "#67e6c1"
  accent-pressed: "#28b88f"
  accent-soft: "#17352e"
  accent-foreground: "#06271f"
  info: "#5ba7ff"
  warning: "#f2b95f"
  danger: "#f1786d"
  success: "#65d88d"
typography:
  display:
    fontFamily: "HarmonyOS Sans SC, MiSans, Microsoft YaHei UI, sans-serif"
    fontSize: "17px"
    fontWeight: 600
    lineHeight: 1.35
    letterSpacing: "0"
  title:
    fontFamily: "MiSans, Microsoft YaHei UI, sans-serif"
    fontSize: "12px"
    fontWeight: 600
    lineHeight: 1.4
    letterSpacing: "0"
  body:
    fontFamily: "MiSans, Microsoft YaHei UI, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.5
    letterSpacing: "0"
  label:
    fontFamily: "MiSans, Microsoft YaHei UI, sans-serif"
    fontSize: "10px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0"
  data:
    fontFamily: "Cascadia Mono, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
    letterSpacing: "0"
rounded:
  sm: "4px"
  md: "6px"
  lg: "8px"
spacing:
  xs: "4px"
  sm: "6px"
  md: "8px"
  lg: "12px"
  xl: "16px"
  xxl: "20px"
  xxxl: "24px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-foreground}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "34px"
  button-secondary:
    backgroundColor: "{colors.bg-raised}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "0 12px"
    height: "34px"
  input:
    backgroundColor: "{colors.bg-control}"
    textColor: "{colors.text-primary}"
    rounded: "{rounded.sm}"
    padding: "0 9px"
    height: "30px"
  icon-button:
    backgroundColor: "transparent"
    textColor: "{colors.text-secondary}"
    rounded: "{rounded.sm}"
    size: "32px"
---

# Design System: 批图王生产控制台

## Overview

**Creative North Star: "生产控制台"**

批图王不是展示型设计软件，而是长时间、高频率使用的电商图片生产工作台。视觉系统以深色设备控制台为参照：层级清楚、信息紧凑、反馈直接，画布与任务结果始终比界面装饰更重要。品牌存在于精准的生产绿、统一的 Lucide 线性图标和稳定的状态语言中，不依赖渐变、发光或大面积装饰。

界面采用“Operate”模式。高频命令一步可达，复杂能力在属性分区、抽屉和弹窗中渐进呈现；当前文档、选中图层、修改状态、预览状态和导出进度必须持续可见。视觉优化不得改变 ViewModel、快捷键、`.cmp` 格式或渲染导出契约。

**Key Characteristics:**

- 高密度、低干扰，适合连续生产。
- 画布优先，侧栏与弹层不抢夺作品注意力。
- 单一生产绿承担主操作、选中与进度语义。
- 依靠色阶与 1 px 边界建立层级，不使用装饰阴影。
- 全部图标来自统一的 Lucide 语义注册表。
- 1180 × 720 到 1600 × 960 之间保持任务完整可达。

## Colors

色板以近中性的控制台黑灰为基底，以克制的生产绿承担交互强调，并为信息、警告、错误和成功保留独立状态色。

### Primary

- **生产绿（`accent`）：** 仅用于主操作、选中项、当前模式和确定进度；强调色上的内容使用深色前景。
- **生产绿高亮（`accent-hover`）：** 用于 hover 和键盘焦点，不作为大面积背景。
- **生产绿按下（`accent-pressed`）：** 用于 pressed、选中边界和文本选择。

### Secondary

- **信息蓝（`info`）：** 用于说明、参考线和信息状态。
- **作业黄（`warning`）：** 用于运行中、未保存和需要注意的状态。
- **故障红（`danger`）：** 用于失败、危险操作和校验错误。
- **完成绿（`success`）：** 用于任务成功和健康状态，不替代主操作色。

### Neutral

- **控制台底色（`bg-app` / `bg-canvas`）：** 应用底层与画布工作区，提供最低视觉亮度。
- **工具表面（`bg-bar` / `bg-panel`）：** 菜单、命令栏、图层和属性面板。
- **抬升表面（`bg-raised` / `bg-control`）：** 菜单、弹层、输入和分段控件。
- **交互表面（`bg-hover` / `bg-selected`）：** hover 与选中反馈，不能改变布局尺寸。
- **钢灰边界（`border` / `border-strong`）：** 分隔、字段和弹层轮廓。
- **内容文字（`text-primary` / `text-secondary` / `text-muted` / `text-disabled`）：** 四级阅读层次，禁用态仍保持可辨认。

**The One Accent Rule.** 同一视图只有生产绿可表示主操作；状态色只表达状态，不能与主操作竞争。

**The Meaning Beyond Color Rule.** 任何状态都必须同时提供文字、图标或位置上下文，不能只靠颜色传达。

## Typography

**Display Font:** HarmonyOS Sans SC，回退到 MiSans 与 Microsoft YaHei UI。

**Body Font:** MiSans，回退到 Microsoft YaHei UI。

**Label/Mono Font:** 数据与尺寸使用 Cascadia Mono，回退到 Consolas。

字体配对强调紧凑和可扫描性。标题通过字重和表面位置建立层级，字号保持克制；尺寸、坐标和数量使用等宽字体，避免数值变化造成跳动。

### Hierarchy

- **Display**（600，17 px）：抽屉与独立任务标题。
- **Title**（600，12 px）：面板标题、属性分区和重要字段。
- **Body**（400，12 px）：正文、菜单、字段值和按钮文案。
- **Label**（400，10 px）：辅助说明、单位、元数据和空态说明。
- **Data**（400，11 px）：尺寸、坐标、缩放、数量和文件序号。

**The Compact Type Rule.** 工具界面不使用 hero 级字号；层级优先来自字重、间距和表面位置。

**The Zero Tracking Rule.** 所有界面文字字距为 0，不使用负字距，也不随窗口宽度缩放字号。

## Layout

主窗口由 42 px 标题菜单栏、54 px 命令栏、36 px 文档标签栏、48 px 左工具轨、276 px 图层面板、弹性画布、336 px 属性检查器和 28 px 状态栏组成。1320 px 以下图层面板收缩到 246 px，属性检查器收缩到 302 px；中央画布始终获得余下空间。

空间阶梯为 4、6、8、12、16、20、24 px。属性区左右内边距 12 px，字段间距 8 px，分区标题高 40 px。紧凑控件高 28 px，标准输入高 30 px，主命令高 34 px，普通图标按钮命中区 32 × 32 px，左工具轨命中区 36 × 36 px。

弹窗用于需要保护焦点的独立任务；抽屉用于保留画布上下文的预设、数据关系和批量导出。中部列表或空态可伸缩，标题和底部主操作必须在 1180 × 720 下完整可见。长列表滚动，长名称省略，说明文字允许换行。

**The Canvas Priority Rule.** 侧栏不得用固定总宽度挤出横向滚动，任何弹层都不得遮断其自身的完成路径。

## Elevation & Depth

系统不使用装饰性阴影。深度通过五级表面色、1 px 边界、模态遮罩和位置关系表达；菜单、弹窗和抽屉使用抬升表面与强边界，画布保持最深背景。焦点使用清晰的生产绿边界，不使用发光 halo。

**The Flat Production Rule.** 静止表面保持平坦；只有弹层边界、遮罩和交互状态负责建立层级。

## Shapes

形状语言紧凑、机械且克制。输入、按钮和列表项使用 4 px 小圆角；普通容器使用 6 px；弹窗和较大工具表面上限为 8 px。业务面板不得使用药丸形状，圆形只用于开关滑块、状态点和图标语义本身。边界统一为 1 px，选中图层允许额外使用 2 px 左侧强调线。

## Components

### Buttons

- **Shape:** 4 px 小圆角，标准命令高 34 px，水平内边距 12 px。
- **Primary:** 生产绿底配深色文字，每个弹窗或抽屉最多一个主按钮。
- **Hover / Focus:** hover 提亮，pressed 加深，键盘焦点显示 1 px 焦点边界；状态变化 120 ms。
- **Secondary / Ghost / Destructive:** 次操作使用抬升表面，工具操作可用透明 ghost，删除使用危险色文字与明确文案。

### Inputs / Fields

- **Style:** 控件表面、强边界、4 px 圆角，高 30 px；多行编辑器保持同一颜色语言。
- **Focus:** 边界切换到焦点色，不通过阴影扩大控件。
- **Error / Disabled:** 错误使用危险边界；禁用文字与图标降低强调但保持可辨认。

### Navigation

主菜单使用文本；命令栏按文件、历史、创建、排列、预览/导出分组；2-4 个短模式使用等宽分段控件。活动项同时使用底色、边界和文字强调。菜单与下拉框保留原生键盘导航，纯图标按钮必须有延迟工具提示和 `Accessible.name`。

### Layer Rows

图层行高 56 px，固定结构为可见性、缩略图、名称/类型和锁定状态。选中行使用弱强调底、左侧强调线和明确图标状态；层级缩进每级 14 px。

### Property Sections

属性分区不使用外层卡片。40 px 标题行负责折叠、摘要和状态，内容使用 12 px 左右内边距与 9 px 垂直节奏，底部 1 px 分隔线结束分区。

### Dialogs, Drawers & Feedback

Dialog 固定为标题、内容、操作区；Drawer 固定为标题、可滚动/伸缩内容和底部完成路径。Toast 只用于短暂结果，运行、成功、失败和取消使用 `StatusBanner` 常驻当前任务，已知比例使用线性进度条。

### Iconography

图标统一使用 Lucide 线性 SVG，通过 `AppIcons.qml` 语义注册和 `AppIcon.qml` 着色。业务 QML 禁止直接资源路径、Unicode 图标、Emoji 和混合图标字体。普通图标 16 px，工具轨图标 18 px，空态图标 22-24 px。

## Do's and Don'ts

### Do:

- **Do** 让当前文档、选中对象、修改状态和导出状态持续可见。
- **Do** 优先复用 `AppButton`、`AppIcon`、`IconButton`、输入、分段、菜单、弹窗和抽屉组件。
- **Do** 在 1180 × 720、1280 × 760、1600 × 960 以及 Windows 125%/150% 缩放下检查完整任务路径。
- **Do** 为所有纯图标按钮、开关和模式控件提供可访问名称与可见键盘焦点。
- **Do** 保持高频命令一步可达，把高级能力放在正确的上下文中渐进展开。

### Don't:

- **Don't** 在业务 QML 中新增界面色十六进制字面量或直接图标资源路径。
- **Don't** 使用 Unicode 图标、Emoji、渐变装饰、玻璃模糊、发光边缘或大圆角卡片。
- **Don't** 把页面区段包装成卡片，也不要嵌套卡片。
- **Don't** 为视觉统一改变 ViewModel、快捷键、`.cmp` 格式、渲染或导出契约。
- **Don't** 让弹层内容在最小窗口下遮挡输入、错误说明或最终操作。
