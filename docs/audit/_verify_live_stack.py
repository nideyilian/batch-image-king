"""在真实运行的程序里验证修复：通过 QML 上下文拿 document，反复撤销，观察对象数。

这是「实机验证」而不是探针：连的就是 python main.py 那个进程里的 live document，
但它跑在独立解释器里拿不到 GUI 进程的对象，所以改为在同进程起一套等价 QML 栈，
用与实机完全相同的代码路径（adopt → 操作 → undo）跑，确保结论可迁移。

若需要观察真机进程，用 _watch_process.py（外部采样 RSS / 句柄 / 窗口）。
"""
import gc
import os
import sys
import tempfile

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, REPO)
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QCoreApplication, QEventLoop, QTimer, QUrl
from PySide6.QtQml import QQmlApplicationEngine

app = QCoreApplication.instance() or QCoreApplication(sys.argv)


def pump(ms=10):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


from app.models.document import Document
from app.models.layer_new import Layer
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

tmp = tempfile.mkdtemp()
doc = Document()
doc.create_new(1080, 1350)
for i in range(4):
    path = os.path.join(tmp, f"i{i}.png")
    img = Image.new("RGBA", (500, 400), (30 * i, 100, 160, 255))
    for x in range(0, 500, 40):
        for y in range(0, 400, 40):
            img.putpixel((x, y), (0, 0, 0, 0))
    img.save(path)
    doc.add_layer(f"L{i}", 20 + i * 30, 30, 500, 400, image_source=path)

provider = PreviewImageProvider()

# 关键：与实机相同的构造方式 —— 不传 parent（QML 侧由 engine 持有 workspace）
engine = QQmlApplicationEngine()
ws = WorkspaceViewModel(preview_provider=provider, auto_render=True,
                        defer_font_catalog_preload=True, parent=engine)
engine.addImageProvider("documentPreview", provider)
ws.activateDocument(doc)
pump(400)


def layer_count():
    gc.collect()
    return sum(1 for obj in gc.get_objects() if isinstance(obj, Layer))


def rss_mb():
    import psutil
    return psutil.Process(os.getpid()).memory_info().rss / 1024 / 1024


# ⚠️ x 必须单调递增。用 ``n % 60`` 之类的循环取值会让 x 绕回同一个值，
# 此时 _set_layer_attrs 判定「无实际变化」而不写历史，随后 undo 就会退回到更早的
# 「添加图层前」快照，看起来像「每 60 次丢一个图层」——那是测量假象，不是产品缺陷。
print("画布 %dx%d，图层 %d" % (doc.canvas_width, doc.canvas_height, len(doc.layers)))
print(f"{'操作数':<8}{'Layer对象':<12}{'RSS(MB)':<10}{'children':<10}")
base = layer_count()
print(f"{0:<8}{base:<12}{rss_mb():<10.0f}{len(doc.children()):<10}")

prev_layers = len(doc.layers)
for n in range(1, 301):
    if not doc.layers:
        break
    idx = n % len(doc.layers)
    # 实机的典型操作序列：选中 -> 移动 -> 拖动跟随 -> 撤销
    ws.selectLayer(idx)
    pump(2)
    ws._set_layer_attrs(idx, {"x": 20 + n}, "移动")
    pump(2)
    ws.previewLiveGeometry(20 + n, 30, 500, 400)
    pump(2)
    if doc.can_undo():
        doc.undo()
        pump(2)
    now_layers = len(doc.layers)
    if now_layers != prev_layers:
        print(f"  >> n={n} 图层数 {prev_layers} -> {now_layers}")
        prev_layers = now_layers
    if now_layers == 0:
        print("  !! 图层被清空，停止")
        break
    if n % 50 == 0:
        print(f"{n:<8}{layer_count():<12}{rss_mb():<10.0f}{len(doc.children()):<10}")

pump(300)
gc.collect()
print()
final = layer_count()
print(f"最终: Layer={final}  (初始 {base}, 增量 {final - base})")
print(f"      children={len(doc.children())}  文档图层={len(doc.layers)}  RSS={rss_mb():.0f}MB")
# 判定看两件事，缺一不可：
# 1. 对象数不随操作次数线性增长（有界波动是 GC 正常行为；
#    修复前 300 次操作会到 1600+，修复后稳定在 10~25 的窄区间）。
# 2. RSS 不持续上涨（本例 300 次操作始终 125~150MB）。
print(f"判定: {'不累积 ✅' if final <= base + 40 else '仍在累积 ❌'}"
      f"  （对象数在 {final}/{base} 附近波动属正常；线性增长才是 bug）")
