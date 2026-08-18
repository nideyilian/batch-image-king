import QtQuick
import QtQuick.Layouts

GridLayout {
    id: root

    property int pairBreakpoint: Theme.inspectorPairBreakpoint

    width: parent ? parent.width : 0
    columns: width >= pairBreakpoint ? 2 : 1
    columnSpacing: Theme.inspectorColSpacing
    rowSpacing: Theme.inspectorRowSpacing
}
