pragma Singleton
import QtQuick

QtObject {
    // Hermes desktop language: warm white surfaces, near-black actions,
    // hairline borders, and green reserved for runtime status.
    readonly property color bgApp: "#f1f1ee"
    readonly property color bgBar: "#ffffff"
    readonly property color bgPanel: "#fbfbf9"
    readonly property color bgRaised: "#f5f5f2"
    readonly property color bgControl: "#ffffff"
    readonly property color bgHover: "#eeeeea"
    readonly property color bgCanvas: "#f7f7f5"
    readonly property color bgSelected: "#e9e9e5"

    readonly property color border: "#deded9"
    readonly property color borderStrong: "#c8c8c1"
    readonly property color focusRing: "#1b1b1b"
    readonly property color gridDot: "#d7d7d1"

    readonly property color textPrimary: "#1b1b1b"
    readonly property color textSecondary: "#555652"
    readonly property color textMuted: "#85867f"
    readonly property color textDisabled: "#b1b1aa"

    // Black is the primary action. Accent colors express state, not branding.
    readonly property color accent: "#171717"
    readonly property color accentHover: "#2b2b2b"
    readonly property color accentPressed: "#000000"
    readonly property color accentSoft: "#ecece8"
    readonly property color accentForeground: "#ffffff"
    readonly property color info: "#5c7890"
    readonly property color warning: "#c58d18"
    readonly property color danger: "#b42318"
    readonly property color success: "#18b78b"

    readonly property color overlayModal: "#55000000"
    readonly property color errorSurface: "#fff1ef"
    readonly property color errorBorder: "#e0aaa4"
    readonly property color errorText: "#a33a31"
    readonly property color successSurface: "#ecf8f3"
    readonly property color successBorder: "#a7dbc7"
    readonly property color progressTrack: "#deded9"

    readonly property color swatchSurface: "#f1f1ee"
    readonly property color swatchAccentBorder: "#171717"
    readonly property color swatchPaper: "#ffffff"
    readonly property color canvasPaper: "#ffffff"
    readonly property color canvasPaperBorder: "#9e9e96"
    readonly property color selectionFill: "#1b1b1b25"
    readonly property color transformFill: "#5c789025"
    readonly property color canvasHandle: "#ffffff"
    readonly property color canvasScrim: "#66000000"
    readonly property color cropAnchorBorder: "#171717"
    readonly property color canvasLabelSurface: "#f0f0ed"
    readonly property color statusPillSurface: "#edf8f4"
    readonly property color floatingPanelSurface: "#fdfdfb"
    readonly property color floatingPanelBorder: "#b9b9b1"

    // Compatibility aliases used by the current QML surface.
    readonly property color guide: info
    readonly property color amber: warning
    readonly property color coral: danger

    readonly property string bodyFont: "MiSans"
    readonly property string displayFont: "HarmonyOS Sans SC"
    readonly property string dataFont: "Cascadia Mono"
    readonly property string iconFont: "Segoe Fluent Icons"

    // Hermes primitives are square. Circular geometry such as knobs and
    // status dots owns its radius locally instead of borrowing these tokens.
    readonly property int radiusSmall: 0
    readonly property int radius: 0
    readonly property int radiusLarge: 0
    readonly property int compactControlHeight: 24
    readonly property int comfortableControlHeight: 32
    readonly property int controlHeight: compactControlHeight
    readonly property int commandHeight: 34
    readonly property int toolButtonSize: 32
    readonly property int railButtonSize: 32
    readonly property int toolRailWidth: 48
    readonly property int layerPanelMinWidth: 200
    readonly property int layerPanelMaxWidth: 420
    readonly property int inspectorPanelMinWidth: 360
    readonly property int inspectorPanelMaxWidth: 560
    readonly property int canvasMinWidth: 280
    readonly property int sidebarResizeHandleWidth: 8
    readonly property int sidebarResizeStep: 16
    readonly property int sectionHeaderHeight: 38
    readonly property int motionFast: 120
    readonly property int motionNormal: 180

    // Labels stay compact; controls keep their own natural widths in the inspector.
    readonly property int inspectorLabelColWidth: 56
    readonly property int inspectorRowHeight: compactControlHeight
    readonly property int inspectorColSpacing: 8
    readonly property int inspectorTextEditorMaxWidth: 400
    readonly property int inspectorWSelect: 160
    readonly property int inspectorWInput: 160
    readonly property int inspectorWPair: 72
    readonly property int inspectorWSliderVB: 56
    readonly property int inspectorWSwatch: 160
    readonly property int inspectorWSeg2: 160
    readonly property int inspectorWSeg3: 160
    readonly property int inspectorWSeg4: 160
    readonly property int inspectorWAlign: 160
    readonly property int inspectorWBind: 160
}
