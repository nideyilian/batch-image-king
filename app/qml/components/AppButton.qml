import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root

    property string text: ""
    property string iconName: ""
    // Hermes Button contract. Legacy values stay supported while callers
    // migrate from primary/secondary/destructive to variant + tone.
    property string variant: "outline"
    property string tone: "neutral"
    property string size: "md"
    property bool fullWidth: false
    property bool iconOnly: false
    property bool loading: false
    property int buttonHeight: -1
    property int horizontalPadding: -1
    signal clicked()

    property bool primary: variant === "primary"
    property bool destructive: variant === "destructive"
    readonly property string effectiveVariant: primary
                                               ? "solid"
                                               : (variant === "secondary"
                                                  ? "outline"
                                                  : (destructive ? "soft" : variant))
    readonly property string effectiveTone: primary
                                            ? "accent"
                                            : (destructive ? "danger" : tone)
    readonly property int sizeHeight: size === "xs"
                                      ? Theme.buttonHeightXs
                                      : (size === "sm"
                                         ? Theme.buttonHeightSm
                                         : (size === "lg"
                                            ? Theme.buttonHeightLg
                                            : Theme.buttonHeightMd))
    readonly property int sizePadding: size === "xs"
                                       ? Theme.buttonPaddingXs
                                       : (size === "sm"
                                          ? Theme.buttonPaddingSm
                                          : (size === "lg"
                                             ? Theme.buttonPaddingLg
                                             : Theme.buttonPaddingMd))
    readonly property color toneForeground: effectiveTone === "danger"
                                            ? Theme.danger
                                            : (effectiveTone === "success"
                                               ? Theme.success
                                               : (effectiveTone === "warning"
                                                  ? Theme.warning
                                                  : Theme.textPrimary))
    readonly property color toneSurface: effectiveTone === "danger"
                                         ? Theme.errorSurface
                                         : (effectiveTone === "success"
                                            ? Theme.successSurface
                                            : Theme.bgRaised)
    readonly property color toneBorder: effectiveTone === "danger"
                                        ? Theme.errorBorder
                                        : (effectiveTone === "accent"
                                           ? Theme.focusRing
                                           : Theme.borderStrong)

    Layout.fillWidth: fullWidth
    implicitWidth: iconOnly
                   ? implicitHeight
                   : contentRow.implicitWidth
                     + (horizontalPadding >= 0 ? horizontalPadding : sizePadding) * 2
    implicitHeight: effectiveVariant === "plain"
                    ? contentRow.implicitHeight
                    : (buttonHeight > 0 ? buttonHeight : sizeHeight)
    radius: Theme.radiusSmall
    color: {
        if (effectiveVariant === "plain") return "transparent"
        if (!enabled) return effectiveVariant === "ghost" ? "transparent" : Theme.bgRaised
        if (effectiveVariant === "ghost") return mouseArea.containsMouse ? toneSurface : "transparent"
        if (effectiveVariant === "solid") {
            if (effectiveTone === "accent")
                return mouseArea.pressed ? Theme.accentPressed
                                         : (mouseArea.containsMouse ? Theme.accentHover : Theme.accent)
            return toneForeground
        }
        if (effectiveVariant === "soft")
            return mouseArea.containsMouse || mouseArea.pressed ? Theme.bgHover : toneSurface
        if (mouseArea.containsMouse || mouseArea.pressed || activeFocus)
            return Theme.bgHover
        return Theme.bgControl
    }
    border.width: effectiveVariant === "ghost" || effectiveVariant === "plain" ? 0 : 1
    border.color: !enabled ? Theme.border : (activeFocus ? Theme.focusRing : toneBorder)
    activeFocusOnTab: enabled && !loading

    transform: Translate {
        y: mouseArea.pressed && root.effectiveVariant !== "plain" ? 4 : 0
    }

    Behavior on color { ColorAnimation { duration: Theme.motionFast } }

    Row {
        id: contentRow
        anchors.centerIn: parent
        spacing: root.iconName.length > 0 && root.text.length > 0 ? Theme.buttonGap : 0

        AppIcon {
            visible: root.iconName.length > 0
            iconName: root.iconName
            iconSize: 15
            iconColor: !root.enabled
                       ? Theme.textDisabled
                       : (root.effectiveVariant === "solid"
                          ? Theme.accentForeground
                          : root.toneForeground)
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            visible: root.text.length > 0
            text: root.text
            color: !root.enabled
                   ? Theme.textDisabled
                   : (root.effectiveVariant === "solid"
                      ? Theme.accentForeground
                      : root.toneForeground)
            font.family: Theme.bodyFont
            font.pixelSize: root.size === "xs"
                            ? 11
                            : (root.size === "sm"
                               ? 11.5
                               : (root.size === "lg" ? 13 : 12))
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        enabled: root.enabled && !root.loading
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPressed: root.forceActiveFocus(Qt.MouseFocusReason)
        onClicked: root.clicked()
    }

    Keys.onSpacePressed: if (!loading) clicked()
    Keys.onReturnPressed: if (!loading) clicked()
    Accessible.name: text
    Accessible.role: Accessible.Button
}
