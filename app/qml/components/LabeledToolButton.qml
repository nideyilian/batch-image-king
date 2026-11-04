import QtQuick
import QtQuick.Controls

// 带文案的工具栏按钮（图标 + 短标签）。
//
// 为什么需要它：工具栏原本全是纯图标按钮，作用只能靠 tooltip 才知道。
// 实测反馈是「点了不知道这个按钮干什么」，所以高频/易混淆的动作补上文案。
//
// 两个刻意的设计：
// 1. `showLabel` 可按窗口宽度收起。1180px 是窗口最小宽度，全部带文案排不下，
//    窄窗口退回纯图标（tooltip 仍在），不靠裁切硬塞。
// 2. 禁用状态下仍然可悬停：按钮置灰时更需要知道它能干什么。IconButton 的
//    MouseArea 跟着 enabled 一起关，禁用时看不到 tooltip，这里不沿用。
Rectangle {
    id: root

    property string iconName: ""
    property string text: ""
    property string tooltip: ""
    property bool showLabel: true
    property bool active: false
    property int buttonSize: Theme.buttonHeightMd
    signal clicked()

    readonly property bool hasLabel: root.showLabel && root.text.length > 0
    readonly property bool hovered: mouseArea.containsMouse

    implicitWidth: root.hasLabel ? labelRow.implicitWidth + 14 : root.buttonSize
    implicitHeight: root.buttonSize
    radius: Theme.radiusSmall
    color: {
        if (!root.enabled) return "transparent"
        if (root.active) return Theme.accentSoft
        return mouseArea.containsMouse ? Theme.bgHover : "transparent"
    }
    border.width: activeFocus || (root.active && !root.enabled) ? 1 : 0
    border.color: activeFocus ? Theme.focusRing : Theme.borderStrong
    activeFocusOnTab: root.enabled

    Behavior on color { ColorAnimation { duration: Theme.motionFast } }

    Row {
        id: labelRow
        anchors.centerIn: parent
        spacing: root.hasLabel ? 6 : 0

        AppIcon {
            anchors.verticalCenter: parent.verticalCenter
            iconName: root.iconName
            iconSize: 15
            iconColor: !root.enabled
                       ? Theme.textDisabled
                       : (root.active ? Theme.accent : Theme.textSecondary)
        }

        Text {
            visible: root.hasLabel
            anchors.verticalCenter: parent.verticalCenter
            text: root.text
            color: !root.enabled
                   ? Theme.textDisabled
                   : (root.active ? Theme.accent : Theme.textPrimary)
            font.family: Theme.bodyFont
            font.pixelSize: 11
            font.weight: Font.Normal
        }
    }

    MouseArea {
        id: mouseArea
        anchors.fill: parent
        // 始终接收悬停，只在点击时判断 enabled —— 禁用状态的按钮更需要 tooltip。
        hoverEnabled: true
        cursorShape: root.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPressed: if (root.enabled) root.forceActiveFocus(Qt.MouseFocusReason)
        onClicked: if (root.enabled) root.clicked()
    }

    Keys.onSpacePressed: if (root.enabled) root.clicked()
    Keys.onReturnPressed: if (root.enabled) root.clicked()

    ToolTip.visible: mouseArea.containsMouse && root.tooltip.length > 0
    ToolTip.text: root.tooltip
    ToolTip.delay: 480
    Accessible.name: root.tooltip.length > 0 ? root.tooltip : root.text
    Accessible.role: Accessible.Button
}
