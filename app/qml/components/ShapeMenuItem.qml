import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

MenuItem {
    id: shapeMenuItem
    implicitWidth: 158
    implicitHeight: 34
    leftPadding: 10
    rightPadding: 10
    contentItem: Text {
        text: shapeMenuItem.text
        color: !shapeMenuItem.enabled
               ? Theme.textDisabled
               : (shapeMenuItem.highlighted ? Theme.textPrimary : Theme.textSecondary)
        font.family: Theme.bodyFont
        font.pixelSize: 11
        verticalAlignment: Text.AlignVCenter
    }
    background: Rectangle {
        color: shapeMenuItem.highlighted ? Theme.bgHover : "transparent"
        radius: Theme.radiusSmall
    }
}
