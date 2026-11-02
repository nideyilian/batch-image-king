import QtQuick
import QtQuick.Layouts
import "."

// 预设列表行（列表视图）。
//
// 何时用列表：预设数量多、且用户按名称/日期找东西时。卡片识别靠图，
// 列表识别靠字段对齐——两者都必须有（Canva / PS 预设管理器均提供双视图）。

Rectangle {
    id: row

    property var presetData: null
    property bool selected: false
    property int thumbTick: 0
    property bool dropTarget: false

    // 同上：不能与 property bool selected 同名
    signal activated()
    signal loadRequested()
    signal favoriteToggled()

    readonly property bool hovered: hoverArea.containsMouse
    readonly property bool thumbReady: presetData && presetData.thumbnailUrl.length > 0

    implicitHeight: 52
    color: dropTarget
           ? Theme.accentSoft
           : (selected ? Theme.bgSelected : (hovered ? Theme.bgHover : "transparent"))

    Rectangle {
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        height: 1
        color: Theme.border
    }

    RowLayout {
        anchors.fill: parent
        anchors.leftMargin: 8
        anchors.rightMargin: 8
        spacing: 10

        // 缩略小图
        Rectangle {
            Layout.preferredWidth: 64
            Layout.preferredHeight: 38
            color: Theme.bgCanvas
            border.width: 1
            border.color: Theme.border
            clip: true

            Image {
                anchors.fill: parent
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                cache: false
                source: {
                    var tick = row.thumbTick
                    return row.presetData ? row.presetData.thumbnailUrl : ""
                }
                opacity: status === Image.Ready ? 1 : 0
            }

            AppIcon {
                anchors.centerIn: parent
                visible: !row.thumbReady
                iconName: AppIcons.loaderCircle
                iconSize: 14
                iconColor: Theme.textMuted
            }
        }

        // 名称 + 描述
        ColumnLayout {
            Layout.fillWidth: true
            spacing: 1
            Text {
                Layout.fillWidth: true
                text: row.presetData ? row.presetData.name : ""
                color: Theme.textPrimary
                font.family: Theme.bodyFont
                font.pixelSize: 12
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }
            TinyLabel {
                Layout.fillWidth: true
                text: row.presetData && row.presetData.description.length > 0
                      ? row.presetData.description
                      : (row.presetData ? row.presetData.category : "")
                color: Theme.textMuted
                elide: Text.ElideRight
            }
        }

        TinyLabel {
            Layout.preferredWidth: 92
            text: row.presetData && row.presetData.canvasSizes.length > 0
                  ? row.presetData.canvasSizes[0] : "—"
            color: Theme.textSecondary
        }

        TinyLabel {
            Layout.preferredWidth: 56
            text: row.presetData ? row.presetData.totalLayers + " 层" : ""
            color: Theme.textMuted
        }

        TinyLabel {
            Layout.preferredWidth: 88
            text: {
                if (!row.presetData) return ""
                if (row.presetData.runCount === 0) return "未使用"
                return row.presetData.runCount + " 次 · " +
                       (row.presetData.lastUsedAt ? row.presetData.lastUsedAt.substring(5, 10) : "")
            }
            color: Theme.textMuted
        }

        IconButton {
            iconName: AppIcons.bookmark
            buttonSize: 26
            active: row.presetData && row.presetData.favorite
            tooltip: row.presetData && row.presetData.favorite ? "取消收藏" : "加入收藏"
            onClicked: row.favoriteToggled()
        }

        IconButton {
            iconName: AppIcons.folderOpen
            buttonSize: 26
            tooltip: "打开为新标签页"
            onClicked: row.loadRequested()
        }
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        // 让按钮先拿到点击
        propagateComposedEvents: true
        onClicked: function(mouse) {
            row.activated()
            mouse.accepted = false
        }
    }
}
