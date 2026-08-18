import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: trailingToggle
    property bool checked: false
    property string accessibleName: "开关"
    signal toggled(bool checked)

    Layout.fillWidth: true
    implicitHeight: Theme.controlHeight

    ToggleSwitch {
        anchors.right: parent.right
        anchors.verticalCenter: parent.verticalCenter
        accessibleName: trailingToggle.accessibleName
        checked: trailingToggle.checked
        enabled: trailingToggle.enabled
        onToggled: checkedValue => trailingToggle.toggled(checkedValue)
    }
}
