import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

TextField {
    id: root

    property bool invalid: false
    property string accessibleName: ""
    property string controlSize: "sm"
    property bool fullWidth: true
    property bool mono: false

    Layout.fillWidth: fullWidth
    implicitHeight: controlSize === "lg"
                    ? Theme.inputHeightLg
                    : (controlSize === "md" ? Theme.inputHeightMd : Theme.inputHeightSm)
    leftPadding: Theme.inputPaddingX
    rightPadding: Theme.inputPaddingX
    color: enabled ? Theme.textPrimary : Theme.textDisabled
    placeholderTextColor: Theme.textMuted
    selectionColor: Theme.selectionBackground
    selectedTextColor: Theme.selectionForeground
    font.family: mono ? Theme.dataFont : Theme.bodyFont
    font.pixelSize: controlSize === "lg" ? 13 : 12
    verticalAlignment: TextInput.AlignVCenter
    selectByMouse: true
    hoverEnabled: true

    background: Rectangle {
        radius: Theme.radiusSmall
        color: Theme.bgControl
        border.width: 1
        border.color: root.invalid
                      ? Theme.danger
                      : (root.activeFocus
                         ? Theme.focusRing
                         : (root.hovered ? Theme.borderStrong : Theme.border))
        Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }
    }

    Accessible.role: Accessible.EditableText
    Accessible.name: accessibleName.length > 0
                     ? accessibleName
                     : (placeholderText.length > 0 ? placeholderText : "文本输入")
}
