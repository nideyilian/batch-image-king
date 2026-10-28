"""批图王 · 设计令牌 v2（唯一事实来源）

最终选定方向：**01 墨黑极简**（参考 Linear / Vercel）
    - 近纯黑底，**零边框**，完全靠底色亮度差分层次
    - 这是刻意选择：旧界面「每个面板都描 1px 边、一屏十几个框」是廉价感主因，
      去掉边框改用亮度差，观感立刻从「Excel 表格」变成「专业工具」

本文件取代此前的双轨制：
  - 旧 `app/ui/design_tokens.py`（97 个令牌，自称单一来源）
  - 旧 `app/ui/theme/tokens.py`（对齐 shadcn 命名，取值又回指前者）
两套并存导致同一产品出现三套主色（#2F9CF4 / #1677FF / #4096FF）与两套字体栈。

取值依据（详见 docs/DESIGN.md）：
  字号   —— TDesign 桌面 12px 下限；11px 仅作 label 档（Material 3 labelSmall）
  间距   —— 4px 栅格（Arco / Ant / Bootstrap / Carbon 一致）
  暗色阶 —— elevation 越高越亮（Radix / Mantlr 明确规则，非简单反色）
  主色   —— 暗色下品牌色降饱和，保证压白字可读（WCAG AA 4.5:1）
  边框   —— 默认不加，用 surface 亮度差分层

命名采用两层：
  Primitive（palette*）：原始色阶，只在本文件内部使用
  Semantic （surface_1 / text_primary 等）：业务代码只准用这一层
"""

from __future__ import annotations


class Palette:
    """Primitive 层：原始色阶，不直接被业务引用。

    色相选择：不用纯灰（R=G=B），而是带极轻微冷调（蓝偏 +1~+3）。
    纯灰在暗色下会「发死」——Linear / Vercel / Radix 的暗色中性阶都带这点冷调。
    """

    # 中性灰阶（按 WCAG 亮度单调递增 + 轻微冷调）
    NEUTRAL_1000 = "#08090A"   # 画布 / 最深
    NEUTRAL_950 = "#0F1011"    # 应用底 / 面板
    NEUTRAL_900 = "#161719"    # 卡片
    NEUTRAL_850 = "#1D1F21"    # 输入框 / 控件
    NEUTRAL_800 = "#23252A"    # 浮层 / hover
    NEUTRAL_750 = "#2A2C32"    # active
    NEUTRAL_650 = "#3C4048"
    NEUTRAL_700 = "#33363D"    # 强调描边
    NEUTRAL_600 = "#4A4E57"
    NEUTRAL_500 = "#6B7079"    # 禁用文字
    NEUTRAL_400 = "#8E97A1"    # 提示文字（最高层浮层上仍 >=4.9:1）
    NEUTRAL_300 = "#949CA6"    # 三级文字
    NEUTRAL_200 = "#B4BCC6"    # 次级文字
    NEUTRAL_100 = "#D6DBE1"
    NEUTRAL_50 = "#F7F8F8"     # 主文字

    # 品牌靛蓝（Linear 同色系；降饱和后压白字达标）
    INDIGO_700 = "#4F5ABF"    # hover/active：比 base 暗
    INDIGO_600 = "#5E6AD2"    # base
    INDIGO_500 = "#7C87E0"    # 仅用于焦点环等非文字
    INDIGO_400 = "#9AA3EA"
    INDIGO_300 = "#BFC5F2"

    # 语义色
    GREEN_600 = "#2E9E5B"
    GREEN_500 = "#3DD68C"
    AMBER_600 = "#B8690F"
    AMBER_500 = "#FF8A3D"
    RED_700 = "#A32B23"       # danger hover：压白字更深
    RED_600 = "#C4342B"       # danger 填充：压白字达标
    RED_500 = "#E5484D"       # danger_emphasis：暗底上作图标/文字
    RED_400 = "#FF6B61"


class Color:
    """Semantic 层：业务代码只用这些。"""

    # —— 表面（零边框方案，完全靠亮度差分层次）——
    canvas = Palette.NEUTRAL_1000       # 画布工作区（最深，独立值）
    surface_base = "#0A0B0D"            # 应用底（比 canvas 略亮，避免层级断裂）
    surface_1 = Palette.NEUTRAL_950     # 侧栏 / 面板
    surface_2 = Palette.NEUTRAL_900     # 卡片 / 分组
    surface_3 = Palette.NEUTRAL_850     # 输入框 / 下拉
    surface_4 = Palette.NEUTRAL_800     # 弹层 / 悬浮
    surface_hover = Palette.NEUTRAL_800
    surface_active = Palette.NEUTRAL_750
    surface_selected = "#1F2437"        # 选中行：靛蓝低饱和底

    # —— 文本 ——
    text_primary = Palette.NEUTRAL_50
    text_secondary = Palette.NEUTRAL_200
    text_tertiary = Palette.NEUTRAL_300
    text_muted = Palette.NEUTRAL_400
    text_disabled = Palette.NEUTRAL_500
    text_on_accent = "#FFFFFF"
    text_on_selected = "#E4E7FF"
    text_link = Palette.INDIGO_400

    # —— 边框（默认不用；仅浮层/分隔需要时取最低一档）——
    # border_subtle 的取值原则：与 surface_1 的亮度差 <= 4。
    # 它只用于「必须被看见的分割线」，不能当卡片描边 ——
    # 实测 #1A1C1F 与面板底亮度差 11.9，在近黑背景上会显示为一条明显亮线，
    # 与 01 方案「零边框、靠亮度差分层次」的核心决策相冲突。
    border_subtle = "#141619"           # 分割线（亮度差 ~3，近乎不可见）
    border_default = Palette.NEUTRAL_800
    border_control = Palette.NEUTRAL_800
    border_strong = Palette.NEUTRAL_700
    border_focus = Palette.INDIGO_500

    # —— 品牌与状态 ——
    accent = Palette.INDIGO_600
    accent_hover = Palette.INDIGO_700
    accent_active = "#434DA6"
    accent_subtle = "#1F2437"

    success = Palette.GREEN_500
    warning = Palette.AMBER_500

    # danger 有两个互相冲突的用途，必须拆两步（本规范的硬结论）：
    #   ① 作为「颜色」出现在暗底上（错误图标 / 文字）→ 需要够亮，>=3:1
    #   ② 作为「填充色」承载白字（删除按钮）→ 需要够暗，白字 >=4.5:1
    # 单值无解：实测 #C4342B 压白字达标但在 surface_1 上仅约 2.6。
    danger = Palette.RED_600            # 填充用
    danger_emphasis = Palette.RED_500   # 图形/文字用
    danger_hover = Palette.RED_700
    info = Palette.INDIGO_400

    # —— 覆盖层 ——
    overlay_scrim = "rgba(0, 0, 0, 0.60)"
    overlay_hover = "rgba(255, 255, 255, 0.05)"
    overlay_pressed = "rgba(255, 255, 255, 0.08)"


class Typography:
    """字号 / 字重 / 行高。

    规则（TDesign + Material 3）：
      桌面正文字号下限 12px；11px 只允许 label / 角标；
      行高 = 字号 + 8（TDesign 官方规则，14/16px 恰好＝1.5 倍）。
    """

    # 字体栈：中文优先。Windows 下 Segoe UI 不含汉字，排在前面会触发逐字回退，
    # 导致中英混排时字重与基线不一致 —— 这是旧界面「字看着不精致」的主因。
    #
    # ⚠ 性能红线（2026-10-27 实测）：QSS 的 font-family **只能写一个字体名**。
    # 只要并列第二个名字（包括 sans-serif 这类通用族），Qt 就会对每个新控件
    # 遍历系统全部 2004 个字体族做匹配，单个控件入场从 0ms 变成 ~420ms，
    # 主窗口启动因此多花 3 秒以上。实测数据：
    #   1 个字体名  → 0 ms
    #   2 个字体名  → 2124 ms   ← 断崖，不是线性
    #   3 个字体名  → 2270 ms
    #   通用族 sans-serif → 2157 ms
    # 回退需求改用 QFont.insertSubstitutions 在程序层解决（见 font_stack()），
    # 既拿到同样的回退效果，又避免 QSS 侧的多字体匹配开销。
    family = '"Microsoft YaHei UI"'          # QSS 用的主字体（只写一个）
    family_mono = '"Cascadia Mono"'

    # 回退链：主字体不存在时，Qt 按这个顺序替换（不走 QSS，无性能损耗）
    family_fallbacks = ("Microsoft YaHei", "PingFang SC", "Segoe UI", "Arial")
    family_mono_fallbacks = ("Consolas", "Courier New", "Menlo")

    @classmethod
    def font_stack(cls) -> str:
        """人类可读的完整字体栈（用于文档、日志、非 QSS 场景如 QFont）。

        禁止把返回值直接塞进 QSS 的 font-family —— 见上方性能红线说明。
        """
        names = [n.strip('"') for n in cls.family.split(",")]
        return ", ".join(f'"{n}"' for n in names + list(cls.family_fallbacks))

    # 字号档（px）—— 01 方案基准 13px
    size_caption = 11    # 仅 label / 角标
    size_sm = 12         # 辅助说明（桌面下限）
    size_base = 13       # 正文 / 控件
    size_md = 14         # 强调正文 / 对话框主体
    size_lg = 16         # 区块标题
    size_xl = 20         # 页面标题
    size_2xl = 24        # 大标题

    # 行高 = 字号 + 8
    line_caption = 19
    line_sm = 20
    line_base = 21
    line_md = 22
    line_lg = 24
    line_xl = 28
    line_2xl = 32

    # 字重
    weight_regular = 400
    weight_medium = 500
    weight_semibold = 600
    weight_bold = 700

    # 字距（01 方案特征：标题收紧）
    tracking_title = -0.2
    tracking_body = 0.0


class Space:
    """间距：4px 栅格（Arco / Ant / Bootstrap / Carbon 一致）。

    01 方案间距节奏偏松（gap 10 / pad 14），这是「透气感」的来源。
    2px 与 6px 作为补充档位保留 —— Tailwind/Chakra 的 space-0.5 / space-1.5
    有先例，且本项目 2px 出现 14 次（边框内衬），强删会造成布局位移。
    """

    xxs = 2
    xs = 4
    sm = 6
    md = 8
    gap = 10        # 01 方案：区块内元素间距（Tailwind space-2.5 / Chakra 2.5 同档）
    lg = 12
    pad = 14        # 01 方案：面板内边距（Tailwind space-3.5 / Chakra 3.5 同档）
    xl = 16
    xxl = 20
    xxxl = 24
    huge = 32


class Radius:
    """圆角：收敛到 4 档，去掉 2/3/5/7 这些绘制抖动产生的碎值。

    01 方案用 6 作为基准（介于锐利与圆润之间）。
    """

    sm = 4      # 小控件 / 标签
    md = 6      # 按钮 / 输入框（01 基准）
    lg = 8      # 卡片 / 面板
    xl = 12     # 对话框
    full = 9999 # 胶囊


class Size:
    """控件尺寸：桌面工具的点击目标下限。"""

    control_h_sm = 26
    control_h = 30        # 01 方案基准
    control_h_lg = 34
    control_h_xl = 38     # 主操作按钮

    icon_sm = 14
    icon = 16
    icon_lg = 20

    # 触控/精确点击最小目标（WCAG 2.5.8 Target Size 24x24）
    hit_target_min = 24


class Motion:
    """动效时长。"""

    instant = 80
    fast = 120
    base = 160
    slow = 240
    easing = "cubic-bezier(0.4, 0, 0.2, 1)"


class Elevation:
    """阴影：暗色下柔和且低透明度。

    01 方案是零边框设计，层次主要靠亮度差；阴影只用于真正的浮层（弹窗/菜单），
    且要比亮色主题更收敛——大模糊在近黑背景上会发浑。
    """

    none = "none"
    sm = "0 1px 2px rgba(0, 0, 0, 0.40)"
    md = "0 2px 8px rgba(0, 0, 0, 0.48)"
    lg = "0 8px 24px rgba(0, 0, 0, 0.56)"
    xl = "0 16px 48px rgba(0, 0, 0, 0.64)"


class ZIndex:
    """层叠阶梯：照 Bootstrap/Chakra 的具名阶梯，禁止 calc 偏移。"""

    base = 0
    raised = 1
    sticky = 10
    dropdown = 1000
    overlay = 1300
    modal = 1400
    popover = 1500
    toast = 1700
    tooltip = 1800


# 边框策略（01 方案的核心决策，供 QSS 生成器读取）
BORDER_POLICY = {
    "default": "none",      # 卡片/面板默认不描边
    "use_brightness": True, # 用 surface 亮度差分层次
    "divider_only": True,   # 仅结构性分割线才用 border_subtle
}


# 便于 QSS 模板与主题层统一取值的字典视图
def as_dict() -> dict:
    """导出扁平字典（键名 semantic.path 形式），供 QSS 生成与文档使用。"""
    out = {}
    for cls in (Color, Typography, Space, Radius, Size, Motion, Elevation, ZIndex):
        name = cls.__name__.lower()
        for k, v in vars(cls).items():
            if k.startswith("_") or callable(v) or isinstance(v, classmethod):
                continue
            out[f"{name}.{k}"] = v
    return out


__all__ = [
    "Palette",
    "Color",
    "Typography",
    "Space",
    "Radius",
    "Size",
    "Motion",
    "Elevation",
    "ZIndex",
    "BORDER_POLICY",
    "as_dict",
]
