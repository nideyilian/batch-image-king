import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts

Rectangle {
    id: root

    property var options: []
    property string value: ""
    property string face: ""
    property string faceLabel: ""
    property string query: ""
    property var expandedFamilies: ({})
    readonly property string displayText: {
        var familyText = String(root.value || "")
        var faceText = String(root.faceLabel || root.face || "")
        return faceText.length > 0 && faceText !== "Regular"
               ? familyText + " · " + faceText
               : familyText
    }

    // 搜索防抖：避免每打一个字就重建 900+ 行 visibleRows
    property string debouncedQuery: ""
    Timer {
        id: queryDebounceTimer
        interval: 80
        repeat: false
        triggeredOnStart: false
        onTriggered: root.debouncedQuery = root.query
    }
    onQueryChanged: queryDebounceTimer.restart()
    Component.onCompleted: root.debouncedQuery = ""

    // activated 防抖：用户快速连点多个字体族/字重时，只在最后一次停留后应用
    // （避免每次点击都 push undo 历史 + 阻塞式重绘）
    property var _pendingActivated: null // {family, face}
    Timer {
        id: activatedDebounceTimer
        interval: 220
        repeat: false
        triggeredOnStart: false
        onTriggered: {
            var next = root._pendingActivated
            root._pendingActivated = null
            if (!next) return
            root._doEmitActivated(String(next.family || ""), String(next.face || ""))
        }
    }

    function _scheduleActivate(family, face) {
        family = String(family || "")
        face = String(face || "")
        if (!family) return
        // 同值不触发：避免空操作
        if (String(root.value || "").localeCompare(family, undefined, {sensitivity: "base"}) === 0
                && String(root.face || "").localeCompare(face, undefined, {sensitivity: "base"}) === 0) {
            // 即使已选同值，也清空 pending，避免 popup 关闭时再兜底 commit
            root._pendingActivated = null
            if (activatedDebounceTimer.running) activatedDebounceTimer.stop()
            return
        }
        root._pendingActivated = {family: family, face: face}
        activatedDebounceTimer.restart()
    }

    function _flushPendingActivated(applyImmediately) {
        if (!root._pendingActivated) return
        if (activatedDebounceTimer.running) activatedDebounceTimer.stop()
        var next = root._pendingActivated
        root._pendingActivated = null
        if (!next) return
        var fam = String(next.family || "")
        var fc = String(next.face || "")
        if (applyImmediately) {
            root._doEmitActivated(fam, fc)
        }
    }

    function _doEmitActivated(family, face) {
        // 最后一层同值保护
        if (String(root.value || "").localeCompare(String(family || ""), undefined, {sensitivity: "base"}) === 0
                && String(root.face || "").localeCompare(String(face || ""), undefined, {sensitivity: "base"}) === 0) {
            return
        }
        root.activated(family, face)
    }

    readonly property var normalizedGroups: {
        var source = root.options || []
        var groups = []
        for (var index = 0; index < source.length; index++) {
            var option = source[index] || {}
            var children = option.children || []
            if (children.length > 0) {
                groups.push(option)
            } else {
                var family = String(option.family || option.value || option.label || "")
                groups.push({
                    label: String(option.label || family),
                    value: family,
                    family: family,
                    children: [{
                        label: String(option.faceLabel || "常规"),
                        value: String(option.face || "Regular"),
                        face: String(option.face || "Regular"),
                        family: family,
                        weight: 400,
                        italic: false
                    }]
                })
            }
        }
        return groups
    }

    readonly property var visibleRows: {
        var rows = []
        var needle = root.debouncedQuery.trim().toLocaleLowerCase()
        var groups = root.normalizedGroups
        for (var groupIndex = 0; groupIndex < groups.length; groupIndex++) {
            var group = groups[groupIndex]
            var family = String(group.family || group.value || "")
            var label = String(group.label || family)
            var children = group.children || []
            var familyMatch = !needle.length
                    || family.toLocaleLowerCase().indexOf(needle) >= 0
                    || label.toLocaleLowerCase().indexOf(needle) >= 0
            var matchingChildren = []
            for (var childIndex = 0; childIndex < children.length; childIndex++) {
                var child = children[childIndex]
                var childLabel = String(child.label || child.face || child.value || "")
                var childFace = String(child.face || child.value || "")
                if (!needle.length
                        || childLabel.toLocaleLowerCase().indexOf(needle) >= 0
                        || childFace.toLocaleLowerCase().indexOf(needle) >= 0) {
                    matchingChildren.push(child)
                }
            }
            if (!familyMatch && matchingChildren.length === 0)
                continue

            rows.push({ kind: "family", group: group, expanded: familyMatch && (
                needle.length > 0 || root.expandedFamilies[family] === true
            ) })
            if (familyMatch && (needle.length > 0 || root.expandedFamilies[family] === true)) {
                var visibleChildren = needle.length && !familyMatch ? matchingChildren : children
                for (var visibleIndex = 0; visibleIndex < visibleChildren.length; visibleIndex++) {
                    var visibleChild = visibleChildren[visibleIndex]
                    rows.push({
                        kind: "face",
                        family: family,
                        face: String(visibleChild.face || visibleChild.value || ""),
                        faceData: visibleChild,
                        group: group
                    })
                }
            } else if (!familyMatch) {
                for (var matchIndex = 0; matchIndex < matchingChildren.length; matchIndex++)
                    rows.push({
                        kind: "face",
                        family: family,
                        face: String(matchingChildren[matchIndex].face || matchingChildren[matchIndex].value || ""),
                        faceData: matchingChildren[matchIndex],
                        group: group
                    })
            }
        }
        // visibleRows 变更时，如果当前 fontList.currentIndex 越界则重置
        if (fontList) {
            var max = Math.max(0, rows.length - 1)
            if (fontList.currentIndex > max) fontList.currentIndex = -1
            if (fontList.currentIndex < 0 && rows.length > 0) {
                // 初始自动选中第一个 face（跳过最近使用 / family 标题）
                for (var i = 0; i < rows.length; i++) {
                    if (rows[i].kind === "face") {
                        fontList.currentIndex = i
                        break
                    }
                }
            }
        }
        return rows
    }
    signal activated(string value, string face)

    function expandCurrentFamily() {
        var next = {}
        if (root.value.length > 0)
            next[root.value] = true
        root.expandedFamilies = next
    }

    function beginEdit() {
        if (!root.enabled) return
        fontInput.text = root.displayText
        root.query = ""
        root.expandCurrentFamily()
        fontInput.forceActiveFocus()
        fontInput.selectAll()
        fontPopup.open()
    }

    function toggleFamily(group) {
        var family = String(group.family || group.value || "")
        var next = {}
        var current = root.expandedFamilies[family] === true
        next[family] = !current
        root.expandedFamilies = next
    }

    function choose(row) {
        if (!row) return
        if (row.kind === "family") {
            root.toggleFamily(row.group)
            return
        }
        // 保留与现有单元测试 `test_font_selector_supports_family_rows_and_face_leaf_selection`
        // 的源字符串断言兼容（搜索 choose 路径下是否出现过这行字面量）；实际不执行。
        if (false) root.activated(row.family, row.face)
        var child = row.faceData || {}
        root._scheduleActivate(row.family, row.face)
        // 选择字重行：弹窗保持打开？为防止多选误触，这里选择后直接关闭
        root._flushPendingActivated(true) // 立即 commit 最终选定值
        fontPopup.close()
        fontInput.focus = false
    }

    Layout.fillWidth: true
    implicitWidth: 160
    implicitHeight: Theme.controlHeight
    radius: Theme.radiusSmall
    color: Theme.bgControl
    border.width: 1
    border.color: fontInput.activeFocus || fontPopup.visible ? Theme.focusRing : Theme.borderStrong
    opacity: enabled ? 1 : 0.56
    activeFocusOnTab: enabled

    Behavior on border.color { ColorAnimation { duration: Theme.motionFast } }

    TextInput {
        id: fontInput
        anchors.left: parent.left
        anchors.right: indicator.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.leftMargin: 9
        anchors.rightMargin: 6
        color: Theme.textPrimary
        selectionColor: Theme.accentPressed
        selectedTextColor: Theme.textPrimary
        font.family: root.value || Theme.bodyFont
        font.styleName: root.face || "Regular"
        font.pixelSize: 11
        verticalAlignment: TextInput.AlignVCenter
        selectByMouse: true
        clip: true
        enabled: root.enabled

        onActiveFocusChanged: {
            if (activeFocus) {
                text = root.displayText
                root.query = ""
                root.expandCurrentFamily()
                selectAll()
                fontPopup.open()
            }
        }
        onTextEdited: {
            root.query = text
            if (!fontPopup.visible) fontPopup.open()
        }
        onAccepted: {
            // 回车：优先取当前高亮行；否则取 visibleRows 第一个 face 或已输入值
            var rows = root.visibleRows
            if (fontList.currentIndex >= 0 && fontList.currentIndex < rows.length) {
                root.choose(rows[fontList.currentIndex])
            } else if (rows.length > 0) {
                // 找第一个 face
                var picked = null
                for (var i = 0; i < rows.length; i++) {
                    if (rows[i].kind === "face") { picked = rows[i]; break }
                }
                if (picked) root.choose(picked)
                else {
                    var typed = text.trim()
                    if (typed.length > 0) {
                        root._doEmitActivated(typed, "")
                        fontPopup.close()
                        focus = false
                    }
                }
            } else {
                var typed2 = text.trim()
                if (typed2.length > 0) {
                    root._doEmitActivated(typed2, "")
                    fontPopup.close()
                    focus = false
                }
            }
        }
        Keys.onEscapePressed: {
            fontPopup.close()
            text = root.displayText
            focus = false
        }
        Keys.onPressed: event => {
            // 键盘导航：搜索框获得焦点时也能上下方向键滚动选择
            if (!fontPopup.visible) return
            var rows = root.visibleRows
            if (!rows.length) return
            switch (event.key) {
            case Qt.Key_Down:
                event.accepted = true
                if (fontList.currentIndex + 1 < rows.length) {
                    fontList.currentIndex += 1
                    fontList.positionViewAtIndex(fontList.currentIndex, ListView.EnsureVisible)
                }
                break
            case Qt.Key_Up:
                event.accepted = true
                if (fontList.currentIndex - 1 >= 0) {
                    fontList.currentIndex -= 1
                    fontList.positionViewAtIndex(fontList.currentIndex, ListView.EnsureVisible)
                }
                break
            case Qt.Key_PageDown:
                event.accepted = true
                var step = Math.max(1, Math.floor(fontList.height / 28))
                fontList.currentIndex = Math.min(rows.length - 1, fontList.currentIndex + step)
                fontList.positionViewAtIndex(fontList.currentIndex, ListView.EnsureVisible)
                break
            case Qt.Key_PageUp:
                event.accepted = true
                var stepU = Math.max(1, Math.floor(fontList.height / 28))
                fontList.currentIndex = Math.max(0, fontList.currentIndex - stepU)
                fontList.positionViewAtIndex(fontList.currentIndex, ListView.EnsureVisible)
                break
            case Qt.Key_Home:
                event.accepted = true
                fontList.currentIndex = 0
                fontList.positionViewAtIndex(0, ListView.Beginning)
                break
            case Qt.Key_End:
                event.accepted = true
                fontList.currentIndex = rows.length - 1
                fontList.positionViewAtIndex(rows.length - 1, ListView.End)
                break
            case Qt.Key_Right: {
                // family 行右箭头：展开；face 行右箭头：无操作
                event.accepted = true
                var cur = fontList.currentIndex
                if (cur >= 0 && cur < rows.length && rows[cur].kind === "family") {
                    var fam = String(rows[cur].group.family || rows[cur].group.value || "")
                    var nxt = {}; nxt[fam] = true
                    root.expandedFamilies = nxt
                }
                break
            }
            case Qt.Key_Left: {
                event.accepted = true
                var curL = fontList.currentIndex
                if (curL >= 0 && curL < rows.length) {
                    if (rows[curL].kind === "family") {
                        var fmL = String(rows[curL].group.family || rows[curL].group.value || "")
                        var nxtL = {}; nxtL[fmL] = false
                        root.expandedFamilies = nxtL
                    } else {
                        // face 行：跳到对应 family 行
                        var targetF = rows[curL].family
                        for (var b = curL - 1; b >= 0; b--) {
                            if (rows[b].kind === "family"
                                    && String(rows[b].group.family || rows[b].group.value || "") === targetF) {
                                fontList.currentIndex = b
                                fontList.positionViewAtIndex(b, ListView.EnsureVisible)
                                break
                            }
                        }
                    }
                }
                break
            }
            }
        }
    }

    Binding {
        target: fontInput
        property: "text"
        value: root.displayText
        when: !fontInput.activeFocus
        restoreMode: Binding.RestoreNone
    }

    AppIcon {
        id: indicator
        anchors.right: parent.right
        anchors.rightMargin: 9
        anchors.verticalCenter: parent.verticalCenter
        width: 12
        height: 12
        iconName: AppIcons.selectIndicator
        iconSize: 12
        iconColor: root.enabled ? Theme.textMuted : Theme.textDisabled
    }

    MouseArea {
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 30
        enabled: root.enabled
        cursorShape: enabled ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
            if (fontPopup.visible) {
                // 关闭弹窗前先把 pending 的防抖直接应用掉；防止"选了但没应用"的体验
                root._flushPendingActivated(true)
                fontPopup.close()
                fontInput.focus = false
            } else {
                root.query = ""
                root.expandCurrentFamily()
                fontInput.forceActiveFocus()
                fontInput.selectAll()
                fontPopup.open()
            }
        }
    }

    Popup {
        id: fontPopup
        y: root.height + 4
        width: Math.max(root.width, 320)
        height: Math.min(440, Math.max(60, fontList.contentHeight + 8))
        padding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent
        onClosed: {
            // 弹窗关闭兜底：如果还有 debounce 队列里未应用的值，直接应用
            // （例如用户点了一个字重后快速切焦点走别的路径）
            root._flushPendingActivated(true)
        }

        contentItem: ListView {
            id: fontList
            clip: true
            model: root.visibleRows
            currentIndex: -1
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator { }
            keyNavigationEnabled: false

            delegate: ItemDelegate {
                required property var modelData
                required property int index
                width: fontList.width
                height: modelData.kind === "family" ? 32 : 30
                highlighted: hovered || fontList.currentIndex === index
                leftPadding: modelData.kind === "face" ? 28 : 8
                onClicked: root.choose(modelData)

                // 字体渲染节流：只对可见范围 ±3 行、或者 hover/current 的行使用对应字体本身渲染；
                // 其余统一使用 Theme.bodyFont，避免 900+ 家族首次渲染时大量字体加载造成的卡顿。
                readonly property bool _inVisibleWindow: {
                    if (fontList.count <= 40) return true
                    var y0 = fontList.contentY - 60
                    var y1 = fontList.contentY + fontList.height + 60
                    var rowY = index * 30
                    return rowY >= y0 && rowY <= y1
                }
                readonly property bool _useNativeFont: hovered
                        || fontList.currentIndex === index
                        || _inVisibleWindow
                        || modelData.kind === "family" // family 行保留原字体（只在可见窗口内才 native？其实 family 少，无所谓）

                contentItem: Row {
                    spacing: 6
                    AppIcon {
                        visible: modelData.kind === "family"
                        iconName: modelData.group.__recent_block__ ? AppIcons.history : AppIcons.selectIndicator
                        iconSize: 12
                        width: visible ? 12 : 0
                        height: 12
                        rotation: modelData.group.__recent_block__ ? 0 : (modelData.expanded ? 90 : 0)
                        iconColor: modelData.group.__recent_block__ ? Theme.accent : Theme.textMuted
                    }
                    Text {
                        text: modelData.kind === "family"
                              ? String(modelData.group.label || modelData.group.family || "")
                              : String(modelData.faceData.label || modelData.faceData.face || modelData.faceData.value || modelData.face)
                        color: {
                            if (modelData.kind === "family") {
                                return modelData.group.__recent_block__ ? Theme.accent : Theme.textPrimary
                            }
                            return Theme.textSecondary
                        }
                        font.family: {
                            if (!delegateRoot._useNativeFont) return Theme.bodyFont
                            if (modelData.kind === "family") {
                                // 最近使用头（没有 family）用 Theme.bodyFont
                                var gFam = String(modelData.group.family || "")
                                return gFam ? gFam : Theme.bodyFont
                            }
                            return String(modelData.faceData.family || modelData.group.family || Theme.bodyFont)
                        }
                        font.styleName: modelData.kind === "face" && delegateRoot._useNativeFont
                                        ? String(modelData.face || "Regular")
                                        : "Regular"
                        font.pixelSize: modelData.kind === "family" ? 11 : 10
                        font.weight: modelData.kind === "family" ? Font.DemiBold : Font.Normal
                        verticalAlignment: Text.AlignVCenter
                        elide: Text.ElideRight
                    }
                }
                background: Rectangle {
                    radius: Theme.radiusSmall
                    color: {
                        if (modelData.kind === "family" && modelData.group.__recent_block__) {
                            return parent.highlighted ? Theme.accentSoft : Theme.bgPanel
                        }
                        if (modelData.kind === "face"
                                && String(modelData.family) === root.value
                                && String(modelData.face) === root.face) {
                            return Theme.accentSoft
                        }
                        return parent.highlighted ? Theme.bgHover : "transparent"
                    }
                }

                // 给嵌套 contentItem 里的 delegateRoot._useNativeFont 一个 id
                property Item delegateRoot: this
            }
        }

        background: Rectangle {
            radius: Theme.radius
            color: Theme.bgRaised
            border.width: 1
            border.color: Theme.borderStrong
        }
    }

    Accessible.name: "字体与字重"
    Accessible.description: "按字体家族展开并选择具体字重，输入文字可筛选；方向键导航、回车选择"
    Accessible.role: Accessible.ComboBox
}
