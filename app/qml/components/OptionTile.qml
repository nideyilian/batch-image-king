import QtQuick
import QtQuick.Layouts

Rectangle {
    id: root

    property string title: ""
    property string detail: ""
    property bool selected: false
    property bool compact: false
    property bool exclusive: false
    signal activated()

    Layout.fillWidth: true
    Layout.minimumWidth: 0
    Layout.preferredHeight: implicitHeight
    implicitWidth: compact ? 92 : 136
    implicitHeight: compact ? 62 : 84
    radius: Theme.radiusSmall
    color: selected ? Theme.accentSoft : (tileMouse.containsMouse ? Theme.bgHover : Theme.bgRaised)
    border.width: 1
    border.color: activeFocus
                  ? Theme.focusRing
                  : (selected ? Theme.accentPressed : Theme.border)
    opacity: enabled ? 1 : 0.38
    activeFocusOnTab: enabled

    Behavior on color {
        ColorAnimation { duration: Theme.motionFast }
    }
    Behavior on border.color {
        ColorAnimation { duration: Theme.motionFast }
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: root.compact ? 8 : 10
        spacing: root.compact ? 3 : 5

        RowLayout {
            Layout.fillWidth: true
            spacing: 5

            Text {
                Layout.fillWidth: true
                text: root.title
                color: root.selected ? Theme.accentHover : Theme.textPrimary
                font.family: Theme.bodyFont
                font.pixelSize: root.compact ? 11 : 12
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            AppIcon {
                iconName: AppIcons.check
                iconSize: root.compact ? 12 : 14
                iconColor: Theme.accent
                opacity: root.selected ? 1 : 0
            }
        }

        Text {
            Layout.fillWidth: true
            Layout.fillHeight: true
            visible: root.detail.length > 0
            text: root.detail
            color: root.selected ? Theme.textSecondary : Theme.textMuted
            font.family: Theme.bodyFont
            font.pixelSize: 10
            wrapMode: Text.Wrap
            maximumLineCount: 2
            elide: Text.ElideRight
            verticalAlignment: Text.AlignTop
        }
    }

    MouseArea {
        id: tileMouse
        anchors.fill: parent
        enabled: root.enabled
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPressed: root.forceActiveFocus(Qt.MouseFocusReason)
        onClicked: root.activated()
    }

    Keys.onSpacePressed: activated()
    Keys.onReturnPressed: activated()

    Accessible.name: title
    Accessible.description: detail
    Accessible.role: exclusive ? Accessible.RadioButton : Accessible.CheckBox
    Accessible.checked: selected
}
