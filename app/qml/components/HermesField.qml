import QtQuick
import QtQuick.Layouts

// QML adaptation of packages/shared-ui/src/components/field in
// Hermes-CN-Desktop. License notices are preserved in THIRD_PARTY_NOTICES.md.
Item {
    id: root

    property string orientation: "vertical"
    property string label: ""
    property string hint: ""
    property string error: ""
    property bool required: false
    property bool compact: false
    property int labelWidth: compact
                             ? Theme.inspectorLabelColWidth
                             : Theme.fieldHorizontalLabelWidth
    property int columnGap: compact
                            ? Theme.inspectorColSpacing
                            : Theme.fieldHorizontalGap
    property int controlSpacing: compact
                                 ? Theme.inspectorColSpacing
                                 : Theme.fieldControlGap
    property int minimumControlHeight: 0
    default property alias controls: controlRow.data

    readonly property bool horizontal: orientation === "horizontal"
    readonly property bool invalid: error.length > 0
    readonly property int controlAreaWidth: horizontal
                                            ? Math.max(0, width - labelWidth - columnGap)
                                            : width
    readonly property int wSliderFill: Math.max(
                                           60,
                                           controlAreaWidth
                                           - controlSpacing
                                           - Theme.inspectorWSliderVB)

    Layout.fillWidth: true
    Layout.minimumWidth: 0
    implicitWidth: fieldLayout.implicitWidth
    implicitHeight: fieldLayout.implicitHeight
    height: implicitHeight

    GridLayout {
        id: fieldLayout
        anchors.left: parent.left
        anchors.right: parent.right
        columns: root.horizontal ? 2 : 1
        columnSpacing: root.columnGap
        rowSpacing: Theme.fieldGap

        Column {
            id: labelGroup
            Layout.row: 0
            Layout.column: 0
            Layout.preferredWidth: root.horizontal ? root.labelWidth : -1
            Layout.fillWidth: !root.horizontal
            spacing: Theme.space1

            Text {
                width: parent.width
                visible: root.label.length > 0
                text: root.label + (root.required ? " *" : "")
                color: root.invalid ? Theme.danger : Theme.textMuted
                font.family: Theme.bodyFont
                font.pixelSize: Theme.fieldLabelFontSize
                font.weight: Font.DemiBold
                horizontalAlignment: Text.AlignLeft
                verticalAlignment: Text.AlignVCenter
                elide: Text.ElideNone
                wrapMode: Text.NoWrap
            }

            Text {
                width: parent.width
                visible: root.hint.length > 0
                text: root.hint
                color: Theme.textDisabled
                font.family: Theme.bodyFont
                font.pixelSize: Theme.fieldHintFontSize
                wrapMode: Text.Wrap
            }
        }

        ColumnLayout {
            id: controlStack
            Layout.row: root.horizontal ? 0 : 1
            Layout.column: root.horizontal ? 1 : 0
            Layout.fillWidth: true
            Layout.minimumWidth: 0
            spacing: Theme.fieldControlGap

            RowLayout {
                id: controlRow
                property alias wSliderFill: root.wSliderFill
                Layout.fillWidth: true
                Layout.minimumWidth: 0
                Layout.minimumHeight: root.minimumControlHeight
                spacing: root.controlSpacing
            }

            Text {
                Layout.fillWidth: true
                visible: root.error.length > 0
                text: root.error
                color: Theme.danger
                font.family: Theme.bodyFont
                font.pixelSize: Theme.fieldHintFontSize
                wrapMode: Text.Wrap
            }
        }
    }

    Accessible.name: label
    Accessible.description: error.length > 0 ? error : hint
    Accessible.role: Accessible.Grouping
}
