import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: section

    property string title: ""
    property string detail: ""
    property string summary: ""
    property string iconName: AppIcons.settings
    property bool expanded: true
    default property alias sectionData: sectionContent.data
    signal toggled(bool expanded)

    width: parent ? parent.width : implicitWidth
    implicitHeight: sectionHeader.height + (expanded ? sectionContent.implicitHeight + 18 : 0) + 1
    height: implicitHeight

    Rectangle {
        id: sectionHeader
        anchors.left: parent.left
        anchors.right: parent.right
        height: 54
        color: sectionMouse.containsMouse || activeFocus ? Theme.bgRaised : "transparent"
        radius: Theme.radiusSmall
        activeFocusOnTab: true

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            spacing: 10

            Rectangle {
                Layout.preferredWidth: 28
                Layout.preferredHeight: 28
                radius: Theme.radiusSmall
                color: Theme.accentSoft
                AppIcon {
                    anchors.centerIn: parent
                    iconName: section.iconName
                    iconSize: 14
                    iconColor: Theme.accent
                }
            }
            Column {
                Layout.fillWidth: true
                spacing: 2
                BodyLabel {
                    text: section.title
                    color: Theme.textPrimary
                    font.weight: Font.DemiBold
                }
                TinyLabel {
                    width: parent.width
                    text: section.detail
                    color: Theme.textMuted
                    elide: Text.ElideRight
                }
            }
            TinyLabel {
                visible: section.summary.length > 0
                text: section.summary
                color: Theme.textSecondary
            }
            AppIcon {
                iconName: AppIcons.chevronDown
                iconSize: 12
                iconColor: Theme.textMuted
                rotation: section.expanded ? 0 : -90
                Behavior on rotation {
                    NumberAnimation { duration: Theme.motionNormal; easing.type: Easing.OutCubic }
                }
            }
        }

        function toggleSection() {
            section.expanded = !section.expanded
            section.toggled(section.expanded)
        }

        MouseArea {
            id: sectionMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPressed: sectionHeader.forceActiveFocus(Qt.MouseFocusReason)
            onClicked: sectionHeader.toggleSection()
        }
        Keys.onSpacePressed: toggleSection()
        Keys.onReturnPressed: toggleSection()
        Accessible.name: section.title
        Accessible.description: section.detail
        Accessible.role: Accessible.Button
    }

    Column {
        id: sectionContent
        anchors.top: sectionHeader.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        anchors.topMargin: 8
        spacing: 10
        visible: section.expanded
    }

    Divider {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
    }

    Accessible.name: title
    Accessible.role: Accessible.Grouping
}
