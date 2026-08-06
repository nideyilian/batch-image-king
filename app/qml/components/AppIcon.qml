import QtQuick
import QtQuick.Controls

Item {
    id: root

    property string iconName: ""
    property string glyph: ""
    property color iconColor: Theme.textSecondary
    property int iconSize: 16
    property bool mirrored: false

    implicitWidth: iconSize
    implicitHeight: iconSize

    IconImage {
        anchors.centerIn: parent
        width: root.iconSize
        height: root.iconSize
        source: root.iconName.length > 0 ? AppIcons.source(root.iconName) : ""
        sourceSize: Qt.size(root.iconSize * 2, root.iconSize * 2)
        color: root.iconColor
        visible: root.iconName.length > 0
        transform: Scale {
            origin.x: root.iconSize / 2
            origin.y: root.iconSize / 2
            xScale: root.mirrored ? -1 : 1
        }
    }

    Text {
        anchors.fill: parent
        visible: root.iconName.length === 0
        text: root.glyph
        color: root.iconColor
        font.family: Theme.iconFont
        font.pixelSize: root.iconSize
        horizontalAlignment: Text.AlignHCenter
        verticalAlignment: Text.AlignVCenter
        renderType: Text.NativeRendering
    }
}
