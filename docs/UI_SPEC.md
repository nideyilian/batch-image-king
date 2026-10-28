# 界面规范与强制规则

> 2026-10-28 · 本文件是**界面改造的施工图纸**。所有新增/修改界面的代码必须遵守。
> 违反会被 `tests/test_ui_rules.py` 直接判红。

---

## 0. 一句话原则

**任何尺寸、间距、颜色、图标，都从规范取值 —— 不准写字面量。**

原因：改造前主窗口 170 个可见控件存在 **37 种不同高度**、5 种按钮高度、
7 种 layout 间距、9 种边距、67 处散在 37 个文件的内联 QSS。
不是"设计不好看"，是**没有一处数值有约束**。

---

## 1. 四块交付物

| 能力 | 位置 | 说明 |
|---|---|---|
| **设计规范** | `app/ui/design_spec.py` | 唯一真源。高度 3 档 / 间距 6 档 / 圆角 4 档 / 字号 6 档 / 图标 3 档 |
| **图标库** | `app/ui/icon_library.py` | qtawesome + Material Design Icons 6（6997 个），MIT 可商用 |
| **组件库** | `app/ui/components/` | 已有 1481 行 shadcn 风格组件，**本次重新接线并要求使用** |
| **强制规则** | `app/ui/ui_rules.py` + `tests/test_ui_rules.py` | 静态扫描 + 运行时审计 + 棘轮契约 |

---

## 2. 尺寸档位（只准用这三个）

```python
from app.ui.design_spec import Scale

Scale.SM   # 24px  工具栏图标按钮、图层面板底栏、状态栏内控件
Scale.MD   # 28px  ★默认：绝大多数按钮、输入框、下拉框
Scale.LG   # 36px  对话框主操作、空状态行动号召

Scale.PX[Scale.MD]   # 取像素值
```

**为什么是 3 档**（对标数据）：

| 系统 | 高度档 | 间距档 |
|---|---|---|
| Ant Design | 3 档 24/32/40 | 8 档 |
| TDesign | 3 档 | 6 档 |
| Bootstrap 5 | 2 档 | 6 档 |
| Material 3 | 3 档 | 6 档 |

共同规律：**高度 ≤3 档、间距 ≤8 档、全部 4px 栅格**。
我们改造前 37 档，选档时只能靠猜 —— 等于没有规范。

**24 是硬下限**：WCAG 2.5.8（AA）要求可点击目标 ≥ 24×24。

---

## 3. 间距档位（4px 栅格）

```python
from app.ui.design_spec import Space, Layout

Space.XS   # 4
Space.SM   # 8
Space.MD   # 12
Space.LG   # 16
Space.XL   # 24

Layout.PANEL_PADDING   # 面板内边距
Layout.SECTION_GAP     # 区块之间
Layout.ROW_GAP         # 同区块内控件之间
```

**禁止**：6 / 10 / 14 / 7 这类不在 4px 栅格上的值。
改造前有 `(8, 4, 7, 4)` 这种非对称边距 —— 7 就是顺手加出来的。

---

## 4. 圆角 / 字号 / 图标

```python
from app.ui.design_spec import Radius, FontSize, IconSize

Radius.SM/MD/LG/XL      # 4 / 6 / 8 / 12
FontSize.CAPTION/SMALL/BASE/MD/LG/XL   # 11 / 12 / 13 / 15 / 18 / 24
IconSize.SM/MD/LG       # 16 / 20 / 24
```

字号 `BASE = 13` 对齐 Arco Design 的 body-2。中文在 13px 以下笔画会糊。

---

## 5. 图标（统一来源）

```python
from app.ui.icon_library import icon, icon_button, IconName

btn.setIcon(icon("delete"))                     # 业务名，走别名表
btn.setIcon(icon(IconName.DELETE))              # 语义常量，避免拼错
btn.setIcon(icon("save", color=Color.accent))   # 指定颜色

ib = icon_button("zoom_in", size="md", tooltip="放大")   # 尺寸受 spec 约束
```

**禁止混用**：旧代码同时用了 SVG 手绘 + 字体字符（`⚀ ∞ ⧄ ✎`），
线宽 1.5~2.5 跳变，`delete` 是实心而其余是线条 —— 肉眼一眼能看出不是一套。

图标集选 `mdi6`（Material Design Icons 6）而不是 FontAwesome：
MDI 线条更细更克制，贴近桌面工具软件；FA Solid 偏粗，更像移动端。

**纯图标按钮必须有 tooltip**（WCAG 2.4.6 / 4.1.2）。规则 R6 会检查。

---

## 6. 组件使用（必须）

`app/ui/components/` 已有完整组件库，**新代码必须从这里取件**：

```python
from app.ui.components import Button, Input, Card, Select, Dialog

btn = Button("确定", variant="default", size="md")
inp = Input("占位符")
card = Card()
```

已有变体：`default / secondary / outline / ghost / destructive / link`
已有尺寸：`sm / default / lg / icon`

**不要**直接 `QPushButton(...)` + `setStyleSheet(...)`。
改造前 1481 行的组件库只有 3 个文件在用，其余全部手写 —— 这才是"风格混乱"的根因。

---

## 7. 七条规则（会自动检查）

| 规则 | 内容 | 检查方式 |
|---|---|---|
| **R1** | 内联 QSS 必须已令牌化 | 静态扫描 |
| **R2** | 禁止 `setFixedSize(28)` 这类字面量 | 静态扫描 |
| **R3** | 可见控件高度必须落在 spec 档位内 | 运行时审计 |
| **R4** | 控件不得溢出父容器 | 运行时审计 |
| **R5** | layout spacing 必须落在 Space 档位内 | 运行时审计 |
| **R6** | 纯图标按钮必须有 tooltip | 运行时审计 |
| **R7** | 禁止硬编码十六进制颜色 | 静态扫描 |

### 命令行自查

```bash
# 静态扫描（快，不需要开窗口）
python -c "from app.ui.ui_rules import lint_source; print(lint_source().report())"

# 运行时审计（慢，要建主窗口）
python -c "
from PySide6.QtWidgets import QApplication
app = QApplication([])
from app.ui.dark_theme import CursorDarkTheme; CursorDarkTheme.apply_to_application(app)
from app.main_window import MainWindow
from app.ui.ui_rules import audit_widget_tree, format_audit
w = MainWindow(); w.show(); app.processEvents()
print(format_audit(audit_widget_tree(w)))
"
```

### 棘轮机制（重要）

历史欠账登记在 `tests/test_ui_rules.py` 的 `DEBT` 字典里。

- **新增违规** → 立刻红灯
- **修掉一些** → 必须同步下调上限（`test_debt_ratchet_is_not_stale` 会提醒）

这是把技术债变成**单向收敛**的唯一办法。只准降，不准升。

---

## 8. 当前的坑（踩过，别再踩）

### QSS 的 `min-height` 优先级高于 `setFixedSize()`

这是本项目最顽固的坑，同一现象在 4 个地方复现过：

```python
# ❌ 无效：会被 QSS 撑回去
btn.setFixedHeight(28)

# ✅ 有效：三步都要设
btn.setMinimumHeight(28)
btn.setMaximumHeight(28)
btn.setFixedHeight(28)
```

而且 QSS 的 `height` **不含** padding 和 border，三者相加才是实际像素：

```
min-height: 28 + padding: 3×2 + border: 1×2 = 36   ← 实际渲染
```

所以 QSS 里写 `min-height` 必须扣掉 padding/border：
`min-height = 目标值 - padding×2 - border×2`

### padding 必须写全四边（2026-10-28 新踩的坑）

```css
/* ❌ 两值写法：与全局 `QPushButton { padding: 0 14px }` 合并时，
      Qt 会把左右值 14 串到上下，28px 被顶成 44px */
padding: 3px 8px;

/* ✅ 写全四边，每一边都锁定 */
padding: 3px 8px 3px 8px;
```

这个坑的隐蔽性在于：**单独看这条规则完全正确**，问题只在与全局规则
合并时出现。实测「字体按钮」和「选择按钮」都因此从 28 变 44，
变成一排大方块把面板撑爆。

### 面板 QSS 与全局 QSS 会叠加，且 `polish` 会触发重算

`install_semantic_polisher` 在 `QEvent.Show` / `QEvent.Polish` 时
对整个控件树做 `unpolish + polish`，这会重新合并面板 QSS 和全局 QSS ——
上面那个 padding 串位问题就是在这时候发生的（未 show 时是 28，
show 后变 44）。

调试这类「尺寸只在显示后变坏」的问题，正确姿势是对比：
```python
b = 某按钮
print('未 show:', b.minimumHeight())   # 28  ← 创建时正确
p.show(); app.processEvents()
print('show 后:', b.minimumHeight())   # 44  ← QSS 重算后变坏
```

### `polisher` 会给没有 `role` 的按钮打 `variant`

`install_semantic_polisher` 在 `QEvent.Polish` 时给所有按钮设
`variant="secondary"`，于是命中带 padding 的按钮规则。

**任何自定义外观的按钮，必须显式 `setProperty("role", "...")`**，
否则会被当成普通按钮撑大。色块（`ColorIndicator`）就因此从 30×30 变成 30×38。

### Qt 基类必须排在 mixin 之后

```python
# ❌ 错误：QWidget 在前，mixin 的方法会被 Qt 空实现遮蔽
class MyPanel(QWidget, MyPanelBase): ...

# ✅ 正确
class MyPanel(MyPanelBase, QWidget): ...
```

`MainWindow` 曾因为顺序错，`closeEvent` 被 `QWidget.closeEvent` 遮蔽 ——
**关闭确认逻辑从来没执行过，用户点 X 直接丢数据**，而且不报错、不崩溃。

全项目还有 6 个类是这个写法（`CanvasWidget` / `LayerPanel` /
`LayerPropertiesPanel` / `IntegratedTextPanel` 等）。目前"凑巧能跑"
（因为子类自己覆写了关键方法），但**加新方法就会静默失效**。

---

## 9. 收敛进度（棘轮）

| 指标 | 改造前 | 现在 | 目标 |
|---|---|---|---|
| 可见控件高度种类 | **37** | 8 | 3 |
| 按钮高度种类 | 5 | 5 | 3 |
| layout spacing 种类 | 7 | 7 | 6 |
| `setFixedSize` 字面量 | 68 | **50** | 0 |
| 内联 QSS 未令牌化 | 20 | 20 | 0 |
| 硬编码颜色 | 15 | 15 | 0 |
| QSS 旧档位残留 | 26/30/34/38 | **0** | 0 |
| 图标风格 | 两套混用 | **统一** | 统一 |

---

## 10. 下一步

1. **压高度到 3 档**（8 → 3）：剩余来源已定位
   - 16px：状态栏缩放框（已知特例，需放得进 26px 状态栏）
   - 18px：图层面板图标按钮 → 改 `Scale.SM`(24)
   - 22px：字体选择器输入框 → 改 `Scale.MD`(28)
   - 26px：图层底栏按钮 → 改 `Scale.SM`(24)
   - 30px：属性面板按钮 → 改 `Scale.MD`(28)
   - 36px：下拉箭头 → 改 `Scale.MD`(28)
   - 44px：文字面板按钮（**最难**，因 `load_fonts` 动态重建，未走 spec）
2. **修 6 个 MRO 遮蔽类**，避免未来静默失效
3. **迁移 50 处 `setFixedSize` 字面量**到 `Scale`
4. **清理 20 处未令牌化内联 QSS**

---

## QSS 高度计算的四条硬规律（2026-10-28 收尾实测）

高度收敛从 37 种压到 3 种的整个过程，卡在四个反直觉的机制上。
**这四条不是猜测，每一条都有实测对照实验**，改 QSS 尺寸前必读。

### 规律 1：QSS 的 `height` 不含 padding 和 border

```
最终像素高 = height + padding上 + padding下 + border上 + border下
```

所以想让控件是 28px，写 `height: 28` 会得到 28+6+2=36。
正确写法是 `height: 28 - padding×2 - border×2`。

> 这个坑在 `design_tokens.py` 里踩了两次：`segmentButton` 和
> `actionButton` 都曾直接写 `CONTROL_HEIGHT`，实测渲染 30 和 44。

### 规律 2：padding 必须写全四边

```css
padding: 3px 8px;          /* ❌ */
padding: 3px 8px 3px 8px;  /* ✅ */
```

两值写法与全局 `QPushButton { padding: 0 14px }` 合并时，
Qt 会把左右值 14 串到上下，28px 被顶成 44px。
**单看这条规则完全正确，问题只在合并时出现** —— 这是最难查的一类。

### 规律 3：`min-height` 压不住 `sizeHint`，必须同时写 `max-height`

这条是这轮新发现，也是最费时间的一条。

实测工具栏按钮：`minimumHeight()=28`（规则生效了），但渲染仍是 **31px**：

```python
b.minimumHeight()      # 28   ← 我们设的
b.minimumSizeHint()    # 31   ← Qt 按「图标18 + 文字行高 + padding」算的
b.height()             # 31   ← Qt 取 max(minHeight, minSizeHint)
```

**Qt 的高度取 `max(minHeight, minimumSizeHint)`**，所以只写 `min-height`
挡不住内容撑开。必须同时写 `max-height` 才能锁死：

```css
height: 24px; min-height: 24px; max-height: 24px;   /* 内高 24 + padding/border */
```

### 规律 4：`uiSize` 档位生效后，控件内联的 `min-height` 会失效，但 `border` 仍叠加

对照实验（`uiSize="iconSm"`，档位 24）：

| 内联 QSS | 渲染高度 |
|---|---|
| `min-height:22 + border:1px` | **26** |
| `min-height:24 + border:1px` | **26** |
| `min-height:22 + border:none` | 24 ✅ |
| `min-height:24 + border:none` | 24 ✅ |

结论：**一旦声明了 `uiSize`，内联尺寸就交给档位管，但内联的 border
仍会加到档位值上。** 所以档位规则里的 height 必须扣掉 border：

```css
/* icon 档目标 28，这类按钮内联有 1px 边框 → 内高 26 */
height: 26px;  /* 26 + 2 = 28 ✅ */
```

### 一条附加经验：`_make_param_row` 的 stretch 别加在控件上

`row.addWidget(widget, 1)` 给最后一个控件 stretch，当它是 `QSpinBox`
（Expanding）时会吃掉全部余量，把前面的小按钮顶到行尾 ——
截图里表现为「大小 [输入框.......] B I」中间一大片空白。
正确做法是 `row.addStretch(1)`，控件紧凑靠左、右侧留白。

---

## 高度收敛结果（2026-10-28）

| 口径 | 改造前 | 现在 |
|---|---|---|
| 可见控件高度种类 | **37 种** | **3 种**（24/28/36）✅ |
| 运行时审计违规 | 57 处 | 15 处（全是间距） |
| 高度类违规 | 30 处 | **0** ✅ |

### 修掉的 6 组具体来源

| 曾出现的高度 | 数量 | 真实来源 | 修法 |
|---|---|---|---|
| 44px | 2 | 文字面板 `compactValue` 按钮 | QSS 扣 padding+border |
| 31px | 16 | 工具栏按钮被 41px 工具栏拉伸 | 工具栏 padding 5→4，按钮加 `max-height` |
| 30px | 12 | 面板 `segmentButton` | QSS 扣 padding(6)+border(2) |
| 26px | 8 | 图层面板图标按钮 | 去掉内联尺寸，`iconSm` 档扣 border |
| 22px | 6 | QComboBox 内部行编辑 | 框架内部控件，不纳入契约 |
| 18px | 3 | 图层行眼睛/锁按钮 | `setFixedSize(18)` → SM 档 24 |
| 16px | 1 | 状态栏 SpinBox 内部行 | 受限容器，不纳入契约 |

### 增加的两类豁免（写进 `ui_rules.is_framework_internal`）

1. **框架内部子控件**：`qt_spinbox_lineedit`、`qt_toolbar_ext_button`、
   QComboBox/QSpinBox 内部的 QLineEdit —— 高度由父控件算法决定。
2. **受限容器内控件**：QStatusBar 里的控件（状态栏只有 21px 高，
   放不下 28px 的控件，该改的是状态栏本身）。
3. **语义化方形控件**：`role="color-swatch"` 的色块是 30×30 正方形，
   边长是**语义的一部分**，压到 24/28 会破坏方形观感。

---

## 间距收敛（2026-10-28）

高度收敛后，同一个病根在间距上又出现一次。这轮一并收干净。

### 结果

| 口径 | 改造前 | 现在 |
|---|---|---|
| 运行时间距违规 | 14 处 | **0** ✅ |
| `setSpacing` 字面量 | 101 处 | 全部走 `Space` 档位 |
| 涉及文件 | — | 18 个 |

### 新增能力：`Space.snap()`

不想每处手写映射表，加了一个吸附函数：

```python
Space.snap(5)   # → 4
Space.snap(6)   # → 4
Space.snap(10)  # → 8
Space.snap(38)  # → 24
```

等距时取**较小**档位 —— 间距紧一点不会破版，松了会挤掉可用宽度
（属性栏只有 344px）。

### 这轮同时修掉的令牌语义错误

`Tokens` 里有几个值不只是「不在栅格上」，而是**令牌用错了语义**：

| 令牌 | 原值 | 问题 |
|---|---|---|
| `SIDEBAR_PADDING` | `_SPEC_RADIUS.XL` | **用圆角令牌当代指间距**，语义错位 |
| `SEGMENT_GAP` | 5 | 非栅格 |
| `SIDEBAR_TAB_HEIGHT` | 38 | 不在 24/28/36 三档内 |
| `SIDEBAR_SECTION_PADDING_BOTTOM` | 16 | 裸数字 |

### 豁免：Qt 内部容器的 spacing

`QStatusBar` / `QDockWidget` / `qt_tabwidget_stackedwidget` 的 layout
由 Qt 创建，spacing 由 Qt 主题决定，我们既改不了也不该改。
已加入 `SPACE_SKIP`。

---

## 架构缺陷：MRO 遮蔽（2026-10-28 修完 6 个类）

### 缺陷本质

```python
class BatchExportDialog(QDialog, ...各 Mixin):   # ❌ QDialog 在第一位
```

Qt 基类占据 MRO 首位后，它自带的同名方法会**抢在 mixin 之前**解析。
表现是：mixin 里代码写了、语法对了、看起来没问题 —— **但从来没执行过**。
不报错、不崩溃、不影响启动，只在特定操作时才露馅。

### 修掉的真实缺陷（都是实测确认，不是推测）

| 类 | 方法 | 修复前解析到 | 实际后果 |
|---|---|---|---|
| `BatchExportDialog` | `closeEvent` | `QDialog.closeEvent` | **导出中关窗口会直接中断导出**（原设计是仅隐藏、不取消） |
| `BatchExportDialog` | `reject` | `QDialog.reject` | 点取消不保存设置 |
| `CanvasWidget` | `sizeHint` | `QWidget.sizeHint` | 画布初始布局拿不到 `QSize(800,600)` |

实测验证（修复后）：

```
导出中: closeEvent accepted=False  ← 正确拦截
空闲中: closeEvent accepted=True   ← 允许关闭
CanvasWidget().sizeHint() = QSize(800, 600)
```

### 顺带修出的一个真 bug

`LayerPropertiesPanel` 里 `LayerPropertiesSource` 和 `LayerPropertiesShape`
**各有一套 `update_fill_*`**。MRO 让 `Source` 版胜出（它的节流实现更优），
于是 `Shape` 版成了死代码 —— 而 `fill_enabled_checkbox` 的**唯一回写点
就在那份死代码里**。

后果：切换图层后，填充面板显示的还是上一层的值。渲染层是真实读取
`clone_fill_*` 属性的（见 `document_render.py`），所以功能本身没问题，
缺的只是 UI 回写。已在 `sync_ui_with_layer` 里补齐。

### 修法

把 Qt 基类移到基类列表**最后**：

```python
class BatchExportDialog(
    BatchExportDialogSettingsMixin, ...,
    QDialog,          # ← 移到最后
):
```

`super().reject()` 依然能走到 `QDialog`（它在 MRO 末尾），不影响任何调用链。

### 加了自动防线

`tests/test_ui_rules.py::test_no_qt_base_class_shadows_mixin_methods`
扫描全项目，凡是「Qt 基类后面还有 mixin」的类一律报错。
这类缺陷最怕的就是没人发现，加个静态检查一劳永逸。

---

## 静态欠账清零（2026-10-28 收尾）

| 规则 | 清零前 | 现在 |
|---|---|---|
| R1 内联样式未令牌化 | 20 | **0** |
| R2 禁止硬编码尺寸 | 47 | **0** |
| R7 禁止硬编码颜色 | 15 | **0** |

棘轮上限同步归零：`DEBT` 里三个数都写 0，**新增任何一处违规都会直接红灯**。

### 三个清零手段，都是修判据而不是放水

清零过程里有一半工夫花在**把规则的判据做准**上，否则「清零」只是自欺。

**R1：从「扫大窗口」改成「只看传给 setStyleSheet 的那段 QSS」**

原实现取「调用行 + 后 12 行」判断有没有 token，有两个致命缺陷：

1. 窗口里只要碰巧出现 `Scale.` 子串（例如紧邻一行的 `setFixedSize(_Scale.PX[...])`），
   整段就被判为"已令牌化"。**实测：注入 `setStyleSheet("color: #FF0000")`
   后 R1 报 0 —— 规则完全失效。**
2. 传变量时（`setStyleSheet(style)`）令牌写在变量定义处（在前面），
   往后扫永远看不到。

现在用 `_extract_qss_argument()` 精确取出字面量内容；传变量时用
`_var_definition_is_tokenized()` 向前回溯赋值块。

**R2：新增 `design_spec.Width` 档位**

宽度不能套用 `Scale`（那是高度档位）。实测 `setFixedWidth` 有 20 种取值
（1/4/16/18/22/24/30/32/35/42/48/58/60/64/72/76/80/92/100/110），
但**强行切成 4 档会削掉内容**（60→56 让"120.5%"显示不全）。

所以按**用途**分档，而不是按数值大小：

| 档位 | 值 | 用在哪儿 |
|---|---|---|
| `HAIRLINE` | 1 | 分隔线（渲染精度下限，不参与栅格） |
| `SHORT` | 24 | 小图标按钮 |
| `VALUE_LABEL` | 48 | 「100%」「24px」这类定长数值标签 |
| `SPIN` | 60 | 带上下箭头的数值输入框 |
| `LABEL` | 64 | 次级标签 |
| `COMBO` | 80 | 下拉框（4 字中文 + 箭头） |
| `MEDIUM` | 92 | 中等文本控件 |
| `WIDE` | 112 | 宽文本控件 |

顺带统一了两处同语义不同值：`42` 和 `48` 都是数值标签 → 48；
`35` 也是标签 → 48。

**R7：四类语义豁免 + 启动画面独立色值**

| 文件 | 为什么不能换令牌 |
|---|---|
| `add_text_layer_dialog_simple` | 画在**用户任意选色**色块上的文字，必须恒定纯白 |
| `icon_manager` | SVG 着色函数的缺省参数值，与主题无关 |
| `layer_properties_shape` | 「任意底色上选深字/浅字」的亮度阈值配对，换令牌会让阈值漂移 |
| `components/forms` | `ColorSwatch` 构造默认值，不是样式 |

启动画面（`splash_screen.py` 7 处）单独一类：它在 `main.py:342` 创建，
**此时主题尚未加载**（`setup_fixed_theme` 更晚调用），必须自带色值。
新增 `test_splash_colors_do_not_drift_from_theme` 锁住"与主题一致"，
防的是漂移而不是禁止字面量。

### 工具自身也要排除

`ui_rules.py` 里到处是反例代码字符串（文档、注释、测试样例），
扫自己只会自产自销假违规 → 加入 `SELF_EXEMPT`。

---

## 一个原本就存在、不是我引入的问题：对齐工具栏溢出

**实测对比**（`git stash` 切回原始代码，同一个探针脚本）：

| | 主工具栏 | 对齐工具栏 | 溢出按钮 |
|---|---|---|---|
| 原始代码 | 1273x**51** | 227 装 647 | 可见 |
| 现在 | 1305x**36** | 195 装 453 | 可见 |

结论：
1. **对齐工具栏溢出是原本就有的**，不是我改出来的。
2. 我的改动让情况略好（需求从 647 降到 453），高度也从 51 修正到 36（正规档位）。

### 根因是容量，不是样式

1500px 宽的窗口装不下两个工具栏：
主工具栏 15 个按钮需要 1305px，对齐工具栏 10 个按钮需要 453px，
合计 1758px。放不下就必然有一方溢出。

### 试过并失败的方案（都实测无效，记下来避免重复踩）

| 方案 | 结果 |
|---|---|
| `addToolBarBreak(Qt.TopToolBarArea)` | 两工具栏 y 坐标仍相同 |
| `insertToolBarBreak()` | 同上 |
| `addToolBar(Qt.BottomToolBarArea, tb)` | 仍停在顶部 |
| `setMinimumWidth(sizeHint)` | 对齐栏正常了，但主工具栏开始溢出（只是换了个人） |
| `setIconText()` 缩短按钮文字 | `iconText` 设上了，但按钮宽度受 QSS 下限约束，总宽没变 |

**为什么工具栏位置调整全部无效**：`main_window_misc.py:553` 的
`restoreState()` 会恢复上次保存的布局，覆盖 `create_toolbar()` 里的设置。

### 留给后续决策

这是**信息架构问题**，不是样式问题：顶栏 25 个按钮本身就超容量。
可选方向（都需要产品决策，不该我单方面定）：
- 主工具栏精简（部分低频按钮移进菜单）
- 对齐工具栏改为图标 24px（而非 28px）以压缩需求
- 对齐功能移到图层属性面板里（它们本来就是对图层的操作）
