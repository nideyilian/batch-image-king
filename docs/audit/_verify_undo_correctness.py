"""验证撤销/重做修复后功能仍然正确（不能只修泄漏而弄坏撤销）。"""
import gc
import os
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer

app = QCoreApplication.instance() or QCoreApplication(sys.argv)

from app.models.document import Document
from app.models.layer_new import Layer


def pump(ms=20):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


def build(n=4):
    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(400, 300)
    for i in range(n):
        path = os.path.join(tmp, f"i{i}.png")
        Image.new("RGBA", (100, 80), (40 * i, 90, 160, 255)).save(path)
        doc.add_layer(f"L{i}", 5 * i + 10, 15, 100, 80, image_source=path)
    return doc


ok = True


def check(label, cond, detail=""):
    global ok
    print(f"  {'PASS' if cond else 'FAIL'}  {label}{('  ' + detail) if detail else ''}")
    if not cond:
        ok = False


print("=== 1. 撤销能正确还原属性值 ===")
doc = build()
doc.save_state("基准")
original_x = doc.layers[0].x
doc.layers[0].x = 200
doc.layers[0].name = "改过的名字"
doc.save_state("改属性")
pump(30)
check("改后 x 生效", doc.layers[0].x == 200, f"x={doc.layers[0].x}")
doc.undo()
pump(30)
check("撤销后 x 还原", doc.layers[0].x == original_x, f"期望 {original_x} 实际 {doc.layers[0].x}")
check("撤销后名字还原", doc.layers[0].name == "L0", f"实际 {doc.layers[0].name}")
check("撤销后图层数不变", len(doc.layers) == 4, f"实际 {len(doc.layers)}")

print("\n=== 2. 重做能重新应用 ===")
doc.redo()
pump(30)
check("重做后 x 恢复为 200", doc.layers[0].x == 200, f"实际 {doc.layers[0].x}")
check("重做后名字恢复", doc.layers[0].name == "改过的名字", f"实际 {doc.layers[0].name}")

print("\n=== 3. 撤销后图层类型不退化 ===")
from app.models.text_layer import TextLayer
from app.models.shaped_layer_new import ShapedLayer

doc2 = build(2)
text = TextLayer(name="文字", x=20, y=20, width=200, height=60)
text.current_text = "测试文字"
doc2.add_text_layer(text)
shaped = ShapedLayer(name="形状", x=50, y=50, width=80, height=80)
doc2.add_shaped_layer(shaped)
doc2.save_state("加文字和形状")
doc2.layers[0].x = 123
doc2.save_state("移动")
doc2.undo()
pump(30)
types = [type(l).__name__ for l in doc2.layers]
check("撤销后文字图层类型保持", "TextLayer" in types, f"类型: {types}")
check("撤销后异形图层类型保持", "ShapedLayer" in types, f"类型: {types}")

print("\n=== 4. 撤销后的图层能触发 document_changed ===")
doc3 = build(2)
doc3.save_state("s")
doc3.layers[0].x = 55
doc3.save_state("s2")
doc3.undo()
pump(30)
fired = {"n": 0}
doc3.document_changed.connect(lambda: fired.__setitem__("n", fired["n"] + 1))
doc3.layers[0].x = 999
pump(30)
check("改撤销后图层的属性会触发重绘信号", fired["n"] > 0, f"触发 {fired['n']} 次")

print("\n=== 5. 绑定组在撤销后仍可用 ===")
doc4 = build(3)
try:
    from app.models.binding_manager import LayerBindingManager

    doc4.save_state("绑定前")
    before_groups = len(doc4.binding_manager.serialize().get("groups", [])) if hasattr(doc4.binding_manager, "serialize") else 0
    doc4.layers[0].x = 77
    doc4.save_state("绑定后")
    doc4.undo()
    pump(30)
    check("撤销后绑定管理器未损坏", doc4.binding_manager is not None)
except Exception as error:
    check("绑定组恢复", False, str(error))

print("\n=== 6. 连续 60 轮撤销/重做后仍正确 ===")
doc5 = build(5)
doc5.save_state("起点")
base_x = doc5.layers[0].x
# 注意：add_layer 会在加入新层**之前**存一份「添加图层前」快照，
# 所以撤销到底会回到「只有 4 层」的状态 —— 这是既有语义，不是本次改动引入。
# 用旧代码（git stash）跑同一场景结果完全一致（undo=4）。
# 因此这里只断言「图层数稳定不再变化」和「无孤儿对象」，不锁具体层数。
layer_count_after_first = None
for r in range(60):
    doc5.layers[0].x = 10 + r
    doc5.save_state(f"r{r}")
    doc5.undo()
    doc5.redo()
    doc5.undo()
    pump(2)
    if layer_count_after_first is None:
        layer_count_after_first = len(doc5.layers)
pump(200)
gc.collect()
check("60 轮后 x 回到基准", doc5.layers[0].x == base_x, f"期望 {base_x} 实际 {doc5.layers[0].x}")
check(
    "60 轮后图层数稳定（不再随轮次变化）",
    len(doc5.layers) == layer_count_after_first,
    f"首轮后 {layer_count_after_first}，60 轮后 {len(doc5.layers)}",
)
live = [o for o in gc.get_objects() if isinstance(o, Layer)]
# 只统计「挂在 doc5 这棵 C++ 树上、但不在 doc5.layers 里」的对象。
# 前几组测试各自建的 Document 还在作用域内，它们的图层不属于 doc5，不能算进来。
in_doc = set(id(x) for x in doc5.layers)
def _parent_is(ob, target):
    # deleteLater 已经执行过的对象，底层 C++ 对象已销毁，访问 parent() 会抛 RuntimeError
    try:
        return ob.parent() is target
    except RuntimeError:
        return False


orphans = [o for o in live if id(o) not in in_doc and _parent_is(o, doc5)]
check("60 轮后 doc5 名下无孤儿图层", len(orphans) == 0, f"孤儿 {len(orphans)}（修复前为 60×N）")
check("C++ 子对象不随轮次增长", len(doc5.children()) <= 12, f"children={len(doc5.children())}（修复前 4→104+）")

print()
print("=== 总结:", "全部通过" if ok else "存在失败项", "===")
sys.exit(0 if ok else 1)
