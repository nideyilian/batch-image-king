pragma Singleton
import QtQuick

QtObject {
    // ================================================================
    // 「琥珀印房 · Amber Atelier」主题色板 v2.0
    // 核心调性：深靛蓝底色 + 琥珀金点缀 + 玻璃态层次边框
    // 灵感来源：高端印刷工坊 / 暗房工作室 / 复古装帧
    // ================================================================

    // —— 背景层级（从低到高：画布 → 面板 → 浮层 → 控制）
    readonly property color bgApp:          "#0b0e14"   // 应用最底层：深夜靛
    readonly property color bgBar:          "#121822"   // 标题栏/标签栏/工具栏：深靛
    readonly property color bgPanel:        "#171e2c"   // 面板本体：靛青
    readonly property color bgRaised:       "#1e2738"   // 凸起卡片/悬浮项：浅靛
    readonly property color bgControl:      "#252f44"   // 控件底板：控制靛
    readonly property color bgHover:        "#2e3a52"   // 悬停态：悬停靛
    readonly property color bgCanvas:       "#090c12"   // 画布工作区：暗靛
    readonly property color bgSelected:     "#3d2f17"   // 选中行：琥珀软底

    // —— 边框与焦点（层次化双层边框：玻璃高光 + 结构阴影）
    readonly property color border:         "#3a4562"   // 常规边框：结构蓝
    readonly property color borderStrong:   "#4e5d82"   // 强调边框：显著蓝
    readonly property color focusRing:      "#f0b849"   // 焦点环：琥珀金亮
    readonly property color gridDot:        "#1e2738"   // 画布网格点

    // —— 玻璃态层次边框（Atelier Glass）
    readonly property color glassHighlight: "#2a354d"   // 玻璃顶高光 1px（上边框）
    readonly property color glassShadow:    "#070a10"   // 玻璃底阴影 1px（下边框）
    readonly property color glassFill:      "#141b28"   // 玻璃叠层填充（半透明面板用）
    readonly property color amberGlow:      "#2e220d"   // 琥珀柔光边（强调容器内侧）

    // —— 文字层级
    readonly property color textPrimary:    "#f4efe4"   // 主文字：暖米白
    readonly property color textSecondary:  "#b5ad9b"   // 次文字：暖灰
    readonly property color textMuted:      "#8a8476"   // 柔文字：淡暖灰
    readonly property color textDisabled:   "#726c61"   // 禁文字：暗暖灰

    // —— 主题色系（琥珀金核心）
    readonly property color accent:         "#e5a93c"   // 主色：琥珀金
    readonly property color accentHover:    "#f0b849"   // 悬停：琥珀亮
    readonly property color accentPressed:  "#c89030"   // 按压：琥珀深
    readonly property color accentSoft:     "#3d2f17"   // 软底：琥珀淡底
    readonly property color accentForeground: "#2a1f0a" // 琥珀底上的文字色：深棕
    readonly property color info:           "#5ba7ff"   // 信息：保留蓝
    readonly property color warning:        "#f0b849"   // 警告：琥珀亮（与 accent 呼应）
    readonly property color danger:         "#ef7d6f"   // 危险：珊瑚橙红
    readonly property color success:        "#5ec98a"   // 成功：冷调松绿（对比琥珀）

    // —— 叠层与状态面
    readonly property color overlayModal:   "#99070a10" // 模态遮罩：深靛 60%
    readonly property color errorSurface:   "#3b2320"   // 错误态底
    readonly property color errorBorder:    "#72413d"   // 错误态边
    readonly property color errorText:      "#e3a59e"   // 错误态文字
    readonly property color successSurface: "#1a3225"   // 成功态底
    readonly property color successBorder:  "#295742"   // 成功态边
    readonly property color progressTrack:  borderStrong

    // —— 色板与画板
    readonly property color swatchSurface:  "#1f2819"   // 色板底板（带绿调温暖）
    readonly property color swatchAccentBorder: "#f0c97d" // 色板琥珀描边
    readonly property color swatchPaper:    "#efead8"   // 色板纸白（暖调）
    readonly property color canvasPaper:    "#efead8"   // 画板纸色（暖米纸）
    readonly property color canvasPaperBorder: "#a58853" // 画板纸边（琥珀铜边）
    readonly property color selectionFill:  "#2d24108f" // 选区填充（琥珀半透明）
    readonly property color transformFill:  "#1f1908aa" // 变换中填充
    readonly property color canvasHandle:   "#f4efe4"   // 变换手柄：暖米白
    readonly property color canvasScrim:    "#99070a10" // 裁剪遮罩
    readonly property color cropAnchorBorder: "#3d2a0a" // 裁剪锚点边：深琥珀
    readonly property color canvasLabelSurface: "#e91b2021" // 画布标签底
    readonly property color statusPillSurface:  "#d916191b" // 状态胶囊底
    readonly property color floatingPanelSurface: "#ec1a2029" // 浮动面板
    readonly property color floatingPanelBorder: "#5a4b3a" // 浮动面板边（暖棕）

    // Compatibility aliases for existing QML call sites.
    readonly property color guide: info
    readonly property color amber: warning
    readonly property color coral: danger

    // —— 字体家族（保持不变，与用户偏好一致）
    readonly property string bodyFont:       "MiSans"
    readonly property string displayFont:    "HarmonyOS Sans SC"
    readonly property string dataFont:       "Cascadia Mono"
    readonly property string iconFont:       "Segoe Fluent Icons"

    // —— 半径与尺寸（保持紧凑，不做大改动）
    readonly property int radiusSmall: 4
    readonly property int radius:      6
    readonly property int radiusLarge: 8
    readonly property int controlHeight: 24
    readonly property int compactControlHeight: 20
    readonly property int commandHeight: 28
    readonly property int toolButtonSize: 26
    readonly property int railButtonSize: 30
    readonly property int sectionHeaderHeight: 28
    readonly property int motionFast: 120
    readonly property int motionNormal: 180

    // ================================================================
    // Inspector 设计规范 (Figma-Inspector 紧凑二列风格)
    // ⚠️ 所有宽度为固定紧凑值 — 保持不变（与 project_memory 契约一致）
    // ================================================================
    readonly property int inspectorLabelColWidth: 42           // Label 列固定宽
    readonly property int inspectorRowHeight: controlHeight    // 24px 标准行高
    readonly property int inspectorColSpacing: 6               // 控件间横向间距

    // —— 控件标准宽度（统一紧凑）
    readonly property int inspectorWSelect: 160                // SelectBox / FontSelectBox
    readonly property int inspectorWInput: 120                 // 单 ValueBox / ColorValueField
    readonly property int inspectorWPair: 82                   // 双控件并排各占宽
    readonly property int inspectorWSliderVB: 58               // Slider 配套 ValueBox
    readonly property int inspectorWSwatch: 186                // ColorValueField + SwatchPanel

    // —— 分段按钮宽度
    readonly property int inspectorWSeg2: 86                   // 2 段
    readonly property int inspectorWSeg3: 110                  // 3 段
    readonly property int inspectorWSeg4: 144                  // 4 段

    // —— 特殊控件宽度
    readonly property int inspectorWAlign: 108                 // 三按钮对齐容器
    readonly property int inspectorWBind: 90                   // 绑定按钮
}
