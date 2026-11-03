"""临时探测：图片进 QML 的那一段 —— 闪烁与掉帧的真凶在这里。"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QSize
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_vm_shared import _pil_to_qimage


def timeit(fn, n=20):
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000)
    s = sorted(out)
    return statistics.median(s), s[int(len(s) * 0.9)], s[-1]


print("=== 1. PIL -> QImage（主线程，每帧都做）===")
for size in ((960, 1200), (1080, 1350), (2400, 3000)):
    img = Image.new("RGBA", size, (10, 20, 30, 255))
    med, p90, mx = timeit(lambda: _pil_to_qimage(img))
    print(f"  {size[0]}x{size[1]:<6} median={med:6.2f}ms p90={p90:6.2f}ms")

print("\n=== 2. provider.requestImage（QML 取图，若尺寸不同会整图重采样）===")
provider = PreviewImageProvider()
for src, req in (((1080, 1350), (1000, 1250)),   # 略有缩小 -> 走 SmoothTransformation
                 ((1080, 1350), (1080, 1350)),   # 等尺寸 -> 应跳过缩放
                 ((2400, 3000), (1200, 1500)),   # 缩一半
                 ((1080, 1350), (600, 750))):    # 缩到 55%
    provider.set_image(_pil_to_qimage(Image.new("RGBA", src, (1, 2, 3, 255))))
    size = QSize()
    med, p90, mx = timeit(lambda: provider.requestImage("current", size, QSize(*req)))
    flag = "  <<< 每次都在重采样！" if med > 3 else ""
    print(f"  源{src[0]}x{src[1]:<5} -> 请求{req[0]}x{req[1]:<5} median={med:6.2f}ms p90={p90:6.2f}ms{flag}")

print("\n=== 3. Qt 6.11 Image 是否有 retainWhileLoading（防闪烁关键）===")
try:
    from PySide6.QtQuick import QQuickItem
    import PySide6.QtQml as qml
    # 用 QML 侧实测属性是否存在
    from PySide6.QtQuick import QQuickView
    view = QQuickView()
    src = '''
import QtQuick
Image {
    id: img
    objectName: "probe"
    property bool probe: retainWhileLoading
}
'''
    view.setSourceData(src.encode())
    if view.status() == QQuickView.Error:
        for e in view.errors():
            print("  QML 错误:", e.toString())
    else:
        root = view.rootObject()
        print("  retainWhileLoading 可用:", root.property("probe") is not None)
except Exception as e:
    print("  探测失败:", e)
