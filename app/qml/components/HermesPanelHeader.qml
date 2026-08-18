import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root

    property string eyebrow: ""
    property string title: ""
    property string detail: ""
    property string iconName: ""
    property bool divider: true
    default property alias actions: actionRow.data

    implicitHeight: 54
    color: Theme.bgPanel

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 14
        anchors.rightMargin: 10
        spacing: 10

        AppIcon {
            visible: root.iconName.length > 0
            iconName: root.iconName
            iconSize: 17
            iconColor: Theme.textSecondary
        }

        ColumnLayout {
            Layout.fillWidth: true
            spacing: 2

            Text {
                visible: root.eyebrow.length > 0
                text: root.eyebrow
                color: Theme.textMuted
                font.family: Theme.dataFont
                font.pixelSize: 9
                font.weight: Font.DemiBold
            }

            Text {
                text: root.title
                color: Theme.textPrimary
                font.family: Theme.displayFont
                font.pixelSize: 13
                font.weight: Font.DemiBold
                elide: Text.ElideRight
                Layout.fillWidth: true
            }

            Text {
                visible: root.detail.length > 0
                text: root.detail
                color: Theme.textMuted
                font.family: Theme.bodyFont
                font.pixelSize: 10
                elide: Text.ElideRight
                Layout.fillWidth: true
            }
        }

        RowLayout {
            id: actionRow
            spacing: 3
        }
    }

    Rectangle {
        visible: root.divider
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.border
    }
}
