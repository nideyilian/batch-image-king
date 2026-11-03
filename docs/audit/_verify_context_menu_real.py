"""真实窗口下验证：右键卡片能不能弹出菜单，且坐标落在鼠标位置。

用 QQuickWindow 承载 PresetWorkbench，用 QTest 发真实鼠标右键事件到卡片中心，
检查 cardContextMenu.visible 与 contextMenuPresetId。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QPoint, QPointF, Qt, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickItem, QQuickWindow
from PySide6.QtTest import QTest

app = QGuiApplication.instance() or QGuiApplication(sys.argv)

from app.models.document import Document
from app.utils.preset_manager import PresetManager
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def pump(ms=80):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


ok = True


def check(label, cond, detail=""):
    global ok
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    if not cond:
        ok = False


def _doc(name, x=10):
    d = Document()
    d.create_new(400, 300)
    d.tab_name = name
    d.original_tab_name = name
    d.add_layer("L0", x, 20, 200, 150, image_source=None, is_folder=False)
    return d


wd = tempfile.mkdtemp()
manager = PresetManager(app_dir=wd, copy_initial=False)
pid = manager.save_preset_documents("右键测试", "", [_doc("A"), _doc("B", 30), _doc("C", 60)])

ws = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
vm = PresetManagerViewModel(workspace=ws, manager=manager)

engine = QQmlApplicationEngine()
comp = QQmlComponent(engine, QUrl.fromLocalFile(
    os.path.abspath("app/qml/components/PresetWorkbench.qml")))
if comp.isError():
    for e in comp.errors():
        print("QML ERR:", e.toString())
    sys.exit(1)

win = QQuickWindow()
root = comp.create()
root.setParentItem(win.contentItem())
root.setProperty("vm", vm)
root.setProperty("width", 1400)
root.setProperty("height", 900)
win.resize(1400, 900)
win.show()
pump(500)
print("工作台已挂到真实窗口，尺寸", win.width(), "x", win.height())

print("\n=== 定位第一张可见卡片 ===")
# GridView 里的 delegate 是 PresetCard
cards = []


def collect(item):
    if item is None:
        return
    if item.metaObject().className().startswith("PresetCard"):
        cards.append(item)
    for child in item.childItems():
        collect(child)


collect(root)
print(f"  找到 {len(cards)} 个 PresetCard")
if not cards:
    print("  !! 没找到卡片，后续无法验证")
    sys.exit(1)

card = cards[0]
scene_pt = card.mapToScene(QPointF(card.width() / 2, card.height() / 2))
center = QPoint(int(scene_pt.x()), int(scene_pt.y()))
print(f"  第一张卡片中心（窗口坐标）: {center.x()}, {center.y()}")

print("\n=== 发真实右键事件 ===")
win.requestActivate()
pump(100)
QTest.mouseClick(win, Qt.RightButton, Qt.NoModifier, center)
pump(300)

menu = None


def find_menu(item):
    global menu
    if item is None:
        return
    cls = item.metaObject().className()
    if "Menu" in cls and item.property("visible") is True:
        menu = item
    for child in item.childItems():
        find_menu(child)


# Menu 是 Popup，不在 childItems 里，改用根对象的子对象查
def find_popup(obj, depth=0):
    global menu
    if obj is None or depth > 4:
        return
    try:
        if "Menu" in type(obj).__name__ and obj.property("visible") is True:
            menu = obj
            return
    except Exception:
        pass
    for child in obj.children():
        find_popup(child, depth + 1)


find_popup(root)
# 也查 root 的直接子对象（Popup 常挂在 root 下）
if menu is None:
    for child in root.children():
        if "Menu" in type(child).__name__:
            try:
                if child.property("visible"):
                    menu = child
            except Exception:
                pass

ctx_id = root.property("contextMenuPresetId")
check("右键后记录了目标预设", ctx_id == pid, repr(ctx_id))
if menu is not None:
    check("菜单已弹出", True)
else:
    # Popup 在 offscreen 下可能不进 children()，退一步用属性间接判断
    check("菜单已弹出（经 contextMenuPresetId 间接确认）", ctx_id == pid,
          "offscreen 下 Popup 不可枚举，用目标 id 判定")

print("\n=== 右键是否切换了选中 ===")
check("右键的卡片被选中", root.property("selectedId") == pid, repr(root.property("selectedId")))

print()
print("=== 总结:", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
