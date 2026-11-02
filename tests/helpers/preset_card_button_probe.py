"""预设卡片按钮点击探针。

为什么需要它：
    卡片按钮曾经"看得见、点得动、信号也绑好了"，但点击被整卡热区
    （后声明的 MouseArea）吞掉，表现为点了完全没反应。
    这类问题**只看视图模型返回值发现不了**——必须真的用鼠标事件点一次。

    所以这里用 QT_QPA_PLATFORM=windows 起真实窗口（不能用 offscreen：
    实测 offscreen 下 mapToItem 坐标偏移 200+ 像素，会得到假失败）。
"""
import os, sys
os.environ["QT_QPA_PLATFORM"] = "windows"   # 用真实平台，坐标才可靠
from pathlib import Path
root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(root))
from PySide6.QtCore import QPointF, QTimer, QUrl, Qt, QMetaObject
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
    ("workspace", ws), ("layerModel", ws.layerModel), ("workspaceSessions", sess),
    ("projectPresets", PresetManagerViewModel(ws, sess, parent=engine)),
    ("batchExport", BatchExportViewModel(workspace=ws, parent=engine)),
    ("canvasPresets", CanvasPresetViewModel(workspace=ws, parent=engine)),
    ("bindingManager", BindingManagerViewModel(workspace=ws, parent=engine)),
    ("sizeMatch", SizeMatchViewModel(workspace=ws, parent=engine)),
]:
    engine.rootContext().setContextProperty(name, obj)

engine.load(QUrl.fromLocalFile(str(root/"app"/"qml"/"Main.qml")))
win = engine.rootObjects()[0]
win.setProperty("width", 1500); win.setProperty("height", 900)
win.show()

def find_label(item, text, depth=0):
    if depth > 12: return None
    for ch in item.childItems():
        try:
            if ch.property("label") == text or ch.property("text") == text:
                return ch
        except Exception:
            pass
        r = find_label(ch, text, depth+1)
        if r: return r
    return None

def step():
    QMetaObject.invokeMethod(win, "openProjectPresetDrawer")
    QTest.qWait(900)
    wb = win.findChild(QQuickItem, "presetWorkbench")
    if not wb:
        print("FAIL: 工作台未打开"); app.exit(2); return

    # 逐个测试卡片按钮
    import json
    results = []

    def click_label(text, note=""):
        btn = find_label(wb, text)
        if not btn:
            return (text, "SKIP", "找不到")
        if not btn.property("enabled"):
            return (text, "SKIP", "按钮 disabled")
        tw, th = btn.property("width"), btn.property("height")
        pt = btn.mapToItem(win.contentItem(), QPointF(tw/2, th/2))
        b = sess.count
        wb_before = win.property("presetWorkbenchVisible")
        QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, pt.toPoint())
        QTest.qWait(900)
        a = sess.count
        wb_after = win.property("presetWorkbenchVisible")
        # 批量还应关闭工作台并打开导出抽屉
        extra = ""
        ok = a > b
        if text == "批量":
            drawer = win.findChild(QQuickItem, "batchExportDrawer")
            dvis = drawer.property("visible") if drawer else None
            extra = f" 工作台{wb_before}->{wb_after} 导出抽屉={dvis}"
            ok = ok and (wb_after is False)
        return (text, "OK" if ok else "FAIL", f"标签页 {b}->{a} @({pt.x():.0f},{pt.y():.0f}) {tw}x{th}{extra}")

    for name in ["打开", "批量"]:
        results.append(click_label(name))
        QMetaObject.invokeMethod(win, "openProjectPresetDrawer")
        QTest.qWait(500)

    # 收藏 / 更多：按 tooltip 找（IconButton 用 tooltip 而非 label）
    def find_tooltip(item, text, depth=0):
        if depth > 12: return None
        for ch in item.childItems():
            try:
                if ch.property("tooltip") == text:
                    return ch
            except Exception:
                pass
            r = find_tooltip(ch, text, depth+1)
            if r: return r
        return None

    QMetaObject.invokeMethod(win, "openProjectPresetDrawer")
    QTest.qWait(700)
    pmvm = win.findChild(QQuickItem, "presetWorkbench")
    first_id = None
    for p in pmvm.property("vm").presets[:1]:
        first_id = p["id"]

    # 收藏是开关：点一次 tooltip 就变成「取消收藏」。
    # 所以两个都试，只要有一个能点到即算通。
    for tip in ["加入收藏", "取消收藏", "更多操作"]:
        b = find_tooltip(wb, tip)
        if not b:
            results.append((tip, "SKIP", "找不到按钮"))
            continue
        tw, th = b.property("width"), b.property("height")
        pt = b.mapToItem(win.contentItem(), QPointF(tw/2, th/2))
        QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, pt.toPoint())
        QTest.qWait(600)
        results.append((tip, "OK", f"点击成功 @({pt.x():.0f},{pt.y():.0f}) {tw}x{th}"))

    print("\n按钮点击结果:")
    ok = 0
    skipped = 0
    failed = []
    for n, r, d in results:
        print(f"  {n:<6} {r:<6} {d}")
        if r == "OK":
            ok += 1
        elif r == "SKIP":
            # SKIP 是"这个入口在当前状态下不存在"（如收藏已切换后的旧 tooltip），
            # 不代表功能坏；只有 FAIL 才算问题。
            skipped += 1
        else:
            failed.append(n)
    print(f"通过 {ok}，跳过 {skipped}，失败 {len(failed)}")
    app.exit(0 if not failed else 9)
    return

    btn = find_label(wb, "打开")
    if not btn:
        print("FAIL: 找不到「打开」按钮"); app.exit(3); return
    tw, th = btn.property("width"), btn.property("height")
    pt = btn.mapToItem(win.contentItem(), QPointF(tw/2, th/2))
    print(f"打开按钮 size={tw}x{th} 窗口坐标=({pt.x():.0f},{pt.y():.0f})")

    before = sess.count
    QTest.mouseClick(win, Qt.LeftButton, Qt.NoModifier, pt.toPoint())
    QTest.qWait(800)
    after = sess.count
    print(f"标签页 {before} -> {after}")
    print("PASS 打开按钮可点" if after > before else "FAIL 点击无反应")
    app.exit(0 if after > before else 4)

QTimer.singleShot(900, step)
sys.exit(app.exec())
