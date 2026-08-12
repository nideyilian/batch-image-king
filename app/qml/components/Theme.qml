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
}
