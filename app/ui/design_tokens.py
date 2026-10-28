#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批图王 · 全局 UI 设计令牌（Design Tokens）单一事实来源

所有颜色 / 字体 / 尺寸 / 间距 / 圆角 / 动效的取值都必须从这里引用，
禁止在业务文件里写死色值或像素。普通图层属性面板与文字图层属性面板
共用本模块生成的控件 QSS，从而保证两套界面视觉一致。

阶段 1 改造说明（2026-08-04）：
- 本模块现为唯一事实来源；`dark_theme.CursorDarkTheme` 与 `visual_hierarchy.VisualHierarchy`
  均已改为从这里取值，不再各自维护重复的十六进制字面量。
- 共享基础值（BG_SECONDARY / BG_TERTIARY / BG_ELEVATED / TEXT_MUTED）已对齐到全局主题，
  消除令牌系统与全局主题长期存在的颜色漂移。
- 新增 Foundation 补充令牌（画布 / 标题栏 / 反转文本 / 覆盖层 / 指示器等）与 Semantic 语义别名层。
"""

from PySide6.QtGui import QColor  # noqa: F401  预留给需要 QColor 的调用方


from app.ui.tokens_v2 import Color as _V2C, Typography as _V2T

# 2026-10-28：尺寸/间距/圆角统一从 design_spec 取，本文件只做转发。
# 这样「改一处，全局生效」，不会再出现两套真源互相打架。
from app.ui.design_spec import (
    Layout as _LAYOUT,
    Radius as _SPEC_RADIUS,
    Scale as _SPEC,
    Space as _SP,
)

# ===== v2 转发层 =====
# 唯一事实来源是 app/ui/tokens_v2.py（方向 01 墨黑极简）。
# 这里把旧令牌里「颜色 / 字体 / 字号 / 间距 / 圆角」映射到 v2 真值，
# 消除此前两套令牌各写一份、导致三套主色并存的漂移。
# 旧令牌的**结构**（97 个名字）保持不变，20 个调用文件无需改。
#
# 刻意不覆盖：CONTROL_RADIUS / CARD_RADIUS / SECTION_GAP / ROW_GAP / PANEL_MARGIN。
# 这些是「属性面板布局契约」（PropertyPanelA2 等类在导入时按值绑定），
# 属于结构尺寸，不该由配色方向左右 —— 改它们会让面板排版漂移，
# 也会破坏 tests/test_property_panel_a2_spec.py 的尺寸契约。
_V2_OVERRIDES = {
    # 背景
    "BG_PRIMARY": _V2C.surface_base,
    "BG_SECONDARY": _V2C.surface_1,
    "BG_TERTIARY": _V2C.surface_2,
    "BG_ELEVATED": _V2C.surface_4,
    "BG_CONTROL_ALT": _V2C.surface_3,
    "BG_HOVER": _V2C.surface_hover,
    "BG_CANVAS": _V2C.canvas,
    "BG_TITLEBAR": _V2C.surface_1,
    "BG_SELECTED": _V2C.surface_selected,
    # 强调
    "ACCENT": _V2C.accent,
    "ACCENT_HOVER": _V2C.accent_hover,
    "ACCENT_PRESSED": _V2C.accent_active,
    # 文本选择背景。原来漏在转发层之外，一直是旧主色 #0E76D8（Ant 蓝系），
    # 而全站其它位置都已是 #5E6AD2 —— 选中输入框文字时会突然跳出一片冷蓝，
    # 是最容易被眼睛抓到的"历史漂移残留"。这里对齐到品牌主色。
    "SELECTION_BG": _V2C.accent,
    # 语义
    "SUCCESS": _V2C.success,
    "WARNING": _V2C.warning,
    "ERROR": _V2C.danger,
    "INFO": _V2C.info,
    # 边框（01 方向零边框，取最低档）
    "BORDER_PRIMARY": _V2C.border_subtle,
    "BORDER_SOFT": _V2C.border_subtle,
    "BORDER_CONTROL": _V2C.surface_3,
    "BORDER_SUBTLE": _V2C.border_subtle,
    "BORDER_FOCUS": _V2C.border_focus,
    "BORDER_INDICATOR": _V2C.border_strong,
    # 文本
    "TEXT_PRIMARY": _V2C.text_primary,
    "TEXT_SECONDARY": _V2C.text_secondary,
    "TEXT_MUTED": _V2C.text_muted,
    "TEXT_DISABLED": _V2C.text_disabled,
    "TEXT_INVERTED": _V2C.text_on_accent,
    "TEXT_INPUT": _V2C.text_primary,
    # 字体（中文优先，修正旧版把 Segoe UI 排前面的问题）
    "FONT_FAMILY": _V2T.family,
    "FONT_SIZE_BASE": _V2T.size_base,
    "FONT_SIZE_SMALL": _V2T.size_sm,
    "FONT_SIZE_TITLE": _V2T.size_lg,
}

class Tokens:
    # ===================== Foundation · 基础灰阶 =====================
    BG_PRIMARY = "#181818"        # 应用主背景 / 面板背景
    BG_SECONDARY = "#1F1F1F"      # 侧栏 / 停靠区 / 卡片背景（已对齐全局主题）
    BG_TERTIARY = "#2A2A2A"       # 普通控件背景（已对齐全局主题）
    BG_ELEVATED = "#2F2F2F"       # 输入框 / 下拉 / 弹层背景（已对齐全局主题）
    BG_CONTROL_ALT = "#242526"    # 按钮默认底
    BG_HOVER = "#303236"          # 控件 hover 底
    BG_CANVAS = "#151515"         # 中央画布工作区背景
    BG_TITLEBAR = "#202024"       # 菜单栏 / 工具栏背景
    BG_SELECTED = "#242B33"       # 列表选中底

    # ===================== Foundation · 蓝色 =====================
    ACCENT = "#2F9CF4"            # 主强调（选中 / 激活）
    ACCENT_HOVER = "#55B2FF"      # 强调 hover
    ACCENT_PRESSED = "#1F7EC8"    # 强调 pressed

    # ===================== Foundation · 红 / 黄 / 绿 =====================
    SUCCESS = "#30D158"
    WARNING = "#FF8A3D"
    ERROR = "#FF453A"
    INFO = "#38A5FF"

    # ===================== Foundation · 边框 =====================
    BORDER_PRIMARY = "#303033"    # 卡片 / 面板描边
    BORDER_SOFT = "#34383B"       # 次级描边 / 分割线
    BORDER_CONTROL = "#3A3A3D"    # 输入框 / 按钮描边
    BORDER_SUBTLE = "#252528"     # 弱分割线 / 禁用描边
    BORDER_FOCUS = "#2F9CF4"      # 焦点边框
    BORDER_INDICATOR = "#52555B"  # 复选 / 单选指示器描边

    # ===================== Foundation · 字体与文本 =====================
    TEXT_PRIMARY = "#F4F4F5"      # 主文本
    TEXT_SECONDARY = "#C7C7C9"    # 次级文本（hover 等）
    TEXT_MUTED = "#8E8E93"        # 次要 / 提示文本（已对齐全局主题）
    TEXT_DISABLED = "#606064"     # 禁用文本
    TEXT_INVERTED = "#FFFFFF"     # 反转文本（主操作按钮文字等）
    TEXT_INPUT = "#E9EEF3"        # 输入框内文本

    # ===================== Foundation · 交互覆盖层 =====================
    OVERLAY_HOVER = "rgba(255, 255, 255, 0.07)"
    OVERLAY_PRESSED = "rgba(255, 255, 255, 0.11)"
    SELECTION_BG = "#0E76D8"      # 文本选择背景
    DISABLED_CTL_BG = "#20252B"   # 禁用按钮底

    # ===================== 字体（统一使用 px，禁止 pt） =====================
    #
    # ⚠ 字号真源 = tokens_v2.Typography（2026-10-28 收敛）
    #
    # 之前这里**又硬写了一遍**，而且与 tokens_v2 的取值冲突：
    #   tokens_v2:  MD=14  LG=16
    #   本文件:     FEATURE_TITLE=15（比 LG 档还大）
    # 结果属性面板里"启用描边"是 15px，比"基本属性"这类区块标题(14px)还大，
    # 整片字号层级是错乱的（实测截图确认）。
    #
    # 现在全部改为回指 tokens_v2，**属性名保留**（21 处调用点不用改）：
    #   SIDEBAR_TITLE_FONT_SIZE  → size_md   (14)  区块标题
    #   SIDEBAR_BODY_FONT_SIZE   → size_base (13)  正文/输入
    #   SECTION_TITLE_FONT_SIZE  → size_base (13)  分区标题
    #   FIELD_LABEL_FONT_SIZE    → size_sm   (12)  字段标签（比内容小一档）
    #   FEATURE_TITLE_FONT_SIZE  → size_md   (14)  功能标题（原 15 → 14）
    #   SUMMARY_FONT_SIZE        → size_caption (11) 摘要
    FONT_FAMILY = _V2T.family
    FONT_SIZE_BASE = _V2T.size_base
    FONT_SIZE_SMALL = _V2T.size_sm
    FONT_SIZE_TITLE = _V2T.size_md
    FONT_WEIGHT_REGULAR = _V2T.weight_regular
    FONT_WEIGHT_MEDIUM = _V2T.weight_semibold
    FONT_WEIGHT_BOLD = _V2T.weight_bold

    # ===================== 图层属性侧边栏排版 =====================
    # Qt QSS 不支持 line-height；行高通过标题栏/控件高度与布局间距落实。
    SIDEBAR_TITLE_FONT_SIZE = _V2T.size_md       # 14
    SIDEBAR_TITLE_FONT_WEIGHT = _V2T.weight_semibold
    SIDEBAR_TITLE_LINE_HEIGHT = 20
    SIDEBAR_BODY_FONT_SIZE = _V2T.size_base      # 13
    SIDEBAR_BODY_FONT_WEIGHT = FONT_WEIGHT_REGULAR
    SIDEBAR_BODY_LINE_HEIGHT = 20

    # ===================== 尺寸 / 间距 / 圆角 =====================
    #
    # 2026-10-28：高度与圆角改由 `app/ui/design_spec.py` 统一供给。
    #
    # 改造前这里写死 CONTROL_HEIGHT=30、CONTROL_RADIUS=5、CARD_RADIUS=7，
    # 而 tokens_v2.Size 又是 26/30/34/38 四档、各处 setFixedSize 还有 32/34/44
    # 字面量 —— 实测同一窗口出现 37 种高度，同排控件歪 8px。
    # 现在只认 design_spec 的三档：24 / 28 / 36。
    CONTROL_HEIGHT = _SPEC.PX[_SPEC.MD]      # 28，所有输入框/按钮/下拉
    CONTROL_RADIUS = _SPEC_RADIUS.MD         # 6
    CARD_RADIUS = _SPEC_RADIUS.LG            # 8
    HEADER_HEIGHT = _SPEC.PX[_SPEC.MD]       # 28，分组标题（原 36 过高）
    #: 边距收敛到 4px 栅格。原值 (10,8,10,8)/(8,6,8,6)/(8,4,7,4) 里
    #: 6 和 7 不在栅格上，是「每次顺手加一个」的产物。
    BODY_MARGINS = (_SP.LG, _SP.SM, _SP.LG, _SP.SM)          # 16, 8, 16, 8
    SUBPANEL_MARGINS = (_SP.SM, _SP.XS, _SP.SM, _SP.XS)      # 8, 4, 8, 4
    HEADER_MARGINS = (_SP.SM, _SP.XS, _SP.SM, _SP.XS)        # 8, 4, 8, 4（修掉非对称的 7）
    GROUP_CONTENT_MARGINS = (_SP.SM, _SP.SM, _SP.SM, _SP.SM)  # 8, 8, 8, 8
    PANEL_MARGIN = _SP.SM          # 8
    ROW_GAP = _SP.SM               # 8（原 6，不在 4px 栅格上）
    SECTION_GAP = _SP.SM           # 8
    SEGMENT_GAP = _SP.XS          # 4（原 5，不在 4px 栅格上）
    #: 表单标签列宽 —— **单一真源 = design_spec.Layout.LABEL_WIDTH(72)**。
    #:
    #: ⚠ 2026-10-28 修：这里原来硬写 58，design_spec.Layout 里另有一份 72，
    #: dialog_a2 里还有一份 82。三份同时生效 → 同一个属性面板里标签列宽实测
    #: 出现 58 / 84 / 640 三种值，右边缘落在 70 / 84 / 96 三个位置，
    #: 这就是"看着乱"的物理来源（不是审美问题，是栅格没对齐）。
    #:
    #: 为什么取 72：属性面板最长的字段标签「渐变不透明:」实测 63px
    #: （12px 微软雅黑），加 5px 呼吸 + 4px 栅格对齐 = 72。
    #: 这个值也正好等于 design_spec 原值，收敛时不用改任何视觉预期。
    LABEL_WIDTH = _LAYOUT.LABEL_WIDTH
    #: 嵌套二级标签（同一行里"主标签 + 子项"）。比主标签窄，不参与主栅格。
    SECONDARY_LABEL_WIDTH = 40
    POSITION_LABEL_WIDTH = 22
    SPIN_WIDTH = 76
    COLOR_SWATCH_SIZE = 30
    ICON_BUTTON_WIDTH = 42
    COLLAPSE_BUTTON_SIZE = _SPEC.PX[_SPEC.SM]   # 24（原 18，低于 WCAG 24px 下限）
    ACTION_BUTTON_WIDTH = 56
    ALIGN_BUTTON_MIN_WIDTH = 56
    FONT_BUTTON_MIN_WIDTH = 56
    FEATURE_TOGGLE_HEIGHT = _SPEC.PX[_SPEC.LG] + _SP.MD   # 36+12=48（4px 栅格）
    # 圆角收敛到 design_spec.Radius 的 4 档（4/6/8/12）。
    # 改造前这里是 5 / 4 / 6 三个近邻值 + 内边距 12/14，
    # 视觉上几乎看不出差别，但会让所有对齐关系错位。
    BUTTON_RADIUS = _SPEC_RADIUS.MD          # 6
    INDICATOR_RADIUS = _SPEC_RADIUS.SM       # 4
    SUBPANEL_RADIUS = _SPEC_RADIUS.MD        # 6
    SIDEBAR_PADDING = _SP.MD      # 12 —— 这原本误用了 Radius 令牌（令牌用错了语义）
    SIDEBAR_SECTION_PADDING_TOP = _SP.MD     # 14 → 12（14 不在栅格上）
    SIDEBAR_SECTION_PADDING_BOTTOM = _SP.LG     # 16
    SIDEBAR_SECTION_GAP = 0
    SIDEBAR_TAB_HEIGHT = _SPEC.PX[_SPEC.LG]     # 36（原 38，不在 24/28/36 三档内）
    SIDEBAR_MIN_WIDTH = 320
    SIDEBAR_PREFERRED_WIDTH = 360
    SIDEBAR_SECTION_RADIUS = 0
    SIDEBAR_NAV_RADIUS = 0
    SIDEBAR_BORDER_WIDTH = 1

    # 侧边栏四色规范：主色 / 辅助色 / 背景色 / 文字色。
    SIDEBAR_COLOR_PRIMARY = ACCENT
    SIDEBAR_COLOR_SECONDARY = BG_TERTIARY
    SIDEBAR_COLOR_BACKGROUND = BG_PRIMARY
    SIDEBAR_COLOR_TEXT = TEXT_PRIMARY

    # 语义化字号（全部回指 tokens_v2.Typography，见上方「字号真源」说明）
    SECTION_TITLE_FONT_SIZE = _V2T.size_base      # 13
    FIELD_LABEL_FONT_SIZE = _V2T.size_sm          # 12（比内容小一档）
    SUMMARY_FONT_SIZE = _V2T.size_caption         # 11
    FEATURE_TITLE_FONT_SIZE = _V2T.size_md        # 14（原 15，超了区块标题一级）
    TEXT_AREA_HEIGHT = 96
    INDICATOR = 16                 # 复选 / 单选指示器边长

    # ===================== 开关 =====================
    SWITCH_W = 52
    SWITCH_H = _SPEC.PX[_SPEC.MD]  # 28
    SWITCH_TRACK_MARGIN = 3
    SWITCH_KNOB = 22

    # ===================== 动效 =====================
    MOTION_MS = 150

    # ===================== Semantic · 语义别名层 =====================
    # 业务代码优先使用语义键，而非具体灰阶，便于后续统一调整层级。
    SEMANTIC = {
        "surface.app": BG_PRIMARY,
        "surface.panel": BG_SECONDARY,
        "surface.control": BG_CONTROL_ALT,
        "surface.elevated": BG_ELEVATED,
        "surface.canvas": BG_CANVAS,
        "surface.titlebar": BG_TITLEBAR,
        "text.primary": TEXT_PRIMARY,
        "text.secondary": TEXT_SECONDARY,
        "text.muted": TEXT_MUTED,
        "text.disabled": TEXT_DISABLED,
        "border.default": BORDER_PRIMARY,
        "border.soft": BORDER_SOFT,
        "border.focus": BORDER_FOCUS,
        "action.primary": ACCENT,
        "action.primary.hover": ACCENT_HOVER,
        "action.primary.pressed": ACCENT_PRESSED,
        "status.success": SUCCESS,
        "status.warning": WARNING,
        "status.error": ERROR,
        "status.info": INFO,
    }

    @classmethod
    def semantic(cls, key: str) -> str:
        """按语义键取色，未知键回退到主文本色。"""
        return cls.SEMANTIC.get(key, cls.TEXT_PRIMARY)

    # ------------------------------------------------------------------
    # QSS 生成器：两套属性面板共用，保证控件外观完全一致
    # ------------------------------------------------------------------
    @classmethod
    def control_qss(cls, selector):
        """通用控件样式（按钮 / 输入 / 下拉 / 分段 / 复选 / 滑块 / 开关）。"""
        return f"""
        {selector} {{
            background: {cls.BG_PRIMARY};
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FONT_SIZE_BASE}px;
            font-family: {cls.FONT_FAMILY};
        }}
        {selector} QLabel {{
            color: {cls.TEXT_PRIMARY};
            background: transparent;
            font-size: {cls.FONT_SIZE_BASE}px;
        }}
        {selector} QLabel[role="sectionTitle"] {{
            color: {cls.TEXT_INVERTED};
            font-size: {cls.SECTION_TITLE_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QLabel[role="fieldLabel"], {selector} QLabel#fieldLabel {{
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QLabel[role="mutedLabel"], {selector} QLabel[role="summaryLabel"] {{
            color: {cls.TEXT_MUTED};
            font-size: {cls.SUMMARY_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QLabel[role="featureTitle"] {{
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FEATURE_TITLE_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        /* 面板内按钮/工具按钮。
           ⚠ min-height 必须**扣掉** padding 与 border —— QSS 的 height 不含这两项，
           三者相加才是实际像素高。写 min-height=CONTROL_HEIGHT(28) + padding 3px
           实测渲染成 36px；再和代码里的 setFixedHeight(28) 打架（Qt 取较大值），
           最终变成 44px —— 「选择」按钮就是这么被撑高的。
           现在：内高 = 28 - 3×2 - 1×2 = 20，加回来正好 28。 */
        {selector} QPushButton, {selector} QToolButton {{
            min-height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            max-height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            background-color: {cls.BG_CONTROL_ALT};
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_MEDIUM};
            /* ⚠ padding 必须写全四边。写 `3px 8px` 这类两值形式时，
               Qt 在与全局 QPushButton 的 `padding: 0 14px` 合并过程中
               会把左右值串到上下，实测把 28px 的按钮顶成 44px。 */
            padding: 3px 8px 3px 8px;
        }}
        /* 颜色块：**尺寸交给控件内联 QSS**（ColorIndicator 里写 min/max = size-2
           以抵消 1px 边框），这里不再重复声明尺寸，否则两者叠加会撑到 32~38px。
           仅保留 padding:0，避免大内边距把 setFixedSize 的可用区吃光。 */
        {selector} QPushButton[role="color-swatch"] {{
            padding: 0px;
        }}
        /* 面板内操作按钮。与上方 segmentButton 同样的两个坑：
           min-height 不含 padding/border；padding 必须写全四边。
           内高 = 28 - 3×2 - 1×2 = 20，加回 padding 与 border 正好 28。 */
        {selector} QAbstractButton[actionButton="true"] {{
            height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            min-height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            max-height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            background-color: {cls.BG_CONTROL_ALT};
            color: {cls.TEXT_PRIMARY};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_MEDIUM};
            padding: 3px 8px 3px 8px;
        }}
        {selector} QPushButton:hover, {selector} QToolButton:hover {{
            background-color: {cls.BG_HOVER};
            border-color: {cls.ACCENT_HOVER};
        }}
        {selector} QPushButton:pressed, {selector} QToolButton:pressed {{
            background-color: {cls.ACCENT_PRESSED};
            border-color: {cls.ACCENT};
        }}
        {selector} QPushButton:disabled, {selector} QToolButton:disabled {{
            color: {cls.TEXT_DISABLED};
            background-color: {cls.DISABLED_CTL_BG};
            border-color: {cls.BORDER_SUBTLE};
        }}
        /* 分段按钮（雅黑/宋体/楷体/Arial、无/纯色/渐变 这类）。
           ⚠ 这里踩过两个坑，都得显式写全：

           坑 1：min-height 不含 padding/border。写 min-height=28 再叠
                padding 3px，实测渲染成 44px（字体按钮变大方块，撑爆面板）。

           坑 2：**padding 必须写全四边**。全局有
                `QPushButton` 的 `padding: 0 14px`，本规则若只写
                `padding: 3px 6px`，Qt 在两套规则合并时会把左右值 14
                串到上下，算出 44px。显式写 `padding: 3px 6px 3px 6px`
                才能锁定每一边。

           现在：内高 = 28 - 3×2 - 0 = 22，加回 padding 3×2 正好 28。 */
        {selector} QPushButton[segmentButton="true"], {selector} QToolButton[segmentButton="true"] {{
            /* 内高 = 28 - padding(3×2) - border(1×2) = 20。
               border 虽然不在这条规则里写，但会从上方
               `{selector} QPushButton` 基础规则继承 1px，
               所以必须一起扣 —— 只扣 padding 会得到 30px。 */
            height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            min-height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            max-height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            padding: 3px 6px 3px 6px;
            background-color: {cls.BG_CONTROL_ALT};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_MEDIUM};
        }}
        {selector} QPushButton[segmentButton="true"]:checked, {selector} QToolButton[segmentButton="true"]:checked {{
            background-color: {cls.ACCENT};
            border-color: {cls.ACCENT_HOVER};
            color: {cls.TEXT_INVERTED};
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QPushButton[compactValue="true"] {{
            /* 内高 = 28 - padding(3×2) - border(1×2) = 20。
               原来直接写 CONTROL_HEIGHT，被 QSS 加上 padding+border 后
               实测渲染成 44px（英文色块按钮把"颜色"那行撑高）。 */
            height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            min-height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            max-height: {cls.CONTROL_HEIGHT - 3 * 2 - 1 * 2}px;
            padding: 3px 8px 3px 8px;
            background-color: {cls.BG_ELEVATED};
            border-color: {cls.BORDER_SOFT};
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        /* 单行输入控件。
           ⚠ min-height 必须扣掉 padding 与 border —— QSS 的 height 不含这两项，
           三者相加才是实际像素高。原来写 min-height=CONTROL_HEIGHT(30) +
           padding 3px，实测渲染成 38px（比契约值高 8px），
           与同排的 QLineEdit / QComboBox 高度不一致，面板看着"歪"。
           max-height 一并锁死（QSpinBox 有上下按钮，sizeHint 会顶高）。

           **不用描边**：实测旧描边 #1D1F21 与控件内部 #23252A 亮度只差 6~9，
           肉眼几乎看不出，却白占 2px 空间、还添一层噪点。
           改用 surface_3(亮度30.7) 对面板底 surface_1(15.9) 的亮度差(14.8) 区分，
           干净且清晰。 */
        {selector} QLineEdit, {selector} QComboBox, {selector} QSpinBox, {selector} QDoubleSpinBox {{
            min-height: {cls.CONTROL_HEIGHT - 3 * 2}px;
            max-height: {cls.CONTROL_HEIGHT - 3 * 2}px;
            background-color: {cls.BG_CONTROL_ALT};
            color: {cls.TEXT_INPUT};
            border: none;
            border-radius: {cls.BUTTON_RADIUS}px;
            selection-background-color: {cls.SELECTION_BG};
            padding: 3px 8px;
        }}
        /* 聚焦才出现描边，让用户明确知道焦点在哪 */
        {selector} QLineEdit:focus, {selector} QComboBox:focus,
        {selector} QSpinBox:focus, {selector} QDoubleSpinBox:focus {{
            border: 1px solid {cls.BORDER_FOCUS};
        }}
        {selector} QTextEdit, {selector} QPlainTextEdit {{
            background-color: {cls.BG_ELEVATED};
            color: {cls.TEXT_INPUT};
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.BUTTON_RADIUS}px;
            selection-background-color: {cls.SELECTION_BG};
            padding: 3px 6px;
        }}
        {selector} QLineEdit:focus, {selector} QTextEdit:focus, {selector} QComboBox:focus,
        {selector} QSpinBox:focus, {selector} QDoubleSpinBox:focus {{
            border-color: {cls.ACCENT};
        }}
        {selector} QCheckBox, {selector} QRadioButton {{
            color: {cls.TEXT_PRIMARY};
            spacing: 6px;
            font-size: {cls.FONT_SIZE_BASE}px;
        }}
        {selector} QCheckBox[role="inlineCheck"] {{
            min-height: {cls.CONTROL_HEIGHT}px;
            max-height: {cls.CONTROL_HEIGHT}px;
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
            font-weight: {cls.FONT_WEIGHT_MEDIUM};
        }}
        {selector} QCheckBox[role="switch"] {{
            min-width: {cls.SWITCH_W}px;
            max-width: {cls.SWITCH_W}px;
            min-height: {cls.SWITCH_H}px;
            max-height: {cls.SWITCH_H}px;
            background: transparent;
        }}
        {selector} QCheckBox::indicator {{
            width: {cls.INDICATOR}px;
            height: {cls.INDICATOR}px;
            border-radius: 4px;
            border: 1px solid {cls.BORDER_INDICATOR};
            background: {cls.BG_ELEVATED};
        }}
        {selector} QRadioButton::indicator {{
            width: 15px;
            height: 15px;
            border-radius: 8px;
            border: 1px solid {cls.BORDER_INDICATOR};
            background: {cls.BG_ELEVATED};
        }}
        {selector} QCheckBox::indicator:checked, {selector} QRadioButton::indicator:checked {{
            background: {cls.ACCENT};
            border-color: {cls.ACCENT_HOVER};
        }}
        {selector} QCheckBox[role="switch"]::indicator {{
            width: 0px;
            height: 0px;
            border: none;
            background: transparent;
        }}
        {selector} QSlider::groove:horizontal {{
            height: 4px;
            background: {cls.BORDER_CONTROL};
            border-radius: 2px;
        }}
        {selector} QSlider::sub-page:horizontal {{
            background: {cls.ACCENT};
            border-radius: 2px;
        }}
        {selector} QSlider::handle:horizontal {{
            background: {cls.ACCENT_HOVER};
            width: 16px;
            height: 16px;
            margin: -6px 0;
            border-radius: 8px;
        }}
        {selector} QPushButton[variant="primary"], {selector} QToolButton[variant="primary"] {{
            background-color: {cls.ACCENT};
            border: 1px solid {cls.ACCENT};
            color: {cls.TEXT_INVERTED};
            font-weight: {cls.FONT_WEIGHT_BOLD};
        }}
        {selector} QPushButton[variant="primary"]:hover, {selector} QToolButton[variant="primary"]:hover {{
            background-color: {cls.ACCENT_HOVER};
            border-color: {cls.ACCENT_HOVER};
        }}
        {selector} QPushButton[variant="primary"]:pressed, {selector} QToolButton[variant="primary"]:pressed {{
            background-color: {cls.ACCENT_PRESSED};
            border-color: {cls.ACCENT_PRESSED};
        }}
        {selector} QPushButton[variant="secondary"], {selector} QToolButton[variant="secondary"] {{
            background-color: {cls.BG_TERTIARY};
            border: 1px solid {cls.BORDER_CONTROL};
            color: {cls.TEXT_PRIMARY};
        }}
        {selector} QPushButton[variant="secondary"]:hover, {selector} QToolButton[variant="secondary"]:hover {{
            background-color: {cls.BG_HOVER};
            border-color: {cls.BORDER_FOCUS};
        }}
        {selector} QPushButton[variant="ghost"], {selector} QToolButton[variant="ghost"] {{
            background: transparent;
            border: 1px solid {cls.BORDER_CONTROL};
            color: {cls.TEXT_SECONDARY};
        }}
        {selector} QPushButton[variant="ghost"]:hover, {selector} QToolButton[variant="ghost"]:hover {{
            background-color: {cls.BG_HOVER};
            border-color: {cls.BORDER_FOCUS};
            color: {cls.TEXT_PRIMARY};
        }}
        """

    @classmethod
    def panel_qss(cls, selector):
        """控件样式 + 卡片/分组角色样式（文字图层面板使用）。"""
        return cls.control_qss(selector) + f"""
        /* 卡片（section）。
           **不加描边** —— 这是设计规范 5.0 的实测结论：
           旧做法每块面板加 1px 描边，一屏十几个框，视觉上像 Excel 表格。
           改用底色差（surface_1 #0F1011 vs surface_base #0A0B0D，亮度差约 3%）
           分层，干净得多。只有真正的浮层（弹窗 / 菜单）才用边框 + 阴影。
           sectionHeader 的分割线也一并去掉，避免"框里还有一条线"。 */
        {selector} QFrame[role="section"] {{
            background-color: {cls.BG_SECONDARY};
            border: none;
            border-radius: {cls.CARD_RADIUS}px;
        }}
        {selector} QFrame[role="sectionHeader"] {{
            background-color: transparent;
            border: none;
            border-top-left-radius: {cls.CARD_RADIUS}px;
            border-top-right-radius: {cls.CARD_RADIUS}px;
        }}
        {selector} QFrame[role="sectionBody"] {{
            background-color: transparent;
            border: none;
        }}
        {selector} QFrame[role="subPanel"] {{
            background-color: {cls.BG_ELEVATED};
            border: 1px solid {cls.BORDER_SOFT};
            border-radius: {cls.SUBPANEL_RADIUS}px;
        }}
        {selector} QFrame[role="parameterGrid"] {{
            background-color: transparent;
            border: none;
        }}
        {selector} QFrame[role="coreDivider"] {{
            background-color: {cls.BORDER_SOFT};
            border: none;
        }}
        {selector} QFrame[role="previewCard"] {{
            background-color: {cls.BG_SECONDARY};
            border: 1px solid {cls.BORDER_PRIMARY};
            border-radius: {cls.SUBPANEL_RADIUS}px;
            padding: 8px;
        }}
        {selector} QLabel[role="previewTitle"] {{
            color: {cls.TEXT_INVERTED};
            font-weight: {cls.FONT_WEIGHT_BOLD};
            font-size: {cls.FIELD_LABEL_FONT_SIZE}px;
        }}
        {selector} QLabel[role="previewArea"] {{
            background-color: {cls.BG_ELEVATED};
            border: 1px solid {cls.BORDER_CONTROL};
            border-radius: {cls.CONTROL_RADIUS}px;
            padding: 12px;
            color: {cls.TEXT_INVERTED};
            /* 大标题：取 size_xl(20)？原值 18 不在档位上。
               这里语义是空状态/提示用的大字，用区块标题档 LG(16) 偏小，
               用页面标题档 XL(20) 更合语义，但要照顾原视觉大小 → 取 LG+XL 之间？
               Qt 不支持中间值，选 LG(16) 保持克制：提示文字不该比正文夸张太多。 */
            font-size: {cls.FONT_SIZE_TITLE}px;
        }}
        """

# ===== 应用 v2 转发（保持旧令牌名不变，值来自 v2）=====
for _k, _v in _V2_OVERRIDES.items():
    if hasattr(Tokens, _k):
        setattr(Tokens, _k, _v)

# 派生令牌必须在覆盖之后再同步一次。
# 原因：`SIDEBAR_COLOR_PRIMARY = ACCENT` 这类赋值写在类体里，是**类定义时按值绑定**的，
# 上面的 setattr 覆盖发生在类定义之后，不会自动刷新这些派生值 ——
# 结果侧栏仍停留在旧主色 #2F9CF4，成为历史漂移的残留。
# 这是本次收敛发现的真实问题，不是测试误报。
_DERIVED = {
    "SIDEBAR_COLOR_PRIMARY": "ACCENT",
    "SIDEBAR_COLOR_SECONDARY": "BG_TERTIARY",
    "SIDEBAR_COLOR_BACKGROUND": "BG_PRIMARY",
    "SIDEBAR_COLOR_TEXT": "TEXT_PRIMARY",
    "BG_CARD": "BG_SECONDARY",
    "BG_PANEL": "BG_SECONDARY",
}
for _alias, _target in _DERIVED.items():
    if hasattr(Tokens, _target):
        setattr(Tokens, _alias, getattr(Tokens, _target))
