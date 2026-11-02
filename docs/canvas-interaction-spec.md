# 画布交互规范（对照 Photoshop 移动工具）

本文件是画布选择的**唯一口径**。改 QML 手势或命中判定前先读这里，
改完必须跑文末列出的探针。

## 1. 工具语义

| 动作 | 行为 |
|---|---|
| 单击图层 | 选中。**几何完全不变**（不吸附、不写历史） |
| 拖图层内部 | 移动 |
| 拖 8 个手柄 | 缩放 |
| 拖边框线（非手柄） | 穿透，选中下层图层 |
| 拖空白处 | 框选 |
| 双击文字图层 | 进入文字编辑 |
| 右键图层 | 图层菜单 |
| Shift + 拖角手柄 | 等比缩放 |
| Ctrl/Option + 拖 | 复制并移动 |
| Shift + 单击 | 加入/移出选区 |

## 2. 手柄规则

**手柄是 8 个离散方块，不是边框带。** 界面画出来就是 8 个小方块
（`8 / actualScale` 屏幕像素），命中区也只能是这 8 个点周围
（半径 `14 / 2 / actualScale` 画布像素）。任何「距边框 N 像素内都算手柄」
的实现都会让视觉与行为脱节——用户以为点在图层上，实际却在缩放。

**选框很小时逐级降级**（与 Photoshop 一致）：

| 选框屏幕尺寸 | 手柄 |
|---|---|
| 富余 | 8 个全显示 |
| 相邻手柄会重叠 | 只留 4 角，边中点隐藏 |
| 角手柄会盖住中心 | 全部隐藏，此时靠拖内部移动 |

三级降级的判据都在 `app/utils/selection_handle_geometry.py`，
QML 侧 `handleAt` 与视觉 `Repeater` 必须用同一套判据，
否则会出现「画得出点不到」或「点得到没画」。

## 3. 命中优先级（`onPressed` 顺序）

1. 右键 → 图层菜单 / 画布菜单
2. 裁剪编辑中 → 交裁剪层处理
3. 文字编辑覆盖层可见 → 先提交编辑，**继续走后续判定**（不要 return）
4. `handleAt` 命中手柄 → 进入缩放
5. 命中图层 → 选中
6. 空白 → 开始框选

第 3 步的「不要 return」是硬要求：旧实现提交编辑后直接 return，
用户点了别的图层没反应，必须点第二次才生效。

## 4. 单击不得产生副作用

`onPressed` 会立刻进入变换态（为了拖动灵敏），但：

- `transformDirty` 只有位移超过 **1 屏幕像素**才置位
- `commitTransform` 在 `!transformDirty` 时直接返回，**不走 snapPosition**
- 即使吸附后几何与起始完全一致，也不写历史

旧实现只要按下就 commit，于是「点一下」会走吸附，
把距参考线 6px 内的图层一把拉过去——这是最容易被误当成「程序乱了」的行为。

## 4.1 拖动必须跟手（预览管线）

拖动中每帧调用 `workspace.previewLiveGeometry(x, y, w, h)`：

- **不写历史、不改 is_modified**（拖动中每帧都改，写历史会撑爆撤销栈）
- 末尾只丢一帧交互质量预览，不升级 final
- QML 侧节流 16ms（约 60fps），并跳过 `!transformDirty` 的帧

松手时 `commitTransform` 走一次 `applySelectedGeometry` 完成正式落盘。
取消时 `cancelTransform` 必须调 `restoreSelectedGeometry` 还原——因为实时预览
已经改过图层几何，不还原会留下半成品。

### 预览结果接受判定（关键，曾导致「拖不动」）

`_on_preview_rendered` 的判定是：

```python
request_id == self._render_request_id
and generation >= self._accepted_preview_generation   # 不是 == self._preview_generation
```

**不能用 `generation == self._preview_generation`。** 每帧都会推进
`_preview_generation`，渲染要 3~15ms，回来时 generation 必然落后，
于是每一帧结果全被丢弃，画面停住不动，只有彻底停手后才接受一次。
这是「拖动卡顿」最真实的成因，修好后 1200² 一帧 10ms、3000² 一帧 15ms。

## 5. 图层命中用半开区间

`0 <= local_x < width`，**不是** `<=`。
宽度 400 的像素是 0..399，用 `<=` 会让右/下边缘多占 1px，
与紧贴的下层图层互相抢点，表现为「点在接缝上总是选上面那个」。

## 6. 文字图层按像素判定

文字框（尤其关掉自动适配的大框）里绝大多数地方是透明的。
命中分两趟：第一趟按像素 alpha，第二趟才用矩形兜底。
这样「点字形」「点框内空白」「点框内压着的下层」三者都成立。

## 7. 验证

| 探针 | 覆盖 |
|---|---|
| `docs/audit/probe_ps_interaction.py` | 单击无副作用、8 手柄离散、边框穿透 |
| `docs/audit/probe_ps_gestures.py` | 各方向缩放锚点、拖动、单击、Shift 等比 |
| `docs/audit/probe_drag_cancel.py` | 拖动中取消还原、正常提交生效 |
| `docs/audit/probe_frame_pacing.py` | 各尺寸下拖动出帧率与帧间隔 |
| `docs/audit/probe_handle_scope.py` | 手柄作用域、小选框降级 |
| `docs/audit/probe_canvas_click_sequence.py` | 切换/编辑/框选的连续操作 |
| `tests/test_selection_handle_geometry.py` | 几何单测 + **QML 源码一致性断言** |
| `tests/test_preview_generation_accept.py` | 预览接受判定、实时几何不写历史 |

QML 里那段 `handleAt` 是内联函数，Python 测不到它的运行结果，
所以测试会直接读 `Main.qml` 源码断言关键结构（不能出现 `nearLeft` 之类
的带式判定、锚点顺序、隐藏条件）。两边不同步时测试会红。
