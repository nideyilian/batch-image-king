import QtQuick
import QtQuick.Layouts

// 批量导出完成后的「结果可能不对」提示条。
//
// 降级和数量调整都意味着：图出来了，但和用户预期不一致。
// 这类信息不能只写日志，否则用户只会看到「图不对」却无从排查。
// 经典版在完成提示文案里带这句，QML 版用独立告警条承接。
Rectangle {
    id: root

    property string degradationText: ""
    property string adjustmentText: ""

    readonly property bool hasWarning: degradationText.length > 0 || adjustmentText.length > 0

    Layout.fillWidth: true
    visible: hasWarning
    implicitHeight: body.implicitHeight + 16
    radius: Theme.radiusSmall
    color: Theme.bgRaised
    border.width: 1
    border.color: Theme.border

    ColumnLayout {
        id: body
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        anchors.topMargin: 8
        spacing: 2

        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: root.degradationText.length > 0
            AppIcon {
                iconName: AppIcons.warning
                iconSize: 12
                iconColor: Theme.warning
            }
            TinyLabel {
                Layout.fillWidth: true
                text: root.degradationText
                color: Theme.warning
                wrapMode: Text.WordWrap
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: 6
            visible: root.adjustmentText.length > 0
            AppIcon {
                iconName: AppIcons.info
                iconSize: 12
                iconColor: Theme.warning
            }
            TinyLabel {
                Layout.fillWidth: true
                text: root.adjustmentText
                color: Theme.warning
                wrapMode: Text.WordWrap
            }
        }
    }
}
