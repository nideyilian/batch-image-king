import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Qt5Compat.GraphicalEffects
import "."

// 预设工作台（三栏）：左侧导航 / 中间卡片网格 / 右侧检查器。
//
// 设计依据（见 docs/preset-workbench-design.md）：
// - Figma 文件浏览器的「最近 / 星标」侧栏 + 缩略图卡片
// - Canva 首页的筛选 + 排序 + 网格/列表双视图
// - Eagle 素材库的中央尺寸滑杆与悬停操作
// - 稿定「批量套版」把「替换项」直接暴露在卡片上
//
// 刻意不做的事：不加圆角、不加卡片阴影、不用底纹分区——
// 与本项目 Hermes 设计系统（radius 全 0）保持一致。

Item {
    id: root
    objectName: "presetWorkbench"

    // ---- 对外接口 ----
    property var vm: null                 // PresetManagerViewModel
    property bool busy: false
    signal requestClose()
    signal requestLoad(string presetId)
    signal requestDuplicate(string presetId)
    signal requestExport(string presetId, string presetName)
    signal requestDelete(string presetId, string presetName)
    signal requestBatchCreate(string presetId)
    signal requestToast(string message)

    // ---- 本地 UI 状态 ----
    property string navScope: "all"       // all / recent / favorite
    property string activeCategory: ""
    property string viewMode: "grid"      // grid / list
    property int cardSize: 208             // 卡片宽度（尺寸滑杆）
    readonly property int cardGap: 14
    // cardSize 是「期望卡片宽度」，不直接当 cellWidth 用。
    // 若直接写死 cellWidth=cardSize，中间区域宽度除不尽时会露出半张残卡
    // （实测 1600 宽、右栏展开时最后一列被切掉一半）。
    // 正确做法：先按期望宽度算出列数，再把宽度均分给这些列。
    readonly property int columns: {
        var available = Math.max(1, gridArea.width - 32)  // 左右各 16 边距
        var fit = Math.floor(available / cardSize)
        return Math.max(1, fit)
    }
    readonly property int cellWidth: columns > 0
                                     ? Math.floor((Math.max(1, gridArea.width - 32)) / columns)
                                     : cardSize
    // 封面按 4:3 取高：电商主图多为 1:1 或 3:4，4:3 能让两者都不至于裁掉主体文字
    readonly property int coverHeight: Math.round((cellWidth - cardGap) * 0.72)
    // 卡片信息区高度：名称 + 元数据 + 常驻操作条（见 PresetCard 的同名注释）。
    // 这两个数必须同步改，否则网格行高与卡片实际高度不一致，列会错落。
    readonly property int infoHeight: 96
    readonly property int rowHeight: coverHeight + infoHeight + cardGap
    property string selectedId: ""
    // 拖拽重排状态：dragId 为空表示未在拖拽
    property string dragId: ""
    property int dragTargetIndex: -1
    readonly property bool manualSort: sortModeValue === "manual"
    property string sortModeValue: "recent"
    // 等待确认删除的分类名（空串表示没有待确认项）
    property string pendingDeleteCategory: ""
    property bool editorDirty: false
    property string editorName: ""
    property string editorDescription: ""

    readonly property var visibleItems: vm ? vm.visiblePresets : []
    readonly property int totalCount: vm ? vm.count : 0

    function presetById(presetId) {
        var items = visibleItems
        for (var i = 0; i < items.length; i++) {
            if (items[i].id === presetId) return items[i]
        }
        return null
    }

    function selectPreset(presetId) {
        selectedId = presetId
        var item = presetById(presetId)
        editorName = item ? item.name : ""
        editorDescription = item ? item.description : ""
        editorDirty = false
    }

    // 供 --select-preset 调试入口与测试调用：写这个属性即按可见顺序选中第 N 张卡片。
    // 用属性而非函数，是因为 QML 根对象的普通 function 不一定暴露给
    // QMetaObject.invokeMethod，而属性读写一定可用。
    property int selectPresetIndex: -1
    onSelectPresetIndexChanged: {
        if (selectPresetIndex < 0) return
        var items = visibleItems
        if (selectPresetIndex < items.length)
            selectPreset(items[selectPresetIndex].id)
    }

    function clearSelection() {
        selectedId = ""
        editorName = ""
        editorDescription = ""
        editorDirty = false
    }

    function applyScope(scope) {
        navScope = scope
        activeCategory = ""
        clearSelection()
        if (vm) {
            vm.setScope(scope)
            vm.setCategory("")
        }
    }

    function applyCategory(name) {
        activeCategory = name
        navScope = "all"
        clearSelection()
        if (vm) {
            vm.setScope("all")
            vm.setCategory(name)
        }
    }

    function requestAllThumbnails() {
        if (!vm) return
        // 后台串行生成，主线程不阻塞；每完成一张通过 thumbnailReady 刷新单卡
        vm.requestAllThumbnails()
    }

    Component.onCompleted: {
        if (vm) {
            vm.setScope(navScope)
            vm.setCategory("")
        }
        // 首次进入不主动全量预取：GridView / ListView 的 delegate 会各自
        // 在创建时请求自己那张缩略图（见 delegate 内的 Component.onCompleted）。
    }

    Connections {
        target: root.vm
        function onThumbnailReady(presetId) {
            // 触发 visiblePresets 重算即可，绑定会自动刷新对应卡片
            thumbnailTick++
        }
    }

    // 用一个自增计数强制依赖 visiblePresets 的绑定重新求值
    property int thumbnailTick: 0

    Rectangle {
        anchors.fill: parent
        color: Theme.bgApp
    }

    ColumnLayout {
        anchors.fill: parent
        spacing: 0

        // ================= 顶部工具条 =================
        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: 56
            color: Theme.bgBar

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 16
                anchors.rightMargin: 12
                spacing: 10

                Item {
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                    AppIcon {
                        anchors.centerIn: parent
                        iconName: AppIcons.layers
                        iconSize: 18
                        iconColor: Theme.textPrimary
                    }
                }

                Text {
                    text: "预设工作台"
                    color: Theme.textPrimary
                    font.family: Theme.displayFont
                    font.pixelSize: 15
                    font.weight: Font.DemiBold
                }

                TinyLabel {
                    text: root.totalCount + " 个预设"
                    color: Theme.textMuted
                }

                Rectangle {
                    Layout.preferredWidth: 1
                    Layout.preferredHeight: 18
                    color: Theme.border
                }

                // 搜索
                Rectangle {
                    Layout.preferredWidth: 240
                    Layout.preferredHeight: 32
                    color: Theme.bgControl
                    border.width: 1
                    border.color: searchField.activeFocus ? Theme.accent : Theme.borderStrong

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 8
                        anchors.rightMargin: 8
                        spacing: 6
                        AppIcon {
                            iconName: AppIcons.search
                            iconSize: 14
                            iconColor: Theme.textMuted
                        }
                        AppTextField {
                            id: searchField
                            Layout.fillWidth: true
                            controlSize: "sm"
                            placeholderText: "搜索名称、描述、标签"
                            color: Theme.textPrimary
                            selectByMouse: true
                            background: Item {}
                            onTextChanged: if (root.vm) root.vm.setSearchText(text)
                        }
                        IconButton {
                            visible: searchField.text.length > 0
                            iconName: AppIcons.close
                            iconSize: 12
                            buttonSize: 20
                            tooltip: "清除搜索"
                            onClicked: {
                                searchField.text = ""
                                if (root.vm) root.vm.setSearchText("")
                            }
                        }
                    }
                }

                Item { Layout.fillWidth: true }

                // 排序下拉
                SelectBox {
                    id: sortBox
                    Layout.preferredWidth: 116
                    Layout.preferredHeight: 30
                    controlSize: "sm"
                    model: [
                        { label: "手动排序", value: "manual" },
                        { label: "最近使用", value: "recent" },
                        { label: "最近创建", value: "created" },
                        { label: "名称 A→Z", value: "name" },
                        { label: "图层最多", value: "layers" },
                        { label: "使用次数", value: "used" }
                    ]
                    textRole: "label"
                    valueRole: "value"
                    currentIndex: 0
                    onActivated: index => {
                        root.sortModeValue = currentValue
                        if (root.vm) root.vm.setSortMode(currentValue)
                    }
                }

                // 尺寸滑杆（Eagle 做法：中置尺寸控制）
                RowLayout {
                    spacing: 6
                    visible: root.viewMode === "grid"
                    AppIcon {
                        iconName: AppIcons.sliders
                        iconSize: 14
                        iconColor: Theme.textMuted
                    }
                    CardSizeSlider {
                        Layout.preferredWidth: 92
                        Layout.preferredHeight: 20
                    }
                }

                // 网格 / 列表切换
                SegmentedControl {
                    Layout.preferredHeight: 30
                    accessibleName: "视图模式"
                    options: [
                        { label: "网格", value: "grid" },
                        { label: "列表", value: "list" }
                    ]
                    value: root.viewMode
                    onActivated: value => root.viewMode = value
                }

                IconButton {
                    iconName: AppIcons.add
                    tooltip: "保存当前文档为预设"
                    buttonSize: 32
                    enabled: !root.busy
                    onClicked: root.requestSaveNew()
                }

                IconButton {
                    iconName: AppIcons.close
                    tooltip: "返回编辑器（Esc）"
                    buttonSize: 32
                    onClicked: root.requestClose()
                }
            }

            Rectangle {
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                height: 1
                color: Theme.border
            }
        }

        // ================= 三栏主体 =================
        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0

            // ---------- 左：导航 ----------
            Rectangle {
                Layout.preferredWidth: 208
                Layout.fillHeight: true
                color: Theme.bgBar

                ColumnLayout {
                    anchors.fill: parent
                    anchors.topMargin: 12
                    anchors.bottomMargin: 12
                    spacing: 2

                    SidebarHeading {
                        Layout.leftMargin: 14
                        Layout.bottomMargin: 6
                        label: "预设库"
                    }

                    NavRow {
                        Layout.fillWidth: true
                        label: "全部预设"
                        iconName: AppIcons.layers
                        count: root.totalCount
                        active: root.navScope === "all" && root.activeCategory === ""
                        onClicked: root.applyScope("all")
                    }
                    NavRow {
                        Layout.fillWidth: true
                        label: "最近使用"
                        iconName: AppIcons.history
                        count: root.vm ? root.vm.recentCount : 0
                        active: root.navScope === "recent"
                        onClicked: root.applyScope("recent")
                    }
                    NavRow {
                        Layout.fillWidth: true
                        label: "收藏"
                        iconName: AppIcons.bookmark
                        count: root.vm ? root.vm.favoriteCount : 0
                        active: root.navScope === "favorite"
                        onClicked: root.applyScope("favorite")
                    }

                    Item { Layout.preferredHeight: 10 }

                    SidebarHeading {
                        Layout.leftMargin: 14
                        Layout.bottomMargin: 6
                        label: "分类"
                    }

                    Flickable {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        contentHeight: categoryColumn.implicitHeight
                        boundsBehavior: Flickable.StopAtBounds

                        Column {
                            id: categoryColumn
                            width: parent.width
                            spacing: 2

                            Repeater {
                                model: root.vm ? root.vm.categories : []
                                delegate: NavRow {
                                    required property var modelData
                                    width: parent.width
                                    label: modelData.name
                                    iconName: AppIcons.folder
                                    count: modelData.count
                                    active: root.activeCategory === modelData.name
                                    indent: true
                                    // 「未分类」是兜底桶，不能删
                                    deletable: modelData.name !== "未分类"
                                    onClicked: root.applyCategory(modelData.name)
                                    onDeleteRequested: root.pendingDeleteCategory = modelData.name
                                }
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        Layout.topMargin: 8
                        Layout.bottomMargin: 8
                        color: Theme.border
                    }

                    // 新建分类：输入名称后把它作为「当前分类」。
                    // 分类本身没有独立实体，只存在于预设的 category 字段上，
                    // 所以「新建」= 先把一个空分类置为当前筛选，用户随后把预设拖进来
                    // 或改用检查器归类。这样避免维护一张可能悬空的分类表。
                    RowLayout {
                        Layout.fillWidth: true
                        Layout.leftMargin: 10
                        Layout.rightMargin: 10
                        spacing: 4
                        visible: root.vm !== null

                        AppTextField {
                            id: newCategoryField
                            Layout.fillWidth: true
                            controlSize: "sm"
                            placeholderText: "新建分类…"
                            color: Theme.textPrimary
                            selectByMouse: true
                            onAccepted: newCategoryApply.applyNow()
                        }
                        IconButton {
                            id: newCategoryApply
                            iconName: AppIcons.add
                            buttonSize: 26
                            tooltip: "新建分类并筛选"
                            function applyNow() {
                                var name = newCategoryField.text.trim()
                                if (name.length === 0) return
                                newCategoryField.text = ""
                                // 已存在的分类直接切换过去，不重复建
                                root.applyCategory(name)
                                root.requestToast("已筛选到分类「" + name + "」")
                            }
                            onClicked: applyNow()
                        }
                    }

                    TinyLabel {
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: "分类与标签在右侧检查器中编辑"
                        color: Theme.textMuted
                    }
                }

                Rectangle {
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 1
                    color: Theme.border
                }
            }

            // ---------- 中：卡片区 ----------
            Item {
                id: gridArea
                Layout.fillWidth: true
                Layout.fillHeight: true

                // 空态
                Column {
                    anchors.centerIn: parent
                    spacing: 8
                    visible: root.visibleItems.length === 0
                    AppIcon {
                        anchors.horizontalCenter: parent.horizontalCenter
                        iconName: AppIcons.layers
                        iconSize: 40
                        iconColor: Theme.textMuted
                    }
                    BodyLabel {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: root.totalCount === 0 ? "还没有预设" : "没有匹配的预设"
                        color: Theme.textPrimary
                    }
                    TinyLabel {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: root.totalCount === 0
                              ? "在编辑器里点「保存为预设」，或从右侧检查器导入已有预设"
                              : "试试换个搜索词，或切回「全部预设」"
                        color: Theme.textMuted
                    }
                }

                // 网格视图
                GridView {
                    id: grid
                    anchors.fill: parent
                    anchors.margins: 16
                    visible: root.viewMode === "grid" && root.visibleItems.length > 0
                    clip: true
                    cellWidth: root.cellWidth
                    cellHeight: root.rowHeight
                    boundsBehavior: Flickable.StopAtBounds
                    model: root.visibleItems

                    delegate: PresetCard {
                        width: grid.cellWidth - root.cardGap
                        height: grid.cellHeight - root.cardGap
                        presetData: modelData
                        selected: root.selectedId === modelData.id
                        thumbTick: root.thumbnailTick
                        onActivated: root.selectPreset(modelData.id)
                        onLoadRequested: root.requestLoad(modelData.id)
                        onBatchRequested: root.requestBatchCreate(modelData.id)
                        onFavoriteToggled: root.vm ? root.vm.toggleFavorite(modelData.id) : false
                        onDuplicateRequested: root.requestDuplicate(modelData.id)
                        onExportRequested: root.requestExport(modelData.id, modelData.name)
                        onDeleteRequested: root.requestDelete(modelData.id, modelData.name)
                        // 懒加载：只有真正进入视口的卡片才请求缩略图，
                        // 避免一进工作台就排 14 个渲染任务、把首屏拖慢。
                        Component.onCompleted: {
                            if (!modelData.thumbnailUrl && root.vm)
                                root.vm.requestThumbnail(modelData.id)
                        }

                        // ---- 拖拽重排 ----
                        // 只在「手动排序」下启用：其它排序模式拖完会被排序规则
                        // 立即覆盖，看起来像"拖了没反应"，比不给拖更让人困惑。
                        dragEnabled: root.manualSort
                        dragging: root.dragId === modelData.id
                        dropTarget: root.dragId.length > 0 && root.dragId !== modelData.id
                                  && root.dragTargetIndex === index

                        Drag.active: root.dragId === modelData.id
                        Drag.source: cardDragArea
                        Drag.hotSpot.x: width / 2
                        Drag.hotSpot.y: height / 2

                        // 拖拽插入位置指示：目标卡片左侧画一条竖线
                        Rectangle {
                            anchors.left: parent.left
                            anchors.verticalCenter: parent.verticalCenter
                            width: 2
                            height: parent.height
                            color: Theme.accent
                            visible: root.dragId.length > 0 && root.dragTargetIndex === index
                                     && root.dragId !== modelData.id
                            z: 10
                        }

                        MouseArea {
                            id: cardDragArea
                            anchors.fill: parent
                            enabled: root.manualSort
                            // 只吃拖拽，不吃点击——点击仍交给 PresetCard 内部的 MouseArea
                            propagateComposedEvents: true
                            drag.target: root.manualSort ? parent : null
                            drag.threshold: 8
                            cursorShape: root.manualSort ? Qt.OpenHandCursor : Qt.ArrowCursor

                            onPressed: function(mouse) {
                                mouse.accepted = false
                            }
                            onPositionChanged: {
                                if (!root.manualSort || !pressed) return
                                if (root.dragId.length === 0) root.dragId = modelData.id
                                var gp = mapToItem(grid, mouse.x, mouse.y)
                                var row = Math.floor((gp.y + grid.contentY) / grid.cellHeight)
                                var col = Math.floor(gp.x / grid.cellWidth)
                                var cols = Math.max(1, Math.floor(grid.width / grid.cellWidth))
                                var target = row * cols + col
                                root.dragTargetIndex = Math.max(0, Math.min(grid.count - 1, target))
                            }
                            onReleased: {
                                if (root.dragId.length > 0 && root.dragTargetIndex >= 0) {
                                    if (root.vm) root.vm.movePreset(root.dragId, root.dragTargetIndex)
                                }
                                root.dragId = ""
                                root.dragTargetIndex = -1
                            }
                            onCanceled: {
                                root.dragId = ""
                                root.dragTargetIndex = -1
                            }
                        }
                    }
                }

                // 列表视图
                ListView {
                    id: listView
                    anchors.fill: parent
                    anchors.margins: 16
                    visible: root.viewMode === "list" && root.visibleItems.length > 0
                    clip: true
                    spacing: 2
                    boundsBehavior: Flickable.StopAtBounds
                    model: root.visibleItems

                    delegate: PresetListRow {
                        width: listView.width
                        presetData: modelData
                        selected: root.selectedId === modelData.id
                        thumbTick: root.thumbnailTick
                        onActivated: root.selectPreset(modelData.id)
                        onLoadRequested: root.requestLoad(modelData.id)
                        onFavoriteToggled: root.vm ? root.vm.toggleFavorite(modelData.id) : false
                        Component.onCompleted: {
                            if (!modelData.thumbnailUrl && root.vm)
                                root.vm.requestThumbnail(modelData.id)
                        }

                        // 拖拽重排（仅手动排序模式）
                        dropTarget: root.dragId.length > 0 && root.dragId !== modelData.id
                                    && root.dragTargetIndex === index

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            height: 2
                            color: Theme.accent
                            visible: root.dragId.length > 0 && root.dragTargetIndex === index
                                     && root.dragId !== modelData.id
                            z: 10
                        }

                        MouseArea {
                            id: rowDragArea
                            anchors.fill: parent
                            enabled: root.manualSort
                            propagateComposedEvents: true
                            cursorShape: root.manualSort ? Qt.OpenHandCursor : Qt.ArrowCursor
                            drag.target: root.manualSort ? parent : null
                            drag.threshold: 8

                            onPressed: function(mouse) { mouse.accepted = false }
                            onPositionChanged: {
                                if (!root.manualSort || !pressed) return
                                if (root.dragId.length === 0) root.dragId = modelData.id
                                var gp = mapToItem(listView, mouse.x, mouse.y)
                                var target = Math.floor((gp.y + listView.contentY) / (listView.spacing + height))
                                root.dragTargetIndex = Math.max(0, Math.min(listView.count - 1, target))
                            }
                            onReleased: {
                                if (root.dragId.length > 0 && root.dragTargetIndex >= 0) {
                                    if (root.vm) root.vm.movePreset(root.dragId, root.dragTargetIndex)
                                }
                                root.dragId = ""
                                root.dragTargetIndex = -1
                            }
                            onCanceled: {
                                root.dragId = ""
                                root.dragTargetIndex = -1
                            }
                        }
                    }
                }
            }

            // ---------- 右：检查器 ----------
            Rectangle {
                Layout.preferredWidth: 300
                Layout.fillHeight: true
                color: Theme.bgBar
                visible: root.selectedId.length > 0

                Rectangle {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    width: 1
                    color: Theme.border
                }

                ColumnLayout {
                    anchors.fill: parent
                    anchors.margins: 16
                    spacing: 12

                    RowLayout {
                        Layout.fillWidth: true
                        Text {
                            Layout.fillWidth: true
                            text: "预设详情"
                            color: Theme.textPrimary
                            font.family: Theme.displayFont
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        IconButton {
                            iconName: AppIcons.close
                            buttonSize: 26
                            tooltip: "收起检查器"
                            onClicked: root.clearSelection()
                        }
                    }

                    // 大预览
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 168
                        color: Theme.bgCanvas
                        border.width: 1
                        border.color: Theme.border

                        Image {
                            id: inspectorImage
                            anchors.fill: parent
                            anchors.margins: 1
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            cache: false
                            source: {
                                var tick = root.thumbnailTick
                                var item = root.presetById(root.selectedId)
                                return item ? item.thumbnailUrl : ""
                            }
                        }

                        Column {
                            anchors.centerIn: parent
                            spacing: 4
                            visible: inspectorImage.status !== Image.Ready
                            AppIcon {
                                anchors.horizontalCenter: parent.horizontalCenter
                                iconName: AppIcons.loaderCircle
                                iconSize: 20
                                iconColor: Theme.textMuted
                            }
                            TinyLabel {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "生成预览中…"
                            }
                        }
                    }

                    // 名称
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        TinyLabel { text: "名称" }
                        AppTextField {
                            Layout.fillWidth: true
                            controlSize: "sm"
                            text: root.editorName
                            color: Theme.textPrimary
                            selectByMouse: true
                            onTextEdited: {
                                root.editorName = text
                                root.editorDirty = true
                            }
                        }
                    }

                    // 描述
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        TinyLabel { text: "描述" }
                        AppTextField {
                            Layout.fillWidth: true
                            controlSize: "sm"
                            text: root.editorDescription
                            placeholderText: "可选"
                            color: Theme.textPrimary
                            selectByMouse: true
                            onTextEdited: {
                                root.editorDescription = text
                                root.editorDirty = true
                            }
                        }
                    }

                    // 元数据
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 6

                        MetaRow {
                            label: "画布"
                            value: {
                                var item = root.presetById(root.selectedId)
                                return item && item.canvasSizes.length > 0
                                        ? item.canvasSizes.join(" / ") : "—"
                            }
                        }
                        MetaRow {
                            label: "图层"
                            value: {
                                var item = root.presetById(root.selectedId)
                                return item ? (item.totalLayers + " 层") : "—"
                            }
                        }
                        MetaRow {
                            label: "标签页"
                            value: {
                                var item = root.presetById(root.selectedId)
                                return item ? (item.documentCount + " 个") : "—"
                            }
                        }
                        MetaRow {
                            label: "使用"
                            value: {
                                var item = root.presetById(root.selectedId)
                                if (!item || item.runCount === 0) return "未使用"
                                return item.runCount + " 次"
                            }
                        }
                        MetaRow {
                            label: "最近"
                            value: {
                                var item = root.presetById(root.selectedId)
                                if (!item || !item.lastUsedAt) return "—"
                                return item.lastUsedAt.substring(0, 10)
                            }
                        }
                    }

                    // ---- 分类与标签（可编辑）----
                    // 放在只读元数据之下：浏览时不需要它们，整理时才用，
                    // 符合「渐进呈现复杂度」原则。
                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 1
                        Layout.topMargin: 2
                        color: Theme.border
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        TinyLabel { text: "分类" }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            AppTextField {
                                id: categoryField
                                Layout.fillWidth: true
                                controlSize: "sm"
                                placeholderText: "未分类"
                                text: {
                                    var tick = root.thumbnailTick
                                    var item = root.presetById(root.selectedId)
                                    return item ? item.category : ""
                                }
                                color: Theme.textPrimary
                                selectByMouse: true
                                onAccepted: categoryApply.applyNow()
                            }
                            IconButton {
                                id: categoryApply
                                iconName: AppIcons.check
                                buttonSize: 28
                                tooltip: "应用分类"
                                enabled: categoryField.text.length > 0
                                function applyNow() {
                                    if (!root.vm || root.selectedId.length === 0) return
                                    if (root.vm.setPresetCategory(root.selectedId,
                                                                  categoryField.text.trim()))
                                        root.requestToast("分类已更新")
                                }
                                onClicked: applyNow()
                            }
                        }
                        // 已有分类快速切换：点一下即归类，不用手打
                        Flow {
                            Layout.fillWidth: true
                            spacing: 4
                            visible: root.vm && root.vm.categories.length > 1

                            Repeater {
                                model: root.vm ? root.vm.categories : []
                                delegate: Rectangle {
                                    required property var modelData
                                    readonly property bool current: {
                                        var item = root.presetById(root.selectedId)
                                        return item && item.category === modelData.name
                                    }
                                    implicitWidth: chipText.implicitWidth + 14
                                    implicitHeight: 20
                                    color: current ? Theme.accentSoft
                                                   : (chipMouse.containsMouse ? Theme.bgHover : "transparent")
                                    border.width: 1
                                    border.color: current ? Theme.accent : Theme.border

                                    Text {
                                        id: chipText
                                        anchors.centerIn: parent
                                        text: modelData.name
                                        color: current ? Theme.textPrimary : Theme.textMuted
                                        font.family: Theme.bodyFont
                                        font.pixelSize: 10
                                    }
                                    MouseArea {
                                        id: chipMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            if (!root.vm) return
                                            root.vm.setPresetCategory(root.selectedId, modelData.name)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ---- 封面选择（仅多标签预设）----
                    // 单文档预设没有可选项，不显示这块，避免占位浪费。
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: {
                            var item = root.presetById(root.selectedId)
                            return item && item.coverCandidates && item.coverCandidates.length > 1
                        }
                        TinyLabel { text: "卡片封面" }
                        Flow {
                            Layout.fillWidth: true
                            spacing: 4
                            Repeater {
                                model: {
                                    var item = root.presetById(root.selectedId)
                                    return item && item.coverCandidates ? item.coverCandidates : []
                                }
                                delegate: Rectangle {
                                    required property var modelData
                                    readonly property bool current: {
                                        var item = root.presetById(root.selectedId)
                                        return item && item.coverIndex === modelData.index
                                    }
                                    implicitWidth: coverText.implicitWidth + 14
                                    implicitHeight: 20
                                    color: current ? Theme.accent
                                                   : (coverMouse.containsMouse ? Theme.bgHover : "transparent")
                                    border.width: 1
                                    border.color: current ? Theme.accent : Theme.border
                                    Text {
                                        id: coverText
                                        anchors.centerIn: parent
                                        text: "第 " + (modelData.index + 1) + " 页"
                                        color: current ? Theme.accentForeground : Theme.textMuted
                                        font.family: Theme.bodyFont
                                        font.pixelSize: 10
                                    }
                                    MouseArea {
                                        id: coverMouse
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            if (!root.vm) return
                                            if (root.vm.setCoverDocument(root.selectedId, modelData.index))
                                                root.requestToast("封面已切换为第 " + (modelData.index + 1) + " 页")
                                        }
                                    }
                                }
                            }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        TinyLabel { text: "标签（逗号分隔）" }
                        AppTextField {
                            id: tagsField
                            Layout.fillWidth: true
                            controlSize: "sm"
                            placeholderText: "如：主图, 夏季, 女装"
                            text: {
                                var tick = root.thumbnailTick
                                var item = root.presetById(root.selectedId)
                                return item ? item.tags.join(", ") : ""
                            }
                            color: Theme.textPrimary
                            selectByMouse: true
                            onAccepted: tagsApply.applyNow()
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            Item { Layout.fillWidth: true }
                            IconButton {
                                id: tagsApply
                                iconName: AppIcons.check
                                buttonSize: 24
                                tooltip: "保存标签"
                                function applyNow() {
                                    if (!root.vm || root.selectedId.length === 0) return
                                    if (root.vm.setPresetTags(root.selectedId, tagsField.text))
                                        root.requestToast("标签已保存")
                                }
                                onClicked: applyNow()
                            }
                        }
                    }

                    Item { Layout.fillHeight: true }

                    TinyLabel {
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: root.vm && root.vm.lastError.length > 0 ? root.vm.lastError : ""
                        color: Theme.danger
                        visible: text.length > 0
                    }

                    AppButton {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        text: root.editorDirty ? "保存修改" : "修改已保存"
                        enabled: root.editorDirty && root.editorName.length > 0
                        onClicked: {
                            if (root.vm.renamePreset(root.selectedId, root.editorName, root.editorDescription)) {
                                root.editorDirty = false
                                root.selectPreset(root.selectedId)
                            }
                        }
                    }

                    // 次入口：卡片上的「打开」已经是一步直达的主入口，
                    // 这里保留一份是为了"先看清楚再打开"的场景（比如逐页翻封面）。
                    // 所以不再用 primary 样式抢主视觉。
                    AppButton {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        text: "在编辑器中打开"
                        onClicked: root.requestLoad(root.selectedId)
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        IconButton {
                            iconName: AppIcons.copy
                            buttonSize: 32
                            tooltip: "复制预设"
                            onClicked: root.requestDuplicate(root.selectedId)
                        }
                        IconButton {
                            iconName: AppIcons.folderOutput
                            buttonSize: 32
                            tooltip: "导出预设"
                            onClicked: {
                                var item = root.presetById(root.selectedId)
                                root.requestExport(root.selectedId, item ? item.name : "")
                            }
                        }
                        IconButton {
                            iconName: AppIcons.trash
                            buttonSize: 32
                            destructive: true
                            tooltip: "删除预设"
                            onClicked: {
                                var item = root.presetById(root.selectedId)
                                root.requestDelete(root.selectedId, item ? item.name : "")
                            }
                        }
                        Item { Layout.fillWidth: true }
                    }
                }
            }
        }
    }

    // 供外部触发的保存入口（顶部 + 按钮）
    signal requestSaveNew()

    // ============ 内部小组件 ============

    // 删除分类确认：分类删掉只是把成员归回「未分类」，不删任何预设，
    // 但仍要确认一次——用户可能只是想改名。
    AppDialog {
        id: deleteCategoryConfirm
        width: 400
        modal: true
        closePolicy: Popup.CloseOnEscape
        title: "删除分类？"
        visible: root.pendingDeleteCategory.length > 0

        ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            BodyLabel {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                color: Theme.textPrimary
                text: "「" + root.pendingDeleteCategory + "」下的预设会归回「未分类」，预设本身不会被删除。"
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton {
                    Layout.preferredWidth: 88
                    label: "取消"
                    onClicked: root.pendingDeleteCategory = ""
                }
                ExportButton {
                    Layout.preferredWidth: 88
                    label: "删除分类"
                    primary: true
                    onClicked: {
                        var affected = root.vm ? root.vm.deleteCategory(root.pendingDeleteCategory) : 0
                        root.pendingDeleteCategory = ""
                        if (affected > 0)
                            root.requestToast(affected + " 个预设已归入「未分类」")
                    }
                }
            }
        }
    }

    // 卡片尺寸滑杆：自绘而非原生 Slider。
    // 原生 Slider 在当前 Qt 样式下会报 "does not support customization of
    // property handle"，且轨道颜色不跟主题走。
    component CardSizeSlider: Item {
        id: sizeSlider
        implicitHeight: 20

        readonly property real ratio: (root.cardSize - 150) / (300 - 150)

        Rectangle {
            id: track
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            anchors.right: parent.right
            height: 2
            color: Theme.borderStrong
        }

        Rectangle {
            anchors.verticalCenter: parent.verticalCenter
            anchors.left: parent.left
            width: Math.max(0, track.width * sizeSlider.ratio)
            height: 2
            color: Theme.accent
        }

        Rectangle {
            id: knob
            width: 10
            height: 10
            anchors.verticalCenter: parent.verticalCenter
            x: Math.max(0, Math.min(track.width - width,
                                    track.width * sizeSlider.ratio - width / 2))
            color: Theme.accent
            border.width: 1
            border.color: Theme.bgBar

            Rectangle {
                anchors.centerIn: parent
                width: 4
                height: 4
                color: Theme.accentForeground
                visible: sliderMouse.containsMouse || sliderMouse.pressed
            }
        }

        MouseArea {
            id: sliderMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.SizeHorCursor
            preventStealing: true
            function applyAt(x) {
                var clamped = Math.max(0, Math.min(track.width, x))
                var value = 150 + (clamped / Math.max(1, track.width)) * (300 - 150)
                // 对齐到 10px 档，网格列宽只在离散值下才整齐
                root.cardSize = Math.round(value / 10) * 10
            }
            onPressed: mouse => applyAt(mouse.x)
            onPositionChanged: mouse => { if (pressed) applyAt(mouse.x) }
            onWheel: wheel => {
                root.cardSize = Math.max(150, Math.min(300,
                    root.cardSize + (wheel.angleDelta.y > 0 ? 10 : -10)))
            }
        }
    }

    component SidebarHeading: Text {
        property string label: ""
        text: label
        color: Theme.textMuted
        font.family: Theme.dataFont
        font.pixelSize: 10
        font.weight: Font.DemiBold
        font.letterSpacing: 0.6
    }

    component NavRow: Rectangle {
        id: navRow
        property string label: ""
        property string iconName: ""
        property int count: -1
        property bool active: false
        property bool indent: false
        // 只有分类行可删；「未分类」是兜底桶，不能删
        property bool deletable: false
        signal clicked()
        signal deleteRequested()

        implicitHeight: 30
        color: active ? Theme.bgSelected : (navMouse.containsMouse ? Theme.bgHover : "transparent")

        RowLayout {
            anchors.fill: parent
            anchors.leftMargin: indent ? 22 : 14
            anchors.rightMargin: 12
            spacing: 8
            AppIcon {
                iconName: navRow.iconName
                iconSize: 14
                iconColor: navRow.active ? Theme.textPrimary : Theme.textSecondary
            }
            Text {
                Layout.fillWidth: true
                text: navRow.label
                color: navRow.active ? Theme.textPrimary : Theme.textSecondary
                font.family: Theme.bodyFont
                font.pixelSize: 12
                font.weight: navRow.active ? Font.DemiBold : Font.Normal
                elide: Text.ElideRight
            }
            Text {
                visible: navRow.count >= 0 && !(navRow.deletable && (navMouse.containsMouse || navRow.active))
                text: navRow.count
                color: Theme.textMuted
                font.family: Theme.dataFont
                font.pixelSize: 10
                // 必须显式给宽度：RowLayout 会优先压缩没有宽度约束的子项，
                // 否则计数会被 fillWidth 的标签挤成 "1"。
                Layout.preferredWidth: 22
                horizontalAlignment: Text.AlignRight
            }

            // 删除分类：默认藏起来，悬停/选中才露出，避免侧栏一片叉号。
            // 用 Item 占位保证不悬停时行宽不跳。
            Item {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                visible: navRow.deletable && (navMouse.containsMouse || navRow.active)

                AppIcon {
                    anchors.centerIn: parent
                    iconName: AppIcons.trash
                    iconSize: 12
                    iconColor: delMouse.containsMouse ? Theme.danger : Theme.textMuted
                }
                MouseArea {
                    id: delMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: navRow.deleteRequested()
                }
            }
        }

        MouseArea {
            id: navMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: navRow.clicked()
        }

        // 选中态左侧竖线（Hermes 风格：用线不用色块）
        Rectangle {
            width: 2
            height: parent.height
            anchors.left: parent.left
            color: Theme.accent
            visible: navRow.active
        }
    }

    component MetaRow: RowLayout {
        property string label: ""
        property string value: ""
        Layout.fillWidth: true
        spacing: 8
        TinyLabel {
            text: label
            Layout.preferredWidth: 44
        }
        BodyLabel {
            Layout.fillWidth: true
            text: value
            color: Theme.textPrimary
            elide: Text.ElideRight
        }
    }
}
