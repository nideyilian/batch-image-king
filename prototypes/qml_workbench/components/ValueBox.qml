import QtQuick

Rectangle {
    id: root

    property alias text: input.text
    property string suffix: ""
    property bool editable: true

    implicitWidth: 94
    implicitHeight: Theme.controlHeight
    radius: Theme.radiusSmall
    color: Theme.bgControl
    border.width: 1
    border.color: input.activeFocus ? Theme.accent : Theme.borderStrong

    Behavior on border.color {
        ColorAnimation { duration: Theme.motionFast }
    }

    TextInput {
        id: input
        anchors.left: parent.left
        anchors.right: suffixLabel.left
        anchors.verticalCenter: parent.verticalCenter
        anchors.leftMargin: 9
        anchors.rightMargin: 4
        color: Theme.textPrimary
        selectionColor: Theme.accentPressed
        selectedTextColor: Theme.textPrimary
        font.family: Theme.bodyFont
        font.pixelSize: 12
        readOnly: !root.editable
        selectByMouse: true
        verticalAlignment: TextInput.AlignVCenter
        clip: true
    }

    Text {
        id: suffixLabel
        anchors.right: parent.right
        anchors.rightMargin: 8
        anchors.verticalCenter: parent.verticalCenter
        text: root.suffix
        visible: text.length > 0
        color: Theme.textMuted
        font.family: Theme.bodyFont
        font.pixelSize: 10
    }
}
