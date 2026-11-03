"""验证「同一预设卡片只对应一套标签页」：重复点击不新建，而是激活已有页。

跑法：python -u docs/audit/_verify_preset_dedup.py
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
        image_path = os.path.join(WORK, f"{title}_{name}.png")
        Image.new("RGBA", (240, 180), (60, 110, 160, 255)).save(image_path)
        doc.add_layer("L0", 10, 20, 200, 150, image_source=image_path)
        docs.append(doc)
    return manager.save_preset_documents(title, "", docs)


preset_a = make_preset("卡片A", ["A-主图", "A-细节", "A-场景"])
preset_b = make_preset("卡片B", ["B-主图", "B-细节"])
preset_c = make_preset("卡片C", ["A-主图"])  # 故意与 A 同名页，测标题撞车

workspace = WorkspaceViewModel(preview_provider=PreviewImageProvider(), auto_render=False)
sessions = WorkspaceSessionViewModel(workspace)
# 清掉初始空文档，避免干扰计数
while sessions.count > 0:
    sessions.requestClose(0)
    if sessions.count > 0:
        sessions.discardAndClose(0)
vm = PresetManagerViewModel(workspace=workspace, sessions=sessions, manager=manager)
print(f"初始标签页数: {sessions.count}")

# ---------------- 场景 1：首次点击正常打开 ----------------
loaded = vm.loadPreset(preset_a)
check("首次点击打开全部 3 页", loaded == 3 and sessions.count == 3, f"loaded={loaded} count={sessions.count}")

# ---------------- 场景 2：重复点击不新建 ----------------
first_active = sessions.activeIndex
for round_index in range(5):
    again = vm.loadPreset(preset_a)
    if sessions.count != 3:
        break
check("重复点击 5 次不产生新标签页", sessions.count == 3, f"count={sessions.count}")
check("重复点击返回值等于已打开页数", again == 3, str(again))

# ---------------- 场景 3：切换后处于前台 ----------------
# 先切到别的标签页，再点卡片，必须切回来
if sessions.count >= 3:
    sessions.activateDocument(2)
    check("先切到第 3 页", sessions.activeIndex == 2, str(sessions.activeIndex))
    vm.loadPreset(preset_a)
    check("点卡片后切回该预设的第 1 页", sessions.activeIndex == 0, str(sessions.activeIndex))
    active_doc = sessions.documentAt(sessions.activeIndex)
    check(
        "前台文档确实是该预设的页",
        str(getattr(active_doc, "source_preset_id", "")) == preset_a,
        str(getattr(active_doc, "source_preset_id", "")),
    )

# ---------------- 场景 4：不同预设互不干扰 ----------------
vm.loadPreset(preset_b)
check("打开卡片B 后总数为 5", sessions.count == 5, str(sessions.count))
vm.loadPreset(preset_a)
check("再点卡片A 仍为 5（不新增）", sessions.count == 5, str(sessions.count))
check("切到了 A 的第 1 页", sessions.activeIndex == 0, str(sessions.activeIndex))

# ---------------- 场景 5：同名页不算同一预设 ----------------
# 卡片C 的唯一页名与卡片A 第一页相同（都叫 A-主图），必须视为不同预设
vm.loadPreset(preset_c)
check("同名页的不同预设会正常打开", sessions.count == 6, str(sessions.count))
c_index = sessions.activeIndex
c_doc = sessions.documentAt(c_index)
check(
    "名片C 的标签页来源是 C 不是 A",
    str(getattr(c_doc, "source_preset_id", "")) == preset_c,
    str(getattr(c_doc, "source_preset_id", "")),
)
vm.loadPreset(preset_c)
check("重复点名片C 不新增", sessions.count == 6, str(sessions.count))

# ---------------- 场景 6：部分关闭后再次点击只激活，不补齐 ----------------
# 语义边界：用户要求「已存在就激活，不要新建」。
# 因此「用户主动关掉了其中几页」也走激活路径 —— 尊重用户的关闭动作，
# 不能因为他又点了一下卡片就把关掉的页全塞回来。
# （补齐能力保留在 open_preset_pages 里，供将来"恢复全部页"之类的显式操作使用。）
sessions.requestClose(2)
if sessions.count > 5:
    sessions.discardAndClose(2)
sessions.requestClose(1)
if sessions.count > 4:
    sessions.discardAndClose(1)
print(f"  关掉两页后标签页数: {sessions.count}（应为 4）")
check("关掉 A 的两页后剩 4 个", sessions.count == 4, str(sessions.count))

before_ids = {id(sessions.documentAt(i)) for i in range(sessions.count)}
reloaded = vm.loadPreset(preset_a)
after_ids = {id(sessions.documentAt(i)) for i in range(sessions.count)}
check("部分已打开时点击不补齐（尊重用户的关闭）", sessions.count == 4, str(sessions.count))
check("原有页对象被复用（没有重建）", before_ids == after_ids, "有旧页被替换")
check("返回值等于剩余已打开页数", reloaded == 1, str(reloaded))
check("激活到了剩下的那一页", sessions.activeIndex == 0, str(sessions.activeIndex))

# ---------------- 场景 7：全部关闭后重开应正常（不是"幽灵已存在"）----------------
for index in range(sessions.count - 1, -1, -1):
    sessions.requestClose(index)
    if sessions.count > index:
        sessions.discardAndClose(index)
print(f"  全部关闭后: {sessions.count}")
reopened = vm.loadPreset(preset_a)
check("全关后重开正常打开 3 页", reopened == 3 and sessions.count == 3, f"reopened={reopened} count={sessions.count}")

# ---------------- 场景 8：来源标记不写进预设文件 ----------------
raw = manager.load_preset(preset_a) or {}
serialized = raw.get("documents", [{}])[0]
check(
    "来源标记没有污染 .cmp",
    "source_preset_id" not in serialized and "source_preset_page" not in serialized,
    str([k for k in serialized if "source" in k]),
)

print()
print(f"总结：{_passed} passed, {_failed} failed")
sys.exit(0 if _failed == 0 else 1)
