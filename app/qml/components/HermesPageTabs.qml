pragma ComponentBehavior: Bound

import QtQuick
import QtQuick.Layouts

// QML adaptation of packages/shared-ui/src/components/page-tabs in
// Hermes-CN-Desktop. License notices are preserved in THIRD_PARTY_NOTICES.md.
Rectangle {
    id: root

    property var items: []
    property int currentIndex: 0
    property bool fillWidth: false
    property string accessibleName: "页面标签"
    signal activated(int index)

    function activate(index) {
        if (!enabled || items.length === 0)
            return
        var boundedIndex = (index + items.length) % items.length
        activated(boundedIndex)
    }

    Layout.fillWidth: true
    implicitHeight: Theme.tabHeight
    height: Theme.tabHeight
    color: Theme.bgPanel
    activeFocusOnTab: enabled

    Keys.onLeftPressed: activate(currentIndex - 1)
    Keys.onRightPressed: activate(currentIndex + 1)
    Keys.onUpPressed: activate(currentIndex - 1)
    Keys.onDownPressed: activate(currentIndex + 1)
    Keys.onPressed: event => {
        if (event.key === Qt.Key_Home) {
            activate(0)
            event.accepted = true
        } else if (event.key === Qt.Key_End) {
            activate(items.length - 1)
            event.accepted = true
        }
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.border
    }

    Row {
        id: tabRow
        anchors.fill: parent

        Repeater {
            model: root.items

            delegate: Rectangle {
                id: tab
                required property int index
                required property var modelData

                readonly property string tabLabel: typeof modelData === "string"
                                                   ? modelData
                                                   : String(modelData.label)
                readonly property bool active: root.currentIndex === index

                width: root.fillWidth
                       ? root.width / Math.max(1, root.items.length)
                       : tabText.implicitWidth + Theme.space2
                height: Theme.tabHeight
                color: tabMouse.containsMouse || activeFocus
                       ? Theme.bgRaised
                       : "transparent"
                activeFocusOnTab: root.enabled

                Text {
                    id: tabText
                    anchors.centerIn: parent
                    text: tab.tabLabel
                    color: tab.active ? Theme.textPrimary : Theme.textMuted
                    font.family: Theme.bodyFont
                    font.pixelSize: 13
                    font.weight: tab.active ? Font.DemiBold : Font.Normal
                }

                Rectangle {
                    anchors.left: parent.left
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    height: 1
                    color: tab.active ? Theme.accent : "transparent"
                }

                MouseArea {
                    id: tabMouse
                    anchors.fill: parent
                    enabled: root.enabled
                    hoverEnabled: true
                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                    onClicked: {
                        tab.forceActiveFocus(Qt.MouseFocusReason)
                        root.activate(tab.index)
                    }
                }

                Keys.onLeftPressed: root.activate(index - 1)
                Keys.onRightPressed: root.activate(index + 1)
                Accessible.name: tabLabel
                Accessible.role: Accessible.PageTab
                Accessible.selected: active
            }
        }
    }

    Accessible.name: accessibleName
    Accessible.role: Accessible.PageTabList
}
