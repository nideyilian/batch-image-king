import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: compactSection

    property string title: ""
    property string detail: ""
    property string iconName: AppIcons.settings
    property bool expanded: true
    default property alias sectionData: compactSectionContent.data

    Layout.fillWidth: true
    implicitHeight: compactSectionHeader.height
                    + (expanded ? compactSectionContent.implicitHeight + 7 : 0) + 1

    Rectangle {
        id: compactSectionHeader
        anchors.left: parent.left
        anchors.right: parent.right
        height: 38
        radius: Theme.radiusSmall
        color: compactSectionMouse.containsMouse || activeFocus ? Theme.bgRaised : "transparent"
        activeFocusOnTab: true

        RowLayout {
            anchors.fill: parent
            spacing: 8

            Rectangle {
                Layout.preferredWidth: 24
                Layout.preferredHeight: 24
                radius: Theme.radiusSmall
                color: Theme.accentSoft
                AppIcon {
                    anchors.centerIn: parent
                    iconName: compactSection.iconName
                    iconSize: 13
                    iconColor: Theme.accent
                }
            }
            Column {
                Layout.fillWidth: true
                spacing: 0
                BodyLabel {
                    text: compactSection.title
                    color: Theme.textPrimary
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
                TinyLabel {
                    width: parent.width
                    text: compactSection.detail
                    font.pixelSize: 9
                    elide: Text.ElideRight
                }
            }
            AppIcon {
                iconName: AppIcons.chevronDown
                iconSize: 11
                iconColor: Theme.textMuted
                rotation: compactSection.expanded ? 0 : -90
            }
        }

        function toggleSection() {
            compactSection.expanded = !compactSection.expanded
        }

        MouseArea {
            id: compactSectionMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onPressed: compactSectionHeader.forceActiveFocus(Qt.MouseFocusReason)
            onClicked: compactSectionHeader.toggleSection()
        }
        Keys.onSpacePressed: toggleSection()
        Keys.onReturnPressed: toggleSection()
        Accessible.name: compactSection.title
        Accessible.description: compactSection.detail
        Accessible.role: Accessible.Button
    }

    Column {
        id: compactSectionContent
        anchors.top: compactSectionHeader.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.topMargin: 6
        spacing: 6
        visible: compactSection.expanded
    }

    Divider {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
    }
}
