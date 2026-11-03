"""验证图层面板模型：属性变更不再 reset，结构变更仍然 reset。"""
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

print("起始行数:", model.rowCount())
print()


def measure(label, fn):
    counter["reset"] = 0
    counter["data"] = 0
    fn()
    print(f"  {label:<34} reset={counter['reset']}  dataChanged={counter['data']}")
    return counter["reset"], counter["data"]


print("=== 应该「不重建」的操作（只发 dataChanged）===")
r1 = measure("改图层名", lambda: setattr(doc.layers[0], "name", "改名了") or doc.layer_changed.emit())
r2 = measure("切换可见性", lambda: ws.toggleLayerVisible(1))
r3 = measure("切换锁定", lambda: ws.toggleLayerLocked(1))
r4 = measure("选中另一图层", lambda: ws.selectLayer(2))
r5 = measure("移动图层位置（x）", lambda: ws._set_layer_attrs(0, {"x": 99}, "移动"))

print()
print("=== 应该「重建」的操作（结构变了）===")
r6 = measure("删除图层", lambda: ws.deleteSelectedLayer())
r7 = measure("复制图层", lambda: ws.duplicateSelectedLayer())
r8 = measure("上移一层", lambda: ws.moveSelectedLayer("forward"))
r9 = measure("新建图层", lambda: doc.add_layer("新的", 10, 10, 50, 50, image_source=None))

print()
print("=== 判定 ===")
no_reset = all(r[0] == 0 for r in (r1, r2, r3, r4, r5))
has_reset = all(r[0] >= 1 for r in (r6, r7, r8, r9))
print(f"  属性类操作均不 reset: {'通过' if no_reset else '失败'}")
print(f"  结构类操作均 reset:   {'通过' if has_reset else '失败'}")
print(f"  最终行数: {model.rowCount()}")

# 每次排序不应该触发两轮
print()
print("=== 单次排序的触发轮数（旧实现是 2 轮全表 reset）===")
ws.selectLayer(0)
counter["reset"] = 0
counter["data"] = 0
ws.moveSelectedLayer("front")
print(f"  一次 moveSelectedLayer: reset={counter['reset']}  dataChanged={counter['data']}"
      f"{'   <<< 已收敛为单次' if counter['reset'] <= 1 else '   <<< 仍在重复触发'}")
