"""端到端：从工作台卡片删除 → 确认弹窗 → 卡片消失 + toast。

前面两个探针分别验证了「信号发了」和「绑定重算了」，都没走真实入口。
这个探针走完整链路：Main.qml 里的删除确认弹窗 → 视图模型 → 卡片网格刷新。

必须用真实窗口（windows 平台）：offscreen 下 mapToItem 坐标偏移，
点击会落空，得到假失败。
"""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "windows")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from PySide6.QtCore import Q_ARG, QMetaObject, QPointF, Qt, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.models.document import Document  # noqa: E402
from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel  # noqa: E402
from app.qml.viewmodels.binding_manager_view_model import BindingManagerViewModel  # noqa: E402
from app.qml.viewmodels.canvas_preset_view_model import CanvasPresetViewModel  # noqa: E402
from app.qml.viewmodels.multi_tab_export_view_model import MultiTabExportViewModel  # noqa: E402
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel  # noqa: E402
from app.qml.viewmodels.size_match_view_model import SizeMatchViewModel  # noqa: E402
from app.qml.viewmodels.update_view_model import UpdateViewModel  # noqa: E402
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel  # noqa: E402
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel  # noqa: E402
from app.utils.preset_manager import PresetManager  # noqa: E402

TEXT_ROLES = ("label", "text", "title", "tooltip")


def find_by_prop(item, prop, value, depth=0):
    if depth > 16:
        return None
    try:
        if item.property(prop) == value:
            return item
    except Exception:  # noqa: BLE001
        pass
    for child in item.childItems():
        found = find_by_prop(child, prop, value, depth + 1)
        if found is not None:
            return found
    return None


def main() -> int:
    app = QGuiApplication.instance() or QGuiApplication(sys.argv)

    tmp = Path(tempfile.mkdtemp())
    document = Document()
    document.create_new(600, 400)

    engine = QQmlApplicationEngine()
    workspace = WorkspaceViewModel(document=document, auto_render=False, parent=engine)
    sessions = WorkspaceSessionViewModel(workspace=workspace, parent=engine)
    manager = PresetManager(app_dir=tmp / "data", copy_initial=False)
    presets = PresetManagerViewModel(workspace, sessions, manager=manager, parent=engine)

    for name, obj in [
        ("workspace", workspace),
        ("workspaceSessions", sessions),
        ("layerModel", workspace.layerModel),
        ("projectPresets", presets),
        ("batchExport", BatchExportViewModel(workspace=workspace, parent=engine)),
        ("canvasPresets", CanvasPresetViewModel(workspace=workspace, parent=engine)),
        ("bindingManager", BindingManagerViewModel(workspace=workspace, parent=engine)),
        ("sizeMatch", SizeMatchViewModel(workspace=workspace, parent=engine)),
        ("multiTabExport", MultiTabExportViewModel(workspace, sessions, parent=engine)),
        ("updateManager", UpdateViewModel()),
    ]:
        engine.rootContext().setContextProperty(name, obj)

    engine.warnings.connect(
        lambda errors: [print(f"QML WARNING: {e.toString()}") for e in errors]
    )
    engine.load(QUrl.fromLocalFile(str(ROOT / "app" / "qml" / "Main.qml")))
    if not engine.rootObjects():
        print("FAIL: Main.qml 加载失败")
        return 2

    win = engine.rootObjects()[0]
    win.setProperty("width", 1600)
    win.setProperty("height", 960)
    win.show()
    QTest.qWait(600)

    assert presets.saveCurrent("甲预设", "") and presets.saveCurrent("乙预设", "")

    QMetaObject.invokeMethod(win, "openProjectPresetDrawer")
    QTest.qWait(600)

    wb = win.findChild(QQuickItem, "presetWorkbench")
    if wb is None or not wb.property("visible"):
        print("FAIL: 工作台未打开")
        return 2

    before = len(wb.property("visibleItems") or [])
    if before != 2:
        print(f"FAIL: 卡片数应为 2，实际 {before}")
        return 2

    victim = presets.presets[0]
    # 走真实入口：工作台信号 → Main.qml 打开确认弹窗
    emitted = QMetaObject.invokeMethod(
        wb, "requestDelete", Qt.DirectConnection,
        Q_ARG("QString", victim["id"]), Q_ARG("QString", victim["name"]),
    )
    assert emitted, "工作台的 requestDelete 信号没能发出去"
    QTest.qWait(400)
    if find_by_prop(win.contentItem(), "text", "删除项目预设？") is None:
        print("FAIL: 确认弹窗没有打开")
        return 2

    # 找到确认弹窗里的「删除」按钮并点它
    dialog_btn = find_by_prop(win.contentItem(), "label", "删除")
    if dialog_btn is None:
        # 弹窗可能挂在 overlay 上，退一步搜整个 contentItem 的父层
        dialog_btn = find_by_prop(win.contentItem().parentItem(), "label", "删除")
    if dialog_btn is None:
        print("FAIL: 找不到确认弹窗的删除按钮")
        return 2

    QTest.mouseClick(
        win, Qt.LeftButton, Qt.NoModifier,
        dialog_btn.mapToScene(QPointF(dialog_btn.width() / 2, dialog_btn.height() / 2)).toPoint(),
    )
    QTest.qWait(500)

    after = len(wb.property("visibleItems") or [])
    problems = []
    if after != 1:
        problems.append(f"删除后卡片数应为 1，实际 {after}")
    if str(wb.property("selectedId") or "") not in ("", victim["id"]):
        problems.append("选中态异常")
    if presets.presetExists(victim["id"]):
        problems.append("条目仍在索引里")

    presets.shutdown()
    if problems:
        print("FAIL: " + "；".join(problems))
        return 1
    print("OK: 工作台删除链路走通")
    return 0


if __name__ == "__main__":
    sys.exit(main())
