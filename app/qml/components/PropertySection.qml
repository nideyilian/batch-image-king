import QtQuick

Item {
    id: root

    property string title: ""
    property string summary: ""
    readonly property bool expanded: true
    default property alias sectionData: contentColumn.data

    implicitHeight: cardContainer.implicitHeight
    height: implicitHeight

    // —— 卡片容器：Atelier Glass 分区卡片
    Rectangle {
        id: cardContainer
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.topMargin: 5
        anchors.bottomMargin: 4
        radius: Theme.radiusCard
        color: Theme.glassFill
        border { width: 1; color: Theme.glassHighlight; opacity: 0.7 }
        implicitHeight: header.height + contentColumn.implicitHeight + 14

        // 玻璃高光顶边
        Rectangle { anchors.top: parent.top; anchors.left: parent.left; anchors.right: parent.right; height: 1; radius: Theme.radiusCard; color: "#ffffff"; opacity: 0.04 }

        Row {
            id: header
            anchors.left: parent.left
            anchors.leftMargin: 12
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.top: parent.top
            anchors.topMargin: 10
            height: Theme.sectionHeaderHeight

            // 琥珀金装饰圆点
            Rectangle {
                width: 5
                height: 5
                radius: 3
                color: Theme.accent
                anchors.verticalCenter: parent.verticalCenter
                anchors.rightMargin: 8
                Rectangle { anchors.centerIn: parent; width: 2; height: 2; radius: 1; color: Theme.amberGlow }
            }

            Text {
                id: sectionTitle
                text: root.title
                color: Theme.textPrimary
                font.family: Theme.displayFont
                font.pixelSize: 11.5
                font.weight: Font.DemiBold
                font.letterSpacing: 0.15
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 9
            }

            // 琥珀金线连到 summary
            Item {
                width: 1
                height: parent.height - 4
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: sectionTitle.right
                anchors.leftMargin: 10
                Rectangle { anchors.centerIn: parent; width: 1; height: 14; color: Theme.border; opacity: 0.5 }
            }

            Text {
                text: root.summary
                color: Theme.amber
                font.family: Theme.interfaceFont
                font.pixelSize: 10
                font.weight: Font.Medium
                opacity: 0.88
                anchors.verticalCenter: parent.verticalCenter
                anchors.left: parent.left
                anchors.leftMargin: 12 + 9 + sectionTitle.implicitWidth + 10 + 1
            }
        }

        Column {
            id: contentColumn
            anchors.top: header.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 12
            anchors.rightMargin: 12
            anchors.topMargin: 6
            spacing: 3
            visible: true
        }

        // 底边柔和分隔（代替硬 border）
        Rectangle {
            anchors.left: parent.left; anchors.leftMargin: 14
            anchors.right: parent.right; anchors.rightMargin: 14
            anchors.bottom: parent.bottom
            height: 1
            color: Theme.glassShadow
            opacity: 0.55
        }
    }

    Accessible.name: title
    Accessible.role: Accessible.Grouping
}
