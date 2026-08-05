import QtQuick
import QtQuick.Controls
import QtQuick.Dialogs
import QtQuick.Layouts
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

    property int selectedLayer: workspace.selectedLayerIndex
    property int activeTool: 0
    property real zoomValue: 0.78
    property int inspectorTab: 0
    property bool randomTransformEnabled: true
    property string toastMessage: ""
    property string activeLayerName: workspace.selectedLayerName
    property bool layerShortcutsEnabled: !selectedTextEditor.editing && !workspace.operationsBlocked

    function showToast(message) {
        toastMessage = message
        toast.opacity = 1
        toastTimer.restart()
    }

    Connections {
        target: workspace
        function onToastRequested(message) { showToast(message) }
        function onSelectionChanged() { selectedTextEditor.releaseFocus() }
    }

    Shortcut {
        sequence: "Ctrl+D"
        enabled: window.layerShortcutsEnabled && workspace.canDuplicateLayer
        onActivated: workspace.duplicateSelectedLayer()
    }

    Shortcut {
        sequence: "Ctrl+["
        enabled: window.layerShortcutsEnabled && workspace.canMoveLayerBackward
        onActivated: workspace.moveSelectedLayer("backward")
    }

    Shortcut {
        sequence: "Ctrl+]"
        enabled: window.layerShortcutsEnabled && workspace.canMoveLayerForward
        onActivated: workspace.moveSelectedLayer("forward")
    }

    FileDialog {
        id: openDialog
        title: "打开批图王项目"
        fileMode: FileDialog.OpenFile
        nameFilters: ["批图王项目 (*.cmp)"]
        onAccepted: workspace.openDocument(selectedFile.toString())
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

    component ExportField: Rectangle {
        id: exportField
        property alias text: exportInput.text
        property string placeholder: ""
        property bool readOnly: false
        signal committed(string value)

        implicitHeight: 36
        radius: Theme.radiusSmall
        color: Theme.bgControl
        border.width: 1
        border.color: exportInput.activeFocus ? Theme.accent : Theme.borderStrong

        TextInput {
            id: exportInput
            anchors.fill: parent
            anchors.leftMargin: 10
            anchors.rightMargin: 10
            color: Theme.textPrimary
            selectionColor: Theme.accentPressed
            selectedTextColor: Theme.textPrimary
            font.family: Theme.bodyFont
            font.pixelSize: 12
            verticalAlignment: TextInput.AlignVCenter
            readOnly: exportField.readOnly
            selectByMouse: true
            clip: true
            onEditingFinished: exportField.committed(text)

            Text {
                anchors.fill: parent
                text: exportField.placeholder
                visible: exportInput.text.length === 0 && !exportInput.activeFocus
                color: Theme.textMuted
                font: exportInput.font
                verticalAlignment: Text.AlignVCenter
            }
        }
    }

    component ExportButton: Rectangle {
        id: exportButton
        property string label: ""
        property string glyph: ""
        property bool primary: false
        property bool destructive: false
        signal clicked()

        implicitHeight: 38
        radius: Theme.radiusSmall
        color: {
            if (!enabled) return Theme.bgControl
            if (buttonMouse.pressed) return destructive ? "#b94d45" : (primary ? Theme.accentPressed : Theme.bgHover)
            if (buttonMouse.containsMouse) return destructive ? "#e56f65" : (primary ? Theme.accentHover : Theme.bgHover)
            return destructive ? Theme.coral : (primary ? Theme.accent : Theme.bgControl)
        }
        border.width: primary || destructive ? 0 : 1
        border.color: Theme.borderStrong
        opacity: enabled ? 1 : 0.42

        Row {
            anchors.centerIn: parent
            spacing: 8
            AppIcon {
                glyph: exportButton.glyph
                iconSize: 14
                iconColor: exportButton.primary || exportButton.destructive ? "#09251d" : Theme.textPrimary
                height: 20
            }
            Text {
                text: exportButton.label
                color: exportButton.primary || exportButton.destructive ? "#09251d" : Theme.textPrimary
                font.family: Theme.bodyFont
                font.pixelSize: 12
                font.weight: Font.DemiBold
                height: 20
                verticalAlignment: Text.AlignVCenter
            }
        }

        MouseArea {
            id: buttonMouse
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
            onClicked: exportButton.clicked()
        }
    }

    component ContentTextEditor: Rectangle {
        id: textEditorRoot
        property string value: ""
        property string placeholder: ""
        property int contextIndex: -1
        property int editingIndex: -1
        readonly property bool editing: contentEditor.activeFocus
        signal committed(string value, int contextIndex)

        function releaseFocus() {
            if (contentEditor.activeFocus)
                contentEditor.focus = false
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
                restoreMode: Binding.RestoreBindingOrValue
            }
        }
    }

    Drawer {
        id: batchExportDrawer
        objectName: "batchExportDrawer"
        edge: Qt.RightEdge
        width: Math.min(420, Math.max(380, window.width * 0.28))
        height: window.height
        modal: true
        dim: true
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
        padding: 0

        Overlay.modal: Rectangle { color: "#990a0c0d" }
        background: Rectangle {
            color: Theme.bgPanel
            border.width: 1
            border.color: Theme.borderStrong
        }

        contentItem: Item {
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: 22
                spacing: 0

                RowLayout {
                    Layout.fillWidth: true
                    Layout.preferredHeight: 46
                    spacing: 12

                    Rectangle {
                        width: 32
                        height: 32
                        radius: Theme.radiusSmall
                        color: Theme.accentSoft
                        AppIcon { anchors.centerIn: parent; glyph: "\uEDE1"; iconSize: 16; iconColor: Theme.accent }
                    }
                    Column {
                        Layout.fillWidth: true
                        spacing: 2
                        Text { text: "批量导出"; color: Theme.textPrimary; font.family: Theme.displayFont; font.pixelSize: 17; font.weight: Font.DemiBold }
                        TinyLabel { text: workspace.documentTitle; color: Theme.textMuted }
                    }
                    IconButton { glyph: "\uE711"; tooltip: "关闭"; buttonSize: 30; onClicked: batchExportDrawer.close() }
                }

                Divider { Layout.fillWidth: true; Layout.topMargin: 10; Layout.bottomMargin: 18 }

                Flickable {
                    Layout.fillWidth: true
                    Layout.fillHeight: true
                    contentWidth: width
                    contentHeight: exportForm.height
                    clip: true
                    boundsBehavior: Flickable.StopAtBounds

                    Column {
                        id: exportForm
                        width: parent.width
                        spacing: 18
                        enabled: !batchExport.running

                        Column {
                            width: parent.width
                            spacing: 8
                            BodyLabel { text: "输出目录"; color: Theme.textSecondary }
                            RowLayout {
                                width: parent.width
                                spacing: 8
                                ExportField {
                                    Layout.fillWidth: true
                                    text: batchExport.outputDirectory
                                    placeholder: "选择文件夹"
                                    readOnly: true
                                }
                                IconButton {
                                    glyph: "\uE8B7"
                                    tooltip: "选择输出目录"
                                    buttonSize: 36
                                    active: true
                                    onClicked: outputFolderDialog.open()
                                }
                            }
                        }

                        RowLayout {
                            width: parent.width
                            spacing: 12
                            Column {
                                Layout.fillWidth: true
                                spacing: 8
                                BodyLabel { text: "生成数量"; color: Theme.textSecondary }
                                ExportField {
                                    width: parent.width
                                    text: String(batchExport.count)
                                    placeholder: "12"
                                    onCommitted: value => batchExport.count = Math.max(0, parseInt(value) || 0)
                                }
                            }
                            Column {
                                Layout.fillWidth: true
                                spacing: 8
                                BodyLabel { text: "起始序号"; color: Theme.textSecondary }
                                ExportField { width: parent.width; text: "1"; readOnly: true }
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: 8
                            BodyLabel { text: "文件名模板"; color: Theme.textSecondary }
                            ExportField {
                                width: parent.width
                                text: batchExport.filenameTemplate
                                placeholder: "image_{number:04d}"
                                onCommitted: value => batchExport.filenameTemplate = value
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: 8
                            BodyLabel { text: "图像格式"; color: Theme.textSecondary }
                            Row {
                                width: parent.width
                                height: 36
                                spacing: 4
                                Repeater {
                                    model: ["png", "jpg", "webp"]
                                    delegate: Rectangle {
                                        required property string modelData
                                        width: (exportForm.width - 8) / 3
                                        height: 36
                                        radius: Theme.radiusSmall
                                        color: batchExport.fileFormat === modelData ? Theme.accentSoft : Theme.bgControl
                                        border.width: 1
                                        border.color: batchExport.fileFormat === modelData ? Theme.accentPressed : Theme.borderStrong
                                        Text {
                                            anchors.centerIn: parent
                                            text: modelData.toUpperCase()
                                            color: batchExport.fileFormat === modelData ? Theme.accent : Theme.textSecondary
                                            font.family: Theme.bodyFont
                                            font.pixelSize: 11
                                            font.weight: Font.DemiBold
                                        }
                                        MouseArea {
                                            anchors.fill: parent
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: batchExport.fileFormat = parent.modelData
                                        }
                                    }
                                }
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 48
                            radius: Theme.radiusSmall
                            color: Theme.bgRaised
                            border.width: 1
                            border.color: Theme.border
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 10
                                BodyLabel { text: "避免重复组合"; color: Theme.textPrimary; Layout.fillWidth: true }
                                ToggleSwitch {
                                    checked: batchExport.avoidDuplicates
                                    onToggled: checkedValue => batchExport.avoidDuplicates = checkedValue
                                }
                            }
                        }

                        Rectangle {
                            width: parent.width
                            height: 58
                            radius: Theme.radiusSmall
                            color: Theme.bgBar
                            border.width: 1
                            border.color: Theme.border
                            RowLayout {
                                anchors.fill: parent
                                anchors.leftMargin: 12
                                anchors.rightMargin: 12
                                Column {
                                    spacing: 3
                                    TinyLabel { text: "预计产出" }
                                    BodyLabel { text: batchExport.count + " 张"; color: Theme.textPrimary }
                                }
                                Item { Layout.fillWidth: true }
                                Column {
                                    spacing: 3
                                    TinyLabel { text: "预计耗时"; horizontalAlignment: Text.AlignRight; width: parent.width }
                                    BodyLabel { text: batchExport.estimatedTime; color: Theme.textPrimary }
                                }
                            }
                        }
                    }
                }

                ColumnLayout {
                    Layout.fillWidth: true
                    Layout.topMargin: 18
                    spacing: 10

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: batchExport.errorMessage.length > 0 ? 60 : 48
                        radius: Theme.radiusSmall
                        color: batchExport.errorMessage.length > 0 ? "#35201f" : (batchExport.succeeded ? "#173126" : Theme.bgRaised)
                        border.width: 1
                        border.color: batchExport.errorMessage.length > 0 ? "#70413d" : (batchExport.succeeded ? "#28583e" : Theme.border)

                        RowLayout {
                            anchors.fill: parent
                            anchors.margins: 10
                            spacing: 9
                            AppIcon {
                                glyph: batchExport.errorMessage.length > 0 ? "\uEA39" : (batchExport.succeeded ? "\uE73E" : "\uE9D9")
                                iconSize: 15
                                iconColor: batchExport.errorMessage.length > 0 ? Theme.coral : (batchExport.succeeded ? Theme.success : Theme.accent)
                            }
                            Column {
                                Layout.fillWidth: true
                                spacing: 2
                                BodyLabel { text: batchExport.statusText; color: Theme.textPrimary }
                                TinyLabel {
                                    width: parent.width
                                    text: batchExport.errorMessage.length > 0 ? batchExport.errorMessage : batchExport.stage
                                    color: batchExport.errorMessage.length > 0 ? "#e7a09a" : Theme.textMuted
                                    elide: Text.ElideRight
                                }
                            }
                            TinyLabel {
                                visible: batchExport.running || batchExport.succeeded || batchExport.canceled
                                text: batchExport.current + " / " + batchExport.total
                                color: Theme.textSecondary
                            }
                        }
                    }

                    Rectangle {
                        Layout.fillWidth: true
                        Layout.preferredHeight: 5
                        visible: batchExport.running || batchExport.current > 0
                        radius: 2
                        color: Theme.borderStrong
                        Rectangle {
                            width: parent.width * batchExport.progress
                            height: parent.height
                            radius: 2
                            color: batchExport.canceled ? Theme.amber : Theme.accent
                        }
                    }

                    TinyLabel {
                        Layout.fillWidth: true
                        visible: batchExport.lastFile.length > 0
                        text: "最近文件  " + batchExport.lastFile
                        elide: Text.ElideMiddle
                        color: Theme.textMuted
                    }

                    RowLayout {
                        Layout.fillWidth: true
                        spacing: 8
                        ExportButton {
                            Layout.fillWidth: true
                            label: "打开目录"
                            glyph: "\uE8B7"
                            enabled: batchExport.outputDirectory.length > 0
                            onClicked: batchExport.openOutputDirectory()
                        }
                        ExportButton {
                            Layout.fillWidth: true
                            label: batchExport.running ? "取消导出" : (batchExport.succeeded ? "再次导出" : "开始导出")
                            glyph: batchExport.running ? "\uE71A" : "\uEDE1"
                            primary: !batchExport.running
                            destructive: batchExport.running
                            onClicked: batchExport.running ? batchExport.cancelExport() : batchExport.startExport()
                        }
                    }
                }
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

                IconButton { glyph: "\uE8E5"; tooltip: "打开项目"; enabled: !workspace.operationsBlocked; onClicked: openDialog.open() }
                IconButton {
                    glyph: "\uE74E"
                    tooltip: "保存"
                    enabled: !workspace.operationsBlocked
                    onClicked: workspace.hasFilePath ? workspace.saveDocument() : saveDialog.open()
                }
                Divider { Layout.preferredHeight: 24; Layout.leftMargin: 3; Layout.rightMargin: 3 }
                IconButton { glyph: "\uE7A7"; tooltip: "撤销"; enabled: workspace.canUndo && !workspace.operationsBlocked; onClicked: workspace.undo() }
                IconButton { glyph: "\uE7A6"; tooltip: "重做"; enabled: workspace.canRedo && !workspace.operationsBlocked; onClicked: workspace.redo() }
                Divider { Layout.preferredHeight: 24; Layout.leftMargin: 3; Layout.rightMargin: 3 }

                Rectangle {
                    Layout.preferredWidth: 106
                    Layout.preferredHeight: 32
                    radius: Theme.radiusSmall
                    color: addImageMouse.containsMouse ? Theme.bgHover : Theme.bgControl
                    border.width: 1
                    border.color: Theme.borderStrong
                    opacity: workspace.operationsBlocked ? 0.38 : 1
                    Row {
                        anchors.centerIn: parent
                        spacing: 7
                        AppIcon { glyph: "\uE91B"; iconSize: 14; iconColor: Theme.textPrimary; height: 20 }
                        BodyLabel { text: "添加图片"; color: Theme.textPrimary; height: 20 }
                    }
                    MouseArea { id: addImageMouse; anchors.fill: parent; enabled: !workspace.operationsBlocked; hoverEnabled: true; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: imageDialog.open() }
                }

                IconButton { glyph: "\uE8D2"; tooltip: "添加文字"; enabled: !workspace.operationsBlocked; onClicked: workspace.addTextLayer() }
                IconButton { glyph: "\uE8B7"; tooltip: "添加素材文件夹"; enabled: !workspace.operationsBlocked; onClicked: imageFolderDialog.open() }
                IconButton { glyph: "\uF158"; tooltip: "添加异形（后续接入）"; enabled: false }
                Divider { Layout.preferredHeight: 24; Layout.leftMargin: 3; Layout.rightMargin: 3 }
                IconButton {
                    glyph: "\uE74B"; tooltip: "左对齐"
                    enabled: workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked
                    onClicked: workspace.alignSelected("left")
                }
                IconButton {
                    glyph: "\uE74A"; tooltip: "水平居中"
                    enabled: workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked
                    onClicked: workspace.alignSelected("hcenter")
                }
                IconButton {
                    glyph: "\uE73F"; tooltip: "垂直居中"
                    enabled: workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked
                    onClicked: workspace.alignSelected("vcenter")
                }

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
                    opacity: workspace.operationsBlocked ? 0.38 : 1
                    MouseArea { anchors.fill: parent; enabled: !workspace.operationsBlocked; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: workspace.renderPreviewNow() }
                }

                IconButton {
                    glyph: "\uE159"
                    tooltip: "导出当前画面"
                    buttonSize: 32
                    enabled: !workspace.operationsBlocked
                    onClicked: exportDialog.open()
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
                        Text { text: batchExport.running ? "查看进度" : "批量导出"; color: "#09251d"; font.family: Theme.bodyFont; font.pixelSize: 12; font.weight: Font.DemiBold; height: 20; verticalAlignment: Text.AlignVCenter }
                    }
                    MouseArea { id: exportMouse; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: batchExportDrawer.open() }
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
                        Rectangle { width: 6; height: 6; radius: 3; color: Theme.amber; visible: workspace.isModified; anchors.verticalCenter: parent.verticalCenter }
                        BodyLabel { text: workspace.documentTitle; color: Theme.textPrimary; height: 22 }
                        AppIcon { glyph: "\uE711"; iconSize: 10; height: 22 }
                    }
                }

                IconButton { glyph: "\uE710"; tooltip: "新建文档"; buttonSize: 36; onClicked: workspace.newDocument(1080, 1350) }
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
                        IconButton { glyph: "\uE710"; tooltip: "添加图片图层"; buttonSize: 28; onClicked: imageDialog.open() }
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
                                onClicked: workspace.toggleLayerVisible(layerDelegate.index)
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
                                onClicked: workspace.toggleLayerLocked(layerDelegate.index)
                            }

                            MouseArea {
                                id: layerMouse
                                anchors.fill: parent
                                anchors.leftMargin: 38
                                anchors.rightMargin: 38
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: workspace.selectLayer(layerDelegate.index)
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
                            IconButton { glyph: "\uE710"; tooltip: "添加图片图层"; buttonSize: 28; enabled: !workspace.operationsBlocked; onClicked: imageDialog.open() }
                            IconButton {
                                glyph: "\uE8C8"
                                tooltip: "复制图层 · Ctrl+D"
                                buttonSize: 28
                                enabled: workspace.canDuplicateLayer
                                onClicked: workspace.duplicateSelectedLayer()
                            }
                            IconButton {
                                glyph: "\uE70E"
                                tooltip: "后移一层 · Ctrl+["
                                buttonSize: 28
                                enabled: workspace.canMoveLayerBackward
                                onClicked: workspace.moveSelectedLayer("backward")
                            }
                            IconButton {
                                glyph: "\uE70D"
                                tooltip: "前移一层 · Ctrl+]"
                                buttonSize: 28
                                enabled: workspace.canMoveLayerForward
                                onClicked: workspace.moveSelectedLayer("forward")
                            }
                            IconButton {
                                glyph: "\uE74D"
                                tooltip: "删除图层"
                                buttonSize: 28
                                enabled: workspace.selectedLayerIndex >= 0 && !workspace.selectedLocked && !workspace.operationsBlocked
                                onClicked: workspace.deleteSelectedLayer()
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
                property real actualScale: Math.max(0.05, fitScale * (zoomValue / 0.78))
                property bool transformActive: false
                property string transformMode: ""
                property real gestureStartMouseX: 0
                property real gestureStartMouseY: 0
                property real gestureStartX: 0
                property real gestureStartY: 0
                property real gestureStartWidth: 1
                property real gestureStartHeight: 1
                property real transientX: workspace.selectedX
                property real transientY: workspace.selectedY
                property real transientWidth: Math.max(1, workspace.selectedWidth)
                property real transientHeight: Math.max(1, workspace.selectedHeight)

                function selectedLocalPoint(canvasX, canvasY) {
                    var width = Math.max(1, workspace.selectedWidth)
                    var height = Math.max(1, workspace.selectedHeight)
                    var centerX = workspace.selectedX + width / 2
                    var centerY = workspace.selectedY + height / 2
                    var radians = workspace.selectedRotation * Math.PI / 180
                    var offsetX = canvasX - centerX
                    var offsetY = canvasY - centerY
                    return {
                        "x": Math.cos(radians) * offsetX + Math.sin(radians) * offsetY + width / 2,
                        "y": -Math.sin(radians) * offsetX + Math.cos(radians) * offsetY + height / 2
                    }
                }

                function handleAt(canvasX, canvasY) {
                    if (workspace.selectedLayerIndex < 0 || workspace.selectedLocked || Math.abs(workspace.selectedRotation) > 0.001)
                        return ""
                    var point = selectedLocalPoint(canvasX, canvasY)
                    var width = Math.max(1, workspace.selectedWidth)
                    var height = Math.max(1, workspace.selectedHeight)
                    var tolerance = 10 / actualScale
                    var nearLeft = Math.abs(point.x) <= tolerance
                    var nearRight = Math.abs(point.x - width) <= tolerance
                    var nearTop = Math.abs(point.y) <= tolerance
                    var nearBottom = Math.abs(point.y - height) <= tolerance
                    if (nearLeft && nearTop) return "nw"
                    if (nearRight && nearTop) return "ne"
                    if (nearLeft && nearBottom) return "sw"
                    if (nearRight && nearBottom) return "se"
                    return ""
                }

                function selectedContains(canvasX, canvasY) {
                    if (workspace.selectedLayerIndex < 0)
                        return false
                    var point = selectedLocalPoint(canvasX, canvasY)
                    return point.x >= 0 && point.x <= workspace.selectedWidth
                            && point.y >= 0 && point.y <= workspace.selectedHeight
                }

                function pointerCursor(canvasX, canvasY) {
                    var handle = handleAt(canvasX, canvasY)
                    if (handle === "nw" || handle === "se") return Qt.SizeFDiagCursor
                    if (handle === "ne" || handle === "sw") return Qt.SizeBDiagCursor
                    if (!workspace.selectedLocked && selectedContains(canvasX, canvasY)) return Qt.OpenHandCursor
                    return Qt.ArrowCursor
                }

                function beginTransform(mode, canvasX, canvasY) {
                    transformMode = mode
                    gestureStartMouseX = canvasX
                    gestureStartMouseY = canvasY
                    gestureStartX = workspace.selectedX
                    gestureStartY = workspace.selectedY
                    gestureStartWidth = Math.max(1, workspace.selectedWidth)
                    gestureStartHeight = Math.max(1, workspace.selectedHeight)
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
                    var minimumSize = 16
                    if (transformMode === "move") {
                        transientX = Math.max(0, Math.min(safeCanvasWidth - gestureStartWidth, gestureStartX + deltaX))
                        transientY = Math.max(0, Math.min(safeCanvasHeight - gestureStartHeight, gestureStartY + deltaY))
                        return
                    }

                    var right = gestureStartX + gestureStartWidth
                    var bottom = gestureStartY + gestureStartHeight
                    if (transformMode === "nw" || transformMode === "sw") {
                        transientX = Math.max(0, Math.min(right - minimumSize, gestureStartX + deltaX))
                        transientWidth = right - transientX
                    } else {
                        transientWidth = Math.max(minimumSize, Math.min(safeCanvasWidth - gestureStartX, gestureStartWidth + deltaX))
                    }
                    if (transformMode === "nw" || transformMode === "ne") {
                        transientY = Math.max(0, Math.min(bottom - minimumSize, gestureStartY + deltaY))
                        transientHeight = bottom - transientY
                    } else {
                        transientHeight = Math.max(minimumSize, Math.min(safeCanvasHeight - gestureStartY, gestureStartHeight + deltaY))
                    }
                }

                function commitTransform() {
                    if (!transformActive)
                        return
                    var finalX = Math.round(transientX)
                    var finalY = Math.round(transientY)
                    var finalWidth = Math.round(transientWidth)
                    var finalHeight = Math.round(transientHeight)
                    transformActive = false
                    transformMode = ""
                    workspace.applySelectedGeometry(finalX, finalY, finalWidth, finalHeight)
                }

                function cancelTransform() {
                    transformActive = false
                    transformMode = ""
                }

                WheelHandler {
                    target: null
                    onWheel: event => {
                        var direction = event.angleDelta.y > 0 ? 1 : -1
                        zoomValue = Math.max(0.35, Math.min(2.0, zoomValue + direction * 0.05))
                        event.accepted = true
                    }
                }

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
                    width: canvasWorkspace.safeCanvasWidth * canvasWorkspace.actualScale
                    height: canvasWorkspace.safeCanvasHeight * canvasWorkspace.actualScale
                    anchors.centerIn: parent

                    Rectangle {
                        id: artboard
                        objectName: "artboard"
                        width: canvasWorkspace.safeCanvasWidth
                        height: canvasWorkspace.safeCanvasHeight
                        scale: canvasWorkspace.actualScale
                        transformOrigin: Item.TopLeft
                        color: "#f4f3ef"
                        border.width: 1
                        border.color: "#5c6260"

                        Image {
                            id: documentPreview
                            anchors.fill: parent
                            source: workspace.previewSource
                            fillMode: Image.PreserveAspectFit
                            asynchronous: true
                            cache: false
                            smooth: true
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
                                var handle = canvasWorkspace.handleAt(mouse.x, mouse.y)
                                if (handle.length > 0) {
                                    canvasWorkspace.beginTransform(handle, mouse.x, mouse.y)
                                    return
                                }
                                var selectedIndex = workspace.selectLayerAt(mouse.x, mouse.y)
                                if (selectedIndex >= 0 && !workspace.selectedLocked)
                                    canvasWorkspace.beginTransform("move", mouse.x, mouse.y)
                            }
                            onPositionChanged: mouse => {
                                if (pressed)
                                    canvasWorkspace.updateTransform(mouse.x, mouse.y)
                            }
                            onReleased: canvasWorkspace.commitTransform()
                            onCanceled: canvasWorkspace.cancelTransform()
                        }

                        Rectangle {
                            id: selectionBox
                            visible: workspace.selectedLayerIndex >= 0
                            x: canvasWorkspace.transformActive ? canvasWorkspace.transientX : workspace.selectedX
                            y: canvasWorkspace.transformActive ? canvasWorkspace.transientY : workspace.selectedY
                            width: canvasWorkspace.transformActive ? canvasWorkspace.transientWidth : Math.max(1, workspace.selectedWidth)
                            height: canvasWorkspace.transformActive ? canvasWorkspace.transientHeight : Math.max(1, workspace.selectedHeight)
                            rotation: workspace.selectedCanRotate ? workspace.selectedRotation : 0
                            transformOrigin: Item.Center
                            color: canvasWorkspace.transformActive ? "#153fd2aa" : "transparent"
                            border.width: Math.max(1, 1.5 / canvasWorkspace.actualScale)
                            border.color: workspace.selectedLocked ? Theme.textMuted : Theme.accent

                            Repeater {
                                model: [
                                    {"x": 0, "y": 0}, {"x": parent.width, "y": 0},
                                    {"x": 0, "y": parent.height}, {"x": parent.width, "y": parent.height}
                                ]
                                delegate: Rectangle {
                                    required property var modelData
                                    visible: !workspace.selectedLocked && Math.abs(workspace.selectedRotation) <= 0.001
                                    width: 8 / canvasWorkspace.actualScale
                                    height: width
                                    radius: width / 2
                                    x: modelData.x - width / 2
                                    y: modelData.y - height / 2
                                    color: "#f4f7f5"
                                    border.width: Math.max(1, 1 / canvasWorkspace.actualScale)
                                    border.color: Theme.accentPressed
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
                                color: "#e91b2021"
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
                    }
                }

                BusyIndicator {
                    anchors.centerIn: parent
                    running: workspace.busy
                    visible: running
                    palette.accent: Theme.accent
                }

                Column {
                    anchors.centerIn: parent
                    spacing: 8
                    visible: layerModel.rowCount() === 0 && !workspace.busy
                    AppIcon { anchors.horizontalCenter: parent.horizontalCenter; glyph: "\uE91B"; iconSize: 24; iconColor: Theme.textMuted }
                    BodyLabel { text: "空白画布"; color: Theme.textMuted }
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
                            TinyLabel { text: selectedLayer >= 0 ? workspace.selectedLayerType + "图层  ·  #" + (selectedLayer + 1) : "图层"; height: 15 }
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
                                enabled: index === 0
                                opacity: enabled ? 1 : 0.42
                                color: inspectorTab === index ? Theme.bgRaised : "transparent"
                                Text { anchors.centerIn: parent; text: modelData; color: inspectorTab === index ? Theme.textPrimary : Theme.textMuted; font.family: Theme.bodyFont; font.pixelSize: 11; font.weight: inspectorTab === index ? Font.DemiBold : Font.Normal }
                                Rectangle { anchors.left: parent.left; anchors.right: parent.right; anchors.bottom: parent.bottom; height: 2; color: inspectorTab === index ? Theme.accent : "transparent" }
                                MouseArea { anchors.fill: parent; enabled: parent.enabled; cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor; onClicked: inspectorTab = index }
                            }
                        }
                    }

                    ScrollView {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: selectedLayer >= 0
                        clip: true
                        ScrollBar.horizontal.policy: ScrollBar.AlwaysOff

                        Column {
                            width: inspector.width
                            visible: inspectorTab === 0

                            PropertySection {
                                width: parent.width
                                title: "内容源"
                                summary: workspace.selectedImageSourceIsFolder ? workspace.selectedImageSourceCount + " 张素材" : "单张图片"
                                visible: workspace.selectedIsImageLayer

                                InspectorRow {
                                    label: "模式"
                                    BodyLabel {
                                        text: workspace.selectedImageSourceIsFolder ? "素材文件夹" : "单文件"
                                        color: workspace.selectedImageSourceIsFolder ? Theme.accent : Theme.textPrimary
                                        Layout.fillWidth: true
                                    }
                                    TinyLabel { text: workspace.selectedImageSourceCount + " 张" }
                                }
                                InspectorRow {
                                    label: "路径"
                                    Rectangle {
                                        Layout.fillWidth: true
                                        Layout.preferredHeight: 30
                                        radius: Theme.radiusSmall
                                        color: Theme.bgControl
                                        border.width: 1
                                        border.color: Theme.borderStrong
                                        Text {
                                            anchors.left: parent.left
                                            anchors.right: parent.right
                                            anchors.leftMargin: 9
                                            anchors.rightMargin: 9
                                            anchors.verticalCenter: parent.verticalCenter
                                            text: workspace.selectedImageSource || "未设置"
                                            color: workspace.selectedImageSource ? Theme.textSecondary : Theme.textMuted
                                            font.family: Theme.bodyFont
                                            font.pixelSize: 10
                                            elide: Text.ElideMiddle
                                        }
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
                                        glyph: "\uE72C"
                                        tooltip: "换一张素材"
                                        buttonSize: 30
                                        enabled: workspace.selectedImageSourceIsFolder && workspace.selectedImageSourceCount > 1 && !workspace.selectedLocked
                                        onClicked: workspace.showNextSelectedImage()
                                    }
                                }
                                InspectorRow {
                                    label: "替换"
                                    ExportButton {
                                        Layout.fillWidth: true
                                        label: "图片"
                                        glyph: "\uE91B"
                                        enabled: !workspace.selectedLocked
                                        onClicked: replaceImageDialog.open()
                                    }
                                    ExportButton {
                                        Layout.fillWidth: true
                                        label: "文件夹"
                                        glyph: "\uE8B7"
                                        enabled: !workspace.selectedLocked
                                        onClicked: replaceImageFolderDialog.open()
                                    }
                                }
                            }

                            PropertySection {
                                width: parent.width
                                title: "文字内容"
                                summary: workspace.selectedTextBindingEnabled ? workspace.selectedTextCandidateCount + " 条候选" : "整段排版"
                                visible: workspace.selectedIsTextLayer

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

                                Row {
                                    width: parent.width
                                    height: 32
                                    spacing: 4
                                    Repeater {
                                        model: [
                                            { label: "按行随机", enabled: true },
                                            { label: "整段排版", enabled: false }
                                        ]
                                        delegate: Rectangle {
                                            required property var modelData
                                            width: (parent.width - 4) / 2
                                            height: 32
                                            radius: Theme.radiusSmall
                                            color: workspace.selectedTextBindingEnabled === modelData.enabled ? Theme.accentSoft : Theme.bgControl
                                            border.width: 1
                                            border.color: workspace.selectedTextBindingEnabled === modelData.enabled ? Theme.accentPressed : Theme.borderStrong
                                            Text {
                                                anchors.centerIn: parent
                                                text: parent.modelData.label
                                                color: workspace.selectedTextBindingEnabled === parent.modelData.enabled ? Theme.accent : Theme.textSecondary
                                                font.family: Theme.bodyFont
                                                font.pixelSize: 11
                                                font.weight: Font.DemiBold
                                            }
                                            MouseArea {
                                                anchors.fill: parent
                                                enabled: !workspace.selectedLocked
                                                cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
                                                onClicked: workspace.setSelectedTextBindingEnabled(parent.modelData.enabled)
                                            }
                                        }
                                    }
                                }

                                InspectorRow {
                                    label: workspace.selectedTextBindingEnabled ? "候选" : "段落"
                                    BodyLabel {
                                        text: workspace.selectedTextBindingEnabled ? workspace.selectedTextCandidateCount + " 条文案" : "1 条文案"
                                        color: Theme.textSecondary
                                        Layout.fillWidth: true
                                    }
                                    ValueBox {
                                        value: workspace.selectedTextFontSize.toString()
                                        bindValue: true
                                        suffix: "px"
                                        Layout.preferredWidth: 84
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => {
                                            var parsed = parseInt(value)
                                            if (!isNaN(parsed)) workspace.setSelectedTextFontSize(parsed)
                                        }
                                    }
                                }
                            }

                            PropertySection {
                                width: parent.width
                                title: "变换"
                                summary: "px / °"

                                InspectorRow {
                                    label: "名称"
                                    ValueBox {
                                        value: workspace.selectedLayerName; bindValue: true; Layout.fillWidth: true
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => workspace.setSelectedName(value)
                                    }
                                }
                                InspectorRow {
                                    label: "位置"
                                    ValueBox {
                                        value: workspace.selectedX.toString(); bindValue: true; suffix: "X"; Layout.fillWidth: true
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedX(parsed) }
                                    }
                                    ValueBox {
                                        value: workspace.selectedY.toString(); bindValue: true; suffix: "Y"; Layout.fillWidth: true
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedY(parsed) }
                                    }
                                }
                                InspectorRow {
                                    label: "尺寸"
                                    ValueBox {
                                        value: workspace.selectedWidth.toString(); bindValue: true; suffix: "W"; Layout.fillWidth: true
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedWidth(parsed) }
                                    }
                                    ValueBox {
                                        value: workspace.selectedHeight.toString(); bindValue: true; suffix: "H"; Layout.fillWidth: true
                                        editable: !workspace.selectedLocked
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedHeight(parsed) }
                                    }
                                }
                                InspectorRow {
                                    label: "旋转"
                                    ValueBox {
                                        value: (Math.round(workspace.selectedRotation * 10) / 10).toString(); bindValue: true; suffix: "°"; Layout.fillWidth: true
                                        editable: workspace.selectedCanRotate && !workspace.selectedLocked
                                        onValueCommitted: value => { var parsed = parseFloat(value); if (!isNaN(parsed)) workspace.setSelectedRotation(parsed) }
                                    }
                                    IconButton {
                                        glyph: "\uE72C"; tooltip: "重置旋转"; buttonSize: 30
                                        enabled: workspace.selectedCanRotate && !workspace.selectedLocked && Math.abs(workspace.selectedRotation) > 0.001
                                        onClicked: workspace.setSelectedRotation(0)
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
                                        Rectangle { width: parent.width * workspace.selectedOpacity / 100; height: parent.height; radius: 2; color: Theme.accent }
                                        Rectangle { x: parent.width * workspace.selectedOpacity / 100 - 7; anchors.verticalCenter: parent.verticalCenter; width: 14; height: 14; radius: 7; color: Theme.textPrimary; border.width: 2; border.color: Theme.accentPressed }
                                    }
                                    ValueBox {
                                        value: workspace.selectedOpacity.toString(); bindValue: true; suffix: "%"; Layout.preferredWidth: 66
                                        onValueCommitted: value => { var parsed = parseInt(value); if (!isNaN(parsed)) workspace.setSelectedOpacity(parsed) }
                                    }
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
                                visible: false

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
                                visible: false
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

                    Item {
                        Layout.fillWidth: true
                        Layout.fillHeight: true
                        visible: selectedLayer < 0

                        Column {
                            anchors.centerIn: parent
                            spacing: 8
                            AppIcon { anchors.horizontalCenter: parent.horizontalCenter; glyph: "\uE7C9"; iconSize: 22; iconColor: Theme.textMuted }
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
                    Rectangle { width: 6; height: 6; radius: 3; color: workspace.busy ? Theme.amber : Theme.success; anchors.verticalCenter: parent.verticalCenter }
                    TinyLabel { text: workspace.statusMessage; color: Theme.textSecondary; height: 28 }
                }
                Divider { Layout.preferredHeight: 14 }
                TinyLabel { text: "RGBA / sRGB IEC61966-2.1"; height: 28 }
                Divider { Layout.preferredHeight: 14 }
                TinyLabel { text: "X " + workspace.selectedX + "  ·  Y " + workspace.selectedY; height: 28 }

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
                                    TinyLabel {
                                        width: 42
                                        text: Math.round(zoomValue * 100) + "%"
                                        color: fitZoomMouse.containsMouse ? Theme.textPrimary : Theme.textSecondary
                                        height: 28
                                        horizontalAlignment: Text.AlignRight
                                        MouseArea {
                                            id: fitZoomMouse
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: zoomValue = 0.78
                                        }
                                    }
                                }
            }

            Divider { anchors.left: parent.left; anchors.right: parent.right; anchors.top: parent.top }
        }
    }
}
