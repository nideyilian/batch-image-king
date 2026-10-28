# 参数布局 UI 规范

## 目标

程序内所有参数编辑界面都应遵循同一条基本规则：同一参数的文案和控件要贴近，不同参数之间要有清晰间隔，并且在右侧面板被拖窄时不能发生文字、控件重叠。

## 基础规则

1. 单个参数使用“标签 + 控件”的参数组。
   - 标签到控件的距离：4-8 px。
   - 标签宽度固定或受控，不能依赖拉伸空间把控件推远。
   - 控件右侧可留弹性空白，但标签和控件之间不能放弹性空白。

2. 同一行放多个参数组时，参数组之间要有明确间隔。
   - 参数组之间的最小间距：18-24 px。
   - 不要用普通 `QHBoxLayout` 把多个标签和控件混排到底。
   - 推荐使用 `QGridLayout`：每组占“标签列 + 控件列”，组之间用独立 spacer 列。

3. 窄面板必须支持换行。
   - 当属性面板有效宽度低于 360 px 时，一行多个参数组应拆成多行。
   - 拆行后每一行仍保持“标签 + 控件”贴近。
   - 禁止通过缩小固定控件或压缩标签来强行塞进一行。

4. 表单型界面优先使用 `QFormLayout`。
   - `labelAlignment` 推荐 `Qt.AlignRight | Qt.AlignVCenter` 或统一的固定宽标签。
   - `horizontalSpacing` 推荐 6-8 px。
   - `verticalSpacing` 推荐 6-10 px。
   - 多参数复合行使用嵌套 `QGridLayout`，不要在一个 `QHBoxLayout` 里无结构混排。

5. 控件尺寸要有下限。
   - 数字输入框常规宽度：72-84 px。
   - 短按钮常规宽度：42-60 px。
   - 颜色按钮：24-32 px。
   - 滑块行必须给数值标签固定宽度，避免数值变化导致布局跳动。

6. 视觉分隔优先按语义，而不是按控件数量。
   - 字体、大小、对齐、颜色、透明度、文本框等是不同语义组，应使用分隔线或 8-12 px 垂直间距。
   - 同一语义组内的参数可同行展示，但必须满足换行规则。

## 推荐实现模式

### 单参数行

```python
line = QHBoxLayout()
line.setSpacing(6)
label.setFixedWidth(58)
line.addWidget(label)
line.addWidget(control)
line.addStretch(1)
```

### 多参数行

```python
grid = QGridLayout()
grid.setHorizontalSpacing(6)
grid.setVerticalSpacing(8)
grid.addWidget(label_a, 0, 0)
grid.addWidget(control_a, 0, 1)
grid.setColumnMinimumWidth(2, 18)
grid.addWidget(label_b, 0, 3)
grid.addWidget(control_b, 0, 4)
```

当可用宽度低于 360 px 时，将第二组移动到下一行：

```python
grid.addWidget(label_b, 1, 0)
grid.addWidget(control_b, 1, 1)
```

## 禁止模式

- 禁止在同一行中使用 `addStretch()` 放在标签和控件之间。
- 禁止使用大量固定空格或硬编码大边距来模拟对齐。
- 禁止让两个参数组在窄面板中继续强行单行显示。
- 禁止为了塞进一行把标签压到和控件重叠。

## 当前优先优化范围

1. 右侧图层属性面板。
2. 文字图层属性面板。
3. 批量导出窗口。
4. 新建/调整画布、添加图层、预设管理等对话框。

每次优化一个界面时，应先按本规范修复参数行，再运行至少一次语法检查；涉及 Qt 交互的界面应手动启动程序确认无重叠。
