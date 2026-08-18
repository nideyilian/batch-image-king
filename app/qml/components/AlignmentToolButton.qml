import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: alignmentButton

    property string alignmentMode: ""
    property string distributionMode: ""
    property string tooltip: ""
    readonly property string iconMode: alignmentMode.length > 0 ? alignmentMode : distributionMode
    readonly property string iconName: {
        if (iconMode === "left") return AppIcons.alignLeft
        if (iconMode === "hcenter") return AppIcons.alignCenterHorizontal
        if (iconMode === "right") return AppIcons.alignRight
        if (iconMode === "top") return AppIcons.alignTop
        if (iconMode === "vcenter") return AppIcons.alignCenterVertical
        if (iconMode === "bottom") return AppIcons.alignBottom
        if (iconMode === "horizontal") return AppIcons.distributeHorizontal
        if (iconMode === "vertical") return AppIcons.distributeVertical
        if (iconMode === "same_size") return AppIcons.fitView
        return AppIcons.circleDot
    }
    signal clicked()

    implicitWidth: 28
    implicitHeight: 30
    radius: Theme.radiusSmall
    color: {
        if (!enabled) return "transparent"
        if (alignmentMouse.pressed) return Theme.bgControl
        return alignmentMouse.containsMouse ? Theme.bgHover : "transparent"
    }
    border.width: activeFocus ? 1 : 0
    border.color: Theme.focusRing
    activeFocusOnTab: enabled

    AppIcon {
        anchors.centerIn: parent
        iconName: alignmentButton.iconName
        iconSize: 16
        iconColor: !alignmentButton.enabled
                   ? Theme.textDisabled
                   : (alignmentMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary)
    }

    MouseArea {
        id: alignmentMouse
        anchors.fill: parent
        enabled: alignmentButton.enabled
        hoverEnabled: true
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPressed: alignmentButton.forceActiveFocus(Qt.MouseFocusReason)
        onClicked: alignmentButton.clicked()
    }

    Keys.onSpacePressed: clicked()

    ToolTip.visible: alignmentMouse.containsMouse && tooltip.length > 0
    ToolTip.text: tooltip
    ToolTip.delay: 420
    Accessible.name: tooltip
    Accessible.role: Accessible.Button
}
