import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Text {
    property bool hovered: false
    color: hovered ? Theme.textPrimary : Theme.textSecondary
    font.family: Theme.bodyFont
    font.pixelSize: 12
    verticalAlignment: Text.AlignVCenter
}
