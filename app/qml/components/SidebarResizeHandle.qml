import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Rectangle {
    id: resizeHandle

    property string tooltip: ""
    property string accessibleName: ""
    property bool dragging: false
    signal dragMoved(real horizontalDelta)
    signal resetRequested()

    Layout.preferredWidth: Theme.sidebarResizeHandleWidth
    Layout.minimumWidth: Theme.sidebarResizeHandleWidth
    Layout.maximumWidth: Theme.sidebarResizeHandleWidth
    Layout.fillHeight: true
    z: 50
    color: resizeMouse.containsMouse || dragging ? Theme.bgHover : Theme.bgBar
    activeFocusOnTab: true

    Rectangle {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        width: 1
        color: resizeMouse.containsMouse || dragging
               ? Theme.borderStrong : Theme.border
    }

    MouseArea {
        id: resizeMouse
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.SizeHorCursor
        preventStealing: true
        property real previousX: 0

        onPressed: mouse => {
            resizeHandle.forceActiveFocus(Qt.MouseFocusReason)
            previousX = resizeMouse.mapToItem(null, mouse.x, mouse.y).x
            resizeHandle.dragging = true
        }
        onReleased: {
            resizeHandle.dragging = false
        }
        onCanceled: {
            resizeHandle.dragging = false
        }
        onPositionChanged: mouse => {
            if (!pressed)
                return
            var sceneX = resizeMouse.mapToItem(null, mouse.x, mouse.y).x
            var delta = sceneX - previousX
            if (Math.abs(delta) < 0.01)
                return
            resizeHandle.dragMoved(delta)
            previousX = sceneX
        }
        onDoubleClicked: resizeHandle.resetRequested()
    }

    Keys.onLeftPressed: dragMoved(-Theme.sidebarResizeStep)
    Keys.onRightPressed: dragMoved(Theme.sidebarResizeStep)

    ToolTip.visible: resizeMouse.containsMouse
    ToolTip.text: resizeHandle.tooltip
    ToolTip.delay: 420
    Accessible.name: accessibleName
    Accessible.description: "可拖拽调整宽度，双击恢复默认"
}
