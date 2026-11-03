"""分类（左侧文件夹）新建 + 重命名入口的真实界面探针。

回归背景（2026-11-04）：
    左栏「分类」原先只是预设 category 字段的聚合视图：
      · 「新建分类」只改了筛选条件，空分类根本不落盘，看起来「建了没建上」；
      · 没有重命名入口，只能逐个预设改分类；
      · 空分类删不掉（旧语义把 0 条当失败）。
    改成持久化分类清单后，必须用**真实 QML 绑定**验证三件事：
      1. 新建分类后侧栏立刻出现（绑定在 vm.categories，notify=presetsChanged）；
      2. 悬停分类行能露出铅笔按钮（用户找得到入口）；
      3. 点铅笔真的把 pendingRenameCategory 设成该分类（信号接通了）。

用 QT_QPA_PLATFORM=windows 起真实窗口：offscreen 下 hover 事件不生效。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QPoint, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.models.document import Document  # noqa: E402
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel  # noqa: E402
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel  # noqa: E402
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel  # noqa: E402
from app.utils.preset_manager import PresetManager  # noqa: E402

HARNESS = """
import QtQuick
import QtQuick.Controls
import QtQuick.Window
import "%(components)s"

Window {
    id: win
    width: 1400
    height: 900
    visible: true
    property var vm: null
    property alias workbench: wb

    PresetWorkbench {
        id: wb
        objectName: "presetWorkbench"
        anchors.fill: parent
        vm: win.vm
        onRequestToast: function(message) { win.lastToast = message }
    }
    property string lastToast: ""
}
"""


def walk(item):
    yield item
    for child in item.childItems():
        yield from walk(child)


def find_by_prop(root, prop, value):
    for item in walk(root):
        try:
            if item.property(prop) == value:
                return item
        except Exception:  # noqa: BLE001 - 不是所有 item 都有该属性
            continue
    return None


def center_in_window(item, window):
    point = item.mapToItem(window.contentItem(), QPointF(item.width() / 2, item.height() / 2))
    return QPoint(int(point.x()), int(point.y()))


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    tmp = Path(tempfile.mkdtemp())
    document = Document()
    document.create_new(600, 400)
    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    manager = PresetManager(app_dir=tmp / "data", copy_initial=False)
    vm = PresetManagerViewModel(workspace, sessions, manager=manager)

    assert vm.saveCurrent("甲", "") and vm.saveCurrent("乙", ""), "预置数据准备失败"
    preset_id = vm.presets[0]["id"]
    assert vm.setPresetCategory(preset_id, "促销卡券"), "分类写入失败"
    assert vm.setPresetCategory(vm.presets[1]["id"], "平台素材"), "分类写入失败"

    harness_path = tmp / "harness.qml"
    components_url = QUrl.fromLocalFile(str(ROOT / "app" / "qml" / "components")).toString()
    harness_path.write_text(HARNESS % {"components": components_url}, encoding="utf-8")

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(ROOT / "app" / "qml"))
    warnings = []
    engine.warnings.connect(lambda errors: warnings.extend(e.toString() for e in errors))
    engine.load(QUrl.fromLocalFile(str(harness_path)))
    if not engine.rootObjects():
        print("FAIL: 工作台 QML 加载失败")
        return 2

    win = engine.rootObjects()[0]
    win.setProperty("vm", vm)
    QTest.qWait(400)

    wb = win.findChild(QQuickItem, "presetWorkbench")
    if wb is None:
        print("FAIL: 找不到 PresetWorkbench")
        return 2

    problems = []

    # 1) 新建空分类后，侧栏必须立刻出现（哪怕 0 个预设）
    if not vm.createCategory("短视频"):
        problems.append("createCategory 返回 False")
    QTest.qWait(200)
    row = find_by_prop(wb, "label", "短视频")
    if row is None:
        problems.append("新建分类后侧栏没有出现该行（绑定没刷新）")

    # 2) 悬停分类行，铅笔按钮应可见
    row = find_by_prop(wb, "label", "促销卡券")
    if row is None:
        problems.append("找不到「促销卡券」分类行")
    else:
        QTest.mouseMove(win, center_in_window(row, win))
        QTest.qWait(200)

        def find_row_action(icon_name):
            """找该行内的操作图标（图标必须落在这一行的横向范围内）。"""
            for item in walk(wb):
                try:
                    if item.property("iconName") != icon_name or not item.isVisible():
                        continue
                    origin = item.mapToItem(row, QPointF(0, 0))
                    if -2 <= origin.x() <= row.width() + 2:
                        return item
                except Exception:  # noqa: BLE001
                    continue
            return None

        # 3) 垃圾桶必须点得动。原先整行 MouseArea 声明在 RowLayout 之后，
        #    盖住了两个按钮 —— 点垃圾桶只会切换分类，看起来「没反应」。
        trash = find_row_action("trash-2")
        if trash is None:
            problems.append("悬停分类行后删除按钮没出现")
        else:
            QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, center_in_window(trash, win))
            QTest.qWait(200)
            if str(wb.property("pendingDeleteCategory") or "") != "促销卡券":
                problems.append("点垃圾桶没有进入删除确认（按钮被整行点击层挡住）")
            wb.setProperty("pendingDeleteCategory", "")
            QTest.qWait(100)

        # 4) 铅笔同理
        pencil = find_row_action("pencil")
        if pencil is None:
            problems.append("悬停分类行后铅笔按钮没出现（用户找不到重命名入口）")
        else:
            QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, center_in_window(pencil, win))
            QTest.qWait(200)
            pending = str(wb.property("pendingRenameCategory") or "")
            if pending != "促销卡券":
                problems.append(f"点铅笔后 pendingRenameCategory 应为「促销卡券」，实际「{pending}」")

    hard_warnings = [w for w in warnings if "PresetWorkbench.qml" in w]
    if hard_warnings:
        problems.append("QML 警告：" + hard_warnings[0])

    vm.shutdown()
    engine.deleteLater()
    QTest.qWait(50)

    if problems:
        print("FAIL: " + "；".join(problems))
        return 1
    print("OK: 新建分类即时出现、悬停露出铅笔、点击进入重命名")
    return 0


if __name__ == "__main__":
    sys.exit(main())
