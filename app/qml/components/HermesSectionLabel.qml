import QtQuick
import QtQuick.Layouts

Item {
    id: root

    property string index: ""
    property string eyebrow: ""
    property string title: ""
    property string detail: ""

    implicitHeight: Math.max(42, content.implicitHeight)
    implicitWidth: content.implicitWidth

    ColumnLayout {
        id: content
        anchors.left: parent.left
        anchors.right: parent.right
        spacing: 3

        RowLayout {
            Layout.fillWidth: true
            spacing: 7

            Text {
                visible: root.index.length > 0
                text: root.index
                color: Theme.textMuted
                font.family: Theme.dataFont
                font.pixelSize: 10
                Layout.alignment: Qt.AlignVCenter
            }

            Text {
                visible: root.eyebrow.length > 0
                text: root.eyebrow
                color: Theme.textMuted
                font.family: Theme.dataFont
                font.pixelSize: 10
                font.weight: Font.DemiBold
                Layout.fillWidth: true
            }
        }

        Text {
            visible: root.title.length > 0
            text: root.title
            color: Theme.textPrimary
            font.family: Theme.displayFont
            font.pixelSize: 15
            font.weight: Font.DemiBold
            Layout.fillWidth: true
            elide: Text.ElideRight
        }

        Text {
            visible: root.detail.length > 0
            text: root.detail
            color: Theme.textMuted
            font.family: Theme.bodyFont
            font.pixelSize: 11
            wrapMode: Text.Wrap
            Layout.fillWidth: true
        }
    }
}
