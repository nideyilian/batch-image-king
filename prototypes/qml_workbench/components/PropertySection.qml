import QtQuick

Item {
    id: root

    property string title: ""
    property string summary: ""
    property bool expanded: true
    default property alias sectionData: contentColumn.data

    implicitHeight: header.height + (expanded ? contentColumn.implicitHeight + 18 : 0)
    height: implicitHeight

    Rectangle {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        height: 38
        color: mouseArea.containsMouse ? Theme.bgRaised : "transparent"

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            text: root.title
            color: Theme.textPrimary
            font.family: Theme.bodyFont
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }

        Text {
            anchors.right: chevron.left
            anchors.rightMargin: 9
            anchors.verticalCenter: parent.verticalCenter
            text: root.summary
            color: Theme.textMuted
            font.family: Theme.bodyFont
            font.pixelSize: 10
        }

        AppIcon {
            id: chevron
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            glyph: root.expanded ? "\uE70D" : "\uE76C"
            iconSize: 11
            iconColor: Theme.textMuted
        }

        MouseArea {
            id: mouseArea
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: root.expanded = !root.expanded
        }
    }

    Column {
        id: contentColumn
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 12
        anchors.rightMargin: 12
        anchors.topMargin: 8
        spacing: 9
        visible: root.expanded
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.border
    }
}
