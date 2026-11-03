"""验证 QML 层「保存改动回此预设」按钮端到端可用。

跑法：python -u docs/audit/_verify_save_button.py

为什么单独需要它：`savePresetFromWorkspace` 单测通过不代表按钮能用。
QML 根对象的普通 function 无法被 `QMetaObject.invokeMethod` 调用
（见 docs/card-tab-management-design.md 第 9.3 节），所以走
`requestSaveToPresetNow` 桥接属性触发，这与用户点按钮走同一条函数。
"""
from __future__ import annotations

import os
import sys
import tempfile

os.environ["QT_QPA_PLATFORM"] = "windows"
PROJECT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT)

from PIL import Image  # noqa: E402
from PySide6.QtCore import QMetaObject, QTimer, QUrl  # noqa: E402
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

WORK = tempfile.mkdtemp()
manager = PresetManager(app_dir=WORK, copy_initial=False)
documents = []
for name in ("主图", "细节图"):
    doc = Document()
    doc.create_new(400, 300)
    doc.tab_name = name
    doc.original_tab_name = name
    path = os.path.join(WORK, f"{name}.png")
    Image.new("RGBA", (120, 90), (60, 110, 160, 255)).save(path)
    doc.add_layer("原图层", 10, 20, 100, 70, image_source=path)
    documents.append(doc)
PRESET_ID = manager.save_preset_documents("保存测试卡", "", documents)

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


def disk_canvas_width(preset_id):
    raw = manager.load_preset(preset_id) or {}
    pages = raw.get("documents") or [{}]
    return pages[0].get("canvas_width")


def step():
    loaded = pmvm.loadPreset(PRESET_ID)
    check("打开预设得到 2 页", loaded == 2 and sessions.count == 2, f"{loaded}/{sessions.count}")

    # 模拟用户在编辑器里改画布尺寸
    sessions.documentAt(0).canvas_width = 1234
    check("改动尚未写盘", disk_canvas_width(PRESET_ID) != 1234, str(disk_canvas_width(PRESET_ID)))

    QMetaObject.invokeMethod(window, "openProjectPresetDrawer")
    QTest.qWait(800)
    workbench = window.findChild(QQuickItem, "presetWorkbench")
    if workbench is None:
        print("FAIL: 工作台没打开")
        app.exit(1)
        return
    workbench.setProperty("selectedId", PRESET_ID)
    QTest.qWait(400)

    check("QML 能查到打开页数", pmvm.openPageCount(PRESET_ID) == 2, str(pmvm.openPageCount(PRESET_ID)))
    check("QML 判定可保存", pmvm.canSavePresetFromWorkspace(PRESET_ID) is True)

    # 走与按钮完全相同的函数（经桥接属性，因为普通 function 不可 invoke）
    workbench.setProperty("requestSaveToPresetNow", True)
    QTest.qWait(1200)

    check("改动已写盘", disk_canvas_width(PRESET_ID) == 1234, str(disk_canvas_width(PRESET_ID)))

    # 未打开的预设，按钮应禁用
    other = manager.save_preset_documents("未打开的", "", [documents[0]])
    check("未打开预设不可保存", pmvm.canSavePresetFromWorkspace(other) is False)

    print()
    print(f"总结：{_passed} passed, {_failed} failed")
    app.exit(0 if _failed == 0 else 1)


QTimer.singleShot(1000, step)
sys.exit(app.exec())
