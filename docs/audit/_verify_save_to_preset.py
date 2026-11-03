"""验证「把工作区改动保存回预设卡片」。

跑法：python -u docs/audit/_verify_save_to_preset.py
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image  # noqa: E402
from PySide6.QtCore import QCoreApplication  # noqa: E402

app = QCoreApplication.instance() or QCoreApplication(sys.argv)

from app.models.document import Document  # noqa: E402
from app.qml.preview_image_provider import PreviewImageProvider  # noqa: E402
from app.qml.viewmodels.preset_manager_view_model import PresetManagerViewModel  # noqa: E402
from app.qml.viewmodels.workspace_session_view_model import WorkspaceSessionViewModel  # noqa: E402
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel  # noqa: E402
from app.utils.preset_manager import PresetManager  # noqa: E402

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


WORK = tempfile.mkdtemp()
manager = PresetManager(app_dir=WORK, copy_initial=False)


def make_preset(title, page_names):
    docs = []
    for name in page_names:
        doc = Document()
        doc.create_new(400, 300)
        doc.tab_name = name
        doc.original_tab_name = name
        path = os.path.join(WORK, f"{title}_{name}.png")
        Image.new("RGBA", (240, 180), (60, 110, 160, 255)).save(path)
        doc.add_layer("原图层", 10, 20, 200, 150, image_source=path)
        docs.append(doc)
    return manager.save_preset_documents(title, "", docs)


preset_a = make_preset("卡片A", ["主图", "细节图"])
preset_b = make_preset("卡片B", ["B主图"])

workspace = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
sessions = WorkspaceSessionViewModel(workspace, include_initial_document=False)
vm = PresetManagerViewModel(workspace=workspace, sessions=sessions, manager=manager)

# ---------------- 1. 打开后修改内容并保存 ----------------
vm.loadPreset(preset_a)
check("打开 A 得到 2 页", sessions.count == 2, str(sessions.count))

# 模拟用户编辑：改画布尺寸 + 加一个图层（两者都能从 .cmp 读回来验证）
doc0 = sessions.documentAt(0)
doc0.canvas_width = 888
doc0.canvas_height = 666
doc0.add_layer("用户新加", 50, 60, 120, 90, image_source=None, is_folder=False)

result = vm.savePresetFromWorkspace(preset_a)
check("保存成功", result.get("ok") is True, str(result))
check("保存页数为 2", result.get("saved") == 2, str(result.get("saved")))

# 直接读磁盘验证（不靠内存）
raw = manager.load_preset(preset_a) or {}
pages = raw.get("documents") or []
check("磁盘上有 2 页", len(pages) == 2, str(len(pages)))
check("画布尺寸已保存", pages[0].get("canvas_width") == 888, str(pages[0].get("canvas_width")))
layer_names = [layer.get("name") for layer in pages[0].get("layers", [])]
check("新图层已保存", "用户新加" in layer_names, str(layer_names))

# ---------------- 2. 不能把别的预设的页写进来 ----------------
vm.loadPreset(preset_b)
before_count = sessions.count
result2 = vm.savePresetFromWorkspace(preset_a)
check("A 仍只保存自己的 2 页", result2.get("saved") == 2, str(result2.get("saved")))
raw_a = manager.load_preset(preset_a) or {}
names_a = [p.get("name") for p in raw_a.get("documents", [])]
check("没有混入 B 的页", "B主图" not in names_a, str(names_a))

# ---------------- 3. 未打开的预设不能保存 ----------------
other = make_preset("未打开", ["x"])
closed = vm.savePresetFromWorkspace(other)
check("未打开的预设保存被拒绝", closed.get("ok") is False, str(closed))
check("拒绝原因正确", closed.get("reason") == "not_open", str(closed.get("reason")))

# ---------------- 4. 改名后保存能存住页名 ----------------
vm.loadPreset(preset_b)
b_doc = sessions.documentAt(sessions.activeIndex)
b_doc.tab_name = "改过的名字"
b_doc.original_tab_name = "改过的名字"
vm.savePresetFromWorkspace(preset_b)
raw_b = manager.load_preset(preset_b) or {}
saved_name = (raw_b.get("documents") or [{}])[0].get("name")
check("改名后保存能存住", saved_name == "改过的名字", str(saved_name))

# ---------------- 5. 保存不应新建预设 ----------------
count_before = len(manager.get_all_presets())
vm.loadPreset(preset_a)
vm.savePresetFromWorkspace(preset_a)
count_after = len(manager.get_all_presets())
check("保存不新增预设条目", count_after == count_before, f"{count_before}->{count_after}")

# ---------------- 6. 重新加载拿到的是保存后的内容 ----------------
for index in range(sessions.count - 1, -1, -1):
    sessions.requestClose(index)
    if sessions.count > index:
        sessions.discardAndClose(index)
check("已清空工作区", sessions.count == 0, str(sessions.count))
vm.loadPreset(preset_a)
reloaded = sessions.documentAt(0)
check("重新加载画布尺寸正确", reloaded.canvas_width == 888, str(reloaded.canvas_width))
reloaded_names = [layer.name for layer in reloaded.layers]
check("重新加载新图层还在", "用户新加" in reloaded_names, str(reloaded_names))

# ---------------- 7. 模态判定：能保存 / 不能保存 ----------------
check("canSave 对已打开预设为 True", vm.canSavePresetFromWorkspace(preset_a) is True)
check("canSave 对未打开预设为 False", vm.canSavePresetFromWorkspace(other) is False)
check("openPageCount 正确", vm.openPageCount(preset_a) == 2, str(vm.openPageCount(preset_a)))

print()
print(f"总结：{_passed} passed, {_failed} failed")
sys.exit(0 if _failed == 0 else 1)
