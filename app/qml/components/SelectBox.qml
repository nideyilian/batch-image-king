import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

ComboBox {
    id: root

    Layout.fillWidth: true
    Layout.minimumWidth: 0
    implicitWidth: 160
    implicitHeight: Theme.controlHeight
    textRole: "label"
    valueRole: "value"
    leftPadding: 10
    rightPadding: 30
    focusPolicy: Qt.StrongFocus

    contentItem: Text {
        leftPadding: 0
        rightPadding: 0
        text: root.displayText
        color: root.enabled ? Theme.textPrimary : Theme.textDisabled
        font.family: Theme.bodyFont
        font.pixelSize: 11
        verticalAlignment: Text.AlignVCenter
        elide: Text.ElideRight
    }

    indicator: AppIcon {
        x: root.width - width - 9
        y: (root.height - height) / 2
        width: 12
        height: 12
        iconName: AppIcons.selectIndicator
        iconSize: 12
        iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
    }

    background: Rectangle {
        radius: Theme.radiusSmall
        color: root.down || root.popup.visible ? Theme.bgHover : Theme.bgControl
        border.width: 1
        border.color: root.activeFocus || root.popup.visible ? Theme.focusRing : Theme.borderStrong

        Behavior on color { ColorAnimation { duration: Theme.motionFast } }
        Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }
    }

    delegate: ItemDelegate {
        required property var modelData
        required property int index

        width: root.width - 8
        height: 30
        highlighted: root.highlightedIndex === index

        contentItem: Text {
            text: modelData.label
            color: root.currentIndex === index ? Theme.textPrimary : Theme.textSecondary
            font.family: Theme.bodyFont
            font.pixelSize: 11
            font.weight: root.currentIndex === index ? Font.DemiBold : Font.Normal
            verticalAlignment: Text.AlignVCenter
            elide: Text.ElideRight
        }

        background: Rectangle {
            radius: Theme.radiusSmall
            color: root.currentIndex === parent.index ? Theme.bgHover : (parent.highlighted ? Theme.bgHover : "transparent")
        }
    }

    popup: Popup {
        y: root.height + 4
        width: root.width
        implicitHeight: Math.min(contentItem.implicitHeight + 8, 220)
        padding: 4

        contentItem: ListView {
            clip: true
            implicitHeight: contentHeight
            model: root.popup.visible ? root.delegateModel : null
            currentIndex: root.highlightedIndex
            ScrollIndicator.vertical: ScrollIndicator { }
        }

        background: Rectangle {
            radius: Theme.radius
            color: Theme.bgRaised
            border.width: 1
            border.color: Theme.borderStrong
        }
    }

    Accessible.name: displayText
    Accessible.role: Accessible.ComboBox
}
