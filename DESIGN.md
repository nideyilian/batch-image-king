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
图层面板 默认 246-276 px，可调 200-420 px
中央画布 弹性区域
属性检查器 固定 320 px（完整显示参数栅格的最小宽度）
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
- 尺寸：`inputHeightSm`、`buttonHeightMd`、`tabHeight`、`switchWidth`、`switchHeight`
- Field：`fieldHorizontalLabelWidth`、`fieldHorizontalGap`、`inspectorLabelColWidth`、`inspectorCompactLabelColWidth`、`inspectorPairBreakpoint`

## Component Library

基础组件：

`AppButton`、`IconButton`、`AppTextField`、`AppTextArea`、`ValueBox`、`SelectBox`、`SegmentedControl`、`ToggleSwitch`、`AppProgressBar`、`StatusBanner`、`AppDialog`、`AppDrawer`、`AppMenu`、`OptionTile`、`PropertySection`

Hermes 专用组件：

`HermesNavItem`、`HermesPanelHeader`、`HermesSectionLabel`、`HermesStatusDot`、`HermesField`、`HermesPageTabs`、`HermesAdaptiveFieldGrid`

其中 `Theme`、`HermesField`、`HermesPageTabs`、`AppButton`、输入控件和开关遵循 Hermes-CN-Desktop `packages/shared-ui` 的令牌与组件契约；QML 适配来源及许可证见 `THIRD_PARTY_NOTICES.md`。

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

---

## 取值依据（这些数字为什么是这个数）

本节回答"为什么"，具体色值不在文档里复制 —— 唯一真源是 `app/qml/components/Theme.qml`。
文档里抄一份色值表，等于制造第二个会漂移的真源，历史上已经漂过两次（见文末「演进」）。

### 字号

主流系统桌面正文下限一致是 **12px**：

| 系统 | 桌面正文下限 | 档位 |
|---|---|---|
| TDesign（腾讯） | 12px | 12/14/16/20 + 24/28/36/48/64 |
| Arco Design（字节） | 12px | body 12/13/14，title 16/20/24 |
| Tailwind | 12px（`text-xs`） | 12/14/16/18/20/24/30 |
| Ant Design | 12px | 基准 14，`fontSizeSM` 12 |
| Material Design 3 | 11px（仅 `labelSmall`） | label 11/12/14；body 12/14/16 |

**行高规则**：`line-height = font-size + 8`（TDesign 官方规则，不是固定 1.5 倍）。
14→22、16→24 恰好等于 1.5 倍，但小字号下这个公式比固定倍数更稳。

`Theme.qml` 定义的五档：`fontSize2Xs 10 / fontSizeXs 11 / fontSizeSm 12 / fontSizeMd 12.5 / fontSizeLg 14`。

> ⚠ **现状与规范的差距（待收敛）**：令牌只定义了 5 档，但组件里实际硬编码了 7 种值
> —— 9(8 处) / 10(13 处) / 11(22 处) / 12(9 处) / 13(4 处) / 16(13 处) / 17(5 处)。
> 其中 9px、10px 低于 12px 下限，只应出现在角标或极紧凑的位置；13/16/17 不在令牌档位内。
> 新增界面一律用 `Theme.fontSize*` 令牌，不要写裸数字。

### 间距

| 系统 | 体系 | 非 4 倍档 |
|---|---|---|
| Arco / Ant / Bootstrap / Carbon | 纯 4px 栅格 | 无 |
| Chakra UI | 4px 为 1 单位 | 有：2 / 6 / 10 / 14 |
| Tailwind | 0.25rem 基准 | 有：2 / 6 / 10 / 14 |

`Theme.qml` 取 **严格 4px 栅格**：`space1 4 / space2 8 / space3 12 / space4 16 / space5 20 / space6 24`，不设 2 和 6 档。

**奇数间距 5/7/9/11 一律禁止** —— 没有任何主流系统支持，只会让对齐变成碰运气。

### 可点击目标

WCAG 2.5.8（AA）要求最小 **24×24 px**。

`Theme.qml` 的控件高：24（紧凑）/ 28（默认）/ 32（大）/ 36（特大）；图标 14/16/20。
主控件高 28 而非 32：一屏能多放一行，这是桌面密集型工具的实际收益。

### 暗色分支

暗色下 elevation 靠**变亮**表达，不是变暗（Radix、Mantlr 一致规则）；
品牌色需降饱和 10–20%，否则在近黑底上会刺眼。

`Theme.qml` 的 `darkMode: true` 分支遵循此规则：`bgApp #111111` → `bgBar #181818`
→ `bgRaised #202020` → `bgControl #242424` → `bgHover #2a2a2a`，单调递增。
默认 `darkMode: false`（浅色是当前主方向）。

### 对比度

正文与背景 **≥ 4.5:1**（WCAG AA），大字与图形 **≥ 3:1**。
接近临界值的取值必须实测，不要靠眼睛判断 —— 详见 `tests/test_design_tokens.py` 的对比度断言。

---

## 落地经验（改造中实测到的，不是推测）

### 视觉提升的大头不在颜色

用同一套控件渲染的三列对照实测：

| 方案 | 做法 | 观感 |
|---|---|---|
| A 改造前 | 旧令牌 + 1px 描边 + 6px 间距 | 廉价、拥挤，每块都有边框像表格 |
| B 仅换令牌 | 新颜色 + 仍用 1px 描边 + 6px 间距 | **和 A 几乎没差别** |
| C 完整改造 | 新令牌 + 去卡片描边 + 12px 间距 + 28px 控件高 | 明显更专业、更透气 |

**约 70% 的提升来自「间距节奏 + 不滥用边框」，颜色只占 30%。**
只对比色值会误判 —— 这正是 B 列看起来没变化的原因。所以 `Visual Rules` 里
"页面区段不使用卡片包裹"不是审美偏好，是收益最大的那一条。

### 硬编码清理的取舍

不要机械全替换：

- **高频且与令牌一致**（如 `#ffffff`）→ 替换为令牌，收益高
- **低频且是局部设计**（某个对话框的特殊高亮）→ 先补令牌再替换，别就地改色
- **确定的漂移色**（曾出现 Ant 蓝 `#1677FF` / `#4096FF`）→ 必改，这是没有理由的偏差

### 改 QML 后的自检

```bash
python -m app.qml.qml_main --screenshot out.png --width 1440 --height 900 --theme light
```

纯代码审查看不出的问题（图标重复、文字裁切、间距塌陷）只有渲染出来才看得见。
本次落地中"两个 ⚠ 图标叠在一起"就是只靠截图才发现的。

---

## 附录 A：QWidget 弹窗（`app/ui`）不属于本规范

经典 Qt Widgets 主界面已于 2026-10-28 下线，`app/ui` 只保留 QML 仍在调用的部分：

| 模块 | 用途 |
|---|---|
| `color_picker_dialog_a2.py`、`dialog_a2.py`、`add_text_layer_dialog_simple.py` | QML 侧调起的弹窗 |
| `tokens_v2.py` | 弹窗令牌真源（"01 墨黑极简"方向） |
| `dark_theme.py` | 由 `tokens_v2` 派生的常量别名层 |
| `design_tokens.py`、`design_spec.py`、`theme/` | 兼容转发与令牌契约 |

**这些弹窗是深色，与工作台的浅色不同层。** 它们取 `tokens_v2.py` 的值，
不取 `Theme.qml` 的值；两者互不覆盖，改一边不要顺手改另一边。

`tokens_v2.py` 自身是那一层的唯一事实来源，本文档**不复制**它的色值
（历史上抄过一次 `#2378C4`，后来代码换成 `INDIGO_600`，文档就过期了）。

已知未收敛项：深色弹窗嵌在浅色工作台里存在观感断层，尚未统一。

---

## 附录 B：演进（避免后人重走一遍）

| 阶段 | 方向 | 被放弃的原因 |
|---|---|---|
| 早期 | 双令牌并存（`design_tokens.py` + `theme/tokens.py`），三套主色 `#2F9CF4` / `#1677FF` / `#4096FF` | 同一产品三种蓝，切换界面色调跳变；改一处要改两处 |
| v2 | "01 墨黑极简"深色（`tokens_v2.py`，Linear / Vercel 风格，零边框靠亮度差） | 方向本身成立，但只服务经典版；经典版下线后不再是主界面语言 |
| 当前 | **Hermes Desktop 浅色工作台**（`Theme.qml`） | 现行基准，浅色为默认 |

`docs/DESIGN.md` 是 v2 阶段的规范，已于本次合并入本文档后删除。
它当时记录的深色色值表、微软雅黑字体栈、`#2378C4` 主色均已失效，
不要从 git 历史里翻出来再用。

详细组件契约（`AppButton`、`HermesField` 等逐个的尺寸与状态）见
`docs/hermes-desktop-design-system.md`；本文档管概览、边界与取值依据。
