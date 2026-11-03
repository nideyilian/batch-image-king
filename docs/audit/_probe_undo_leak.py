"""验证撤销/重做是否会累积「脱管的图层对象」和信号连接。

_restore_state 每次撤销都用 deserialize_layer_tree 重建全部图层：
  - 新图层没有 .changed.connect(document_changed)
  - 旧图层也没有断开连接（它们随 self.layers 被替换后成为孤儿，
    但若仍被 Signal/父子关系引用，就不会被 GC）

若累积成立，长时间操作后：对象数涨、连接数涨、内存涨，最终卡死。
"""
import gc
import os
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QCoreApplication

app = QCoreApplication.instance() or QCoreApplication(sys.argv)

from app.models.document import Document
from app.models.layer_new import Layer


def build(n=5):
    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(400, 300)
    for i in range(n):
        path = os.path.join(tmp, f"i{i}.png")
        Image.new("RGBA", (100, 80), (40 * i, 90, 160, 255)).save(path)
        doc.add_layer(f"L{i}", 5 * i, 5, 100, 80, image_source=path)
    return doc


def count_layers():
    return sum(1 for o in gc.get_objects() if isinstance(o, Layer))


doc = build()
gc.collect()
base_objs = count_layers()
print(f"初始 Layer 对象数: {base_objs}")
print(f"文档图层数: {len(doc.layers)}")

doc.save_state("基准")
print()

print("=== 反复「改属性 + 撤销」，观察 Layer 对象是否累积 ===")
print(f"{'轮次':<8}{'Layer对象':<12}{'增量':<8}{'文档图层':<10}")
for round_index in range(1, 41):
    layer = doc.layers[round_index % len(doc.layers)]
    layer.x = 10 + round_index
    doc.save_state(f"移动{round_index}")
    if doc.can_undo():
        doc.undo()
    if round_index % 5 == 0:
        gc.collect()
        now = count_layers()
        print(f"{round_index:<8}{now:<12}{now - base_objs:<8}{len(doc.layers):<10}")

gc.collect()
final_objs = count_layers()
print()
print(f"最终 Layer 对象数: {final_objs}（初始 {base_objs}，增量 {final_objs - base_objs}）")
print(f"是否累积: {'是 <<< 泄漏' if final_objs > base_objs + 10 else '否'}")

print()
print("=== 检查撤销后新图层的 changed 信号连接状态 ===")
doc2 = build(3)
doc2.save_state("s1")
doc2.layers[0].x = 99
doc2.save_state("s2")
doc2.undo()
restored = doc2.layers[0]
receivers = restored.receivers("2changed()") if hasattr(restored, "receivers") else -1
print(f"  撤销后新图层 changed 连接数: {receivers}（0 = 脱管，改属性不会触发重绘）")
old_receivers = restored.receivers("2changed()") if hasattr(restored, "receivers") else "n/a"
print(f"  正常路径（add_layer）新建图层应为 1")

doc3 = build(1)
normal = doc3.layers[0]
print(f"  对比：add_layer 建出的图层 changed 连接数 = {normal.receivers('2changed()') if hasattr(normal, 'receivers') else 'n/a'}")
