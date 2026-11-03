"""复现「操作多几下就卡死」：真实 QML 引擎 + 连续编辑操作 + 窗口存活监控。

现象（用户实机）：
  PID 73296 窗口句柄变 0，进程活着，事件循环未退出，
  日志最后一条停在 20:55:19，没有任何异常堆栈。

本脚本在 offscreen 下真实加载 Main.qml，然后连续做编辑操作，
每轮检查 rootObjects 是否还在、窗口是否仍可见。
"""
import os
import sys
import tempfile
import traceback

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine

app = QGuiApplication.instance() or QGuiApplication(sys.argv)


def pump(ms=30):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
from app.qml.viewmodels.canvas_preset_view_model import CanvasPresetViewModel
from app.qml.viewmodels.binding_manager_view_model import BindingManagerViewModel
from app.qml.viewmodels.size_match_view_model import SizeMatchViewModel
from app.qml.viewmodels.update_view_model import UpdateViewModel
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.qml.viewmodels.multi_tab_export_view_model import MultiTabExportViewModel
from app.qml.legacy_feature_bridge import LegacyFeatureBridge


def build_doc(layer_count=6, canvas=(1080, 1350)):
    from app.models.document import Document

    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(*canvas)
    for i in range(layer_count):
        path = os.path.join(tmp, f"img_{i}.png")
        img = Image.new("RGBA", (760, 560), (25 * i % 255, 90, 160, 255))
        for x in range(0, 760, 32):
            for y in range(0, 560, 32):
                img.putpixel((x, y), (0, 0, 0, 0))
        img.save(path)
        doc.add_layer(f"L{i}", 30 + i * 10, 40 + i * 10, 760, 560, image_source=path)
    return doc


print("=== 搭建真实 QML 工作台 ===")
engine = QQmlApplicationEngine()
preview_provider = PreviewImageProvider()
workspace = WorkspaceViewModel(
    preview_provider=preview_provider, auto_render=True,
    defer_font_catalog_preload=True, parent=engine,
)
batch_export = BatchExportViewModel(workspace=workspace, parent=engine)
canvas_presets = CanvasPresetViewModel(workspace=workspace, parent=engine)
binding_manager = BindingManagerViewModel(workspace=workspace, parent=engine)
size_match = SizeMatchViewModel(workspace=workspace, parent=engine)
update_manager = UpdateViewModel(parent=engine)
engine.addImageProvider("documentPreview", preview_provider)

doc = build_doc()
workspace.activateDocument(doc)

sessions = WorkspaceSessionViewModel(workspace=workspace, parent=engine, include_initial_document=True)
project_presets = PresetManagerViewModel(workspace=workspace, sessions=sessions, parent=engine)
multi_tab = MultiTabExportViewModel(workspace=workspace, sessions=sessions, parent=engine)
legacy = LegacyFeatureBridge(
    workspace=workspace, sessions=sessions,
    preset_view_model=project_presets, parent=engine,
)

for name, obj in (
    ("workspace", workspace), ("workspaceSessions", sessions),
    ("layerModel", workspace.layerModel), ("batchExport", batch_export),
    ("canvasPresets", canvas_presets), ("projectPresets", project_presets),
    ("bindingManager", binding_manager), ("sizeMatch", size_match),
    ("multiTabExport", multi_tab), ("legacyTools", legacy),
    ("updateManager", update_manager),
):
    engine.rootContext().setContextProperty(name, obj)

qml_path = os.path.join(REPO, "app", "qml", "Main.qml")
engine.load(QUrl.fromLocalFile(qml_path))
if not engine.rootObjects():
    print("!! QML 加载失败")
    sys.exit(1)
window = engine.rootObjects()[0]
workspace.setAutoRender(True)
pump(800)
print("窗口创建成功，rootObjects =", len(engine.rootObjects()))


def alive(tag):
    n = len(engine.rootObjects())
    ok = n > 0
    print(f"  [{tag}] rootObjects={n} {'OK' if ok else '<<< 窗口已消失 !!'}")
    return ok


alive("初始")

# ---- 连续编辑操作 ----
print("\n=== 连续执行编辑操作 ===")
rounds = 0
fail_at = None
try:
    for round_index in range(40):
        rounds += 1
        idx = round_index % len(doc.layers)
        # 1. 选中
        workspace.selectLayer(idx)
        pump(20)
        # 2. 移动
        workspace._set_layer_attrs(idx, {"x": 30 + round_index, "y": 40}, "移动")
        pump(20)
        # 3. 拖动式实时几何
        workspace.previewLiveGeometry(30 + round_index, 40, 760, 560)
        pump(16)
        # 4. 透明度
        workspace._set_layer_attr(idx, "opacity", 0.5 + (round_index % 5) * 0.1, "透明度")
        pump(20)
        # 5. 可见性
        workspace.toggleLayerVisible(idx)
        pump(20)
        workspace.toggleLayerVisible(idx)
        pump(20)
        # 6. 撤销
        if workspace.canUndo if hasattr(workspace, "canUndo") else doc.can_undo():
            workspace.undo() if hasattr(workspace, "undo") else doc.undo()
            pump(20)
        # 7. 重做
        if doc.can_redo():
            doc.redo()
            pump(20)
        # 8. 上移/下移
        workspace.moveSelectedLayer("forward")
        pump(20)
        workspace.moveSelectedLayer("backward")
        pump(20)

        if round_index % 5 == 0:
            print(f"  第 {round_index + 1} 轮...")
        if not alive(f"第 {round_index + 1} 轮"):
            fail_at = round_index + 1
            break
except Exception:
    print("\n!!! 抛出异常 !!!")
    traceback.print_exc()
    fail_at = rounds

print()
if fail_at:
    print(f">>> 在第 {fail_at} 轮出现问题")
else:
    print(f">>> 完成 {rounds} 轮连续操作，窗口始终存活")

alive("结束")
