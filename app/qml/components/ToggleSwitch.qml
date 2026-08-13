import QtQuick

Rectangle {
    id: root

    property bool checked: false
    property string accessibleName: "开关"
    signal toggled(bool checked)

    implicitWidth: Theme.switchWidth
    implicitHeight: Theme.switchHeight
    radius: Theme.switchHeight / 2
    color: !enabled ? Theme.bgRaised : (checked ? Theme.accent : Theme.bgControl)
    activeFocusOnTab: enabled
    border.width: activeFocus ? 1 : (enabled && checked ? 0 : 1)
    border.color: activeFocus ? Theme.focusRing : (enabled ? Theme.borderStrong : Theme.border)

    Behavior on color {
        ColorAnimation { duration: Theme.motionNormal }
    }

    Rectangle {
        width: Theme.switchThumbSize
        height: Theme.switchThumbSize
        radius: Theme.switchThumbSize / 2
        x: root.checked ? root.width - width - Theme.space1 : Theme.space1
        anchors.verticalCenter: parent.verticalCenter
        color: !root.enabled
               ? Theme.textDisabled
               : (root.checked ? Theme.accentForeground : Theme.textMuted)

        Behavior on x {
            NumberAnimation { duration: Theme.motionNormal; easing.type: Easing.OutCubic }
        }
    }

    MouseArea {
        anchors.fill: parent
        enabled: root.enabled
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
            root.forceActiveFocus(Qt.MouseFocusReason)
            root.checked = !root.checked
            root.toggled(root.checked)
        }
    }

    Keys.onSpacePressed: {
        checked = !checked
        toggled(checked)
    }

    Accessible.name: accessibleName
    Accessible.description: checked ? "已开启" : "已关闭"
    Accessible.role: Accessible.CheckBox
    Accessible.checked: checked
}
