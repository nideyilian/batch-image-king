"""验证「清空全部 + 同时关闭工作区」在真实 QML 里的端到端效果。

跑法：python -u docs/audit/_verify_clear_all_workspace.py

为什么需要它：`closeAllDocuments(also_close=True)` 后端单测通过，
但这条路径**从来没有 QML 层覆盖**。实测发现：界面点「清空标签页」后
卡片空了、工作区的标签页还在 —— 用户看到的就是「清空没生效」。
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "windows"
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from PIL import Image  # noqa: E402
from PySide6.QtCore import QMetaObject, QPointF, QTimer, QUrl  # noqa: E402
from PySide6.QtGui import QGuiApplication  # noqa: E402
from PySide6.QtQml import QQmlApplicationEngine  # noqa: E402
from PySide6.QtQuick import QQuickItem  # noqa: E402
from PySide6.QtTest import QTest  # noqa: E402

from app.models.document import Document  # noqa: E402
from app.qml.preview_image_provider import PreviewImageProvider  # noqa: E402
from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel  # noqa: E402
from app.qml.viewmodels.binding_manager_view_model import BindingManagerViewModel  # noqa: E402
from app.qml.viewmodels.canvas_preset_view_model import CanvasPresetViewModel  # noqa: E402
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel  # noqa: E402
from app.qml.viewmodels.size_match_view_model import SizeMatchViewModel  # noqa: E402
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel  # noqa: E402
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel  # noqa: E402
from app.utils.preset_manager import PresetManager  # noqa: E402

PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
WORK = tempfile.mkdtemp()
manager = PresetManager(app_dir=WORK, copy_initial=False)

documents = []
for name in ("主图", "细节图", "场景图"):
    doc = Document()
    doc.create_new(400, 300)
    doc.tab_name = name
    doc.original_tab_name = name
    path = os.path.join(WORK, f"{name}.png")
    Image.new("RGBA", (120, 90), (60, 110, 160, 255)).save(path)
    doc.add_layer("L0", 10, 20, 100, 70, image_source=path)
    documents.append(doc)
PRESET_ID = manager.save_preset_documents("测试卡", "", documents)

app = QGuiApplication(sys.argv)
engine = QQmlApplicationEngine()
provider = PreviewImageProvider()
workspace = WorkspaceViewModel(preview_provider=provider, auto_render=False, parent=engine)
engine.addImageProvider("documentPreview", provider)
sessions = WorkspaceSessionViewModel(workspace=workspace, parent=engine, include_initial_document=False)
pmvm = PresetManagerViewModel(workspace=workspace, sessions=sessions, manager=manager, parent=engine)
for name, obj in [
    ("workspace", workspace),
    ("layerModel", workspace.layerModel),
    ("workspaceSessions", sessions),
    ("projectPresets", pmvm),
    ("batchExport", BatchExportViewModel(workspace=workspace, parent=engine)),
    ("canvasPresets", CanvasPresetViewModel(workspace=workspace, parent=engine)),
    ("bindingManager", BindingManagerViewModel(workspace=workspace, parent=engine)),
    ("sizeMatch", SizeMatchViewModel(workspace=workspace, parent=engine)),
]:
    engine.rootContext().setContextProperty(name, obj)

engine.load(QUrl.fromLocalFile(os.path.join(PROJECT, "app", "qml", "Main.qml")))
roots = engine.rootObjects()
if not roots:
    print("FAIL: Main.qml 加载失败")
    sys.exit(1)
window = roots[0]
window.setProperty("width", 1500)
window.setProperty("height", 900)
window.show()

_passed = 0
_failed = 0


def check(name, ok, detail=""):
    global _passed, _failed
    if ok:
        _passed += 1
        print(f"PASS  {name}")
    else:
        _failed += 1
        print(f"FAIL  {name}   {detail}")


def walk(item, depth=0):
    if depth > 30:
        return
    yield item
    for child in item.childItems():
        yield from walk(child, depth + 1)


def find_prop(item, prop):
    for node in walk(item):
        try:
            if node.property(prop) is not None:
                return node
        except Exception:  # noqa: BLE001
            pass
    return None


def step():
    loaded = pmvm.loadPreset(PRESET_ID)
    check("预设已打开到工作区", loaded == 3 and sessions.count == 3, f"loaded={loaded} count={sessions.count}")

    QMetaObject.invokeMethod(window, "openProjectPresetDrawer")
    QTest.qWait(900)
    workbench = window.findChild(QQuickItem, "presetWorkbench")
    if workbench is None:
        print("FAIL: 工作台没打开")
        app.exit(1)
        return
    workbench.setProperty("selectedId", PRESET_ID)
    QTest.qWait(600)

    # 对话框默认不勾选（尊重用户：不该顺手关掉正在编辑的东西）
    QMetaObject.invokeMethod(workbench, "requestClearAllTabs")
    QTest.qWait(600)
    check(
        "清空对话框已打开（pendingClearTabsId 已设）",
        workbench.property("pendingClearTabsId") == PRESET_ID,
        str(workbench.property("pendingClearTabsId")),
    )
    # Popup 不在 item 树里，findChild 读不到；用根对象上镜像的开关状态。
    check(
        "开关默认不勾选",
        workbench.property("alsoCloseWorkspaceOnClear") is False,
        str(workbench.property("alsoCloseWorkspaceOnClear")),
    )

    # 勾选后确认（等价于用户在界面上拨开关 + 点确认按钮）
    workbench.setProperty("alsoCloseWorkspaceOnClear", True)
    QTest.qWait(300)
    check(
        "能勾选「同时关闭工作区」",
        workbench.property("alsoCloseWorkspaceOnClear") is True,
    )

    workbench.setProperty("requestConfirmClearTabs", True)
    QTest.qWait(1500)

    card = next((c for c in pmvm.presets if c["id"] == PRESET_ID), None)
    check("工作区标签页已关闭", sessions.count == 0, f"count={sessions.count}")
    check("卡片页数归零", card is not None and card["documentCount"] == 0, str(card))

    print()
    print(f"总结：{_passed} passed, {_failed} failed")
    app.exit(0 if _failed == 0 else 1)


QTimer.singleShot(1000, step)
sys.exit(app.exec())
