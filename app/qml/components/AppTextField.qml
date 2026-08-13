import QtQuick
import QtQuick.Controls.Basic

TextField {
    id: root

    property bool invalid: false
    property string accessibleName: ""

    implicitHeight: Theme.controlHeight
    leftPadding: 9
    rightPadding: 9
    color: enabled ? Theme.textPrimary : Theme.textDisabled
    placeholderTextColor: Theme.textMuted
    selectionColor: Theme.accentPressed
    selectedTextColor: Theme.textPrimary
    font.family: Theme.bodyFont
    font.pixelSize: 11
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true

    background: Rectangle {
        radius: Theme.radiusSmall
        color: Theme.bgControl
        border.width: 1
        border.color: root.invalid ? Theme.errorBorder : (root.activeFocus ? Theme.focusRing : Theme.borderStrong)
        Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }
    }

    Accessible.role: Accessible.EditableText
    Accessible.name: accessibleName.length > 0
                     ? accessibleName
                     : (placeholderText.length > 0 ? placeholderText : "文本输入")
}
