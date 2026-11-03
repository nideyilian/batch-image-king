"""PM 层实测：原地改写 .cmp 的四个方法是否真的落盘且索引同步。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from PIL import Image

from app.models.document import Document
from app.utils.preset_manager import PresetManager


def _doc(name, x=10, w=200, h=150):
    doc = Document()
    doc.create_new(400, 300)
    doc.tab_name = name
    doc.original_tab_name = name
    doc.add_layer("L0", x, 20, w, h, image_source=None, is_folder=False)
    return doc


workdir = tempfile.mkdtemp()
manager = PresetManager(app_dir=workdir, copy_initial=False)

preset_id = manager.save_preset_documents(
    "测试预设", "三页", [_doc("主图"), _doc("细节图", 30), _doc("场景图", 60)]
)
print("创建预设:", preset_id)

ok = True


def check(label, cond, detail=""):
    global ok
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    if not cond:
        ok = False


def titles():
    data = manager.load_preset(preset_id)
    return [d.get("original_tab_name") or d.get("name") for d in data["documents"]]


def index_info():
    return manager.presets_index.get(preset_id, {})


print("\n=== 1. rename_document：两个字段都要变 ===")
result = manager.rename_document(preset_id, 1, "改过的名字")
check("返回成功", result[0] is True, str(result))
data = manager.load_preset(preset_id)
page = data["documents"][1]
check("documents[1].name", page.get("name") == "改过的名字", repr(page.get("name")))
check("documents[1].original_tab_name", page.get("original_tab_name") == "改过的名字",
      repr(page.get("original_tab_name")))
check("摘要读到新名", manager.get_preset_summary(preset_id)["tab_names"][1] == "改过的名字",
      str(manager.get_preset_summary(preset_id)["tab_names"]))
check("其它页未受影响", titles()[0] == "主图" and titles()[2] == "场景图", str(titles()))

print("\n=== 2. 越界页号必须拒绝 ===")
check("负下标", manager.rename_document(preset_id, -1, "x") == (False, "page_missing"))
check("超界", manager.rename_document(preset_id, 99, "x") == (False, "page_missing"))

print("\n=== 3. mtime 乐观锁：外部改动后写回要被拒 ===")
data, mtime = manager._read_preset_for_write(preset_id)
data["documents"][0]["name"] = "竞争写入"
# 模拟另一个入口刚刚改过文件
import time
time.sleep(0.02)
manager.rename_document(preset_id, 2, "别的入口改的")
ok_write, reason = manager._commit_preset_write(preset_id, data, mtime)
check("过期写回被拒", ok_write is False and reason == "stale", f"{ok_write}, {reason}")
check("别人的修改没有被覆盖", titles()[2] == "别的入口改的", str(titles()))

print("\n=== 4. close_document：删单页 + 封面让位 ===")
manager.set_cover_index(preset_id, 2)
check("封面先设为第3页", index_info().get("cover_index") == 2)
ok_close, remaining, reason, removed = manager.close_document(preset_id, 2)
check("删除成功", ok_close is True, f"{ok_close},{remaining},{reason}")
check("带回被删页 payload", isinstance(removed, dict) and "layers" in removed, str(type(removed)))
check("带回被删页 payload", isinstance(removed, dict) and "layers" in removed, str(type(removed)))
check("剩余 2 页", remaining == 2, str(remaining))
check("封面跟着让位到 1", index_info().get("cover_index") == 1, str(index_info().get("cover_index")))
check("索引 document_count 同步", index_info().get("document_count") == 2,
      str(index_info().get("document_count")))

print("\n=== 5. 删封面前一页时封面下移 ===")
manager.set_cover_index(preset_id, 1)
manager.close_document(preset_id, 0)
check("删第0页后封面从1变0", index_info().get("cover_index") == 0,
      str(index_info().get("cover_index")))

print("\n=== 6. clear_preset_documents：清空但保留预设 ===")
before_info = dict(index_info())
ok_clear, reason = manager.clear_preset_documents(preset_id)
check("清空成功", ok_clear is True, str(reason))
data = manager.load_preset(preset_id)
check("documents 为空", data["documents"] == [], str(data.get("documents")))
check("预设名保留", data.get("name") == "测试预设", repr(data.get("name")))
after_info = index_info()
check("索引 document_count = 0", after_info.get("document_count") == 0, str(after_info.get("document_count")))
check("索引 total_layers = 0", after_info.get("total_layers") == 0, str(after_info.get("total_layers")))
check("索引 canvas_sizes 为空", after_info.get("canvas_sizes") == [], str(after_info.get("canvas_sizes")))
check("分类保留", after_info.get("category") == before_info.get("category"),
      f"{before_info.get('category')} -> {after_info.get('category')}")
check("cover_index 归 0", after_info.get("cover_index") == 0, str(after_info.get("cover_index")))
check(".cmp 文件仍在", os.path.isfile(manager._preset_file_path(preset_id)))

print("\n=== 7. 撤销：restore_document_payloads ===")
snapshot = [
    {"canvas_width": 400, "canvas_height": 300, "layers": [], "name": "恢复页",
     "original_tab_name": "恢复页", "index": 0},
]
ok_restore, reason = manager.restore_document_payloads(preset_id, snapshot)
check("恢复成功", ok_restore is True, str(reason))
check("页数回到 1", len(manager.load_preset(preset_id)["documents"]) == 1)
check("索引 document_count 回到 1", index_info().get("document_count") == 1,
      str(index_info().get("document_count")))

print("\n=== 8. 不存在的预设 ===")
check("rename 返回 preset_missing", manager.rename_document("不存在", 0, "x") == (False, "preset_missing"))
check("clear 返回 preset_missing", manager.clear_preset_documents("不存在") == (False, "preset_missing"))

print("\n=== 9. 原子写：不应残留临时文件 ===")
temp_files = [f for f in os.listdir(manager.presets_dir) if f.endswith(".tmp")]
check("没有 .tmp 残留", temp_files == [], str(temp_files))

print()
print("=== 总结:", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
