import QtQuick

Rectangle {
    id: root

    property bool checked: false
    signal toggled(bool checked)

    implicitWidth: 38
    implicitHeight: 22
    radius: height / 2
    color: checked ? Theme.accent : Theme.bgControl
    border.width: checked ? 0 : 1
    border.color: Theme.borderStrong

    Behavior on color {
        ColorAnimation { duration: Theme.motionNormal }
    }

    Rectangle {
        width: 16
        height: 16
        radius: 8
        x: root.checked ? root.width - width - 3 : 3
        anchors.verticalCenter: parent.verticalCenter
        color: root.checked ? "#0d2c23" : Theme.textMuted

        Behavior on x {
            NumberAnimation { duration: Theme.motionNormal; easing.type: Easing.OutCubic }
        }
    }

    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: {
            root.checked = !root.checked
            root.toggled(root.checked)
        }
    }
}
