import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: compactButton
    property string label: ""
    property bool active: false
    signal clicked()

    implicitWidth: 94
    implicitHeight: Theme.controlHeight
    radius: Theme.radiusSmall
    color: {
        if (!enabled) return Theme.bgControl
        if (compactMouse.pressed || compactMouse.containsMouse) return Theme.bgHover
        return active ? Theme.accentSoft : Theme.bgControl
    }
    border.width: 1
    border.color: !enabled
                  ? Theme.border
                  : (active ? Theme.accentPressed : Theme.borderStrong)

    Text {
        anchors.centerIn: parent
        text: compactButton.label
        color: !compactButton.enabled
               ? Theme.textDisabled
               : (compactButton.active ? Theme.accent : Theme.textSecondary)
        font.family: Theme.bodyFont
        font.pixelSize: 11
        font.weight: Font.DemiBold
    }
    MouseArea {
        id: compactMouse
        anchors.fill: parent
        enabled: compactButton.enabled
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: compactButton.clicked()
    }
    Accessible.name: label
    Accessible.role: Accessible.Button
}
