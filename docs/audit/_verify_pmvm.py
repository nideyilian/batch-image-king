"""PMVM 层实测：校验规则、改名、清空、撤销、busy 互斥。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document
from app.utils.preset_manager import PresetManager
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

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
    "预设A", "desc", [_doc("主图"), _doc("细节图", 30), _doc("场景图", 60)]
)

ws = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
vm = PresetManagerViewModel(workspace=ws, manager=manager)

print(f"预设 id={preset_id}")

print("\n=== 1. tabTitles 与卡片同源 ===")
titles = vm.tabTitles(preset_id)
check("返回 3 页", len(titles) == 3, str(len(titles)))
check("页名正确", [t["title"] for t in titles] == ["主图", "细节图", "场景图"],
      str([t["title"] for t in titles]))
check("封面标记在第0页", [t["isCover"] for t in titles] == [True, False, False],
      str([t["isCover"] for t in titles]))
card = next(p for p in vm.presets if p["id"] == preset_id)
check("卡片也带 tabTitles", len(card["tabTitles"]) == 3, str(len(card["tabTitles"])))
check("卡片页数与页列表一致", card["documentCount"] == len(card["tabTitles"]),
      f"{card['documentCount']} vs {len(card['tabTitles'])}")

print("\n=== 2. 校验规则（按序短路）===")
v = vm.validateDocumentTitle(preset_id, 0, "   ")
check("空名被拒", v["ok"] is False and v["reason"] == "empty", v.get("reason"))
v = vm.validateDocumentTitle(preset_id, 0, "x" * 41)
check("41 字符被拒", v["ok"] is False and v["reason"] == "too_long", v.get("reason"))
v = vm.validateDocumentTitle(preset_id, 0, "x" * 40)
check("40 字符通过", v["ok"] is True, str(v))
v = vm.validateDocumentTitle(preset_id, 0, "中" * 40)
check("40 个中文字通过（按字符不按字节）", v["ok"] is True, str(v))
v = vm.validateDocumentTitle(preset_id, 0, "a\nb")
check("换行被拒", v["ok"] is False and v["reason"] == "control_char", v.get("reason"))
v = vm.validateDocumentTitle(preset_id, 0, "细节图")
check("同预设重名被拒", v["ok"] is False and v["reason"] == "duplicate", v.get("reason"))
v = vm.validateDocumentTitle(preset_id, 0, "细节图  ")
check("只差空白的重名也被拒", v["ok"] is False and v["reason"] == "duplicate", v.get("reason"))
v = vm.validateDocumentTitle(preset_id, 0, "主图")
check("改成自己原名 → changed=False", v["ok"] is True and v["changed"] is False, str(v))
v = vm.validateDocumentTitle(preset_id, 0, "  主图  ")
check("首尾空白算同值", v["ok"] is True and v["changed"] is False, str(v))
v = vm.validateDocumentTitle(preset_id, 0, "新名字")
check("正常改名 changed=True", v["ok"] is True and v["changed"] is True, str(v))
v = vm.validateDocumentTitle(preset_id, 9, "新名字")
check("越界页号被拒", v["ok"] is False and v["reason"] == "page_missing", v.get("reason"))

print("\n=== 3. renameDocument 写盘 + 信号粒度 ===")
signals = {"titles": 0, "presets": 0}
vm.documentTitlesChanged.connect(lambda _pid: signals.__setitem__("titles", signals["titles"] + 1))
vm.presetsChanged.connect(lambda: signals.__setitem__("presets", signals["presets"] + 1))
res = vm.renameDocument(preset_id, 1, "改名成功")
check("改名 ok", res["ok"] is True and res["changed"] is True, str(res))
check("发 documentTitlesChanged", signals["titles"] == 1, str(signals["titles"]))
check("不发 presetsChanged（避免整屏卡片闪）", signals["presets"] == 0, str(signals["presets"]))
data = manager.load_preset(preset_id)
check("磁盘上 name 已改", data["documents"][1]["name"] == "改名成功", data["documents"][1]["name"])
check("磁盘上 original_tab_name 已改",
      data["documents"][1]["original_tab_name"] == "改名成功",
      data["documents"][1]["original_tab_name"])
check("页列表读到新名", vm.tabTitles(preset_id)[1]["title"] == "改名成功",
      vm.tabTitles(preset_id)[1]["title"])

signals["titles"] = 0
res = vm.renameDocument(preset_id, 1, "改名成功")
check("改成同名 → changed=False 且不发信号",
      res["ok"] is True and res["changed"] is False and signals["titles"] == 0, str(res))

print("\n=== 4. 校验失败不写盘 ===")
before = manager.load_preset(preset_id)["documents"][0]["name"]
res = vm.renameDocument(preset_id, 0, "")
check("空名 → validate 失败", res["ok"] is False and res["reason"] == "empty", str(res))
after = manager.load_preset(preset_id)["documents"][0]["name"]
check("磁盘未被改动", before == after, f"{before} -> {after}")

print("\n=== 5. closeAllDocuments ===")
signals["presets"] = 0
cleared_signals = {"n": 0}
vm.documentsCleared.connect(lambda _pid: cleared_signals.__setitem__("n", cleared_signals["n"] + 1))
res = vm.closeAllDocuments(preset_id, False)
check("清空 ok", res["ok"] is True, str(res))
check("cleared=3", res.get("cleared") == 3, str(res.get("cleared")))
check("发 documentsCleared", cleared_signals["n"] == 1, str(cleared_signals["n"]))
check("发 presetsChanged", signals["presets"] >= 1, str(signals["presets"]))
data = manager.load_preset(preset_id)
check("磁盘 documents 为空", data["documents"] == [], str(data.get("documents")))
card = next(p for p in vm.presets if p["id"] == preset_id)
check("卡片 documentCount=0", card["documentCount"] == 0, str(card["documentCount"]))
check("卡片 tabTitles 为空", card["tabTitles"] == [], str(card["tabTitles"]))
check("预设本身仍在", manager.load_preset(preset_id) is not None)

print("\n=== 6. 空预设再清空 ===")
res = vm.closeAllDocuments(preset_id, False)
check("再清空 → no_documents", res["ok"] is False and res["reason"] == "no_documents", str(res))

print("\n=== 7. 撤销恢复 ===")
res = vm.undoClearDocuments(preset_id)
check("撤销 ok", res["ok"] is True, str(res))
check("恢复到 3 页", res.get("restored") == 3, str(res.get("restored")))
data = manager.load_preset(preset_id)
check("磁盘恢复 3 页", len(data["documents"]) == 3, str(len(data["documents"])))
check("页名一并恢复", [d["name"] for d in data["documents"]] == ["主图", "改名成功", "场景图"],
      str([d["name"] for d in data["documents"]]))
res = vm.undoClearDocuments(preset_id)
check("重复撤销 → no_undo", res["ok"] is False and res["reason"] == "no_undo", str(res))

print("\n=== 8. 不存在/损坏的预设 ===")
res = vm.renameDocument("不存在的id", 0, "x")
check("不存在 → preset_missing", res["ok"] is False and res["reason"] == "preset_missing", str(res))
res = vm.closeAllDocuments("不存在的id", False)
check("清空不存在 → preset_missing", res["ok"] is False and res["reason"] == "preset_missing", str(res))

print("\n=== 9. busy 状态位 ===")
check("初始不 busy", vm.busy is False)
vm._set_busy(True, "测试中")
check("busy 生效", vm.busy is True and vm.busyReason == "测试中", f"{vm.busy}/{vm.busyReason}")
res = vm.renameDocument(preset_id, 0, "并发改名")
check("busy 期间改名被拒", res["ok"] is False and res["reason"] == "busy", str(res))
vm._set_busy(False)
check("解除 busy", vm.busy is False and vm.busyReason == "")

print()
print("=== 总结:", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
