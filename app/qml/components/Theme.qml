pragma Singleton
import QtQuick

QtObject {
    readonly property color bgApp: "#0d1011"
    readonly property color bgBar: "#111516"
    readonly property color bgPanel: "#151a1c"
    readonly property color bgRaised: "#1a2022"
    readonly property color bgControl: "#20272a"
    readonly property color bgHover: "#293235"
    readonly property color bgCanvas: "#090c0d"
    readonly property color bgSelected: "#17352e"

    readonly property color border: "#2b3437"
    readonly property color borderStrong: "#3b474a"
    readonly property color focusRing: "#67e6c1"
    readonly property color gridDot: "#20282a"

    readonly property color textPrimary: "#f3f6f5"
    readonly property color textSecondary: "#aab5b1"
    readonly property color textMuted: "#84918c"
    readonly property color textDisabled: "#74807c"

    readonly property color accent: "#3bd5aa"
    readonly property color accentHover: "#67e6c1"
    readonly property color accentPressed: "#28b88f"
    readonly property color accentSoft: "#17352e"
    readonly property color accentForeground: "#06271f"
    readonly property color info: "#5ba7ff"
    readonly property color warning: "#f2b95f"
    readonly property color danger: "#f1786d"
    readonly property color success: "#65d88d"

    readonly property color overlayModal: "#990a0c0d"
    readonly property color errorSurface: "#35201f"
    readonly property color errorBorder: "#70413d"
    readonly property color errorText: "#e7a09a"
    readonly property color successSurface: "#173126"
    readonly property color successBorder: "#28583e"
    readonly property color progressTrack: borderStrong

    readonly property color swatchSurface: "#15221e"
    readonly property color swatchAccentBorder: "#84f0d0"
    readonly property color swatchPaper: "#f3f1ea"
    readonly property color canvasPaper: "#f4f3ef"
    readonly property color canvasPaperBorder: "#5c6260"
    readonly property color selectionFill: "#2330b58f"
    readonly property color transformFill: "#153fd2aa"
    readonly property color canvasHandle: "#f4f7f5"
    readonly property color canvasScrim: "#99090b0c"
    readonly property color cropAnchorBorder: "#231b0e"
    readonly property color canvasLabelSurface: "#e91b2021"
    readonly property color statusPillSurface: "#d916191b"
    readonly property color floatingPanelSurface: "#ec222729"
    readonly property color floatingPanelBorder: "#40504b"

    // Compatibility aliases for existing QML call sites.
    readonly property color guide: info
    readonly property color amber: warning
    readonly property color coral: danger

    readonly property string bodyFont: "MiSans"
    readonly property string displayFont: "HarmonyOS Sans SC"
    readonly property string dataFont: "Cascadia Mono"
    readonly property string iconFont: "Segoe Fluent Icons"

    readonly property int radiusSmall: 4
    readonly property int radius: 6
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
    // 用途：图层侧边栏参数面板（Main.qml / InspectorRow 及所有子控件）
    // 所有宽度为固定紧凑值，除 SliderFill 动态外，不随面板宽度膨胀 → 杜绝大横条
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
