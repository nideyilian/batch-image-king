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
    // 正在重命名的分类名（空串表示没有）
    property string pendingRenameCategory: ""
    property bool editorDirty: false
    property string editorName: ""
    property string editorDescription: ""

    // ---- 标签页（页列表）状态 ----
    // 当前处于编辑态的页下标，-1 表示没有。同一时刻只允许一页在编辑：
    // 切到另一页时前一页按「失焦=提交」处理。
    property int editingTabIndex: -1
    // 编辑态的草稿文本（与输入框双向同步）
    property string editingTabDraft: ""
    // 编辑态的错误提示
    property string tabRenameError: ""
    // 行尾 ⋮ 菜单作用的页下标
    property int contextTabIndex: -1
    // 「清空全部」的待确认预设 id（空串表示没有待确认项）
    property string pendingClearTabsId: ""
    // 镜像「同时关闭工作区」开关状态（可读写）。
    //
    // 为什么要有这个镜像：Popup 是独立窗口，不在 item 树里，外部（含自动化
    // 测试）既 findChild 不到对话框，也读不到它内部的 alsoCloseWorkspace。
    // 上一轮就是因为这条链路无法验证，把「勾了也等于没勾」的缺陷漏了出去。
    // 真值仍在 clearTabsDialog 里，这里双向同步。
    property bool alsoCloseWorkspaceOnClear: false
    onAlsoCloseWorkspaceOnClearChanged: {
        if (clearTabsDialog.alsoCloseWorkspace !== alsoCloseWorkspaceOnClear)
            clearTabsDialog.alsoCloseWorkspace = alsoCloseWorkspaceOnClear
    }
    // 「关闭本页」的待确认页下标，-1 表示没有
    property int pendingCloseTabIndex: -1
    // 卡片右键菜单作用的目标预设 id（空串表示菜单未打开）
    property string contextMenuPresetId: ""

    // ---- 外部/调试驱动入口 ----
    // QML 根对象上的普通 function 无法被 QMetaObject.invokeMethod 找到（实测），
    // 所以暴露几个可写属性作为桥：写属性即触发对应动作，测试与调试脚本用。
    // 这也是 qml_debug_entries 里 selectPresetIndex 的同一套路子。
    property int requestTabRenameIndex: -1
    onRequestTabRenameIndexChanged: {
        if (requestTabRenameIndex < 0) return
        var idx = requestTabRenameIndex
        requestTabRenameIndex = -1
        beginTabRename(idx)
    }
    property bool requestSubmitTabRename: false
    onRequestSubmitTabRenameChanged: {
        if (!requestSubmitTabRename) return
        requestSubmitTabRename = false
        submitTabRename()
    }
    property bool requestCancelTabRename: false
    onRequestCancelTabRenameChanged: {
        if (!requestCancelTabRename) return
        requestCancelTabRename = false
        cancelTabRename()
    }
    property bool requestClearTabsDialog: false
    onRequestClearTabsDialogChanged: {
        if (!requestClearTabsDialog) return
        requestClearTabsDialog = false
        requestClearAllTabs()
    }
    property bool requestConfirmClearTabs: false
    onRequestConfirmClearTabsChanged: {
        if (!requestConfirmClearTabs) return
        requestConfirmClearTabs = false
        // ⚠️ 不能写死 false：对话框里的「同时关闭工作区」开关必须传下去，
        // 否则用户勾了也等于没勾（卡片清空了，工作区标签页还在）。
        performClearAllTabs(clearTabsDialog.alsoCloseWorkspace)
    }
    // 供调试/自动化触发「保存改动回此预设」（QMetaObject 找不到普通 function）
    property bool requestSaveToPresetNow: false
    onRequestSaveToPresetNowChanged: {
        if (!requestSaveToPresetNow) return
        requestSaveToPresetNow = false
        requestSaveToPreset(selectedId)
    }
    property int requestCloseTabIndex: -1
    onRequestCloseTabIndexChanged: {
        if (requestCloseTabIndex < 0) return
        var idx = requestCloseTabIndex
        requestCloseTabIndex = -1
        requestCloseTab(idx)
    }
    property bool requestConfirmCloseTab: false
    onRequestConfirmCloseTabChanged: {
        if (!requestConfirmCloseTab) return
        requestConfirmCloseTab = false
        performCloseTab()
    }

    /// 进入某页的编辑态。原文预填并全选（参考 Figma 图层改名）。
    function beginTabRename(pageIndex) {
        if (!vm || selectedId.length === 0) return
        if (vm.busy) {
            requestToast(vm.busyReason || "正在处理其它操作，请稍候")
            return
        }
        var item = presetById(selectedId)
        if (!item || item.corrupt) return
        if (pageIndex < 0 || pageIndex >= item.tabTitles.length) return
        // 已有另一页在编辑：先提交它，再切过来
        if (editingTabIndex >= 0 && editingTabIndex !== pageIndex)
            submitTabRename()
        tabRenameError = ""
        editingTabDraft = item.tabTitles[pageIndex].title
        editingTabIndex = pageIndex
    }

    /// 提交改名。校验失败留在编辑态并显示红字；成功则退出编辑态。
    function submitTabRename() {
        if (!vm || editingTabIndex < 0) return
        var pageIndex = editingTabIndex
        var result = vm.renameDocument(selectedId, pageIndex, editingTabDraft)
        if (result && result.ok) {
            editingTabIndex = -1
            editingTabDraft = ""
            tabRenameError = ""
            if (result.changed)
                requestToast("已重命名为「" + result.title + "」")
            return
        }
        // 校验 / 写盘失败：保持编辑态，保留用户输入，红字提示
        tabRenameError = (result && result.message) || "重命名失败"
    }

    /// 取消改名（Esc）：还原原文，零写入。
    function cancelTabRename() {
        editingTabIndex = -1
        editingTabDraft = ""
        tabRenameError = ""
    }

    /// 打开「关闭本页」确认弹窗。
    /// 关闭会删掉该页的图层内容且写盘，属不可逆操作，必须确认。
    function requestCloseTab(pageIndex) {
        if (!vm || selectedId.length === 0) return
        if (vm.busy) {
            requestToast(vm.busyReason || "正在处理其它操作，请稍候")
            return
        }
        var item = presetById(selectedId)
        if (!item || item.corrupt) return
        if (pageIndex < 0 || pageIndex >= item.tabTitles.length) return
        // 关闭前先落地当前编辑态，避免用户刚打的字被一起删掉
        if (editingTabIndex >= 0)
            submitTabRename()
        pendingCloseTabIndex = pageIndex
        closeTabDialog.open()
    }

    /// 执行关闭单页。
    function performCloseTab() {
        if (!vm || pendingCloseTabIndex < 0) return
        var pageIndex = pendingCloseTabIndex
        var result = vm.closeDocument(selectedId, pageIndex)
        if (result && result.ok) {
            pendingCloseTabIndex = -1
            if (editingTabIndex === pageIndex)
                cancelTabRename()
            closeTabDialog.close()
            if (result.remaining <= 0) {
                // 关到空：等同清空，给撤销入口
                requestToastWithUndo("已关闭最后一页（" + result.title + "）", result.undo_token)
            } else {
                requestToast("已关闭「" + result.title + "」，剩余 " + result.remaining + " 页")
            }
            return
        }
        closeTabDialog.errorMessage = (result && result.message) || "关闭失败"
    }

    /// 把工作区里该预设的标签页内容覆盖保存回卡片。
    function requestSaveToPreset(presetId) {
        if (!vm) return
        var targetId = String(presetId || "")
        if (targetId.length === 0) return
        if (vm.busy) {
            requestToast(vm.busyReason || "正在处理其它操作，请稍候")
            return
        }
        // 保存前先落地页名编辑态：否则刚改的页名不会被写进 .cmp
        if (editingTabIndex >= 0)
            submitTabRename()
        var result = vm.savePresetFromWorkspace(targetId)
        if (result && result.ok) {
            requestToast("已保存 " + result.saved + " 页到预设")
            return
        }
        requestToast((result && result.message) || "保存失败")
    }

    /// 打开「清空全部」确认弹窗。
    function requestClearAllTabs() {
        var item = presetById(selectedId)
        if (!item) return
        if (item.documentCount <= 0) return
        if (vm && vm.busy) {
            requestToast(vm.busyReason || "正在处理其它操作，请稍候")
            return
        }
        // 清空前先落地当前编辑态，否则用户刚打的字会静默丢失
        if (editingTabIndex >= 0)
            submitTabRename()
        clearTabsDialog.openFor(selectedId)
    }

    /// 执行清空（确认后调用）。
    function performClearAllTabs(alsoCloseInWorkspace) {
        if (!vm || pendingClearTabsId.length === 0) return
        var targetId = pendingClearTabsId
        var result = vm.closeAllDocuments(targetId, alsoCloseInWorkspace)
        if (result && result.ok) {
            editingTabIndex = -1
            editingTabDraft = ""
            tabRenameError = ""
            pendingClearTabsId = ""
            clearTabsDialog.close()
            var extra = (result.workspace_closed || 0) > 0
                        ? "，并关闭了工作区 " + result.workspace_closed + " 个标签页" : ""
            requestToastWithUndo("已清空 " + result.cleared + " 个标签页" + extra, targetId)
            return
        }
        // 失败：弹窗不关闭，改为显示错误并提供重试
        clearTabsDialog.errorMessage = (result && result.message) || "清空失败"
    }

    /// Toast 带「撤销」按钮（仅清空全部用）。
    signal undoClearRequested(string presetId)
    function requestToastWithUndo(message, presetId) {
        undoToast.message = message
        undoToast.presetId = presetId
        undoToast.open()
    }

    /// 写操作失败时的统一提示。
    ///
    /// 之前这些入口只在成功时 toast，失败什么都不说 —— 用户看到的是
    /// 「点了没反应」（收藏没亮、封面没换、分类没变），既不知道失败，
    /// 也不知道原因。失败一律走这里，文案优先用视图模型的 lastError。
    function reportFailure(fallback) {
        requestToast((vm && vm.lastError) ? vm.lastError : (fallback || "操作失败，请重试"))
    }

    /// 订阅页名变化做行级刷新（不发 presetsChanged，避免整屏卡片闪）。
    Connections {
        target: vm
        enabled: vm !== null
        function onPresetsChanged() {
            // 选中项被删掉时（入口可能在卡片、详情面板、右键菜单或旧抽屉），
            // 选中态必须立刻退掉：否则右侧检查器停留在一个已不存在的预设上，
            // 按钮全都还能点，点完只得到「预设不存在」——看起来像界面没刷新。
            if (root.selectedId.length > 0 && root.vm
                    && !root.vm.presetExists(root.selectedId)) {
                root.clearSelection()
            }
        }
        function onDocumentTitlesChanged(presetId) {
            if (presetId === root.selectedId)
                root.thumbnailTick++   // 触发 tabList model 重算
        }
        function onDocumentsCleared(presetId) {
            if (presetId === root.selectedId) {
                root.editingTabIndex = -1
                root.editingTabDraft = ""
                root.tabRenameError = ""
                root.pendingCloseTabIndex = -1
                root.thumbnailTick++
            }
        }
        function onBusyChanged() {
            // 进入 busy 时强制结束编辑态，避免输入框在写盘期间还能改
            if (vm && vm.busy && root.editingTabIndex >= 0)
                root.cancelTabRename()
        }
    }

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

    /// 把焦点移到右侧详情的「名称」输入框并全选。
    ///
    /// 卡片右键的「重命名预设」用这个，而不是另开弹窗：
    /// 卡片名与页名只差两个字，两个弹窗并存时用户很容易改错对象。
    /// 走「选中卡片 + 聚焦名称框」这条路，改的一定是卡片名。
    function requestFocusPresetName() {
        presetNameField.forceActiveFocus()
        presetNameField.selectAll()
    }

    function clearSelection() {
        selectedId = ""
        editorName = ""
        editorDescription = ""
        editorDirty = false
        // 选中项没了，页名编辑态也要一起收掉：否则编辑态还挂在旧卡片上，
        // 下次选中别的卡片按回车，会把新卡片的页名改成旧草稿。
        if (editingTabIndex >= 0)
            cancelTabRename()
        pendingCloseTabIndex = -1
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
                                    // 「未分类」是兜底桶，不能删也不能改名
                                    renamable: modelData.name !== "未分类"
                                    deletable: modelData.name !== "未分类"
                                    onClicked: root.applyCategory(modelData.name)
                                    onRenameRequested: root.pendingRenameCategory = modelData.name
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

                    // 新建分类：真的往分类清单里写一条，然后切到该分类。
                    // 早先只是把筛选条件设成这个名字——列表里没有预设时它就
                    // 什么也不显示，用户会以为「建了但没建上」。
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
                                if (name.length === 0 || !root.vm) return
                                if (!root.vm.createCategory(name)) {
                                    root.reportFailure(root.vm.lastError || "新建分类失败")
                                    return
                                }
                                newCategoryField.text = ""
                                root.applyCategory(name)
                                root.requestToast("已新建分类「" + name + "」")
                            }
                            onClicked: applyNow()
                        }
                    }

                    TinyLabel {
                        Layout.leftMargin: 14
                        Layout.rightMargin: 14
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                        text: "悬停分类可重命名或删除；预设归属在右侧检查器里改"
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
                        onFavoriteToggled: {
                            if (root.vm && !root.vm.toggleFavorite(modelData.id))
                                root.reportFailure("更新收藏状态失败")
                        }
                        onDuplicateRequested: root.requestDuplicate(modelData.id)
                        onExportRequested: root.requestExport(modelData.id, modelData.name)
                        onDeleteRequested: root.requestDelete(modelData.id, modelData.name)
                        // 右键菜单：与详情面板页列表同一套操作，
                        // 只是把入口搬到卡片上（卡片操作条已满，加不下按钮）
                        onContextMenuRequested: (presetData, sceneX, sceneY) => {
                            root.contextMenuPresetId = presetData.id
                            cardContextMenu.popup(sceneX, sceneY)
                        }
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
                                    // 失败必须说一声：拖完卡片自己弹回原位，
                                    // 不提示的话用户只会以为拖拽功能坏了。
                                    if (root.vm && !root.vm.movePreset(root.dragId, root.dragTargetIndex))
                                        root.reportFailure("调整顺序失败")
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
                        onFavoriteToggled: {
                            if (root.vm && !root.vm.toggleFavorite(modelData.id))
                                root.reportFailure("更新收藏状态失败")
                        }
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
                                    // 失败必须说一声：拖完卡片自己弹回原位，
                                    // 不提示的话用户只会以为拖拽功能坏了。
                                    if (root.vm && !root.vm.movePreset(root.dragId, root.dragTargetIndex))
                                        root.reportFailure("调整顺序失败")
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
                            id: presetNameField
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
                                    else
                                        root.reportFailure("更新分类失败")
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
                                            if (!root.vm.setPresetCategory(root.selectedId, modelData.name))
                                                root.reportFailure("更新分类失败")
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // ---- 标签页列表（可改名 / 可清空）----
                    //
                    // 卡片封面只有 200×110，塞不下 3 行列表，所以页列表放这里：
                    // 卡片负责「认出是哪个」，详情面板负责「改它」。
                    // 行高 28 是双击热区的下限值（再矮就难点中），
                    // 超过 3 行内部滚动，不无限撑高面板。
                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 4
                        visible: {
                            var item = root.presetById(root.selectedId)
                            return item && !item.corrupt
                        }

                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 4
                            TinyLabel {
                                text: "标签页"
                                Layout.fillWidth: true
                            }
                            // 关闭全部：文字 + 图标的小按钮。
                            // 不用 CompactActionButton：它宽度写死 94、且不支持图标，
                            // 改公共组件会影响别处，所以这里就地做一个轻量版。
                            // documentCount <= 1 时**隐藏**（不是禁用）：
                            // 只有一页时说"关闭全部"等于清空整卡，
                            // 与「删除预设」语义混淆，不给这个入口。
                            Rectangle {
                                id: clearAllTabsButton
                                readonly property var currentItem: root.presetById(root.selectedId)
                                visible: currentItem && currentItem.documentCount > 1
                                enabled: root.vm && !root.vm.busy
                                implicitWidth: clearAllRow.implicitWidth + 14
                                implicitHeight: 22
                                radius: Theme.radiusSmall
                                color: !enabled ? Theme.bgControl
                                                : (clearAllMouse.containsMouse ? Theme.bgHover
                                                                               : "transparent")
                                border.width: 1
                                border.color: enabled ? Theme.borderStrong : Theme.border

                                // 悬停探测放在这里（在 ToolTip 绑定之前声明）：
                                // ToolTip.visible 若引用后面才声明的 MouseArea，
                                // 构造期会拿到 undefined（"Unable to assign
                                // [undefined] to bool"），绑定依赖注册不上，
                                // 提示就永远不出现。
                                HoverHandler { id: clearAllHover }

                                Row {
                                    id: clearAllRow
                                    anchors.centerIn: parent
                                    spacing: 3
                                    AppIcon {
                                        anchors.verticalCenter: parent.verticalCenter
                                        iconName: AppIcons.trash
                                        iconSize: 11
                                        iconColor: enabled ? Theme.textSecondary : Theme.textDisabled
                                    }
                                    Text {
                                        text: "清空全部"
                                        color: enabled ? Theme.textSecondary : Theme.textDisabled
                                        font.family: Theme.bodyFont
                                        font.pixelSize: 10
                                    }
                                }
                                MouseArea {
                                    id: clearAllMouse
                                    anchors.fill: parent
                                    enabled: parent.enabled
                                    hoverEnabled: true
                                    cursorShape: parent.enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onClicked: root.requestClearAllTabs()
                                }
                                ToolTip.delay: 500
                                ToolTip.visible: clearAllHover.hovered
                                ToolTip.text: root.vm && root.vm.busy
                                              ? root.vm.busyReason
                                              : "清空该预设的全部标签页（预设本身保留）"
                                Accessible.name: "清空全部标签页"
                                Accessible.role: Accessible.Button
                            }
                        }

                        // 空态：没有标签页时给出明确说明，不显示一个空框
                        Rectangle {
                            Layout.fillWidth: true
                            Layout.preferredHeight: emptyTabsRow.implicitHeight + 16
                            visible: {
                                var item = root.presetById(root.selectedId)
                                return item && item.documentCount === 0
                            }
                            color: "transparent"
                            border.width: 1
                            border.color: Theme.border
                            radius: Theme.radiusSmall

                            ColumnLayout {
                                id: emptyTabsRow
                                anchors.centerIn: parent
                                spacing: 2
                                AppIcon {
                                    Layout.alignment: Qt.AlignHCenter
                                    // 用 trash 而不是虚构的 file-x：图标集是随代码分发的
                                    // Lucide 子集（app/qml/icons/ 只有 102 个），
                                    // 引用不存在的名字会渲染成空白。
                                    iconName: AppIcons.trash
                                    iconSize: 14
                                    iconColor: Theme.textMuted
                                }
                                TinyLabel {
                                    Layout.alignment: Qt.AlignHCenter
                                    text: "没有标签页"
                                    color: Theme.textMuted
                                }
                            }
                        }

                        ListView {
                            id: tabList
                            Layout.fillWidth: true
                            Layout.preferredHeight: {
                                var item = root.presetById(root.selectedId)
                                var n = item ? item.tabTitles.length : 0
                                // 超过 3 页时多留 4px：底部要放得下「还有 N 页」的指示，
                                // 否则用户看到「标签页 4 个」但只数出 3 行，会以为丢了一页。
                                return Math.min(3, n) * 28 + (n > 3 ? 6 : 2)
                            }
                            visible: {
                                var item = root.presetById(root.selectedId)
                                return item && item.documentCount > 0
                            }
                            clip: true
                            boundsBehavior: Flickable.StopAtBounds
                            model: {
                                var tick = root.thumbnailTick
                                var item = root.presetById(root.selectedId)
                                return item ? item.tabTitles : []
                            }

                            delegate: Rectangle {
                                id: tabRow
                                required property var modelData
                                width: tabList.width
                                height: 28
                                color: tabMouse.containsMouse ? Theme.bgHover : "transparent"
                                radius: Theme.radiusSmall

                                readonly property bool editing: root.editingTabIndex === modelData.index

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 6
                                    anchors.rightMargin: 4
                                    spacing: 6

                                    // 页序号徽标（不用缩略图：面板约 300px，图会挤掉名字）
                                    Rectangle {
                                        Layout.preferredWidth: 16
                                        Layout.preferredHeight: 16
                                        radius: 3
                                        color: modelData.isCover ? Theme.accentSoft : Theme.bgControl
                                        border.width: 1
                                        border.color: modelData.isCover ? Theme.accent : Theme.border
                                        Text {
                                            anchors.centerIn: parent
                                            text: String(modelData.index + 1)
                                            color: modelData.isCover ? Theme.accent : Theme.textMuted
                                            font.family: Theme.bodyFont
                                            font.pixelSize: 9
                                        }
                                    }

                                    // 非编辑态：显示页名
                                    Text {
                                        Layout.fillWidth: true
                                        visible: !tabRow.editing
                                        text: modelData.title
                                        color: Theme.textPrimary
                                        font.family: Theme.bodyFont
                                        font.pixelSize: 11
                                        elide: Text.ElideRight
                                        maximumLineCount: 1
                                        ToolTip.delay: 600
                                        ToolTip.visible: tabNameHover.hovered && truncated
                                        ToolTip.text: modelData.title
                                        readonly property bool truncated: contentWidth > width

                                        HoverHandler { id: tabNameHover }
                                    }

                                    // 编辑态：内联输入框，预填并全选原文
                                    AppTextField {
                                        id: tabTitleField
                                        Layout.fillWidth: true
                                        visible: tabRow.editing
                                        controlSize: "sm"
                                        text: root.editingTabDraft
                                        selectByMouse: true
                                        onTextChanged: root.editingTabDraft = text
                                        onAccepted: root.submitTabRename()
                                        Keys.onEscapePressed: root.cancelTabRename()
                                        Keys.onReturnPressed: root.submitTabRename()

                                        Component.onCompleted: {
                                            if (visible) {
                                                forceActiveFocus()
                                                selectAll()
                                            }
                                        }
                                        onVisibleChanged: {
                                            if (visible) {
                                                forceActiveFocus()
                                                selectAll()
                                            }
                                        }
                                    }
                                }

                                // 行尾 ⋮ 菜单（重命名 / 设为封面 / 关闭本页）
                                IconButton {
                                    anchors.right: parent.right
                                    anchors.rightMargin: 2
                                    anchors.verticalCenter: parent.verticalCenter
                                    visible: !tabRow.editing
                                    iconName: AppIcons.more
                                    buttonSize: 20
                                    tooltip: "标签页操作"
                                    onClicked: {
                                        root.contextTabIndex = modelData.index
                                        tabRowMenu.popup()
                                    }
                                }

                                MouseArea {
                                    id: tabMouse
                                    // 避开右侧 ⋮ 按钮的点击区，否则点菜单会先触发双击改名
                                    anchors.fill: parent
                                    anchors.rightMargin: 22
                                    hoverEnabled: true
                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                    enabled: !tabRow.editing
                                    cursorShape: Qt.IBeamCursor
                                    onDoubleClicked: root.beginTabRename(modelData.index)
                                    onClicked: mouse => {
                                        if (mouse.button === Qt.RightButton) {
                                            root.contextTabIndex = modelData.index
                                            tabRowMenu.popup()
                                        }
                                    }
                                }
                            }
                        }

                        // 「还有 N 页」提示：超过 3 页时列表内部滚动，
                        // 不给提示的话用户看到「标签页 4 个」却只数出 3 行，会以为丢了一页。
                        Item {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 12
                            visible: {
                                var item = root.presetById(root.selectedId)
                                return item && item.tabTitles.length > 3
                            }
                            TinyLabel {
                                anchors.left: parent.left
                                anchors.leftMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                text: {
                                    var item = root.presetById(root.selectedId)
                                    var n = item ? item.tabTitles.length : 0
                                    return "还有 " + Math.max(0, n - 3) + " 页，滚动查看"
                                }
                                color: Theme.textMuted
                            }
                        }

                        // 编辑态的错误提示（红字，不退出编辑态）
                        TinyLabel {
                            Layout.fillWidth: true
                            visible: text.length > 0
                            text: root.tabRenameError
                            color: Theme.coral
                            wrapMode: Text.WordWrap
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
                                            else
                                                root.reportFailure("切换封面失败")
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
                                    else
                                        root.reportFailure("更新标签失败")
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
                                root.requestToast("预设信息已保存")
                            } else {
                                root.reportFailure("保存预设信息失败")
                            }
                        }
                    }

                    // 把工作区里这张卡片的标签页内容存回来。
                    //
                    // 与上面「保存修改」分工不同，两个都不能省：
                    //   上面那管名称/描述（卡片元数据）
                    //   这里管标签页内容（图层、画布尺寸、页名）
                    // 用户在工作区改完图后如果没有这个入口，就只能「另存为」新预设，
                    // 库里会堆出一堆重复卡片。
                    // 套一层 HoverHandler：按钮 disabled 时它内部的 MouseArea
                    // 收不到悬停事件，ToolTip 就永远不出现 —— 而「为什么禁用」
                    // 恰恰只有靠这条提示才能说清。外层是正常 Item，能收到。
                    Item {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        HoverHandler { id: saveToPresetHover }

                        AppButton {
                            anchors.fill: parent
                            readonly property int openPages: root.vm && root.selectedId.length > 0
                                                            ? root.vm.openPageCount(root.selectedId) : 0
                            text: openPages > 0 ? "保存改动回此预设（" + openPages + " 页）"
                                                : "保存改动回此预设"
                            // 没打开过就无处可存：禁用而不是隐藏，让用户知道有这条路
                            enabled: root.vm && !root.vm.busy && openPages > 0
                            ToolTip.delay: 500
                            ToolTip.visible: saveToPresetHover.hovered
                            ToolTip.text: openPages > 0
                                          ? "把工作区里这 " + openPages + " 页的当前内容覆盖保存到该预设"
                                          : "先在编辑器中打开该预设，改完再回来保存"
                            onClicked: root.requestSaveToPreset(root.selectedId)
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

    // 重命名分类：成员跟着改名，位置保持不动。
    AppDialog {
        id: renameCategoryDialog
        width: 400
        height: 176
        modal: true
        closePolicy: Popup.CloseOnEscape
        title: "重命名分类"
        visible: root.pendingRenameCategory.length > 0

        onVisibleChanged: {
            if (!visible) return
            renameCategoryField.text = root.pendingRenameCategory
            renameCategoryField.forceActiveFocus()
            // 全选旧名字：用户多半是想整个换掉，而不是在中间插字
            if (renameCategoryField.text.length > 0)
                renameCategoryField.select(0, renameCategoryField.text.length)
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 12

            AppTextField {
                id: renameCategoryField
                Layout.fillWidth: true
                controlSize: "sm"
                placeholderText: "分类名称"
                color: Theme.textPrimary
                selectByMouse: true
                onAccepted: renameApply.applyNow()
            }

            BodyLabel {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                color: Theme.textMuted
                text: "该分类下的预设会一起改用新名称，预设内容不受影响。"
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton {
                    Layout.preferredWidth: 88
                    label: "取消"
                    onClicked: root.pendingRenameCategory = ""
                }
                ExportButton {
                    id: renameApply
                    Layout.preferredWidth: 88
                    label: "重命名"
                    primary: true
                    enabled: renameCategoryField.text.trim().length > 0
                    function applyNow() {
                        var oldName = root.pendingRenameCategory
                        var newName = renameCategoryField.text.trim()
                        if (!root.vm || !oldName || !newName) return
                        if (!root.vm.renameCategory(oldName, newName)) {
                            // 失败不关弹窗：用户还要接着改名字
                            root.reportFailure(root.vm.lastError || "重命名分类失败")
                            return
                        }
                        root.pendingRenameCategory = ""
                        // 正停在这个分类上时只换筛选值，不重走 applyCategory
                        // （那个会顺手清空卡片选中态）
                        if (root.activeCategory === oldName)
                            root.activeCategory = newName
                        root.requestToast("分类已重命名为「" + newName + "」")
                    }
                    onClicked: applyNow()
                }
            }
        }
    }

    // 删除分类确认：分类删掉只是把成员归回「未分类」，不删任何预设，
    // 但仍要确认一次——用户可能只是想改名。
    AppDialog {
        id: deleteCategoryConfirm
        width: 400
        height: 160
        modal: true
        closePolicy: Popup.CloseOnEscape
        title: "删除分类？"
        visible: root.pendingDeleteCategory.length > 0

        contentItem: ColumnLayout {
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
                        // -1 才是失败；0 表示删的是空分类，同样算成功
                        var affected = root.vm ? root.vm.deleteCategory(root.pendingDeleteCategory) : -1
                        var name = root.pendingDeleteCategory
                        root.pendingDeleteCategory = ""
                        if (affected >= 0)
                            root.requestToast(affected > 0
                                              ? affected + " 个预设已归入「未分类」"
                                              : "已删除空分类「" + name + "」")
                        else
                            root.reportFailure(root.vm ? (root.vm.lastError || "删除分类失败")
                                                       : "删除分类失败")
                    }
                }
            }
        }
    }

    // ---- 卡片右键菜单 ----
    //
    // 为什么加在卡片上：卡片操作条已经有 5 个按钮（打开/批量/收藏/复制/删除），
    // 再把「清空标签页」塞进去会挤掉视觉呼吸空间。右键菜单不占版面。
    //
    // 菜单项刻意**与详情面板页列表保持一致**：同一功能不在两处用不同名字，
    // 否则用户会以为是两回事。
    AppMenu {
        id: cardContextMenu

        ShapeMenuItem {
            text: "打开"
            enabled: root.contextMenuPresetId.length > 0 && !root.vm?.busy
            onTriggered: root.requestLoad(root.contextMenuPresetId)
        }
        MenuSeparator { }

        ShapeMenuItem {
            text: "重命名预设"
            enabled: root.contextMenuPresetId.length > 0 && !root.vm?.busy
            onTriggered: {
                // 复用右侧详情的名称输入框：选中卡片后聚焦并全选，
                // 不另开一个重命名弹窗（卡片名与页名容易混）。
                root.selectedId = root.contextMenuPresetId
                root.requestFocusPresetName()
            }
        }
        ShapeMenuItem {
            text: "复制预设"
            enabled: root.contextMenuPresetId.length > 0 && !root.vm?.busy
            onTriggered: root.requestDuplicate(root.contextMenuPresetId)
        }
        MenuSeparator { }

        ShapeMenuItem {
            // 需要至少 2 页：只有一页时「清空全部」等同删除整卡内容，
            // 与「删除预设」语义混淆（详见设计文档 1.3）
            text: "清空全部标签页…"
            enabled: {
                if (!root.vm || root.vm.busy) return false
                var item = root.presetById(root.contextMenuPresetId)
                return item && item.documentCount > 1
            }
            onTriggered: {
                root.selectedId = root.contextMenuPresetId
                root.requestClearAllTabs()
            }
        }
        MenuSeparator { }

        ShapeMenuItem {
            text: "删除预设…"
            enabled: root.contextMenuPresetId.length > 0 && !root.vm?.busy
            onTriggered: {
                var item = root.presetById(root.contextMenuPresetId)
                if (item)
                    root.requestDelete(item.id, item.name)
            }
        }
    }

    // ---- 页行尾 ⋮ 菜单 ----
    AppMenu {
        id: tabRowMenu

        ShapeMenuItem {
            text: "重命名标签页"
            enabled: root.vm && !root.vm.busy
            onTriggered: root.beginTabRename(root.contextTabIndex)
        }
        ShapeMenuItem {
            text: "设为卡片封面"
            enabled: root.vm && !root.vm.busy
            onTriggered: {
                if (root.vm && root.contextTabIndex >= 0
                        && !root.vm.setCoverDocument(root.selectedId, root.contextTabIndex))
                    root.reportFailure("切换封面失败")
            }
        }
        MenuSeparator { }
        ShapeMenuItem {
            // 危险操作，与「清空全部」之间加分隔线，避免误点
            text: "关闭本页"
            enabled: root.vm && !root.vm.busy
            onTriggered: root.requestCloseTab(root.contextTabIndex)
        }
    }

    // ---- 关闭单个标签页确认 ----
    //
    // 关闭 = 删掉这一页的图层内容并写盘，不可逆。必须二次确认。
    // 关的是最后一页时文案要变——那种情况下卡片会进入空态，
    // 用户需要知道「不是删了预设」。
    AppDialog {
        id: closeTabDialog
        property string errorMessage: ""

        width: 420
        height: 200
        modal: true
        closePolicy: Popup.CloseOnEscape
        title: "关闭这个标签页？"

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 10

            BodyLabel {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                color: Theme.textPrimary
                text: {
                    var item = root.presetById(root.selectedId)
                    var idx = root.pendingCloseTabIndex
                    var name = (item && idx >= 0 && idx < item.tabTitles.length)
                               ? item.tabTitles[idx].title : ""
                    return "「" + name + "」的图层内容将被删除，无法恢复。"
                }
            }

            TinyLabel {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                color: Theme.textMuted
                text: {
                    var item = root.presetById(root.selectedId)
                    // 最后一页：说明会变成空预设，且预设本身保留
                    if (item && item.documentCount <= 1)
                        return "这是该预设的最后一页。关闭后预设会变为空状态，但预设本身、分类与标签都会保留。"
                    return "其余标签页与预设本身不受影响。"
                }
            }

            TinyLabel {
                Layout.fillWidth: true
                visible: closeTabDialog.errorMessage.length > 0
                text: closeTabDialog.errorMessage
                color: Theme.coral
                wrapMode: Text.Wrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton {
                    Layout.preferredWidth: 88
                    label: "取消"
                    onClicked: {
                        root.pendingCloseTabIndex = -1
                        closeTabDialog.close()
                    }
                }
                ExportButton {
                    Layout.preferredWidth: 112
                    label: closeTabDialog.errorMessage.length > 0 ? "重试" : "关闭标签页"
                    primary: true
                    onClicked: root.performCloseTab()
                }
            }
        }
    }

    // ---- 清空全部标签页确认 ----
    //
    // 一次性清空 N 页，误点代价高（.cmp 被覆盖后没有系统级回收站），
    // 所以必须二次确认，且明确写出「预设本身保留」「工作区不受影响」。
    AppDialog {
        id: clearTabsDialog
        // Popup 不在 contentItem 的 childItems 里，findChild 只能靠 objectName 找到。
        // 没有它，自动化测试无法验证「勾选开关 → 真的关掉工作区标签」这条链路，
        // 上一轮就是这么漏掉的（后端单测过了，界面链路从没验过）。
        objectName: "presetClearTabsDialog"
        property string errorMessage: ""
        property bool alsoCloseWorkspace: false
        // 开关真实状态回写到根对象镜像，外部才读得到
        onAlsoCloseWorkspaceChanged: {
            if (root.alsoCloseWorkspaceOnClear !== alsoCloseWorkspace)
                root.alsoCloseWorkspaceOnClear = alsoCloseWorkspace
        }

        width: 440
        height: 248
        modal: true
        closePolicy: Popup.CloseOnEscape
        title: "关闭全部标签页？"

        function openFor(presetId) {
            errorMessage = ""
            alsoCloseWorkspace = false
            root.pendingClearTabsId = presetId
            open()
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 18
            spacing: 10

            BodyLabel {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                color: Theme.textPrimary
                text: {
                    var item = root.presetById(root.pendingClearTabsId)
                    var n = item ? item.documentCount : 0
                    return "将清空「" + (item ? item.name : "") + "」中的 " + n
                           + " 个标签页，此操作不可撤销。"
                }
            }

            TinyLabel {
                Layout.fillWidth: true
                wrapMode: Text.Wrap
                text: "预设本身、分类与标签会保留。已打开到工作区的标签页不受影响。"
                color: Theme.textMuted
            }

            // 可选：同时关闭工作区里来自该预设的标签页。
            // 默认不勾——用户想清的是卡片内容，不该顺手关掉正在编辑的东西。
            RowLayout {
                Layout.fillWidth: true
                spacing: 6
                visible: {
                    var item = root.presetById(root.pendingClearTabsId)
                    return item && item.documentCount > 0
                }
                ToggleSwitch {
                    id: alsoCloseSwitch
                    checked: clearTabsDialog.alsoCloseWorkspace
                    // 注意：toggled 带 bool 参数。这里显式用形参 value，
                    // 不要写 `checked = !checked` —— 那会解析到开关自身的属性。
                    onToggled: value => clearTabsDialog.alsoCloseWorkspace = value
                }
                TinyLabel {
                    Layout.fillWidth: true
                    text: "同时关闭工作区中来自此预设的标签页"
                    color: Theme.textSecondary
                    wrapMode: Text.Wrap
                }
            }

            TinyLabel {
                Layout.fillWidth: true
                visible: clearTabsDialog.errorMessage.length > 0
                text: clearTabsDialog.errorMessage
                color: Theme.coral
                wrapMode: Text.Wrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton {
                    Layout.preferredWidth: 88
                    label: "取消"
                    onClicked: {
                        root.pendingClearTabsId = ""
                        clearTabsDialog.alsoCloseWorkspace = false
                        clearTabsDialog.close()
                    }
                }
                ExportButton {
                    Layout.preferredWidth: 128
                    label: clearTabsDialog.errorMessage.length > 0 ? "重试" : "清空标签页"
                    primary: true
                    onClicked: root.performClearAllTabs(clearTabsDialog.alsoCloseWorkspace)
                }
            }
        }
    }

    // ---- 清空后的「撤销」Toast（30s 内有效）----
    // 独立于普通 Toast：带一个撤销按钮。放在底部居中，不遮详情面板。
    Rectangle {
        id: undoToast
        property string message: ""
        property string presetId: ""

        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 24
        width: undoToastRow.implicitWidth + 28
        height: 40
        radius: Theme.radiusSmall
        color: Theme.bgRaised
        border.width: 1
        border.color: Theme.borderStrong
        visible: opacity > 0
        opacity: 0
        z: 400

        Behavior on opacity { NumberAnimation { duration: 140 } }

        function open() {
            opacity = 1
            hideTimer.restart()
        }
        function dismiss() {
            opacity = 0
            presetId = ""
        }

        Timer {
            id: hideTimer
            interval: 8000
            onTriggered: undoToast.dismiss()
        }

        Row {
            id: undoToastRow
            anchors.centerIn: parent
            spacing: 10
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: undoToast.message
                color: Theme.textPrimary
                font.family: Theme.bodyFont
                font.pixelSize: 11
            }
            Rectangle {
                anchors.verticalCenter: parent.verticalCenter
                width: 56
                height: 24
                radius: Theme.radiusSmall
                color: undoMouse.containsMouse ? Theme.accentSoft : "transparent"
                border.width: 1
                border.color: Theme.accent
                Text {
                    anchors.centerIn: parent
                    text: "撤销"
                    color: Theme.accent
                    font.family: Theme.bodyFont
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
                MouseArea {
                    id: undoMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        var targetId = undoToast.presetId
                        undoToast.dismiss()
                        if (!root.vm || targetId.length === 0) return
                        var result = root.vm.undoClearDocuments(targetId)
                        if (result && result.ok)
                            root.requestToast("已恢复 " + result.restored + " 个标签页")
                        else
                            root.requestToast((result && result.message) || "撤销失败")
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
        // 只有分类行可删/可改名；「未分类」是兜底桶
        property bool deletable: false
        property bool renamable: false
        signal clicked()
        signal renameRequested()
        signal deleteRequested()

        implicitHeight: 30
        color: active ? Theme.bgSelected : (rowHover.hovered ? Theme.bgHover : "transparent")

        // 悬停判断用 HoverHandler 而不是 MouseArea.containsMouse：
        // 行尾按钮会盖在整行 MouseArea 上面，一旦鼠标移上去，
        // containsMouse 会翻成 false，按钮随即隐藏 → 点不到还闪。
        // HoverHandler 只看光标是否在本项范围内，不受子项遮挡影响。
        HoverHandler { id: rowHover }

        // 整行点击必须放在最底层声明：QML 同层子项按声明顺序叠放，
        // 后声明的 MouseArea 会盖住 RowLayout 里的重命名/删除按钮，
        // 导致这两个按钮点了只会切换分类（实测点击无任何反应）。
        MouseArea {
            id: navMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: navRow.clicked()
        }

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
                visible: navRow.count >= 0
                         && !((navRow.renamable || navRow.deletable)
                              && (rowHover.hovered || navRow.active))
                text: navRow.count
                color: Theme.textMuted
                font.family: Theme.dataFont
                font.pixelSize: 10
                // 必须显式给宽度：RowLayout 会优先压缩没有宽度约束的子项，
                // 否则计数会被 fillWidth 的标签挤成 "1"。
                Layout.preferredWidth: 22
                horizontalAlignment: Text.AlignRight
            }

            // 重命名分类：和删除一起只在悬停/选中时露出。
            Item {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                visible: navRow.renamable && (rowHover.hovered || navRow.active)

                AppIcon {
                    anchors.centerIn: parent
                    iconName: AppIcons.pencil
                    iconSize: 12
                    iconColor: renameMouse.containsMouse ? Theme.accent : Theme.textMuted
                }
                MouseArea {
                    id: renameMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: navRow.renameRequested()
                    ToolTip.delay: 500
                    ToolTip.visible: containsMouse
                    ToolTip.text: "重命名分类"
                }
            }

            // 删除分类：默认藏起来，悬停/选中才露出，避免侧栏一片叉号。
            // 用 Item 占位保证不悬停时行宽不跳。
            Item {
                Layout.preferredWidth: 18
                Layout.preferredHeight: 18
                visible: navRow.deletable && (rowHover.hovered || navRow.active)

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
