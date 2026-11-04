import QtQuick
import QtQuick.Controls.Basic

Dialog {
    modal: true
    focus: true
    padding: 0
    closePolicy: Popup.CloseOnEscape
    header: null
    footer: null

    // Popup 默认定位在父项的左上角。这里在组件层统一居中，调用点不必各自记得写
    // anchors.centerIn —— 预设工作台曾因 4 个弹窗全漏写而贴在窗口左上角，
    // 且默认 contentItem 与隐式高度互相依赖导致尺寸塌缩、背景都画不出来。
    anchors.centerIn: parent

    Overlay.modal: Rectangle { color: Theme.overlayModal }

    background: Rectangle {
        color: Theme.bgPanel
        border.width: 1
        border.color: Theme.borderStrong
        radius: Theme.radiusSmall
    }
}
