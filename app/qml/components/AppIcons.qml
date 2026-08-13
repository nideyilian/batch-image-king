pragma Singleton
import QtQuick

QtObject {
    readonly property string add: "plus"
    readonly property string close: "x"
    readonly property string more: "ellipsis"
    readonly property string help: "circle-help"
    readonly property string circleDot: "circle-dot"
    readonly property string chevronDown: "chevron-down"
    readonly property string chevronUp: "chevron-up"
    readonly property string chevronRight: "chevron-right"
    readonly property string selectIndicator: "chevrons-up-down"

    readonly property string fileNew: "file-plus-2"
    readonly property string fileImage: "file-image"
    readonly property string fileText: "file-text"
    readonly property string folder: "folder"
    readonly property string folderOpen: "folder-open"
    readonly property string folderInput: "folder-input"
    readonly property string folderOutput: "folder-output"
    readonly property string save: "save"

    readonly property string undo: "undo-2"
    readonly property string redo: "redo-2"
    readonly property string history: "history"
    readonly property string refresh: "refresh-cw"
    readonly property string rotateLeft: "rotate-ccw"
    readonly property string rotateRight: "rotate-cw"

    readonly property string pointer: "mouse-pointer-2"
    readonly property string move: "move"
    readonly property string hand: "hand"
    readonly property string type: "type"
    readonly property string shapes: "shapes"
    readonly property string image: "image"
    readonly property string images: "images"
    readonly property string imageAdd: "image-plus"
    readonly property string layers: "layers-3"
    readonly property string group: "group"
    readonly property string ungroup: "ungroup"

    readonly property string eye: "eye"
    readonly property string eyeOff: "eye-off"
    readonly property string lock: "lock-keyhole"
    readonly property string unlock: "unlock-keyhole"
    readonly property string copy: "copy"
    readonly property string paste: "clipboard-paste"
    readonly property string trash: "trash-2"

    readonly property string crop: "crop"
    readonly property string flipHorizontal: "flip-horizontal-2"
    readonly property string flipVertical: "flip-vertical-2"
    readonly property string arrowLeft: "arrow-left"
    readonly property string arrowRight: "arrow-right"
    readonly property string arrowUp: "arrow-up"
    readonly property string arrowDown: "arrow-down"
    readonly property string horizontal: "arrow-left-right"
    readonly property string vertical: "arrow-up-down"

    readonly property string alignLeft: "align-start-vertical"
    readonly property string alignCenterHorizontal: "align-center-vertical"
    readonly property string alignRight: "align-end-vertical"
    readonly property string alignTop: "align-start-horizontal"
    readonly property string alignCenterVertical: "align-center-horizontal"
    readonly property string alignBottom: "align-end-horizontal"
    readonly property string distributeHorizontal: "align-horizontal-distribute-center"
    readonly property string distributeVertical: "align-vertical-distribute-center"

    readonly property string ruler: "ruler"
    readonly property string guides: "scan-line"
    readonly property string magnet: "magnet"
    readonly property string zoomIn: "zoom-in"
    readonly property string zoomOut: "zoom-out"
    readonly property string fitView: "maximize-2"
    readonly property string panelRight: "panel-right"
    readonly property string panelLeftClose: "panel-left-close"

    readonly property string link: "link-2"
    readonly property string unlink: "unlink-2"
    readonly property string shuffle: "shuffle"
    readonly property string randomize: "wand-sparkles"
    readonly property string sparkles: "sparkles"
    readonly property string tag: "tag"
    readonly property string settings: "settings-2"
    readonly property string sliders: "sliders-horizontal"
    readonly property string sun: "sun"
    readonly property string moon: "moon"

    readonly property string search: "search"
    readonly property string preview: "scan-eye"
    readonly property string listChecks: "list-checks"
    readonly property string exportAction: "send-to-back"
    readonly property string check: "circle-check"
    readonly property string info: "info"
    readonly property string warning: "triangle-alert"
    readonly property string error: "circle-x"
    readonly property string loader: "loader-circle"

    readonly property var layerByType: ({
        "图层组": group,
        "文字": type,
        "异形": shapes,
        "图片": image
    })

    function source(iconName) {
        var resolvedName = iconName && iconName.length > 0 ? iconName : help
        return Qt.resolvedUrl("../icons/" + resolvedName + ".svg")
    }
}
