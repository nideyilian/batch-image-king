import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
import QtCore
import "components"

ApplicationWindow {
    id: window

    width: 1600
    height: 960
    minimumWidth: 1180
    minimumHeight: 720
    visible: true
    title: "批图王 · QML 工作台"
    color: Theme.bgApp

    onClosing: function(close) {
        if (!workspaceSessions.applicationCloseApproved) {
            close.accepted = false
            workspaceSessions.requestApplicationClose()
        }
    }

    property int selectedLayer: workspace.selectedLayerIndex
    property int activeTool: 0
    property int inspectorTab: 0
    property string toastMessage: ""
    property string activeLayerName: workspace.selectedLayerName
    readonly property bool hasOpenDocument: workspaceSessions.count > 0

    // 统一的快捷键焦点门控：画布文字编辑中 / 阻塞态 / 任意属性面板输入框取得焦点时
    // 都会抑制图层编辑类与单字母工具类快捷键，避免抢输入或误触发。
    function _activeFocusIsEditable() {
        var it = window.activeFocusItem
        if (!it) return false
        // selectByMouse -> TextField/TextArea; inputMethodHints/cursorPosition -> SpinBox/ValueBox/SelectBox 等可编辑
        if (it.hasOwnProperty && it.hasOwnProperty("selectByMouse")) return true
        if (it.hasOwnProperty && it.hasOwnProperty("cursorPosition")) return true
        if (it.hasOwnProperty && it.hasOwnProperty("inputMethodHints")) return true
        return false
    }
    property bool _editableInputHasFocus: _activeFocusIsEditable()
    property bool layerShortcutsEnabled: hasOpenDocument && !selectedTextEditor.editing
                                          && !workspace.operationsBlocked && !_editableInputHasFocus
    property bool toolShortcutsEnabled: !selectedTextEditor.editing && !_editableInputHasFocus
    property string pendingCloseTitle: ""
    property int contextDocumentIndex: -1
    property bool updateBannerDismissed: false
    property string updateBannerText: ""
    property bool pendingUpdateInstall: false
    property var quickCanvasPresets: [
        { name: "方形图", width: 800, height: 800 },
        { name: "横版 16:9", width: 1280, height: 720 },
        { name: "竖版 9:16", width: 1080, height: 1920 }
    ]
    readonly property var blendModeOptions: [
        { label: "正常", value: "normal" },
        { label: "正片叠底", value: "multiply" },
        { label: "滤色", value: "screen" },
        { label: "叠加", value: "overlay" },
        { label: "柔光", value: "soft_light" },
        { label: "强光", value: "hard_light" },
        { label: "颜色减淡", value: "color_dodge" },
        { label: "颜色加深", value: "color_burn" },
        { label: "变暗", value: "darken" },
        { label: "变亮", value: "lighten" },
        { label: "差值", value: "difference" },
        { label: "排除", value: "exclusion" },
        { label: "色相", value: "hue" },
        { label: "饱和度", value: "saturation" },
        { label: "颜色", value: "color" },
        { label: "明度", value: "luminosity" }
    ]
    readonly property var imageFitOptions: [
        { label: "填满裁剪", value: "crop" },
        { label: "完整显示", value: "fit" },
        { label: "原始尺寸", value: "original" }
    ]
    readonly property var cropDirectionOptions: [
        { iconName: AppIcons.circleDot, label: "居中裁剪", value: "center" },
        { iconName: AppIcons.arrowUp, label: "保留顶部", value: "top" },
        { iconName: AppIcons.arrowDown, label: "保留底部", value: "bottom" },
        { iconName: AppIcons.arrowLeft, label: "保留左侧", value: "left" },
        { iconName: AppIcons.arrowRight, label: "保留右侧", value: "right" }
    ]
    readonly property var vectorHandleLinkOptions: [
        { label: "镜像", value: "mirror" },
        { label: "共线", value: "collinear" },
        { label: "自由", value: "free" }
    ]
    readonly property var cloneMirrorOptions: [
        { label: "无镜像", value: "none" },
        { label: "左右镜像", value: "horizontal" },
        { label: "上下镜像", value: "vertical" }
    ]
    readonly property var cloneFillModeOptions: [
        { label: "常规网格", value: "grid" },
        { label: "错位排列", value: "staggered" },
        { label: "边框排列", value: "border" }
    ]
    readonly property var strokeTypeOptions: [
        { label: "内描边", value: 0 },
        { label: "居中描边", value: 1 },
        { label: "外描边", value: 2 }
    ]
    readonly property var strokeJoinOptions: [
        { label: "斜接", value: "miter" },
        { label: "圆角", value: "round" },
        { label: "斜切", value: "bevel" }
    ]
    readonly property var strokeCapOptions: [
        { label: "平头", value: "butt" },
        { label: "圆头", value: "round" },
        { label: "方头", value: "square" }
    ]
    readonly property var textGradientTypeOptions: [
        { label: "线性", value: "linear" },
        { label: "径向", value: "radial" },
        { label: "角度", value: "angular" }
    ]
    readonly property var textGradientDirectionOptions: [
        { label: "水平", value: "horizontal" },
        { label: "垂直", value: "vertical" },
        { label: "左上 → 右下", value: "diagonal_lr" },
        { label: "右上 → 左下", value: "diagonal_rl" }
    ]

    function showToast(message) {
        toastMessage = message
        toast.opacity = 1
        toastTimer.restart()
    }

    function openNewCanvasDialog() {
        if (!workspace.operationsBlocked)
            newCanvasDialog.open()
    }

    function defaultQuickCanvasPresets() {
        return [
            { name: "方形图", width: 800, height: 800 },
            { name: "横版 16:9", width: 1280, height: 720 },
            { name: "竖版 9:16", width: 1080, height: 1920 }
        ]
    }

    function normalizedQuickCanvasPresets(candidates) {
        if (!candidates || candidates.length !== 3)
            return null
        var normalized = []
        for (var index = 0; index < candidates.length; index++) {
            var candidate = candidates[index] || {}
            var name = String(candidate.name || "").trim()
            var widthValue = parseInt(candidate.width)
            var heightValue = parseInt(candidate.height)
            if (name.length === 0 || isNaN(widthValue) || isNaN(heightValue)
                    || widthValue < 16 || heightValue < 16
                    || widthValue > 32768 || heightValue > 32768)
                return null
            normalized.push({ name: name, width: widthValue, height: heightValue })
        }
        return normalized
    }

    function loadQuickCanvasPresets() {
        var restored = null
        if (newCanvasSettings.quickPresetsJson.length > 0) {
            try {
                restored = normalizedQuickCanvasPresets(JSON.parse(newCanvasSettings.quickPresetsJson))
            } catch (error) {
                restored = null
            }
        }
        quickCanvasPresets = restored || defaultQuickCanvasPresets()
        if (!restored)
            newCanvasSettings.quickPresetsJson = JSON.stringify(quickCanvasPresets)
    }

    function replaceQuickCanvasPreset(index, name, widthValue, heightValue) {
        if (index < 0 || index >= quickCanvasPresets.length)
            return false
        var normalized = normalizedQuickCanvasPresets([
            index === 0 ? { name: name, width: widthValue, height: heightValue } : quickCanvasPresets[0],
            index === 1 ? { name: name, width: widthValue, height: heightValue } : quickCanvasPresets[1],
            index === 2 ? { name: name, width: widthValue, height: heightValue } : quickCanvasPresets[2]
        ])
        if (!normalized)
            return false
        quickCanvasPresets = normalized
        newCanvasSettings.quickPresetsJson = JSON.stringify(normalized)
        return true
    }

    function isSupportedImageUrl(urlValue) {
        var cleanUrl = String(urlValue || "").split("?")[0].split("#")[0].toLowerCase()
        return /\.(png|jpe?g|webp|gif|bmp|tiff?)$/.test(cleanUrl)
    }

    function hasSupportedImageUrl(urls) {
        if (!urls)
            return false
        for (var index = 0; index < urls.length; index++) {
            if (isSupportedImageUrl(urls[index]))
                return true
        }
        return false
    }

    function addDroppedImages(urls) {
        var addedCount = 0
        for (var index = 0; urls && index < urls.length; index++) {
            var urlValue = urls[index]
            if (isSupportedImageUrl(urlValue) && workspace.addImageLayer(String(urlValue)))
                addedCount++
        }
        return addedCount
    }

    function openBatchExportDrawer() {
        if (window.hasOpenDocument && (!workspace.operationsBlocked || batchExport.running)) {
            if (batchExport.fileFormat !== "png" && batchExport.fileFormat !== "jpg")
                batchExport.fileFormat = "png"
            batchExportDrawer.open()
        }
    }

    function openMultiTabExportDrawer() {
        if (window.hasOpenDocument && (!workspace.operationsBlocked || multiTabExport.running))
            multiTabExportDrawer.open()
    }

    function openProjectPresetDrawer() {
        if (!workspace.operationsBlocked)
            projectPresetDrawer.open()
    }

    function openCanvasPresetDrawer() {
        if (window.hasOpenDocument && !workspace.operationsBlocked)
            canvasPresetDrawer.open()
    }

    function openDataRelations(tab) {
        if (!window.hasOpenDocument || workspace.operationsBlocked) return
        dataRelationsDrawer.activeTab = tab
        dataRelationsDrawer.open()
    }

    function openResizeCanvasDialog() {
        if (window.hasOpenDocument && !workspace.operationsBlocked)
            resizeCanvasDialog.openForDocument()
    }

    function openRenameDocumentDialog(index) {
        if (!workspace.operationsBlocked)
            renameDocumentDialog.openForDocument(index)
    }

    function openUpdateDialog() {
        if (!updateManager.downloading)
            updateManager.checkForUpdates()
        updateDialog.open()
    }

    function openAboutDialog() {
        aboutDialog.open()
    }

    function restoreExportSurface(index) {
        if (multiTabExport.running) {
            multiTabExportDrawer.open()
            return true
        }
        if (batchExport.running && index === workspaceSessions.activeIndex) {
            batchExportDrawer.open()
            return true
        }
        showToast("当前标签页没有正在后台运行的导出任务")
        return false
    }

    function selectInspectorTab(index) {
        inspectorTab = index
        Qt.callLater(function() {
            if (inspectorScroll.contentItem) {
                inspectorScroll.contentItem.contentX = 0
                inspectorScroll.contentItem.contentY = 0
                inspectorScroll.contentItem.returnToBounds()
            }
        })
    }

    function revealTextTypography() {
        inspectorTab = 0
        textFontSection.expanded = true
        textTypographySection.expanded = true
        Qt.callLater(function() {
            if (inspectorScroll.contentItem)
                inspectorScroll.contentItem.contentY = Math.max(0, textFontSection.y - 8)
        })
    }

    function revealTextContentEditing() {
        if (workspace.selectedLayerIndex < 0)
            return
        inspectorTab = 0
        textContentSection.expanded = true
        Qt.callLater(function() {
            if (inspectorScroll.contentItem)
                inspectorScroll.contentItem.contentY = Math.max(0, textContentSection.y - 8)
            if (!workspace.textEditOverlayVisible)
                selectedTextEditor.beginEdit()
        })
    }

    function focusCanvasTextEditor() {
        Qt.callLater(function() {
            if (canvasTextEditInput.activeFocus)
                return
            canvasTextEditInput.forceActiveFocus()
            canvasTextEditInput.selectAll()
        })
    }

    function revealTextAppearance() {
        inspectorTab = 1
        textBackgroundSection.expanded = true
        Qt.callLater(function() {
            if (inspectorScroll.contentItem)
                inspectorScroll.contentItem.contentY = Math.max(0, textBackgroundSection.y - 8)
        })
    }

    function revealTextEffects() {
        inspectorTab = 1
        textShadowSection.expanded = true
        textGlowSection.expanded = true
        Qt.callLater(function() {
            if (inspectorScroll.contentItem)
                inspectorScroll.contentItem.contentY = Math.max(0, textShadowSection.y - 8)
        })
    }

    function revealAdvancedProperties() {
        if (workspace.selectedLayerIndex < 0) return
        inspectorTab = 1
        layerTransformSection.expanded = true
        clonePropertiesSection.expanded = true
        Qt.callLater(function() {
            if (!inspectorScroll.contentItem) return
            var target = workspace.selectedSupportsClone ? clonePropertiesSection : layerTransformSection
            inspectorScroll.contentItem.contentY = Math.max(0, target.y - 8)
        })
    }

    function alignCurrentSelection(mode) {
        if (workspace.selectedLayerCount > 1)
            workspace.alignSelectedLayers(mode)
        else
            workspace.alignSelected(mode)
    }

    function revealLayerNameEditor() {
        if (workspace.selectedLayerIndex < 0) return
        inspectorTab = 0
        var section = workspace.selectedIsLayerGroup ? groupSection : basicPropertiesSection
        var editor = workspace.selectedIsLayerGroup ? groupNameEditor : layerNameEditor
        section.expanded = true
        Qt.callLater(function() {
            if (inspectorScroll.contentItem)
                inspectorScroll.contentItem.contentY = Math.max(0, section.y - 8)
            editor.beginEdit()
        })
    }

    function optionIndex(options, value) {
        for (var index = 0; index < options.length; index++) {
            if (options[index].value === value) return index
        }
        return 0
    }

    function colorChannelHex(channel) {
        var text = Math.round(Math.max(0, Math.min(1, channel)) * 255).toString(16).toUpperCase()
        return text.length < 2 ? "0" + text : text
    }

    function colorToHex(colorValue) {
        var result = "#" + colorChannelHex(colorValue.r) + colorChannelHex(colorValue.g) + colorChannelHex(colorValue.b)
        return colorValue.a < 0.999 ? result + colorChannelHex(colorValue.a) : result
    }

    function hexToColor(hexValue) {
        var value = String(hexValue || "#000000").replace("#", "")
        if (value.length !== 6 && value.length !== 8) return Qt.rgba(0, 0, 0, 1)
        var red = parseInt(value.slice(0, 2), 16) / 255
        var green = parseInt(value.slice(2, 4), 16) / 255
        var blue = parseInt(value.slice(4, 6), 16) / 255
        var alpha = value.length === 8 ? parseInt(value.slice(6, 8), 16) / 255 : 1
        return Qt.rgba(red, green, blue, alpha)
    }

    Settings {
        id: newCanvasSettings
        category: "newCanvas"
        property string quickPresetsJson: ""
    }

    Component.onCompleted: window.loadQuickCanvasPresets()

    Connections {
        target: workspace
        function onToastRequested(message) { showToast(message) }
        function onSelectionChanged() { selectedTextEditor.releaseFocus() }
    }

    Connections {
        target: workspaceSessions
        function onCloseConfirmationRequested(index, title) {
            pendingCloseTitle = title
            closeConfirmDialog.open()
        }
        function onSavePathRequested(index, title) {
            pendingCloseTitle = title
            closeSaveDialog.open()
        }
        function onApplicationCloseReady() {
            if (pendingUpdateInstall) {
                if (updateManager.installDownloadedUpdate()) {
                    Qt.callLater(function() { window.close() })
                } else {
                    pendingUpdateInstall = false
                    workspaceSessions.cancelClose()
                    updateDialog.open()
                }
                return
            }
            Qt.callLater(function() { window.close() })
        }
    }

    Connections {
        target: updateManager
        function onAutoUpdateDetected(version) {
            updateBannerDismissed = false
            updateBannerText = "发现新版本 v" + version
            updateDialog.open()
        }
        function onUpdateFinished(ok, message) {
            if (ok) {
                showToast(message)
            } else {
                showToast("更新失败：" + message)
            }
        }
    }

    // ============================================================
    // 统一 Photoshop 风格快捷键（与 app/utils/shortcut_contract.py 同步）
    // 修改任何键位请先改契约模块，再同步到这里与经典 UI
    // ============================================================

    // --- 1. 文件 / 历史 --------------------------------------------------
    Shortcut { sequence: "Ctrl+N";        enabled: !workspace.operationsBlocked;                         onActivated: window.openNewCanvasDialog() }
    Shortcut { sequence: "Ctrl+O";        onActivated: openDialog.open() }
    Shortcut { sequence: "Ctrl+S";        enabled: window.hasOpenDocument;                                  onActivated: workspace.hasFilePath ? workspace.saveDocument() : saveDialog.open() }
    Shortcut { sequence: "Ctrl+Shift+S";  enabled: window.hasOpenDocument;                                  onActivated: saveDialog.open() }
    Shortcut { sequence: "Ctrl+W";        enabled: window.hasOpenDocument;                                  onActivated: workspaceSessions.requestClose(workspaceSessions.activeIndex) }
    Shortcut { sequence: "Ctrl+Z";        enabled: workspace.canUndo;                                        onActivated: workspace.undo() }
    Shortcut { sequence: "Ctrl+Shift+Z";  enabled: workspace.canRedo;                                        onActivated: workspace.redo() }   // PS 标准重做
    Shortcut { sequence: "Ctrl+Y";        enabled: workspace.canRedo;                                        onActivated: workspace.redo() }   // Windows 兼容别名
    Shortcut { sequence: "Ctrl+Alt+Z";    enabled: workspace.canUndo;                                        onActivated: workspace.undo() }   // PS「后退一步」别名

    // --- 2. 图层编辑（Photoshop 核心语义区 —— 应用专属功能严禁占用） ---
    Shortcut { sequence: "Ctrl+C";        enabled: window.layerShortcutsEnabled;                             onActivated: legacyTools.copySelectedLayers() }
    Shortcut { sequence: "Ctrl+V";        enabled: window.layerShortcutsEnabled && legacyTools.hasLayerClipboard; onActivated: legacyTools.pasteLayers() }
    Shortcut { sequence: "Ctrl+Shift+C";  enabled: window.layerShortcutsEnabled && workspace.selectedLayerIndex >= 0; onActivated: workspace.copySelectedLayerStyle() }
    Shortcut { sequence: "Ctrl+Shift+V";  enabled: window.layerShortcutsEnabled && workspace.selectedLayerIndex >= 0; onActivated: workspace.pasteSelectedLayerStyle() }
    Shortcut { sequence: "Ctrl+A";        enabled: window.layerShortcutsEnabled;                             onActivated: legacyTools.selectAllLayers() }
    Shortcut { sequence: "Ctrl+J";        enabled: window.layerShortcutsEnabled;                             onActivated: workspace.duplicateSelectedLayers() }        // PS:复制选中图层到新图层
    Shortcut { sequence: "Delete";        enabled: window.layerShortcutsEnabled && workspace.selectedLayerIndex >= 0; onActivated: workspace.deleteSelectedLayers() }
    Shortcut { sequence: "F2";            enabled: window.layerShortcutsEnabled && workspace.selectedLayerIndex >= 0; onActivated: window.revealLayerNameEditor() }
    // 变换 / 合并 / 编组
    Shortcut { sequence: "Ctrl+T";        enabled: window.layerShortcutsEnabled && workspace.selectedLayerIndex >= 0; onActivated: workspace.beginFreeTransform() }        // PS:自由变换
    Shortcut { sequence: "Ctrl+E";        enabled: window.layerShortcutsEnabled && workspace.selectedLayerIndex >= 0; onActivated: workspace.mergeSelectedDown() }            // PS:向下合并
    Shortcut { sequence: "Ctrl+G";        enabled: window.layerShortcutsEnabled;                             onActivated: workspace.groupSelectedLayers() }                     // PS:图层编组
    Shortcut { sequence: "Ctrl+Shift+G";  enabled: window.layerShortcutsEnabled;                             onActivated: workspace.ungroupSelectedGroups() }                   // PS:取消编组
    // 顺序移动
    Shortcut { sequence: "Ctrl+[";        enabled: window.layerShortcutsEnabled && workspace.canMoveLayerBackward; onActivated: workspace.moveSelectedLayer("backward") }
    Shortcut { sequence: "Ctrl+]";        enabled: window.layerShortcutsEnabled && workspace.canMoveLayerForward;  onActivated: workspace.moveSelectedLayer("forward") }
    Shortcut { sequence: "Ctrl+Shift+[";  enabled: window.layerShortcutsEnabled;                             onActivated: workspace.moveSelectedLayer("to_back") }     // PS:置于底层
    Shortcut { sequence: "Ctrl+Shift+]";  enabled: window.layerShortcutsEnabled;                             onActivated: workspace.moveSelectedLayer("to_front") }    // PS:置于顶层
    Shortcut { sequence: "Ctrl+Down";     enabled: window.layerShortcutsEnabled && workspace.canMoveLayerBackward; onActivated: workspace.moveSelectedLayer("backward") } // 兼容别名
    Shortcut { sequence: "Ctrl+Up";       enabled: window.layerShortcutsEnabled && workspace.canMoveLayerForward;  onActivated: workspace.moveSelectedLayer("forward") }  // 兼容别名

    // --- 3. 视图（Ctrl+R 还给 PS 标尺，Alt+Ctrl+C=修改画布尺寸） ---
    Shortcut { sequence: "Ctrl+R";        enabled: window.hasOpenDocument;                                   onActivated: workspace.toggleRulers() }   // PS:切换标尺
    Shortcut { sequence: ";";             enabled: window.hasOpenDocument;                                   onActivated: workspace.toggleGuides() }   // PS:切换参考线（保留简洁形式）
    Shortcut { sequence: "Ctrl++";        enabled: window.hasOpenDocument;                                   onActivated: workspace.setZoomFactor(workspace.zoomFactor * 1.1) }
    Shortcut { sequence: "Ctrl+-";        enabled: window.hasOpenDocument;                                   onActivated: workspace.setZoomFactor(workspace.zoomFactor / 1.1) }
    Shortcut { sequence: "Ctrl+0";        enabled: window.hasOpenDocument;                                   onActivated: workspace.resetView() }

    // --- 4. 工具切换（单字母 —— 非文字编辑且非输入框焦点时生效） -----
    Shortcut { sequence: "V"; enabled: window.toolShortcutsEnabled; onActivated: activeTool = 0 }   // 移动/选择
    Shortcut { sequence: "H"; enabled: window.toolShortcutsEnabled; onActivated: activeTool = 1 }   // 抓手
    Shortcut { sequence: "Z"; enabled: window.toolShortcutsEnabled; onActivated: activeTool = 2 }   // 缩放（PS 标准，新增）
    Shortcut { sequence: "T"; enabled: window.toolShortcutsEnabled; onActivated: activeTool = 3 }   // 文字工具（PS 标准；新建图层→Shift+F8）
    Shortcut { sequence: "C"; enabled: window.toolShortcutsEnabled; onActivated: workspace.startCropEdit() }   // 裁剪工具（PS 标准）
    Shortcut { sequence: "P"; enabled: window.toolShortcutsEnabled; onActivated: activeTool = 4 }   // 路径/钢笔
    Shortcut { sequence: "G"; enabled: window.toolShortcutsEnabled; onActivated: activeTool = 5 }   // 渐变/油漆桶
    Shortcut { sequence: "I"; enabled: window.toolShortcutsEnabled; onActivated: activeTool = 6 }   // 吸管
    Shortcut { sequence: "U"; enabled: window.toolShortcutsEnabled; onActivated: activeTool = 7 }   // 形状/矢量
    Shortcut { sequence: "A"; enabled: window.toolShortcutsEnabled && workspace.selectedVectorPathEnabled; onActivated: activeTool = 8 }   // 路径选择（仅路径模式）

    // --- 5. 批图王专属（避开 PS 核心键位，参见 shortcut_contract.py） ---
    Shortcut { sequence: "Ctrl+Shift+X";        enabled: window.hasOpenDocument;                                  onActivated: exportDialog.open() }                              // 原 Ctrl+E：导出当前画面
    Shortcut { sequence: "F12";                  enabled: window.hasOpenDocument && (!workspace.operationsBlocked || batchExport.running); onActivated: window.openBatchExportDrawer() } // 批量导出
    Shortcut { sequence: "Ctrl+Alt+Shift+X";    enabled: window.hasOpenDocument && (!workspace.operationsBlocked || multiTabExport.running); onActivated: window.openMultiTabExportDrawer() } // 原 Ctrl+Shift+E：多标签导出
    Shortcut { sequence: "Alt+Shift+D";         enabled: !workspace.operationsBlocked && workspaceSessions.activeIndex >= 0;               onActivated: workspaceSessions.duplicateDocument(workspaceSessions.activeIndex) } // 原 Ctrl+D：复制标签页
    Shortcut { sequence: "Shift+F8";            enabled: window.layerShortcutsEnabled;                                                         onActivated: textLayerDialog.openFresh() } // 原 Ctrl+T：添加文字图层
    Shortcut { sequence: "Shift+Ctrl+N";        enabled: window.layerShortcutsEnabled;                                                         onActivated: workspace.addEmptyImageLayer() } // 原 Ctrl+L：新建空图片图层（对齐 PS 新建图层习惯）
    Shortcut { sequence: "Ctrl+Shift+P";        enabled: !workspace.operationsBlocked;                                                        onActivated: window.openProjectPresetDrawer() } // 原 Ctrl+P：预设中心
    Shortcut { sequence: "Alt+Ctrl+C";          enabled: window.hasOpenDocument && !workspace.operationsBlocked;                             onActivated: window.openResizeCanvasDialog() } // 原 Ctrl+R：修改画布尺寸（对齐 PS Alt+Ctrl+C=Canvas Size）

    FileDialog {
        id: openDialog
        title: "打开批图王项目"
        fileMode: FileDialog.OpenFile
        nameFilters: ["批图王项目 (*.cmp)"]
        onAccepted: workspaceSessions.openDocument(selectedFile.toString())
    }

    FileDialog {
        id: closeSaveDialog
        title: "保存后关闭 " + pendingCloseTitle
        fileMode: FileDialog.SaveFile
        defaultSuffix: "cmp"
        nameFilters: ["批图王项目 (*.cmp)"]
        onAccepted: workspaceSessions.saveAndClose(
            workspaceSessions.pendingCloseIndex,
            selectedFile.toString()
        )
        onRejected: {
            pendingUpdateInstall = false
            workspaceSessions.cancelClose()
        }
    }

    AppDialog {
        id: newCanvasDialog
        objectName: "newCanvasDialog"
        anchors.centerIn: parent
        width: 440
        height: 410
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape

        function chooseSize(widthValue, heightValue) {
            canvasWidthInput.text = String(widthValue)
            canvasHeightInput.text = String(heightValue)
        }

        function createCanvas() {
            var widthValue = parseInt(canvasWidthInput.text)
            var heightValue = parseInt(canvasHeightInput.text)
            if (workspaceSessions.newDocument(widthValue, heightValue)) close()
        }

        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
            radius: Theme.radius
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            spacing: 16
            anchors.margins: 20

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "新建画布"
                    color: Theme.textPrimary
                    font.family: Theme.displayFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 28; onClicked: newCanvasDialog.close() }
            }

            Divider { Layout.fillWidth: true }

            BodyLabel { text: "常用尺寸"; color: Theme.textPrimary }
            GridLayout {
                Layout.fillWidth: true
                columns: 3
                rowSpacing: 8
                columnSpacing: 8

                Repeater {
                    model: window.quickCanvasPresets
                    delegate: Rectangle {
                        id: quickPresetTile
                        required property var modelData
                        required property int index
                        Layout.fillWidth: true
                        Layout.preferredHeight: 60
                        radius: Theme.radiusSmall
                        color: presetMouse.containsMouse ? Theme.bgHover : Theme.bgControl
                        border.width: 1
                        border.color: activeFocus ? Theme.focusRing : Theme.borderStrong
                        activeFocusOnTab: true
                        Column {
                            anchors.left: parent.left
                            anchors.right: editQuickPresetButton.left
                            anchors.verticalCenter: parent.verticalCenter
                            anchors.leftMargin: 8
                            anchors.rightMargin: 2
                            spacing: 2
                            BodyLabel { text: quickPresetTile.modelData.name; color: Theme.textPrimary; width: parent.width; elide: Text.ElideRight; horizontalAlignment: Text.AlignHCenter }
                            TinyLabel { text: quickPresetTile.modelData.width + " x " + quickPresetTile.modelData.height; width: parent.width; horizontalAlignment: Text.AlignHCenter }
                        }
                        MouseArea {
                            id: presetMouse
                            anchors.left: parent.left
                            anchors.top: parent.top
                            anchors.bottom: parent.bottom
                            anchors.right: editQuickPresetButton.left
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onPressed: quickPresetTile.forceActiveFocus(Qt.MouseFocusReason)
                            onClicked: newCanvasDialog.chooseSize(quickPresetTile.modelData.width, quickPresetTile.modelData.height)
                        }
                        IconButton {
                            id: editQuickPresetButton
                            anchors.right: parent.right
                            anchors.rightMargin: 4
                            anchors.verticalCenter: parent.verticalCenter
                            iconName: AppIcons.settings
                            tooltip: "编辑常用尺寸"
                            buttonSize: 32
                            iconSize: 14
                            onClicked: quickCanvasPresetDialog.openForPreset(quickPresetTile.index)
                        }
                        Keys.onSpacePressed: newCanvasDialog.chooseSize(modelData.width, modelData.height)
                        Keys.onReturnPressed: newCanvasDialog.chooseSize(modelData.width, modelData.height)
                        Keys.onEnterPressed: newCanvasDialog.chooseSize(modelData.width, modelData.height)
                        Accessible.name: modelData.name + " " + modelData.width + " x " + modelData.height
                        Accessible.role: Accessible.Button
                    }
                }
            }

            BodyLabel { text: "自定义尺寸"; color: Theme.textPrimary }
            RowLayout {
                Layout.fillWidth: true
                spacing: 10

                AppTextField {
                    id: canvasWidthInput
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    text: "800"
                    placeholderText: "宽度"
                    color: Theme.textPrimary
                    selectByMouse: true
                    validator: IntValidator { bottom: 16; top: 32768 }
                    background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: canvasWidthInput.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
                }
                TinyLabel { text: "x"; Layout.preferredWidth: 10; horizontalAlignment: Text.AlignHCenter }
                AppTextField {
                    id: canvasHeightInput
                    Layout.fillWidth: true
                    Layout.preferredHeight: 38
                    text: "800"
                    placeholderText: "高度"
                    color: Theme.textPrimary
                    selectByMouse: true
                    validator: IntValidator { bottom: 16; top: 32768 }
                    background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: canvasHeightInput.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
                    Keys.onReturnPressed: newCanvasDialog.createCanvas()
                }
                TinyLabel { text: "px"; Layout.preferredWidth: 18; horizontalAlignment: Text.AlignRight }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton { Layout.preferredWidth: 88; label: "取消"; onClicked: newCanvasDialog.close() }
                ExportButton { Layout.preferredWidth: 112; label: "创建画布"; iconName: AppIcons.add; primary: true; onClicked: newCanvasDialog.createCanvas() }
            }
        }
    }

    AppDialog {
        id: resizeCanvasDialog
        objectName: "resizeCanvasDialog"
        anchors.centerIn: parent
        width: 500
        height: 350
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape
        property int adjustmentMode: 0
        property string errorMessage: ""

        function openForDocument() {
            resizeCanvasWidthInput.text = String(workspace.canvasWidth)
            resizeCanvasHeightInput.text = String(workspace.canvasHeight)
            adjustmentMode = 0
            errorMessage = ""
            open()
            Qt.callLater(function() { resizeCanvasWidthInput.forceActiveFocus() })
        }

        function applyResize() {
            var widthValue = parseInt(resizeCanvasWidthInput.text)
            var heightValue = parseInt(resizeCanvasHeightInput.text)
            if (isNaN(widthValue) || isNaN(heightValue)
                    || widthValue < 16 || heightValue < 16
                    || widthValue > 32768 || heightValue > 32768) {
                errorMessage = "宽度和高度必须在 16 到 32768 像素之间"
                return
            }
            if (workspace.resizeCanvas(widthValue, heightValue, adjustmentMode))
                close()
            else
                errorMessage = workspace.statusMessage
        }

        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
            radius: Theme.radius
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Column {
                    Layout.fillWidth: true
                    spacing: 3
                    Text {
                        text: "修改画布尺寸"
                        color: Theme.textPrimary
                        font.family: Theme.displayFont
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                    }
                    TinyLabel { text: "当前 " + workspace.canvasWidth + " x " + workspace.canvasHeight + " px" }
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 28; onClicked: resizeCanvasDialog.close() }
            }

            Divider { Layout.fillWidth: true }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: 10
                columnSpacing: 12

                BodyLabel { text: "新尺寸"; color: Theme.textMuted; Layout.preferredWidth: 68 }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    AppTextField {
                        id: resizeCanvasWidthInput
                        Layout.fillWidth: true
                        Layout.preferredHeight: 38
                        placeholderText: "宽度"
                        color: Theme.textPrimary
                        selectByMouse: true
                        validator: IntValidator { bottom: 16; top: 32768 }
                        background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: resizeCanvasWidthInput.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
                    }
                    TinyLabel { text: "x"; Layout.preferredWidth: 10; horizontalAlignment: Text.AlignHCenter }
                    AppTextField {
                        id: resizeCanvasHeightInput
                        Layout.fillWidth: true
                        Layout.preferredHeight: 38
                        placeholderText: "高度"
                        color: Theme.textPrimary
                        selectByMouse: true
                        validator: IntValidator { bottom: 16; top: 32768 }
                        background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: resizeCanvasHeightInput.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
                        Keys.onReturnPressed: resizeCanvasDialog.applyResize()
                    }
                    TinyLabel { text: "px"; Layout.preferredWidth: 18; horizontalAlignment: Text.AlignRight }
                }

                BodyLabel { text: "图层处理"; color: Theme.textMuted }
                RowLayout {
                    id: canvasAdjustmentOptions
                    Layout.fillWidth: true
                    spacing: 8

                    OptionTile {
                        title: "比例缩放"
                        detail: "同步调整图层位置与尺寸"
                        exclusive: true
                        selected: resizeCanvasDialog.adjustmentMode === 0
                        onActivated: resizeCanvasDialog.adjustmentMode = 0
                    }
                    OptionTile {
                        title: "居中保留"
                        detail: "保持尺寸并移动到画布中心"
                        exclusive: true
                        selected: resizeCanvasDialog.adjustmentMode === 1
                        onActivated: resizeCanvasDialog.adjustmentMode = 1
                    }
                    OptionTile {
                        title: "左上保留"
                        detail: "保持尺寸并对齐画布左上"
                        exclusive: true
                        selected: resizeCanvasDialog.adjustmentMode === 2
                        onActivated: resizeCanvasDialog.adjustmentMode = 2
                    }
                }
            }

            TinyLabel {
                Layout.fillWidth: true
                visible: text.length > 0
                text: resizeCanvasDialog.errorMessage
                color: Theme.coral
                wrapMode: Text.Wrap
            }

            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton { Layout.preferredWidth: 84; label: "取消"; onClicked: resizeCanvasDialog.close() }
                ExportButton { Layout.preferredWidth: 112; label: "应用尺寸"; iconName: AppIcons.check; primary: true; onClicked: resizeCanvasDialog.applyResize() }
            }
        }
    }

    AppDialog {
        id: renameDocumentDialog
        objectName: "renameDocumentDialog"
        anchors.centerIn: parent
        width: 430
        height: 220
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape
        property int documentIndex: -1
        property string errorMessage: ""

        function openForDocument(index) {
            if (index < 0 || index >= workspaceSessions.count) return
            documentIndex = index
            renameDocumentInput.text = workspaceSessions.titleAt(index)
            errorMessage = ""
            open()
            Qt.callLater(function() {
                renameDocumentInput.forceActiveFocus()
                renameDocumentInput.selectAll()
            })
        }

        function submit() {
            var titleValue = renameDocumentInput.text.trim()
            if (titleValue.length === 0) {
                errorMessage = "标签页名称不能为空"
                return
            }
            if (workspaceSessions.renameDocument(documentIndex, titleValue))
                close()
            else
                errorMessage = "无法重命名当前标签页"
        }

        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
            radius: Theme.radius
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "重命名标签页"
                    color: Theme.textPrimary
                    font.family: Theme.displayFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 28; onClicked: renameDocumentDialog.close() }
            }
            Divider { Layout.fillWidth: true }
            BodyLabel { text: "标签页名称"; color: Theme.textMuted }
            AppTextField {
                id: renameDocumentInput
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                color: Theme.textPrimary
                selectByMouse: true
                placeholderText: "输入名称"
                background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: renameDocumentInput.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
                Keys.onReturnPressed: renameDocumentDialog.submit()
            }
            TinyLabel { Layout.fillWidth: true; visible: text.length > 0; text: renameDocumentDialog.errorMessage; color: Theme.coral }
            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton { Layout.preferredWidth: 84; label: "取消"; onClicked: renameDocumentDialog.close() }
                ExportButton { Layout.preferredWidth: 96; label: "确认"; iconName: AppIcons.check; primary: true; onClicked: renameDocumentDialog.submit() }
            }
        }
    }

    AppDialog {
        id: textLayerDialog
        objectName: "textLayerDialog"
        anchors.centerIn: parent
        width: 560
        height: Math.min(590, window.height - 48)
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape
        // impeccable-disable-next-line design-system-font: output-content font, not UI typography
        property string fontFamily: "sans-serif"
        property string fontFace: ""
        property string alignment: "left"
        property bool bindingEnabled: true
        property string errorMessage: ""

        function openFresh() {
            textLayerNameInput.text = "新文字图层"
            textLayerContentInput.text = "示例文字"
            bindingEnabled = true
            // impeccable-disable-next-line design-system-font: output-content font, not UI typography
            fontFamily = "sans-serif"
            fontFace = ""
            textLayerFontSizeInput.text = "24"
            textLayerColorInput.text = "#000000"
            alignment = "left"
            errorMessage = ""
            open()
            Qt.callLater(function() { textLayerNameInput.beginEdit() })
        }

        function createLayer() {
            var success = workspace.addConfiguredTextLayer({
                name: textLayerNameInput.text,
                content: textLayerContentInput.text,
                bindingEnabled: textLayerDialog.bindingEnabled,
                fontFamily: fontFamily,
                fontFace: fontFace,
                fontSize: parseInt(textLayerFontSizeInput.text),
                color: textLayerColorInput.text,
                alignment: alignment
            })
            if (success) close()
            else errorMessage = workspace.statusMessage
        }

        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
            radius: Theme.radius
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "添加文字图层"
                    color: Theme.textPrimary
                    font.family: Theme.displayFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 28; onClicked: textLayerDialog.close() }
            }

            Divider { Layout.fillWidth: true }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: 10
                columnSpacing: 12

                BodyLabel { text: "图层名称"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                ValueBox {
                    id: textLayerNameInput
                    Layout.fillWidth: false
                    text: "新文字图层"
                    onValueCommitted: value => text = value
                }

                BodyLabel { text: "内容模式"; color: Theme.textMuted }
                RowLayout {
                    id: textContentModeOptions
                    Layout.fillWidth: true
                    spacing: 8

                    OptionTile {
                        title: "按行随机"
                        detail: "每一行作为独立候选文案"
                        exclusive: true
                        selected: textLayerDialog.bindingEnabled
                        onActivated: textLayerDialog.bindingEnabled = true
                    }
                    OptionTile {
                        title: "整段排版"
                        detail: "保留真实换行和段落结构"
                        exclusive: true
                        selected: !textLayerDialog.bindingEnabled
                        onActivated: textLayerDialog.bindingEnabled = false
                    }
                }
            }

            BodyLabel { text: "文字内容"; color: Theme.textMuted }
            AppTextArea {
                id: textLayerContentInput
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.minimumHeight: 130
                text: "示例文字"
                placeholderText: "输入文字内容"
                color: Theme.textPrimary
                placeholderTextColor: Theme.textMuted
                selectionColor: Theme.accentPressed
                selectedTextColor: Theme.textPrimary
                font.family: Theme.bodyFont
                font.pixelSize: 12
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                padding: 10
                background: Rectangle {
                    color: Theme.bgControl
                    border.width: 1
                    border.color: textLayerContentInput.activeFocus ? Theme.accent : Theme.borderStrong
                    radius: Theme.radiusSmall
                }
            }

            GridLayout {
                Layout.fillWidth: true
                columns: 2
                rowSpacing: 10
                columnSpacing: 12

                BodyLabel { text: "字体"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                FontSelectBox {
                    Layout.fillWidth: false
                    value: textLayerDialog.fontFamily
                    face: textLayerDialog.fontFace
                    options: workspace.textFontTreeOptions
                    onActivated: function(value, face) {
                        textLayerDialog.fontFamily = value
                        textLayerDialog.fontFace = face
                    }
                }

                BodyLabel { text: "字号与颜色"; color: Theme.textMuted }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    ValueBox { id: textLayerFontSizeInput; text: "24"; suffix: "px"; Layout.preferredWidth: 104 }
                    ValueBox { id: textLayerColorInput; text: "#000000"; Layout.fillWidth: false }
                    Rectangle {
                        Layout.preferredWidth: Theme.controlHeight
                        Layout.preferredHeight: Theme.controlHeight
                        radius: Theme.radiusSmall
                        color: window.hexToColor(textLayerColorInput.text)
                        border.width: 1
                        border.color: Theme.borderStrong
                    }
                }

                BodyLabel { text: "对齐"; color: Theme.textMuted }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6
                    CompactActionButton { label: "左对齐"; active: textLayerDialog.alignment === "left"; Layout.fillWidth: false; onClicked: textLayerDialog.alignment = "left" }
                    CompactActionButton { label: "居中"; active: textLayerDialog.alignment === "center"; Layout.fillWidth: false; onClicked: textLayerDialog.alignment = "center" }
                    CompactActionButton { label: "右对齐"; active: textLayerDialog.alignment === "right"; Layout.fillWidth: false; onClicked: textLayerDialog.alignment = "right" }
                }
            }

            TinyLabel {
                Layout.fillWidth: true
                text: textLayerDialog.errorMessage
                color: Theme.coral
                visible: text.length > 0
                wrapMode: Text.Wrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton { Layout.preferredWidth: 88; label: "取消"; onClicked: textLayerDialog.close() }
                ExportButton { Layout.preferredWidth: 112; label: "添加图层"; iconName: AppIcons.add; primary: true; onClicked: textLayerDialog.createLayer() }
            }
        }
    }

    AppDialog {
        id: shapedLayerDialog
        objectName: "shapedLayerDialog"
        anchors.centerIn: parent
        width: 620
        height: Math.min(580, window.height - 48)
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape
        property string sourceMode: "none"
        property string shapeType: "rectangle"
        property string trapezoidSlopeSide: "right"
        property string errorMessage: ""

        function openFresh() {
            shapedLayerNameInput.text = "异形图层"
            shapeType = "rectangle"
            shapedLayerXInput.text = "0"
            shapedLayerYInput.text = "0"
            shapedLayerWidthInput.text = "200"
            shapedLayerHeightInput.text = "200"
            shapedLayerSourceInput.text = ""
            shapedLayerUseOriginalInput.checked = false
            shapedTrapezoidTopInput.text = "100"
            shapedTrapezoidBottomInput.text = "80"
            shapedPolygonRotationInput.text = "0"
            shapedPolygonCornerInput.text = "0"
            sourceMode = "none"
            trapezoidSlopeSide = "right"
            errorMessage = ""
            open()
            Qt.callLater(function() { shapedLayerNameInput.beginEdit() })
        }

        function createLayer() {
            var success = workspace.addConfiguredShapedLayer({
                name: shapedLayerNameInput.text,
                shapeType: shapedLayerDialog.shapeType,
                x: parseInt(shapedLayerXInput.text),
                y: parseInt(shapedLayerYInput.text),
                width: parseInt(shapedLayerWidthInput.text),
                height: parseInt(shapedLayerHeightInput.text),
                source: shapedLayerSourceInput.text,
                sourceIsFolder: sourceMode === "folder",
                useOriginalSize: shapedLayerUseOriginalInput.checked,
                trapezoidTopRatio: parseInt(shapedTrapezoidTopInput.text),
                trapezoidBottomRatio: parseInt(shapedTrapezoidBottomInput.text),
                trapezoidSlopeSide: trapezoidSlopeSide,
                polygonRotation: parseFloat(shapedPolygonRotationInput.text),
                polygonCornerRadius: parseInt(shapedPolygonCornerInput.text)
            })
            if (success) close()
            else errorMessage = workspace.statusMessage
        }

        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
            radius: Theme.radius
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 22
            spacing: 14

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "添加异形图层"
                    color: Theme.textPrimary
                    font.family: Theme.displayFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 28; onClicked: shapedLayerDialog.close() }
            }

            Divider { Layout.fillWidth: true }

            ScrollView {
                id: shapedFormScroll
                Layout.fillWidth: true
                Layout.fillHeight: true
                clip: true
                ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                ColumnLayout {
                    width: shapedFormScroll.availableWidth
                    spacing: 12

                    GridLayout {
                        Layout.fillWidth: true
                        columns: 2
                        rowSpacing: 10
                        columnSpacing: 12

                        BodyLabel { text: "图层名称"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                        ValueBox { id: shapedLayerNameInput; Layout.fillWidth: false; text: "异形图层" }

                        BodyLabel { text: "形状"; color: Theme.textMuted; Layout.alignment: Qt.AlignTop; Layout.topMargin: 8 }
                        GridLayout {
                            id: shapedLayerTypeOptions
                            Layout.fillWidth: true
                            columns: 3
                            rowSpacing: 6
                            columnSpacing: 6

                            OptionTile {
                                compact: true
                                exclusive: true
                                title: "矩形"
                                detail: "标准四边形"
                                selected: shapedLayerDialog.shapeType === "rectangle"
                                onActivated: shapedLayerDialog.shapeType = "rectangle"
                            }
                            OptionTile {
                                compact: true
                                exclusive: true
                                title: "直角梯形"
                                detail: "可调上下底与斜边"
                                selected: shapedLayerDialog.shapeType === "right_trapezoid"
                                onActivated: shapedLayerDialog.shapeType = "right_trapezoid"
                            }
                            OptionTile {
                                compact: true
                                exclusive: true
                                title: "圆形"
                                detail: "圆形或椭圆"
                                selected: shapedLayerDialog.shapeType === "circle"
                                onActivated: shapedLayerDialog.shapeType = "circle"
                            }
                            OptionTile {
                                compact: true
                                exclusive: true
                                title: "正五边形"
                                detail: "可调旋转与圆角"
                                selected: shapedLayerDialog.shapeType === "pentagon"
                                onActivated: shapedLayerDialog.shapeType = "pentagon"
                            }
                            OptionTile {
                                compact: true
                                exclusive: true
                                title: "正六边形"
                                detail: "可调旋转与圆角"
                                selected: shapedLayerDialog.shapeType === "hexagon"
                                onActivated: shapedLayerDialog.shapeType = "hexagon"
                            }
                        }
                    }

                    BodyLabel { text: "位置与尺寸"; color: Theme.textPrimary; font.weight: Font.DemiBold }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        BodyLabel { text: "位置"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                        ValueBox { id: shapedLayerXInput; text: "0"; suffix: "X"; Layout.fillWidth: false }
                        ValueBox { id: shapedLayerYInput; text: "0"; suffix: "Y"; Layout.fillWidth: false }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        BodyLabel { text: "尺寸"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                        ValueBox { id: shapedLayerWidthInput; text: "200"; suffix: "W"; Layout.fillWidth: false }
                        ValueBox { id: shapedLayerHeightInput; text: "200"; suffix: "H"; Layout.fillWidth: false }
                    }

                    BodyLabel { text: "内容源（可稍后设置）"; color: Theme.textPrimary; font.weight: Font.DemiBold }
                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        BodyLabel { text: "来源"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                        ValueBox {
                            id: shapedLayerSourceInput
                            Layout.fillWidth: false
                            text: ""
                            editable: false
                        }
                        IconButton {
                            iconName: AppIcons.image
                            tooltip: "选择单张图片"
                            onClicked: shapedLayerSourceFileDialog.open()
                        }
                        IconButton {
                            iconName: AppIcons.folderInput
                            tooltip: "选择素材文件夹"
                            onClicked: shapedLayerSourceFolderDialog.open()
                        }
                        IconButton {
                            iconName: AppIcons.close
                            tooltip: "清除内容源"
                            enabled: shapedLayerDialog.sourceMode !== "none"
                            onClicked: {
                                shapedLayerDialog.sourceMode = "none"
                                shapedLayerSourceInput.text = ""
                            }
                        }
                    }
                    RowLayout {
                        Layout.fillWidth: true
                        BodyLabel { text: "源模式"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                        BodyLabel {
                            text: shapedLayerDialog.sourceMode === "file" ? "单张图片" : shapedLayerDialog.sourceMode === "folder" ? "素材文件夹" : "尚未选择"
                            color: shapedLayerDialog.sourceMode === "none" ? Theme.textMuted : Theme.textSecondary
                            Layout.fillWidth: true
                        }
                        BodyLabel { text: "使用原始尺寸"; color: Theme.textMuted }
                        ToggleSwitch {
                            id: shapedLayerUseOriginalInput
                            accessibleName: "使用原始尺寸"
                            checked: false
                            enabled: shapedLayerDialog.sourceMode === "file"
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        visible: shapedLayerDialog.shapeType === "right_trapezoid"
                        BodyLabel { text: "梯形参数"; color: Theme.textPrimary; font.weight: Font.DemiBold }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            BodyLabel { text: "上下底"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                            ValueBox { id: shapedTrapezoidTopInput; text: "100"; suffix: "% 上"; Layout.fillWidth: false }
                            ValueBox { id: shapedTrapezoidBottomInput; text: "80"; suffix: "% 下"; Layout.fillWidth: false }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            BodyLabel { text: "斜边"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                            CompactActionButton { label: "右侧"; active: shapedLayerDialog.trapezoidSlopeSide === "right"; Layout.fillWidth: false; onClicked: shapedLayerDialog.trapezoidSlopeSide = "right" }
                            CompactActionButton { label: "左侧"; active: shapedLayerDialog.trapezoidSlopeSide === "left"; Layout.fillWidth: false; onClicked: shapedLayerDialog.trapezoidSlopeSide = "left" }
                        }
                    }

                    ColumnLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        visible: shapedLayerDialog.shapeType === "pentagon" || shapedLayerDialog.shapeType === "hexagon"
                        BodyLabel { text: "多边形参数"; color: Theme.textPrimary; font.weight: Font.DemiBold }
                        RowLayout {
                            Layout.fillWidth: true
                            spacing: 8
                            BodyLabel { text: "外观"; color: Theme.textMuted; Layout.preferredWidth: 72 }
                            ValueBox { id: shapedPolygonRotationInput; text: "0"; suffix: "°"; Layout.fillWidth: false }
                            ValueBox { id: shapedPolygonCornerInput; text: "0"; suffix: "px 圆角"; Layout.fillWidth: false }
                        }
                    }
                }
            }

            TinyLabel {
                Layout.fillWidth: true
                text: shapedLayerDialog.errorMessage
                color: Theme.coral
                visible: text.length > 0
                wrapMode: Text.Wrap
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton { Layout.preferredWidth: 88; label: "取消"; onClicked: shapedLayerDialog.close() }
                ExportButton { Layout.preferredWidth: 112; label: "添加图层"; iconName: AppIcons.add; primary: true; onClicked: shapedLayerDialog.createLayer() }
            }
        }
    }

    AppDialog {
        id: presetDeleteConfirm
        anchors.centerIn: parent
        width: 390
        height: 170
        modal: true
        padding: 0
        property string presetId: ""
        property string presetName: ""
        background: Rectangle { color: Theme.bgPanel; border.width: 1; border.color: Theme.borderStrong; radius: Theme.radius }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 14
            Text { text: "删除项目预设？"; color: Theme.textPrimary; font.family: Theme.displayFont; font.pixelSize: 16; font.weight: Font.DemiBold }
            BodyLabel { text: "“" + presetDeleteConfirm.presetName + "”将从本机永久移除。"; color: Theme.textSecondary; Layout.fillWidth: true; wrapMode: Text.Wrap }
            RowLayout {
                Layout.fillWidth: true
                Item { Layout.fillWidth: true }
                ExportButton { Layout.preferredWidth: 80; label: "取消"; onClicked: presetDeleteConfirm.close() }
                ExportButton {
                    Layout.preferredWidth: 90
                    label: "删除"
                    primary: true
                    onClicked: {
                        projectPresets.deletePreset(presetDeleteConfirm.presetId)
                        projectPresetDrawer.clearEditor()
                        presetDeleteConfirm.close()
                    }
                }
            }
        }
    }

    AppDrawer {
        id: projectPresetDrawer
        objectName: "projectPresetDrawer"
        edge: Qt.RightEdge
        width: Math.min(460, Math.max(390, window.width * 0.29))
        height: window.height
        modal: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0

        property string selectedPresetId: ""

        function clearEditor() {
            selectedPresetId = ""
            projectPresetName.clear()
            projectPresetDescription.clear()
        }

        function selectPreset(presetId) {
            var items = projectPresets.presets
            for (var index = 0; index < items.length; index++) {
                if (items[index].id === presetId) {
                    selectedPresetId = presetId
                    projectPresetName.text = items[index].name
                    projectPresetDescription.text = items[index].description
                    return
                }
            }
        }

        function savePreset(includeAll) {
            var success = includeAll
                    ? projectPresets.saveAll(projectPresetName.text, projectPresetDescription.text)
                    : projectPresets.saveCurrent(projectPresetName.text, projectPresetDescription.text)
            if (success) {
                showToast(includeAll ? "全部文档已保存为预设" : "当前文档已保存为预设")
                clearEditor()
            } else {
                showToast(projectPresets.lastError)
            }
        }

        Overlay.modal: Rectangle { color: Theme.overlayModal }
        background: Rectangle { color: Theme.bgPanel; border.width: 1; border.color: Theme.borderStrong }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Text { text: "项目预设"; color: Theme.textPrimary; font.family: Theme.displayFont; font.pixelSize: 17; font.weight: Font.DemiBold; Layout.fillWidth: true }
                TinyLabel { text: projectPresets.count + " 项" }
                IconButton { iconName: AppIcons.folderInput; tooltip: "导入预设"; buttonSize: 32; enabled: !workspace.operationsBlocked; onClicked: projectPresetImportDialog.open() }
                IconButton { iconName: AppIcons.folderOutput; tooltip: "导出全部预设"; buttonSize: 32; enabled: projectPresets.count > 0; onClicked: projectPresetExportAllDialog.open() }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 32; onClicked: projectPresetDrawer.close() }
            }
            TinyLabel { text: "保存当前或全部文档，加载时追加为新标签页"; color: Theme.textMuted }
            Divider { Layout.fillWidth: true }

            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(220, projectPresetDrawer.height - 500)
                clip: true
                spacing: 2
                model: projectPresets.presets

                delegate: Rectangle {
                    required property var modelData
                    width: ListView.view.width
                    height: 66
                    radius: Theme.radiusSmall
                    color: modelData.id === projectPresetDrawer.selectedPresetId ? Theme.accentSoft : (projectPresetMouse.containsMouse ? Theme.bgHover : "transparent")
                    border.width: modelData.id === projectPresetDrawer.selectedPresetId ? 1 : 0
                    border.color: Theme.accentPressed
                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 6
                        spacing: 8
                        Column {
                            Layout.fillWidth: true
                            spacing: 3
                            BodyLabel { text: modelData.name; color: Theme.textPrimary; width: parent.width; elide: Text.ElideRight }
                                TinyLabel {
                                    text: (modelData.canvasSizes.length > 0 ? modelData.canvasSizes.join(" / ") : (modelData.documentCount > 1 ? modelData.documentCount + " 个标签页" : "单文档预设"))
                                          + (modelData.totalLayers > 0 ? "  ·  " + modelData.totalLayers + " 图层" : "")
                                }
                            TinyLabel { text: modelData.description || "无描述"; width: parent.width; elide: Text.ElideRight }
                        }
                        IconButton {
                            iconName: AppIcons.folderOpen
                            tooltip: "追加加载为新标签页"
                            buttonSize: 32
                            onClicked: {
                                var loaded = projectPresets.loadPreset(modelData.id)
                                if (loaded > 0) {
                                    showToast("已加载 " + loaded + " 个标签页")
                                    projectPresetDrawer.close()
                                } else showToast(projectPresets.lastError)
                            }
                        }
                        IconButton {
                            iconName: AppIcons.copy
                            tooltip: "复制预设"
                            buttonSize: 32
                            onClicked: {
                                var duplicatedId = projectPresets.duplicatePreset(modelData.id)
                                if (duplicatedId.length > 0) {
                                    projectPresetDrawer.selectPreset(duplicatedId)
                                    showToast("预设已复制")
                                } else showToast(projectPresets.lastError)
                            }
                        }
                        IconButton {
                            iconName: AppIcons.folderOutput
                            tooltip: "导出预设"
                            buttonSize: 32
                            onClicked: projectPresetExportDialog.openForPreset(modelData.id, modelData.name)
                        }
                    }
                    MouseArea {
                        id: projectPresetMouse
                        anchors.fill: parent
                        anchors.rightMargin: 112
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: projectPresetDrawer.selectPreset(modelData.id)
                    }
                }
            }

            Item {
                Layout.fillWidth: true
                Layout.preferredHeight: 72
                visible: projectPresets.count === 0
                Column {
                    anchors.centerIn: parent
                    spacing: 5
                    BodyLabel { text: "还没有项目预设"; color: Theme.textPrimary; anchors.horizontalCenter: parent.horizontalCenter }
                    TinyLabel { text: "保存当前或全部文档，也可以导入已有预设"; anchors.horizontalCenter: parent.horizontalCenter }
                }
            }
            Divider { Layout.fillWidth: true }
            AppTextField {
                id: projectPresetName
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                placeholderText: "预设名称"
                color: Theme.textPrimary
                selectByMouse: true
                background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: projectPresetName.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
            }
            AppTextField {
                id: projectPresetDescription
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                placeholderText: "描述（可选）"
                color: Theme.textPrimary
                selectByMouse: true
                background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: projectPresetDescription.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
            }
            TinyLabel {
                Layout.fillWidth: true
                text: projectPresets.lastError
                color: Theme.danger
                visible: text.length > 0
                wrapMode: Text.Wrap
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                ExportButton {
                    Layout.fillWidth: true
                    label: "保存当前文档"
                    iconName: AppIcons.save
                    primary: true
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    onClicked: projectPresetDrawer.savePreset(false)
                }
                ExportButton {
                    Layout.fillWidth: true
                    label: "保存全部文档"
                    iconName: AppIcons.layers
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    onClicked: projectPresetDrawer.savePreset(true)
                }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                TinyLabel {
                    Layout.fillWidth: true
                    text: projectPresetDrawer.selectedPresetId.length > 0 ? "已选择预设，可更新信息或删除" : "选择预设后可更新信息"
                }
                IconButton {
                    iconName: AppIcons.shuffle
                    tooltip: "更新所选预设名称与描述"
                    buttonSize: 36
                    enabled: projectPresetDrawer.selectedPresetId.length > 0
                    onClicked: {
                        if (projectPresets.renamePreset(projectPresetDrawer.selectedPresetId, projectPresetName.text, projectPresetDescription.text)) {
                            showToast("预设信息已更新")
                        } else {
                            showToast(projectPresets.lastError)
                        }
                    }
                }
                IconButton {
                    iconName: AppIcons.trash
                    tooltip: "删除所选预设"
                    buttonSize: 36
                    enabled: projectPresetDrawer.selectedPresetId.length > 0
                    onClicked: {
                        presetDeleteConfirm.presetId = projectPresetDrawer.selectedPresetId
                        presetDeleteConfirm.presetName = projectPresetName.text
                        presetDeleteConfirm.open()
                    }
                }
            }
        }
    }

    AppDrawer {
        id: dataRelationsDrawer
        objectName: "dataRelationsDrawer"
        edge: Qt.RightEdge
        width: Math.min(460, Math.max(400, window.width * 0.29))
        height: window.height
        modal: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        property int activeTab: 0

        Overlay.modal: Rectangle { color: Theme.overlayModal }
        background: Rectangle { color: Theme.bgPanel; border.width: 1; border.color: Theme.borderStrong }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Text { text: "数据关系"; color: Theme.textPrimary; font.family: Theme.displayFont; font.pixelSize: 17; font.weight: Font.DemiBold; Layout.fillWidth: true }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 30; onClicked: dataRelationsDrawer.close() }
            }
            SegmentedControl {
                Layout.fillWidth: false
                Layout.preferredHeight: 34
                accessibleName: "数据关系类型"
                options: [
                    { label: "绑定组", value: 0 },
                    { label: "尺寸匹配", value: 1 }
                ]
                value: dataRelationsDrawer.activeTab
                onActivated: value => dataRelationsDrawer.activeTab = value
            }
            Divider { Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: dataRelationsDrawer.activeTab === 0
                spacing: 10
                RowLayout {
                    Layout.fillWidth: true
                    BodyLabel { text: "全局绑定"; color: Theme.textPrimary; Layout.fillWidth: true }
                    ToggleSwitch { accessibleName: "全局绑定"; checked: bindingManager.globalEnabled; onToggled: checked => bindingManager.setGlobalEnabled(checked) }
                }
                TinyLabel { text: "绑定图层会按相同分类共同随机取图或取文案"; Layout.fillWidth: true; wrapMode: Text.Wrap }
                ExportButton {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    label: "预览下一组"
                    iconName: AppIcons.shuffle
                    enabled: bindingManager.globalEnabled && bindingManager.groups.length > 0 && !workspace.operationsBlocked
                    onClicked: {
                        if (bindingManager.previewNextCombination() > 0)
                            showToast("已切换绑定组合")
                        else
                            showToast("当前绑定组没有可用组合")
                    }
                }
                ListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(160, dataRelationsDrawer.height - 470)
                    visible: bindingManager.groups.length > 0
                    clip: true
                    spacing: 3
                    model: bindingManager.groups
                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width
                        height: 64
                        radius: Theme.radiusSmall
                        color: Theme.bgControl
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 5
                            Column {
                                Layout.fillWidth: true
                                spacing: 3
                                BodyLabel { text: modelData.name; color: Theme.textPrimary }
                                TinyLabel { text: modelData.layerNames.join(" · "); width: parent.width; elide: Text.ElideRight }
                                TinyLabel {
                                    text: modelData.selectedCategory.length > 0
                                          ? "本次：" + modelData.selectedCategory
                                          : modelData.categoryCount + " 分类  ·  " + modelData.usedCombinations + " 已用组合"
                                    width: parent.width
                                    elide: Text.ElideRight
                                }
                            }
                    IconButton { iconName: AppIcons.history; tooltip: "重置组合历史"; buttonSize: 30; onClicked: bindingManager.resetCombinationHistory(modelData.id) }
                            IconButton { iconName: AppIcons.trash; tooltip: "删除绑定组"; buttonSize: 30; onClicked: bindingManager.deleteGroup(modelData.id) }
                        }
                    }
                }
                Item {
                    objectName: "bindingEmptyState"
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(140, dataRelationsDrawer.height - 470)
                    Layout.minimumHeight: 140
                    visible: bindingManager.groups.length === 0

                    Column {
                        anchors.centerIn: parent
                        width: Math.min(parent.width, 300)
                        spacing: 8

                        AppIcon {
                            anchors.horizontalCenter: parent.horizontalCenter
                            iconName: AppIcons.layers
                            iconSize: 24
                            iconColor: Theme.textMuted
                        }
                        BodyLabel {
                            width: parent.width
                            text: "请先选择至少 2 个图层"
                            color: Theme.textPrimary
                            horizontalAlignment: Text.AlignHCenter
                        }
                        TinyLabel {
                            width: parent.width
                            text: "关闭面板，在图层列表中按 Ctrl 或 Shift 多选后重新打开"
                            wrapMode: Text.Wrap
                            horizontalAlignment: Text.AlignHCenter
                        }
                        AppButton {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "返回选择图层"
                            iconName: AppIcons.layers
                            onClicked: dataRelationsDrawer.close()
                        }
                    }
                }
                Divider { Layout.fillWidth: true }
                TinyLabel { text: "当前选择 " + workspace.selectedLayerCount + " 个图层"; color: workspace.selectedLayerCount >= 2 ? Theme.accent : Theme.textMuted }
                RowLayout {
                    objectName: "bindingCreationFooter"
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    AppTextField {
                        id: bindingGroupName
                        Layout.fillWidth: true
                        Layout.preferredHeight: 36
                        placeholderText: "绑定组名称"
                        color: Theme.textPrimary
                        background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: bindingGroupName.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
                    }
                    ExportButton {
                        Layout.preferredWidth: 110
                        label: "建立绑定"
                        iconName: AppIcons.link
                        primary: true
                        enabled: workspace.selectedLayerCount >= 2 && bindingGroupName.text.length > 0
                        onClicked: {
                            if (bindingManager.createGroup(bindingGroupName.text, workspace.selectedLayerIndices).length > 0)
                                bindingGroupName.clear()
                            else showToast("绑定组名称重复或选择无效")
                        }
                    }
                }
            }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: dataRelationsDrawer.activeTab === 1
                spacing: 10
                RowLayout {
                    Layout.fillWidth: true
                    BodyLabel { text: "全局尺寸匹配"; color: Theme.textPrimary; Layout.fillWidth: true }
                    ToggleSwitch { accessibleName: "全局尺寸匹配"; checked: sizeMatch.globalEnabled; onToggled: checked => sizeMatch.setGlobalEnabled(checked) }
                }
                TinyLabel { text: "根据源图层孔位临时调整目标图层，预览和导出共用同一规则"; Layout.fillWidth: true; wrapMode: Text.Wrap }
                ListView {
                    Layout.fillWidth: true
                    Layout.preferredHeight: Math.max(160, dataRelationsDrawer.height - 570)
                    clip: true
                    spacing: 3
                    model: sizeMatch.relations
                    delegate: Rectangle {
                        required property var modelData
                        width: ListView.view.width
                        height: 60
                        radius: Theme.radiusSmall
                        color: Theme.bgControl
                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 5
                            Column {
                                Layout.fillWidth: true
                                spacing: 3
                                BodyLabel { text: modelData.sourceName + "  →  " + modelData.targetNames.join("、"); color: Theme.textPrimary; width: parent.width; elide: Text.ElideRight }
                                TinyLabel { text: "留白 " + modelData.padding + " px" + (modelData.autoMaskEnabled ? "  ·  自动遮罩" : "") + (modelData.autoRotate ? "  ·  自动旋转" : "") }
                            }
                            ToggleSwitch { accessibleName: "启用尺寸匹配关系"; checked: modelData.enabled; onToggled: checked => sizeMatch.setRelationEnabled(modelData.id, checked) }
                            IconButton { iconName: AppIcons.trash; tooltip: "删除关系"; buttonSize: 30; onClicked: sizeMatch.removeRelation(modelData.id) }
                        }
                    }
                }
                Divider { Layout.fillWidth: true }
                RowLayout {
                    Layout.fillWidth: true
                    BodyLabel { text: "源图层"; Layout.preferredWidth: 54 }
                    SelectBox {
                        id: sizeSourceSelect
                        Layout.fillWidth: false
                        model: sizeMatch.layerNames.map(function(name) { return { label: name, value: name } })
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    BodyLabel { text: "目标图层"; Layout.preferredWidth: 54 }
                    SelectBox {
                        id: sizeTargetSelect
                        Layout.fillWidth: false
                        model: sizeMatch.layerNames.map(function(name) { return { label: name, value: name } })
                    }
                    BodyLabel { text: "留白" }
                    AppTextField {
                        id: sizePaddingInput
                        Layout.preferredWidth: 58
                        Layout.preferredHeight: 34
                        text: "1"
                        color: Theme.textPrimary
                        horizontalAlignment: Text.AlignHCenter
                        validator: IntValidator { bottom: 0; top: 1000 }
                        background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: sizePaddingInput.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 6

                    OptionTile {
                        id: oneToManyOption
                        compact: true
                        title: "一对多"
                        detail: "一个源匹配多个目标"
                        onActivated: selected = !selected
                    }
                    OptionTile {
                        id: autoRotateOption
                        compact: true
                        title: "自动旋转"
                        detail: "按孔位方向调整素材"
                        onActivated: selected = !selected
                    }
                    OptionTile {
                        id: autoMaskOption
                        compact: true
                        title: "自动遮罩"
                        detail: "按透明边缘生成遮罩"
                        onActivated: selected = !selected
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: autoMaskOption.selected
                    BodyLabel { text: "阈值"; Layout.preferredWidth: 40 }
                    AppTextField {
                        id: maskThresholdInput
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        text: "32"
                        color: Theme.textPrimary
                        validator: IntValidator { bottom: 0; top: 255 }
                        background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: Theme.borderStrong; radius: Theme.radiusSmall }
                    }
                    BodyLabel { text: "容差"; Layout.preferredWidth: 40 }
                    AppTextField {
                        id: maskToleranceInput
                        Layout.fillWidth: true
                        Layout.preferredHeight: 34
                        text: "18"
                        color: Theme.textPrimary
                        validator: IntValidator { bottom: 0; top: 255 }
                        background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: Theme.borderStrong; radius: Theme.radiusSmall }
                    }
                }
                ExportButton {
                    Layout.fillWidth: true
                    label: "添加尺寸匹配关系"
                    iconName: AppIcons.add
                    primary: true
                    enabled: sizeSourceSelect.currentValue !== sizeTargetSelect.currentValue && sizeMatch.layerNames.length >= 2
                    onClicked: {
                        var relationId = sizeMatch.addRelation(
                            sizeSourceSelect.currentValue,
                            [sizeTargetSelect.currentValue],
                            parseInt(sizePaddingInput.text),
                            oneToManyOption.selected,
                            autoRotateOption.selected,
                            autoMaskOption.selected,
                            parseInt(maskThresholdInput.text),
                            parseInt(maskToleranceInput.text)
                        )
                        if (relationId.length === 0) showToast("尺寸匹配关系无效或已存在")
                    }
                }
            }
        }
    }

    AppDrawer {
        id: canvasPresetDrawer
        objectName: "canvasPresetDrawer"
        edge: Qt.RightEdge
        width: Math.min(420, Math.max(360, window.width * 0.27))
        height: window.height
        modal: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0
        property int selectedPresetIndex: -1

        Overlay.modal: Rectangle { color: Theme.overlayModal }
        background: Rectangle { color: Theme.bgPanel; border.width: 1; border.color: Theme.borderStrong }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Text { text: "画布预设"; color: Theme.textPrimary; font.family: Theme.displayFont; font.pixelSize: 17; font.weight: Font.DemiBold; Layout.fillWidth: true }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 30; onClicked: canvasPresetDrawer.close() }
            }
            TinyLabel { text: "当前画布  " + workspace.canvasWidth + " x " + workspace.canvasHeight }
            Divider { Layout.fillWidth: true }

            ListView {
                id: canvasPresetList
                Layout.fillWidth: true
                Layout.preferredHeight: Math.max(240, canvasPresetDrawer.height - 500)
                clip: true
                spacing: 4
                model: canvasPresets.presets
                currentIndex: canvasPresetDrawer.selectedPresetIndex

                delegate: Rectangle {
                    required property int index
                    required property var modelData
                    width: ListView.view.width
                    height: 52
                    radius: Theme.radiusSmall
                    color: index === canvasPresetDrawer.selectedPresetIndex ? Theme.accentSoft : (presetRowMouse.containsMouse ? Theme.bgHover : "transparent")
                    border.width: index === canvasPresetDrawer.selectedPresetIndex ? 1 : 0
                    border.color: Theme.accentPressed

                    RowLayout {
                        anchors.fill: parent
                        anchors.leftMargin: 10
                        anchors.rightMargin: 6
                        spacing: 8
                        Column {
                            Layout.fillWidth: true
                            spacing: 2
                            BodyLabel { text: modelData.name; color: Theme.textPrimary; width: parent.width; elide: Text.ElideRight }
                            TinyLabel { text: modelData.width + " x " + modelData.height + "  ·  " + modelData.category }
                        }
                        TinyLabel { text: modelData.is_builtin ? "内置" : "自定义"; color: modelData.is_builtin ? Theme.textMuted : Theme.accent }
                        IconButton {
                            iconName: AppIcons.check
                            tooltip: "应用预设"
                            buttonSize: 30
                            onClicked: {
                                canvasPresets.applyPreset(index)
                                canvasPresetDrawer.close()
                            }
                        }
                    }
                    MouseArea {
                        id: presetRowMouse
                        anchors.fill: parent
                        anchors.rightMargin: 38
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            canvasPresetDrawer.selectedPresetIndex = index
                            presetNameInput.text = modelData.name
                            presetWidthInput.text = String(modelData.width)
                            presetHeightInput.text = String(modelData.height)
                        }
                    }
                }
            }

            Divider { Layout.fillWidth: true }
            AppTextField {
                id: presetNameInput
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                placeholderText: "预设名称"
                color: Theme.textPrimary
                selectByMouse: true
                background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: presetNameInput.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
            }
            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                AppTextField {
                    id: presetWidthInput
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    text: String(workspace.canvasWidth)
                    placeholderText: "宽度"
                    color: Theme.textPrimary
                    validator: IntValidator { bottom: 16; top: 32768 }
                    background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: presetWidthInput.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
                }
                TinyLabel { text: "x" }
                AppTextField {
                    id: presetHeightInput
                    Layout.fillWidth: true
                    Layout.preferredHeight: 36
                    text: String(workspace.canvasHeight)
                    placeholderText: "高度"
                    color: Theme.textPrimary
                    validator: IntValidator { bottom: 16; top: 32768 }
                    background: Rectangle { color: Theme.bgControl; border.width: 1; border.color: presetHeightInput.activeFocus ? Theme.accent : Theme.borderStrong; radius: Theme.radiusSmall }
                }
            }
            RowLayout {
                Layout.fillWidth: true
                ExportButton {
                    Layout.fillWidth: true
                    label: "新建预设"
                    iconName: AppIcons.add
                    primary: true
                    onClicked: {
                        if (!canvasPresets.createPreset(presetNameInput.text, parseInt(presetWidthInput.text), parseInt(presetHeightInput.text)))
                            showToast("名称已存在或尺寸无效")
                    }
                }
                IconButton {
                    iconName: AppIcons.refresh
                    tooltip: "更新所选自定义预设"
                    buttonSize: 36
                    enabled: canvasPresetDrawer.selectedPresetIndex >= 0
                             && !canvasPresets.presets[canvasPresetDrawer.selectedPresetIndex].is_builtin
                    onClicked: {
                        var selected = canvasPresets.presets[canvasPresetDrawer.selectedPresetIndex]
                        if (!canvasPresets.renamePreset(selected.name, presetNameInput.text, parseInt(presetWidthInput.text), parseInt(presetHeightInput.text)))
                            showToast("无法更新预设")
                    }
                }
                IconButton {
                    iconName: AppIcons.trash
                    tooltip: "删除所选自定义预设"
                    buttonSize: 36
                    enabled: canvasPresetDrawer.selectedPresetIndex >= 0
                             && !canvasPresets.presets[canvasPresetDrawer.selectedPresetIndex].is_builtin
                    onClicked: {
                        var selected = canvasPresets.presets[canvasPresetDrawer.selectedPresetIndex]
                        if (canvasPresets.deletePreset(selected.name)) {
                            canvasPresetDrawer.selectedPresetIndex = -1
                            presetNameInput.clear()
                        }
                    }
                }
            }
        }
    }

    AppDialog {
        id: closeConfirmDialog
        anchors.centerIn: parent
        width: 430
        height: 180
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape
        onRejected: {
            pendingUpdateInstall = false
            workspaceSessions.cancelClose()
        }

        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
            radius: Theme.radius
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            spacing: 18
            anchors.margins: 22
            Text {
                text: "保存对文档的更改？"
                color: Theme.textPrimary
                font.family: Theme.displayFont
                font.pixelSize: 16
                font.weight: Font.DemiBold
            }
            Text {
                Layout.fillWidth: true
                text: pendingCloseTitle
                color: Theme.textSecondary
                font.family: Theme.bodyFont
                font.pixelSize: 12
                elide: Text.ElideMiddle
            }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                ExportButton { Layout.preferredWidth: 86; label: "取消"; onClicked: { pendingUpdateInstall = false; workspaceSessions.cancelClose(); closeConfirmDialog.close() } }
                Item { Layout.fillWidth: true }
                ExportButton { Layout.preferredWidth: 96; label: "不保存"; destructive: true; onClicked: { workspaceSessions.discardAndClose(workspaceSessions.pendingCloseIndex); closeConfirmDialog.close() } }
                ExportButton { Layout.preferredWidth: 104; label: "保存"; iconName: AppIcons.save; primary: true; onClicked: { closeConfirmDialog.close(); workspaceSessions.saveAndClose(workspaceSessions.pendingCloseIndex, "") } }
            }
        }
    }

    FileDialog {
        id: saveDialog
        title: "保存批图王项目"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "cmp"
        nameFilters: ["批图王项目 (*.cmp)"]
        onAccepted: workspace.saveDocumentTo(selectedFile.toString())
    }

    FileDialog {
        id: exportDialog
        title: "导出当前画面"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "png"
        nameFilters: ["PNG 图片 (*.png)", "JPEG 图片 (*.jpg *.jpeg)", "WebP 图片 (*.webp)"]
        onAccepted: workspace.exportImageTo(selectedFile.toString())
    }

    FileDialog {
        id: imageDialog
        title: "添加图片图层"
        fileMode: FileDialog.OpenFile
        nameFilters: ["图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"]
        onAccepted: workspace.addImageLayer(selectedFile.toString())
    }

    FileDialog {
        id: projectPresetImportDialog
        title: "导入项目预设"
        fileMode: FileDialog.OpenFile
        nameFilters: ["预设文件 (*.preset *.pst)", "所有文件 (*)"]
        onAccepted: {
            var imported = projectPresets.importPreset(selectedFile.toString())
            showToast(imported > 0 ? "已导入 " + imported + " 个预设" : projectPresets.lastError)
        }
    }

    FileDialog {
        id: projectPresetExportDialog
        title: "导出项目预设"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "preset"
        nameFilters: ["预设文件 (*.preset)"]
        property string presetId: ""

        function openForPreset(presetId, presetName) {
            projectPresetExportDialog.presetId = presetId
            title = "导出项目预设 · " + presetName
            open()
        }

        onAccepted: {
            var success = projectPresets.exportPreset(presetId, selectedFile.toString())
            showToast(success ? "预设已导出" : projectPresets.lastError)
        }
    }

    FileDialog {
        id: projectPresetExportAllDialog
        title: "导出全部项目预设"
        fileMode: FileDialog.SaveFile
        defaultSuffix: "preset"
        nameFilters: ["预设合集 (*.preset)"]
        onAccepted: {
            var exported = projectPresets.exportAll(selectedFile.toString())
            showToast(exported > 0 ? "已导出 " + exported + " 个预设" : projectPresets.lastError)
        }
    }

    FileDialog {
        id: shapedLayerSourceFileDialog
        title: "选择异形图层图片"
        fileMode: FileDialog.OpenFile
        nameFilters: ["图片文件 (*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff)"]
        onAccepted: {
            shapedLayerDialog.sourceMode = "file"
            shapedLayerSourceInput.text = selectedFile.toString()
        }
    }

    FolderDialog {
        id: shapedLayerSourceFolderDialog
        title: "选择异形图层素材文件夹"
        onAccepted: {
            shapedLayerDialog.sourceMode = "folder"
            shapedLayerSourceInput.text = selectedFolder.toString()
        }
    }

    AppMenu {
        id: fileMenu
        ShapeMenuItem { text: "新建画布\tCtrl+N"; enabled: !workspace.operationsBlocked; onTriggered: window.openNewCanvasDialog() }
        ShapeMenuItem { text: "打开项目\tCtrl+O"; onTriggered: openDialog.open() }
        MenuSeparator { }
        ShapeMenuItem { text: "保存\tCtrl+S"; enabled: window.hasOpenDocument; onTriggered: workspace.hasFilePath ? workspace.saveDocument() : saveDialog.open() }
        ShapeMenuItem { text: "另存为\tCtrl+Shift+S"; enabled: window.hasOpenDocument; onTriggered: saveDialog.open() }
        MenuSeparator { }
        ShapeMenuItem { text: "关闭当前标签\tCtrl+W"; enabled: window.hasOpenDocument; onTriggered: workspaceSessions.requestClose(workspaceSessions.activeIndex) }
        ShapeMenuItem { text: "复制当前标签\tAlt+Shift+D"; enabled: window.hasOpenDocument; onTriggered: workspaceSessions.duplicateDocument(workspaceSessions.activeIndex) }
        MenuSeparator { }
        ShapeMenuItem { text: "导出当前画面\tCtrl+Shift+X"; enabled: window.hasOpenDocument; onTriggered: exportDialog.open() }
        ShapeMenuItem { text: "完整批量导出\tF12"; enabled: window.hasOpenDocument && (!workspace.operationsBlocked || batchExport.running); onTriggered: window.openBatchExportDrawer() }
        ShapeMenuItem { text: "多标签高级导出\tCtrl+Alt+Shift+X"; enabled: window.hasOpenDocument && (!workspace.operationsBlocked || multiTabExport.running); onTriggered: window.openMultiTabExportDrawer() }
        MenuSeparator { }
        ShapeMenuItem { text: "退出"; onTriggered: window.close() }
    }

    AppMenu {
        id: editMenu
        ShapeMenuItem { text: "撤销\tCtrl+Z"; enabled: workspace.canUndo; onTriggered: workspace.undo() }
        ShapeMenuItem { text: "重做\tCtrl+Shift+Z"; enabled: workspace.canRedo; onTriggered: workspace.redo() }
        ShapeMenuItem { text: "后退一步\tCtrl+Alt+Z"; enabled: workspace.canUndo; onTriggered: workspace.undo() }
        MenuSeparator { }
        ShapeMenuItem { text: "复制图层\tCtrl+C"; enabled: workspace.selectedLayerIndex >= 0; onTriggered: legacyTools.copySelectedLayers() }
        ShapeMenuItem { text: "粘贴图层\tCtrl+V"; enabled: window.hasOpenDocument && legacyTools.hasLayerClipboard; onTriggered: legacyTools.pasteLayers() }
        ShapeMenuItem { text: "复制图层样式\tCtrl+Shift+C"; enabled: workspace.selectedLayerIndex >= 0; onTriggered: workspace.copySelectedLayerStyle() }
        ShapeMenuItem { text: "粘贴图层样式\tCtrl+Shift+V"; enabled: workspace.selectedLayerIndex >= 0; onTriggered: workspace.pasteSelectedLayerStyle() }
        ShapeMenuItem { text: "复制选中图层到新图层\tCtrl+J"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0; onTriggered: workspace.duplicateSelectedLayers() }
        MenuSeparator { }
        ShapeMenuItem { text: "全选图层\tCtrl+A"; enabled: window.hasOpenDocument; onTriggered: legacyTools.selectAllLayers() }
    }

    AppMenu {
        id: layerMenu
        ShapeMenuItem { text: "新建空图片图层\tShift+Ctrl+N"; enabled: window.hasOpenDocument; onTriggered: workspace.addEmptyImageLayer() }
        ShapeMenuItem { text: "导入图片为图层"; enabled: window.hasOpenDocument; onTriggered: imageDialog.open() }
        ShapeMenuItem { text: "导入素材文件夹"; enabled: window.hasOpenDocument; onTriggered: imageFolderDialog.open() }
        ShapeMenuItem { text: "添加文字图层\tShift+F8"; enabled: window.hasOpenDocument; onTriggered: textLayerDialog.openFresh() }
        ShapeMenuItem { text: "添加异形图层"; enabled: window.hasOpenDocument; onTriggered: shapedLayerDialog.openFresh() }
        MenuSeparator { }
        ShapeMenuItem { text: "自由变换\tCtrl+T"; enabled: workspace.selectedLayerIndex >= 0; onTriggered: workspace.beginFreeTransform() }
        ShapeMenuItem { text: "向下合并图层(编组)\tCtrl+E"; enabled: workspace.selectedLayerIndex >= 1; onTriggered: workspace.mergeSelectedDown() }
        ShapeMenuItem { text: "图层编组\tCtrl+G"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0; onTriggered: workspace.groupSelectedLayers() }
        ShapeMenuItem { text: "取消图层编组\tCtrl+Shift+G"; enabled: window.hasOpenDocument; onTriggered: workspace.ungroupSelectedGroups() }
        MenuSeparator { }
        ShapeMenuItem { text: "重命名图层\tF2"; enabled: workspace.selectedLayerIndex >= 0; onTriggered: window.revealLayerNameEditor() }
        ShapeMenuItem { text: "图层下移一层\tCtrl+["; enabled: workspace.selectedLayerIndex >= 0; onTriggered: workspace.moveSelectedLayer("backward") }
        ShapeMenuItem { text: "图层上移一层\tCtrl+]"; enabled: workspace.selectedLayerIndex >= 0; onTriggered: workspace.moveSelectedLayer("forward") }
        ShapeMenuItem { text: "图层置于底层\tCtrl+Shift+["; enabled: workspace.selectedLayerIndex >= 0; onTriggered: workspace.moveSelectedLayer("to_back") }
        ShapeMenuItem { text: "图层置于顶层\tCtrl+Shift+]"; enabled: workspace.selectedLayerIndex >= 0; onTriggered: workspace.moveSelectedLayer("to_front") }
        ShapeMenuItem { text: "高级图层属性"; enabled: workspace.selectedLayerIndex >= 0; onTriggered: window.revealAdvancedProperties() }
        ShapeMenuItem { text: "绑定管理"; enabled: window.hasOpenDocument && !workspace.operationsBlocked; onTriggered: window.openDataRelations(0) }
        ShapeMenuItem { text: "尺寸匹配管理"; enabled: window.hasOpenDocument && !workspace.operationsBlocked; onTriggered: window.openDataRelations(1) }
        MenuSeparator { }
        ShapeMenuItem { text: "删除所选图层\tDelete"; enabled: workspace.selectedLayerIndex >= 0; onTriggered: workspace.deleteSelectedLayers() }
    }

    AppMenu {
        id: canvasMenu
        ShapeMenuItem { text: "修改画布尺寸(Canvas Size)\tAlt+Ctrl+C"; enabled: window.hasOpenDocument && !workspace.operationsBlocked; onTriggered: window.openResizeCanvasDialog() }
        ShapeMenuItem { text: "画布预设管理"; enabled: window.hasOpenDocument && !workspace.operationsBlocked; onTriggered: window.openCanvasPresetDrawer() }
        MenuSeparator { }
        ShapeMenuItem { text: "项目预设中心\tCtrl+Shift+P"; enabled: !workspace.operationsBlocked; onTriggered: window.openProjectPresetDrawer() }
    }

    AppMenu {
        id: viewMenu
        ShapeMenuItem { text: "切换标尺显示\tCtrl+R"; enabled: window.hasOpenDocument; onTriggered: workspace.toggleRulers() }
        ShapeMenuItem { text: "切换参考线\t;"; enabled: window.hasOpenDocument; onTriggered: workspace.toggleGuides() }
        MenuSeparator { }
        ShapeMenuItem { text: "放大\tCtrl++"; enabled: window.hasOpenDocument; onTriggered: workspace.setZoomFactor(workspace.zoomFactor + 0.05) }
        ShapeMenuItem { text: "缩小\tCtrl+-"; enabled: window.hasOpenDocument; onTriggered: workspace.setZoomFactor(workspace.zoomFactor - 0.05) }
        ShapeMenuItem { text: "实际大小 100%\tCtrl+0"; enabled: window.hasOpenDocument; onTriggered: workspace.resetView() }
        ShapeMenuItem { text: "适合窗口"; enabled: window.hasOpenDocument; onTriggered: workspace.setZoomFactor(canvasWorkspace.fitScale) }
        MenuSeparator { }
        ShapeMenuItem { text: (workspace.showRulers ? "✓  " : "    ") + "显示标尺"; enabled: window.hasOpenDocument; onTriggered: workspace.setShowRulers(!workspace.showRulers) }
        ShapeMenuItem { text: (workspace.showGuides ? "✓  " : "    ") + "显示参考线"; enabled: window.hasOpenDocument; onTriggered: workspace.setShowGuides(!workspace.showGuides) }
        ShapeMenuItem { text: (workspace.snapToGuides ? "✓  " : "    ") + "吸附到参考线"; enabled: window.hasOpenDocument; onTriggered: workspace.setSnapToGuides(!workspace.snapToGuides) }
        ShapeMenuItem { text: "清空参考线"; enabled: window.hasOpenDocument; onTriggered: workspace.clearGuides() }
    }

    AppMenu {
        id: helpMenu
        ShapeMenuItem { text: "检查更新"; onTriggered: window.openUpdateDialog() }
        MenuSeparator { }
        ShapeMenuItem { text: "关于批图王"; onTriggered: window.openAboutDialog() }
    }

    AppDialog {
        id: updateDialog
        objectName: "updateDialog"
        anchors.centerIn: parent
        width: 460
        height: 440
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape

        onOpened: {
            if (!updateManager.downloading && !updateManager.checking && !updateManager.updateAvailable && updateManager.errorMessage.length === 0)
                updateManager.checkForUpdates()
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            spacing: 14
            anchors.margins: 20

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "检查更新"
                    color: Theme.textPrimary
                    font.family: Theme.displayFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 28; onClicked: updateDialog.close() }
            }

            Divider { Layout.fillWidth: true }

            RowLayout {
                Layout.fillWidth: true
                spacing: 16
                Column {
                    Layout.fillWidth: true
                    spacing: 4
                    BodyLabel { text: "当前版本"; color: Theme.textMuted }
                    BodyLabel { text: "v" + updateManager.currentVersion; color: Theme.textPrimary; font.weight: Font.DemiBold }
                }
                AppIcon { iconName: AppIcons.refresh; iconSize: 16; iconColor: Theme.textMuted }
                Column {
                    Layout.fillWidth: true
                    spacing: 4
                    BodyLabel { text: "最新版本"; color: Theme.textMuted }
                    BodyLabel {
                        text: updateManager.latestVersion.length > 0 ? "v" + updateManager.latestVersion : "-"
                        color: updateManager.updateAvailable ? Theme.accent : Theme.textPrimary
                        font.weight: Font.DemiBold
                    }
                }
            }

            StatusBanner {
                Layout.fillWidth: true
                Layout.preferredHeight: updateManager.errorMessage.length > 0 ? 56 : 0
                visible: updateManager.errorMessage.length > 0
                tone: "error"
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    AppIcon { iconName: AppIcons.error; iconSize: 15; iconColor: Theme.coral }
                    BodyLabel { text: updateManager.errorMessage; color: Theme.textPrimary; Layout.fillWidth: true; wrapMode: Text.Wrap }
                }
            }

            StatusBanner {
                Layout.fillWidth: true
                Layout.preferredHeight: updateManager.checking ? 44 : 0
                visible: updateManager.checking
                tone: "neutral"
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    AppIcon { iconName: AppIcons.info; iconSize: 15; iconColor: Theme.accent }
                    BodyLabel { text: "正在检查更新…"; color: Theme.textPrimary }
                }
            }

            StatusBanner {
                Layout.fillWidth: true
                Layout.preferredHeight: updateManager.readyToInstall ? 56 : 0
                visible: updateManager.readyToInstall
                tone: "neutral"
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    AppIcon { iconName: AppIcons.info; iconSize: 15; iconColor: Theme.accent }
                    BodyLabel {
                        text: "新版已下载，保存当前工作后即可安装并重启"
                        color: Theme.textPrimary
                        Layout.fillWidth: true
                        wrapMode: Text.Wrap
                    }
                }
            }

            Column {
                Layout.fillWidth: true
                Layout.fillHeight: true
                visible: updateManager.updateAvailable
                spacing: 8
                BodyLabel { text: "更新说明"; color: Theme.textPrimary; font.weight: Font.DemiBold }
                Rectangle {
                    width: parent.width
                    Layout.fillWidth: true
                    height: 150
                    radius: Theme.radiusSmall
                    color: Theme.bgControl
                    border.width: 1
                    border.color: Theme.borderStrong
                    clip: true
                    Flickable {
                        id: releaseNotesScroller
                        anchors.fill: parent
                        anchors.margins: 10
                        contentHeight: releaseNotesText.height
                        clip: true
                        ScrollBar.vertical: ScrollBar { }
                        Text {
                            id: releaseNotesText
                            width: releaseNotesScroller.width - 20
                            text: updateManager.releaseNotes
                            color: Theme.textSecondary
                            font.family: Theme.bodyFont
                            font.pixelSize: 12
                            wrapMode: Text.Wrap
                        }
                    }
                }
            }

            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton {
                    label: "打开下载页"
                    visible: updateManager.updateAvailable && !updateManager.downloading && !updateManager.readyToInstall
                    onClicked: updateManager.openReleasePage()
                }
                ExportButton {
                    label: updateManager.downloading
                           ? "正在下载…"
                           : (updateManager.readyToInstall ? "立即安装并重启" : "下载更新")
                    primary: updateManager.updateAvailable && !updateManager.downloading
                    enabled: updateManager.updateAvailable && !updateManager.downloading
                    onClicked: {
                        if (updateManager.readyToInstall) {
                            pendingUpdateInstall = true
                            updateDialog.close()
                            var closeStarted = workspaceSessions.requestApplicationClose()
                            if (!closeStarted && !workspaceSessions.applicationClosePending) {
                                pendingUpdateInstall = false
                                updateDialog.open()
                            }
                        } else {
                            updateManager.downloadAndInstall()
                        }
                    }
                }
                ExportButton {
                    label: "关闭"
                    enabled: !updateManager.downloading
                    onClicked: updateDialog.close()
                }
            }

            Column {
                Layout.fillWidth: true
                visible: updateManager.downloading
                spacing: 6
                RowLayout {
                    Layout.fillWidth: true
                    TinyLabel { text: updateManager.progressText; color: Theme.textSecondary; Layout.fillWidth: true }
                    TinyLabel { text: updateManager.downloadProgress + "%"; color: Theme.textSecondary }
                }
                AppProgressBar {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 5
                    progress: updateManager.downloadProgress / 100
                    tone: "accent"
                }
            }
        }
    }

    AppDialog {
        id: aboutDialog
        objectName: "aboutDialog"
        anchors.centerIn: parent
        width: 380
        height: 220
        modal: true
        focus: true
        closePolicy: Popup.CloseOnEscape

        contentItem: ColumnLayout {
            anchors.fill: parent
            spacing: 10
            anchors.margins: 24

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "关于批图王"
                    color: Theme.textPrimary
                    font.family: Theme.displayFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 28; onClicked: aboutDialog.close() }
            }

            Divider { Layout.fillWidth: true }

            BodyLabel { text: "批图王"; color: Theme.textPrimary; font.pixelSize: 20; font.weight: Font.DemiBold }
            BodyLabel { text: "版本 v" + updateManager.currentVersion; color: Theme.textSecondary }
            BodyLabel { text: "图像批量合成与批量导出工具"; color: Theme.textMuted }

            Item { Layout.fillHeight: true }

            ExportButton {
                Layout.fillWidth: true
                Layout.preferredHeight: 36
                label: "确定"
                onClicked: aboutDialog.close()
            }
        }
    }

    AppMenu {
        id: documentTabMenu
        ShapeMenuItem { text: "复制标签页"; onTriggered: workspaceSessions.duplicateDocument(contextDocumentIndex) }
        ShapeMenuItem {
            text: "重命名标签页"
            onTriggered: window.openRenameDocumentDialog(contextDocumentIndex)
        }
        MenuSeparator { }
        ShapeMenuItem { text: "向左移动"; enabled: contextDocumentIndex > 0; onTriggered: workspaceSessions.moveDocument(contextDocumentIndex, contextDocumentIndex - 1) }
        ShapeMenuItem { text: "向右移动"; enabled: contextDocumentIndex >= 0 && contextDocumentIndex < workspaceSessions.count - 1; onTriggered: workspaceSessions.moveDocument(contextDocumentIndex, contextDocumentIndex + 1) }
        MenuSeparator { }
        ShapeMenuItem { text: "关闭其他标签页"; enabled: workspaceSessions.count > 1; onTriggered: workspaceSessions.closeOtherDocuments(contextDocumentIndex) }
        ShapeMenuItem { text: "关闭标签页"; onTriggered: workspaceSessions.requestClose(contextDocumentIndex) }
        ShapeMenuItem { text: "恢复导出面板"; onTriggered: window.restoreExportSurface(contextDocumentIndex) }
    }

    FolderDialog {
        id: imageFolderDialog
        title: "添加素材文件夹"
        onAccepted: workspace.addImageFolder(selectedFolder.toString())
    }

    FileDialog {
        id: replaceImageDialog
        title: "替换图片源"
        fileMode: FileDialog.OpenFile
        nameFilters: ["图片文件 (*.png *.jpg *.jpeg *.bmp *.gif *.tif *.tiff)"]
        onAccepted: workspace.setSelectedImageSource(selectedFile.toString())
    }

    FolderDialog {
        id: replaceImageFolderDialog
        title: "选择素材文件夹"
        onAccepted: workspace.setSelectedImageSource(selectedFolder.toString())
    }

    FolderDialog {
        id: outputFolderDialog
        title: "选择批量导出目录"
        onAccepted: batchExport.outputDirectory = selectedFolder.toString()
    }

    FolderDialog {
        id: multiOutputFolderDialog
        title: "选择多标签批量导出目录"
        onAccepted: multiTabExport.outputDirectory = selectedFolder.toString()
    }

    AppDialog {
        id: effectColorDialog
        objectName: "effectColorDialog"
        anchors.centerIn: parent
        width: Math.min(820, Math.max(740, window.width - 96))
        height: Math.min(590, Math.max(550, window.height - 96))
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape
        header: null
        footer: null
        property string target: "stroke"
        property int colorIndex: 0
        property int rangeStart: 0
        property int rangeEnd: 0
        property string editorHtml: ""
        property string errorMessage: ""
        property color currentColor: "#000000"
        property real hue: 0
        property real saturation: 0
        property real brightness: 0
        property real alphaValue: 1
        readonly property color selectedColor: Qt.hsva(hue, saturation, brightness, alphaValue)

        title: {
            if (target === "stroke") return "选择描边颜色"
            if (target === "overlay") return "选择叠加颜色"
            if (target === "textFill") return "选择文字颜色"
            if (target === "textBackground") return "选择文字背景颜色"
            if (target === "textShadow") return "选择文字阴影颜色"
            if (target === "textGlow") return "选择文字发光颜色"
            if (target === "textRange") return "选择选区文字颜色"
            if (target === "canvasTextRange") return "选择选区文字颜色"
            return "选择渐变颜色"
        }

        function openFor(targetName, colorValue, index, start, end) {
            target = targetName
            colorIndex = index === undefined ? 0 : index
            rangeStart = start === undefined ? 0 : start
            rangeEnd = end === undefined ? 0 : end
            editorHtml = ""
            currentColor = window.hexToColor(colorValue || "#000000")
            setFromColor(currentColor)
            errorMessage = ""
            open()
        }

        function openForTextEditor(colorValue, start, end, html) {
            target = "canvasTextRange"
            colorIndex = 0
            rangeStart = start
            rangeEnd = end
            editorHtml = html
            currentColor = window.hexToColor(colorValue || workspace.selectedTextColor)
            setFromColor(currentColor)
            errorMessage = ""
            open()
        }

        function clamp(value, minimum, maximum) {
            return Math.max(minimum, Math.min(maximum, value))
        }

        function hexByte(value) {
            var text = Math.round(clamp(value, 0, 255)).toString(16).toUpperCase()
            return text.length < 2 ? "0" + text : text
        }

        function colorToHex(colorValue) {
            var result = "#" + hexByte(colorValue.r * 255)
                    + hexByte(colorValue.g * 255)
                    + hexByte(colorValue.b * 255)
            if (colorValue.a < 0.999) result += hexByte(colorValue.a * 255)
            return result
        }

        function setFromColor(colorValue) {
            var nextHue = colorValue.hsvHue
            if (nextHue >= 0) hue = nextHue
            saturation = colorValue.hsvSaturation
            brightness = colorValue.hsvValue
            alphaValue = colorValue.a
            effectColorInput.value = colorToHex(colorValue)
            errorMessage = ""
        }

        function setFromHex(textValue) {
            var hexValue = String(textValue || "").trim().toUpperCase()
            if (hexValue.charAt(0) !== "#") hexValue = "#" + hexValue
            if (!/^#[0-9A-F]{6}([0-9A-F]{2})?$/.test(hexValue)) {
                errorMessage = "请输入 #RRGGBB 或 #RRGGBBAA 格式"
                return false
            }
            setFromColor(window.hexToColor(hexValue))
            return true
        }

        function setHsv(nextHue, nextSaturation, nextBrightness) {
            if (isNaN(nextHue)) nextHue = hue
            if (isNaN(nextSaturation)) nextSaturation = saturation
            if (isNaN(nextBrightness)) nextBrightness = brightness
            hue = clamp(nextHue, 0, 1)
            saturation = clamp(nextSaturation, 0, 1)
            brightness = clamp(nextBrightness, 0, 1)
            effectColorInput.value = colorToHex(selectedColor)
            errorMessage = ""
        }

        function setRgb(red, green, blue) {
            if (isNaN(red)) red = selectedColor.r * 255
            if (isNaN(green)) green = selectedColor.g * 255
            if (isNaN(blue)) blue = selectedColor.b * 255
            setFromColor(Qt.rgba(
                clamp(red, 0, 255) / 255,
                clamp(green, 0, 255) / 255,
                clamp(blue, 0, 255) / 255,
                alphaValue
            ))
        }

        function setAlpha(alpha) {
            if (isNaN(alpha)) return
            alphaValue = clamp(alpha, 0, 255) / 255
            effectColorInput.value = colorToHex(selectedColor)
            errorMessage = ""
        }

        function selectPaletteColor(hexValue) {
            var preset = window.hexToColor(hexValue)
            setFromColor(Qt.rgba(preset.r, preset.g, preset.b, alphaValue))
        }

        function applyColor() {
            if (!setFromHex(effectColorInput.text)) return
            var hexValue = colorToHex(selectedColor)
            var targetName = target
            if (target === "stroke") workspace.setSelectedStrokeColor(hexValue)
            else if (target === "overlay") workspace.setSelectedColorOverlayColor(hexValue)
            else if (target === "textFill") workspace.setSelectedTextColor(hexValue)
            else if (target === "textGradient") workspace.setSelectedTextGradientColor(colorIndex, hexValue)
            else if (target === "textBackground") workspace.setSelectedTextBackgroundColor(hexValue)
            else if (target === "textShadow") workspace.setSelectedTextShadowColor(hexValue)
            else if (target === "textGlow") workspace.setSelectedTextGlowColor(hexValue)
            else if (target === "textRange") workspace.setSelectedTextColorRangeQt(rangeStart, rangeEnd, hexValue)
            else if (target === "canvasTextRange") {
                var updatedHtml = workspace.applyTextEditorColor(
                    editorHtml,
                    rangeStart,
                    rangeEnd,
                    hexValue
                )
                canvasTextEditOverlay.replaceFormattedText(updatedHtml, rangeStart, rangeEnd)
            }
            else workspace.setSelectedGradientOverlayColor(colorIndex, hexValue)
            close()
            if (targetName === "canvasTextRange") {
                Qt.callLater(function() {
                    window.focusCanvasTextEditor()
                    canvasTextEditInput.select(rangeStart, rangeEnd)
                })
            }
        }

        onClosed: {
            if (target === "canvasTextRange" && workspace.textEditOverlayVisible) {
                Qt.callLater(function() {
                    window.focusCanvasTextEditor()
                    canvasTextEditInput.select(rangeStart, rangeEnd)
                })
            }
        }

        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
            radius: Theme.radius
        }

        contentItem: ColumnLayout {
            spacing: 0

            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 56
                color: Theme.bgBar

                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 14
                    spacing: 10

                    Rectangle {
                        Layout.preferredWidth: 28
                        Layout.preferredHeight: 28
                        radius: Theme.radiusSmall
                        color: Theme.accentSoft
                        AppIcon {
                            anchors.centerIn: parent
                            iconName: AppIcons.sliders
                            iconSize: 15
                            iconColor: Theme.accent
                        }
                    }
                    Text {
                        text: effectColorDialog.title
                        color: Theme.textPrimary
                        font.family: Theme.displayFont
                        font.pixelSize: 16
                        font.weight: Font.DemiBold
                        Layout.fillWidth: true
                    }
                    IconButton {
                        iconName: AppIcons.close
                        tooltip: "关闭"
                        buttonSize: 30
                        onClicked: effectColorDialog.close()
                    }
                }

                Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom }
            }

            RowLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                Layout.leftMargin: 18
                Layout.rightMargin: 18
                Layout.topMargin: 16
                Layout.bottomMargin: 16
                spacing: 16

                ColumnLayout {
                    Layout.fillHeight: true
                    Layout.fillWidth: true
                    Layout.minimumWidth: 400
                    spacing: 8

                    TinyLabel {
                        text: "颜色区域"
                        color: Theme.textSecondary
                        font.weight: Font.DemiBold
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        spacing: 10

                        Rectangle {
                            id: saturationValueField
                            Layout.fillWidth: true
                            Layout.fillHeight: true
                            Layout.minimumHeight: 350
                            radius: Theme.radiusSmall
                            color: "white"
                            border.width: 1
                            border.color: Theme.borderStrong
                            clip: true

                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 1
                                gradient: Gradient {
                                    orientation: Gradient.Horizontal
                                    GradientStop { position: 0; color: "white" }
                                    GradientStop { position: 1; color: Qt.hsva(effectColorDialog.hue, 1, 1, 1) }
                                }
                            }
                            Rectangle {
                                anchors.fill: parent
                                anchors.margins: 1
                                gradient: Gradient {
                                    GradientStop { position: 0; color: "transparent" }
                                    GradientStop { position: 1; color: "black" }
                                }
                            }
                            Rectangle {
                                x: 1 + effectColorDialog.saturation * Math.max(0, parent.width - width - 2)
                                y: 1 + (1 - effectColorDialog.brightness) * Math.max(0, parent.height - height - 2)
                                width: 14
                                height: 14
                                radius: 7
                                color: "transparent"
                                border.width: 2
                                border.color: "white"
                                Rectangle {
                                    anchors.fill: parent
                                    anchors.margins: -1
                                    radius: width / 2
                                    color: "transparent"
                                    border.width: 1
                                    border.color: "black"
                                }
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.CrossCursor
                                function pick(mouse) {
                                    effectColorDialog.setHsv(
                                        effectColorDialog.hue,
                                        effectColorDialog.clamp(mouse.x / width, 0, 1),
                                        1 - effectColorDialog.clamp(mouse.y / height, 0, 1)
                                    )
                                }
                                onPressed: mouse => pick(mouse)
                                onPositionChanged: mouse => { if (pressed) pick(mouse) }
                            }
                        }

                        Rectangle {
                            id: hueStrip
                            Layout.preferredWidth: 24
                            Layout.fillHeight: true
                            Layout.minimumHeight: 350
                            radius: Theme.radiusSmall
                            border.width: 1
                            border.color: Theme.borderStrong
                            gradient: Gradient {
                                GradientStop { position: 0.00; color: "#FF0000" }
                                GradientStop { position: 0.17; color: "#FFFF00" }
                                GradientStop { position: 0.33; color: "#00FF00" }
                                GradientStop { position: 0.50; color: "#00FFFF" }
                                GradientStop { position: 0.67; color: "#0000FF" }
                                GradientStop { position: 0.83; color: "#FF00FF" }
                                GradientStop { position: 1.00; color: "#FF0000" }
                            }
                            Rectangle {
                                x: -3
                                y: effectColorDialog.hue * Math.max(0, parent.height - height)
                                width: parent.width + 6
                                height: 4
                                radius: 2
                                color: Theme.bgPanel
                                border.width: 1
                                border.color: "white"
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                function pick(mouse) {
                                    effectColorDialog.setHsv(
                                        effectColorDialog.clamp(mouse.y / height, 0, 1),
                                        effectColorDialog.saturation,
                                        effectColorDialog.brightness
                                    )
                                }
                                onPressed: mouse => pick(mouse)
                                onPositionChanged: mouse => { if (pressed) pick(mouse) }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.preferredWidth: 294
                    Layout.fillHeight: true
                    spacing: 8

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 74
                        radius: Theme.radiusSmall
                        color: Theme.bgControl
                        border.width: 1
                        border.color: Theme.border

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 8
                            spacing: 8

                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: Theme.radiusSmall
                                color: effectColorDialog.selectedColor
                                border.width: 1
                                border.color: Theme.borderStrong
                                TinyLabel {
                                    anchors.left: parent.left
                                    anchors.bottom: parent.bottom
                                    anchors.margins: 6
                                    text: "新颜色"
                                    color: effectColorDialog.brightness > 0.62 && effectColorDialog.saturation < 0.55 ? "#17201d" : "white"
                                    font.weight: Font.DemiBold
                                }
                            }
                            Rectangle {
                                Layout.fillWidth: true
                                Layout.fillHeight: true
                                radius: Theme.radiusSmall
                                color: effectColorDialog.currentColor
                                border.width: 1
                                border.color: Theme.borderStrong
                                TinyLabel {
                                    anchors.left: parent.left
                                    anchors.bottom: parent.bottom
                                    anchors.margins: 6
                                    text: "原颜色"
                                    color: effectColorDialog.currentColor.hsvValue > 0.62 && effectColorDialog.currentColor.hsvSaturation < 0.55 ? "#17201d" : "white"
                                    font.weight: Font.DemiBold
                                }
                            }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8

                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            TinyLabel { text: "HSV"; color: Theme.textSecondary; font.weight: Font.DemiBold }
                            ValueBox { value: Math.round(effectColorDialog.hue * 359).toString(); bindValue: true; suffix: "H°"; Layout.fillWidth: false; onValueCommitted: value => effectColorDialog.setHsv(parseFloat(value) / 359, effectColorDialog.saturation, effectColorDialog.brightness) }
                            ValueBox { value: Math.round(effectColorDialog.saturation * 100).toString(); bindValue: true; suffix: "S%"; Layout.fillWidth: false; onValueCommitted: value => effectColorDialog.setHsv(effectColorDialog.hue, parseFloat(value) / 100, effectColorDialog.brightness) }
                            ValueBox { value: Math.round(effectColorDialog.brightness * 100).toString(); bindValue: true; suffix: "V%"; Layout.fillWidth: false; onValueCommitted: value => effectColorDialog.setHsv(effectColorDialog.hue, effectColorDialog.saturation, parseFloat(value) / 100) }
                        }
                        ColumnLayout {
                            Layout.fillWidth: true
                            spacing: 6
                            TinyLabel { text: "RGB"; color: Theme.textSecondary; font.weight: Font.DemiBold }
                            ValueBox { value: Math.round(effectColorDialog.selectedColor.r * 255).toString(); bindValue: true; suffix: "R"; Layout.fillWidth: false; onValueCommitted: value => effectColorDialog.setRgb(parseFloat(value), effectColorDialog.selectedColor.g * 255, effectColorDialog.selectedColor.b * 255) }
                            ValueBox { value: Math.round(effectColorDialog.selectedColor.g * 255).toString(); bindValue: true; suffix: "G"; Layout.fillWidth: false; onValueCommitted: value => effectColorDialog.setRgb(effectColorDialog.selectedColor.r * 255, parseFloat(value), effectColorDialog.selectedColor.b * 255) }
                            ValueBox { value: Math.round(effectColorDialog.selectedColor.b * 255).toString(); bindValue: true; suffix: "B"; Layout.fillWidth: false; onValueCommitted: value => effectColorDialog.setRgb(effectColorDialog.selectedColor.r * 255, effectColorDialog.selectedColor.g * 255, parseFloat(value)) }
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        ValueBox {
                            Layout.preferredWidth: 92
                            value: Math.round(effectColorDialog.alphaValue * 255).toString()
                            bindValue: true
                            suffix: "A"
                            accessibleName: "透明度"
                            onValueCommitted: value => effectColorDialog.setAlpha(parseFloat(value))
                        }
                        ValueBox {
                            id: effectColorInput
                            Layout.fillWidth: false
                            value: "#000000"
                            bindValue: true
                            invalid: effectColorDialog.errorMessage.length > 0
                            accessibleName: "十六进制颜色"
                            onValueCommitted: value => effectColorDialog.setFromHex(value)
                        }
                    }

                    TinyLabel { text: "常用颜色"; color: Theme.textSecondary; font.weight: Font.DemiBold }
                    GridLayout {
                        Layout.fillWidth: true
                        columns: 8
                        columnSpacing: 6
                        rowSpacing: 6
                        Repeater {
                            model: [
                                "#000000", "#404040", "#808080", "#BFBFBF", "#FFFFFF", "#7F0000", "#FF0000", "#FF7F7F",
                                "#7F3F00", "#FF7F00", "#FFFF00", "#007F00", "#00FF00", "#007F7F", "#00FFFF", "#0000FF",
                                "#7F00FF", "#FF00FF", "#46D7AD", "#4FA3FF", "#F7BD63", "#F1786D", "#65D88D", "#747D7A"
                            ]
                            delegate: Rectangle {
                                required property string modelData
                                Layout.preferredWidth: 27
                                Layout.preferredHeight: 27
                                radius: Theme.radiusSmall
                                color: modelData
                                border.width: effectColorDialog.colorToHex(effectColorDialog.selectedColor).slice(0, 7) === modelData ? 2 : 1
                                border.color: paletteMouse.containsMouse || border.width === 2 ? Theme.accent : Theme.borderStrong
                                activeFocusOnTab: true
                                MouseArea {
                                    id: paletteMouse
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onPressed: parent.forceActiveFocus(Qt.MouseFocusReason)
                                    onClicked: effectColorDialog.selectPaletteColor(parent.modelData)
                                }
                                Keys.onSpacePressed: effectColorDialog.selectPaletteColor(modelData)
                                Keys.onReturnPressed: effectColorDialog.selectPaletteColor(modelData)
                                Accessible.name: "颜色 " + modelData
                                Accessible.role: Accessible.Button
                            }
                        }
                    }
                    Item { Layout.fillHeight: true }
                }
            }
            Rectangle {
                Layout.fillWidth: true
                Layout.preferredHeight: 64
                color: Theme.bgBar

                Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top }
                RowLayout {
                    anchors.fill: parent
                    anchors.leftMargin: 18
                    anchors.rightMargin: 18
                    spacing: 8
                    TinyLabel {
                        text: effectColorDialog.errorMessage
                        color: Theme.coral
                        visible: text.length > 0
                        Layout.fillWidth: true
                        elide: Text.ElideRight
                    }
                    Item { Layout.fillWidth: effectColorDialog.errorMessage.length === 0 }
                    ExportButton { Layout.preferredWidth: 88; label: "取消"; onClicked: effectColorDialog.close() }
                    ExportButton { Layout.preferredWidth: 100; label: "应用"; primary: true; onClicked: effectColorDialog.applyColor() }
                }
            }
        }
    }

    AppDialog {
        id: quickCanvasPresetDialog
        objectName: "quickCanvasPresetDialog"
        anchors.centerIn: parent
        width: 380
        height: 330
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape
        property int presetIndex: -1
        property string errorMessage: ""

        function openForPreset(index) {
            var preset = window.quickCanvasPresets[index]
            if (!preset)
                return
            presetIndex = index
            quickPresetNameInput.text = preset.name
            quickPresetWidthInput.text = String(preset.width)
            quickPresetHeightInput.text = String(preset.height)
            errorMessage = ""
            open()
            Qt.callLater(function() { quickPresetNameInput.forceActiveFocus() })
        }

        function savePreset() {
            var name = quickPresetNameInput.text.trim()
            var widthValue = parseInt(quickPresetWidthInput.text)
            var heightValue = parseInt(quickPresetHeightInput.text)
            if (name.length === 0) {
                errorMessage = "请输入尺寸名称"
                return
            }
            if (!window.replaceQuickCanvasPreset(presetIndex, name, widthValue, heightValue)) {
                errorMessage = "宽度和高度必须在 16 到 32768 像素之间"
                return
            }
            newCanvasDialog.chooseSize(widthValue, heightValue)
            close()
        }

        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
            radius: Theme.radius
        }

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Text {
                    text: "编辑常用尺寸"
                    color: Theme.textPrimary
                    font.family: Theme.displayFont
                    font.pixelSize: 16
                    font.weight: Font.DemiBold
                    Layout.fillWidth: true
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 28; onClicked: quickCanvasPresetDialog.close() }
            }

            Divider { Layout.fillWidth: true }

            BodyLabel { text: "名称"; color: Theme.textPrimary }
            AppTextField {
                id: quickPresetNameInput
                Layout.fillWidth: true
                accessibleName: "常用尺寸名称"
                placeholderText: "例如：横版封面"
                maximumLength: 32
            }

            BodyLabel { text: "画布尺寸"; color: Theme.textPrimary }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                AppTextField {
                    id: quickPresetWidthInput
                    Layout.fillWidth: true
                    accessibleName: "常用尺寸宽度"
                    placeholderText: "宽度"
                    validator: IntValidator { bottom: 16; top: 32768 }
                }
                TinyLabel { text: "x"; Layout.preferredWidth: 10; horizontalAlignment: Text.AlignHCenter }
                AppTextField {
                    id: quickPresetHeightInput
                    Layout.fillWidth: true
                    accessibleName: "常用尺寸高度"
                    placeholderText: "高度"
                    validator: IntValidator { bottom: 16; top: 32768 }
                    Keys.onReturnPressed: quickCanvasPresetDialog.savePreset()
                }
                TinyLabel { text: "px"; Layout.preferredWidth: 18; horizontalAlignment: Text.AlignRight }
            }

            Text {
                Layout.fillWidth: true
                Layout.preferredHeight: 18
                text: quickCanvasPresetDialog.errorMessage
                color: Theme.danger
                font.family: Theme.bodyFont
                font.pixelSize: 11
                elide: Text.ElideRight
            }

            Item { Layout.fillHeight: true }
            RowLayout {
                Layout.fillWidth: true
                spacing: 8
                Item { Layout.fillWidth: true }
                ExportButton { Layout.preferredWidth: 86; label: "取消"; onClicked: quickCanvasPresetDialog.close() }
                ExportButton { Layout.preferredWidth: 96; label: "保存"; iconName: AppIcons.save; primary: true; onClicked: quickCanvasPresetDialog.savePreset() }
            }
        }
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

    component ExportSettingsSection: Item {
        id: section

        property string title: ""
        property string detail: ""
        property string summary: ""
        property string iconName: AppIcons.settings
        property bool expanded: true
        default property alias sectionData: sectionContent.data
        signal toggled(bool expanded)

        width: parent ? parent.width : implicitWidth
        implicitHeight: sectionHeader.height + (expanded ? sectionContent.implicitHeight + 18 : 0) + 1
        height: implicitHeight

        Rectangle {
            id: sectionHeader
            anchors.left: parent.left
            anchors.right: parent.right
            height: 54
            color: sectionMouse.containsMouse || activeFocus ? Theme.bgRaised : "transparent"
            radius: Theme.radiusSmall
            activeFocusOnTab: true

            RowLayout {
                anchors.fill: parent
                anchors.leftMargin: 8
                anchors.rightMargin: 8
                spacing: 10

                Rectangle {
                    Layout.preferredWidth: 28
                    Layout.preferredHeight: 28
                    radius: Theme.radiusSmall
                    color: Theme.accentSoft
                    AppIcon {
                        anchors.centerIn: parent
                        iconName: section.iconName
                        iconSize: 14
                        iconColor: Theme.accent
                    }
                }
                Column {
                    Layout.fillWidth: true
                    spacing: 2
                    BodyLabel {
                        text: section.title
                        color: Theme.textPrimary
                        font.weight: Font.DemiBold
                    }
                    TinyLabel {
                        width: parent.width
                        text: section.detail
                        color: Theme.textMuted
                        elide: Text.ElideRight
                    }
                }
                TinyLabel {
                    visible: section.summary.length > 0
                    text: section.summary
                    color: Theme.textSecondary
                }
                AppIcon {
                    iconName: AppIcons.chevronDown
                    iconSize: 12
                    iconColor: Theme.textMuted
                    rotation: section.expanded ? 0 : -90
                    Behavior on rotation {
                        NumberAnimation { duration: Theme.motionNormal; easing.type: Easing.OutCubic }
                    }
                }
            }

            function toggleSection() {
                section.expanded = !section.expanded
                section.toggled(section.expanded)
            }

            MouseArea {
                id: sectionMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onPressed: sectionHeader.forceActiveFocus(Qt.MouseFocusReason)
                onClicked: sectionHeader.toggleSection()
            }
            Keys.onSpacePressed: toggleSection()
            Keys.onReturnPressed: toggleSection()
            Accessible.name: section.title
            Accessible.description: section.detail
            Accessible.role: Accessible.Button
        }

        Column {
            id: sectionContent
            anchors.top: sectionHeader.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.leftMargin: 8
            anchors.rightMargin: 8
            anchors.topMargin: 8
            spacing: 10
            visible: section.expanded
        }

        Divider {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
        }

        Accessible.name: title
        Accessible.role: Accessible.Grouping
    }

    component CompactExportSection: Item {
        id: compactSection

        property string title: ""
        property string detail: ""
        property string iconName: AppIcons.settings
        property bool expanded: true
        default property alias sectionData: compactSectionContent.data

        Layout.fillWidth: true
        implicitHeight: compactSectionHeader.height
                        + (expanded ? compactSectionContent.implicitHeight + 7 : 0) + 1

        Rectangle {
            id: compactSectionHeader
            anchors.left: parent.left
            anchors.right: parent.right
            height: 38
            radius: Theme.radiusSmall
            color: compactSectionMouse.containsMouse || activeFocus ? Theme.bgRaised : "transparent"
            activeFocusOnTab: true

            RowLayout {
                anchors.fill: parent
                spacing: 8

                Rectangle {
                    Layout.preferredWidth: 24
                    Layout.preferredHeight: 24
                    radius: Theme.radiusSmall
                    color: Theme.accentSoft
                    AppIcon {
                        anchors.centerIn: parent
                        iconName: compactSection.iconName
                        iconSize: 13
                        iconColor: Theme.accent
                    }
                }
                Column {
                    Layout.fillWidth: true
                    spacing: 0
                    BodyLabel {
                        text: compactSection.title
                        color: Theme.textPrimary
                        font.pixelSize: 11
                        font.weight: Font.DemiBold
                    }
                    TinyLabel {
                        width: parent.width
                        text: compactSection.detail
                        font.pixelSize: 9
                        elide: Text.ElideRight
                    }
                }
                AppIcon {
                    iconName: AppIcons.chevronDown
                    iconSize: 11
                    iconColor: Theme.textMuted
                    rotation: compactSection.expanded ? 0 : -90
                }
            }

            function toggleSection() {
                compactSection.expanded = !compactSection.expanded
            }

            MouseArea {
                id: compactSectionMouse
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onPressed: compactSectionHeader.forceActiveFocus(Qt.MouseFocusReason)
                onClicked: compactSectionHeader.toggleSection()
            }
            Keys.onSpacePressed: toggleSection()
            Keys.onReturnPressed: toggleSection()
            Accessible.name: compactSection.title
            Accessible.description: compactSection.detail
            Accessible.role: Accessible.Button
        }

        Column {
            id: compactSectionContent
            anchors.top: compactSectionHeader.bottom
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.topMargin: 6
            spacing: 6
            visible: compactSection.expanded
        }

        Divider {
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
        }
    }

    component MenuLabel: Text {
        property bool hovered: false
        color: hovered ? Theme.textPrimary : Theme.textSecondary
        font.family: Theme.bodyFont
        font.pixelSize: 12
        verticalAlignment: Text.AlignVCenter
    }

    component AlignmentToolButton: Rectangle {
        id: alignmentButton

        property string alignmentMode: ""
        property string distributionMode: ""
        property string tooltip: ""
        readonly property string iconMode: alignmentMode.length > 0 ? alignmentMode : distributionMode
        readonly property string iconName: {
            if (iconMode === "left") return AppIcons.alignLeft
            if (iconMode === "hcenter") return AppIcons.alignCenterHorizontal
            if (iconMode === "right") return AppIcons.alignRight
            if (iconMode === "top") return AppIcons.alignTop
            if (iconMode === "vcenter") return AppIcons.alignCenterVertical
            if (iconMode === "bottom") return AppIcons.alignBottom
            if (iconMode === "horizontal") return AppIcons.distributeHorizontal
            if (iconMode === "vertical") return AppIcons.distributeVertical
            if (iconMode === "same_size") return AppIcons.fitView
            return AppIcons.circleDot
        }
        signal clicked()

        implicitWidth: 28
        implicitHeight: 30
        radius: Theme.radiusSmall
        color: {
            if (!enabled) return "transparent"
            if (alignmentMouse.pressed) return Theme.bgControl
            return alignmentMouse.containsMouse ? Theme.bgHover : "transparent"
        }
        opacity: enabled ? 1 : 0.32
        border.width: activeFocus ? 1 : 0
        border.color: Theme.focusRing
        activeFocusOnTab: enabled

        AppIcon {
            anchors.centerIn: parent
            iconName: alignmentButton.iconName
            iconSize: 16
            iconColor: alignmentMouse.containsMouse && alignmentButton.enabled
                       ? Theme.textPrimary : Theme.textSecondary
        }

        MouseArea {
            id: alignmentMouse
            anchors.fill: parent
            enabled: alignmentButton.enabled
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onPressed: alignmentButton.forceActiveFocus(Qt.MouseFocusReason)
            onClicked: alignmentButton.clicked()
        }

        Keys.onSpacePressed: clicked()

        ToolTip.visible: alignmentMouse.containsMouse && tooltip.length > 0
        ToolTip.text: tooltip
        ToolTip.delay: 420
        Accessible.name: tooltip
        Accessible.role: Accessible.Button
    }

    component ToolRailButton: Rectangle {
        id: toolButton
        property int toolIndex: 0
        property string iconName: ""
        property string label: ""
        signal triggered()

        width: Theme.railButtonSize
        height: Theme.railButtonSize
        radius: Theme.radiusSmall
        color: activeTool === toolIndex ? Theme.accentSoft : (toolMouse.containsMouse ? Theme.bgHover : "transparent")
        border.width: activeTool === toolIndex ? 1 : 0
        border.color: activeFocus ? Theme.focusRing : Theme.accentPressed
        opacity: enabled ? 1 : 0.34
        activeFocusOnTab: enabled

        AppIcon {
            anchors.centerIn: parent
            iconName: toolButton.iconName
            iconSize: 18
            iconColor: activeTool === toolButton.toolIndex ? Theme.accent : Theme.textSecondary
        }

        MouseArea {
            id: toolMouse
            anchors.fill: parent
            enabled: toolButton.enabled
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onPressed: toolButton.forceActiveFocus(Qt.MouseFocusReason)
            onClicked: {
                activeTool = toolButton.toolIndex
                toolButton.triggered()
            }
        }

        Keys.onSpacePressed: triggered()

        ToolTip.visible: toolMouse.containsMouse
        ToolTip.text: toolButton.label
        ToolTip.delay: 420
    }

    component InspectorRow: Item {
        id: rowRoot
        property string label: ""
        // 把外部子控件定向导入到内部 controlArea RowLayout
        default property alias controls: controlArea.data
        width: parent ? parent.width : 300
        height: Theme.inspectorRowHeight
        readonly property int controlAreaWidth: Math.max(80, width - Theme.inspectorLabelColWidth - Theme.inspectorColSpacing)

        // 静态规范全部走 Theme.inspectorXxx；wSliderFill 仅用于 Slider（需要操作长度）
        readonly property int wSliderFill: Math.max(60, controlAreaWidth - Theme.inspectorColSpacing - Theme.inspectorWSliderVB)

        BodyLabel {
            id: rowLabel
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            width: Theme.inspectorLabelColWidth
            text: rowRoot.label
            color: Theme.textMuted
            elide: Text.ElideRight
            font.pixelSize: 10
            // ★ Figma/Photoshop 专业 Inspector 风格：Label 右对齐（贴 Label 列的右边界）
            horizontalAlignment: Text.AlignRight
        }

        // ★ 控件区：从 Label 右边紧挨着开始，左对齐紧凑排列，不再 fill 中间空白 → 视觉上完全贴合，无大片空洞
        // 这是 Figma / Sketch / Photoshop 属性面板的经典二列布局：Label 的右边界一条线，控件的左边界一条线
        RowLayout {
            id: controlArea
            // wSliderFill 仍透传（Slider 行需要动态长度）
            property alias wSliderFill: rowRoot.wSliderFill
            anchors.left: rowLabel.right
            anchors.leftMargin: Theme.inspectorColSpacing
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            spacing: Theme.inspectorColSpacing
            // 不再有 fill 占位 Item → RowLayout 天然左对齐紧排所有子控件
        }
    }

    component TrailingToggle: Item {
        id: trailingToggle
        property bool checked: false
        property string accessibleName: "开关"
        signal toggled(bool checked)

        Layout.fillWidth: true
        implicitHeight: Theme.controlHeight

        ToggleSwitch {
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            accessibleName: trailingToggle.accessibleName
            checked: trailingToggle.checked
            enabled: trailingToggle.enabled
            onToggled: checkedValue => trailingToggle.toggled(checkedValue)
        }
    }

    component FormatToggleButton: Rectangle {
        id: formatButton
        property string symbol: ""
        property string tooltip: ""
        property bool active: false
        property bool italicSymbol: false
        signal clicked()

        implicitWidth: Theme.controlHeight
        implicitHeight: Theme.controlHeight
        radius: Theme.radiusSmall
        color: {
            if (!enabled) return "transparent"
            if (formatMouse.pressed || formatMouse.containsMouse) return Theme.bgHover
            return active ? Theme.accentSoft : "transparent"
        }
        border.width: active ? 1 : 0
        border.color: Theme.accentPressed
        opacity: enabled ? 1 : 0.38

        Text {
            anchors.centerIn: parent
            text: formatButton.symbol
            color: formatButton.active ? Theme.accent : Theme.textSecondary
            font.family: Theme.bodyFont
            font.pixelSize: 14
            font.weight: formatButton.symbol === "B" ? Font.Bold : Font.Normal
            font.italic: formatButton.italicSymbol
        }
        MouseArea {
            id: formatMouse
            anchors.fill: parent
            enabled: formatButton.enabled
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: formatButton.clicked()
        }
        ToolTip.visible: formatMouse.containsMouse && formatButton.tooltip.length > 0
        ToolTip.text: formatButton.tooltip
        ToolTip.delay: 420
        Accessible.name: tooltip
        Accessible.role: Accessible.Button
    }

    component CompactActionButton: Rectangle {
        id: compactButton
        property string label: ""
        property bool active: false
        signal clicked()

        implicitWidth: 94
        implicitHeight: Theme.controlHeight
        radius: Theme.radiusSmall
        color: {
            if (!enabled) return Theme.bgControl
            if (compactMouse.pressed || compactMouse.containsMouse) return Theme.bgHover
            return active ? Theme.accentSoft : Theme.bgControl
        }
        border.width: 1
        border.color: active ? Theme.accentPressed : Theme.borderStrong
        opacity: enabled ? 1 : 0.38

        Text {
            anchors.centerIn: parent
            text: compactButton.label
            color: compactButton.active ? Theme.accent : Theme.textSecondary
            font.family: Theme.bodyFont
            font.pixelSize: 11
            font.weight: Font.DemiBold
        }
        MouseArea {
            id: compactMouse
            anchors.fill: parent
            enabled: compactButton.enabled
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: compactButton.clicked()
        }
        Accessible.name: label
        Accessible.role: Accessible.Button
    }

    component ColorValueField: RowLayout {
        id: colorField
        property string value: "#000000"
        signal pickRequested()
        signal valueCommitted(string value)

        spacing: 6
        Rectangle {
            Layout.preferredWidth: Theme.controlHeight
            Layout.preferredHeight: Theme.controlHeight
            radius: Theme.radiusSmall
            color: window.hexToColor(colorField.value)
            border.width: 1
            border.color: colorMouse.containsMouse ? Theme.accent : Theme.borderStrong
            opacity: colorField.enabled ? 1 : 0.38
            MouseArea {
                id: colorMouse
                anchors.fill: parent
                enabled: colorField.enabled
                hoverEnabled: true
                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                onClicked: colorField.pickRequested()
            }
        }
        ValueBox {
            value: colorField.value
            bindValue: true
            Layout.fillWidth: false
            editable: colorField.enabled
            onValueCommitted: value => colorField.valueCommitted(value)
        }
    }

    component ShapeMenuItem: MenuItem {
        id: shapeMenuItem
        implicitWidth: 158
        implicitHeight: 34
        leftPadding: 10
        rightPadding: 10
        contentItem: Text {
            text: shapeMenuItem.text
            color: !shapeMenuItem.enabled
                   ? Theme.textDisabled
                   : (shapeMenuItem.highlighted ? Theme.textPrimary : Theme.textSecondary)
            font.family: Theme.bodyFont
            font.pixelSize: 11
            verticalAlignment: Text.AlignVCenter
        }
        background: Rectangle {
            color: shapeMenuItem.highlighted ? Theme.bgHover : "transparent"
            radius: Theme.radiusSmall
        }
    }

    component ExportField: AppTextField {
        id: exportField
        property string placeholder: ""
        signal committed(string value)

        implicitHeight: 36
        placeholderText: placeholder
        font.pixelSize: 12
        onEditingFinished: exportField.committed(text)
    }

    component ExportButton: AppButton {
        id: exportButton
        property string label: ""
        text: label
    }

    component ContentTextEditor: Rectangle {
        id: textEditorRoot
        property string value: ""
        property string placeholder: ""
        property int contextIndex: -1
        property int editingIndex: -1
        readonly property bool editing: contentEditor.activeFocus
        readonly property int selectionStart: contentEditor.selectionStart
        readonly property int selectionEnd: contentEditor.selectionEnd
        readonly property int selectionLength: Math.abs(selectionEnd - selectionStart)
        signal committed(string value, int contextIndex)

        function releaseFocus() {
            if (contentEditor.activeFocus)
                contentEditor.focus = false
        }

        function beginEdit() {
            if (!textEditorRoot.enabled)
                return
            contentEditor.forceActiveFocus()
        }

        function selectRange(start, end) {
            contentEditor.select(start, end)
            contentEditor.forceActiveFocus()
        }

        implicitHeight: 104
        radius: Theme.radiusSmall
        color: Theme.bgControl
        border.width: 1
        border.color: contentEditor.activeFocus ? Theme.accent : Theme.borderStrong
        opacity: enabled ? 1 : 0.45

        Flickable {
            id: editorFlick
            anchors.fill: parent
            anchors.margins: 10
            contentWidth: width
            contentHeight: contentEditor.paintedHeight
            clip: true
            boundsBehavior: Flickable.StopAtBounds

            TextEdit {
                id: contentEditor
                width: editorFlick.width
                height: Math.max(editorFlick.height, paintedHeight)
                color: Theme.textPrimary
                selectionColor: Theme.accentPressed
                selectedTextColor: Theme.textPrimary
                font.family: Theme.bodyFont
                font.pixelSize: 12
                wrapMode: TextEdit.Wrap
                selectByMouse: true
                readOnly: !textEditorRoot.enabled
                onActiveFocusChanged: {
                    if (activeFocus) {
                        contentEditor.text = textEditorRoot.value
                        textEditorRoot.editingIndex = textEditorRoot.contextIndex
                    } else if (textEditorRoot.editingIndex >= 0) {
                        textEditorRoot.committed(text, textEditorRoot.editingIndex)
                        textEditorRoot.editingIndex = -1
                    }
                }
                Keys.onPressed: event => {
                    if ((event.modifiers & Qt.ControlModifier) && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
                        focus = false
                        event.accepted = true
                    }
                }

                Text {
                    anchors.left: parent.left
                    anchors.top: parent.top
                    text: textEditorRoot.placeholder
                    visible: contentEditor.text.length === 0 && !contentEditor.activeFocus
                    color: Theme.textMuted
                    font: contentEditor.font
                }
            }

            Binding {
                target: contentEditor
                property: "text"
                value: textEditorRoot.value
                when: !contentEditor.activeFocus
                restoreMode: Binding.RestoreNone
            }
        }
    }

    AppDialog {
        id: batchExportAdvancedDialog
        objectName: "batchExportAdvancedDialog"
        anchors.centerIn: parent
        width: Math.min(620, window.width - 32)
        height: Math.min(590, window.height - 40)
        modal: true
        focus: true
        padding: 0
        closePolicy: Popup.CloseOnEscape
        header: null
        footer: null

        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 20
            spacing: 12

            RowLayout {
                Layout.fillWidth: true
                Layout.preferredHeight: 34
                spacing: 10
                Rectangle {
                    Layout.preferredWidth: 30
                    Layout.preferredHeight: 30
                    radius: Theme.radiusSmall
                    color: Theme.accentSoft
                    AppIcon { anchors.centerIn: parent; iconName: AppIcons.sliders; iconSize: 15; iconColor: Theme.accent }
                }
                Column {
                    Layout.fillWidth: true
                    spacing: 1
                    Text { text: "高级策略"; color: Theme.textPrimary; font.family: Theme.displayFont; font.pixelSize: 16; font.weight: Font.DemiBold }
                    TinyLabel { text: "质量、性能、内存保护和异常终止条件" }
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 30; onClicked: batchExportAdvancedDialog.close() }
            }

            Divider { Layout.fillWidth: true }

            ColumnLayout {
                Layout.fillWidth: true
                Layout.fillHeight: true
                spacing: 10
                enabled: !batchExport.running

                BodyLabel { text: "质量策略"; color: Theme.textSecondary }
                GridLayout {
                    id: qualityStrategyGrid
                    Layout.fillWidth: true
                    columns: 2
                    rowSpacing: 8
                    columnSpacing: 8

                    OptionTile {
                        compact: true
                        exclusive: true
                        title: "高质量"
                        detail: "优先保留图像细节"
                        selected: batchExport.qualityProfile === "quality"
                        onActivated: batchExport.qualityProfile = "quality"
                    }
                    OptionTile {
                        compact: true
                        exclusive: true
                        title: "均衡"
                        detail: "兼顾质量与处理速度"
                        selected: batchExport.qualityProfile === "balanced"
                        onActivated: batchExport.qualityProfile = "balanced"
                    }
                    OptionTile {
                        compact: true
                        exclusive: true
                        title: "速度优先"
                        detail: "缩短批量处理时间"
                        selected: batchExport.qualityProfile === "speed"
                        onActivated: batchExport.qualityProfile = "speed"
                    }
                    OptionTile {
                        compact: true
                        exclusive: true
                        title: "体积优先"
                        detail: "控制输出文件大小"
                        selected: batchExport.qualityProfile === "size"
                        onActivated: batchExport.qualityProfile = "size"
                    }
                }

                BodyLabel { text: "性能策略"; color: Theme.textSecondary }
                RowLayout {
                    id: performanceStrategyOptions
                    Layout.fillWidth: true
                    spacing: 8
                    OptionTile {
                        compact: true
                        title: "高性能管线"
                        detail: "加速批量渲染与写出"
                        selected: batchExport.useHighPerformance
                        onActivated: batchExport.useHighPerformance = !batchExport.useHighPerformance
                    }
                    OptionTile {
                        compact: true
                        title: "预读素材"
                        detail: "提前读取，减少等待"
                        selected: batchExport.preloadEnabled
                        onActivated: batchExport.preloadEnabled = !batchExport.preloadEnabled
                    }
                    OptionTile {
                        compact: true
                        title: "独立 Worker"
                        detail: "大批量任务隔离运行"
                        selected: batchExport.externalWorkerEnabled
                        onActivated: batchExport.externalWorkerEnabled = !batchExport.externalWorkerEnabled
                    }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    BodyLabel { text: "内存保护"; Layout.preferredWidth: 70 }
                    SelectBox {
                        Layout.fillWidth: false
                        model: [
                            { label: "自动", value: "auto" },
                            { label: "低内存", value: "low" },
                            { label: "自定义", value: "custom" },
                            { label: "关闭", value: "off" }
                        ]
                        currentIndex: window.optionIndex(model, batchExport.memoryGuardMode)
                        onActivated: batchExport.memoryGuardMode = currentValue
                    }
                }
                RowLayout {
                    Layout.fillWidth: true
                    visible: batchExport.memoryGuardMode === "custom"
                    spacing: 8
                    BodyLabel { text: "上限 MB"; Layout.preferredWidth: 70 }
                    ExportField { Layout.fillWidth: true; text: String(batchExport.memoryLimitMB); onCommitted: value => batchExport.memoryLimitMB = Math.max(0, parseInt(value) || 0) }
                    BodyLabel { text: "预留 MB"; Layout.preferredWidth: 58 }
                    ExportField { Layout.fillWidth: true; text: String(batchExport.memoryReserveMB); onCommitted: value => batchExport.memoryReserveMB = Math.max(256, parseInt(value) || 256) }
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Column {
                        Layout.fillWidth: true
                        spacing: 4
                        TinyLabel { text: "连续失败上限" }
                        ExportField { width: parent.width; text: String(batchExport.maxConsecutiveFailures); onCommitted: value => batchExport.maxConsecutiveFailures = Math.max(1, parseInt(value) || 1) }
                    }
                    Column {
                        Layout.fillWidth: true
                        spacing: 4
                        TinyLabel { text: "失败率上限 %" }
                        ExportField { width: parent.width; text: String(batchExport.failureRateLimit); onCommitted: value => batchExport.failureRateLimit = Math.max(1, Math.min(100, parseInt(value) || 1)) }
                    }
                    Column {
                        Layout.fillWidth: true
                        spacing: 4
                        TinyLabel { text: "停滞超时 秒" }
                        ExportField { width: parent.width; text: String(batchExport.stallTimeoutSeconds); onCommitted: value => batchExport.stallTimeoutSeconds = Math.max(30, parseInt(value) || 30) }
                    }
                }

                Item { Layout.fillHeight: true }
                RowLayout {
                    Layout.fillWidth: true
                    spacing: 8
                    Item { Layout.fillWidth: true }
                    ExportButton { Layout.preferredWidth: 92; label: "完成"; iconName: AppIcons.check; primary: true; onClicked: batchExportAdvancedDialog.close() }
                }
            }
        }
    }

    AppDrawer {
        id: batchExportDrawer
        objectName: "batchExportDrawer"
        edge: Qt.RightEdge
        width: Math.min(480, Math.max(450, window.width * 0.39))
        height: window.height
        modal: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0

        function showUniqueLayerSelector() {
            batchExport.uniqueUseEnabled = true
            uniqueLayerPicker.selectorOpen = true
        }

        Overlay.modal: Rectangle { color: Theme.overlayModal }
        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
        }

        contentItem: Item {
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 12
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 44
                    spacing: 12

                    Rectangle {
                        Layout.preferredWidth: 32
                        Layout.preferredHeight: 32
                        radius: Theme.radiusSmall
                        color: Theme.accentSoft
                        AppIcon { anchors.centerIn: parent; iconName: AppIcons.exportAction; iconSize: 16; iconColor: Theme.accent }
                    }
                    Column {
                        Layout.fillWidth: true
                        spacing: 2
                        Text { text: "批量导出"; color: Theme.textPrimary; font.family: Theme.displayFont; font.pixelSize: 17; font.weight: Font.DemiBold }
                        TinyLabel { text: workspace.documentTitle; color: Theme.textMuted }
                    }
                    Rectangle {
                        Layout.preferredWidth: 92
                        Layout.preferredHeight: 28
                        radius: Theme.radiusSmall
                        color: Theme.bgRaised
                        TinyLabel {
                            anchors.centerIn: parent
                            text: batchExport.effectiveCount + " 张 · " + batchExport.fileFormat.toUpperCase()
                            color: Theme.textSecondary
                        }
                    }
                    IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 30; onClicked: batchExportDrawer.close() }
                }

                Divider { Layout.fillWidth: true; Layout.topMargin: 6; Layout.bottomMargin: 5 }

                ColumnLayout {
                    id: exportForm
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    spacing: window.height < 800 ? 6 : 16
                    enabled: !batchExport.running

                        CompactExportSection {
                            title: "导出任务"
                            detail: "目录、数量和起始序号"
                            iconName: AppIcons.folderOutput

                            Column {
                                width: parent.width
                                spacing: 5
                                BodyLabel { text: "输出目录"; color: Theme.textSecondary; font.pixelSize: 11 }
                                RowLayout {
                                    width: parent.width
                                    spacing: 6
                                    ExportField {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 32
                                        text: batchExport.outputDirectory
                                        placeholder: "选择文件夹"
                                        onCommitted: value => batchExport.outputDirectory = value
                                    }
                                    IconButton {
                                        iconName: AppIcons.folderOpen
                                        tooltip: "选择输出目录"
                                        buttonSize: 32
                                        active: true
                                        onClicked: outputFolderDialog.open()
                                    }
                                }
                            }

                            RowLayout {
                                width: parent.width
                                spacing: 8
                                Column {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 1
                                    Layout.minimumWidth: 0
                                    Layout.alignment: Qt.AlignTop
                                    spacing: 4
                                    BodyLabel { text: "生成数量"; color: Theme.textSecondary; font.pixelSize: 11 }
                                    ExportField {
                                        width: parent.width
                                        height: 32
                                        text: String(batchExport.count)
                                        placeholder: "10"
                                        enabled: !batchExport.traverseMode
                                        onCommitted: value => batchExport.count = Math.max(0, parseInt(value) || 0)
                                    }
                                }
                                Column {
                                    Layout.fillWidth: true
                                    Layout.preferredWidth: 1
                                    Layout.minimumWidth: 0
                                    Layout.alignment: Qt.AlignTop
                                    spacing: 4
                                    BodyLabel { text: "起始序号"; color: Theme.textSecondary; font.pixelSize: 11 }
                                    ExportField {
                                        width: parent.width
                                        height: 32
                                        text: String(batchExport.startIndex)
                                        placeholder: "1"
                                        onCommitted: value => batchExport.startIndex = Math.max(0, parseInt(value) || 0)
                                    }
                                }
                            }
                        }

                        CompactExportSection {
                            title: "文件命名"
                            detail: "日期、前缀与序号规则"
                            iconName: AppIcons.tag

                            Column {
                                width: parent.width
                                spacing: 5
                                RowLayout {
                                    width: parent.width
                                    spacing: 6
                                    BodyLabel { text: "添加日期"; Layout.preferredWidth: 58; font.pixelSize: 11 }
                                    ToggleSwitch {
                                        accessibleName: "文件名添加当前日期"
                                        checked: batchExport.useDate
                                        onToggled: checkedValue => batchExport.useDate = checkedValue
                                    }
                                    SelectBox {
                                        Layout.fillWidth: false
                                        Layout.preferredHeight: 32
                                        enabled: batchExport.useDate
                                        model: [
                                            { label: "YYYYMMDD", value: 0 },
                                            { label: "YYYY-MM-DD", value: 1 },
                                            { label: "YYMMDD", value: 2 }
                                        ]
                                        currentIndex: batchExport.dateFormatIndex
                                        onActivated: batchExport.dateFormatIndex = currentValue
                                    }
                                }
                                RowLayout {
                                    width: parent.width
                                    spacing: 6
                                    BodyLabel { text: "文件前缀"; Layout.preferredWidth: 58; font.pixelSize: 11 }
                                    ExportField {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 32
                                        text: batchExport.customText
                                        placeholder: "例如 export"
                                        onCommitted: value => batchExport.customText = value
                                    }
                                }
                                RowLayout {
                                    width: parent.width
                                    spacing: 6
                                    BodyLabel { text: "序号格式"; Layout.preferredWidth: 58; font.pixelSize: 11 }
                                    SelectBox {
                                        Layout.fillWidth: false
                                        Layout.preferredHeight: 32
                                        model: [
                                            { label: "0001, 0002, ...", value: 0 },
                                            { label: "001, 002, ...", value: 1 },
                                            { label: "01, 02, ...", value: 2 },
                                            { label: "1, 2, ...", value: 3 }
                                        ]
                                        currentIndex: batchExport.numberFormatIndex
                                        onActivated: batchExport.numberFormatIndex = currentValue
                                    }
                                }
                            }
                        }

                        CompactExportSection {
                            title: "输出格式"
                            detail: "格式与单文件体积"
                            iconName: AppIcons.fileImage

                            RowLayout {
                                width: parent.width
                                spacing: 8
                                SegmentedControl {
                                    id: batchFormatControl
                                    Layout.preferredWidth: 158
                                    Layout.preferredHeight: 32
                                    options: [
                                        { label: "PNG", value: "png" },
                                        { label: "JPG", value: "jpg" }
                                    ]
                                    value: batchExport.fileFormat
                                    accessibleName: "输出格式"
                                    onActivated: value => batchExport.fileFormat = value
                                }
                                BodyLabel { text: "大小 KB"; Layout.preferredWidth: 48; font.pixelSize: 11 }
                                ExportField {
                                    Layout.fillWidth: false
                                    Layout.preferredHeight: 32
                                    text: String(batchExport.maxFileSizeKB)
                                    placeholder: "0（不限制）"
                                    onCommitted: value => batchExport.maxFileSizeKB = Math.max(0, parseInt(value) || 0)
                                }
                            }
                        }

                        CompactExportSection {
                            id: strategySection
                            title: "组合策略"
                            detail: "随机、去重与遍历"
                            iconName: AppIcons.shuffle
                            z: uniqueLayerPicker.selectorOpen ? 10 : 0

                            Rectangle {
                                id: compactStrategyBar
                                width: parent.width
                                height: 30
                                radius: Theme.radiusSmall
                                color: Theme.bgControl
                                border.width: 1
                                border.color: Theme.border
                                Row {
                                    id: strategyOptionsRow
                                    objectName: "batchStrategyOptions"
                                    anchors.fill: parent
                                    anchors.margins: 2
                                    spacing: 2
                                    property var strategyOptions: [
                                        { label: "智能采样", value: "sample" },
                                        { label: "单次用图", value: "unique" },
                                        { label: "遍历组合", value: "traverse" }
                                    ]
                                    function optionSelected(value) {
                                        if (value === "sample") return batchExport.avoidDuplicates
                                        if (value === "unique") return batchExport.uniqueUseEnabled
                                        return batchExport.traverseMode
                                    }
                                    function toggleOption(value) {
                                        if (value === "sample") batchExport.avoidDuplicates = !batchExport.avoidDuplicates
                                        else if (value === "unique") batchExport.uniqueUseEnabled = !batchExport.uniqueUseEnabled
                                        else batchExport.traverseMode = !batchExport.traverseMode
                                    }
                                    Repeater {
                                        model: parent.strategyOptions
                                        delegate: Rectangle {
                                            required property var modelData
                                            width: (compactStrategyBar.width - 8) / 3
                                            height: compactStrategyBar.height - 4
                                            radius: Math.max(2, Theme.radiusSmall - 1)
                                            color: strategyOptionsRow.optionSelected(modelData.value)
                                                   ? Theme.accentSoft
                                                   : (strategyMouse.containsMouse ? Theme.bgHover : "transparent")
                                            border.width: strategyOptionsRow.optionSelected(modelData.value) ? 1 : 0
                                            border.color: Theme.accentPressed
                                            activeFocusOnTab: true
                                            Text {
                                                anchors.centerIn: parent
                                                text: parent.modelData.label
                                                color: strategyOptionsRow.optionSelected(parent.modelData.value)
                                                       ? Theme.accent : Theme.textSecondary
                                                font.family: Theme.bodyFont
                                                font.pixelSize: 10
                                                font.weight: strategyOptionsRow.optionSelected(parent.modelData.value)
                                                             ? Font.DemiBold : Font.Normal
                                            }
                                            MouseArea {
                                                id: strategyMouse
                                                anchors.fill: parent
                                                hoverEnabled: true
                                                cursorShape: Qt.PointingHandCursor
                                                onPressed: parent.forceActiveFocus(Qt.MouseFocusReason)
                                                onClicked: strategyOptionsRow.toggleOption(parent.modelData.value)
                                            }
                                            Keys.onSpacePressed: strategyOptionsRow.toggleOption(modelData.value)
                                            Keys.onReturnPressed: strategyOptionsRow.toggleOption(modelData.value)
                                            Accessible.name: modelData.label
                                            Accessible.role: Accessible.CheckBox
                                            Accessible.checked: strategyOptionsRow.optionSelected(modelData.value)
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                id: uniqueLayerPicker
                                objectName: "uniqueLayerPicker"
                                width: parent.width
                                height: 32
                                enabled: batchExport.uniqueUseEnabled
                                opacity: enabled ? 1 : 0.46
                                radius: Theme.radiusSmall
                                color: selectorOpen || uniqueLayerMouse.containsMouse
                                       ? Theme.bgHover : Theme.bgControl
                                border.width: 1
                                border.color: selectorOpen || activeFocus
                                              ? Theme.focusRing
                                              : (selectedLayerCount > 0 ? Theme.accentPressed : Theme.borderStrong)
                                activeFocusOnTab: enabled && eligibleLayerCount > 0
                                property bool selectorOpen: false
                                readonly property bool openMenuAbove: window.height < 840

                                readonly property int eligibleLayerCount: {
                                    var count = 0
                                    var options = batchExport.uniqueLayerOptions
                                    for (var index = 0; index < options.length; index++) {
                                        if (options[index].eligible) count++
                                    }
                                    return count
                                }
                                readonly property int selectedLayerCount: {
                                    var count = 0
                                    var options = batchExport.uniqueLayerOptions
                                    for (var index = 0; index < options.length; index++) {
                                        if (options[index].eligible && options[index].selected) count++
                                    }
                                    return count
                                }

                                function toggleSelector() {
                                    if (eligibleLayerCount <= 0) return
                                    selectorOpen = !selectorOpen
                                }

                                onEnabledChanged: if (!enabled) selectorOpen = false

                                RowLayout {
                                    anchors.fill: parent
                                    anchors.leftMargin: 9
                                    anchors.rightMargin: 9
                                    spacing: 8
                                    BodyLabel {
                                        text: "限制图层"
                                        color: Theme.textSecondary
                                        font.pixelSize: 11
                                    }
                                    TinyLabel {
                                        Layout.fillWidth: true
                                        text: !batchExport.uniqueUseEnabled
                                              ? "启用单次用图后选择"
                                              : (uniqueLayerPicker.eligibleLayerCount <= 0
                                              ? "没有可用的图片图层"
                                              : (uniqueLayerPicker.selectedLayerCount > 0
                                                 ? "已选 " + uniqueLayerPicker.selectedLayerCount
                                                   + " / " + uniqueLayerPicker.eligibleLayerCount
                                                 : "请选择图片图层"))
                                        color: uniqueLayerPicker.eligibleLayerCount > 0
                                               && uniqueLayerPicker.selectedLayerCount === 0
                                               ? Theme.coral : Theme.textMuted
                                        elide: Text.ElideRight
                                    }
                                    AppIcon {
                                        iconName: AppIcons.selectIndicator
                                        iconSize: 12
                                        iconColor: batchExport.uniqueUseEnabled
                                                   && uniqueLayerPicker.eligibleLayerCount > 0
                                                   ? Theme.textMuted : Theme.textDisabled
                                    }
                                }

                                MouseArea {
                                    id: uniqueLayerMouse
                                    anchors.fill: parent
                                    enabled: batchExport.uniqueUseEnabled
                                             && uniqueLayerPicker.eligibleLayerCount > 0
                                    hoverEnabled: true
                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                    onPressed: uniqueLayerPicker.forceActiveFocus(Qt.MouseFocusReason)
                                    onClicked: uniqueLayerPicker.toggleSelector()
                                }
                                Keys.onSpacePressed: toggleSelector()
                                Keys.onReturnPressed: toggleSelector()
                                Keys.onEscapePressed: selectorOpen = false
                                Accessible.name: "单次用图限制图层"
                                Accessible.description: eligibleLayerCount <= 0
                                                        ? "没有可用的图片图层"
                                                        : "已选择 " + selectedLayerCount + " 个，共 " + eligibleLayerCount + " 个可用图层"
                                Accessible.role: Accessible.Button

                                Rectangle {
                                    id: uniqueLayerMenu
                                    objectName: "uniqueLayerMenu"
                                    x: 0
                                    y: uniqueLayerPicker.openMenuAbove
                                       ? -height - 4
                                       : uniqueLayerPicker.height + 4
                                    width: uniqueLayerPicker.width
                                    height: Math.min(180, Math.max(70, batchExport.uniqueLayerOptions.length * 32 + 38))
                                    visible: uniqueLayerPicker.selectorOpen
                                    z: 100
                                    radius: Theme.radius
                                    color: Theme.bgRaised
                                    border.width: 1
                                    border.color: Theme.borderStrong

                                    ListView {
                                        id: uniqueLayerList
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.top: parent.top
                                        anchors.bottom: uniqueLayerMenuFooter.top
                                        anchors.margins: 4
                                        clip: true
                                        model: uniqueLayerMenu.visible ? batchExport.uniqueLayerOptions : []
                                        boundsBehavior: Flickable.StopAtBounds

                                        delegate: ItemDelegate {
                                            id: uniqueLayerOption
                                            required property var modelData
                                            required property int index
                                            width: uniqueLayerList.width
                                            height: 32
                                            enabled: modelData.eligible
                                            highlighted: hovered
                                            onClicked: batchExport.setUniqueLayerSelected(modelData.index, !modelData.selected)

                                            contentItem: RowLayout {
                                                spacing: 8
                                                AppIcon {
                                                    iconName: uniqueLayerOption.modelData.selected
                                                              ? AppIcons.check : AppIcons.circleDot
                                                    iconSize: 13
                                                    iconColor: uniqueLayerOption.modelData.selected
                                                               ? Theme.accent : Theme.textMuted
                                                }
                                                BodyLabel {
                                                    Layout.fillWidth: true
                                                    text: uniqueLayerOption.modelData.label
                                                    color: uniqueLayerOption.modelData.eligible
                                                           ? Theme.textPrimary : Theme.textDisabled
                                                    elide: Text.ElideRight
                                                }
                                                TinyLabel {
                                                    visible: !uniqueLayerOption.modelData.eligible
                                                    text: "非图片图层"
                                                    color: Theme.textDisabled
                                                }
                                            }
                                            background: Rectangle {
                                                radius: Theme.radiusSmall
                                                color: uniqueLayerOption.modelData.selected
                                                       ? Theme.accentSoft
                                                       : (uniqueLayerOption.highlighted ? Theme.bgHover : "transparent")
                                            }
                                            Accessible.name: modelData.label
                                            Accessible.role: Accessible.CheckBox
                                            Accessible.checked: modelData.selected
                                        }
                                    }

                                    Rectangle {
                                        id: uniqueLayerMenuFooter
                                        anchors.left: parent.left
                                        anchors.right: parent.right
                                        anchors.bottom: parent.bottom
                                        anchors.margins: 4
                                        height: 30
                                        radius: Theme.radiusSmall
                                        color: uniqueLayerDoneMouse.containsMouse ? Theme.bgHover : "transparent"
                                        Row {
                                            anchors.centerIn: parent
                                            spacing: 6
                                            AppIcon { iconName: AppIcons.check; iconSize: 12; iconColor: Theme.accent }
                                            BodyLabel { text: "完成"; color: Theme.textPrimary; font.pixelSize: 11 }
                                        }
                                        MouseArea {
                                            id: uniqueLayerDoneMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: uniqueLayerPicker.selectorOpen = false
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            id: advancedStrategyEntry
                            Layout.fillWidth: true
                            Layout.preferredHeight: 42
                            radius: Theme.radiusSmall
                            color: advancedStrategyMouse.containsMouse || activeFocus ? Theme.bgRaised : "transparent"
                            border.width: 1
                            border.color: Theme.border
                            activeFocusOnTab: true

                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 8
                                anchors.rightMargin: 8
                                spacing: 8
                                Rectangle {
                                    Layout.preferredWidth: 24
                                    Layout.preferredHeight: 24
                                    radius: Theme.radiusSmall
                                    color: Theme.accentSoft
                                    AppIcon { anchors.centerIn: parent; iconName: AppIcons.sliders; iconSize: 13; iconColor: Theme.accent }
                                }
                                Column {
                                    Layout.fillWidth: true
                                    spacing: 0
                                    BodyLabel { text: "高级策略"; color: Theme.textPrimary; font.pixelSize: 11; font.weight: Font.DemiBold }
                                    TinyLabel { text: "质量、性能与保护"; font.pixelSize: 9 }
                                }
                                TinyLabel {
                                    text: (batchExport.qualityProfile === "quality" ? "高质量"
                                           : (batchExport.qualityProfile === "balanced" ? "均衡"
                                              : (batchExport.qualityProfile === "speed" ? "速度" : "体积")))
                                          + " · " + (batchExport.memoryGuardMode === "auto" ? "自动"
                                                       : (batchExport.memoryGuardMode === "low" ? "低内存"
                                                          : (batchExport.memoryGuardMode === "custom" ? "自定义" : "关闭")))
                                    color: Theme.textSecondary
                                }
                                AppIcon { iconName: AppIcons.chevronRight; iconSize: 12; iconColor: Theme.textMuted }
                            }
                            MouseArea {
                                id: advancedStrategyMouse
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onPressed: advancedStrategyEntry.forceActiveFocus(Qt.MouseFocusReason)
                                onClicked: batchExportAdvancedDialog.open()
                            }
                            Keys.onSpacePressed: batchExportAdvancedDialog.open()
                            Keys.onReturnPressed: batchExportAdvancedDialog.open()
                            Accessible.name: "高级策略"
                            Accessible.description: "打开质量、性能与保护设置"
                            Accessible.role: Accessible.Button
                        }

                        Item { Layout.fillHeight: true }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 8
                    spacing: 8

                    StatusBanner {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 46
                        tone: batchExport.errorMessage.length > 0 ? "error" : (batchExport.succeeded ? "success" : "neutral")

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            anchors.topMargin: 6
                            anchors.bottomMargin: 6
                            spacing: 8
                            AppIcon {
                                iconName: batchExport.errorMessage.length > 0 ? AppIcons.error : (batchExport.succeeded ? AppIcons.check : AppIcons.info)
                                iconSize: 14
                                iconColor: batchExport.errorMessage.length > 0 ? Theme.coral : (batchExport.succeeded ? Theme.success : Theme.accent)
                            }
                            Column {
                                Layout.fillWidth: true
                                spacing: 0
                                BodyLabel { text: batchExport.statusText; color: Theme.textPrimary; font.pixelSize: 11 }
                                TinyLabel {
                                    width: parent.width
                                    text: batchExport.errorMessage.length > 0
                                          ? batchExport.errorMessage
                                          : (batchExport.failureSummary.length > 0
                                             ? batchExport.failureSummary
                                             : (batchExport.lastFile.length > 0
                                                ? "最近文件  " + batchExport.lastFile
                                                : batchExport.stage))
                                    color: batchExport.errorMessage.length > 0 || batchExport.failureSummary.length > 0
                                           ? Theme.errorText : Theme.textMuted
                                    elide: batchExport.lastFile.length > 0 ? Text.ElideMiddle : Text.ElideRight
                                }
                            }
                            TinyLabel {
                                text: batchExport.running || batchExport.succeeded || batchExport.canceled
                                      ? batchExport.current + " / " + batchExport.total
                                      : "预计 " + batchExport.effectiveCount + " 张 · " + batchExport.estimatedTime
                                color: Theme.textSecondary
                            }
                        }
                        AppProgressBar {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.leftMargin: 1
                            anchors.rightMargin: 1
                            height: 3
                            visible: batchExport.running || batchExport.current > 0
                            progress: batchExport.progress
                            tone: batchExport.canceled ? "warning" : "accent"
                        }
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        ExportButton {
                            Layout.preferredWidth: 108
                            label: "保存配置"
                            iconName: AppIcons.save
                            enabled: !batchExport.running
                            onClicked: batchExport.saveSettings()
                        }
                        ExportButton {
                            Layout.preferredWidth: 104
                            label: "打开目录"
                            iconName: AppIcons.folderOpen
                            enabled: batchExport.outputDirectory.length > 0
                            onClicked: batchExport.openOutputDirectory()
                        }
                        ExportButton {
                            Layout.fillWidth: true
                            label: batchExport.running ? "取消导出" : (batchExport.canRetry ? "按原配置重试" : (batchExport.succeeded ? "再次导出" : "开始导出"))
                            iconName: batchExport.running ? AppIcons.close : AppIcons.exportAction
                            primary: !batchExport.running
                            destructive: batchExport.running
                            onClicked: batchExport.running ? batchExport.cancelExport() : (batchExport.canRetry ? batchExport.retryExport() : batchExport.startExport())
                        }
                    }
                }
            }
        }
    }

    AppDrawer {
        id: multiTabExportDrawer
        objectName: "multiTabExportDrawer"
        edge: Qt.RightEdge
        width: Math.min(540, Math.max(470, window.width * 0.34))
        height: window.height
        modal: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0

        Overlay.modal: Rectangle { color: Theme.overlayModal }
        background: Rectangle { color: Theme.bgPanel; border.width: 1; border.color: Theme.borderStrong }
        contentItem: ColumnLayout {
            anchors.fill: parent
            anchors.margins: 12
            spacing: 8

            RowLayout {
                Layout.fillWidth: true
                Rectangle {
                    Layout.preferredWidth: 32; Layout.preferredHeight: 32
                    radius: Theme.radiusSmall; color: Theme.accentSoft
                    AppIcon { anchors.centerIn: parent; iconName: AppIcons.listChecks; iconSize: 16; iconColor: Theme.accent }
                }
                Column {
                    Layout.fillWidth: true
                    spacing: 2
                    Text { text: "多标签批量导出"; color: Theme.textPrimary; font.family: Theme.displayFont; font.pixelSize: 17; font.weight: Font.DemiBold }
                    TinyLabel { text: multiTabExport.selectedDocumentCount + " 个标签页  ·  " + multiTabExport.totalImages + " 张" }
                }
                IconButton { iconName: AppIcons.close; tooltip: "关闭"; buttonSize: 30; onClicked: multiTabExportDrawer.close() }
            }
            Divider { Layout.fillWidth: true }

            RowLayout {
                Layout.fillWidth: true
                ExportField {
                    Layout.fillWidth: true
                    text: multiTabExport.outputDirectory
                    placeholder: "选择总输出目录"
                    readOnly: multiTabExport.running
                    onCommitted: value => multiTabExport.outputDirectory = value
                }
                IconButton { iconName: AppIcons.folderOpen; tooltip: "选择输出目录"; buttonSize: 36; active: true; onClicked: multiOutputFolderDialog.open() }
            }
            RowLayout {
                Layout.fillWidth: true
                ExportField {
                    Layout.fillWidth: true
                    text: multiTabExport.filenameTemplate
                    placeholder: "image_{number:04d}"
                    onCommitted: value => multiTabExport.filenameTemplate = value
                }
                SelectBox {
                    Layout.preferredWidth: 104
                    model: [
                        { label: "PNG", value: "png" },
                        { label: "JPG", value: "jpg" },
                        { label: "WEBP", value: "webp" }
                    ]
                    currentIndex: window.optionIndex(model, multiTabExport.fileFormat)
                    onActivated: multiTabExport.fileFormat = currentValue
                }
            }
            RowLayout {
                Layout.fillWidth: false
                spacing: 8

                OptionTile {
                    title: "智能采样"
                    detail: "跨标签均衡组合，降低重复"
                    selected: multiTabExport.avoidDuplicates
                    onActivated: multiTabExport.avoidDuplicates = !multiTabExport.avoidDuplicates
                }
                OptionTile {
                    title: "遍历组合"
                    detail: "各标签按组合顺序逐项生成"
                    selected: multiTabExport.traverseMode
                    onActivated: multiTabExport.traverseMode = !multiTabExport.traverseMode
                }
            }

            TinyLabel { text: "标签页任务"; color: Theme.textSecondary }
            ListView {
                Layout.fillWidth: true
                Layout.preferredHeight: Math.min(
                    Math.max(220, multiTabExport.count * 103),
                    Math.max(220, multiTabExportDrawer.height - 520)
                )
                Layout.maximumHeight: Layout.preferredHeight
                clip: true
                spacing: 5
                model: multiTabExport

                delegate: Rectangle {
                    required property int index
                    required property string title
                    required property bool selectedForExport
                    required property int exportCount
                    required property int startIndex
                    required property string subdirectory
                    required property string status
                    required property int progress
                    required property string error
                    required property string canvasSize
                    width: ListView.view.width
                    height: 98
                    radius: Theme.radiusSmall
                    color: selectedForExport ? Theme.bgControl : Theme.bgBar
                    border.width: 1
                    border.color: status === "失败" ? Theme.coral : (status === "导出中" ? Theme.accent : Theme.border)
                    opacity: selectedForExport ? 1 : 0.55

                    ColumnLayout {
                        anchors.fill: parent
                        anchors.margins: 7
                        spacing: 5
                        RowLayout {
                            Layout.fillWidth: true
                            ToggleSwitch { accessibleName: "导出 " + title; checked: selectedForExport; enabled: !multiTabExport.running; onToggled: checkedValue => multiTabExport.setDocumentEnabled(index, checkedValue) }
                            BodyLabel { text: title; color: Theme.textPrimary; Layout.fillWidth: true; elide: Text.ElideRight }
                            TinyLabel { text: canvasSize }
                            TinyLabel { text: status; color: status === "失败" ? Theme.coral : (status === "完成" ? Theme.success : Theme.textMuted) }
                        }
                        RowLayout {
                            Layout.fillWidth: true
                            TinyLabel { text: "数量" }
                            ExportField { Layout.preferredWidth: 64; text: String(exportCount); readOnly: multiTabExport.running; onCommitted: value => multiTabExport.setDocumentCount(index, parseInt(value) || 0) }
                            TinyLabel { text: "起始" }
                            ExportField { Layout.preferredWidth: 72; text: String(startIndex); readOnly: multiTabExport.running; onCommitted: value => multiTabExport.setDocumentStartIndex(index, parseInt(value) || 0) }
                            TinyLabel { text: "子目录" }
                            ExportField { Layout.fillWidth: true; text: subdirectory; readOnly: multiTabExport.running; onCommitted: value => multiTabExport.setDocumentSubdirectory(index, value) }
                        }
                        AppProgressBar {
                            Layout.fillWidth: true
                            Layout.preferredHeight: 3
                            visible: progress > 0
                            progress: Math.min(1, progress / Math.max(1, exportCount))
                            tone: status === "失败" ? "danger" : "accent"
                        }
                    }
                    ToolTip.visible: error.length > 0 && taskErrorMouse.containsMouse
                    ToolTip.text: error
                    MouseArea { id: taskErrorMouse; anchors.fill: parent; enabled: error.length > 0; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                }
            }

            ExportButton {
                Layout.fillWidth: true
                Layout.preferredHeight: 38
                label: multiTabExport.running ? "取消全部任务" : "开始多标签导出"
                iconName: multiTabExport.running ? AppIcons.close : AppIcons.listChecks
                primary: !multiTabExport.running && multiTabExport.selectedDocumentCount > 0 && multiTabExport.outputDirectory.length > 0
                destructive: multiTabExport.running
                enabled: multiTabExport.running || (multiTabExport.selectedDocumentCount > 0 && multiTabExport.outputDirectory.length > 0)
                onClicked: multiTabExport.running ? multiTabExport.cancelExport() : multiTabExport.startExport()
            }

            StatusBanner {
                Layout.fillWidth: true
                Layout.preferredHeight: 46
                tone: multiTabExport.failureSummary.length > 0 ? "error" : "neutral"
                RowLayout {
                    anchors.fill: parent
                    anchors.margins: 10
                    Column {
                        Layout.fillWidth: true
                        spacing: 2
                        BodyLabel { text: multiTabExport.statusText; color: Theme.textPrimary }
                        TinyLabel { text: multiTabExport.failureSummary.length > 0 ? multiTabExport.failureSummary : (multiTabExport.completedImages + " / " + multiTabExport.totalImages + " 张"); width: parent.width; elide: Text.ElideRight; color: multiTabExport.failureSummary.length > 0 ? Theme.coral : Theme.textMuted }
                    }
                    TinyLabel { text: Math.round(multiTabExport.progress * 100) + "%"; color: Theme.textSecondary }
                }
            }
            AppProgressBar {
                Layout.fillWidth: true
                Layout.preferredHeight: 4
                visible: multiTabExport.running || multiTabExport.completedImages > 0
                progress: multiTabExport.progress
                tone: multiTabExport.canceled ? "warning" : "accent"
            }
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
                    spacing: 22
                    Layout.preferredWidth: 360

                    MenuLabel {
                        height: 42; text: "文件"; hovered: fileMenuMouse.containsMouse
                        MouseArea { id: fileMenuMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: fileMenu.popup(parent, 0, parent.height) }
                    }
                    MenuLabel {
                        height: 42; text: "编辑"; hovered: editMenuMouse.containsMouse
                        MouseArea { id: editMenuMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: editMenu.popup(parent, 0, parent.height) }
                    }
                    MenuLabel {
                        height: 42; text: "图层"; hovered: layerMenuMouse.containsMouse
                        MouseArea { id: layerMenuMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: layerMenu.popup(parent, 0, parent.height) }
                    }
                    MenuLabel {
                        height: 42; text: "画布"; hovered: canvasMenuMouse.containsMouse
                        MouseArea { id: canvasMenuMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: canvasMenu.popup(parent, 0, parent.height) }
                    }
                    MenuLabel {
                        height: 42; text: "视图"; hovered: viewMenuMouse.containsMouse
                        MouseArea { id: viewMenuMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: viewMenu.popup(parent, 0, parent.height) }
                    }
                    MenuLabel {
                        height: 42; text: "帮助"; hovered: helpMenuMouse.containsMouse
                        MouseArea { id: helpMenuMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: helpMenu.popup(parent, 0, parent.height) }
                    }
                }

                Item { Layout.fillWidth: true }

                Row {
                    spacing: 8

                    Rectangle {
                        width: gpuRow.width + 18
                        height: 26
                        radius: 13
                        color: Theme.accentSoft
                        border.width: 1
                        border.color: Theme.accentPressed

                        Row {
                            id: gpuRow
                            anchors.centerIn: parent
                            spacing: 7
                            Rectangle { width: 6; height: 6; radius: 3; color: Theme.success; anchors.verticalCenter: parent.verticalCenter }
                            TinyLabel { text: "快速预览"; color: Theme.textSecondary; height: 20 }
                        }
                    }

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

                IconButton {
                    iconName: AppIcons.folderOpen
                    tooltip: "打开项目"
                    visible: window.hasOpenDocument
                    enabled: !workspace.operationsBlocked
                    onClicked: openDialog.open()
                }
                IconButton {
                    iconName: AppIcons.save
                    tooltip: "保存"
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    onClicked: workspace.hasFilePath ? workspace.saveDocument() : saveDialog.open()
                }
                IconButton {
                    iconName: AppIcons.fileText
                    tooltip: "项目预设"
                    enabled: !workspace.operationsBlocked
                    onClicked: window.openProjectPresetDrawer()
                }
                IconButton {
                    iconName: AppIcons.link
                    tooltip: "图层绑定管理"
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    onClicked: window.openDataRelations(0)
                }
                IconButton {
                    iconName: AppIcons.fitView
                    tooltip: "图层尺寸匹配"
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    onClicked: window.openDataRelations(1)
                }
                Divider { Layout.preferredHeight: 24; Layout.leftMargin: 3; Layout.rightMargin: 3 }
                IconButton { iconName: AppIcons.undo; tooltip: "撤销"; enabled: workspace.canUndo && !workspace.operationsBlocked; onClicked: workspace.undo() }
                IconButton { iconName: AppIcons.redo; tooltip: "重做"; enabled: workspace.canRedo && !workspace.operationsBlocked; onClicked: workspace.redo() }
                Divider { Layout.preferredHeight: 24; Layout.leftMargin: 3; Layout.rightMargin: 3 }

                AppButton {
                    Layout.preferredWidth: 106
                    text: "新建图层"
                    iconName: AppIcons.imageAdd
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    onClicked: workspace.addEmptyImageLayer()
                }

                IconButton { iconName: AppIcons.type; tooltip: "添加文字"; enabled: window.hasOpenDocument && !workspace.operationsBlocked; onClicked: textLayerDialog.openFresh() }
                IconButton {
                    iconName: AppIcons.shapes
                    tooltip: "添加异形图层"
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    onClicked: shapedLayerDialog.openFresh()
                }
                Divider { Layout.preferredHeight: 24; Layout.leftMargin: 3; Layout.rightMargin: 3 }

                Rectangle {
                    Layout.preferredWidth: alignmentTools.width + 8
                    Layout.preferredHeight: 32
                    radius: Theme.radiusSmall
                    color: Theme.bgBar
                    border.width: 1
                    border.color: Theme.border

                    Row {
                        id: alignmentTools
                        anchors.centerIn: parent
                        spacing: 0

                        AlignmentToolButton { alignmentMode: "left"; tooltip: "左对齐"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: window.alignCurrentSelection(alignmentMode) }
                        AlignmentToolButton { alignmentMode: "hcenter"; tooltip: "水平居中"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: window.alignCurrentSelection(alignmentMode) }
                        AlignmentToolButton { alignmentMode: "right"; tooltip: "右对齐"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: window.alignCurrentSelection(alignmentMode) }
                        AlignmentToolButton { alignmentMode: "top"; tooltip: "顶对齐"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: window.alignCurrentSelection(alignmentMode) }
                        AlignmentToolButton { alignmentMode: "vcenter"; tooltip: "垂直居中"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: window.alignCurrentSelection(alignmentMode) }
                        AlignmentToolButton { alignmentMode: "bottom"; tooltip: "底对齐"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: window.alignCurrentSelection(alignmentMode) }
                        AlignmentToolButton { distributionMode: "horizontal"; tooltip: "水平等距分布（至少 3 个图层）"; enabled: window.hasOpenDocument && workspace.selectedLayerCount > 2 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: workspace.distributeSelectedLayers(distributionMode) }
                        AlignmentToolButton { distributionMode: "vertical"; tooltip: "垂直等距分布（至少 3 个图层）"; enabled: window.hasOpenDocument && workspace.selectedLayerCount > 2 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: workspace.distributeSelectedLayers(distributionMode) }
                        Item {
                            width: 7
                            height: 30
                            Divider { anchors.centerIn: parent; width: 1; height: 18 }
                        }
                        AlignmentToolButton { alignmentMode: "center"; tooltip: "完全居中于画板"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: window.alignCurrentSelection(alignmentMode) }
                        AlignmentToolButton { alignmentMode: "same_size"; tooltip: "完全匹配画板大小"; enabled: window.hasOpenDocument && workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked; onClicked: window.alignCurrentSelection(alignmentMode) }
                    }
                }

                Item { Layout.fillWidth: true }

                AppButton {
                    Layout.preferredWidth: 92
                    text: "预览"
                    iconName: AppIcons.preview
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    onClicked: workspace.renderPreviewNow()
                }

                IconButton {
                    iconName: AppIcons.exportAction
                    tooltip: "导出当前画面"
                    buttonSize: 32
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    onClicked: exportDialog.open()
                }

                IconButton {
                    iconName: AppIcons.listChecks
                    tooltip: "多标签批量导出"
                    buttonSize: 32
                    enabled: window.hasOpenDocument && (!workspace.operationsBlocked || multiTabExport.running)
                    onClicked: window.openMultiTabExportDrawer()
                }

                AppButton {
                    Layout.preferredWidth: 112
                    text: "批量导出"
                    iconName: AppIcons.exportAction
                    variant: "primary"
                    enabled: window.hasOpenDocument && (!workspace.operationsBlocked || batchExport.running)
                    onClicked: window.openBatchExportDrawer()
                }
            }

            Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom }
        }

        Rectangle {
            id: documentTabs
            enabled: !workspace.operationsBlocked
            opacity: enabled ? 1 : 0.55
            Layout.fillWidth: true
            Layout.preferredHeight: 36
            color: Theme.bgBar

            RowLayout {
                anchors.fill: parent
                spacing: 0

                Item { Layout.preferredWidth: 48 }

                ListView {
                    id: documentTabList
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    orientation: ListView.Horizontal
                    boundsBehavior: Flickable.StopAtBounds
                    clip: true
                    spacing: 1
                    model: workspaceSessions
                    currentIndex: workspaceSessions.activeIndex

                    delegate: Rectangle {
                        id: documentTab
                        required property int index
                        required property string title
                        required property bool modified
                        required property bool active

                        width: Math.min(240, Math.max(150, tabTitle.implicitWidth + 70))
                        height: 36
                        color: active ? Theme.bgCanvas : (tabMouse.containsMouse ? Theme.bgRaised : Theme.bgBar)

                        Rectangle {
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.top: parent.top
                            height: 2
                            color: documentTab.active ? Theme.accent : "transparent"
                        }

                        RowLayout {
                            anchors.fill: parent
                            anchors.leftMargin: 10
                            anchors.rightMargin: 5
                            spacing: 7
                            Rectangle { Layout.preferredWidth: 6; Layout.preferredHeight: 6; radius: 3; color: Theme.amber; visible: documentTab.modified }
                            Text {
                                id: tabTitle
                                Layout.fillWidth: true
                                text: documentTab.title
                                color: documentTab.active ? Theme.textPrimary : Theme.textSecondary
                                font.family: Theme.bodyFont
                                font.pixelSize: 11
                                font.weight: documentTab.active ? Font.DemiBold : Font.Normal
                                elide: Text.ElideMiddle
                                verticalAlignment: Text.AlignVCenter
                            }
                            IconButton {
                                iconName: AppIcons.close
                                tooltip: "关闭文档"
                                buttonSize: 24
                                onClicked: workspaceSessions.requestClose(documentTab.index)
                            }
                        }

                        MouseArea {
                            id: tabMouse
                            anchors.fill: parent
                            anchors.rightMargin: 30
                            acceptedButtons: Qt.LeftButton | Qt.RightButton
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onPressed: function(mouse) {
                                if (mouse.button === Qt.RightButton) {
                                    contextDocumentIndex = documentTab.index
                                    workspaceSessions.activateDocument(documentTab.index)
                                    documentTabMenu.popup(documentTab, mouse.x, mouse.y)
                                }
                            }
                            onClicked: function(mouse) {
                                if (mouse.button === Qt.LeftButton)
                                    workspaceSessions.activateDocument(documentTab.index)
                            }
                        }
                    }
                }

                IconButton {
                    iconName: AppIcons.add
                    tooltip: "新建文档"
                    buttonSize: 36
                    Layout.preferredWidth: 40
                    visible: window.hasOpenDocument
                    onClicked: window.openNewCanvasDialog()
                }
            }

            Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom }
        }

        RowLayout {
            id: workspaceArea
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: 0
            enabled: !workspace.operationsBlocked
            opacity: enabled ? 1 : 0.72

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

                    ToolRailButton { toolIndex: 0; iconName: AppIcons.pointer; label: "选择工具 (V)"; enabled: window.hasOpenDocument }
                    ToolRailButton { toolIndex: 1; iconName: AppIcons.hand; label: "抓手工具 (H)"; enabled: window.hasOpenDocument }
                }

                Column {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottomMargin: 10
                    spacing: 6

                    Rectangle {
                        width: 26; height: 26; radius: 4; color: Theme.swatchSurface; border.width: 1; border.color: Theme.borderStrong
                        Rectangle { width: 15; height: 15; anchors.left: parent.left; anchors.top: parent.top; anchors.margins: 3; color: Theme.accent; border.width: 1; border.color: Theme.swatchAccentBorder }
                        Rectangle { width: 15; height: 15; anchors.right: parent.right; anchors.bottom: parent.bottom; anchors.margins: 3; color: Theme.swatchPaper; border.width: 1; border.color: Theme.borderStrong }
                    }
                }

                Divider { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right }
            }

            Rectangle {
                id: layerPanel
                Layout.preferredWidth: window.width < 1320 ? 246 : 276
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
                    }

                    Divider { Layout.fillWidth: true }

                    ListView {
                        id: layerList
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        clip: true
                        model: layerModel
                        currentIndex: -1
                        boundsBehavior: Flickable.StopAtBounds

                        delegate: Rectangle {
                            id: layerDelegate
                            required property int index
                            required property string name
                            required property string typeName
                            required property string iconName
                            required property color accent
                            required property bool shown
                            required property bool locked
                            required property bool selected
                            required property int depth
                            required property bool isGroup
                            required property bool expanded
                            required property bool parentExpanded
                            required property int layerIndex

                            width: layerList.width
                            height: parentExpanded ? 58 : 0
                            visible: parentExpanded
                            color: selected ? Theme.bgSelected : (layerMouse.containsMouse ? Theme.bgRaised : "transparent")

                            Rectangle {
                                anchors.left: parent.left
                                anchors.top: parent.top
                                anchors.bottom: parent.bottom
                                width: 2
                                color: selected ? Theme.accent : "transparent"
                            }

                            IconButton {
                                id: eyeButton
                                anchors.left: parent.left
                                anchors.leftMargin: 6 + layerDelegate.depth * 12
                                anchors.verticalCenter: parent.verticalCenter
                                iconName: layerDelegate.shown ? AppIcons.eye : AppIcons.eyeOff
                                tooltip: layerDelegate.shown ? "隐藏图层" : "显示图层"
                                buttonSize: 28
                                onClicked: workspace.toggleLayerVisible(layerDelegate.layerIndex)
                            }

                            IconButton {
                                id: disclosureButton
                                anchors.left: eyeButton.right
                                anchors.leftMargin: 1
                                anchors.verticalCenter: parent.verticalCenter
                                visible: layerDelegate.isGroup
                                iconName: layerDelegate.expanded ? AppIcons.chevronDown : AppIcons.chevronRight
                                tooltip: layerDelegate.expanded ? "折叠图层组" : "展开图层组"
                                buttonSize: 22
                                onClicked: workspace.toggleLayerGroupExpanded(layerDelegate.layerIndex)
                            }

                            Rectangle {
                                anchors.left: layerDelegate.isGroup ? disclosureButton.right : eyeButton.right
                                anchors.leftMargin: 4
                                anchors.verticalCenter: parent.verticalCenter
                                width: 36
                                height: 36
                                radius: Theme.radiusSmall
                                color: Theme.bgControl
                                border.width: 1
                                border.color: Theme.borderStrong

                                AppIcon {
                                    anchors.centerIn: parent
                                    iconName: layerDelegate.iconName
                                    iconSize: 16
                                    iconColor: layerDelegate.accent
                                }
                            }

                            Column {
                                anchors.left: parent.left
                                anchors.leftMargin: 82 + layerDelegate.depth * 12 + (layerDelegate.isGroup ? 20 : 0)
                                anchors.right: lockButton.left
                                anchors.rightMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                spacing: 3
                                Text { width: parent.width; text: layerDelegate.name; color: layerDelegate.selected ? Theme.textPrimary : Theme.textSecondary; font.family: Theme.bodyFont; font.pixelSize: 11; font.weight: layerDelegate.selected ? Font.DemiBold : Font.Normal; elide: Text.ElideRight }
                                TinyLabel { text: layerDelegate.typeName; color: Theme.textMuted; height: 15 }
                            }

                            IconButton {
                                id: lockButton
                                anchors.right: parent.right
                                anchors.rightMargin: 6
                                anchors.verticalCenter: parent.verticalCenter
                                iconName: layerDelegate.locked ? AppIcons.lock : AppIcons.unlock
                                tooltip: layerDelegate.locked ? "解锁图层" : "锁定图层"
                                buttonSize: 28
                                onClicked: workspace.toggleLayerLocked(layerDelegate.layerIndex)
                            }

                            MouseArea {
                                id: layerMouse
                                anchors.fill: parent
                                anchors.leftMargin: 38
                                anchors.rightMargin: 38
                                acceptedButtons: Qt.LeftButton | Qt.RightButton
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                drag.target: layerDelegate
                                drag.axis: Drag.YAxis
                                drag.minimumY: 0
                                drag.maximumY: Math.max(0, layerList.contentHeight - layerDelegate.height)
                                property real dragStartY: 0
                                onPressed: mouse => {
                                    dragStartY = layerDelegate.y
                                    if (mouse.button === Qt.RightButton) {
                                        if (!layerDelegate.selected)
                                            workspace.selectLayer(layerDelegate.layerIndex)
                                        layerContextMenu.popup()
                                    }
                                }
                                onClicked: mouse => {
                                    if (mouse.button !== Qt.LeftButton) return
                                    workspace.selectLayerWithModifiers(
                                        layerDelegate.layerIndex,
                                        (mouse.modifiers & Qt.ControlModifier) !== 0,
                                        (mouse.modifiers & Qt.ShiftModifier) !== 0
                                    )
                                }
                                onReleased: mouse => {
                                    if (mouse.button !== Qt.LeftButton || Math.abs(layerDelegate.y - dragStartY) < 8) return
                                    var mapped = layerDelegate.mapToItem(layerList.contentItem, 8, layerDelegate.height / 2)
                                    var dropIndex = layerList.indexAt(mapped.x, mapped.y)
                                    if (dropIndex >= 0) {
                                        var targetItem = layerList.itemAtIndex(dropIndex)
                                        if (targetItem)
                                            workspace.moveSelectedLayersTo(targetItem.layerIndex)
                                    }
                                }
                            }

                            AppMenu {
                                id: layerContextMenu
                                ShapeMenuItem {
                                    text: workspace.selectedLayerCount > 1 ? "复制所选图层" : "复制图层"
                                    onTriggered: workspace.selectedLayerCount > 1
                                                 ? workspace.duplicateSelectedLayers()
                                                 : workspace.duplicateSelectedLayer()
                                }
                                ShapeMenuItem { text: "建立图层组"; enabled: workspace.canGroupSelectedLayers; onTriggered: workspace.groupSelectedLayers() }
                                ShapeMenuItem { text: "解散图层组"; enabled: workspace.canUngroupSelectedLayers; onTriggered: workspace.ungroupSelectedGroups() }
                                MenuSeparator { }
                                ShapeMenuItem { text: "显示所选"; onTriggered: workspace.setSelectedLayersVisible(true) }
                                ShapeMenuItem { text: "隐藏所选"; onTriggered: workspace.setSelectedLayersVisible(false) }
                                ShapeMenuItem { text: "锁定所选"; onTriggered: workspace.setSelectedLayersLocked(true) }
                                ShapeMenuItem { text: "解锁所选"; onTriggered: workspace.setSelectedLayersLocked(false) }
                                MenuSeparator { }
                                ShapeMenuItem { text: "左对齐"; enabled: workspace.selectedLayerCount > 1; onTriggered: workspace.alignSelectedLayers("left") }
                                ShapeMenuItem { text: "水平居中"; enabled: workspace.selectedLayerCount > 1; onTriggered: workspace.alignSelectedLayers("hcenter") }
                                ShapeMenuItem { text: "右对齐"; enabled: workspace.selectedLayerCount > 1; onTriggered: workspace.alignSelectedLayers("right") }
                                ShapeMenuItem { text: "顶对齐"; enabled: workspace.selectedLayerCount > 1; onTriggered: workspace.alignSelectedLayers("top") }
                                ShapeMenuItem { text: "垂直居中"; enabled: workspace.selectedLayerCount > 1; onTriggered: workspace.alignSelectedLayers("vcenter") }
                                ShapeMenuItem { text: "底对齐"; enabled: workspace.selectedLayerCount > 1; onTriggered: workspace.alignSelectedLayers("bottom") }
                                ShapeMenuItem { text: "双向居中"; enabled: workspace.selectedLayerCount > 1; onTriggered: workspace.alignSelectedLayers("center") }
                                ShapeMenuItem { text: "相同尺寸"; enabled: workspace.selectedLayerCount > 1; onTriggered: workspace.alignSelectedLayers("same_size") }
                                ShapeMenuItem { text: "水平等距"; enabled: workspace.selectedLayerCount > 2; onTriggered: workspace.distributeSelectedLayers("horizontal") }
                                ShapeMenuItem { text: "垂直等距"; enabled: workspace.selectedLayerCount > 2; onTriggered: workspace.distributeSelectedLayers("vertical") }
                                MenuSeparator { }
                                ShapeMenuItem { text: "删除所选图层"; onTriggered: workspace.deleteSelectedLayers() }
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
                            IconButton {
                                iconName: AppIcons.copy
                                tooltip: workspace.selectedLayerCount > 1 ? "复制所选图层" : "复制图层"
                                buttonSize: 28
                                enabled: workspace.selectedLayerCount > 1 || workspace.canDuplicateLayer
                                onClicked: workspace.selectedLayerCount > 1
                                           ? workspace.duplicateSelectedLayers()
                                           : workspace.duplicateSelectedLayer()
                            }
                            IconButton {
                                iconName: AppIcons.copy
                                tooltip: "复制图层样式"
                                buttonSize: 28
                                visible: workspace.selectedLayerCount <= 1
                                enabled: workspace.selectedLayerIndex >= 0 && !workspace.operationsBlocked
                                onClicked: workspace.copySelectedLayerStyle()
                            }
                            IconButton {
                                iconName: AppIcons.paste
                                tooltip: workspace.hasLayerStyleClipboard
                                         ? "粘贴图层样式 · " + workspace.layerStyleClipboardSummary
                                         : "粘贴图层样式 · 尚未复制"
                                buttonSize: 28
                                visible: workspace.selectedLayerCount <= 1
                                enabled: workspace.hasLayerStyleClipboard
                                         && workspace.selectedLayerIndex >= 0
                                         && !workspace.selectedLocked
                                         && !workspace.operationsBlocked
                                onClicked: workspace.pasteSelectedLayerStyle()
                            }
                            IconButton {
                                iconName: AppIcons.group
                                tooltip: "建立图层组"
                                buttonSize: 28
                                visible: workspace.selectedLayerCount > 1
                                enabled: workspace.canGroupSelectedLayers
                                onClicked: workspace.groupSelectedLayers()
                            }
                            IconButton {
                                iconName: AppIcons.ungroup
                                tooltip: "解散图层组"
                                buttonSize: 28
                                visible: workspace.canUngroupSelectedLayers
                                enabled: workspace.canUngroupSelectedLayers
                                onClicked: workspace.ungroupSelectedGroups()
                            }
                            IconButton {
                            iconName: AppIcons.arrowDown
                                tooltip: "后移一层 · Ctrl+["
                                buttonSize: 28
                                visible: workspace.selectedLayerCount <= 1
                                enabled: workspace.canMoveLayerBackward
                                onClicked: workspace.moveSelectedLayer("backward")
                            }
                            IconButton {
                            iconName: AppIcons.arrowUp
                                tooltip: "前移一层 · Ctrl+]"
                                buttonSize: 28
                                visible: workspace.selectedLayerCount <= 1
                                enabled: workspace.canMoveLayerForward
                                onClicked: workspace.moveSelectedLayer("forward")
                            }
                            IconButton {
                                iconName: AppIcons.trash
                                tooltip: "删除图层"
                                buttonSize: 28
                                enabled: workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked
                                onClicked: workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup
                                           ? workspace.deleteSelectedLayers()
                                           : workspace.deleteSelectedLayer()
                            }
                        }
                    }
                }

                Divider { anchors.top: parent.top; anchors.bottom: parent.bottom; anchors.right: parent.right }
            }

            Rectangle {
                id: canvasWorkspace
                Layout.fillWidth: true
                Layout.fillHeight: true
                color: Theme.bgCanvas
                clip: true

                property real safeCanvasWidth: Math.max(1, workspace.canvasWidth)
                property real safeCanvasHeight: Math.max(1, workspace.canvasHeight)
                property real fitScale: Math.min(
                    (height - 54) / safeCanvasHeight,
                    (width - 60) / safeCanvasWidth
                )
                property real actualScale: workspace.zoomFactor
                property int rulerSize: 22
                property bool transformActive: false
                property string transformMode: ""
                property real gestureStartMouseX: 0
                property real gestureStartMouseY: 0
                property real gestureStartX: 0
                property real gestureStartY: 0
                property real gestureStartWidth: 1
                property real gestureStartHeight: 1
                property real gestureStartLocalX: 0
                property real gestureStartLocalY: 0
                property real transientX: workspace.selectedX
                property real transientY: workspace.selectedY
                property real transientWidth: Math.max(1, workspace.selectedWidth)
                property real transientHeight: Math.max(1, workspace.selectedHeight)
                property bool marqueeActive: false
                property bool marqueeAdditive: false
                property real marqueeStartX: 0
                property real marqueeStartY: 0
                property real marqueeCurrentX: 0
                property real marqueeCurrentY: 0

                // —— 空格临时抓手（Photoshop 风格：按住空格+左键拖拽平移视图）
                property bool spacePressedTemp: false
                focus: true
                HoverHandler {
                    // 鼠标进入画布时抢占焦点，确保画布能接收 Space 这类键盘事件
                    onHoveredChanged: if (hovered) canvasWorkspace.forceActiveFocus(Qt.MouseFocusReason)
                }
                Keys.onPressed: event => {
                    if (event.key === Qt.Key_Space && !event.isAutoRepeat) {
                        if (!selectedTextEditor.editing && !window._editableInputHasFocus) {
                            spacePressedTemp = true
                            event.accepted = true
                        }
                    }
                }
                Keys.onReleased: event => {
                    if (event.key === Qt.Key_Space && !event.isAutoRepeat && spacePressedTemp) {
                        spacePressedTemp = false
                        event.accepted = true
                    }
                }

                DropArea {
                    id: imageDropArea
                    anchors.fill: parent
                    enabled: window.hasOpenDocument && !workspace.operationsBlocked
                    z: 100

                    onEntered: function(drag) {
                        drag.accepted = drag.hasUrls && window.hasSupportedImageUrl(drag.urls)
                    }
                    onDropped: function(drop) {
                        if (drop.hasUrls && window.addDroppedImages(drop.urls) > 0)
                            drop.acceptProposedAction()
                        else
                            drop.accepted = false
                    }

                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 12
                        visible: imageDropArea.containsDrag
                        color: Qt.rgba(Theme.accent.r, Theme.accent.g, Theme.accent.b, 0.10)
                        border.width: 1
                        border.color: Theme.accent
                        radius: Theme.radius

                        Column {
                            anchors.centerIn: parent
                            spacing: 6
                            AppIcon {
                                anchors.horizontalCenter: parent.horizontalCenter
                                iconName: AppIcons.imageAdd
                                iconSize: 24
                                iconColor: Theme.accent
                            }
                            BodyLabel {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "释放以添加图片图层"
                                color: Theme.textPrimary
                            }
                            TinyLabel {
                                anchors.horizontalCenter: parent.horizontalCenter
                                text: "支持同时拖入多张图片"
                            }
                        }
                    }
                }

                function rulerMajorStep() {
                    var desiredCanvasUnits = 80 / Math.max(0.001, actualScale)
                    var magnitude = Math.pow(10, Math.floor(Math.log(desiredCanvasUnits) / Math.LN10))
                    var normalized = desiredCanvasUnits / magnitude
                    if (normalized <= 1) return magnitude
                    if (normalized <= 2) return 2 * magnitude
                    if (normalized <= 5) return 5 * magnitude
                    return 10 * magnitude
                }

                function rulerLabel(value, majorStep) {
                    if (Math.abs(value) < majorStep / 1000) return "0"
                    if (majorStep >= 1) return String(Math.round(value))
                    var decimals = Math.max(0, Math.ceil(-Math.log(majorStep) / Math.LN10))
                    return Number(value).toFixed(decimals)
                }

                Row {
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.topMargin: workspace.showRulers ? canvasWorkspace.rulerSize + 8 : 10
                    anchors.rightMargin: 10
                    spacing: 3
                    z: 30
                    visible: window.hasOpenDocument

                    Rectangle {
                        width: guideTools.width + 10
                        height: 36
                        radius: Theme.radiusSmall
                        color: Theme.bgBar
                        border.width: 1
                        border.color: Theme.borderStrong
                        Row {
                            id: guideTools
                            anchors.centerIn: parent
                            spacing: 1
                            IconButton { iconName: AppIcons.ruler; tooltip: "显示标尺"; active: workspace.showRulers; buttonSize: 30; onClicked: workspace.setShowRulers(!workspace.showRulers) }
                            IconButton { iconName: AppIcons.guides; tooltip: "显示参考线"; active: workspace.showGuides; buttonSize: 30; onClicked: workspace.setShowGuides(!workspace.showGuides) }
                            IconButton { iconName: AppIcons.magnet; tooltip: "吸附到参考线"; active: workspace.snapToGuides; buttonSize: 30; onClicked: workspace.setSnapToGuides(!workspace.snapToGuides) }
                            IconButton { iconName: AppIcons.trash; tooltip: "清空参考线"; buttonSize: 30; enabled: workspace.horizontalGuides.length + workspace.verticalGuides.length > 0; onClicked: workspace.clearGuides() }
                            IconButton {
                                iconName: AppIcons.fileImage
                                tooltip: "画布预设"
                                buttonSize: 30
                                onClicked: {
                                    presetWidthInput.text = String(workspace.canvasWidth)
                                    presetHeightInput.text = String(workspace.canvasHeight)
                                    canvasPresetDrawer.open()
                                }
                            }
                            Item {
                                width: 7
                                height: 30
                                Divider { anchors.centerIn: parent; width: 1; height: 18 }
                            }
                            IconButton {
                                id: randomizeAllLayersButton
                                iconName: AppIcons.randomize
                                tooltip: "随机化所有图层\n绑定的图层将选择匹配的图片"
                                buttonSize: 30
                                primary: enabled
                                enabled: workspace.layerCount > 0 && !workspace.operationsBlocked
                                onClicked: workspace.randomizeAllLayers()
                            }
                        }
                    }
                }

                function selectedLocalPoint(canvasX, canvasY) {
                    var aggregate = workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup
                    var width = Math.max(1, aggregate ? workspace.selectionBoundsWidth : workspace.selectedWidth)
                    var height = Math.max(1, aggregate ? workspace.selectionBoundsHeight : workspace.selectedHeight)
                    var originX = aggregate ? workspace.selectionBoundsX : workspace.selectedX
                    var originY = aggregate ? workspace.selectionBoundsY : workspace.selectedY
                    var centerX = originX + width / 2
                    var centerY = originY + height / 2
                    var radians = (aggregate ? 0 : workspace.selectedRotation) * Math.PI / 180
                    var offsetX = canvasX - centerX
                    var offsetY = canvasY - centerY
                    return {
                        "x": Math.cos(radians) * offsetX + Math.sin(radians) * offsetY + width / 2,
                        "y": -Math.sin(radians) * offsetX + Math.cos(radians) * offsetY + height / 2
                    }
                }

                function handleAt(canvasX, canvasY) {
                    if (workspace.selectedLayerIndex < 0 || workspace.selectedLocked)
                        return ""
                    var point = selectedLocalPoint(canvasX, canvasY)
                    var aggregate = workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup
                    var width = Math.max(1, aggregate ? workspace.selectionBoundsWidth : workspace.selectedWidth)
                    var height = Math.max(1, aggregate ? workspace.selectionBoundsHeight : workspace.selectedHeight)
                    var tolerance = 10 / actualScale
                    var nearLeft = Math.abs(point.x) <= tolerance
                    var nearRight = Math.abs(point.x - width) <= tolerance
                    var nearTop = Math.abs(point.y) <= tolerance
                    var nearBottom = Math.abs(point.y - height) <= tolerance
                    if (nearLeft && nearTop) return "nw"
                    if (nearRight && nearTop) return "ne"
                    if (nearLeft && nearBottom) return "sw"
                    if (nearRight && nearBottom) return "se"
                    if (nearTop) return "n"
                    if (nearRight) return "e"
                    if (nearBottom) return "s"
                    if (nearLeft) return "w"
                    return ""
                }

                function selectedContains(canvasX, canvasY) {
                    if (workspace.selectedLayerIndex < 0)
                        return false
                    var point = selectedLocalPoint(canvasX, canvasY)
                    var aggregate = workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup
                    var width = aggregate ? workspace.selectionBoundsWidth : workspace.selectedWidth
                    var height = aggregate ? workspace.selectionBoundsHeight : workspace.selectedHeight
                    return point.x >= 0 && point.x <= width && point.y >= 0 && point.y <= height
                }

                function pointerCursor(canvasX, canvasY) {
                    var handle = handleAt(canvasX, canvasY)
                    if (handle === "nw" || handle === "se") return Qt.SizeFDiagCursor
                    if (handle === "ne" || handle === "sw") return Qt.SizeBDiagCursor
                    if (handle === "n" || handle === "s") return Qt.SizeVerCursor
                    if (handle === "e" || handle === "w") return Qt.SizeHorCursor
                    if (!workspace.selectedLocked && selectedContains(canvasX, canvasY)) return Qt.OpenHandCursor
                    return Qt.ArrowCursor
                }

                function beginTransform(mode, canvasX, canvasY) {
                    transformMode = mode
                    gestureStartMouseX = canvasX
                    gestureStartMouseY = canvasY
                    var aggregate = workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup
                    gestureStartX = aggregate ? workspace.selectionBoundsX : workspace.selectedX
                    gestureStartY = aggregate ? workspace.selectionBoundsY : workspace.selectedY
                    gestureStartWidth = Math.max(1, aggregate ? workspace.selectionBoundsWidth : workspace.selectedWidth)
                    gestureStartHeight = Math.max(1, aggregate ? workspace.selectionBoundsHeight : workspace.selectedHeight)
                    var localPoint = selectedLocalPoint(canvasX, canvasY)
                    gestureStartLocalX = localPoint.x
                    gestureStartLocalY = localPoint.y
                    transientX = gestureStartX
                    transientY = gestureStartY
                    transientWidth = gestureStartWidth
                    transientHeight = gestureStartHeight
                    transformActive = true
                }

                function updateTransform(canvasX, canvasY) {
                    if (!transformActive)
                        return
                    var deltaX = canvasX - gestureStartMouseX
                    var deltaY = canvasY - gestureStartMouseY
                    var minimumSize = 10
                    if (transformMode === "move") {
                        transientX = gestureStartX + deltaX
                        transientY = gestureStartY + deltaY
                        return
                    }

                    var localPoint = selectedLocalPoint(canvasX, canvasY)
                    var localDeltaX = localPoint.x - gestureStartLocalX
                    var localDeltaY = localPoint.y - gestureStartLocalY
                    var right = gestureStartX + gestureStartWidth
                    var bottom = gestureStartY + gestureStartHeight
                    var changesLeft = transformMode === "nw" || transformMode === "w" || transformMode === "sw"
                    var changesRight = transformMode === "ne" || transformMode === "e" || transformMode === "se"
                    var changesTop = transformMode === "nw" || transformMode === "n" || transformMode === "ne"
                    var changesBottom = transformMode === "sw" || transformMode === "s" || transformMode === "se"
                    if (workspace.selectedAspectRatioLocked && transformMode.length === 2) {
                        var fixedX = transformMode === "nw" || transformMode === "sw" ? right : gestureStartX
                        var fixedY = transformMode === "nw" || transformMode === "ne" ? bottom : gestureStartY
                        var desiredWidth = transformMode === "nw" || transformMode === "sw"
                                ? gestureStartWidth - localDeltaX : gestureStartWidth + localDeltaX
                        var desiredHeight = transformMode === "nw" || transformMode === "ne"
                                ? gestureStartHeight - localDeltaY : gestureStartHeight + localDeltaY
                        var scale = (desiredWidth * gestureStartWidth + desiredHeight * gestureStartHeight)
                                / (gestureStartWidth * gestureStartWidth + gestureStartHeight * gestureStartHeight)
                        var minimumScale = Math.max(minimumSize / gestureStartWidth, minimumSize / gestureStartHeight)
                        scale = Math.max(minimumScale, scale)
                        transientWidth = gestureStartWidth * scale
                        transientHeight = gestureStartHeight * scale
                        transientX = transformMode === "nw" || transformMode === "sw"
                                ? fixedX - transientWidth : fixedX
                        transientY = transformMode === "nw" || transformMode === "ne"
                                ? fixedY - transientHeight : fixedY
                        return
                    }
                    if (changesLeft) {
                        transientX = Math.min(right - minimumSize, gestureStartX + localDeltaX)
                        transientWidth = right - transientX
                    } else if (changesRight) {
                        transientWidth = Math.max(minimumSize, gestureStartWidth + localDeltaX)
                    }
                    if (changesTop) {
                        transientY = Math.min(bottom - minimumSize, gestureStartY + localDeltaY)
                        transientHeight = bottom - transientY
                    } else if (changesBottom) {
                        transientHeight = Math.max(minimumSize, gestureStartHeight + localDeltaY)
                    }
                }

                function commitTransform() {
                    if (!transformActive)
                        return
                    var finalX = Math.round(transientX)
                    var finalY = Math.round(transientY)
                    var finalWidth = Math.round(transientWidth)
                    var finalHeight = Math.round(transientHeight)
                    var snapped = workspace.snapPosition(finalX, finalY, finalWidth, finalHeight, 6 / canvasWorkspace.actualScale)
                    finalX = Math.round(snapped.x)
                    finalY = Math.round(snapped.y)
                    transformActive = false
                    transformMode = ""
                    if (workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup)
                        workspace.transformSelectedLayers(finalX, finalY, finalWidth, finalHeight)
                    else
                        workspace.applySelectedGeometry(finalX, finalY, finalWidth, finalHeight)
                }

                function cancelTransform() {
                    transformActive = false
                    transformMode = ""
                }

                WheelHandler {
                    target: null
                    enabled: window.hasOpenDocument
                    onWheel: event => {
                        var direction = event.angleDelta.y > 0 ? 1 : -1
                        workspace.setZoomFactor(direction > 0 ? workspace.zoomFactor * 1.1 : workspace.zoomFactor / 1.1)
                        event.accepted = true
                    }
                }

                Canvas {
                    anchors.fill: parent
                    visible: window.hasOpenDocument
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

                DragHandler {
                    id: canvasPanHandler
                    target: null
                    enabled: window.hasOpenDocument
                    // 抓手工具(H)或空格临时抓手时都允许左键拖拽平移；否则仅中键
                    acceptedButtons: (activeTool === 1 || canvasWorkspace.spacePressedTemp)
                                      ? Qt.LeftButton | Qt.MiddleButton
                                      : Qt.MiddleButton
                    cursorShape: active
                                  ? Qt.ClosedHandCursor
                                  : ((activeTool === 1 || canvasWorkspace.spacePressedTemp)
                                     ? Qt.OpenHandCursor
                                     : Qt.ArrowCursor)
                    property int startOffsetX: 0
                    property int startOffsetY: 0
                    onActiveChanged: {
                        if (active) {
                            startOffsetX = workspace.viewOffsetX
                            startOffsetY = workspace.viewOffsetY
                        }
                    }
                    onTranslationChanged: {
                        if (!active) return
                        workspace.setViewOffset(
                            Math.round(startOffsetX + translation.x),
                            Math.round(startOffsetY + translation.y)
                        )
                    }
                }

                Item {
                    id: artboardFrame
                    visible: window.hasOpenDocument
                    width: canvasWorkspace.safeCanvasWidth * canvasWorkspace.actualScale
                    height: canvasWorkspace.safeCanvasHeight * canvasWorkspace.actualScale
                    anchors.centerIn: parent
                    anchors.horizontalCenterOffset: workspace.viewOffsetX
                    anchors.verticalCenterOffset: workspace.viewOffsetY

                    Rectangle {
                        id: artboard
                        objectName: "artboard"
                        width: canvasWorkspace.safeCanvasWidth
                        height: canvasWorkspace.safeCanvasHeight
                        scale: canvasWorkspace.actualScale
                        transformOrigin: Item.TopLeft
                        color: Theme.canvasPaper
                        border.width: 1
                        border.color: Theme.canvasPaperBorder

                        Image {
                            id: documentPreview
                            anchors.fill: parent
                            source: workspace.previewSource
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            cache: false
                            smooth: true
                        }

                        Repeater {
                            model: workspace.horizontalGuides
                            delegate: Rectangle {
                                id: horizontalGuide
                                required property int index
                                required property real modelData
                                visible: workspace.showGuides
                                x: 0
                                y: modelData
                                width: artboard.width
                                height: Math.max(1, 1 / canvasWorkspace.actualScale)
                                color: Theme.guide
                                z: 15
                                MouseArea {
                                    anchors.left: parent.left
                                    anchors.right: parent.right
                                    anchors.verticalCenter: parent.verticalCenter
                                    height: Math.max(8, 8 / canvasWorkspace.actualScale)
                                    cursorShape: Qt.SizeVerCursor
                                    drag.target: horizontalGuide
                                    drag.axis: Drag.YAxis
                                    drag.minimumY: 0
                                    drag.maximumY: artboard.height
                                    onReleased: workspace.moveGuide("horizontal", index, horizontalGuide.y)
                                    onDoubleClicked: workspace.removeGuide("horizontal", index)
                                }
                            }
                        }

                        Repeater {
                            model: workspace.verticalGuides
                            delegate: Rectangle {
                                id: verticalGuide
                                required property int index
                                required property real modelData
                                visible: workspace.showGuides
                                x: modelData
                                y: 0
                                width: Math.max(1, 1 / canvasWorkspace.actualScale)
                                height: artboard.height
                                color: Theme.guide
                                z: 15
                                MouseArea {
                                    anchors.top: parent.top
                                    anchors.bottom: parent.bottom
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    width: Math.max(8, 8 / canvasWorkspace.actualScale)
                                    cursorShape: Qt.SizeHorCursor
                                    drag.target: verticalGuide
                                    drag.axis: Drag.XAxis
                                    drag.minimumX: 0
                                    drag.maximumX: artboard.width
                                    onReleased: workspace.moveGuide("vertical", index, verticalGuide.x)
                                    onDoubleClicked: workspace.removeGuide("vertical", index)
                                }
                            }
                        }

                        MouseArea {
                            id: canvasPointer
                            anchors.fill: parent
                            acceptedButtons: Qt.LeftButton
                            hoverEnabled: true
                            preventStealing: true
                            cursorShape: canvasWorkspace.transformActive
                                         ? (canvasWorkspace.transformMode === "move" ? Qt.ClosedHandCursor : canvasWorkspace.pointerCursor(mouseX, mouseY))
                                         : canvasWorkspace.pointerCursor(mouseX, mouseY)

                            onPressed: mouse => {
                                if (workspace.cropEditing)
                                    return
                                if (workspace.textEditOverlayVisible) {
                                    canvasTextEditOverlay.commit()
                                    mouse.accepted = true
                                    return
                                }
                                var handle = canvasWorkspace.handleAt(mouse.x, mouse.y)
                                if (handle.length > 0) {
                                    canvasWorkspace.beginTransform(handle, mouse.x, mouse.y)
                                    return
                                }
                                var ctrl = (mouse.modifiers & Qt.ControlModifier) !== 0
                                var shift = (mouse.modifiers & Qt.ShiftModifier) !== 0
                                var alt = (mouse.modifiers & Qt.AltModifier) !== 0
                                var selectedIndex = workspace.selectLayerAtWithModifiers(mouse.x, mouse.y, ctrl || alt, shift)
                                if (ctrl)
                                    return
                                if (selectedIndex >= 0 && !workspace.selectedLocked) {
                                    canvasWorkspace.beginTransform("move", mouse.x, mouse.y)
                                    return
                                }
                                canvasWorkspace.marqueeActive = true
                                canvasWorkspace.marqueeAdditive = ctrl
                                canvasWorkspace.marqueeStartX = mouse.x
                                canvasWorkspace.marqueeStartY = mouse.y
                                canvasWorkspace.marqueeCurrentX = mouse.x
                                canvasWorkspace.marqueeCurrentY = mouse.y
                            }
                            onPositionChanged: mouse => {
                                if (!pressed) return
                                if (canvasWorkspace.transformActive)
                                    canvasWorkspace.updateTransform(mouse.x, mouse.y)
                                else if (canvasWorkspace.marqueeActive) {
                                    canvasWorkspace.marqueeCurrentX = mouse.x
                                    canvasWorkspace.marqueeCurrentY = mouse.y
                                }
                            }
                            onReleased: {
                                if (canvasWorkspace.transformActive) {
                                    canvasWorkspace.commitTransform()
                                    return
                                }
                                if (canvasWorkspace.marqueeActive) {
                                    workspace.selectLayersInRect(
                                        canvasWorkspace.marqueeStartX,
                                        canvasWorkspace.marqueeStartY,
                                        canvasWorkspace.marqueeCurrentX,
                                        canvasWorkspace.marqueeCurrentY,
                                        canvasWorkspace.marqueeAdditive
                                    )
                                    canvasWorkspace.marqueeActive = false
                                }
                            }
                            onCanceled: {
                                canvasWorkspace.cancelTransform()
                                canvasWorkspace.marqueeActive = false
                            }
                            onDoubleClicked: mouse => {
                                if (workspace.cropEditing)
                                    return
                                // The second press can start the normal move gesture before
                                // MouseArea emits doubleClicked. Cancel that no-op gesture so
                                // text editing is not swallowed by transformActive.
                                if (canvasWorkspace.transformActive)
                                    canvasWorkspace.cancelTransform()
                                if (workspace.beginTextEditAt(mouse.x, mouse.y)) {
                                    window.revealTextContentEditing()
                                    if (workspace.startTextEditOverlay())
                                        window.focusCanvasTextEditor()
                                }
                            }
                        }

                        Rectangle {
                            visible: canvasWorkspace.marqueeActive
                            x: Math.min(canvasWorkspace.marqueeStartX, canvasWorkspace.marqueeCurrentX)
                            y: Math.min(canvasWorkspace.marqueeStartY, canvasWorkspace.marqueeCurrentY)
                            width: Math.abs(canvasWorkspace.marqueeCurrentX - canvasWorkspace.marqueeStartX)
                            height: Math.abs(canvasWorkspace.marqueeCurrentY - canvasWorkspace.marqueeStartY)
                            color: Theme.selectionFill
                            border.width: Math.max(1, 1 / canvasWorkspace.actualScale)
                            border.color: Theme.accent
                            z: 8
                        }

                        Rectangle {
                            id: selectionBox
                            visible: workspace.selectedLayerIndex >= 0 && !workspace.textEditOverlayVisible
                            x: canvasWorkspace.transformActive ? canvasWorkspace.transientX
                               : (workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup ? workspace.selectionBoundsX : workspace.selectedX)
                            y: canvasWorkspace.transformActive ? canvasWorkspace.transientY
                               : (workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup ? workspace.selectionBoundsY : workspace.selectedY)
                            width: canvasWorkspace.transformActive ? canvasWorkspace.transientWidth
                                   : Math.max(1, workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup ? workspace.selectionBoundsWidth : workspace.selectedWidth)
                            height: canvasWorkspace.transformActive ? canvasWorkspace.transientHeight
                                    : Math.max(1, workspace.selectedLayerCount > 1 || workspace.selectedIsLayerGroup ? workspace.selectionBoundsHeight : workspace.selectedHeight)
                            rotation: workspace.selectedLayerCount === 1 && !workspace.selectedIsLayerGroup && workspace.selectedCanRotate ? workspace.selectedRotation : 0
                            transformOrigin: Item.Center
                            color: canvasWorkspace.transformActive ? Theme.transformFill : "transparent"
                            border.width: Math.max(1, 1.5 / canvasWorkspace.actualScale)
                            border.color: workspace.selectedLocked ? Theme.textMuted : Theme.accent

                            Repeater {
                                model: [
                                    {"edge": "nw", "x": 0, "y": 0},
                                    {"edge": "n", "x": parent.width / 2, "y": 0},
                                    {"edge": "ne", "x": parent.width, "y": 0},
                                    {"edge": "e", "x": parent.width, "y": parent.height / 2},
                                    {"edge": "se", "x": parent.width, "y": parent.height},
                                    {"edge": "s", "x": parent.width / 2, "y": parent.height},
                                    {"edge": "sw", "x": 0, "y": parent.height},
                                    {"edge": "w", "x": 0, "y": parent.height / 2}
                                ]
                                delegate: Rectangle {
                                    required property var modelData
                                    visible: !workspace.selectedLocked
                                             && !workspace.cropEditing
                                             && !workspace.selectedVectorPathEnabled
                                    width: 8 / canvasWorkspace.actualScale
                                    height: width
                                    radius: modelData.edge.length === 1 ? 1 / canvasWorkspace.actualScale : width / 2
                                    x: modelData.x - width / 2
                                    y: modelData.y - height / 2
                                    color: Theme.canvasHandle
                                    border.width: Math.max(1, 1 / canvasWorkspace.actualScale)
                                    border.color: Theme.accentPressed
                                }
                            }

                            Item {
                                id: cropOverlay
                                anchors.fill: parent
                                visible: workspace.cropEditing
                                z: 4

                                readonly property var rect: workspace.selectedCropRect
                                readonly property real cropX: rect[0] * width
                                readonly property real cropY: rect[1] * height
                                readonly property real cropRight: rect[2] * width
                                readonly property real cropBottom: rect[3] * height

                                Rectangle {
                                    x: 0; y: 0; width: parent.width; height: cropOverlay.cropY
                                    color: Theme.canvasScrim
                                }
                                Rectangle {
                                    x: 0; y: cropOverlay.cropBottom; width: parent.width
                                    height: parent.height - cropOverlay.cropBottom
                                    color: Theme.canvasScrim
                                }
                                Rectangle {
                                    x: 0; y: cropOverlay.cropY; width: cropOverlay.cropX
                                    height: cropOverlay.cropBottom - cropOverlay.cropY
                                    color: Theme.canvasScrim
                                }
                                Rectangle {
                                    x: cropOverlay.cropRight; y: cropOverlay.cropY
                                    width: parent.width - cropOverlay.cropRight
                                    height: cropOverlay.cropBottom - cropOverlay.cropY
                                    color: Theme.canvasScrim
                                }
                                Rectangle {
                                    x: cropOverlay.cropX
                                    y: cropOverlay.cropY
                                    width: cropOverlay.cropRight - cropOverlay.cropX
                                    height: cropOverlay.cropBottom - cropOverlay.cropY
                                    color: "transparent"
                                    border.width: Math.max(1, 1.5 / canvasWorkspace.actualScale)
                                    border.color: Theme.amber
                                }

                                Repeater {
                                    model: [
                                        { edge: "nw", x: cropOverlay.cropX, y: cropOverlay.cropY },
                                        { edge: "n", x: (cropOverlay.cropX + cropOverlay.cropRight) / 2, y: cropOverlay.cropY },
                                        { edge: "ne", x: cropOverlay.cropRight, y: cropOverlay.cropY },
                                        { edge: "e", x: cropOverlay.cropRight, y: (cropOverlay.cropY + cropOverlay.cropBottom) / 2 },
                                        { edge: "se", x: cropOverlay.cropRight, y: cropOverlay.cropBottom },
                                        { edge: "s", x: (cropOverlay.cropX + cropOverlay.cropRight) / 2, y: cropOverlay.cropBottom },
                                        { edge: "sw", x: cropOverlay.cropX, y: cropOverlay.cropBottom },
                                        { edge: "w", x: cropOverlay.cropX, y: (cropOverlay.cropY + cropOverlay.cropBottom) / 2 }
                                    ]
                                    delegate: Rectangle {
                                        required property var modelData
                                        width: 10 / canvasWorkspace.actualScale
                                        height: width
                                        x: modelData.x - width / 2
                                        y: modelData.y - height / 2
                                        color: Theme.amber
                                        border.width: Math.max(1, 1 / canvasWorkspace.actualScale)
                                        border.color: Theme.cropAnchorBorder
                                        radius: modelData.edge.length === 1 ? 2 / canvasWorkspace.actualScale : width / 2

                                        MouseArea {
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            preventStealing: true
                                            cursorShape: {
                                                if (parent.modelData.edge === "n" || parent.modelData.edge === "s") return Qt.SizeVerCursor
                                                if (parent.modelData.edge === "e" || parent.modelData.edge === "w") return Qt.SizeHorCursor
                                                if (parent.modelData.edge === "nw" || parent.modelData.edge === "se") return Qt.SizeFDiagCursor
                                                return Qt.SizeBDiagCursor
                                            }
                                            onPositionChanged: mouse => {
                                                if (!pressed) return
                                                var point = mapToItem(selectionBox, mouse.x, mouse.y)
                                                var nx = Math.max(0, Math.min(1, point.x / Math.max(1, selectionBox.width)))
                                                var ny = Math.max(0, Math.min(1, point.y / Math.max(1, selectionBox.height)))
                                                var current = workspace.selectedCropRect
                                                var left = current[0]
                                                var top = current[1]
                                                var right = current[2]
                                                var bottom = current[3]
                                                var edge = parent.modelData.edge
                                                if (edge.indexOf("w") >= 0) left = Math.min(nx, right - 0.02)
                                                if (edge.indexOf("e") >= 0) right = Math.max(nx, left + 0.02)
                                                if (edge.indexOf("n") >= 0) top = Math.min(ny, bottom - 0.02)
                                                if (edge.indexOf("s") >= 0) bottom = Math.max(ny, top + 0.02)
                                                workspace.updateCropRect(left, top, right, bottom)
                                            }
                                        }
                                    }
                                }
                            }

                            Repeater {
                                model: workspace.selectedVectorPathEnabled && !workspace.cropEditing
                                       ? workspace.selectedVectorNodes : []
                                delegate: Item {
                                    required property var modelData
                                    required property int index
                                    x: modelData.x
                                    y: modelData.y
                                    width: 0
                                    height: 0
                                    z: 5

                                    Rectangle {
                                        visible: workspace.selectedVectorNodeIndex === parent.index
                                        x: 0
                                        y: -height / 2
                                        width: Math.hypot(
                                            parent.modelData.in_x - parent.modelData.x,
                                            parent.modelData.in_y - parent.modelData.y
                                        )
                                        height: Math.max(1, 1 / canvasWorkspace.actualScale)
                                        color: Theme.amber
                                        transformOrigin: Item.Left
                                        rotation: Math.atan2(
                                            parent.modelData.in_y - parent.modelData.y,
                                            parent.modelData.in_x - parent.modelData.x
                                        ) * 180 / Math.PI
                                    }
                                    Rectangle {
                                        visible: workspace.selectedVectorNodeIndex === parent.index
                                        x: 0
                                        y: -height / 2
                                        width: Math.hypot(
                                            parent.modelData.out_x - parent.modelData.x,
                                            parent.modelData.out_y - parent.modelData.y
                                        )
                                        height: Math.max(1, 1 / canvasWorkspace.actualScale)
                                        color: Theme.amber
                                        transformOrigin: Item.Left
                                        rotation: Math.atan2(
                                            parent.modelData.out_y - parent.modelData.y,
                                            parent.modelData.out_x - parent.modelData.x
                                        ) * 180 / Math.PI
                                    }

                                    Rectangle {
                                        id: inHandle
                                        visible: workspace.selectedVectorNodeIndex === parent.index
                                        width: 8 / canvasWorkspace.actualScale
                                        height: width
                                        radius: width / 2
                                        x: parent.modelData.in_x - parent.modelData.x - width / 2
                                        y: parent.modelData.in_y - parent.modelData.y - height / 2
                                        color: Theme.bgPanel
                                        border.width: Math.max(1, 1 / canvasWorkspace.actualScale)
                                        border.color: Theme.amber
                                        MouseArea {
                                            anchors.fill: parent
                                            drag.target: parent
                                            preventStealing: true
                                            cursorShape: Qt.CrossCursor
                                            onReleased: workspace.moveSelectedVectorHandle(
                                                inHandle.parent.index,
                                                "in",
                                                inHandle.parent.modelData.x + inHandle.x + inHandle.width / 2,
                                                inHandle.parent.modelData.y + inHandle.y + inHandle.height / 2
                                            )
                                        }
                                    }
                                    Rectangle {
                                        id: outHandle
                                        visible: workspace.selectedVectorNodeIndex === parent.index
                                        width: 8 / canvasWorkspace.actualScale
                                        height: width
                                        radius: width / 2
                                        x: parent.modelData.out_x - parent.modelData.x - width / 2
                                        y: parent.modelData.out_y - parent.modelData.y - height / 2
                                        color: Theme.bgPanel
                                        border.width: Math.max(1, 1 / canvasWorkspace.actualScale)
                                        border.color: Theme.amber
                                        MouseArea {
                                            anchors.fill: parent
                                            drag.target: parent
                                            preventStealing: true
                                            cursorShape: Qt.CrossCursor
                                            onReleased: workspace.moveSelectedVectorHandle(
                                                outHandle.parent.index,
                                                "out",
                                                outHandle.parent.modelData.x + outHandle.x + outHandle.width / 2,
                                                outHandle.parent.modelData.y + outHandle.y + outHandle.height / 2
                                            )
                                        }
                                    }
                                    Rectangle {
                                        id: vectorAnchor
                                        width: 10 / canvasWorkspace.actualScale
                                        height: width
                                        x: -width / 2
                                        y: -height / 2
                                        radius: workspace.selectedVectorNodeIndex === parent.index ? width / 2 : 2 / canvasWorkspace.actualScale
                                        color: workspace.selectedVectorNodeIndex === parent.index ? Theme.accent : Theme.canvasHandle
                                        border.width: Math.max(1, 1 / canvasWorkspace.actualScale)
                                        border.color: Theme.accentPressed
                                        MouseArea {
                                            anchors.fill: parent
                                            drag.target: parent
                                            preventStealing: true
                                            cursorShape: Qt.SizeAllCursor
                                            onPressed: workspace.selectVectorNode(vectorAnchor.parent.index)
                                            onDoubleClicked: workspace.cycleSelectedVectorNodeType()
                                            onReleased: workspace.moveSelectedVectorNode(
                                                vectorAnchor.parent.index,
                                                vectorAnchor.parent.modelData.x + vectorAnchor.x + vectorAnchor.width / 2,
                                                vectorAnchor.parent.modelData.y + vectorAnchor.y + vectorAnchor.height / 2
                                            )
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                visible: canvasWorkspace.transformActive
                                anchors.left: parent.left
                                anchors.bottom: parent.top
                                anchors.bottomMargin: 8 / canvasWorkspace.actualScale
                                width: geometryLabel.implicitWidth + 14 / canvasWorkspace.actualScale
                                height: 22 / canvasWorkspace.actualScale
                                radius: 3 / canvasWorkspace.actualScale
                                color: Theme.canvasLabelSurface
                                border.width: Math.max(1, 1 / canvasWorkspace.actualScale)
                                border.color: Theme.borderStrong

                                Text {
                                    id: geometryLabel
                                    anchors.centerIn: parent
                                    text: Math.round(canvasWorkspace.transientWidth) + " x " + Math.round(canvasWorkspace.transientHeight)
                                    color: Theme.textPrimary
                                    font.family: Theme.bodyFont
                                    font.pixelSize: 10 / canvasWorkspace.actualScale
                                }
                            }
                        }

                            Rectangle {
                                id: canvasTextEditOverlay
                                objectName: "canvasTextEditOverlay"
                                visible: workspace.textEditOverlayVisible && workspace.selectedIsTextLayer
                                x: workspace.selectedX
                                y: workspace.selectedY
                                width: Math.max(1, workspace.selectedWidth)
                                height: Math.max(1, workspace.selectedHeight)
                                rotation: workspace.selectedCanRotate ? workspace.selectedRotation : 0
                                transformOrigin: Item.Center
                                z: 60
                                color: "transparent"
                                border.width: Math.max(1, 1.5 / canvasWorkspace.actualScale)
                                border.color: workspace.selectedLocked ? Theme.textMuted : Theme.accent
                                clip: false
                                property int editingIndex: -1
                                readonly property real overlayScale: Math.max(0.05, canvasWorkspace.actualScale)
                                readonly property real handleSize: Math.max(7 / overlayScale, 7)

                                Rectangle {
                                    anchors.fill: parent
                                    anchors.margins: -Math.max(1, 1 / canvasTextEditOverlay.overlayScale)
                                    color: "transparent"
                                    border.width: Math.max(1, 1 / canvasTextEditOverlay.overlayScale)
                                    border.color: "#eafef8"
                                    opacity: workspace.selectedLocked ? 0.36 : 0.86
                                    z: -1
                                }

                                Repeater {
                                    model: [
                                        {"x": 0, "y": 0},
                                        {"x": parent.width / 2, "y": 0},
                                        {"x": parent.width, "y": 0},
                                        {"x": parent.width, "y": parent.height / 2},
                                        {"x": parent.width, "y": parent.height},
                                        {"x": parent.width / 2, "y": parent.height},
                                        {"x": 0, "y": parent.height},
                                        {"x": 0, "y": parent.height / 2}
                                    ]
                                    delegate: Rectangle {
                                        required property var modelData
                                        visible: !workspace.selectedLocked
                                        width: canvasTextEditOverlay.handleSize
                                        height: width
                                        radius: width / 2
                                        x: modelData.x - width / 2
                                        y: modelData.y - height / 2
                                        color: "#eafff8"
                                        border.width: Math.max(1, 1 / canvasTextEditOverlay.overlayScale)
                                        border.color: Theme.accent
                                        z: 62
                                    }
                                }

                                function commit() {
                                    if (canvasTextEditInput.editing) {
                                        canvasTextEditOverlay.commitValue()
                                        canvasTextEditInput.focus = false
                                    }
                                }

                                function commitValue() {
                                    if (canvasTextEditOverlay.editingIndex < 0)
                                        return
                                    if (canvasTextEditInput.getFormattedText === undefined) {
                                        canvasTextEditOverlay.editingIndex = -1
                                        workspace.commitTextEditOverlay(canvasTextEditInput.text)
                                        return
                                    }
                                    var formattedText = canvasTextEditInput.getFormattedText(
                                        0,
                                        canvasTextEditInput.length
                                    )
                                    canvasTextEditOverlay.editingIndex = -1
                                    workspace.commitTextEditOverlayRichText(formattedText)
                                }

                                function cancel() {
                                    if (canvasTextEditOverlay.editingIndex < 0)
                                        return
                                    canvasTextEditOverlay.editingIndex = -1
                                    workspace.cancelTextEditOverlay()
                                    canvasTextEditInput.focus = false
                                }

                                function formattedText() {
                                    return canvasTextEditInput.getFormattedText(
                                        0,
                                        canvasTextEditInput.length
                                    )
                                }

                                function replaceFormattedText(html, start, end) {
                                    canvasTextEditInput.text = html
                                    canvasTextEditInput.select(start, end)
                                    workspace.stageTextEditOverlayDraft(html)
                                    canvasTextSelectionToolbar.refreshStyleInfo()
                                }

                                TextEdit {
                                    id: canvasTextEditInput
                                    objectName: "canvasTextEditInput"
                                    anchors.fill: parent
                                    anchors.margins: Math.max(0, workspace.selectedTextBoxPadding)
                                    textFormat: TextEdit.RichText
                                    color: workspace.selectedTextColor
                                    selectionColor: Theme.accentPressed
                                    selectedTextColor: Theme.textPrimary
                                    font.family: workspace.selectedTextResolvedFontFamily
                                    font.pixelSize: workspace.selectedTextFontSize
                                    font.weight: workspace.selectedTextFontWeight
                                    font.italic: workspace.selectedTextItalic
                                    font.letterSpacing: workspace.selectedTextLetterSpacing
                                    horizontalAlignment: workspace.selectedTextAlignmentId === "center"
                                                         ? TextEdit.AlignHCenter
                                                         : (workspace.selectedTextAlignmentId === "right"
                                                            ? TextEdit.AlignRight
                                                             : TextEdit.AlignLeft)
                                    verticalAlignment: workspace.selectedTextAutoFitTextBox
                                                       ? TextEdit.AlignTop
                                                       : TextEdit.AlignVCenter
                                    wrapMode: TextEdit.Wrap
                                    selectByMouse: true
                                    persistentSelection: true
                                    readOnly: workspace.selectedLocked || !workspace.textEditOverlayVisible
                                    z: 61
                                    readonly property bool editing: canvasTextEditOverlay.editingIndex >= 0
                                                                    && workspace.textEditOverlayVisible

                                    onActiveFocusChanged: {
                                        if (activeFocus && workspace.textEditOverlayVisible
                                                && canvasTextEditOverlay.editingIndex < 0) {
                                            canvasTextEditOverlay.editingIndex = workspace.selectedLayerIndex
                                            canvasTextEditInput.text = workspace.selectedTextEditorHtml
                                        }
                                    }

                                    onTextChanged: {
                                        if (editing) {
                                            workspace.stageTextEditOverlayDraft(
                                                canvasTextEditOverlay.formattedText()
                                            )
                                            canvasTextSelectionToolbar.refreshStyleInfo()
                                        }
                                    }
                                    onSelectionStartChanged: canvasTextSelectionToolbar.refreshStyleInfo()
                                    onSelectionEndChanged: canvasTextSelectionToolbar.refreshStyleInfo()

                                    Keys.onPressed: event => {
                                        if (event.key === Qt.Key_Escape) {
                                            canvasTextEditOverlay.cancel()
                                            event.accepted = true
                                        } else if ((event.modifiers & Qt.ControlModifier)
                                                   && (event.key === Qt.Key_Return || event.key === Qt.Key_Enter)) {
                                            canvasTextEditOverlay.commit()
                                            event.accepted = true
                                        }
                                    }

                                    Connections {
                                        target: workspace
                                        function onTextEditingChanged() {
                                            if (!workspace.textEditOverlayVisible) {
                                                canvasTextEditOverlay.editingIndex = -1
                                                canvasTextEditInput.focus = false
                                            }
                                        }
                                    }
                                }
                            }

                            Rectangle {
                                id: canvasTextSelectionToolbar
                                objectName: "canvasTextSelectionToolbar"
                                visible: workspace.textEditOverlayVisible
                                         && !workspace.selectedTextBindingEnabled
                                         && canvasTextEditInput.selectionStart !== canvasTextEditInput.selectionEnd
                                width: 286
                                height: 36
                                x: Math.min(
                                    Math.max(workspace.selectedX, 8 / canvasWorkspace.actualScale),
                                    Math.max(
                                        8 / canvasWorkspace.actualScale,
                                        artboard.width - width / canvasWorkspace.actualScale
                                            - 8 / canvasWorkspace.actualScale
                                    )
                                )
                                y: workspace.selectedY >= (height + 10) / canvasWorkspace.actualScale
                                   ? workspace.selectedY - (height + 8) / canvasWorkspace.actualScale
                                   : Math.min(
                                       artboard.height - height / canvasWorkspace.actualScale
                                           - 8 / canvasWorkspace.actualScale,
                                       workspace.selectedY + workspace.selectedHeight
                                           + 8 / canvasWorkspace.actualScale
                                   )
                                scale: 1 / canvasWorkspace.actualScale
                                transformOrigin: Item.TopLeft
                                z: 80
                                radius: Theme.radiusSmall
                                color: Theme.floatingPanelSurface
                                border.width: 1
                                border.color: Theme.floatingPanelBorder
                                property var styleInfo: ({
                                    "characterCount": 0,
                                    "fontSize": workspace.selectedTextFontSize,
                                    "mixedFontSize": false,
                                    "color": workspace.selectedTextColor,
                                    "mixedColor": false
                                })

                                function refreshStyleInfo() {
                                    if (!workspace.textEditOverlayVisible
                                            || canvasTextEditInput.selectionStart === canvasTextEditInput.selectionEnd)
                                        return
                                    styleInfo = workspace.inspectTextEditorSelection(
                                        canvasTextEditOverlay.formattedText(),
                                        canvasTextEditInput.selectionStart,
                                        canvasTextEditInput.selectionEnd
                                    )
                                }

                                onVisibleChanged: {
                                    if (visible)
                                        refreshStyleInfo()
                                }

                                Row {
                                    anchors.fill: parent
                                    anchors.leftMargin: 6
                                    anchors.rightMargin: 4
                                    spacing: 4

                                    TinyLabel {
                                        width: 44
                                        height: parent.height
                                        text: canvasTextSelectionToolbar.styleInfo.characterCount + " 字"
                                        color: Theme.textSecondary
                                        horizontalAlignment: Text.AlignHCenter
                                    }

                                    Rectangle {
                                        id: canvasTextColorSwatch
                                        width: 28
                                        height: 28
                                        anchors.verticalCenter: parent.verticalCenter
                                        radius: Theme.radiusSmall
                                        color: canvasTextSelectionToolbar.styleInfo.color
                                        border.width: activeFocus ? 2 : 1
                                        border.color: activeFocus ? Theme.focusRing : Theme.borderStrong
                                        activeFocusOnTab: visible

                                        Text {
                                            anchors.centerIn: parent
                                            visible: canvasTextSelectionToolbar.styleInfo.mixedColor
                                            text: "混"
                                            color: Theme.textPrimary
                                            font.family: Theme.bodyFont
                                            font.pixelSize: 9
                                            font.weight: Font.DemiBold
                                        }

                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onPressed: canvasTextColorSwatch.forceActiveFocus(Qt.MouseFocusReason)
                                            onClicked: effectColorDialog.openForTextEditor(
                                                canvasTextSelectionToolbar.styleInfo.mixedColor
                                                    ? workspace.selectedTextColor
                                                    : canvasTextSelectionToolbar.styleInfo.color,
                                                canvasTextEditInput.selectionStart,
                                                canvasTextEditInput.selectionEnd,
                                                canvasTextEditOverlay.formattedText()
                                            )
                                        }
                                        Keys.onSpacePressed: effectColorDialog.openForTextEditor(
                                            canvasTextSelectionToolbar.styleInfo.color,
                                            canvasTextEditInput.selectionStart,
                                            canvasTextEditInput.selectionEnd,
                                            canvasTextEditOverlay.formattedText()
                                        )
                                        Accessible.name: "修改选区文字颜色"
                                        Accessible.role: Accessible.Button
                                    }

                                    ValueBox {
                                        width: 78
                                        height: 28
                                        anchors.verticalCenter: parent.verticalCenter
                                        value: canvasTextSelectionToolbar.styleInfo.mixedFontSize
                                               ? "混合"
                                               : canvasTextSelectionToolbar.styleInfo.fontSize.toString()
                                        bindValue: true
                                        suffix: "px"
                                        accessibleName: "选区文字字号"
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (isNaN(parsed) || parsed < 1)
                                                return
                                            var start = canvasTextEditInput.selectionStart
                                            var end = canvasTextEditInput.selectionEnd
                                            var updatedHtml = workspace.applyTextEditorFontSize(
                                                canvasTextEditOverlay.formattedText(),
                                                start,
                                                end,
                                                parsed
                                            )
                                            canvasTextEditOverlay.replaceFormattedText(updatedHtml, start, end)
                                            Qt.callLater(function() {
                                                window.focusCanvasTextEditor()
                                                canvasTextEditInput.select(start, end)
                                            })
                                        }
                                    }

                                    IconButton {
                                        iconName: AppIcons.refresh
                                        tooltip: "清除选区局部样式"
                                        buttonSize: 28
                                        anchors.verticalCenter: parent.verticalCenter
                                        onClicked: {
                                            var start = canvasTextEditInput.selectionStart
                                            var end = canvasTextEditInput.selectionEnd
                                            var updatedHtml = workspace.clearTextEditorStyle(
                                                canvasTextEditOverlay.formattedText(),
                                                start,
                                                end
                                            )
                                            canvasTextEditOverlay.replaceFormattedText(updatedHtml, start, end)
                                            Qt.callLater(function() {
                                                window.focusCanvasTextEditor()
                                                canvasTextEditInput.select(start, end)
                                            })
                                        }
                                    }

                                    Rectangle {
                                        width: 1
                                        height: 20
                                        anchors.verticalCenter: parent.verticalCenter
                                        color: Theme.borderStrong
                                    }

                                    IconButton {
                                        iconName: AppIcons.close
                                        tooltip: "取消文字编辑"
                                        buttonSize: 28
                                        destructive: true
                                        anchors.verticalCenter: parent.verticalCenter
                                        onClicked: canvasTextEditOverlay.cancel()
                                    }

                                    IconButton {
                                        iconName: AppIcons.check
                                        tooltip: "完成文字编辑"
                                        buttonSize: 28
                                        primary: true
                                        anchors.verticalCenter: parent.verticalCenter
                                        onClicked: canvasTextEditOverlay.commit()
                                    }
                                }
                            }
                    }
                }

                Rectangle {
                    id: viewportTopRuler
                    visible: window.hasOpenDocument && workspace.showRulers
                    x: canvasWorkspace.rulerSize
                    y: 0
                    width: Math.max(0, canvasWorkspace.width - x)
                    height: canvasWorkspace.rulerSize
                    color: Theme.bgBar
                    z: 40
                    clip: true

                    property real rulerOriginX: artboardFrame.x
                    property real rulerScale: canvasWorkspace.actualScale

                    onRulerOriginXChanged: viewportTopRulerCanvas.requestPaint()
                    onRulerScaleChanged: viewportTopRulerCanvas.requestPaint()
                    onWidthChanged: viewportTopRulerCanvas.requestPaint()

                    Canvas {
                        id: viewportTopRulerCanvas
                        anchors.fill: parent
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            var scale = Math.max(0.001, viewportTopRuler.rulerScale)
                            var major = canvasWorkspace.rulerMajorStep()
                            var minor = major / 5
                            var minimumValue = (viewportTopRuler.x - viewportTopRuler.rulerOriginX) / scale
                            var maximumValue = (viewportTopRuler.x + width - viewportTopRuler.rulerOriginX) / scale
                            var firstValue = Math.floor(minimumValue / minor) * minor
                            ctx.strokeStyle = Theme.textMuted
                            ctx.fillStyle = Theme.textSecondary
                            ctx.lineWidth = 1
                            ctx.font = "9px sans-serif"
                            ctx.textBaseline = "top"
                            for (var value = firstValue; value <= maximumValue + minor / 2; value += minor) {
                                var ratio = value / major
                                var isMajor = Math.abs(ratio - Math.round(ratio)) < 0.001
                                var px = viewportTopRuler.rulerOriginX - viewportTopRuler.x + value * scale
                                ctx.beginPath()
                                ctx.moveTo(Math.round(px) + 0.5, height)
                                ctx.lineTo(Math.round(px) + 0.5, height - (isMajor ? 9 : 5))
                                ctx.stroke()
                                if (isMajor)
                                    ctx.fillText(canvasWorkspace.rulerLabel(value, major), px + 3, 2)
                            }
                        }
                    }

                    Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 1; color: Theme.borderStrong }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.CrossCursor
                        onClicked: mouse => {
                            var canvasX = (viewportTopRuler.x + mouse.x - artboardFrame.x) / canvasWorkspace.actualScale
                            if (canvasX >= 0 && canvasX <= workspace.canvasWidth)
                                workspace.addGuide("vertical", canvasX)
                        }
                    }
                }

                Rectangle {
                    id: viewportLeftRuler
                    visible: window.hasOpenDocument && workspace.showRulers
                    x: 0
                    y: canvasWorkspace.rulerSize
                    width: canvasWorkspace.rulerSize
                    height: Math.max(0, canvasWorkspace.height - y)
                    color: Theme.bgBar
                    z: 40
                    clip: true

                    property real rulerOriginY: artboardFrame.y
                    property real rulerScale: canvasWorkspace.actualScale

                    onRulerOriginYChanged: viewportLeftRulerCanvas.requestPaint()
                    onRulerScaleChanged: viewportLeftRulerCanvas.requestPaint()
                    onHeightChanged: viewportLeftRulerCanvas.requestPaint()

                    Canvas {
                        id: viewportLeftRulerCanvas
                        anchors.fill: parent
                        onPaint: {
                            var ctx = getContext("2d")
                            ctx.clearRect(0, 0, width, height)
                            var scale = Math.max(0.001, viewportLeftRuler.rulerScale)
                            var major = canvasWorkspace.rulerMajorStep()
                            var minor = major / 5
                            var minimumValue = (viewportLeftRuler.y - viewportLeftRuler.rulerOriginY) / scale
                            var maximumValue = (viewportLeftRuler.y + height - viewportLeftRuler.rulerOriginY) / scale
                            var firstValue = Math.floor(minimumValue / minor) * minor
                            ctx.strokeStyle = Theme.textMuted
                            ctx.fillStyle = Theme.textSecondary
                            ctx.lineWidth = 1
                            ctx.font = "9px sans-serif"
                            ctx.textBaseline = "top"
                            for (var value = firstValue; value <= maximumValue + minor / 2; value += minor) {
                                var ratio = value / major
                                var isMajor = Math.abs(ratio - Math.round(ratio)) < 0.001
                                var py = viewportLeftRuler.rulerOriginY - viewportLeftRuler.y + value * scale
                                ctx.beginPath()
                                ctx.moveTo(width, Math.round(py) + 0.5)
                                ctx.lineTo(width - (isMajor ? 9 : 5), Math.round(py) + 0.5)
                                ctx.stroke()
                                if (isMajor) {
                                    ctx.save()
                                    ctx.translate(2, py - 3)
                                    ctx.rotate(-Math.PI / 2)
                                    ctx.fillText(canvasWorkspace.rulerLabel(value, major), 0, 0)
                                    ctx.restore()
                                }
                            }
                        }
                    }

                    Rectangle { anchors.top: parent.top; anchors.right: parent.right; anchors.bottom: parent.bottom; width: 1; color: Theme.borderStrong }
                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.CrossCursor
                        onClicked: mouse => {
                            var canvasY = (viewportLeftRuler.y + mouse.y - artboardFrame.y) / canvasWorkspace.actualScale
                            if (canvasY >= 0 && canvasY <= workspace.canvasHeight)
                                workspace.addGuide("horizontal", canvasY)
                        }
                    }
                }

                Rectangle {
                    id: rulerOriginCorner
                    visible: window.hasOpenDocument && workspace.showRulers
                    x: 0
                    y: 0
                    width: canvasWorkspace.rulerSize
                    height: canvasWorkspace.rulerSize
                    color: Theme.bgBar
                    border.width: 1
                    border.color: Theme.borderStrong
                    z: 42

                    Rectangle { anchors.centerIn: parent; width: 10; height: 1; color: Theme.textMuted }
                    Rectangle { anchors.centerIn: parent; width: 1; height: 10; color: Theme.textMuted }
                    ToolTip.visible: rulerCornerMouse.containsMouse
                    ToolTip.text: "标尺原点"
                    ToolTip.delay: 420
                    MouseArea { id: rulerCornerMouse; anchors.fill: parent; hoverEnabled: true }
                }

                BusyIndicator {
                    anchors.centerIn: parent
                    running: workspace.busy
                    visible: window.hasOpenDocument && running
                    palette.accent: Theme.accent
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 8
                    // 使用带通知信号的属性，避免 rowCount() 的非响应式调用让提示停留在有图层文档上。
                    visible: window.hasOpenDocument && workspace.layerCount === 0 && !workspace.busy
                    AppIcon { anchors.horizontalCenter: parent.horizontalCenter; iconName: AppIcons.image; iconSize: 24; iconColor: Theme.textMuted }
                    BodyLabel { text: "空白画布"; color: Theme.textMuted }
                }

                Column {
                    objectName: "noDocumentState"
                    anchors.centerIn: parent
                    spacing: 18
                    visible: !window.hasOpenDocument

                    Column {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 7
                        AppIcon {
                            anchors.horizontalCenter: parent.horizontalCenter
                            iconName: AppIcons.fileImage
                            iconSize: 30
                            iconColor: Theme.textMuted
                        }
                        Text {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "没有打开的文档"
                            color: Theme.textPrimary
                            font.family: Theme.displayFont
                            font.pixelSize: 18
                            font.weight: Font.DemiBold
                        }
                        BodyLabel {
                            anchors.horizontalCenter: parent.horizontalCenter
                            text: "新建画布或打开现有项目"
                            color: Theme.textMuted
                        }
                    }

                    Row {
                        anchors.horizontalCenter: parent.horizontalCenter
                        spacing: 8
                        ExportButton {
                            width: 116
                            label: "新建画布"
                            iconName: AppIcons.add
                            primary: true
                            onClicked: newCanvasDialog.open()
                        }
                        ExportButton {
                            width: 116
                            label: "打开项目"
                            iconName: AppIcons.folderOpen
                            onClicked: openDialog.open()
                        }
                    }
                }

                Rectangle {
                    anchors.horizontalCenter: parent.horizontalCenter
                    y: 14
                    width: canvasBadgeRow.width + 20
                    height: 25
                    radius: 12
                    color: Theme.statusPillSurface
                    border.width: 1
                    border.color: Theme.border
                    visible: window.hasOpenDocument
                    Row {
                        id: canvasBadgeRow
                        anchors.centerIn: parent
                        spacing: 7
                        Rectangle { width: 5; height: 5; radius: 3; color: Theme.accent; anchors.verticalCenter: parent.verticalCenter }
                        TinyLabel { text: workspace.canvasWidth + " × " + workspace.canvasHeight + " px  ·  RGBA"; color: Theme.textSecondary; height: 18 }
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
                    color: Theme.floatingPanelSurface
                    border.width: 1
                    border.color: Theme.floatingPanelBorder
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

                StatusBanner {
                    id: updateBanner
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.topMargin: 12
                    anchors.rightMargin: 12
                    width: 340
                    visible: updateManager.updateAvailable && !updateManager.downloading && !updateDialog.opened && !updateBannerDismissed
                    tone: "success"
                    z: 20

                    RowLayout {
                        anchors.fill: parent
                        anchors.margins: 10
                        spacing: 9
                        AppIcon { iconName: AppIcons.info; iconSize: 15; iconColor: Theme.accent }
                        Column {
                            Layout.fillWidth: false
                            spacing: 2
                            BodyLabel { text: updateBannerText.length > 0 ? updateBannerText : "发现新版本"; color: Theme.textPrimary; elide: Text.ElideRight }
                            TinyLabel { text: "点击查看更新说明"; color: Theme.textMuted }
                        }
                        IconButton { iconName: AppIcons.close; tooltip: "忽略本次"; buttonSize: 22; onClicked: updateBannerDismissed = true }
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            updateBannerDismissed = false
                            updateDialog.open()
                        }
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
                            TinyLabel { text: selectedLayer >= 0 ? workspace.selectedLayerType + "图层  ·  #" + (selectedLayer + 1) : "图层"; height: 15 }
                        }

                    }

                    Divider { Layout.fillWidth: true }

                    Row {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 26

                        Repeater {
                            model: ["基本参数", "更多参数"]
                            delegate: Rectangle {
                                required property int index
                                required property string modelData
                                width: inspector.width / 2
                                height: 26
                                color: "transparent"
                                Text {
                                    anchors.centerIn: parent
                                    text: modelData
                                    color: inspectorTab === index ? Theme.textPrimary : Theme.textMuted
                                    font.family: Theme.bodyFont
                                    font.pixelSize: 10
                                    font.weight: inspectorTab === index ? Font.DemiBold : Font.Normal
                                    opacity: inspectorTab === index ? 1.0 : 0.7
                                }
                                Rectangle {
                                    anchors.left: parent.left; anchors.leftMargin: 12
                                    anchors.right: parent.right; anchors.rightMargin: 12
                                    anchors.bottom: parent.bottom
                                    height: 2
                                    visible: inspectorTab === index
                                    color: inspectorTab === index ? Theme.accent : "transparent"
                                }
                                MouseArea { anchors.fill: parent; enabled: parent.enabled; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: window.selectInspectorTab(index) }
                            }
                        }
                    }

                    ScrollView {
                        id: inspectorScroll
                        objectName: "inspectorScroll"
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: selectedLayer >= 0
                        clip: true
                        contentWidth: availableWidth
                        contentHeight: propertyInspectorColumn.implicitHeight
                                       + effectInspectorColumn.implicitHeight
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff
                        ScrollBar.horizontal.interactive: false

                        GridLayout {
                            id: propertyInspectorColumn
                            width: inspectorScroll.contentWidth
                            columns: 1
                            columnSpacing: 0
                            rowSpacing: 0

                            PropertySection {
                                id: imageSourceSection
                                Layout.fillWidth: true
                                Layout.row: 10
                                title: "图像源"
                                summary: workspace.selectedImageSource
                                         ? (workspace.selectedImageSourceIsFolder ? workspace.selectedImageSourceCount + " 张素材" : "单张图片")
                                         : "未设置"
                                visible: inspectorTab === 0 && workspace.selectedHasImageSource

                                InspectorRow {
                                    label: "路径"
                                    ValueBox {
                                        Layout.fillWidth: false
                                        value: workspace.selectedImageSource
                                        bindValue: true
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => workspace.setSelectedImageSource(value)
                                    }
                                }
                                InspectorRow {
                                    label: "当前"
                                    BodyLabel {
                                        text: workspace.selectedImageCurrentFile || "无预览"
                                        color: Theme.textSecondary
                                        elide: Text.ElideMiddle
                                        Layout.fillWidth: true
                                    }
                                    IconButton {
                                        iconName: AppIcons.refresh
                                        tooltip: "换一张素材"
                                        buttonSize: 30
                                        enabled: workspace.selectedImageSourceIsFolder && workspace.selectedImageSourceCount > 1 && !workspace.selectedLocked
                                        onClicked: workspace.showNextSelectedImage()
                                    }
                                }
                                InspectorRow {
                                    label: "选择"
                                    ExportButton {
                                        Layout.fillWidth: true
                                        label: "图片"
                                        iconName: AppIcons.image
                                        enabled: !workspace.selectedLocked
                                        onClicked: replaceImageDialog.open()
                                    }
                                    ExportButton {
                                        Layout.fillWidth: true
                                        label: "文件夹"
                                        iconName: AppIcons.folderOpen
                                        enabled: !workspace.selectedLocked
                                        onClicked: replaceImageFolderDialog.open()
                                    }
                                }
                            }

                            PropertySection {
                                Layout.fillWidth: true
                                Layout.row: 21
                                title: "矢量路径"
                                summary: workspace.selectedVectorPathEnabled
                                         ? workspace.selectedVectorNodes.length + " 个节点" : "矩形边界"
                                visible: inspectorTab === 0 && workspace.selectedSupportsVectorPath

                                InspectorRow {
                                    label: "路径"
                                    BodyLabel {
                                        text: workspace.selectedVectorPathEnabled ? "贝塞尔路径" : "尚未转换"
                                        color: workspace.selectedVectorPathEnabled ? Theme.accent : Theme.textMuted
                                        Layout.fillWidth: true
                                    }
                                    CompactActionButton {
                                        Layout.preferredWidth: 86
                                        label: workspace.selectedVectorPathEnabled ? "重建矩形" : "转为路径"
                                        active: workspace.selectedVectorPathEnabled
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.convertSelectedToVectorPath()
                                    }
                                }

                                InspectorRow {
                                    label: "闭合"
                                    visible: workspace.selectedVectorPathEnabled
                                    TrailingToggle {
                                        accessibleName: "闭合路径"
                                        checked: workspace.selectedVectorPathClosed
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onToggled: checkedValue => workspace.setSelectedVectorPathClosed(checkedValue)
                                    }
                                }

                                InspectorRow {
                                    label: "控制柄"
                                    visible: workspace.selectedVectorPathEnabled
                                    SelectBox {
                                        Layout.fillWidth: false
                                        model: window.vectorHandleLinkOptions
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        currentIndex: {
                                            for (var index = 0; index < window.vectorHandleLinkOptions.length; index++) {
                                                if (window.vectorHandleLinkOptions[index].value === workspace.selectedVectorHandleLinkMode) return index
                                            }
                                            return 0
                                        }
                                        onActivated: workspace.setSelectedVectorHandleLinkMode(currentValue)
                                    }
                                }

                                InspectorRow {
                                    label: "节点"
                                    visible: workspace.selectedVectorPathEnabled
                                    BodyLabel {
                                        text: workspace.selectedVectorNodeIndex >= 0
                                              ? "#" + (workspace.selectedVectorNodeIndex + 1) + " · " + workspace.selectedVectorNodeType
                                              : "在画布中选择"
                                        color: workspace.selectedVectorNodeIndex >= 0 ? Theme.textSecondary : Theme.textMuted
                                        Layout.fillWidth: true
                                        elide: Text.ElideRight
                                    }
                                    IconButton {
                                        iconName: AppIcons.add
                                        tooltip: "在选中节点后插入"
                                        buttonSize: 30
                                        enabled: workspace.selectedVectorNodeIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.insertVectorNodeAfter(workspace.selectedVectorNodeIndex)
                                    }
                                    IconButton {
                                        iconName: AppIcons.refresh
                                        tooltip: "切换角点、平滑点和对称点"
                                        buttonSize: 30
                                        enabled: workspace.selectedVectorNodeIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.cycleSelectedVectorNodeType()
                                    }
                                    IconButton {
                                        iconName: AppIcons.trash
                                        tooltip: "删除选中节点"
                                        buttonSize: 30
                                        enabled: workspace.selectedVectorNodeIndex >= 0
                                                 && workspace.selectedVectorNodes.length > (workspace.selectedVectorPathClosed ? 3 : 2)
                                                 && !workspace.selectedLocked
                                                 && !workspace.operationsBlocked
                                        onClicked: workspace.deleteSelectedVectorNode()
                                    }
                                }
                            }

                            PropertySection {
                                id: advancedSettingsSection
                                Layout.fillWidth: true
                                Layout.row: 20
                                title: "高级设置"
                                summary: workspace.selectedFitModeName
                                visible: inspectorTab === 0 && workspace.selectedSupportsImageFit

                                InspectorRow {
                                    label: "适配"
                                    SelectBox {
                                        Layout.fillWidth: false
                                        model: window.imageFitOptions
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        currentIndex: {
                                            for (var index = 0; index < window.imageFitOptions.length; index++) {
                                                if (window.imageFitOptions[index].value === workspace.selectedFitModeId) return index
                                            }
                                            return 0
                                        }
                                        onActivated: workspace.setSelectedFitMode(currentValue)
                                    }
                                }

                                InspectorRow {
                                    label: "透明留白"
                                    TrailingToggle {
                                        accessibleName: "去除图片透明留白"
                                        checked: workspace.selectedTrimTransparentBoundsEnabled
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onToggled: checkedValue => workspace.setSelectedTrimTransparentBoundsEnabled(checkedValue)
                                    }
                                }

                                InspectorRow {
                                    label: "裁剪"
                                    visible: workspace.selectedFitModeId === "crop"
                                    RowLayout {
                                        Layout.fillWidth: true
                                        spacing: 4

                                        Repeater {
                                            model: window.cropDirectionOptions
                                            delegate: IconButton {
                                                required property var modelData
                                                iconName: modelData.iconName
                                                tooltip: modelData.label
                                                buttonSize: 30
                                                active: workspace.selectedCropDirectionId === modelData.value
                                                enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                                onClicked: workspace.setSelectedCropDirection(modelData.value)
                                            }
                                        }
                                    }
                                }

                                InspectorRow {
                                    label: "自由裁剪"
                                    visible: workspace.selectedSupportsFreeCrop
                                    BodyLabel {
                                        text: workspace.cropEditing ? "调整画布中的裁剪框" : "源图范围"
                                        color: workspace.cropEditing ? Theme.amber : Theme.textSecondary
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    IconButton {
                                        iconName: AppIcons.crop
                                        tooltip: workspace.cropEditing ? "确认自由裁剪" : "开始自由裁剪"
                                        buttonSize: 30
                                        active: workspace.cropEditing
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.cropEditing
                                                   ? workspace.confirmCropEdit()
                                                   : workspace.startCropEdit()
                                    }
                                    IconButton {
                                        iconName: workspace.cropEditing ? AppIcons.close : AppIcons.refresh
                                        tooltip: workspace.cropEditing ? "取消自由裁剪" : "重置自由裁剪"
                                        buttonSize: 30
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.cropEditing
                                                   ? workspace.cancelCropEdit()
                                                   : workspace.resetSelectedCrop()
                                    }
                                }

                            }

                            PropertySection {
                                id: shapeSection
                                Layout.fillWidth: true
                                Layout.row: 30
                                title: "形状"
                                summary: workspace.selectedShapeTypeName
                                visible: inspectorTab === 0 && workspace.selectedIsShapedLayer

                                GridLayout {
                                    width: parent.width
                                    columns: 3
                                    rowSpacing: 5
                                    columnSpacing: 5

                                    Repeater {
                                        model: [
                                            { label: "矩形", value: "rectangle" },
                                            { label: "圆形", value: "circle" },
                                            { label: "梯形", value: "right_trapezoid" },
                                            { label: "五边形", value: "pentagon" },
                                            { label: "六边形", value: "hexagon" }
                                        ]
                                        delegate: Rectangle {
                                            required property var modelData
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 34
                                            radius: Theme.radiusSmall
                                            color: workspace.selectedShapeTypeId === modelData.value ? Theme.accentSoft : Theme.bgControl
                                            border.width: 1
                                            border.color: workspace.selectedShapeTypeId === modelData.value ? Theme.accentPressed : Theme.borderStrong
                                            Text {
                                                anchors.centerIn: parent
                                                text: modelData.label
                                                color: workspace.selectedShapeTypeId === modelData.value ? Theme.accent : Theme.textSecondary
                                                font.family: Theme.bodyFont
                                                font.pixelSize: 10
                                                font.weight: Font.DemiBold
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                                hoverEnabled: true
                                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                onClicked: workspace.setSelectedShapeType(modelData.value)
                                            }
                                        }
                                    }
                                }

                                InspectorRow {
                                    label: "上下底"
                                    visible: workspace.selectedShapeTypeId === "right_trapezoid"
                                    ValueBox {
                                        value: workspace.selectedTrapezoidTopWidth.toString()
                                        bindValue: true
                                        suffix: "上"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTrapezoidTopWidth(parsed)
                                        }
                                    }
                                    ValueBox {
                                        value: workspace.selectedTrapezoidBottomWidth.toString()
                                        bindValue: true
                                        suffix: "下"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTrapezoidBottomWidth(parsed)
                                        }
                                    }
                                }

                                InspectorRow {
                                    label: "斜边"
                                    visible: workspace.selectedShapeTypeId === "right_trapezoid"
                                    Repeater {
                                        model: [
                                            { label: "左侧", value: "left" },
                                            { label: "右侧", value: "right" }
                                        ]
                                        delegate: Rectangle {
                                            required property var modelData
                                            Layout.fillWidth: true
                                            Layout.preferredHeight: 30
                                            radius: Theme.radiusSmall
                                            color: workspace.selectedTrapezoidSlopeSide === modelData.value ? Theme.accentSoft : Theme.bgControl
                                            border.width: 1
                                            border.color: workspace.selectedTrapezoidSlopeSide === modelData.value ? Theme.accentPressed : Theme.borderStrong
                                            Text {
                                                anchors.centerIn: parent
                                                text: modelData.label
                                                color: workspace.selectedTrapezoidSlopeSide === modelData.value ? Theme.accent : Theme.textSecondary
                                                font.family: Theme.bodyFont
                                                font.pixelSize: 10
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                onClicked: workspace.setSelectedTrapezoidSlopeSide(modelData.value)
                                            }
                                        }
                                    }
                                }

                                InspectorRow {
                                    label: "旋转"
                                    visible: workspace.selectedShapeTypeId === "pentagon" || workspace.selectedShapeTypeId === "hexagon"
                                    ValueBox {
                                        value: (Math.round(workspace.selectedPolygonRotation * 10) / 10).toString()
                                        bindValue: true
                                        suffix: "°"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseFloat(value)
                                            if (!isNaN(parsed)) workspace.setSelectedPolygonRotation(parsed)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "顶点圆角"
                                    visible: workspace.selectedSupportsShapeCornerRadius
                                    ValueBox {
                                        value: workspace.selectedPolygonCornerRadius.toString()
                                        bindValue: true
                                        suffix: "px"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedPolygonCornerRadius(parsed)
                                        }
                                    }
                                    TinyLabel {
                                        text: "最大 " + workspace.selectedPolygonCornerRadiusMax
                                        Layout.preferredWidth: 62
                                    }
                                }
                            }

                            PropertySection {
                                id: textContentSection
                                Layout.fillWidth: true
                                Layout.row: 10
                                title: "文字内容"
                                summary: workspace.selectedTextBindingEnabled ? workspace.selectedTextCandidateCount + " 条候选" : "整段排版"
                                visible: inspectorTab === 0 && workspace.selectedIsTextLayer

                                ContentTextEditor {
                                    id: selectedTextEditor
                                    width: parent.width
                                    value: workspace.selectedTextContent
                                    placeholder: "输入文字内容"
                                    contextIndex: workspace.selectedLayerIndex
                                    enabled: !workspace.selectedLocked
                                    onCommitted: (value, contextIndex) => {
                                        workspace.setTextContentForLayer(contextIndex, value)
                                    }
                                }

                                InspectorRow {
                                    id: rangeColorRow
                                    label: "选区色"
                                    visible: !workspace.selectedTextBindingEnabled
                                    CompactActionButton {
                                        Layout.preferredWidth: 90
                                        label: "选区颜色"
                                        enabled: selectedTextEditor.selectionLength > 0
                                                 && !workspace.selectedLocked
                                                 && !workspace.operationsBlocked
                                        onClicked: effectColorDialog.openFor(
                                            "textRange",
                                            workspace.selectedTextColor,
                                            0,
                                            selectedTextEditor.selectionStart,
                                            selectedTextEditor.selectionEnd
                                        )
                                    }
                                    CompactActionButton {
                                        Layout.preferredWidth: 70
                                        label: "清除"
                                        enabled: selectedTextEditor.selectionLength > 0
                                                 && workspace.selectedTextColorRangeCount > 0
                                                 && !workspace.selectedLocked
                                                 && !workspace.operationsBlocked
                                        onClicked: workspace.clearSelectedTextColorRangeQt(
                                            selectedTextEditor.selectionStart,
                                            selectedTextEditor.selectionEnd
                                        )
                                    }
                                    TinyLabel {
                                        Layout.preferredWidth: 40
                                        text: workspace.selectedTextColorRangeCount > 0 ? workspace.selectedTextColorRangeCount + "处" : ""
                                        horizontalAlignment: Text.AlignRight
                                        color: Theme.textMuted
                                    }
                                }

                                InspectorRow {
                                    id: rangeFontSizeRow
                                    label: "选区字"
                                    visible: !workspace.selectedTextBindingEnabled
                                    CompactActionButton {
                                        Layout.preferredWidth: 90
                                        label: "应用字号"
                                        enabled: selectedTextEditor.selectionLength > 0
                                                 && !workspace.selectedLocked
                                                 && !workspace.operationsBlocked
                                        onClicked: {
                                            var parsed = parseInt(rangeFontSizeInput.text)
                                            if (!isNaN(parsed) && parsed >= 1)
                                                workspace.setSelectedTextFontSizeRangeQt(
                                                    selectedTextEditor.selectionStart,
                                                    selectedTextEditor.selectionEnd,
                                                    parsed
                                                )
                                        }
                                    }
                                    CompactActionButton {
                                        Layout.preferredWidth: 70
                                        label: "清除"
                                        enabled: selectedTextEditor.selectionLength > 0
                                                 && workspace.selectedTextFontSizeRangeCount > 0
                                                 && !workspace.selectedLocked
                                                 && !workspace.operationsBlocked
                                        onClicked: workspace.clearSelectedTextFontSizeRangeQt(
                                            selectedTextEditor.selectionStart,
                                            selectedTextEditor.selectionEnd
                                        )
                                    }
                                    TinyLabel {
                                        Layout.preferredWidth: 40
                                        text: workspace.selectedTextFontSizeRangeCount > 0 ? workspace.selectedTextFontSizeRangeCount + "处" : ""
                                        horizontalAlignment: Text.AlignRight
                                        color: Theme.textMuted
                                    }
                                }

                                InspectorRow {
                                    label: "字号值"
                                    visible: !workspace.selectedTextBindingEnabled
                                    ValueBox {
                                        id: rangeFontSizeInput
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedTextFontSize.toString()
                                        bindValue: true
                                        suffix: "px"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                    }
                                }

                                InspectorRow {
                                    label: "绑定"
                                    Row {
                                        Layout.preferredWidth: Theme.inspectorWBind
                                        height: 22
                                        spacing: 2
                                        Repeater {
                                            model: [
                                                { label: "行随机", enabled: true },
                                                { label: "整段", enabled: false }
                                            ]
                                            delegate: Rectangle {
                                                required property var modelData
                                                width: (parent.width - 2) / 2
                                                height: parent.height
                                                radius: 3
                                                color: workspace.selectedTextBindingEnabled === modelData.enabled ? Theme.accentSoft : (bindMouse.containsMouse ? Theme.bgHover : Theme.bgControl)
                                                border.width: 1
                                                border.color: workspace.selectedTextBindingEnabled === modelData.enabled ? Theme.accentPressed : Theme.borderStrong
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: parent.modelData.label
                                                    color: workspace.selectedTextBindingEnabled === parent.modelData.enabled ? Theme.accent : Theme.textSecondary
                                                    font.family: Theme.bodyFont
                                                    font.pixelSize: 9
                                                    font.weight: Font.DemiBold
                                                }
                                                MouseArea {
                                                    id: bindMouse
                                                    anchors.fill: parent
                                                    enabled: !workspace.selectedLocked
                                                    hoverEnabled: true
                                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                    onClicked: workspace.setSelectedTextBindingEnabled(parent.modelData.enabled)
                                                }
                                            }
                                        }
                                    }
                                }

                            }

                            PropertySection {
                                id: textFontSection
                                objectName: "textFontSection"
                                Layout.fillWidth: false
                                Layout.row: 20
                                title: "字体"
                                summary: workspace.selectedTextFontSize + " px"
                                visible: inspectorTab === 0 && workspace.selectedIsTextLayer

                                InspectorRow {
                                    label: "字体"
                                    FontSelectBox {
                                        Layout.preferredWidth: Theme.inspectorWSelect
                                        options: workspace.selectedTextFontTreeOptions
                                        value: workspace.selectedTextFontFamily
                                        face: workspace.selectedTextFontFace
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: function(value, face) {
                                            workspace.setSelectedTextFontFace(value, face)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "样式"
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedTextFontSize.toString()
                                        bindValue: true
                                        suffix: "px"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextFontSize(parsed)
                                        }
                                    }
                                    FormatToggleButton {
                                        symbol: "B"
                                        tooltip: "粗体"
                                        active: workspace.selectedTextBold
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.setSelectedTextBold(!workspace.selectedTextBold)
                                    }
                                    FormatToggleButton {
                                        symbol: "I"
                                        tooltip: "斜体"
                                        italicSymbol: true
                                        active: workspace.selectedTextItalic
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.setSelectedTextItalic(!workspace.selectedTextItalic)
                                    }
                                }
                                Text {
                                    visible: workspace.selectedTextFontWarning.length > 0
                                    text: workspace.selectedTextFontWarning
                                    color: Theme.errorText
                                    font.family: Theme.bodyFont
                                    font.pixelSize: 11
                                    wrapMode: Text.Wrap
                                    Layout.fillWidth: false
                                }
                                InspectorRow {
                                    label: "字重"
                                    SelectBox {
                                        Layout.preferredWidth: Theme.inspectorWSelect
                                        model: workspace.selectedTextFontWeightOptions
                                        currentIndex: window.optionIndex(model, workspace.selectedTextFontWeight)
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: workspace.setSelectedTextFontWeight(currentValue)
                                    }
                                }
                            }

                            PropertySection {
                                id: textTypographySection
                                objectName: "textTypographySection"
                                Layout.fillWidth: false
                                Layout.row: 30
                                title: "排版"
                                summary: workspace.selectedTextTypographySummary
                                visible: inspectorTab === 0 && workspace.selectedIsTextLayer

                                InspectorRow {
                                    label: "对齐"
                                    Row {
                                        Layout.preferredWidth: Theme.inspectorWAlign
                                        height: 22
                                        spacing: 2
                                        Repeater {
                                            model: [
                                                { label: "左", value: "left" },
                                                { label: "中", value: "center" },
                                                { label: "右", value: "right" }
                                            ]
                                            delegate: Rectangle {
                                                required property var modelData
                                                width: (parent.width - 4) / 3
                                                height: parent.height
                                                radius: 3
                                                color: workspace.selectedTextAlignmentId === modelData.value ? Theme.accentSoft : (alignMouse.containsMouse ? Theme.bgHover : Theme.bgControl)
                                                border.width: 1
                                                border.color: workspace.selectedTextAlignmentId === modelData.value ? Theme.accentPressed : Theme.borderStrong
                                                opacity: enabled ? 1 : 0.38
                                                enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: parent.modelData.label
                                                    color: workspace.selectedTextAlignmentId === parent.modelData.value ? Theme.accent : Theme.textSecondary
                                                    font.family: Theme.bodyFont
                                                    font.pixelSize: 9
                                                    font.weight: Font.DemiBold
                                                }
                                                MouseArea {
                                                    id: alignMouse
                                                    anchors.fill: parent
                                                    enabled: parent.enabled
                                                    hoverEnabled: true
                                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                    onClicked: workspace.setSelectedTextAlignment(parent.modelData.value)
                                                }
                                            }
                                        }
                                    }
                                    SegmentedControl {
                                        Layout.preferredWidth: Theme.inspectorWSeg2
                                        accessibleName: "文字排列方向"
                                        options: [
                                            { label: "横", value: "horizontal" },
                                            { label: "竖", value: "vertical" }
                                        ]
                                        value: workspace.selectedTextVerticalLayout ? "vertical" : "horizontal"
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: value => workspace.setSelectedTextVerticalLayout(value === "vertical")
                                    }
                                }
                                InspectorRow {
                                    label: "间距"
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextLineSpacingPercent.toString()
                                        bindValue: true
                                        suffix: "行距%"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextLineSpacingPercent(parsed)
                                        }
                                    }
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextLetterSpacing.toString()
                                        bindValue: true
                                        suffix: "字距px"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextLetterSpacing(parsed)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "文本框"
                                    SegmentedControl {
                                        Layout.preferredWidth: Theme.inspectorWSeg2
                                        accessibleName: "文本框尺寸模式"
                                        options: [
                                            { label: "手动", value: "manual" },
                                            { label: "自动", value: "auto" }
                                        ]
                                        value: workspace.selectedTextAutoFitTextBox ? "auto" : "manual"
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: value => workspace.setSelectedTextAutoFitTextBox(value === "auto")
                                    }
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedTextBoxPadding.toString()
                                        bindValue: true
                                        suffix: "px"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextBoxPadding(parsed)
                                        }
                                    }
                                }
                            }

                            PropertySection {
                                id: groupSection
                                Layout.fillWidth: false
                                Layout.row: 0
                                title: "图层组"
                                summary: workspace.selectedGroupChildCount + " 个图层"
                                visible: inspectorTab === 0 && workspace.selectedIsLayerGroup

                                InspectorRow {
                                    label: "名称"
                                    ValueBox {
                                        id: groupNameEditor
                                        value: workspace.selectedLayerName
                                        bindValue: true
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => workspace.setSelectedName(value)
                                    }
                                }
                                InspectorRow {
                                    label: "展开"
                                    TrailingToggle {
                                        accessibleName: "展开图层组"
                                        checked: workspace.selectedGroupExpanded
                                        enabled: !workspace.operationsBlocked
                                        onToggled: workspace.toggleLayerGroupExpanded(workspace.selectedLayerIndex)
                                    }
                                }
                            }

                            PropertySection {
                                id: basicPropertiesSection
                                Layout.fillWidth: true
                                Layout.row: 0
                                title: "基本属性"
                                summary: workspace.selectedWidth + " × " + workspace.selectedHeight
                                expanded: false
                                visible: inspectorTab === 0 && !workspace.selectedIsLayerGroup

                                InspectorRow {
                                    label: "名称"
                                    ValueBox {
                                        id: layerNameEditor
                                        value: workspace.selectedLayerName; bindValue: true; Layout.fillWidth: false
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => workspace.setSelectedName(value)
                                    }
                                }
                                InspectorRow {
                                    label: "位置"
                                    ValueBox {
                                        value: workspace.selectedX.toString(); bindValue: true; suffix: "X"; Layout.fillWidth: false
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedX(parsed) }
                                    }
                                    ValueBox {
                                        value: workspace.selectedY.toString(); bindValue: true; suffix: "Y"; Layout.fillWidth: false
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedY(parsed) }
                                    }
                                }
                                InspectorRow {
                                    label: "尺寸"
                                    ValueBox {
                                        value: workspace.selectedWidth.toString(); bindValue: true; suffix: "W"; Layout.fillWidth: false
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedWidth(parsed) }
                                    }
                                    ValueBox {
                                        value: workspace.selectedHeight.toString(); bindValue: true; suffix: "H"; Layout.fillWidth: false
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedHeight(parsed) }
                                    }
                                    IconButton {
                                        iconName: workspace.selectedAspectRatioLocked ? AppIcons.lock : AppIcons.unlock
                                        tooltip: workspace.selectedAspectRatioLocked ? "解除比例锁定" : "锁定宽高比例"
                                        buttonSize: 30
                                        active: workspace.selectedAspectRatioLocked
                                        enabled: workspace.selectedSupportsAspectRatioLock && !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.setSelectedAspectRatioLocked(!workspace.selectedAspectRatioLocked)
                                    }
                                }
                            }

                            PropertySection {
                                id: appearanceSection
                                Layout.fillWidth: true
                                Layout.row: 40
                                title: "外观"
                                summary: workspace.selectedSupportsBlendMode ? workspace.selectedBlendModeName : "标准"
                                visible: inspectorTab === 0 && !workspace.selectedIsLayerGroup

                                InspectorRow {
                                    label: "不透明度"
                                    Slider {
                                        id: opacitySlider
                                        objectName: "opacitySlider"
                                        Layout.preferredWidth: parent.wSliderFill
                                        Layout.preferredHeight: 14
                                        from: 0
                                        to: 100
                                        stepSize: 1
                                        snapMode: Slider.SnapAlways
                                        value: workspace.selectedOpacity
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPressedChanged: {
                                            if (pressed)
                                                workspace.beginSelectedOpacityEdit()
                                            else
                                                workspace.endSelectedOpacityEdit()
                                        }
                                        onMoved: workspace.updateSelectedOpacityEdit(Math.round(value))

                                        background: Rectangle {
                                            x: opacitySlider.leftPadding
                                            y: opacitySlider.topPadding + opacitySlider.availableHeight / 2 - height / 2
                                            width: opacitySlider.availableWidth
                                            height: 3
                                            radius: 2
                                            color: Theme.borderStrong

                                            Rectangle {
                                                width: opacitySlider.visualPosition * parent.width
                                                height: parent.height
                                                radius: parent.radius
                                                color: opacitySlider.enabled ? Theme.accent : Theme.textDisabled
                                            }
                                        }

                                        handle: Rectangle {
                                            x: opacitySlider.leftPadding
                                               + opacitySlider.visualPosition * (opacitySlider.availableWidth - width)
                                            y: opacitySlider.topPadding + opacitySlider.availableHeight / 2 - height / 2
                                            width: 10
                                            height: 10
                                            radius: 5
                                            color: opacitySlider.enabled ? Theme.textPrimary : Theme.textDisabled
                                            border.width: 1
                                            border.color: opacitySlider.activeFocus ? Theme.focusRing : Theme.accentPressed
                                        }

                                        Accessible.name: "图层不透明度"
                                    }
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWSliderVB
                                        value: workspace.selectedOpacity.toString(); bindValue: true; suffix: "%"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedOpacity(parsed) }
                                    }
                                }
                                InspectorRow {
                                    label: "混合"
                                    SelectBox {
                                        Layout.preferredWidth: Theme.inspectorWSelect
                                        model: window.blendModeOptions
                                        enabled: workspace.selectedSupportsBlendMode && !workspace.selectedLocked && !workspace.operationsBlocked
                                        currentIndex: {
                                            for (var index = 0; index < window.blendModeOptions.length; index++) {
                                                if (window.blendModeOptions[index].value === workspace.selectedBlendModeId) return index
                                            }
                                            return 0
                                        }
                                        onActivated: workspace.setSelectedBlendMode(currentValue)
                                    }
                                }
                            }

                            PropertySection {
                                id: layerTransformSection
                                objectName: "layerTransformSection"
                                Layout.fillWidth: false
                                Layout.row: 20
                                title: "图层变换"
                                summary: Math.abs(workspace.selectedRotation) > 0.001
                                         ? Math.round(workspace.selectedRotation * 10) / 10 + "°"
                                         : (workspace.selectedFlipHorizontal || workspace.selectedFlipVertical ? "已翻转" : "未变换")
                                visible: inspectorTab === 1 && !workspace.selectedIsLayerGroup

                                InspectorRow {
                                    label: "旋转"
                                    ValueBox {
                                        value: (Math.round(workspace.selectedRotation * 10) / 10).toString()
                                        bindValue: true
                                        suffix: "°"
                                        Layout.fillWidth: false
                                        editable: workspace.selectedCanRotate && !workspace.selectedLocked
                                        onValueCommitted: value => {
                                            var parsed = parseFloat(value)
                                            if (!isNaN(parsed)) workspace.setSelectedRotation(parsed)
                                        }
                                    }
                                    IconButton {
                                        iconName: AppIcons.rotateLeft
                                        tooltip: "重置旋转"
                                        buttonSize: 30
                                        enabled: workspace.selectedCanRotate && !workspace.selectedLocked && Math.abs(workspace.selectedRotation) > 0.001
                                        onClicked: workspace.setSelectedRotation(0)
                                    }
                                }

                                InspectorRow {
                                    label: "翻转"
                                    Item {
                                        Layout.fillWidth: true
                                    }
                                    IconButton {
                                        iconName: AppIcons.horizontal
                                        tooltip: "水平翻转"
                                        buttonSize: 30
                                        active: workspace.selectedFlipHorizontal
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.setSelectedFlipHorizontal(!workspace.selectedFlipHorizontal)
                                    }
                                    IconButton {
                                        iconName: AppIcons.vertical
                                        tooltip: "垂直翻转"
                                        buttonSize: 30
                                        active: workspace.selectedFlipVertical
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.setSelectedFlipVertical(!workspace.selectedFlipVertical)
                                    }
                                }
                            }

                            PropertySection {
                                id: randomTransformSection
                                Layout.fillWidth: true
                                Layout.row: 30
                                title: "随机变换"
                                summary: workspace.selectedRandomTransformEnabledCount > 0
                                         ? workspace.selectedRandomTransformEnabledCount + " 项已启用" : "关闭"
                                visible: inspectorTab === 1 && workspace.selectedSupportsRandomTransform

                                RowLayout {
                                    width: parent.width
                                    spacing: 6

                                    OptionTile {
                                        compact: true
                                        title: "位置"
                                        detail: workspace.selectedRandomPositionEnabled
                                                ? "±" + workspace.selectedRandomPositionRange + " px"
                                                : "随机偏移"
                                        selected: workspace.selectedRandomPositionEnabled
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: workspace.setSelectedRandomPositionEnabled(!workspace.selectedRandomPositionEnabled)
                                    }
                                    OptionTile {
                                        compact: true
                                        title: "缩放"
                                        detail: workspace.selectedRandomScaleEnabled
                                                ? workspace.selectedRandomScaleMinPercent + "–" + workspace.selectedRandomScaleMaxPercent + "%"
                                                : "随机比例"
                                        selected: workspace.selectedRandomScaleEnabled
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: workspace.setSelectedRandomScaleEnabled(!workspace.selectedRandomScaleEnabled)
                                    }
                                    OptionTile {
                                        compact: true
                                        title: "旋转"
                                        detail: workspace.selectedRandomRotationEnabled
                                                ? "±" + Math.round(workspace.selectedRandomRotationRange * 10) / 10 + "°"
                                                : "随机角度"
                                        selected: workspace.selectedRandomRotationEnabled
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: workspace.setSelectedRandomRotationEnabled(!workspace.selectedRandomRotationEnabled)
                                    }
                                }

                                InspectorRow {
                                    label: "位置范围"
                                    visible: workspace.selectedRandomPositionEnabled
                                    ValueBox {
                                        value: workspace.selectedRandomPositionRange.toString()
                                        bindValue: true
                                        suffix: "± px"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedRandomPositionRange(parsed)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "缩放范围"
                                    visible: workspace.selectedRandomScaleEnabled
                                    ValueBox {
                                        value: workspace.selectedRandomScaleMinPercent.toString()
                                        bindValue: true
                                        suffix: "min%"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedRandomScaleMinPercent(parsed)
                                        }
                                    }
                                    ValueBox {
                                        value: workspace.selectedRandomScaleMaxPercent.toString()
                                        bindValue: true
                                        suffix: "max%"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedRandomScaleMaxPercent(parsed)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "旋转范围"
                                    visible: workspace.selectedRandomRotationEnabled
                                    ValueBox {
                                        value: (Math.round(workspace.selectedRandomRotationRange * 10) / 10).toString()
                                        bindValue: true
                                        suffix: "±°"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseFloat(value)
                                            if (!isNaN(parsed)) workspace.setSelectedRandomRotationRange(parsed)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "本次"
                                    TinyLabel {
                                        text: workspace.selectedRandomPreviewSummary
                                        color: workspace.selectedRandomTransformEnabledCount > 0 ? Theme.textSecondary : Theme.textMuted
                                        elide: Text.ElideRight
                                        Layout.fillWidth: true
                                    }
                                    IconButton {
                                        iconName: AppIcons.randomize
                                        tooltip: "换一组随机变换"
                                        buttonSize: 30
                                        enabled: workspace.selectedRandomTransformEnabledCount > 0 && !workspace.selectedLocked && !workspace.operationsBlocked
                                        onClicked: workspace.regenerateSelectedRandomTransform()
                                    }
                                }
                            }

                            PropertySection {
                                id: clonePropertiesSection
                                objectName: "clonePropertiesSection"
                                Layout.fillWidth: true
                                Layout.row: 10
                                title: "图层分身"
                                summary: workspace.selectedCloneEnabled
                                         ? workspace.selectedCloneRows + " × " + workspace.selectedCloneColumns
                                         : "关闭"
                                visible: inspectorTab === 1 && workspace.selectedSupportsClone

                                InspectorRow {
                                    label: "启用"
                                    TrailingToggle {
                                        accessibleName: "启用图层分身"
                                        checked: workspace.selectedCloneEnabled
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onToggled: checkedValue => workspace.setSelectedCloneEnabled(checkedValue)
                                    }
                                }

                                InspectorRow {
                                    label: "布局"
                                    visible: workspace.selectedCloneEnabled
                                    SegmentedControl {
                                        Layout.fillWidth: false
                                        accessibleName: "分身布局模式"
                                        options: [
                                            { label: "固定行列", value: "fixed" },
                                            { label: "填充画布", value: "fill" }
                                        ]
                                        value: workspace.selectedCloneLayoutMode
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: value => workspace.setSelectedCloneLayoutMode(value)
                                    }
                                }

                                InspectorRow {
                                    label: "数量"
                                    visible: workspace.selectedCloneEnabled && workspace.selectedCloneLayoutMode === "fixed"
                                    ValueBox {
                                        value: workspace.selectedCloneRows.toString()
                                        bindValue: true
                                        suffix: "行"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCloneRows(parsed)
                                        }
                                    }
                                    ValueBox {
                                        value: workspace.selectedCloneColumns.toString()
                                        bindValue: true
                                        suffix: "列"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCloneColumns(parsed)
                                        }
                                    }
                                }

                                InspectorRow {
                                    label: "间距"
                                    visible: workspace.selectedCloneEnabled && workspace.selectedCloneLayoutMode === "fixed"
                                    ValueBox {
                                        value: workspace.selectedCloneRowSpacing.toString()
                                        bindValue: true
                                        suffix: "行px"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCloneRowSpacing(parsed)
                                        }
                                    }
                                    ValueBox {
                                        value: workspace.selectedCloneColumnSpacing.toString()
                                        bindValue: true
                                        suffix: "列px"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCloneColumnSpacing(parsed)
                                        }
                                    }
                                }

                                InspectorRow {
                                    label: "镜像"
                                    visible: workspace.selectedCloneEnabled
                                    SelectBox {
                                        Layout.fillWidth: false
                                        model: window.cloneMirrorOptions
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        currentIndex: window.optionIndex(window.cloneMirrorOptions, workspace.selectedCloneMirrorMode)
                                        onActivated: workspace.setSelectedCloneMirrorMode(currentValue)
                                    }
                                }

                                InspectorRow {
                                    label: "尺寸"
                                    visible: workspace.selectedCloneEnabled
                                    SegmentedControl {
                                        Layout.fillWidth: false
                                        accessibleName: "分身尺寸模式"
                                        options: [
                                            { label: "沿用图层", value: "source" },
                                            { label: "独立尺寸", value: "custom" }
                                        ]
                                        value: workspace.selectedCloneCustomSizeEnabled ? "custom" : "source"
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: value => workspace.setSelectedCloneCustomSizeEnabled(value === "custom")
                                    }
                                }

                                InspectorRow {
                                    label: "分身尺寸"
                                    visible: workspace.selectedCloneEnabled && workspace.selectedCloneCustomSizeEnabled
                                    ValueBox {
                                        value: workspace.selectedCloneCustomWidth.toString()
                                        bindValue: true
                                        suffix: "W"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCloneCustomWidth(parsed)
                                        }
                                    }
                                    ValueBox {
                                        value: workspace.selectedCloneCustomHeight.toString()
                                        bindValue: true
                                        suffix: "H"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCloneCustomHeight(parsed)
                                        }
                                    }
                                }

                                InspectorRow {
                                    label: "排列"
                                    visible: workspace.selectedCloneEnabled && workspace.selectedCloneLayoutMode === "fill"
                                    SelectBox {
                                        Layout.fillWidth: false
                                        model: window.cloneFillModeOptions
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        currentIndex: window.optionIndex(window.cloneFillModeOptions, workspace.selectedCloneFillMode)
                                        onActivated: workspace.setSelectedCloneFillMode(currentValue)
                                    }
                                }

                                InspectorRow {
                                    label: "铺排参数"
                                    visible: workspace.selectedCloneEnabled && workspace.selectedCloneLayoutMode === "fill"
                                    ValueBox {
                                        value: workspace.selectedCloneFillSpacing.toString()
                                        bindValue: true
                                        suffix: "间距"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCloneFillSpacing(parsed)
                                        }
                                    }
                                    ValueBox {
                                        value: workspace.selectedCloneFillMargin.toString()
                                        bindValue: true
                                        suffix: "边距"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCloneFillMargin(parsed)
                                        }
                                    }
                                }

                                InspectorRow {
                                    label: "铺排角度"
                                    visible: workspace.selectedCloneEnabled && workspace.selectedCloneLayoutMode === "fill"
                                    ValueBox {
                                        value: (Math.round(workspace.selectedCloneFillAngle * 10) / 10).toString()
                                        bindValue: true
                                        suffix: "°"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseFloat(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCloneFillAngle(parsed)
                                        }
                                    }
                                }
                            }

                            PropertySection {
                                width: parent.width
                                title: "图层绑定"
                                summary: "未绑定"
                                expanded: false
                                visible: false
                            }
                        }

                        Column {
                            id: effectInspectorColumn
                            width: inspectorScroll.availableWidth
                            y: propertyInspectorColumn.implicitHeight
                            visible: selectedLayer >= 0

                            PropertySection {
                                id: textFillSection
                                objectName: "textFillSection"
                                width: parent.width
                                title: "文字填充"
                                summary: workspace.selectedTextFillSummary
                                visible: inspectorTab === 0 && workspace.selectedIsTextLayer

                                InspectorRow {
                                    label: "模式"
                                    Row {
                                        Layout.preferredWidth: Theme.inspectorWSeg2
                                        height: 22
                                        spacing: 2
                                        Repeater {
                                            model: [
                                                { label: "纯色", value: "solid" },
                                                { label: "渐变", value: "gradient" }
                                            ]
                                            delegate: Rectangle {
                                                required property var modelData
                                                width: (parent.width - 2) / 2
                                                height: parent.height
                                                radius: 3
                                                color: workspace.selectedTextFillModeId === modelData.value ? Theme.accentSoft : (fillMouse.containsMouse ? Theme.bgHover : Theme.bgControl)
                                                border.width: 1
                                                border.color: workspace.selectedTextFillModeId === modelData.value ? Theme.accentPressed : Theme.borderStrong
                                                opacity: enabled ? 1 : 0.38
                                                enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: parent.modelData.label
                                                    color: workspace.selectedTextFillModeId === parent.modelData.value ? Theme.accent : Theme.textSecondary
                                                    font.family: Theme.bodyFont
                                                    font.pixelSize: 9
                                                    font.weight: Font.DemiBold
                                                }
                                                MouseArea {
                                                    id: fillMouse
                                                    anchors.fill: parent
                                                    enabled: parent.enabled
                                                    hoverEnabled: true
                                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                    onClicked: workspace.setSelectedTextFillMode(parent.modelData.value)
                                                }
                                            }
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "颜色"
                                    visible: workspace.selectedTextFillModeId === "solid"
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedTextColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("textFill", workspace.selectedTextColor)
                                        onValueCommitted: value => workspace.setSelectedTextColor(value)
                                    }
                                }
                                InspectorRow {
                                    label: "类型"
                                    visible: workspace.selectedTextFillModeId === "gradient"
                                    SelectBox {
                                        Layout.preferredWidth: Theme.inspectorWSelect
                                        model: window.textGradientTypeOptions
                                        currentIndex: window.optionIndex(window.textGradientTypeOptions, workspace.selectedTextGradientTypeId)
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: workspace.setSelectedTextGradientType(currentValue)
                                    }
                                }
                                InspectorRow {
                                    label: "方向"
                                    visible: workspace.selectedTextFillModeId === "gradient"
                                             && workspace.selectedTextGradientTypeId === "linear"
                                    SelectBox {
                                        Layout.preferredWidth: Theme.inspectorWSelect
                                        model: window.textGradientDirectionOptions
                                        currentIndex: window.optionIndex(window.textGradientDirectionOptions, workspace.selectedTextGradientDirectionId)
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: workspace.setSelectedTextGradientDirection(currentValue)
                                    }
                                }
                                InspectorRow {
                                    label: "起始"
                                    visible: workspace.selectedTextFillModeId === "gradient"
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedTextGradientStartColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("textGradient", workspace.selectedTextGradientStartColor, 0)
                                        onValueCommitted: value => workspace.setSelectedTextGradientColor(0, value)
                                    }
                                }
                                InspectorRow {
                                    label: "结束"
                                    visible: workspace.selectedTextFillModeId === "gradient"
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedTextGradientEndColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("textGradient", workspace.selectedTextGradientEndColor, 1)
                                        onValueCommitted: value => workspace.setSelectedTextGradientColor(1, value)
                                    }
                                }
                                InspectorRow {
                                    label: "中心"
                                    visible: workspace.selectedTextFillModeId === "gradient"
                                             && workspace.selectedTextGradientTypeId === "radial"
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextGradientCenterXPercent.toString()
                                        bindValue: true
                                        suffix: "X%"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var xValue = parseInt(value)
                                            var yValue = workspace.selectedTextGradientCenterYPercent
                                            if (!isNaN(xValue)) workspace.setSelectedTextGradientCenter(xValue, yValue)
                                        }
                                    }
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextGradientCenterYPercent.toString()
                                        bindValue: true
                                        suffix: "Y%"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var xValue = workspace.selectedTextGradientCenterXPercent
                                            var yValue = parseInt(value)
                                            if (!isNaN(yValue)) workspace.setSelectedTextGradientCenter(xValue, yValue)
                                        }
                                    }
                                }
                            }

                            PropertySection {
                                id: textBackgroundSection
                                objectName: "textBackgroundSection"
                                width: parent.width
                                title: "文字背景"
                                summary: workspace.selectedTextBackgroundSummary
                                visible: inspectorTab === 1 && workspace.selectedIsTextLayer

                                InspectorRow {
                                    label: "模式"
                                    SegmentedControl {
                                        Layout.preferredWidth: Theme.inspectorWSeg2
                                        accessibleName: "文字背景模式"
                                        options: [
                                            { label: "关", value: "off" },
                                            { label: "纯", value: "solid" }
                                        ]
                                        value: workspace.selectedTextBackgroundEnabled ? "solid" : "off"
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: function(value) {
                                            workspace.setSelectedTextBackgroundEnabled(value === "solid")
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "颜色"
                                    visible: workspace.selectedTextBackgroundEnabled
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedTextBackgroundColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("textBackground", workspace.selectedTextBackgroundColor)
                                        onValueCommitted: value => workspace.setSelectedTextBackgroundColor(value)
                                    }
                                }
                                InspectorRow {
                                    label: "参数"
                                    visible: workspace.selectedTextBackgroundEnabled
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextBackgroundOpacity.toString()
                                        bindValue: true
                                        suffix: "%"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextBackgroundOpacity(parsed)
                                        }
                                    }
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextBackgroundPadding.toString()
                                        bindValue: true
                                        suffix: "扩px"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextBackgroundPadding(parsed)
                                        }
                                    }
                                }
                            }

                            PropertySection {
                                id: textShadowSection
                                objectName: "textShadowSection"
                                width: parent.width
                                title: "文字阴影"
                                summary: workspace.selectedTextShadowSummary
                                visible: inspectorTab === 1 && workspace.selectedIsTextLayer

                                InspectorRow {
                                    label: "模式"
                                    SegmentedControl {
                                        Layout.preferredWidth: Theme.inspectorWSeg2
                                        accessibleName: "文字阴影模式"
                                        options: [
                                            { label: "关", value: "off" },
                                            { label: "开", value: "on" }
                                        ]
                                        value: workspace.selectedTextShadowEnabled ? "on" : "off"
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: function(value) {
                                            workspace.setSelectedTextShadowEnabled(value === "on")
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "偏移"
                                    visible: workspace.selectedTextShadowEnabled
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextShadowOffsetX.toString()
                                        bindValue: true
                                        suffix: "X"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var xValue = parseInt(value)
                                            var yValue = workspace.selectedTextShadowOffsetY
                                            if (!isNaN(xValue)) workspace.setSelectedTextShadowOffset(xValue, yValue)
                                        }
                                    }
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextShadowOffsetY.toString()
                                        bindValue: true
                                        suffix: "Y"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var xValue = workspace.selectedTextShadowOffsetX
                                            var yValue = parseInt(value)
                                            if (!isNaN(yValue)) workspace.setSelectedTextShadowOffset(xValue, yValue)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "模糊/色"
                                    visible: workspace.selectedTextShadowEnabled
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextShadowBlur.toString()
                                        bindValue: true
                                        suffix: "px"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextShadowBlur(parsed)
                                        }
                                    }
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextShadowColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("textShadow", workspace.selectedTextShadowColor)
                                        onValueCommitted: value => workspace.setSelectedTextShadowColor(value)
                                    }
                                }
                                InspectorRow {
                                    label: "透明度"
                                    visible: workspace.selectedTextShadowEnabled
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedTextShadowOpacity.toString()
                                        bindValue: true
                                        suffix: "%"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextShadowOpacity(parsed)
                                        }
                                    }
                                }
                            }

                            PropertySection {
                                id: textGlowSection
                                objectName: "textGlowSection"
                                width: parent.width
                                title: "文字发光"
                                summary: workspace.selectedTextGlowSummary
                                visible: inspectorTab === 1 && workspace.selectedIsTextLayer

                                InspectorRow {
                                    label: "模式"
                                    SegmentedControl {
                                        Layout.preferredWidth: Theme.inspectorWSeg2
                                        accessibleName: "文字发光模式"
                                        options: [
                                            { label: "关", value: "off" },
                                            { label: "开", value: "on" }
                                        ]
                                        value: workspace.selectedTextGlowEnabled ? "on" : "off"
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: function(value) {
                                            workspace.setSelectedTextGlowEnabled(value === "on")
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "参数"
                                    visible: workspace.selectedTextGlowEnabled
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextGlowStrength.toString()
                                        bindValue: true
                                        suffix: "强度"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextGlowStrength(parsed)
                                        }
                                    }
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextGlowRadius.toString()
                                        bindValue: true
                                        suffix: "半径px"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextGlowRadius(parsed)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "颜色/透"
                                    visible: workspace.selectedTextGlowEnabled
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextGlowColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("textGlow", workspace.selectedTextGlowColor)
                                        onValueCommitted: value => workspace.setSelectedTextGlowColor(value)
                                    }
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedTextGlowOpacity.toString()
                                        bindValue: true
                                        suffix: "%"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextGlowOpacity(parsed)
                                        }
                                    }
                                }
                            }

                            PropertySection {
                                id: advancedStrokeSection
                                objectName: "advancedStrokeSection"
                                width: parent.width
                                title: "描边"
                                summary: workspace.selectedStrokeEnabled ? workspace.selectedStrokeWidth + " px" : "关闭"
                                visible: inspectorTab === 0 && workspace.selectedSupportsStroke

                                InspectorRow {
                                    label: "模式"
                                    SegmentedControl {
                                        Layout.preferredWidth: workspace.selectedSupportsAdvancedStroke ? Theme.inspectorWSeg4 : Theme.inspectorWSeg2
                                        accessibleName: "描边模式"
                                        options: workspace.selectedSupportsAdvancedStroke
                                            ? [
                                                { label: "关", value: "off" },
                                                { label: "外", value: "outer" },
                                                { label: "中", value: "center" },
                                                { label: "内", value: "inner" }
                                            ]
                                            : [
                                                { label: "关", value: "off" },
                                                { label: "开", value: "on" }
                                            ]
                                        value: {
                                            if (!workspace.selectedStrokeEnabled) return "off"
                                            if (!workspace.selectedSupportsAdvancedStroke) return "on"
                                            var t = workspace.selectedStrokeType
                                            if (t === 0) return "inner"
                                            if (t === 1) return "center"
                                            return "outer"
                                        }
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: function(value) {
                                            if (value === "off") {
                                                workspace.setSelectedStrokeEnabled(false)
                                                return
                                            }
                                            if (value === "on") {
                                                workspace.setSelectedStrokeEnabled(true)
                                                return
                                            }
                                            workspace.setSelectedStrokeEnabled(true)
                                            if (value === "inner") workspace.setSelectedStrokeType(0)
                                            else if (value === "center") workspace.setSelectedStrokeType(1)
                                            else if (value === "outer") workspace.setSelectedStrokeType(2)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "宽/色"
                                    visible: workspace.selectedStrokeEnabled
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedStrokeWidth.toString()
                                        bindValue: true
                                        suffix: "px"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedStrokeWidth(parsed)
                                        }
                                    }
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedStrokeColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("stroke", workspace.selectedStrokeColor)
                                        onValueCommitted: value => workspace.setSelectedStrokeColor(value)
                                    }
                                }
                                InspectorRow {
                                    label: "色板"
                                    visible: workspace.selectedStrokeEnabled
                                    Row {
                                        Layout.preferredWidth: 130
                                        spacing: 5
                                        Repeater {
                                            model: ["#000000", "#F2F4F3", "#46D7AD", "#F1786D", "#F7BD63"]
                                            delegate: Rectangle {
                                                required property string modelData
                                                width: 18
                                                height: 18
                                                radius: 3
                                                color: modelData
                                                border.width: workspace.selectedStrokeColor.toUpperCase() === modelData ? 2 : 1
                                                border.color: workspace.selectedStrokeColor.toUpperCase() === modelData ? Theme.accent : Theme.borderStrong
                                                MouseArea {
                                                    anchors.fill: parent
                                                    enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                                    hoverEnabled: true
                                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                    onClicked: workspace.setSelectedStrokeColor(modelData)
                                                }
                                            }
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "连接"
                                    visible: workspace.selectedStrokeEnabled && workspace.selectedSupportsAdvancedStroke
                                    SelectBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        model: window.strokeJoinOptions
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        currentIndex: window.optionIndex(window.strokeJoinOptions, workspace.selectedStrokeJoin)
                                        onActivated: workspace.setSelectedStrokeJoin(currentValue)
                                    }
                                    SelectBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        model: window.strokeCapOptions
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        currentIndex: window.optionIndex(window.strokeCapOptions, workspace.selectedStrokeCap)
                                        onActivated: workspace.setSelectedStrokeCap(currentValue)
                                    }
                                }
                                InspectorRow {
                                    label: "虚线"
                                    visible: workspace.selectedStrokeEnabled && workspace.selectedSupportsAdvancedStroke
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedStrokeDashLength.toString()
                                        bindValue: true
                                        suffix: "段"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedStrokeDash(parsed, workspace.selectedStrokeDashGap)
                                        }
                                    }
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedStrokeDashGap.toString()
                                        bindValue: true
                                        suffix: "间隔"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedStrokeDash(workspace.selectedStrokeDashLength, parsed)
                                        }
                                    }
                                }
                            }
                            PropertySection {
                                id: overlaySection
                                objectName: "overlaySection"
                                width: parent.width
                                title: "颜色叠加"
                                summary: workspace.selectedOverlayMode === "color"
                                         ? "纯色 · " + workspace.selectedColorOverlayOpacity + "%"
                                         : workspace.selectedOverlayMode === "gradient"
                                           ? "渐变 · " + workspace.selectedGradientOverlayOpacity + "% · " + Math.round(workspace.selectedGradientOverlayAngle) + "°"
                                           : "关闭"
                                visible: inspectorTab === 0
                                         && (workspace.selectedSupportsColorOverlay || workspace.selectedSupportsGradientOverlay)

                                InspectorRow {
                                    label: "模式"
                                    SegmentedControl {
                                        Layout.preferredWidth: Theme.inspectorWSeg3
                                        accessibleName: "颜色叠加模式"
                                        options: [
                                            { label: "关闭", value: "none" },
                                            { label: "纯色", value: "color" },
                                            { label: "渐变", value: "gradient" }
                                        ]
                                        value: workspace.selectedOverlayMode
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: value => workspace.setSelectedOverlayMode(value)
                                    }
                                }
                                InspectorRow {
                                    label: "颜色"
                                    visible: workspace.selectedOverlayMode === "color"
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedColorOverlayColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("overlay", workspace.selectedColorOverlayColor)
                                        onValueCommitted: value => workspace.setSelectedColorOverlayColor(value)
                                    }
                                }
                                InspectorRow {
                                    label: "起始"
                                    visible: workspace.selectedOverlayMode === "gradient"
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedGradientStartColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("gradient", workspace.selectedGradientStartColor, 0)
                                        onValueCommitted: value => workspace.setSelectedGradientOverlayColor(0, value)
                                    }
                                }
                                InspectorRow {
                                    label: "结束"
                                    visible: workspace.selectedOverlayMode === "gradient"
                                    ColorValueField {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: workspace.selectedGradientEndColor
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onPickRequested: effectColorDialog.openFor("gradient", workspace.selectedGradientEndColor, 1)
                                        onValueCommitted: value => workspace.setSelectedGradientOverlayColor(1, value)
                                    }
                                }
                                InspectorRow {
                                    label: "强度"
                                    visible: workspace.selectedOverlayMode !== "none"
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: (workspace.selectedOverlayMode === "color"
                                                ? workspace.selectedColorOverlayOpacity
                                                : workspace.selectedGradientOverlayOpacity).toString()
                                        bindValue: true
                                        suffix: "%"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (isNaN(parsed)) return
                                            if (workspace.selectedOverlayMode === "color")
                                                workspace.setSelectedColorOverlayOpacity(parsed)
                                            else
                                                workspace.setSelectedGradientOverlayOpacity(parsed)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "角度"
                                    visible: workspace.selectedOverlayMode === "gradient"
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWInput
                                        value: (Math.round(workspace.selectedGradientOverlayAngle * 10) / 10).toString()
                                        bindValue: true
                                        suffix: "°"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseFloat(value)
                                            if (!isNaN(parsed)) workspace.setSelectedGradientOverlayAngle(parsed)
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "方向"
                                    visible: workspace.selectedOverlayMode === "gradient"
                                    Row {
                                        Layout.preferredWidth: 42 * 4 + 4 * 3
                                        spacing: 4
                                        Repeater {
                                            model: [0, 45, 90, 135]
                                            delegate: Rectangle {
                                                required property int modelData
                                                width: 42
                                                height: 28
                                                radius: Theme.radiusSmall
                                                color: Math.round(workspace.selectedGradientOverlayAngle) === modelData ? Theme.accentSoft : Theme.bgControl
                                                border.width: 1
                                                border.color: Math.round(workspace.selectedGradientOverlayAngle) === modelData ? Theme.accentPressed : Theme.borderStrong
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: modelData + "°"
                                                    color: Math.round(workspace.selectedGradientOverlayAngle) === modelData ? Theme.accent : Theme.textSecondary
                                                    font.family: Theme.bodyFont
                                                    font.pixelSize: 10
                                                    font.weight: Font.DemiBold
                                                }
                                                MouseArea {
                                                    anchors.fill: parent
                                                    enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                                    hoverEnabled: true
                                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                    onClicked: workspace.setSelectedGradientOverlayAngle(modelData)
                                                }
                                            }
                                        }
                                    }
                                }
                            }
                            PropertySection {
                                id: cornerSection
                                objectName: "cornerSection"
                                width: parent.width
                                title: "圆角"
                                summary: workspace.selectedCornerMode === "independent"
                                         ? "独立四角"
                                         : workspace.selectedCornerRadius + " px"
                                visible: inspectorTab === 0 && workspace.selectedSupportsCornerRadius

                                InspectorRow {
                                    label: "模式"
                                    visible: workspace.selectedSupportsVectorCorners
                                    SegmentedControl {
                                        Layout.preferredWidth: Theme.inspectorWSeg2
                                        accessibleName: "圆角编辑模式"
                                        options: [
                                            { label: "统一", value: "uniform" },
                                            { label: "独立四角", value: "independent" }
                                        ]
                                        value: workspace.selectedCornerMode
                                        enabled: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onActivated: value => workspace.setSelectedCornerMode(value)
                                    }
                                }
                                InspectorRow {
                                    label: "半径"
                                    visible: workspace.selectedCornerMode === "uniform"
                                    ValueBox {
                                        Layout.preferredWidth: Theme.inspectorWPair
                                        value: workspace.selectedCornerRadius.toString()
                                        bindValue: true
                                        suffix: "px"
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedCornerRadius(parsed)
                                        }
                                    }
                                    TinyLabel { text: "最大 " + workspace.selectedCornerRadiusMax; Layout.preferredWidth: 62 }
                                }
                                InspectorRow {
                                    label: "预设"
                                    visible: workspace.selectedCornerMode === "uniform"
                                    Row {
                                        Layout.preferredWidth: 42 * 4 + 4 * 3
                                        spacing: 4
                                        Repeater {
                                            model: [0, 12, 24, 48]
                                            delegate: Rectangle {
                                                required property int modelData
                                                width: 42
                                                height: 28
                                                radius: Theme.radiusSmall
                                                enabled: modelData <= workspace.selectedCornerRadiusMax
                                                         && !workspace.selectedLocked
                                                         && !workspace.operationsBlocked
                                                opacity: enabled ? 1 : 0.38
                                                color: workspace.selectedCornerRadius === modelData ? Theme.accentSoft : Theme.bgControl
                                                border.width: 1
                                                border.color: workspace.selectedCornerRadius === modelData ? Theme.accentPressed : Theme.borderStrong
                                                Text {
                                                    anchors.centerIn: parent
                                                    text: modelData
                                                    color: workspace.selectedCornerRadius === modelData ? Theme.accent : Theme.textSecondary
                                                    font.family: Theme.bodyFont
                                                    font.pixelSize: 10
                                                    font.weight: Font.DemiBold
                                                }
                                                MouseArea {
                                                    anchors.fill: parent
                                                    enabled: parent.enabled
                                                    hoverEnabled: true
                                                    cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                    onClicked: workspace.setSelectedCornerRadius(parent.modelData)
                                                }
                                            }
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "上角"
                                    visible: workspace.selectedCornerMode === "independent"
                                    ValueBox {
                                        value: workspace.selectedVectorCornerRadii[0].toString()
                                        bindValue: true
                                        suffix: "TL"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            var radii = workspace.selectedVectorCornerRadii
                                            if (!isNaN(parsed)) workspace.setSelectedVectorCornerRadii(parsed, radii[1], radii[2], radii[3])
                                        }
                                    }
                                    ValueBox {
                                        value: workspace.selectedVectorCornerRadii[1].toString()
                                        bindValue: true
                                        suffix: "TR"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            var radii = workspace.selectedVectorCornerRadii
                                            if (!isNaN(parsed)) workspace.setSelectedVectorCornerRadii(radii[0], parsed, radii[2], radii[3])
                                        }
                                    }
                                }
                                InspectorRow {
                                    label: "下角"
                                    visible: workspace.selectedCornerMode === "independent"
                                    ValueBox {
                                        value: workspace.selectedVectorCornerRadii[3].toString()
                                        bindValue: true
                                        suffix: "BL"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            var radii = workspace.selectedVectorCornerRadii
                                            if (!isNaN(parsed)) workspace.setSelectedVectorCornerRadii(radii[0], radii[1], radii[2], parsed)
                                        }
                                    }
                                    ValueBox {
                                        value: workspace.selectedVectorCornerRadii[2].toString()
                                        bindValue: true
                                        suffix: "BR"
                                        Layout.fillWidth: false
                                        editable: !workspace.selectedLocked && !workspace.operationsBlocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            var radii = workspace.selectedVectorCornerRadii
                                            if (!isNaN(parsed)) workspace.setSelectedVectorCornerRadii(radii[0], radii[1], parsed, radii[3])
                                        }
                                    }
                                }
                            }
                        }
                    }

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: selectedLayer < 0

                        Column {
                            anchors.centerIn: parent
                            spacing: 8
                            AppIcon { anchors.horizontalCenter: parent.horizontalCenter; iconName: AppIcons.layers; iconSize: 22; iconColor: Theme.textMuted }
                            BodyLabel { text: "无选中图层"; color: Theme.textMuted }
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
                    Rectangle { width: 6; height: 6; radius: 3; color: !window.hasOpenDocument ? Theme.textMuted : (workspace.busy ? Theme.amber : Theme.success); anchors.verticalCenter: parent.verticalCenter }
                    TinyLabel { text: window.hasOpenDocument ? workspace.statusMessage : "没有打开的文档"; color: Theme.textSecondary; height: 28 }
                }
                Divider { Layout.preferredHeight: 14; visible: window.hasOpenDocument }
                TinyLabel { text: "RGBA / sRGB IEC61966-2.1"; height: 28; visible: window.hasOpenDocument }
                Divider { Layout.preferredHeight: 14; visible: window.hasOpenDocument }
                TinyLabel { text: "X " + workspace.selectedX + "  ·  Y " + workspace.selectedY; height: 28; visible: window.hasOpenDocument }

                Item { Layout.fillWidth: true }

                Row {
                    spacing: 5
                    enabled: window.hasOpenDocument
                    opacity: enabled ? 1 : 0.32
                    IconButton {
                        iconName: AppIcons.zoomOut; tooltip: "缩小"; buttonSize: 24
                        onClicked: workspace.setZoomFactor(workspace.zoomFactor / 1.1)
                    }
                    Rectangle {
                        width: 92
                        height: 4
                        anchors.verticalCenter: parent.verticalCenter
                        radius: 2
                        color: Theme.borderStrong
                        Rectangle { width: parent.width * Math.log(workspace.zoomFactor / 0.1) / Math.log(100); height: 4; radius: 2; color: Theme.accent }
                        Rectangle { x: parent.width * Math.log(workspace.zoomFactor / 0.1) / Math.log(100) - 6; anchors.verticalCenter: parent.verticalCenter; width: 12; height: 12; radius: 6; color: Theme.textPrimary; border.width: 2; border.color: Theme.accentPressed }
                    }
                    IconButton {
                        iconName: AppIcons.zoomIn; tooltip: "放大"; buttonSize: 24
                        onClicked: workspace.setZoomFactor(workspace.zoomFactor * 1.1)
                    }
                                    TinyLabel {
                                        width: 42
                                        text: Math.round(workspace.zoomFactor * 100) + "%"
                                        color: fitZoomMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                                        height: 28
                                        horizontalAlignment: Text.AlignRight
                                        MouseArea {
                                            id: fitZoomMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: workspace.resetView()
                                        }
                                    }
                                }
            }

            Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top }
        }
    }
}
