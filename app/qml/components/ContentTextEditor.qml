import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
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
            selectionColor: Theme.selectionBackground
            selectedTextColor: Theme.selectionForeground
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
