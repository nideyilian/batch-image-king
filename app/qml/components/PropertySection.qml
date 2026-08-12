import QtQuick

Item {
    id: root

    property string title: ""
    property string summary: ""
    property bool expanded: true
    default property alias sectionData: contentColumn.data

    implicitHeight: header.height + (expanded ? contentColumn.implicitHeight + 10 : 0)
    height: implicitHeight

    Rectangle {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        height: Theme.sectionHeaderHeight
        color: mouseArea.containsMouse ? Theme.bgRaised : "transparent"

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            text: root.title
            color: Theme.textPrimary
            font.family: Theme.bodyFont
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }

        Text {
            anchors.right: chevron.left
            anchors.rightMargin: 7
            anchors.verticalCenter: parent.verticalCenter
            text: root.summary
            color: Theme.textMuted
            font.family: Theme.bodyFont
            font.pixelSize: 10
        }

        AppIcon {
            id: chevron
            anchors.right: parent.right
            anchors.rightMargin: 10
            anchors.verticalCenter: parent.verticalCenter
            iconName: AppIcons.chevronDown
            iconSize: 12
            iconColor: Theme.textMuted
            rotation: root.expanded ? 0 : -90

            Behavior on rotation {
                NumberAnimation { duration: Theme.motionNormal; easing.type: Easing.OutCubic }
            }
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
        anchors.leftMargin: 10
        anchors.rightMargin: 10
        anchors.topMargin: 5
        spacing: 6
        visible: root.expanded
    }

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.border
    }

    Accessible.name: title
    Accessible.role: Accessible.Grouping
}
