pragma Singleton
import QtQuick

QtObject {
    // QML mapping of Hermes-CN-Desktop shared-ui tokens. See
    // THIRD_PARTY_NOTICES.md for source and license notices.
    // 默认深色（2026-10-28 按产品定位调整）。浅色主题仍完整保留，
    // 由标题栏的太阳/月亮按钮切换并持久化到 uiAppearance/themeMode。
    property bool darkMode: true

    readonly property color bgApp: darkMode ? "#111111" : "#f4f4f3"
    readonly property color bgBar: darkMode ? "#181818" : "#ffffff"
    readonly property color bgPanel: darkMode ? "#181818" : "#ffffff"
    readonly property color bgRaised: darkMode ? "#202020" : "#f7f7f6"
    readonly property color bgControl: darkMode ? "#242424" : "#ffffff"
    readonly property color bgHover: darkMode ? "#2a2a2a" : "#ececeb"
    readonly property color bgCanvas: darkMode ? "#111111" : "#f7f7f5"
    readonly property color bgSelected: darkMode ? "#2a2a2a" : "#e9e9e5"

    readonly property color border: darkMode ? "#292929" : "#e8e8e5"
    readonly property color borderStrong: darkMode ? "#3a3a3a" : "#d5d5d2"
    readonly property color focusRing: darkMode ? "#f1f1ef" : "#171716"
    readonly property color gridDot: darkMode ? "#3a3a3a" : "#d7d7d1"

    readonly property color textPrimary: darkMode ? "#f1f1ef" : "#171716"
    readonly property color textSecondary: darkMode ? "#cececa" : "#3f3f3d"
    readonly property color textMuted: darkMode ? "#a1a19d" : "#656562"
    readonly property color textDisabled: darkMode ? "#a1a19d" : "#73736f"

    // High-contrast neutral is the primary action. Accent colors express state, not branding.
    readonly property color accent: darkMode ? "#f1f1ef" : "#171716"
    readonly property color accentHover: darkMode ? "#ffffff" : "#2b2b2a"
    readonly property color accentPressed: darkMode ? "#cececa" : "#000000"
    readonly property color accentSoft: darkMode ? "#2a2a2a" : "#ecece8"
    readonly property color accentForeground: darkMode ? "#111111" : "#ffffff"
    readonly property color selectionBackground: accent
    readonly property color selectionForeground: accentForeground
    readonly property color info: darkMode ? "#b8b8b4" : "#5c7890"
    readonly property color warning: darkMode ? "#cca700" : "#9d6b00"
    readonly property color danger: darkMode ? "#f48771" : "#d13438"
    readonly property color success: darkMode ? "#89d185" : "#16825d"

    readonly property color overlayModal: "#55000000"
    readonly property color errorSurface: darkMode ? "#30201d" : "#fff1ef"
    readonly property color errorBorder: darkMode ? "#75483f" : "#e0aaa4"
    readonly property color errorText: darkMode ? "#f48771" : "#a33a31"
    readonly property color successSurface: darkMode ? "#213020" : "#ecf8f3"
    readonly property color successBorder: darkMode ? "#4c7049" : "#a7dbc7"
    readonly property color progressTrack: darkMode ? "#2a2a2a" : "#deded9"

    readonly property color swatchSurface: darkMode ? "#242424" : "#f1f1ee"
    readonly property color swatchAccentBorder: darkMode ? "#f1f1ef" : "#171717"
    readonly property color swatchPaper: darkMode ? "#ffffff" : "#ffffff"
    readonly property color canvasPaper: darkMode ? "#f7f7f4" : "#ffffff"
    readonly property color canvasPaperBorder: darkMode ? "#858581" : "#9e9e96"
    readonly property color selectionFill: darkMode ? "#f1f1ef25" : "#1b1b1b25"
    readonly property color transformFill: darkMode ? "#b8b8b435" : "#5c789025"
    readonly property color canvasHandle: darkMode ? "#f1f1ef" : "#ffffff"
    readonly property color canvasScrim: "#66000000"
    readonly property color cropAnchorBorder: darkMode ? "#f1f1ef" : "#171717"
    readonly property color canvasLabelSurface: darkMode ? "#202020" : "#f0f0ed"
    readonly property color statusPillSurface: darkMode ? "#213020" : "#edf8f4"
    readonly property color floatingPanelSurface: darkMode ? "#202020" : "#fdfdfb"
    readonly property color floatingPanelBorder: darkMode ? "#3a3a3a" : "#b9b9b1"

    // Compatibility aliases used by the current QML surface.
    readonly property color guide: info
    readonly property color amber: warning
    readonly property color coral: danger

    readonly property string bodyFont: "HarmonyOS Sans SC"
    readonly property string displayFont: "HarmonyOS Sans SC"
    readonly property string dataFont: "Cascadia Mono"
    readonly property string iconFont: "Segoe Fluent Icons"

    // Hermes primitives are square. Circular geometry such as knobs and
    // status dots owns its radius locally instead of borrowing these tokens.
    readonly property int radiusSmall: 0
    readonly property int radius: 0
    readonly property int radiusLarge: 0

    // Hermes primitives: strict 4 px grid and fixed component contracts.
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 20
    readonly property int space6: 24
    readonly property int fontSize2Xs: 10
    readonly property int fontSizeXs: 11
    readonly property int fontSizeSm: 12
    readonly property real fontSizeMd: 12.5
    readonly property int fontSizeLg: 14

    readonly property int buttonHeightXs: 24
    readonly property int buttonHeightSm: 28
    readonly property int buttonHeightMd: 32
    readonly property int buttonHeightLg: 36
    readonly property int buttonPaddingXs: 8
    readonly property int buttonPaddingSm: 8
    readonly property int buttonPaddingMd: 12
    readonly property int buttonPaddingLg: 16
    readonly property int buttonGap: 8

    // This inspector opts into Hermes compact density.
    readonly property int inputHeightSm: 24
    readonly property int inputHeightMd: 28
    readonly property int inputHeightLg: 32
    readonly property int inputPaddingX: 8
    readonly property int segmentHeight: 24
    readonly property int tabHeight: 40
    readonly property int switchWidth: 32
    readonly property int switchHeight: 20
    readonly property int switchThumbSize: 12
    readonly property real fieldLabelFontSize: 11.5
    readonly property int fieldHintFontSize: 11
    readonly property int fieldHorizontalLabelWidth: 160
    readonly property int fieldHorizontalGap: 16
    readonly property int fieldGap: 8
    readonly property int fieldControlGap: 4

    readonly property int compactControlHeight: 24
    readonly property int comfortableControlHeight: 32
    readonly property int controlHeight: compactControlHeight
    readonly property int commandHeight: 34
    readonly property int toolButtonSize: 32
    readonly property int railButtonSize: 32
    readonly property int toolRailWidth: 48
    readonly property int layerPanelMinWidth: 200
    readonly property int layerPanelMaxWidth: 420
    readonly property int inspectorPanelWidth: 320
    readonly property int canvasMinWidth: 280
    readonly property int sidebarResizeHandleWidth: 8
    readonly property int sidebarResizeStep: 16
    readonly property int sectionHeaderHeight: 40
    readonly property int motionFast: 120
    readonly property int motionNormal: 180

    // Inspector geometry stays on the 4 px grid. Four-character Chinese
    // labels fit without truncation in the primary field column.
    readonly property int inspectorLabelColWidth: 64
    readonly property int inspectorCompactLabelColWidth: 52
    readonly property int inspectorRowHeight: compactControlHeight
    readonly property int inspectorColSpacing: 12
    readonly property int inspectorRowSpacing: 8
    readonly property int inspectorSectionGutter: 12
    readonly property int inspectorPairBreakpoint: 320
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
