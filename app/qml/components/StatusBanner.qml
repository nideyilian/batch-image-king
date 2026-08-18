import QtQuick

Rectangle {
    id: root

    property string tone: "neutral"
    default property alias contentData: contentSlot.data

    implicitHeight: 48
    radius: Theme.radiusSmall
    color: tone === "error"
           ? Theme.errorSurface
           : (tone === "success" ? Theme.successSurface : Theme.bgRaised)
    border.width: 1
    border.color: tone === "error"
                  ? Theme.errorBorder
                  : (tone === "success" ? Theme.successBorder : Theme.border)

    Item {
        id: contentSlot
        anchors.fill: parent
    }
}
