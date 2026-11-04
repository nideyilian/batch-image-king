import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: root

    // 编号只在「存在先后顺序且有当前步骤反馈的流程」里显示（见
    // docs/hermes-desktop-design-system.md 6.2）。并列导航和动作按钮默认关闭，
    // 否则 01/02/03 会被误读成必须依次完成的步骤。
    property bool showIndex: false
    property string index: ""
    property string text: ""
    property string iconName: ""
    property bool active: false
    property string badge: ""
    // tooltip 要说清「点了会发生什么」，不能只是复读标签文字。
    property string description: ""
    signal clicked()

    // 宽度跟随文案自适应：固定 112 会把「新建画布」这类四字标签挤成省略号。
    // 同一行里的多项仍保持等宽观感，由使用方按最长标签统一 covered 即可。
    implicitWidth: Math.max(84, contentRow.implicitWidth + 19)
    implicitHeight: 34
    radius: Theme.radiusSmall
    color: active
           ? Theme.accent
           : (mouse.containsMouse ? Theme.bgHover : "transparent")
    border.width: active ? 1 : 0
    border.color: Theme.accent
    activeFocusOnTab: enabled

    RowLayout {
        id: contentRow
        anchors.fill: parent
        anchors.leftMargin: 10
        anchors.rightMargin: 9
        spacing: 8

        Text {
            visible: root.showIndex && root.index.length > 0
            text: root.index
            color: !root.enabled
                   ? Theme.textDisabled
                   : (root.active ? Theme.accentForeground : Theme.textMuted)
            font.family: Theme.dataFont
            font.pixelSize: 11
        }

        AppIcon {
            visible: root.iconName.length > 0
            iconName: root.iconName
            iconSize: 15
            iconColor: !root.enabled
                       ? Theme.textDisabled
                       : (root.active ? Theme.accentForeground : Theme.textSecondary)
        }

        Text {
            text: root.text
            color: !root.enabled
                   ? Theme.textDisabled
                   : (root.active ? Theme.accentForeground : Theme.textPrimary)
            font.family: Theme.bodyFont
            font.pixelSize: 12
            font.weight: root.active ? Font.DemiBold : Font.Normal
            // 不设 Layout.fillWidth：宽度由文案决定，避免与 implicitWidth 形成绑定环。
            elide: Text.ElideNone
        }

        Text {
            visible: root.badge.length > 0
            text: root.badge
            color: !root.enabled
                   ? Theme.textDisabled
                   : (root.active ? Theme.accentForeground : Theme.textMuted)
            font.family: Theme.dataFont
            font.pixelSize: 11
        }
    }

    MouseArea {
        id: mouse
        anchors.fill: parent
        hoverEnabled: true
        enabled: root.enabled
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onPressed: root.forceActiveFocus(Qt.MouseFocusReason)
        onClicked: root.clicked()
    }

    Keys.onSpacePressed: clicked()
    Keys.onReturnPressed: clicked()
    ToolTip.visible: mouse.containsMouse && root.text.length > 0
    ToolTip.text: root.description.length > 0 ? root.description : root.text
    ToolTip.delay: 420
    Accessible.name: root.text
    Accessible.role: Accessible.Button
}
