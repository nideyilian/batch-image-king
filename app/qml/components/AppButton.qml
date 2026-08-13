import QtQuick
import QtQuick.Controls

Rectangle {
    id: root

    property string text: ""
    property string iconName: ""
    property string variant: "secondary"
    property int buttonHeight: Theme.commandHeight
    property int horizontalPadding: 12
    signal clicked()

    property bool primary: variant === "primary"
    property bool destructive: variant === "destructive"
    readonly property bool ghost: variant === "ghost"

    implicitWidth: contentRow.implicitWidth + horizontalPadding * 2
    implicitHeight: buttonHeight
    radius: Theme.radiusSmall
    color: {
        if (!enabled) return ghost ? "transparent" : Theme.bgRaised
        if (ghost) return mouseArea.containsMouse ? Theme.bgHover : "transparent"
        if (mouseArea.pressed) return destructive ? Theme.danger : (primary ? Theme.accentPressed : Theme.bgHover)
        if (mouseArea.containsMouse || activeFocus) return destructive ? Theme.errorSurface : (primary ? Theme.accentHover : Theme.bgHover)
        if (destructive) return Theme.errorSurface
        return primary ? Theme.accent : Theme.bgControl
    }
    border.width: ghost ? 0 : 1
    border.color: !enabled
                  ? Theme.border
                  : (activeFocus ? Theme.focusRing : (destructive ? Theme.errorBorder : Theme.borderStrong))
    opacity: 1
    activeFocusOnTab: enabled

    Behavior on color { ColorAnimation { duration: Theme.motionFast } }

    Row {
        id: contentRow
        anchors.centerIn: parent
        spacing: root.iconName.length > 0 && root.text.length > 0 ? 7 : 0

        AppIcon {
            visible: root.iconName.length > 0
            iconName: root.iconName
            iconSize: 15
            iconColor: !root.enabled
                       ? Theme.textMuted
                       : (root.primary ? Theme.accentForeground : (root.destructive ? Theme.danger : Theme.textSecondary))
            anchors.verticalCenter: parent.verticalCenter
        }

        Text {
            visible: root.text.length > 0
            text: root.text
            color: !root.enabled
                   ? Theme.textMuted
                   : (root.primary ? Theme.accentForeground : (root.destructive ? Theme.danger : Theme.textPrimary))
            font.family: Theme.bodyFont
            font.pixelSize: 12
            font.weight: Font.DemiBold
            anchors.verticalCenter: parent.verticalCenter
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPressed: root.forceActiveFocus(Qt.MouseFocusReason)
        onClicked: root.clicked()
    }

    Keys.onSpacePressed: clicked()
    Keys.onReturnPressed: clicked()
    Accessible.name: text
    Accessible.role: Accessible.Button
}
