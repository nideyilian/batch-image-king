import QtQuick
import QtQuick.Controls.Basic

Dialog {
    modal: true
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape

    Overlay.modal: Rectangle { color: Theme.overlayModal }

    background: Rectangle {
        color: Theme.bgPanel
        border.width: 1
        border.color: Theme.borderStrong
        radius: Theme.radius
    }
}
