import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    property string index: ""
    property string text: ""
    property string iconName: ""
    property bool active: false
    property string badge: ""
    signal clicked()

    implicitWidth: 112
    implicitHeight: 34
    radius: Theme.radiusSmall
    color: active
           ? Theme.accent
           : (mouse.containsMouse ? Theme.bgHover : "transparent")
    border.width: active ? 1 : 0
    border.color: Theme.accent
    activeFocusOnTab: enabled
    opacity: enabled ? 1 : 0.45

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 9
        spacing: 8

        Text {
            visible: root.index.length > 0
            text: root.index
            color: root.active ? Theme.accentForeground : Theme.textMuted
            font.family: Theme.dataFont
            font.pixelSize: 10
        }

        AppIcon {
            visible: root.iconName.length > 0
            iconName: root.iconName
            iconSize: 15
            iconColor: root.active ? Theme.accentForeground : Theme.textSecondary
        }

        Text {
            text: root.text
            color: root.active ? Theme.accentForeground : Theme.textPrimary
            font.family: Theme.bodyFont
            font.pixelSize: 12
            font.weight: root.active ? Font.DemiBold : Font.Normal
            Layout.fillWidth: true
            elide: Text.ElideRight
        }

        Text {
            visible: root.badge.length > 0
            text: root.badge
            color: root.active ? Theme.accentForeground : Theme.textMuted
            font.family: Theme.dataFont
            font.pixelSize: 9
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPressed: root.forceActiveFocus(Qt.MouseFocusReason)
        onClicked: root.clicked()
    }

    Keys.onSpacePressed: clicked()
    Keys.onReturnPressed: clicked()
    ToolTip.visible: mouse.containsMouse && root.text.length > 0
    ToolTip.text: root.text
    ToolTip.delay: 420
    Accessible.name: root.text
    Accessible.role: Accessible.Button
}
