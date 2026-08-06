import QtQuick

Rectangle {
    id: root

    property bool checked: false
    property string accessibleName: "开关"
    signal toggled(bool checked)

    implicitWidth: 38
    implicitHeight: 22
    radius: height / 2
    color: checked ? Theme.accent : Theme.bgControl
    opacity: enabled ? 1 : 0.56
    activeFocusOnTab: enabled
    border.width: activeFocus ? 1 : (checked ? 0 : 1)
    border.color: activeFocus ? Theme.focusRing : Theme.borderStrong

    Behavior on color {
        ColorAnimation { duration: Theme.motionNormal }
    }

    Rectangle {
        width: 16
        height: 16
        radius: 8
        x: root.checked ? root.width - width - 3 : 3
        anchors.verticalCenter: parent.verticalCenter
        color: root.checked ? Theme.accentForeground : Theme.textMuted

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
