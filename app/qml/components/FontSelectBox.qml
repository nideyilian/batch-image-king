import QtQuick
import QtQuick.Controls.Basic

Rectangle {
    id: root

    property var options: []
    property string value: ""
    property string query: ""
    readonly property var filteredOptions: {
        var needle = query.trim().toLocaleLowerCase()
        var source = options || []
        if (!needle.length) return source
        return source.filter(function(option) {
            return String(option.label || option.value || "").toLocaleLowerCase().indexOf(needle) >= 0
        })
    }
    signal activated(string value)

    function beginEdit() {
        if (!root.enabled) return
        fontInput.text = String(root.value)
        root.query = ""
        fontInput.forceActiveFocus()
        fontInput.selectAll()
        fontPopup.open()
    }

    function choose(option) {
        if (!option) return
        root.activated(String(option.value || option.label || ""))
        fontPopup.close()
        fontInput.focus = false
    }

    implicitWidth: 180
    implicitHeight: Theme.controlHeight
    radius: Theme.radiusSmall
    color: Theme.bgControl
    border.width: 1
    border.color: fontInput.activeFocus || fontPopup.visible ? Theme.focusRing : Theme.borderStrong
    opacity: enabled ? 1 : 0.56
    activeFocusOnTab: enabled

    Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }

    TextInput {
        id: fontInput
        anchors.left: parent.left
        anchors.right: indicator.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.leftMargin: 9
        anchors.rightMargin: 6
        color: Theme.textPrimary
        selectionColor: Theme.accentPressed
        selectedTextColor: Theme.textPrimary
        font.family: root.value || Theme.bodyFont
        font.pixelSize: 11
        verticalAlignment: TextInput.AlignVCenter
        selectByMouse: true
        clip: true
        enabled: root.enabled

        onActiveFocusChanged: {
            if (activeFocus) {
                text = String(root.value)
                root.query = ""
                selectAll()
                fontPopup.open()
            }
        }
        onTextEdited: {
            root.query = text
            if (!fontPopup.visible) fontPopup.open()
        }
        onAccepted: {
            var typed = text.trim()
            if (root.filteredOptions.length > 0) root.choose(root.filteredOptions[0])
            else if (typed.length > 0) {
                root.activated(typed)
                fontPopup.close()
                focus = false
            }
        }
        Keys.onEscapePressed: {
            fontPopup.close()
            text = String(root.value)
            focus = false
        }
    }

    Binding {
        target: fontInput
        property: "text"
        value: root.value
        when: !fontInput.activeFocus
        restoreMode: Binding.RestoreNone
    }

    AppIcon {
        id: indicator
        anchors.right: parent.right
        anchors.rightMargin: 9
        anchors.verticalCenter: parent.verticalCenter
        width: 12
        height: 12
        iconName: AppIcons.selectIndicator
        iconSize: 12
        iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
    }

    MouseArea {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 30
        enabled: root.enabled
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
            if (fontPopup.visible) {
                fontPopup.close()
                fontInput.focus = false
            } else {
                root.query = ""
                fontInput.forceActiveFocus()
                fontInput.selectAll()
                fontPopup.open()
            }
        }
    }

    Popup {
        id: fontPopup
        y: root.height + 4
        width: root.width
        height: Math.min(248, Math.max(38, fontList.contentHeight + 8))
        padding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        contentItem: ListView {
            id: fontList
            clip: true
            model: root.filteredOptions
            currentIndex: -1
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator { }

            delegate: ItemDelegate {
                required property var modelData
                required property int index
                width: fontList.width
                height: 32
                highlighted: hovered || fontList.currentIndex === index
                onClicked: root.choose(modelData)

                contentItem: Text {
                    text: String(parent.modelData.label || parent.modelData.value || "")
                    color: String(parent.modelData.value) === root.value ? Theme.accent : Theme.textSecondary
                    font.family: String(parent.modelData.value || Theme.bodyFont)
                    font.pixelSize: 11
                    verticalAlignment: Text.AlignVCenter
                    elide: Text.ElideRight
                }
                background: Rectangle {
                    radius: Theme.radiusSmall
                    color: String(parent.modelData.value) === root.value ? Theme.accentSoft : (parent.highlighted ? Theme.bgHover : "transparent")
                }
            }
        }

        background: Rectangle {
            radius: Theme.radius
            color: Theme.bgRaised
            border.width: 1
            border.color: Theme.borderStrong
        }
    }

    Accessible.name: "字体"
    Accessible.description: "输入字体名称以筛选系统字体"
    Accessible.role: Accessible.ComboBox
}
