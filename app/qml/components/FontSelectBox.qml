import QtQuick
import QtQuick.Controls.Basic

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
        var needle = root.query.trim().toLocaleLowerCase()
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
        var child = row.faceData || {}
        root.activated(row.family, row.face)
        fontPopup.close()
        fontInput.focus = false
    }

    implicitWidth: 180
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
            var typed = text.trim()
            if (root.visibleRows.length > 0) root.choose(root.visibleRows[0])
            else if (typed.length > 0) {
                root.activated(typed, "")
                fontPopup.close()
                focus = false
            }
        }
        Keys.onEscapePressed: {
            fontPopup.close()
            text = root.displayText
            focus = false
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
        width: root.width
        height: Math.min(320, Math.max(44, fontList.contentHeight + 8))
        padding: 4
        closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutsideParent

        contentItem: ListView {
            id: fontList
            clip: true
            model: root.visibleRows
            currentIndex: -1
            boundsBehavior: Flickable.StopAtBounds
            ScrollIndicator.vertical: ScrollIndicator { }

            delegate: ItemDelegate {
                required property var modelData
                required property int index
                width: fontList.width
                height: modelData.kind === "family" ? 32 : 30
                highlighted: hovered || fontList.currentIndex === index
                leftPadding: modelData.kind === "face" ? 28 : 8
                onClicked: root.choose(modelData)

                contentItem: Row {
                    spacing: 6
                    AppIcon {
                        visible: modelData.kind === "family"
                        iconName: AppIcons.selectIndicator
                        iconSize: 12
                        width: visible ? 12 : 0
                        height: 12
                        rotation: modelData.expanded ? 90 : 0
                        iconColor: Theme.textMuted
                    }
                    Text {
                        text: modelData.kind === "family"
                              ? String(modelData.group.label || modelData.group.family || "")
                              : String(modelData.faceData.label || modelData.faceData.face || modelData.faceData.value || modelData.face)
                        color: modelData.kind === "family" ? Theme.textPrimary : Theme.textSecondary
                        font.family: modelData.kind === "family"
                                     ? String(modelData.group.family || Theme.bodyFont)
                                     : String(modelData.faceData.family || modelData.group.family || Theme.bodyFont)
                        font.styleName: modelData.kind === "face"
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
                    color: modelData.kind === "face"
                           && String(modelData.family) === root.value
                           && String(modelData.face) === root.face
                           ? Theme.accentSoft
                           : (parent.highlighted ? Theme.bgHover : "transparent")
                }
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
    Accessible.description: "按字体家族展开并选择具体字重，输入文字可筛选"
    Accessible.role: Accessible.ComboBox
}
