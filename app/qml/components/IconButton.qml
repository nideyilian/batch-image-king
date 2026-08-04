import QtQuick
import QtQuick.Controls

Rectangle {
    id: root

    property string glyph: ""
    property string tooltip: ""
    property bool active: false
    property bool primary: false
    property int buttonSize: 32
    signal clicked()

    implicitWidth: buttonSize
    implicitHeight: buttonSize
    radius: Theme.radiusSmall
    color: {
        if (!enabled) return "transparent"
        if (mouseArea.pressed) return primary ? Theme.accentPressed : Theme.bgHover
        if (mouseArea.containsMouse) return primary ? Theme.accentHover : Theme.bgHover
        if (primary) return Theme.accent
        if (active) return Theme.accentSoft
        return "transparent"
    }
    border.width: active && !primary ? 1 : 0
    border.color: Theme.accentPressed
    opacity: enabled ? 1 : 0.38

    Behavior on color {
        ColorAnimation { duration: Theme.motionFast }
    }

    AppIcon {
        anchors.centerIn: parent
        glyph: root.glyph
        iconSize: 16
        iconColor: root.primary ? "#09251d" : (root.active ? Theme.accent : Theme.textSecondary)
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: root.clicked()
    }

    ToolTip.visible: mouseArea.containsMouse && root.tooltip.length > 0
    ToolTip.text: root.tooltip
    ToolTip.delay: 480
    Accessible.name: tooltip
    Accessible.role: Accessible.Button
}
