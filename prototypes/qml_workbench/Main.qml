import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import "components"

ApplicationWindow {
    id: window

    width: 1600
    height: 960
    minimumWidth: 1180
    minimumHeight: 720
    visible: true
    title: "批图王 · QML 工作台原型"
    color: Theme.bgApp

    property int selectedLayer: 0
    property int activeTool: 0
    property real zoomValue: 0.78
    property int inspectorTab: 0
    property bool randomTransformEnabled: true
    property string toastMessage: ""
    property string activeLayerName: layerModel.get(selectedLayer).name

    function showToast(message) {
        toastMessage = message
        toast.opacity = 1
        toastTimer.restart()
    }

    ListModel {
        id: layerModel
        ListElement { name: "限量腕表"; typeName: "文字"; glyph: "\uE8D2"; accent: "#46d7ad"; shown: true; locked: false }
        ListElement { name: "曜石黑 · 2026"; typeName: "文字"; glyph: "\uE8D2"; accent: "#f7bd63"; shown: true; locked: false }
        ListElement { name: "腕表主体"; typeName: "图片"; glyph: "\uEB9F"; accent: "#b9c4c0"; shown: true; locked: false }
        ListElement { name: "柔光叠加"; typeName: "异形"; glyph: "\uF158"; accent: "#f1786d"; shown: true; locked: false }
        ListElement { name: "产品底图"; typeName: "图片"; glyph: "\uEB9F"; accent: "#8e9894"; shown: true; locked: true }
        ListElement { name: "画布背景"; typeName: "背景"; glyph: "\uE91B"; accent: "#d9d9d5"; shown: true; locked: true }
    }

    component Divider: Rectangle {
        implicitWidth: 1
        implicitHeight: 1
        color: Theme.border
    }

    component TinyLabel: Text {
        color: Theme.textMuted
        font.family: Theme.bodyFont
        font.pixelSize: 10
        verticalAlignment: Text.AlignVCenter
    }

    component BodyLabel: Text {
        color: Theme.textSecondary
        font.family: Theme.bodyFont
        font.pixelSize: 12
        verticalAlignment: Text.AlignVCenter
    }

    component MenuLabel: Text {
        property bool hovered: false
        color: hovered ? Theme.textPrimary : Theme.textSecondary
        font.family: Theme.bodyFont
        font.pixelSize: 12
        verticalAlignment: Text.AlignVCenter
    }

    component ToolRailButton: Rectangle {
        id: toolButton
        property int toolIndex: 0
        property string glyph: ""
        property string label: ""

        width: 38
        height: 38
        radius: Theme.radius
        color: activeTool === toolIndex ? Theme.accentSoft : (toolMouse.containsMouse ? Theme.bgHover : "transparent")
        border.width: activeTool === toolIndex ? 1 : 0
        border.color: "#2c7460"

        AppIcon {
            anchors.centerIn: parent
            glyph: toolButton.glyph
            iconSize: 17
            iconColor: activeTool === toolButton.toolIndex ? Theme.accent : Theme.textSecondary
        }

        MouseArea {
            id: toolMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                activeTool = toolButton.toolIndex
                showToast("已切换到" + toolButton.label)
            }
        }

        ToolTip.visible: toolMouse.containsMouse
        ToolTip.text: toolButton.label
        ToolTip.delay: 420
    }

    component InspectorRow: RowLayout {
        property string label: ""
        spacing: 8
        width: parent ? parent.width : 300
        height: Theme.controlHeight

        BodyLabel {
            text: parent.label
            color: Theme.textMuted
            Layout.preferredWidth: 52
        }
    }

    ColumnLayout {
        objectName: "captureRoot"
        anchors.fill: parent
        spacing: 0

        Rectangle {
            id: titleBar
            Layout.fillWidth: true
            Layout.preferredHeight: 42
            color: Theme.bgBar

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 14
                anchors.rightMargin: 14
                spacing: 0

                Row {
                    Layout.preferredWidth: 188
                    spacing: 10

                    Item {
                        width: 26
                        height: 26

                        Rectangle {
                            width: 18; height: 18
                            anchors.left: parent.left
                            anchors.bottom: parent.bottom
                            color: Theme.accent
                            rotation: 8
                            radius: 2
                        }
                        Rectangle {
                            width: 14; height: 14
                            anchors.right: parent.right
                            anchors.top: parent.top
                            color: Theme.amber
                            rotation: -8
                            radius: 2
                        }
                    }

                    Text {
                        height: 26
                        text: "批图王"
                        color: Theme.textPrimary
                        font.family: Theme.displayFont
                        font.pixelSize: 17
                        font.weight: Font.DemiBold
                        verticalAlignment: Text.AlignVCenter
                    }
                }

                Row {
                    spacing: 24
                    Layout.preferredWidth: 360

                    Repeater {
                        model: ["文件", "编辑", "图层", "画布", "视图"]
                        delegate: MenuLabel {
                            required property string modelData
                            height: 42
                            text: modelData
                            hovered: menuMouse.containsMouse
                            MouseArea {
                                id: menuMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: showToast(parent.text + "菜单将在正式版本中接入")
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                Row {
                    spacing: 8

                    Rectangle {
                        width: gpuRow.width + 18
                        height: 26
                        radius: 13
                        color: "#192822"
                        border.width: 1
                        border.color: "#29473d"

                        Row {
                            id: gpuRow
                            anchors.centerIn: parent
                            spacing: 7
                            Rectangle { width: 6; height: 6; radius: 3; color: Theme.success; anchors.verticalCenter: parent.verticalCenter }
                            TinyLabel { text: "快速预览"; color: Theme.textSecondary; height: 20 }
                        }
                    }

                    IconButton { glyph: "\uE713"; tooltip: "设置"; buttonSize: 28; onClicked: showToast("设置") }
                    IconButton { glyph: "\uE77B"; tooltip: "账户"; buttonSize: 28; onClicked: showToast("账户") }
                }
            }

            Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom }
        }

        Rectangle {
            id: commandBar
            Layout.fillWidth: true
            Layout.preferredHeight: 54
            color: Theme.bgPanel

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 10
                anchors.rightMargin: 12
                spacing: 6

                IconButton { glyph: "\uE8E5"; tooltip: "打开项目"; onClicked: showToast("打开项目") }
                IconButton { glyph: "\uE74E"; tooltip: "保存"; onClicked: showToast("项目已保存") }
                Divider { Layout.preferredHeight: 24; Layout.leftMargin: 3; Layout.rightMargin: 3 }
                IconButton { glyph: "\uE7A7"; tooltip: "撤销"; onClicked: showToast("已撤销一步") }
                IconButton { glyph: "\uE7A6"; tooltip: "重做"; onClicked: showToast("已重做一步") }
                Divider { Layout.preferredHeight: 24; Layout.leftMargin: 3; Layout.rightMargin: 3 }

                Rectangle {
                    Layout.preferredWidth: 106
                    Layout.preferredHeight: 32
                    radius: Theme.radiusSmall
                    color: addImageMouse.containsMouse ? Theme.bgHover : Theme.bgControl
                    border.width: 1
                    border.color: Theme.borderStrong
                    Row {
                        anchors.centerIn: parent
                        spacing: 7
                        AppIcon { glyph: "\uE91B"; iconSize: 14; iconColor: Theme.textPrimary; height: 20 }
                        BodyLabel { text: "添加图片"; color: Theme.textPrimary; height: 20 }
                    }
                    MouseArea { id: addImageMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: showToast("添加图片图层") }
                }

                IconButton { glyph: "\uE8D2"; tooltip: "添加文字"; onClicked: showToast("添加文字图层") }
                IconButton { glyph: "\uF158"; tooltip: "添加异形"; onClicked: showToast("添加异形图层") }
                Divider { Layout.preferredHeight: 24; Layout.leftMargin: 3; Layout.rightMargin: 3 }
                IconButton { glyph: "\uE74B"; tooltip: "左对齐"; onClicked: showToast("左对齐") }
                IconButton { glyph: "\uE74A"; tooltip: "水平居中"; onClicked: showToast("水平居中") }
                IconButton { glyph: "\uE73F"; tooltip: "垂直居中"; onClicked: showToast("垂直居中") }

                Item { Layout.fillWidth: true }

                Rectangle {
                    Layout.preferredWidth: 92
                    Layout.preferredHeight: 32
                    radius: Theme.radiusSmall
                    color: Theme.bgControl
                    Row {
                        anchors.centerIn: parent
                        spacing: 8
                        AppIcon { glyph: "\uE71E"; iconSize: 14; height: 20 }
                        BodyLabel { text: "预览"; color: Theme.textPrimary; height: 20 }
                    }
                    MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: showToast("正在生成高质量预览") }
                }

                Rectangle {
                    Layout.preferredWidth: 112
                    Layout.preferredHeight: 32
                    radius: Theme.radiusSmall
                    color: exportMouse.pressed ? Theme.accentPressed : (exportMouse.containsMouse ? Theme.accentHover : Theme.accent)
                    Row {
                        anchors.centerIn: parent
                        spacing: 8
                        AppIcon { glyph: "\uEDE1"; iconSize: 14; iconColor: "#09251d"; height: 20 }
                        Text { text: "批量导出"; color: "#09251d"; font.family: Theme.bodyFont; font.pixelSize: 12; font.weight: Font.DemiBold; height: 20; verticalAlignment: Text.AlignVCenter }
                    }
                    MouseArea { id: exportMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: showToast("已创建批量导出任务") }
                }
            }

            Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom }
        }

        Rectangle {
            id: documentTabs
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            color: Theme.bgBar

            Row {
                anchors.fill: parent
                anchors.leftMargin: 48

                Rectangle {
                    width: 220
                    height: 36
                    color: Theme.bgCanvas
                    Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top; height: 2; color: Theme.accent }
                    Row {
                        anchors.centerIn: parent
                        spacing: 8
                        Rectangle { width: 6; height: 6; radius: 3; color: Theme.amber; anchors.verticalCenter: parent.verticalCenter }
                        BodyLabel { text: "腕表新品主图.cmp"; color: Theme.textPrimary; height: 22 }
                        AppIcon { glyph: "\uE711"; iconSize: 10; height: 22 }
                    }
                }

                Rectangle {
                    width: 192
                    height: 36
                    color: secondTabMouse.containsMouse ? Theme.bgRaised : "transparent"
                    Row {
                        anchors.centerIn: parent
                        spacing: 8
                        BodyLabel { text: "夏季活动海报.cmp"; height: 22 }
                        AppIcon { glyph: "\uE711"; iconSize: 10; height: 22 }
                    }
                    MouseArea { id: secondTabMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: showToast("切换文档") }
                }

                IconButton { glyph: "\uE710"; tooltip: "新建文档"; buttonSize: 36; onClicked: showToast("新建文档") }
            }

            Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            Rectangle {
                id: toolRail
                Layout.preferredWidth: 48
                Layout.fillHeight: true
                color: Theme.bgBar

                Column {
                    anchors.top: parent.top
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.topMargin: 10
                    spacing: 5

                    ToolRailButton { toolIndex: 0; glyph: "\uE7C9"; label: "选择工具 (V)" }
                    ToolRailButton { toolIndex: 1; glyph: "\uE7C2"; label: "抓手工具 (H)" }
                    ToolRailButton { toolIndex: 2; glyph: "\uE8D2"; label: "文字工具 (T)" }
                    ToolRailButton { toolIndex: 3; glyph: "\uF158"; label: "形状工具 (U)" }
                    ToolRailButton { toolIndex: 4; glyph: "\uE790"; label: "取色器 (I)" }
                    ToolRailButton { toolIndex: 5; glyph: "\uE71E"; label: "缩放工具 (Z)" }
                }

                Column {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottomMargin: 10
                    spacing: 6

                    Rectangle {
                        width: 26; height: 26; radius: 4; color: "#15221e"; border.width: 1; border.color: Theme.borderStrong
                        Rectangle { width: 15; height: 15; anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 3; color: Theme.accent; border.width: 1; border.color: "#84f0d0" }
                        Rectangle { width: 15; height: 15; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 3; color: "#f3f1ea"; border.width: 1; border.color: Theme.borderStrong }
                    }
                    ToolRailButton { toolIndex: 9; glyph: "\uE946"; label: "帮助" }
                }

                Divider { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right }
            }

            Rectangle {
                id: layerPanel
                Layout.preferredWidth: window.width < 1320 ? 236 : 276
                Layout.fillHeight: true
                color: Theme.bgPanel

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 44
                        Layout.leftMargin: 12
                        Layout.rightMargin: 10
                        spacing: 6

                        Text {
                            text: "图层"
                            color: Theme.textPrimary
                            font.family: Theme.displayFont
                            font.pixelSize: 13
                            font.weight: Font.DemiBold
                            Layout.fillWidth: true
                        }
                        IconButton { glyph: "\uE721"; tooltip: "筛选图层"; buttonSize: 28; onClicked: showToast("筛选图层") }
                        IconButton { glyph: "\uE710"; tooltip: "新建图层"; buttonSize: 28; onClicked: showToast("新建图层") }
                    }

                    Divider { Layout.fillWidth: true }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 38
                        color: Theme.bgBar

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            spacing: 0

                            Rectangle {
                                width: (parent.width - 20) / 2
                                height: parent.height
                                color: "transparent"
                                Text { anchors.centerIn: parent; text: "图层"; color: Theme.textPrimary; font.family: Theme.bodyFont; font.pixelSize: 11; font.weight: Font.DemiBold }
                                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 2; color: Theme.accent }
                            }
                            Rectangle {
                                width: (parent.width - 20) / 2
                                height: parent.height
                                color: assetTabMouse.containsMouse ? Theme.bgRaised : "transparent"
                                Text { anchors.centerIn: parent; text: "素材"; color: Theme.textMuted; font.family: Theme.bodyFont; font.pixelSize: 11 }
                                MouseArea { id: assetTabMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: showToast("素材视图") }
                            }
                        }
                    }

                    ListView {
                        id: layerList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: layerModel
                        currentIndex: selectedLayer
                        boundsBehavior: Flickable.StopAtBounds

                        delegate: Rectangle {
                            id: layerDelegate
                            required property int index
                            required property string name
                            required property string typeName
                            required property string glyph
                            required property color accent
                            required property bool shown
                            required property bool locked

                            width: layerList.width
                            height: 62
                            color: selectedLayer === index ? Theme.bgSelected : (layerMouse.containsMouse ? Theme.bgRaised : "transparent")

                            Rectangle {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                width: 2
                                color: selectedLayer === index ? Theme.accent : "transparent"
                            }

                            IconButton {
                                id: eyeButton
                                anchors.left: parent.left
                                anchors.leftMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                glyph: layerDelegate.shown ? "\uE890" : "\uED1A"
                                tooltip: layerDelegate.shown ? "隐藏图层" : "显示图层"
                                buttonSize: 28
                                onClicked: {
                                    layerModel.setProperty(layerDelegate.index, "shown", !layerDelegate.shown)
                                    showToast(layerDelegate.shown ? "图层已隐藏" : "图层已显示")
                                }
                            }

                            Rectangle {
                                anchors.left: eyeButton.right
                                anchors.leftMargin: 4
                                anchors.verticalCenter: parent.verticalCenter
                                width: 38
                                height: 38
                                radius: Theme.radiusSmall
                                color: layerDelegate.index === 2 || layerDelegate.index === 4 ? "#d8d8d4" : Theme.bgControl
                                border.width: 1
                                border.color: Theme.borderStrong

                                AppIcon {
                                    anchors.centerIn: parent
                                    glyph: layerDelegate.glyph
                                    iconSize: 16
                                    iconColor: layerDelegate.accent
                                }
                            }

                            Column {
                                anchors.left: parent.left
                                anchors.leftMargin: 82
                                anchors.right: lockButton.left
                                anchors.rightMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 3
                                Text { width: parent.width; text: layerDelegate.name; color: selectedLayer === index ? Theme.textPrimary : Theme.textSecondary; font.family: Theme.bodyFont; font.pixelSize: 11; font.weight: selectedLayer === index ? Font.DemiBold : Font.Normal; elide: Text.ElideRight }
                                TinyLabel { text: layerDelegate.typeName; color: Theme.textMuted; height: 15 }
                            }

                            IconButton {
                                id: lockButton
                                anchors.right: parent.right
                                anchors.rightMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                glyph: layerDelegate.locked ? "\uE72E" : "\uE785"
                                tooltip: layerDelegate.locked ? "解锁图层" : "锁定图层"
                                buttonSize: 28
                                onClicked: layerModel.setProperty(layerDelegate.index, "locked", !layerDelegate.locked)
                            }

                            MouseArea {
                                id: layerMouse
                                anchors.fill: parent
                                anchors.leftMargin: 38
                                anchors.rightMargin: 38
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: selectedLayer = layerDelegate.index
                            }

                            Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 42
                        color: Theme.bgBar

                        Row {
                            anchors.centerIn: parent
                            spacing: 5
                            IconButton { glyph: "\uE710"; tooltip: "新建图层"; buttonSize: 28; onClicked: showToast("新建图层") }
                            IconButton { glyph: "\uE8B0"; tooltip: "创建分组"; buttonSize: 28; onClicked: showToast("创建图层组") }
                            IconButton { glyph: "\uE8C8"; tooltip: "复制图层"; buttonSize: 28; onClicked: showToast("已复制图层") }
                            IconButton { glyph: "\uE74D"; tooltip: "删除图层"; buttonSize: 28; onClicked: showToast("删除需要二次确认") }
                        }
                    }
                }

                Divider { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right }
            }

            Rectangle {
                id: workspace
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.bgCanvas
                clip: true

                property real fitScale: Math.min(0.86, (height - 50) / 650, (width - 60) / 520)
                property real actualScale: Math.min(zoomValue, fitScale)

                Canvas {
                    anchors.fill: parent
                    onPaint: {
                        var ctx = getContext("2d")
                        ctx.clearRect(0, 0, width, height)
                        ctx.fillStyle = Theme.gridDot
                        for (var y = 18; y < height; y += 18) {
                            for (var x = 18; x < width; x += 18) {
                                ctx.fillRect(x, y, 1, 1)
                            }
                        }
                    }
                }

                Item {
                    id: artboardFrame
                    width: 520 * workspace.actualScale
                    height: 650 * workspace.actualScale
                    anchors.centerIn: parent

                    Rectangle {
                        width: 520
                        height: 650
                        scale: workspace.actualScale
                        transformOrigin: Item.TopLeft
                        color: "#f1f0ec"
                        border.width: 1
                        border.color: "#5c6260"

                        Image {
                            id: productImage
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            height: 428
                            source: "assets/watch-product.jpg"
                            fillMode: Image.PreserveAspectCrop
                            asynchronous: false
                            cache: true
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            height: 428
                            color: "transparent"
                            border.width: selectedLayer === 2 || selectedLayer === 4 ? 2 : 0
                            border.color: Theme.accent
                        }

                        Rectangle {
                            x: 34
                            y: 28
                            width: 92
                            height: 26
                            radius: 13
                            color: "#e8ebe7"
                            border.width: 1
                            border.color: "#c4cbc7"
                            Text { anchors.centerIn: parent; text: "ATELIER 26"; color: "#19201e"; font.family: Theme.bodyFont; font.pixelSize: 10; font.weight: Font.DemiBold }
                        }

                        Text {
                            anchors.right: parent.right
                            anchors.rightMargin: 30
                            y: 31
                            text: "01 / 06"
                            color: "#4a514e"
                            font.family: Theme.bodyFont
                            font.pixelSize: 10
                            font.letterSpacing: 1
                        }

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            height: 222
                            color: "#111816"

                            Rectangle { x: 34; y: 27; width: 44; height: 3; color: Theme.accent }

                            Text {
                                id: headline
                                x: 34
                                y: 47
                                width: 430
                                text: "限量腕表"
                                color: "#f5f3eb"
                                font.family: Theme.displayFont
                                font.pixelSize: 38
                                font.weight: Font.DemiBold
                                font.letterSpacing: 0
                            }

                            Text {
                                x: 36
                                y: 102
                                text: "曜石黑 · 2026 EDITION"
                                color: Theme.amber
                                font.family: Theme.bodyFont
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                                font.letterSpacing: 1
                            }

                            Text {
                                x: 36
                                y: 140
                                width: 282
                                text: "留住每一次准确抵达。\n轻量陶瓷表体，48 小时长续航。"
                                color: "#9ea9a5"
                                font.family: Theme.bodyFont
                                font.pixelSize: 11
                                lineHeight: 1.55
                            }

                            Rectangle {
                                x: 384
                                y: 139
                                width: 102
                                height: 38
                                radius: 3
                                color: "#f1eee5"
                                Text { anchors.centerIn: parent; text: "立即探索  →"; color: "#111816"; font.family: Theme.bodyFont; font.pixelSize: 10; font.weight: Font.DemiBold }
                            }

                            Rectangle {
                                visible: selectedLayer === 0 || selectedLayer === 1
                                x: selectedLayer === 0 ? 26 : 28
                                y: selectedLayer === 0 ? 39 : 94
                                width: selectedLayer === 0 ? 240 : 222
                                height: selectedLayer === 0 ? 58 : 30
                                color: "transparent"
                                border.width: 1
                                border.color: Theme.accent

                                Repeater {
                                    model: [
                                        {"x": -3, "y": -3}, {"x": parent.width / 2 - 3, "y": -3}, {"x": parent.width - 3, "y": -3},
                                        {"x": -3, "y": parent.height - 3}, {"x": parent.width / 2 - 3, "y": parent.height - 3}, {"x": parent.width - 3, "y": parent.height - 3}
                                    ]
                                    delegate: Rectangle {
                                        required property var modelData
                                        x: modelData.x
                                        y: modelData.y
                                        width: 6
                                        height: 6
                                        color: "#f4f7f5"
                                        border.width: 1
                                        border.color: Theme.accentPressed
                                    }
                                }
                            }
                        }

                        Rectangle {
                            visible: selectedLayer === 3
                            x: 330
                            y: 82
                            width: 150
                            height: 150
                            radius: 75
                            color: "transparent"
                            border.width: 1
                            border.color: Theme.coral
                        }
                    }
                }

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 14
                    width: canvasBadgeRow.width + 20
                    height: 25
                    radius: 12
                    color: "#d916191b"
                    border.width: 1
                    border.color: Theme.border
                    Row {
                        id: canvasBadgeRow
                        anchors.centerIn: parent
                        spacing: 7
                        Rectangle { width: 5; height: 5; radius: 3; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                        TinyLabel { text: "1080 × 1350 px  ·  RGB"; color: Theme.textSecondary; height: 18 }
                    }
                }

                Rectangle {
                    id: toast
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 24
                    width: toastRow.width + 28
                    height: 38
                    radius: Theme.radius
                    color: "#ec222729"
                    border.width: 1
                    border.color: "#40504b"
                    opacity: 0

                    Behavior on opacity { NumberAnimation { duration: Theme.motionNormal } }

                    Row {
                        id: toastRow
                        anchors.centerIn: parent
                        spacing: 9
                        Rectangle { width: 7; height: 7; radius: 4; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                        BodyLabel { text: toastMessage; color: Theme.textPrimary; height: 22 }
                    }

                    Timer {
                        id: toastTimer
                        interval: 1800
                        onTriggered: toast.opacity = 0
                    }
                }
            }

            Rectangle {
                id: inspector
                Layout.preferredWidth: window.width < 1320 ? 302 : 336
                Layout.fillHeight: true
                color: Theme.bgPanel

                ColumnLayout {
                    anchors.fill: parent
                    spacing: 0

                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 56

                        Column {
                            anchors.left: parent.left
                            anchors.leftMargin: 14
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 3
                            Text { text: activeLayerName; color: Theme.textPrimary; font.family: Theme.displayFont; font.pixelSize: 13; font.weight: Font.DemiBold }
                            TinyLabel { text: layerModel.get(selectedLayer).typeName + "图层  ·  #" + (selectedLayer + 1); height: 15 }
                        }

                        IconButton { anchors.right: parent.right; anchors.rightMargin: 10; anchors.verticalCenter: parent.verticalCenter; glyph: "\uE712"; tooltip: "更多操作"; buttonSize: 28; onClicked: showToast("图层更多操作") }
                    }

                    Divider { Layout.fillWidth: true }

                    Row {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 40

                        Repeater {
                            model: ["属性", "效果"]
                            delegate: Rectangle {
                                required property int index
                                required property string modelData
                                width: inspector.width / 2
                                height: 40
                                color: inspectorTab === index ? Theme.bgRaised : "transparent"
                                Text { anchors.centerIn: parent; text: modelData; color: inspectorTab === index ? Theme.textPrimary : Theme.textMuted; font.family: Theme.bodyFont; font.pixelSize: 11; font.weight: inspectorTab === index ? Font.DemiBold : Font.Normal }
                                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 2; color: inspectorTab === index ? Theme.accent : "transparent" }
                                MouseArea { anchors.fill: parent; cursorShape: Qt.PointingHandCursor; onClicked: inspectorTab = index }
                            }
                        }
                    }

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        Column {
                            width: inspector.width
                            visible: inspectorTab === 0

                            PropertySection {
                                width: parent.width
                                title: "变换"
                                summary: "px / °"

                                InspectorRow {
                                    label: "位置"
                                    ValueBox { text: selectedLayer === 0 ? "34" : "0"; suffix: "X"; Layout.fillWidth: true }
                                    ValueBox { text: selectedLayer === 0 ? "475" : "0"; suffix: "Y"; Layout.fillWidth: true }
                                }
                                InspectorRow {
                                    label: "尺寸"
                                    ValueBox { text: selectedLayer === 0 ? "240" : "520"; suffix: "W"; Layout.fillWidth: true }
                                    ValueBox { text: selectedLayer === 0 ? "58" : "428"; suffix: "H"; Layout.fillWidth: true }
                                }
                                InspectorRow {
                                    label: "旋转"
                                    ValueBox { text: "0"; suffix: "°"; Layout.fillWidth: true }
                                    Rectangle {
                                        Layout.preferredWidth: 32; Layout.preferredHeight: 30; radius: Theme.radiusSmall; color: Theme.bgControl; border.width: 1; border.color: Theme.borderStrong
                                        AppIcon { anchors.centerIn: parent; glyph: "\uE72C"; iconSize: 13 }
                                    }
                                }
                            }

                            PropertySection {
                                width: parent.width
                                title: "外观"
                                summary: "正常"

                                InspectorRow {
                                    label: "不透明度"
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 4
                                        radius: 2
                                        color: Theme.borderStrong
                                        Rectangle { width: parent.width * 0.92; height: parent.height; radius: 2; color: Theme.accent }
                                        Rectangle { x: parent.width * 0.92 - 7; anchors.verticalCenter: parent.verticalCenter; width: 14; height: 14; radius: 7; color: Theme.textPrimary; border.width: 2; border.color: Theme.accentPressed }
                                    }
                                    ValueBox { text: "92"; suffix: "%"; Layout.preferredWidth: 66 }
                                }
                                InspectorRow {
                                    label: "混合"
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 30
                                        radius: Theme.radiusSmall
                                        color: Theme.bgControl
                                        border.width: 1
                                        border.color: Theme.borderStrong
                                        BodyLabel { anchors.left: parent.left; anchors.leftMargin: 9; anchors.verticalCenter: parent.verticalCenter; text: "正常" }
                                        AppIcon { anchors.right: parent.right; anchors.rightMargin: 8; anchors.verticalCenter: parent.verticalCenter; glyph: "\uE70D"; iconSize: 10 }
                                    }
                                }
                                InspectorRow {
                                    label: "填充"
                                    Rectangle { Layout.preferredWidth: 30; Layout.preferredHeight: 30; radius: 4; color: selectedLayer < 2 ? "#f4f2eb" : "#d9d9d5"; border.width: 1; border.color: Theme.borderStrong }
                                    ValueBox { text: selectedLayer < 2 ? "#F4F2EB" : "原图"; Layout.fillWidth: true; editable: false }
                                }
                            }

                            PropertySection {
                                width: parent.width
                                title: "随机变换"
                                summary: randomTransformEnabled ? "已启用" : "关闭"

                                InspectorRow {
                                    label: "启用"
                                    BodyLabel { text: "每次导出生成变化"; color: Theme.textSecondary; Layout.fillWidth: true }
                                    ToggleSwitch { checked: randomTransformEnabled; onToggled: checkedValue => randomTransformEnabled = checkedValue }
                                }
                                InspectorRow {
                                    label: "位置"
                                    ValueBox { text: "-12"; suffix: "min"; Layout.fillWidth: true }
                                    ValueBox { text: "+12"; suffix: "max"; Layout.fillWidth: true }
                                }
                                InspectorRow {
                                    label: "旋转"
                                    ValueBox { text: "-3"; suffix: "°"; Layout.fillWidth: true }
                                    ValueBox { text: "+3"; suffix: "°"; Layout.fillWidth: true }
                                }
                            }

                            PropertySection {
                                width: parent.width
                                title: "图层绑定"
                                summary: "未绑定"
                                expanded: false
                            }
                        }

                        Column {
                            width: inspector.width
                            visible: inspectorTab === 1

                            PropertySection {
                                width: parent.width
                                title: "描边"
                                summary: "1 px"
                                InspectorRow {
                                    label: "启用"
                                    BodyLabel { text: "细节描边"; Layout.fillWidth: true }
                                    ToggleSwitch { checked: true }
                                }
                                InspectorRow {
                                    label: "宽度"
                                    ValueBox { text: "1"; suffix: "px"; Layout.fillWidth: true }
                                }
                            }
                            PropertySection {
                                width: parent.width
                                title: "颜色叠加"
                                summary: "关闭"
                                expanded: false
                            }
                            PropertySection {
                                width: parent.width
                                title: "渐变叠加"
                                summary: "线性"
                                expanded: false
                            }
                            PropertySection {
                                width: parent.width
                                title: "圆角"
                                summary: "0 px"
                                expanded: false
                            }
                        }
                    }
                }

                Divider { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.left: parent.left }
            }
        }

        Rectangle {
            id: statusBar
            Layout.fillWidth: true
            Layout.preferredHeight: 28
            color: Theme.bgBar

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 12
                anchors.rightMargin: 12
                spacing: 12

                Row {
                    spacing: 6
                    Rectangle { width: 6; height: 6; radius: 3; color: Theme.success; anchors.verticalCenter: parent.verticalCenter }
                    TinyLabel { text: "就绪"; color: Theme.textSecondary; height: 28 }
                }
                Divider { Layout.preferredHeight: 14 }
                TinyLabel { text: "RGB / sRGB IEC61966-2.1"; height: 28 }
                Divider { Layout.preferredHeight: 14 }
                TinyLabel { text: "X 34  ·  Y 475"; height: 28 }

                Item { Layout.fillWidth: true }

                Row {
                    spacing: 5
                    IconButton {
                        glyph: "\uE738"; tooltip: "缩小"; buttonSize: 24
                        onClicked: zoomValue = Math.max(0.35, zoomValue - 0.05)
                    }
                    Rectangle {
                        width: 92
                        height: 4
                        anchors.verticalCenter: parent.verticalCenter
                        radius: 2
                        color: Theme.borderStrong
                        Rectangle { width: parent.width * ((zoomValue - 0.35) / 1.65); height: 4; radius: 2; color: Theme.accent }
                        Rectangle { x: parent.width * ((zoomValue - 0.35) / 1.65) - 6; anchors.verticalCenter: parent.verticalCenter; width: 12; height: 12; radius: 6; color: Theme.textPrimary; border.width: 2; border.color: Theme.accentPressed }
                    }
                    IconButton {
                        glyph: "\uE8A3"; tooltip: "放大"; buttonSize: 24
                        onClicked: zoomValue = Math.min(2.0, zoomValue + 0.05)
                    }
                    TinyLabel { width: 42; text: Math.round(zoomValue * 100) + "%"; color: Theme.textSecondary; height: 28; horizontalAlignment: Text.AlignRight }
                }
            }

            Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top }
        }
    }
}
