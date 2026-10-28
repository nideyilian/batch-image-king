"""批图王界面设计规范 —— 唯一真源（Single Source of Truth）。

═══════════════════════════════════════════════════════════════════════════
为什么需要这个文件
═══════════════════════════════════════════════════════════════════════════

2026-10-28 实测：主窗口 170 个可见控件，存在 **37 种不同高度**
（16/18/24/26/30/31/36/38/44 混用）、**5 种按钮高度**、**7 种 layout 间距**、
**9 种 layout 边距**（含 `(8,4,7,4)` 这种非对称值）。

同期清点：`setStyleSheet` 调用点 **67 处，散在 37 个文件**。
项目其实早有一套 shadcn/ui 风格组件库（`app/ui/components/`，1481 行），
但只有 **3 个文件**在用它，其余全部手写控件 + 内联 QSS。

→ 结论：问题不是「缺组件库」，是**缺一份不许随手加数字的规格**。
   本文件就是那份规格。所有界面代码只准从 `Scale` / `Space` / `Radius`
   / `FontSize` 取值，不准写字面量。

═══════════════════════════════════════════════════════════════════════════
档位为什么是这几个数（不是拍脑袋）
═══════════════════════════════════════════════════════════════════════════

对标业界成熟系统（2026-10 逐一核对）：

| 系统            | 控件高度档 | 间距档 |
|-----------------|-----------|--------|
| Ant Design      | 3 档 24/32/40 | 8 档 4/8/12/16/24/32/48/64 |
| TDesign         | 3 档 24/32/40 | 6 档 |
| Bootstrap 5     | 2 档     | 6 档（0.25rem 步进） |
| Material 3      | 3 档     | 6 档（4dp 栅格） |
| Radix / Chakra  | 2~3 档   | 6 档 |

共同规律：**高度档 ≤ 3、间距档 ≤ 8、全部落在 4px 栅格上。**

本文件据此定档。凡不在档位内的数值，测试会报错。

═══════════════════════════════════════════════════════════════════════════
怎么用
═══════════════════════════════════════════════════════════════════════════

    from app.ui.design_spec import Scale, Space, Radius, FontSize, IconSize

    btn = QPushButton("确定")
    btn.setProperty("uiSize", Scale.MD)        # 高度 28
    layout.setSpacing(Space.MD)                # 8
    layout.setContentsMargins(Space.LG, Space.MD, Space.LG, Space.MD)
    label.setStyleSheet(f"font-size: {FontSize.BODY}px")

    # 绝对不要写：
    #   layout.setSpacing(6)
    #   btn.setFixedHeight(38)
    #   label.setStyleSheet("font-size: 13px")
"""

from __future__ import annotations

# 字号真源：tokens_v2.Typography（见 FontSize 类说明）
from app.ui.tokens_v2 import Typography as _Typo


class Scale:
    """控件高度档位（3 档）。

    语义按「信息密度」分，不按「大小」分 —— 这样选档时不需要猜。

    | 档位 | 高度 | 用在哪儿 |
    |------|------|---------|
    | SM   | 24   | 工具栏图标按钮、图层面板底栏、状态栏内控件 |
    | MD   | 28   | **默认**。绝大多数按钮、输入框、下拉框 |
    | LG   | 36   | 对话框主操作按钮、空状态页的行动号召 |
    """

    SM = "sm"
    MD = "md"
    LG = "lg"

    #: 档位 → 像素高度。QSS 与代码共用，禁止另写数字。
    PX = {SM: 24, MD: 28, LG: 36}

    #: WCAG 2.5.8（AA）要求可点击目标 ≥ 24x24。SM 档正好卡在下限。
    MIN_CLICKABLE = 24

    @classmethod
    def all_px(cls) -> set[int]:
        """所有合法高度集合，供契约测试断言用。"""
        return set(cls.PX.values())


class Width:
    """控件宽度档位（按**用途**分，不是按数值大小分）。

    为什么要单独一套，而不是复用 `Scale`（高度）：
    - 高度表达「这是多高的控件」，3 档足够（工具条 / 默认 / 主操作）
    - 宽度表达「这里要放多长的内容」，由**内容长度**决定，需要的档位天然更多

    实测现状：`setFixedWidth` 用了 20 种不同值
    （1/4/16/18/22/24/30/32/35/42/48/58/60/64/72/76/80/92/100/110）。
    这里面 `1` 是分隔线、`42/48` 是数字标签、`60/80` 是下拉框 ——
    **强行套 4px 栅格会削掉内容宽度**（例如 60→56 会让"120.5%"显示不全）。

    所以这里的策略是「**登记 + 归并**」而不是「一刀切成 4 档」：
    - 数值归到 4px 栅格（除分隔线 1px）
    - 同一语义只留一个值（原来 42 和 48 都是"数值标签"，统一到 48）
    """

    #: 分隔线：1px 是渲染精度下限，不参与栅格
    HAIRLINE = 1

    #: 数值标签（"100%"、"24px" 这类，固定字符数）
    VALUE_LABEL = 48

    #: 短标签 / 小图标按钮
    SHORT = 24

    #: 次级标签、小型下拉
    LABEL = 64

    #: 数值输入框（spin 右侧带上下箭头，需要额外宽度）
    SPIN = 60

    #: 下拉框（"常规网格" 这类 4 字中文 + 箭头）
    COMBO = 80

    #: 中等文本控件
    MEDIUM = 92

    #: 宽文本控件
    WIDE = 112

    #: 合法集合。注意：这套**故意**比 Scale 多，
    #: 因为宽度由内容决定，不是「控件规格」。
    ALL = (HAIRLINE, SHORT, VALUE_LABEL, SPIN, LABEL, COMBO, MEDIUM, WIDE)


class Space:
    """间距档位（6 档，4px 栅格）。

    为什么砍到 6 档：现有代码有 2/4/6/8/10/12/14/16/20/24/32 共 11 档，
    其中 6/10/14 不在 4px 栅格上，是「每次顺手加一个」的产物。
    视觉上 6 和 8 几乎看不出差别，但会让对齐关系全部错位。
    """

    NONE = 0
    XS = 4
    SM = 8
    MD = 12
    LG = 16
    XL = 24

    #: 合法集合，供契约测试用
    ALL = (NONE, XS, SM, MD, LG, XL)

    @classmethod
    def snap(cls, value: int | float) -> int:
        """把任意间距值吸附到最近的档位。

        用于把历史遗留的非栅格值（2/3/5/6/10/14…）迁到规范上，
        不用每处手写映射表。等距时取**较小**的档位 —— 宁可紧一点，
        因为间距紧不会破版，松了会挤掉可用宽度（属性栏只有 344px）。
        """
        return min(cls.ALL, key=lambda s: (abs(s - value), s))

    @classmethod
    def is_valid(cls, value: int) -> bool:
        return value in cls.ALL


class Radius:
    """圆角档位（4 档）。"""

    SM = 4    # 小控件：色块、标签、复选框
    MD = 6    # 默认：按钮、输入框、卡片
    LG = 8    # 大容器：面板、分组
    XL = 12   # 对话框

    ALL = (SM, MD, LG, XL)


class FontSize:
    """字号档位（6 档，px）。

    ⚠ 真源 = `tokens_v2.Typography`（2026-10-28 收敛）。

    之前这里独立写死了一套，且与 tokens_v2 **取值冲突**：
        tokens_v2:  MD=14  LG=16
        本文件:     MD=15  LG=18     ← 同一档位两个值
    于是「按 spec 写」和「按 tokens_v2 写」会得到不同字号，
    而两者都自称是规范 —— 这就是字号层级失控的根源。

    现在改为回指，本类只做「同一套值的另一套命名」：
        FontSize.CAPTION == Typography.size_caption (11)
        FontSize.SMALL   == Typography.size_sm      (12)
        FontSize.BASE    == Typography.size_base    (13)
        FontSize.MD      == Typography.size_md      (14)
        FontSize.LG      == Typography.size_lg      (16)
        FontSize.XL      == Typography.size_xl      (20)
        FontSize.XXL     == Typography.size_2xl     (24)

    新增字号请先加到 tokens_v2.Typography，不要在这里直接写数字。
    """

    from app.ui.tokens_v2 import Typography as _T

    CAPTION = _T.size_caption   # 11  辅助说明、状态栏
    SMALL = _T.size_sm          # 12  次要信息、图层面板尺寸标签
    BASE = _T.size_base         # 13  **正文默认**
    MD = _T.size_md             # 14  小标题、面板标题
    LG = _T.size_lg             # 16  区块标题
    XL = _T.size_xl             # 20  页面标题
    XXL = _T.size_2xl           # 24  启动画面、空状态大标题
    ALL = (CAPTION, SMALL, BASE, MD, LG, XL, XXL)


class IconSize:
    """图标档位（3 档）。"""

    SM = 16   # 内联在文字旁
    MD = 20   # **默认**：工具栏、按钮内图标
    LG = 24   # 面板头部、导航

    ALL = (SM, MD, LG)


class LineHeight:
    """行高。TDesign 规范：line-height = font-size + 8。"""

    @staticmethod
    def for_size(font_px: int) -> int:
        return font_px + 8


class Opacity:
    """透明度档位。禁止随手写 0.1 / 0.15 / 0.2 这种。"""

    DISABLED = 0.38    # Material 3 标准的禁用态
    SUBTLE = 0.12      # 弱化的底色/描边
    HOVER = 0.08       # hover 叠加层
    PRESSED = 0.16     # 按下叠加层


class Motion:
    """动效时长（ms）。超过 300ms 会显得迟钝。"""

    INSTANT = 0
    FAST = 120     # 状态切换
    BASE = 180     # **默认**：展开/收起
    SLOW = 260     # 面板滑入


class Layout:
    """容器级约定。"""

    #: 面板内边距（所有侧栏统一）
    PANEL_PADDING = Space.MD

    #: 区块之间的垂直间距
    SECTION_GAP = Space.MD

    #: 同一区块内，控件之间的垂直间距
    ROW_GAP = Space.SM

    #: 标签与控件之间的水平间距
    LABEL_GAP = Space.SM

    #: 表单标签统一宽度（保证冒号对齐）
    LABEL_WIDTH = 72

    #: 侧栏最小宽度。低于此值，中文图层名会开始省略。
    SIDEBAR_MIN_WIDTH = 180

    #: 状态栏高度。可交互控件必须放得进去（当前缩放到 24px 档）
    STATUSBAR_HEIGHT = 26


# ── 兼容层：把新规格接到既有 Theme API 上 ─────────────────────────────
#
# 项目里已有 `Theme.layout("control-h")` 这类调用。为保证平滑迁移，
# 这里提供映射，让旧调用点也能拿到新档位的值。

LEGACY_LAYOUT_MAP = {
    "control-h": Scale.PX[Scale.MD],
    "control-h-sm": Scale.PX[Scale.SM],
    "control-h-lg": Scale.PX[Scale.LG],
    "control-h-xl": Scale.PX[Scale.LG],   # 旧 38 档取消，并入 LG
    "icon-btn": Scale.PX[Scale.LG],       # 36，按住 24 图标 + 6 内距
    "icon-btn-sm": Scale.PX[Scale.SM],    # 24
}


__all__ = [
    "Scale", "Space", "Radius", "FontSize", "IconSize",
    "LineHeight", "Opacity", "Motion", "Layout", "LEGACY_LAYOUT_MAP",
]
