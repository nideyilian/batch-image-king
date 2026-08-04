import QtQuick

Text {
    property string glyph: ""
    property color iconColor: Theme.textSecondary
    property int iconSize: 16

    text: glyph
    color: iconColor
    font.family: Theme.iconFont
    font.pixelSize: iconSize
    horizontalAlignment: Text.AlignHCenter
    verticalAlignment: Text.AlignVCenter
    renderType: Text.NativeRendering
}
