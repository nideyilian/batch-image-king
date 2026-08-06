import QtQuick
import QtQuick.Controls.Basic

Drawer {
    modal: true
    dim: true
    padding: 0
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside

    Overlay.modal: Rectangle { color: Theme.overlayModal }

    background: Rectangle {
        color: Theme.bgPanel
        border.width: 1
        border.color: Theme.borderStrong
    }
}
