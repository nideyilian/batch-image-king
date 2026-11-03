"""QML 层实测：页列表渲染 + 双击改名 + 清空确认 + 撤销。

加载真实 PresetWorkbench，用 QMetaObject 调用根对象上的 QML function，
走的是与用户点击完全相同的代码路径（beginTabRename / submitTabRename / ...）。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QMetaObject, QTimer, QUrl, Qt
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent

app = QGuiApplication.instance() or QGuiApplication(sys.argv)

from app.models.document import Document
from app.utils.preset_manager import PresetManager
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def pump(ms=40):
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
    doc = Document()
    doc.create_new(400, 300)
    doc.tab_name = name
    doc.original_tab_name = name
    doc.add_layer("L0", x, 20, 200, 150, image_source=None, is_folder=False)
    return doc


workdir = tempfile.mkdtemp()
manager = PresetManager(app_dir=workdir, copy_initial=False)
preset_id = manager.save_preset_documents(
    "QML测试预设", "", [_doc("第一页"), _doc("第二页", 30), _doc("第三页", 60)]
)

ws = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
vm = PresetManagerViewModel(workspace=ws, manager=manager)

engine = QQmlApplicationEngine()
engine.rootContext().setContextProperty("vm", vm)
# 直接实例化工作台并注入 vm（走属性而非 context，避免与组件内部 vm 绑定冲突）
qml_path = os.path.abspath("app/qml/components/PresetWorkbench.qml")
component2 = QQmlComponent(engine, QUrl.fromLocalFile(qml_path))
if component2.isError():
    for err in component2.errors():
        print("QML ERR:", err.toString())
    sys.exit(1)
root = component2.create()
if root is None:
    print("创建失败")
    sys.exit(1)

root.setProperty("vm", vm)
root.setProperty("width", 1400)
root.setProperty("height", 900)
pump(200)

print("=== 1. 选中卡片后页列表数据正确 ===")

# 用 selectPresetIndex 属性触发选中（QML 根对象的普通 function 不一定可被
# invokeMethod 找到，属性读写一定可用）
root.setProperty("selectPresetIndex", 0)
pump(100)
selected = root.property("selectedId")
check("选中了卡片", bool(selected), repr(selected))

item = None
items = vm.visiblePresets
for it in items:
    if it["id"] == selected:
        item = it
        break
check("能取到该卡片摘要", item is not None)
if item:
    check("tabTitles 有 3 项", len(item["tabTitles"]) == 3, str(len(item["tabTitles"])))
    check("页名正确", [t["title"] for t in item["tabTitles"]] == ["第一页", "第二页", "第三页"],
          str([t["title"] for t in item["tabTitles"]]))

print("\n=== 2. beginTabRename：进入编辑态 ===")
# 用桥接属性触发（QML 根对象的普通 function 无法被 invokeMethod 找到）
root.setProperty("requestTabRenameIndex", 1)
pump(80)

editing_index = root.property("editingTabIndex")
print(f"  editingTabIndex = {editing_index}")
print(f"  editingTabDraft = {root.property('editingTabDraft')!r}")

check("进入编辑态", root.property("editingTabIndex") == 1, str(root.property("editingTabIndex")))

print("\n=== 3. submitTabRename：提交并落盘 ===")
root.setProperty("editingTabDraft", "改过的第二页")
root.setProperty("requestSubmitTabRename", True)
pump(120)

data = manager.load_preset(preset_id)
names = [d.get("original_tab_name") or d.get("name") for d in data["documents"]]
check("磁盘已改名", names[1] == "改过的第二页", str(names))
check("退出编辑态", root.property("editingTabIndex") == -1, str(root.property("editingTabIndex")))
check("清空错误提示", root.property("tabRenameError") == "", repr(root.property("tabRenameError")))

print("\n=== 4. 非法名：留在编辑态并给红字 ===")
root.setProperty("requestTabRenameIndex", 0)
pump(60)
root.setProperty("editingTabDraft", "")
root.setProperty("requestSubmitTabRename", True)
pump(80)
check("空名 → 仍在编辑态", root.property("editingTabIndex") == 0, str(root.property("editingTabIndex")))
check("显示错误红字", len(root.property("tabRenameError")) > 0, repr(root.property("tabRenameError")))

print("\n=== 5. cancelTabRename：Esc 还原、零写入 ===")
before = [d.get("name") for d in manager.load_preset(preset_id)["documents"]]
root.setProperty("requestCancelTabRename", True)
pump(60)
after = [d.get("name") for d in manager.load_preset(preset_id)["documents"]]
check("退出编辑态", root.property("editingTabIndex") == -1)
check("错误提示清空", root.property("tabRenameError") == "")
check("磁盘未变", before == after, f"{before} -> {after}")

print("\n=== 6. 清空全部 + 撤销 ===")
root.setProperty("requestClearTabsDialog", True)
pump(80)
check("弹窗拿到待确认 id", root.property("pendingClearTabsId") == preset_id,
      repr(root.property("pendingClearTabsId")))

root.setProperty("requestConfirmClearTabs", True)
pump(150)
data = manager.load_preset(preset_id)
check("磁盘已清空", data["documents"] == [], str(data.get("documents")))
check("待确认 id 复位", root.property("pendingClearTabsId") == "")

# 撤销
result = vm.undoClearDocuments(preset_id)
pump(80)
check("撤销成功", result["ok"] is True, str(result))
data = manager.load_preset(preset_id)
check("恢复到 3 页", len(data["documents"]) == 3, str(len(data["documents"])))

print()
print("=== 总结:", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
