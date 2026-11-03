"""profiler：把 interactive 一帧的 90ms 精确拆到函数级。"""
import cProfile
import io
import os
import pstats
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document


def build_doc(layer_count=12, canvas=(1080, 1350)):
    doc = Document()
    doc.create_new(*canvas)
    tmp = tempfile.mkdtemp()
    for i in range(layer_count):
        path = os.path.join(tmp, f"img_{i}.png")
        Image.new("RGBA", (600 + i * 10, 400 + i * 10), (30 * i % 255, 90, 160, 255)).save(path)
        doc.add_layer(f"图层{i}", 40 + i * 8, 60 + i * 6, 600 + i * 10, 400 + i * 10, image_source=path)
    return doc


doc = build_doc()
from app.services.preview_render_service import render_preview_to_image

# 预热
render_preview_to_image(doc, force_refresh=True)
render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True)

pr = cProfile.Profile()
pr.enable()
for _ in range(5):
    render_preview_to_image(doc, force_refresh=True, interactive_low_quality=True)
pr.disable()

s = io.StringIO()
pstats.Stats(pr, stream=s).sort_stats("cumulative").print_stats(28)
text = s.getvalue()
print("=== interactive (force=True) 累计耗时 top ===")
started = False
for line in text.splitlines():
    if "Ordered by" in line:
        started = True
    if started:
        print(line)

pr2 = cProfile.Profile()
pr2.enable()
for _ in range(5):
    render_preview_to_image(doc, force_refresh=True, interactive_low_quality=False)
pr2.disable()
s2 = io.StringIO()
pstats.Stats(pr2, stream=s2).sort_stats("cumulative").print_stats(15)
print("\n=== final (force=True) 累计耗时 top ===")
started = False
for line in s2.getvalue().splitlines():
    if "Ordered by" in line:
        started = True
    if started:
        print(line)
