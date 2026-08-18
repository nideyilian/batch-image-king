import QtQuick

Item {
    id: root

    property string tone: "success"
    property string label: ""
    property bool compact: false

    implicitWidth: row.implicitWidth
    implicitHeight: compact ? 18 : 24

    Row {
        id: row
        anchors.verticalCenter: parent.verticalCenter
        spacing: 7

        Rectangle {
            width: compact ? 6 : 7
            height: width
            radius: width / 2
            anchors.verticalCenter: parent.verticalCenter
            color: root.tone === "warning"
                   ? Theme.warning
                   : (root.tone === "danger" ? Theme.danger : Theme.success)
        }

        Text {
            visible: root.label.length > 0
            text: root.label
            color: Theme.textSecondary
            font.family: Theme.bodyFont
            font.pixelSize: compact ? 10 : 11
            verticalAlignment: Text.AlignVCenter
        }
    }
}
