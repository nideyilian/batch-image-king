import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: formatButton
    property string symbol: ""
    property string tooltip: ""
    property bool active: false
    property bool italicSymbol: false
    signal clicked()

    implicitWidth: Theme.controlHeight
    implicitHeight: Theme.controlHeight
    radius: Theme.radiusSmall
    color: {
        if (!enabled) return "transparent"
        if (formatMouse.pressed || formatMouse.containsMouse) return Theme.bgHover
        return active ? Theme.accentSoft : "transparent"
    }
    border.width: active ? 1 : 0
    border.color: Theme.accentPressed

    Text {
        anchors.centerIn: parent
        text: formatButton.symbol
        color: !formatButton.enabled
               ? Theme.textDisabled
               : (formatButton.active ? Theme.accent : Theme.textSecondary)
        font.family: Theme.bodyFont
        font.pixelSize: 14
        font.weight: formatButton.symbol === "B" ? Font.Bold : Font.Normal
        font.italic: formatButton.italicSymbol
    }
    MouseArea {
        id: formatMouse
        anchors.fill: parent
        enabled: formatButton.enabled
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: formatButton.clicked()
    }
    ToolTip.visible: formatMouse.containsMouse && formatButton.tooltip.length > 0
    ToolTip.text: formatButton.tooltip
    ToolTip.delay: 420
    Accessible.name: tooltip
    Accessible.role: Accessible.Button
}
