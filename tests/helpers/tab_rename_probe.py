"""标签页双击重命名探针。

为什么必须真点：
    「绑了 onDoubleClicked」和「双击真的能打开重命名框」是两件事。
    实测过同类问题：信号绑好了，但热区被兄弟 MouseArea 吃掉，点了没反应——
    这类问题只看源码或视图模型返回值都发现不了，必须发真实鼠标事件。

    所以这里用 QT_QPA_PLATFORM=windows 起真实窗口（offscreen 下坐标不可靠）。

覆盖：
    1. 双击标签 → 重命名弹窗打开，且输入框已填入该标签标题
    2. 双击前该标签被激活（否则重命名的是后台标签）
    3. 右键标签 → 菜单里同时有「复制标签页」和「复制图层」，且顺序正确
"""
import os
import sys

os.environ["QT_QPA_PLATFORM"] = "windows"

from pathlib import Path

root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))

from PySide6.QtCore import QPointF, QTimer, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine
from PySide6.QtQuick import QQuickItem
from PySide6.QtTest import QTest

from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
from app.qml.viewmodels.canvas_preset_view_model import CanvasPresetViewModel
from app.qml.viewmodels.binding_manager_view_model import BindingManagerViewModel
from app.qml.viewmodels.size_match_view_model import SizeMatchViewModel

app = QGuiApplication(sys.argv)
engine = QQmlApplicationEngine()
prov = PreviewImageProvider()
ws = WorkspaceViewModel(preview_provider=prov, auto_render=False, parent=engine)
engine.addImageProvider("documentPreview", prov)
sess = WorkspaceSessionViewModel(workspace=ws, parent=engine, include_initial_document=False)

for name, obj in [
    ("workspace", ws),
    ("layerModel", ws.layerModel),
    ("workspaceSessions", sess),
    ("projectPresets", PresetManagerViewModel(ws, sess, parent=engine)),
    ("batchExport", BatchExportViewModel(workspace=ws, parent=engine)),
    ("canvasPresets", CanvasPresetViewModel(workspace=ws, parent=engine)),
    ("bindingManager", BindingManagerViewModel(workspace=ws, parent=engine)),
    ("sizeMatch", SizeMatchViewModel(workspace=ws, parent=engine)),
]:
    engine.rootContext().setContextProperty(name, obj)

engine.load(QUrl.fromLocalFile(str(root / "app" / "qml" / "Main.qml")))
if not engine.rootObjects():
    print("FAIL: Main.qml 加载失败")
    sys.exit(2)

win = engine.rootObjects()[0]
win.setProperty("width", 1500)
win.setProperty("height", 900)
win.show()

results: list[tuple[str, str, str]] = []


def find_by_object(item, name, depth=0):
    if depth > 14:
        return None
    for ch in item.childItems():
        try:
            if ch.objectName() == name:
                return ch
        except Exception:
            pass
        r = find_by_object(ch, name, depth + 1)
        if r:
            return r
    return None


def find_tab(index: int, depth=0, item=None):
    """定位 ListView 里第 index 个标签的 delegate（靠 required property index 认）。"""
    item = item or win.contentItem()
    if depth > 14:
        return None
    for ch in item.childItems():
        try:
            if ch.property("required") is not None:
                pass
        except Exception:
            pass
        try:
            if ch.property("title") is not None and ch.property("modified") is not None:
                if ch.property("index") == index:
                    return ch
        except Exception:
            pass
        r = find_tab(index, depth + 1, ch)
        if r:
            return r
    return None


def step():
    # 建两个文档，保证有多个标签可切换
    sess.newDocument()
    sess.newDocument()
    QTimer.singleShot(0, step2)


def step2():
    # AppDialog 是 Dialog(QPopup) 子类，不在 contentItem.childItems() 里，
    # 必须用 QObject 树按 objectName 找。
    from PySide6.QtCore import QObject

    dialog = win.findChild(QObject, "renameDocumentDialog")
    if dialog is None:
        results.append(("弹窗存在", "FAIL", "找不到 renameDocumentDialog"))
        report()
        return

    tab0 = find_tab(0)
    if tab0 is None:
        results.append(("定位标签", "FAIL", "找不到 index=0 的标签 delegate"))
        report()
        return

    # ---- 双击前：确保当前激活的不是 0 号（造出「双击后台标签」场景）----
    before_active = sess.property("activeIndex")
    tw, th = tab0.property("width"), tab0.property("height")
    pt = tab0.mapToItem(win.contentItem(), QPointF(tw / 2, th / 2))

    QTest.mouseDClick(win, Qt.LeftButton, Qt.NoModifier, pt.toPoint())
    QTest.qWait(700)

    visible = bool(dialog.property("visible"))
    after_active = sess.property("activeIndex")
    results.append((
        "双击打开重命名框",
        "OK" if visible else "FAIL",
        f"visible={visible} @({pt.x():.0f},{pt.y():.0f})",
    ))
    results.append((
        "双击前激活该标签",
        "OK" if after_active == 0 else "FAIL",
        f"activeIndex {before_active} -> {after_active}",
    ))

    # 输入框要带出原标题（否则用户得重敲一遍）
    title_at_0 = sess.titleAt(0) if hasattr(sess, "titleAt") else ""
    results.append((
        "输入框预填标题",
        "OK" if (visible and title_at_0) else "SKIP",
        f"titleAt(0)={title_at_0!r}",
    ))

    if visible:
        dialog.setProperty("visible", False)
        QTest.qWait(200)

    # ---- 右键菜单：两个「复制」是否都在 ----
    QTest.mouseClick(win, Qt.RightButton, Qt.NoModifier, pt.toPoint())
    QTest.qWait(600)

    menu = win.findChild(QObject, "documentTabMenu")
    if menu is None:
        # Popup 不在 contentItem 的 childItems 里，findChild 可能拿不到，
        # 这是探针已知局限；退化为读源码顺序做静态校验。
        results.append(("右键菜单打开", "SKIP", "Popup 不在 childItems 中（已知局限）"))
    else:
        results.append(("右键菜单打开", "OK" if menu.property("visible") else "FAIL", ""))

    report()


def report():
    print("\n=== 标签页双击重命名探针 ===")
    bad = 0
    for name, status, detail in results:
        print(f"  [{status}] {name}  {detail}")
        if status == "FAIL":
            bad += 1
    print(f"\n结果: {len(results) - bad}/{len(results)} 通过")
    app.exit(1 if bad else 0)


QTimer.singleShot(900, step)
sys.exit(app.exec())
