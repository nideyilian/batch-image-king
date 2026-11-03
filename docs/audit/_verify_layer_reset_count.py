"""精确验证：一次真实的图层排序，模型触发几轮 reset。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def build(n=6):
    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(400, 300)
    for i in range(n):
        path = os.path.join(tmp, f"i{i}.png")
        Image.new("RGBA", (100, 80), (40 * i, 90, 160, 255)).save(path)
        doc.add_layer(f"L{i}", 5 * i, 5, 100, 80, image_source=path)
    return doc


doc = build()
ws = WorkspaceViewModel(document=doc, preview_provider=PreviewImageProvider(), auto_render=False)
model = ws._layer_model

counter = {"reset": 0, "data": 0}
model.modelAboutToBeReset.connect(lambda: counter.__setitem__("reset", counter["reset"] + 1))
model.dataChanged.connect(lambda *a: counter.__setitem__("data", counter["data"] + 1))


def names_order():
    return [model.data(model.index(r, 0), model.NameRole) for r in range(model.rowCount())]


print("当前面板顺序（上->下）:", names_order())
print()

# 选中间那层，往前移
mid = 3
ws.selectLayer(mid)
selected_name = doc.layers[mid].name
print(f"选中: {selected_name}（文档索引 {mid}）")

counter["reset"] = 0
counter["data"] = 0
ws.moveSelectedLayer("forward")

print(f"一次 moveSelectedLayer('forward'): reset={counter['reset']}  dataChanged={counter['data']}")
print("移动后顺序:", names_order())

print()
# 再试「移到顶层」
ws.selectLayer(mid)
counter["reset"] = 0
counter["data"] = 0
ws.moveSelectedLayer("front")
print(f"一次 moveSelectedLayer('front'):   reset={counter['reset']}  dataChanged={counter['data']}")
print("移动后顺序:", names_order())

print()
# 目标已经相同 -> 应该是 0 次（空操作）
counter["reset"] = 0
counter["data"] = 0
ws.moveSelectedLayer("front")
print(f"重复同一操作（空操作）:              reset={counter['reset']}  dataChanged={counter['data']}")

print()
print("=== 说明 ===")
print("  旧实现 _finish_arrangement 里 layer_changed.emit() 会触发一次 reset，")
print("  紧接着显式调 _layer_model.reset_from_document() 又一次 -> 固定 2 轮。")
print("  现在单一触发点 + 结构指纹 = 结构真变时 1 轮，否则 0 轮。")
