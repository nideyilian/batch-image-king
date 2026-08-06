import QtQuick

Rectangle {
    id: root

    property real progress: 0
    property string tone: "accent"
    property int thickness: 4

    implicitHeight: thickness
    radius: Math.max(1, thickness / 2)
    color: Theme.progressTrack
    clip: true

    Rectangle {
        width: parent.width * Math.max(0, Math.min(1, root.progress))
        height: parent.height
        radius: parent.radius
        color: root.tone === "warning"
               ? Theme.warning
               : (root.tone === "danger" ? Theme.danger : Theme.accent)

        Behavior on width { NumberAnimation { duration: Theme.motionNormal; easing.type: Easing.OutCubic } }
    }

    Accessible.role: Accessible.ProgressBar
    Accessible.name: "进度"
}
