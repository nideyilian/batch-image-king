import QtQuick
import QtQuick.Controls

Rectangle {
    id: root

    property string iconName: ""
    property string glyph: ""
    property string tooltip: ""
    property bool active: false
    property bool primary: false
    property bool destructive: false
    property int buttonSize: Theme.toolButtonSize
    property int iconSize: 16
    signal clicked()

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    radius: Theme.radiusSmall
    color: {
        if (!enabled) return "transparent"
        if (mouseArea.pressed) {
            if (destructive) return Theme.danger
            return primary ? Theme.accentPressed : Theme.bgHover
        }
        if (mouseArea.containsMouse || activeFocus) {
            if (destructive) return Qt.rgba(Theme.danger.r, Theme.danger.g, Theme.danger.b, 0.18)
            return primary ? Theme.accentHover : Theme.bgHover
        }
        if (primary) return Theme.accent
        if (active) return Theme.accentSoft
        return "transparent"
    }
    border.width: activeFocus || (active && !primary) ? 1 : 0
    border.color: activeFocus ? Theme.focusRing : (destructive ? Theme.errorBorder : Theme.borderStrong)
    activeFocusOnTab: enabled

    Behavior on color { ColorAnimation { duration: Theme.motionFast } }
    Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }

    AppIcon {
        anchors.centerIn: parent
        iconName: root.iconName
        glyph: root.glyph
        iconSize: root.iconSize
        iconColor: {
            if (!root.enabled) return Theme.textDisabled
            if (root.destructive) return Theme.danger
            if (root.primary) return Theme.accentForeground
            if (root.active) return Theme.accent
            return Theme.textSecondary
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
    Keys.onEnterPressed: clicked()

    ToolTip.visible: mouseArea.containsMouse && root.tooltip.length > 0
    ToolTip.text: root.tooltip
    ToolTip.delay: 480
    Accessible.name: tooltip
    Accessible.role: Accessible.Button
}
