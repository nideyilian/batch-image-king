import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "."

// 预设卡片（网格视图）。
//
// 结构参考 Figma 文件卡片 + Canva 模板卡：
//   [封面上 16:9 缩略图]
//   [名称 / 画布尺寸 / 图层数]
// 悬停时封面淡入操作条（打开 / 批量创作 / 复制 / 导出 / 删除）。
//
// 缩略图未就绪时显示骨架（扫描条纹），不做转圈——一屏十几个转圈太吵。

Rectangle {
    id: card

    property var presetData: null
    property bool selected: false
    property int thumbTick: 0
    // 悬停轮播：多页预设按页循环换图
    property int carouselIndex: 0
    readonly property var pageThumbs: presetData && presetData.pageThumbs
                                        ? presetData.pageThumbs : []
    readonly property bool carouselAvailable: pageThumbs.length > 1
    // 堆叠角标：模拟"底下还有几页"的卡片层叠感
    readonly property int stackDepth: carouselAvailable
                                      ? Math.min(3, pageThumbs.length) : 0

    // 拖拽重排（仅「手动排序」模式启用）
    property bool dragEnabled: false
    property bool dragging: false
    property bool dropTarget: false

    // 注意：不能叫 selected()——上面已有 property bool selected，
    // QML 里同名会互相遮蔽，实测 card.selected() 会变成"把 bool 当函数调"，
    // 报 "Property 'selected' ... is not a function" 且点击完全无反应。
    signal activated()
    signal loadRequested()
    signal batchRequested()
    signal favoriteToggled()
    signal duplicateRequested()
    signal exportRequested()
    signal deleteRequested()

    readonly property bool thumbReady: presetData && presetData.thumbnailUrl.length > 0
    // 悬停态用 HoverHandler 提供，点击用 TapHandler。
    // 不用覆盖全卡的 MouseArea：它会抢走子按钮的点击（QML 的兄弟节点
    // 命中测试按声明顺序 + z 决定，在 Layout 里很难稳定控制）。
    // PointerHandler 系与子项的交互优先级天然是「子项优先」。
    readonly property bool hovered: cardHover.hovered

    color: selected ? Theme.bgSelected : (hovered ? Theme.bgHover : Theme.bgRaised)
    border.width: 1
    border.color: dropTarget
                  ? Theme.accent
                  : (selected ? Theme.accent : (hovered ? Theme.borderStrong : Theme.border))
    // 拖拽中的卡片浮起，和落点位置区分开
    opacity: dragging ? 0.55 : 1.0
    scale: dragging ? 1.02 : 1.0
    z: dragging ? 5 : 0
    Behavior on opacity { NumberAnimation { duration: 90 } }


    // 悬停 / 整卡点击。
    //
    // 必须在 ColumnLayout **之前**声明：QML 里后声明的兄弟节点在上层，
    // 放在后面会盖住内容，导致卡片底部按钮点了完全没反应
    // （实测：禁用整卡热区后按钮立刻恢复，加 z 无效）。
    HoverHandler {
        id: cardHover
    }

    TapHandler {
        acceptedButtons: Qt.LeftButton
        gesturePolicy: TapHandler.ReleaseWithinBounds
        onTapped: card.activated()
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ---------- 封面 ----------
        Rectangle {
            id: coverBox
            Layout.fillWidth: true
            Layout.fillHeight: true
            color: Theme.bgCanvas
            clip: true

            // 堆叠暗示：多页预设在封面上沿错位露出细边，
            // 让人一眼看出"这卡里不止一页"，不必悬停才知道。
            //
            // 注意 z 值：这里必须 > 0 才能压在封面上沿之上。
            // 之前用 z: -1（想放到"封面底下"）会被父容器背景整块遮住，
            // 表现为"改了完全没变化"。
            Image {
                id: cover
                anchors.fill: parent
                fillMode: Image.PreserveAspectCrop
                asynchronous: true
                cache: false
                // thumbTick 参与求值：缩略图重生成后强制换源
                source: {
                    var tick = card.thumbTick
                    if (!card.carouselAvailable)
                        return card.presetData ? card.presetData.thumbnailUrl : ""
                    var list = card.pageThumbs
                    var index = Math.max(0, Math.min(list.length - 1, card.carouselIndex))
                    return list[index]
                }
                opacity: status === Image.Ready ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 120 } }
            }

            // 骨架占位：斜向扫描条纹。
            // 浅色主题下 bgControl 是白色，和卡片底几乎没有区分，
            // 所以骨架统一压在 bgCanvas 上并加一层描边，保证两种主题都看得出「在加载」。
            Rectangle {
                anchors.fill: parent
                visible: !card.thumbReady || cover.status !== Image.Ready
                color: Theme.bgCanvas

                Rectangle {
                    id: shimmer
                    width: 60
                    height: parent.height * 1.6
                    y: -parent.height * 0.3
                    rotation: 18
                    // 深色用提亮、浅色用压暗：同一套透明色在两种底上观感相反
                    color: Theme.darkMode
                           ? Qt.rgba(1, 1, 1, 0.055)
                           : Qt.rgba(0, 0, 0, 0.045)

                    NumberAnimation on x {
                        running: shimmer.parent.visible
                        from: -80
                        to: card.width + 80
                        duration: 1100
                        loops: Animation.Infinite
                    }
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 4
                    AppIcon {
                        anchors.horizontalCenter: parent.horizontalCenter
                        iconName: AppIcons.loaderCircle
                        iconSize: 18
                        iconColor: Theme.textMuted
                    }
                    TinyLabel {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: "生成预览"
                    }
                }
            }

            // 顶部信息条：标签页数 / 收藏
            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.top: parent.top
                height: 26
                color: Qt.rgba(0, 0, 0, Theme.darkMode ? 0.42 : 0.05)
                visible: card.presetData && (card.presetData.documentCount > 1
                                             || card.presetData.favorite)

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 8
                    anchors.rightMargin: 6
                    spacing: 6

                    Rectangle {
                        visible: card.presetData && card.presetData.documentCount > 1
                        implicitWidth: tabCount.implicitWidth + 10
                        implicitHeight: 16
                        color: Qt.rgba(0, 0, 0, Theme.darkMode ? 0.45 : 0.12)
                        Text {
                            id: tabCount
                            anchors.centerIn: parent
                            text: card.presetData ? card.presetData.documentCount + " 页" : ""
                            color: Theme.textPrimary
                            font.family: Theme.dataFont
                            font.pixelSize: 9
                        }
                    }

                    // 页码圆点：告诉用户"有几页、现在第几页"。
                    // 试过把多页做成卡片层叠边（Figma 风格），但放在顶部会被
                    // 本信息条整条盖住；放在底部又会直接压住缩略图内容，很脏。
                    // 圆点是这个尺寸下最不占地方的表达方式。
                    // 页码圆点。4px 在 1x 屏几乎看不见（实测放大 4 倍才认得出），
                    // 所以加到 5px 并垫一层半透明深底，保证任何底图上都能分辨。
                    Rectangle {
                        visible: card.carouselAvailable
                        implicitWidth: dotsRow.implicitWidth + 10
                        implicitHeight: 17
                        radius: 3
                        color: Qt.rgba(0, 0, 0, 0.5)

                        Row {
                            id: dotsRow
                            anchors.centerIn: parent
                            spacing: 3

                            Repeater {
                                model: Math.min(6, card.pageThumbs.length)
                                delegate: Rectangle {
                                    required property int index
                                    width: 5
                                    height: 5
                                    radius: 2.5
                                    anchors.verticalCenter: parent.verticalCenter
                                    color: index === card.carouselIndex
                                           ? "#ffffff"
                                           : Qt.rgba(1, 1, 1, 0.45)
                                }
                            }
                            // 超过 6 页时用 +N 收尾，避免圆点拉成长条
                            Text {
                                visible: card.pageThumbs.length > 6
                                anchors.verticalCenter: parent.verticalCenter
                                text: "+" + (card.pageThumbs.length - 6)
                                color: Qt.rgba(1, 1, 1, 0.8)
                                font.family: Theme.dataFont
                                font.pixelSize: 8
                            }
                        }
                    }

                    Item { Layout.fillWidth: true }

                    Item {
                        implicitWidth: 20
                        implicitHeight: 20
                        visible: card.presetData && card.presetData.favorite
                        AppIcon {
                            anchors.centerIn: parent
                            iconName: AppIcons.bookmark
                            iconSize: 13
                            iconColor: Theme.warning
                        }
                    }
                }
            }

            // 素材缺失角标：源素材被删/移位后，缩略图会莫名其妙变空。
            // 不提示的话用户会以为程序坏了，而不是"我的图没了"。
            Rectangle {
                anchors.left: parent.left
                anchors.bottom: parent.bottom
                anchors.leftMargin: 6
                anchors.bottomMargin: 6
                visible: card.presetData && card.presetData.missingSources
                         && card.presetData.missingSources.length > 0
                implicitWidth: missText.implicitWidth + 12
                implicitHeight: 18
                color: Qt.rgba(0.72, 0.16, 0.12, 0.92)

                Text {
                    id: missText
                    anchors.centerIn: parent
                    text: card.presetData
                          ? "素材缺失 " + card.presetData.missingSources.length
                          : ""
                    color: "#ffffff"
                    font.family: Theme.bodyFont
                    font.pixelSize: 10
                }
            }

        }

        // ---------- 信息区 ----------
        // 三行结构：
        //   1. 名称（主信息）
        //   2. 画布 · 图层 · 分类角标（次要信息）
        //   3. 主操作条（常驻，不靠悬停）
        // 高度必须与 PresetWorkbench.infoHeight 一致，否则网格行高会错位。
        ColumnLayout {
            Layout.fillWidth: true
            Layout.preferredHeight: 92
            Layout.leftMargin: 9
            Layout.rightMargin: 9
            Layout.topMargin: 7
            spacing: 3

            Text {
                Layout.fillWidth: true
                text: card.presetData ? card.presetData.name : ""
                color: Theme.textPrimary
                font.family: Theme.bodyFont
                font.pixelSize: 12
                font.weight: Font.DemiBold
                elide: Text.ElideRight
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                TinyLabel {
                    Layout.maximumWidth: card.width - 90
                    elide: Text.ElideRight
                    // 多标签预设可能有多种画布：显示首个 + 总数，
                    // 只显示第一个会让人以为整个预设只有一种尺寸。
                    text: {
                        if (!card.presetData) return ""
                        var sizes = card.presetData.canvasSizes
                        if (!sizes || sizes.length === 0) return "未知画布"
                        return sizes.length > 1
                               ? sizes[0] + " +" + (sizes.length - 1)
                               : sizes[0]
                    }
                    color: Theme.textMuted
                }
                Rectangle {
                    width: 1
                    height: 8
                    color: Theme.border
                    visible: card.presetData && card.presetData.totalLayers > 0
                }
                TinyLabel {
                    // 窄卡片下"图层数"是最先该让位的：分类角标更有辨识价值。
                    visible: card.presetData && card.presetData.totalLayers > 0
                             && card.width >= 190
                    text: card.presetData ? card.presetData.totalLayers + " 图层" : ""
                    color: Theme.textMuted
                }
                Item { Layout.fillWidth: true }

                // 分类角标：让用户不打开检查器也能看出归属。
                // 未分类不显示，避免每张卡都挂一个无信息量的标签。
                Rectangle {
                    visible: card.presetData && card.presetData.category
                             && card.presetData.category !== "未分类"
                    implicitWidth: categoryText.implicitWidth + 10
                    implicitHeight: 15
                    color: "transparent"
                    border.width: 1
                    border.color: Theme.borderStrong
                    Text {
                        id: categoryText
                        anchors.centerIn: parent
                        text: card.presetData ? card.presetData.category : ""
                        color: Theme.textMuted
                        font.family: Theme.bodyFont
                        font.pixelSize: 10
                    }
                }
            }

            // 常驻操作条。
            // 之前所有操作都藏在「悬停浮层」里，鼠标一移开卡片只剩图和名字，
            // 用户以为没有按钮。这里把高频动作常驻，低频的收进「更多」。
            //
            // z 必须高于整卡 hoverArea（z:1），否则按钮收不到点击——
            // 这是实测踩过的坑：按钮看得见、点了没反应。
            RowLayout {
                Layout.fillWidth: true
                Layout.topMargin: 1
                spacing: 4
                z: 5

                // 主操作：一步打开为标签页。
                // 这是卡片的默认用途——"点开就用"，不再需要先进检查器再点一次。
                // 想先看详情再加标签页，用点卡片空白处选中后看右侧检查器。
                CardAction {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 24
                    label: "打开"
                    iconName: AppIcons.folderOpen
                    primary: true
                    tooltip: "打开为标签页"
                    enabled: card.presetData && card.presetData.documentCount > 0
                    onClicked: card.loadRequested()
                }

                // 次主操作：批量创作
                CardAction {
                    Layout.fillWidth: true
                    label: "批量"
                    iconName: AppIcons.randomize
                    enabled: card.presetData && card.presetData.totalLayers > 0
                    onClicked: card.batchRequested()
                }

                // 收藏（图标态，因为状态需要一眼可见）
                IconButton {
                    z: 5
                    iconName: AppIcons.bookmark
                    buttonSize: 24
                    iconSize: 13
                    active: card.presetData && card.presetData.favorite
                    tooltip: card.presetData && card.presetData.favorite ? "取消收藏" : "加入收藏"
                    onClicked: card.favoriteToggled()
                }

                // 更多：复制 / 导出 / 删除
                IconButton {
                    id: moreButton
                    z: 5
                    iconName: AppIcons.more
                    buttonSize: 24
                    iconSize: 13
                    tooltip: "更多操作"
                    onClicked: moreMenu.open()

                    AppMenu {
                        id: moreMenu
                        y: moreButton.height + 2
                        // 靠右弹，避免超出卡片右边界
                        x: moreButton.width - width

                        MenuItem {
                            text: "复制预设"
                            height: 30
                            onClicked: card.duplicateRequested()
                        }
                        MenuItem {
                            text: "导出预设…"
                            height: 30
                            onClicked: card.exportRequested()
                        }
                        MenuSeparator {}
                        MenuItem {
                            text: "删除预设"
                            height: 30
                            onClicked: card.deleteRequested()
                        }
                    }
                }
            }
        }

        // 内联：卡片操作按钮。
        // 不做成独立文件，因为它只服务卡片，且要读 card 的状态。
        component CardAction: Rectangle {
            id: action
            property string label: ""
            property string iconName: ""
            property string tooltip: ""
            property bool primary: false
            signal clicked()

            // 必须高于整卡 hoverArea（z:1）：后者在文件末尾声明，
            // QML 里后声明即在上层，不显式提层按钮会收不到点击。
            z: 5
            implicitHeight: 22
            radius: Theme.radiusSmall
            color: {
                if (!enabled) return "transparent"
                if (actionMouse.containsMouse) return primary ? Theme.accentPressed : Theme.bgHover
                return primary ? Theme.accent : "transparent"
            }
            border.width: 1
            border.color: !enabled
                          ? Theme.border
                          : (primary ? Theme.accent : Theme.borderStrong)
            opacity: enabled ? 1.0 : 0.45

            RowLayout {
                anchors.centerIn: parent
                spacing: 3
                AppIcon {
                    iconName: action.iconName
                    iconSize: 11
                    iconColor: action.primary ? Theme.accentForeground : Theme.textSecondary
                }
                Text {
                    text: action.label
                    color: action.primary ? Theme.accentForeground : Theme.textSecondary
                    font.family: Theme.bodyFont
                    font.pixelSize: 10
                    font.weight: Font.DemiBold
                }
            }

            ToolTip.visible: action.tooltip.length > 0 && actionMouse.containsMouse
            ToolTip.text: action.tooltip
            ToolTip.delay: 600

            MouseArea {
                id: actionMouse
                anchors.fill: parent
                hoverEnabled: true
                enabled: action.enabled
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: action.clicked()
            }
        }
    }

    // 悬停轮播：每 900ms 换一页。
    // 只在悬停且多页时跑——不在所有卡片上常驻定时器，避免 14 张卡
    // 同时刷新造成无谓的图片解码。
    Timer {
        id: carouselTimer
        interval: 900
        running: card.hovered && card.carouselAvailable && !card.dragging
        repeat: true
        onTriggered: {
            if (card.pageThumbs.length > 1)
                card.carouselIndex = (card.carouselIndex + 1) % card.pageThumbs.length
        }
    }

    // 离开悬停时回到封面页，下次进来从头开始
    onHoveredChanged: if (!hovered) card.carouselIndex = 0

}
