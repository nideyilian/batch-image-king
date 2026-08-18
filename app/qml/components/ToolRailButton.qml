import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: toolButton
    property int toolIndex: 0
    property string iconName: ""
    property string label: ""
    signal triggered()

    width: Theme.railButtonSize
    height: Theme.railButtonSize
    radius: Theme.radiusSmall
    color: activeTool === toolIndex ? Theme.accentSoft : (toolMouse.containsMouse ? Theme.bgHover : "transparent")
    border.width: activeTool === toolIndex ? 1 : 0
    border.color: activeFocus ? Theme.focusRing : Theme.accentPressed
    activeFocusOnTab: enabled

    AppIcon {
        anchors.centerIn: parent
        iconName: toolButton.iconName
        iconSize: 18
        iconColor: !toolButton.enabled
                   ? Theme.textDisabled
                   : (activeTool === toolButton.toolIndex ? Theme.accent : Theme.textSecondary)
    }

    MouseArea {
        id: toolMouse
        anchors.fill: parent
        enabled: toolButton.enabled
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPressed: toolButton.forceActiveFocus(Qt.MouseFocusReason)
        onClicked: {
            activeTool = toolButton.toolIndex
            toolButton.triggered()
        }
    }

    Keys.onSpacePressed: triggered()

    ToolTip.visible: toolMouse.containsMouse
    ToolTip.text: toolButton.label
    ToolTip.delay: 420
}
