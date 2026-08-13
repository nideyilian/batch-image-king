import QtQuick

Item {
    id: root

    property string title: ""
    property string summary: ""
    // 保留可写兼容属性：现有 Main.qml 会主动展开目标分区。
    // Hermes 工作台默认保持分区展开，避免属性面板里出现隐藏的完成路径。
    property bool expanded: true
    default property alias sectionData: contentColumn.data

    implicitHeight: header.height + (root.expanded ? contentColumn.implicitHeight + Theme.space4 : 0) + 1
    height: implicitHeight

    Rectangle {
        id: header
        anchors.left: parent.left
        anchors.right: parent.right
        height: Theme.sectionHeaderHeight
        color: Theme.bgRaised

        Text {
            anchors.left: parent.left
            anchors.leftMargin: Theme.inspectorSectionGutter
            anchors.verticalCenter: parent.verticalCenter
            text: root.title
            color: Theme.textPrimary
            font.family: Theme.bodyFont
            font.pixelSize: Theme.fontSizeSm
            font.weight: Font.DemiBold
        }

        Text {
            anchors.right: parent.right
            anchors.rightMargin: Theme.inspectorSectionGutter
            anchors.verticalCenter: parent.verticalCenter
            text: root.summary
            color: Theme.textMuted
            font.family: Theme.bodyFont
            font.pixelSize: Theme.fontSizeXs
        }
    }

    Column {
        id: contentColumn
        anchors.top: header.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.leftMargin: Theme.inspectorSectionGutter
        anchors.rightMargin: Theme.inspectorSectionGutter
        anchors.topMargin: Theme.inspectorRowSpacing
        spacing: Theme.inspectorRowSpacing
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
