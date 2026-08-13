import QtQuick

Item {
    id: root

    property string title: ""
    property string summary: ""
    // 保留可写兼容属性：现有 Main.qml 会主动展开目标分区。
    // Hermes 工作台默认保持分区展开，避免属性面板里出现隐藏的完成路径。
    property bool expanded: true
    default property alias sectionData: contentColumn.data

    // ★ 去除折叠：始终展开高度
    implicitHeight: header.height + contentColumn.implicitHeight + 9
    height: implicitHeight

    Rectangle {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        height: Theme.sectionHeaderHeight
        color: "transparent"

        Text {
            anchors.left: parent.left
            anchors.leftMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: root.title
            color: Theme.textPrimary
            font.family: Theme.bodyFont
            font.pixelSize: 11
            font.weight: Font.DemiBold
        }

        Text {
            anchors.right: parent.right
            anchors.rightMargin: 8
            anchors.verticalCenter: parent.verticalCenter
            text: root.summary
            color: Theme.textMuted
            font.family: Theme.bodyFont
            font.pixelSize: 10
        }
    }

    Column {
        id: contentColumn
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        anchors.topMargin: 3
        spacing: 3
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
