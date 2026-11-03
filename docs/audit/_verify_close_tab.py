"""单页关闭实测：PMVM + QML 两层，重点验证「关到空后撤销能还原真实图层内容」。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlComponent, QQmlApplicationEngine

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


def _doc(name, x=10, layers=1):
    doc = Document()
    doc.create_new(400, 300)
    doc.tab_name = name
    doc.original_tab_name = name
    for i in range(layers):
        doc.add_layer(f"L{i}", x + i * 5, 20, 200, 150, image_source=None, is_folder=False)
    return doc


workdir = tempfile.mkdtemp()
manager = PresetManager(app_dir=workdir, copy_initial=False)
preset_id = manager.save_preset_documents(
    "关闭测试", "", [_doc("第一页", 10, 2), _doc("第二页", 30, 3), _doc("第三页", 60, 1)]
)


class _WS:
    operationsBlocked = False

    def _set_status(self, *_a, **_k):
        pass


vm = PresetManagerViewModel(workspace=_WS(), manager=manager)

print("=== 1. 关闭中间页：其余页顺序正确 ===")
res = vm.closeDocument(preset_id, 1)
check("ok", res["ok"] is True, str(res))
check("remaining=2", res["remaining"] == 2, str(res.get("remaining")))
check("返回被关页名", res["title"] == "第二页", repr(res.get("title")))
names = [t["title"] for t in vm.tabTitles(preset_id)]
check("页名顺序", names == ["第一页", "第三页"], str(names))
data = manager.load_preset(preset_id)
check("磁盘 2 页", len(data["documents"]) == 2, str(len(data["documents"])))

print("\n=== 2. 关闭后卡片页数同步 ===")
card = next(p for p in vm.presets if p["id"] == preset_id)
check("documentCount=2", card["documentCount"] == 2, str(card["documentCount"]))
check("tabTitles 同步", len(card["tabTitles"]) == 2, str(len(card["tabTitles"])))

print("\n=== 3. 撤销能还原被关页的真实图层 ===")
undo = vm.undoClearDocuments(preset_id)
check("撤销 ok", undo["ok"] is True, str(undo))
check("恢复 3 页", undo["restored"] == 3, str(undo.get("restored")))
data = manager.load_preset(preset_id)
check("第二页回来了", data["documents"][1]["name"] == "第二页", data["documents"][1]["name"])
check("第二页的 3 个图层都在", len(data["documents"][1]["layers"]) == 3,
      str(len(data["documents"][1]["layers"])))
check("图层名完整", [l["name"] for l in data["documents"][1]["layers"]] == ["L0", "L1", "L2"],
      str([l["name"] for l in data["documents"][1]["layers"]]))

print("\n=== 4. 关到空：预设保留 + 空态 ===")
vm.closeDocument(preset_id, 0)
vm.closeDocument(preset_id, 0)
res = vm.closeDocument(preset_id, 0)
check("最后一页关闭 ok", res["ok"] is True, str(res))
check("remaining=0", res["remaining"] == 0, str(res.get("remaining")))
data = manager.load_preset(preset_id)
check("磁盘为空", data["documents"] == [], str(data.get("documents")))
check("预设本身还在", data.get("name") == "关闭测试", repr(data.get("name")))
card = next(p for p in vm.presets if p["id"] == preset_id)
check("卡片页数 0", card["documentCount"] == 0, str(card["documentCount"]))
check("空预设打不开", vm.loadPreset(preset_id) == 0)

print("\n=== 5. 关到空后撤销能还原最后一页 ===")
undo = vm.undoClearDocuments(preset_id)
check("撤销 ok", undo["ok"] is True, str(undo))
data = manager.load_preset(preset_id)
check("恢复 1 页", len(data["documents"]) == 1, str(len(data["documents"])))
check("页名正确", data["documents"][0]["name"] == "第三页", data["documents"][0]["name"])
check("图层内容在", len(data["documents"][0]["layers"]) == 1,
      str(len(data["documents"][0]["layers"])))

print("\n=== 6. 越界/缺失 ===")
check("越界页号", vm.closeDocument(preset_id, 9)["reason"] == "page_missing")
check("不存在预设", vm.closeDocument("nope", 0)["reason"] == "preset_missing")

print("\n=== 7. QML 层：菜单项与确认弹窗 ===")
engine = QQmlApplicationEngine()
qml_path = os.path.abspath("app/qml/components/PresetWorkbench.qml")
component = QQmlComponent(engine, QUrl.fromLocalFile(qml_path))
if component.isError():
    for err in component.errors():
        print("QML ERR:", err.toString())
    sys.exit(1)
root = component.create()
root.setProperty("vm", vm)
root.setProperty("width", 1400)
root.setProperty("height", 900)
pump(150)
root.setProperty("selectPresetIndex", 0)
pump(100)
check("选中卡片", bool(root.property("selectedId")), repr(root.property("selectedId")))

# 恢复成 3 页，便于测 QML 关闭
before_titles = [t["title"] for t in vm.tabTitles(root.property("selectedId"))]
print(f"  当前页：{before_titles}")

root.setProperty("requestCloseTabIndex", 0)
pump(80)
check("弹窗记下待关页", root.property("pendingCloseTabIndex") == 0,
      str(root.property("pendingCloseTabIndex")))

root.setProperty("requestConfirmCloseTab", True)
pump(150)
after_titles = [t["title"] for t in vm.tabTitles(root.property("selectedId"))]
check("QML 关闭后少一页", len(after_titles) == len(before_titles) - 1,
      f"{before_titles} -> {after_titles}")
check("待关下标复位", root.property("pendingCloseTabIndex") == -1)

print()
print("=== 总结:", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
