import QtQuick

Rectangle {
    id: root

    property var options: []
    property var value: options.length > 0 ? options[0].value : undefined
    property int optionHeight: 26
    property string accessibleName: "模式选择"
    signal activated(var value)

    readonly property int currentIndex: {
        for (var index = 0; index < options.length; index++) {
            if (options[index].value === value) return index
        }
        return -1
    }

    function activateIndex(index) {
        if (!enabled || options.length === 0) return
        var boundedIndex = Math.max(0, Math.min(options.length - 1, index))
        activated(options[boundedIndex].value)
    }

    implicitWidth: 180
    implicitHeight: Theme.controlHeight
    radius: Theme.radiusSmall
    color: Theme.bgControl
    border.width: 1
    border.color: Theme.border
    activeFocusOnTab: enabled

    Keys.onLeftPressed: activateIndex(currentIndex <= 0 ? options.length - 1 : currentIndex - 1)
    Keys.onRightPressed: activateIndex(currentIndex >= options.length - 1 ? 0 : currentIndex + 1)
    Keys.onSpacePressed: activateIndex(currentIndex < 0 ? 0 : currentIndex)
    Keys.onReturnPressed: activateIndex(currentIndex < 0 ? 0 : currentIndex)

    Row {
        anchors.fill: parent
        anchors.margins: 2
        spacing: 2

        Repeater {
            model: root.options

            delegate: Rectangle {
                required property var modelData
                required property int index

                width: (root.width - 4 - (root.options.length - 1) * 2) / Math.max(1, root.options.length)
                height: root.height - 4
                radius: Math.max(2, Theme.radiusSmall - 1)
                color: root.value === modelData.value ? Theme.accentSoft : (segmentMouse.containsMouse ? Theme.bgHover : "transparent")
                border.width: root.value === modelData.value ? 1 : 0
                border.color: Theme.accentPressed

                Text {
                    anchors.fill: parent
                    text: parent.modelData.label
                    color: root.value === parent.modelData.value ? Theme.accent : Theme.textSecondary
                    font.family: Theme.bodyFont
                    font.pixelSize: 10
                    font.weight: root.value === parent.modelData.value ? Font.DemiBold : Font.Normal
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }

                MouseArea {
                    id: segmentMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        root.forceActiveFocus(Qt.MouseFocusReason)
                        root.activated(parent.modelData.value)
                    }
                }

                Accessible.name: modelData.label
                Accessible.role: Accessible.RadioButton
                Accessible.checked: root.value === modelData.value
            }
        }
    }

    Accessible.name: accessibleName
    Accessible.role: Accessible.PageTabList
}
