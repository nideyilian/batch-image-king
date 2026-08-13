import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root

    property var options: []
    property var value: options.length > 0 ? options[0].value : undefined
    property int optionHeight: 20
    property bool fillWidth: false // compact(inline pill) by default, true = full-width big bar
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

    // In compact inline mode, use content-derived width and align right.
    // When fillWidth=true, use the legacy full-width bar layout.
    readonly property int __segCount: Math.max(1, options.length)
    readonly property int __inlineWidth: {
        // Each segment uses minimum 28px for 1-2 chars label, up to 48px.
        var count = __segCount
        var avg = 32
        if (count <= 2) avg = 40
        else if (count === 3) avg = 36
        return avg * count + 4 + (count - 1) * 2
    }
    Layout.fillWidth: true
    implicitWidth: fillWidth ? 180 : __inlineWidth
    implicitHeight: Theme.compactControlHeight
    radius: Theme.radiusSmall
    color: fillWidth ? Theme.bgControl : Theme.bgControl
    border.width: 1
    border.color: Theme.border
    activeFocusOnTab: enabled
    opacity: enabled ? 1 : 0.38

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

                width: fillWidth
                    ? (root.width - 4 - (root.options.length - 1) * 2) / Math.max(1, root.options.length)
                    : Math.max(24, (root.width - 4 - (root.options.length - 1) * 2) / Math.max(1, root.options.length))
                height: root.height - 4
                radius: Theme.radiusSmall
                enabled: root.enabled
                color: root.value === modelData.value ? Theme.accent : (segmentMouse.containsMouse ? Theme.bgHover : "transparent")
                border.width: root.value === modelData.value ? 1 : 0
                border.color: Theme.accent

                Text {
                    anchors.fill: parent
                    text: parent.modelData.label
                    color: root.value === parent.modelData.value ? Theme.accentForeground : Theme.textSecondary
                    font.family: Theme.bodyFont
                    font.pixelSize: fillWidth ? 10 : 9
                    font.weight: root.value === parent.modelData.value ? Font.DemiBold : Font.Normal
                    horizontalAlignment: Text.AlignHCenter
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }

                MouseArea {
                    id: segmentMouse
                    anchors.fill: parent
                    enabled: parent.enabled
                    hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
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
