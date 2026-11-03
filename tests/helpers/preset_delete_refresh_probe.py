"""预设卡片删除后必须从工作台消失的探针。

回归背景（2026-11-03）：
    删除项目预设后，数据层已经从索引里删掉了，但工作台的卡片网格
    绑定的是 ``visiblePresets``（notify=viewChanged），而 ``deletePreset``
    只发了 ``presetsChanged`` —— 于是卡片原地不动，还能点、还能右键，
    点下去只会得到「预设不存在」。用户看到的是「删了没反应」。

    这条必须用**真实 QML 绑定**验证：只断言视图模型返回值是测不出来的，
    因为 ``visiblePresets`` 每次读都是新值，问题出在绑定没被通知重算。

用 QT_QPA_PLATFORM=windows 起真实窗口（offscreen 下 QQuickWindow 的
布局与真实平台不一致，历史上出现过假失败）。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import QUrl  # noqa: E402
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


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    tmp = Path(tempfile.mkdtemp())
    document = Document()
    document.create_new(600, 400)
    workspace = WorkspaceViewModel(document=document, auto_render=False)
    sessions = WorkspaceSessionViewModel(workspace=workspace)
    manager = PresetManager(app_dir=tmp / "data", copy_initial=False)
    vm = PresetManagerViewModel(workspace, sessions, manager=manager)

    assert vm.saveCurrent("A", "") and vm.saveCurrent("B", ""), "预置数据准备失败"

    harness_path = tmp / "harness.qml"
    components_url = QUrl.fromLocalFile(str(ROOT / "app" / "qml" / "components")).toString()
    harness_path.write_text(HARNESS % {"components": components_url}, encoding="utf-8")

    engine = QQmlApplicationEngine()
    engine.addImportPath(str(ROOT / "app" / "qml"))
    engine.warnings.connect(
        lambda errors: [print(f"QML WARNING: {e.toString()}") for e in errors]
    )
    engine.load(QUrl.fromLocalFile(str(harness_path)))
    if not engine.rootObjects():
        print("FAIL: 工作台 QML 加载失败")
        return 2

    win = engine.rootObjects()[0]
    win.setProperty("vm", vm)
    QTest.qWait(300)

    wb = win.findChild(QQuickItem, "presetWorkbench")
    if wb is None:
        print("FAIL: 找不到 PresetWorkbench")
        return 2

    def visible_count() -> int:
        items = wb.property("visibleItems") or []
        return len(items)

    if visible_count() != 2:
        print(f"FAIL: 初始卡片数应为 2，实际 {visible_count()}")
        return 2

    victim = vm.presets[0]
    wb.setProperty("selectedId", victim["id"])
    QTest.qWait(100)

    ok = vm.deletePreset(victim["id"])
    QTest.qWait(200)

    problems = []
    if not ok:
        problems.append("deletePreset 返回 False")
    if visible_count() != 1:
        problems.append(f"删除后卡片数应为 1，实际 {visible_count()}（卡片没刷新）")
    if str(wb.property("selectedId") or "") != "":
        problems.append("删除后选中态未清空（详情面板停留在已删除的预设上）")

    vm.shutdown()
    engine.deleteLater()
    QTest.qWait(50)

    if problems:
        print("FAIL: " + "；".join(problems))
        return 1
    print("OK: 删除后卡片消失且选中态清空")
    return 0


if __name__ == "__main__":
    sys.exit(main())
