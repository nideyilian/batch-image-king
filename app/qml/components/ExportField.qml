import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

AppTextField {
    id: exportField
    property string placeholder: ""
    signal committed(string value)

    implicitHeight: Theme.comfortableControlHeight
    placeholderText: placeholder
    font.pixelSize: 12
    onEditingFinished: exportField.committed(text)
}
