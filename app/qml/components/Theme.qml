pragma Singleton
import QtQuick

QtObject {
    readonly property color bgApp: "#101214"
    readonly property color bgBar: "#141719"
    readonly property color bgPanel: "#181c1e"
    readonly property color bgRaised: "#1e2325"
    readonly property color bgControl: "#242a2d"
    readonly property color bgHover: "#2b3235"
    readonly property color bgCanvas: "#0d0f10"
    readonly property color bgSelected: "#20332f"

    readonly property color border: "#2b3134"
    readonly property color borderStrong: "#3a4346"
    readonly property color gridDot: "#252a2c"

    readonly property color textPrimary: "#f2f4f3"
    readonly property color textSecondary: "#b8c0bd"
    readonly property color textMuted: "#747d7a"
    readonly property color textDisabled: "#505754"

    readonly property color accent: "#46d7ad"
    readonly property color accentHover: "#65e5c0"
    readonly property color accentPressed: "#30b58f"
    readonly property color accentSoft: "#173b32"
    readonly property color amber: "#f7bd63"
    readonly property color coral: "#f1786d"
    readonly property color success: "#65d88d"

    readonly property string bodyFont: "MiSans"
    readonly property string displayFont: "HarmonyOS Sans SC"
    readonly property string iconFont: "Segoe Fluent Icons"

    readonly property int radiusSmall: 4
    readonly property int radius: 6
    readonly property int controlHeight: 30
    readonly property int motionFast: 120
    readonly property int motionNormal: 180
}
