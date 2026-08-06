import QtQuick

Rectangle {
    id: root

    property alias text: input.text
    property string value: ""
    property bool bindValue: false
    property string suffix: ""
    property bool editable: true
    property bool invalid: false
    property string accessibleName: ""
    signal valueCommitted(string value)

    function beginEdit() {
        if (!root.editable) return
        if (root.bindValue)
            input.text = String(root.value)
        input.forceActiveFocus()
        input.selectAll()
    }

    implicitWidth: 94
    implicitHeight: Theme.controlHeight
    radius: Theme.radiusSmall
    color: Theme.bgControl
    border.width: 1
    border.color: root.invalid ? Theme.danger : (input.activeFocus ? Theme.focusRing : Theme.borderStrong)
    opacity: enabled ? 1 : 0.56

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
        enabled: root.enabled
        onActiveFocusChanged: {
            if (activeFocus) {
                if (root.bindValue)
                    text = String(root.value)
                selectAll()
            }
        }
        onEditingFinished: root.valueCommitted(text)
        Keys.onEscapePressed: {
            if (root.bindValue)
                text = String(root.value)
            focus = false
        }
    }

    Binding {
        target: input
        property: "text"
        value: root.value
        when: root.bindValue && !input.activeFocus
        restoreMode: Binding.RestoreNone
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

    Accessible.name: accessibleName.length > 0
                     ? accessibleName
                     : (suffix.length > 0 ? suffix + " 数值" : "数值")
    Accessible.role: Accessible.EditableText
}
