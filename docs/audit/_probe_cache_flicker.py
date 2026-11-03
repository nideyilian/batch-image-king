"""验证闪烁的真正机制：异步换源时，帧是否会「倒放」。

拖拽时每帧发一个新的 revision URL。若两帧同时在解码、完成顺序不确定，
就会出现「先显示第 5 帧，再跳回第 4 帧」—— 这就是用户说的闪。
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickWindow

from app.qml.preview_image_provider import PreviewImageProvider

app = QGuiApplication.instance() or QGuiApplication([])


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


class CountingProvider(PreviewImageProvider):
    """记录每次被请求时 provider 手里是第几版，以及请求线程。"""

    def __init__(self):
        super().__init__()
        self.requests = []

    def requestImage(self, image_id, size, requested_size):  # noqa: N802
        self.requests.append((image_id, time.perf_counter(), requested_size.width()))
        return super().requestImage(image_id, size, requested_size)


QML = b'''
import QtQuick

Item {
    id: host
    width: 400
    height: 300
    property url imgSource: ""
    property bool cacheOn: false
    property int st: img.status
    property int frames: 0

    Image {
        id: img
        anchors.fill: parent
        source: host.imgSource
        asynchronous: true
        cache: host.cacheOn
        smooth: true
        sourceSize.width: 400
        sourceSize.height: 300
        onStatusChanged: if (status === Image.Ready) host.frames++
    }
}
'''


def make_provider(width, height, shade):
    image = QImage(width, height, QImage.Format_RGBA8888)
    image.fill(shade)
    p = CountingProvider()
    p.set_image(image)
    return p


print("=== 拖动时连发 20 帧，看 QML 实际取图次数与尺寸 ===")
for cache_on in (False, True):
    for src_size in ((960, 1200), (1080, 1350)):
        provider = make_provider(*src_size, 0xFF203040)
        engine = QQmlApplicationEngine()
        engine.addImageProvider("documentPreview", provider)
        comp = QQmlComponent(engine)
        comp.setData(QML, QUrl("qrc:/p.qml"))
        host = comp.create()
        win = QQuickWindow()
        host.setParentItem(win.contentItem())
        host.setWidth(400)
        host.setHeight(300)
        win.resize(400, 300)
        win.show()
        pump(300)
        host.setProperty("cacheOn", cache_on)

        provider.requests.clear()
        t0 = time.perf_counter()
        for rev in range(1, 21):
            host.setProperty("imgSource", f"image://documentPreview/current?revision={rev}")
            pump(16)
        pump(400)
        reqs = len(provider.requests)
        widths = sorted({r[2] for r in provider.requests})
        print(f"  cache={str(cache_on):<5} 源{src_size[0]}x{src_size[1]:<5} "
              f"发 20 帧 -> provider 被请求 {reqs:>2} 次，请求宽度={widths}")
        win.close()
        engine.deleteLater()
        pump(50)

print("\n=== 关键：同一 URL 重复设置会不会重复解码 ===")
provider = make_provider(1080, 1350, 0xFF203040)
engine = QQmlApplicationEngine()
engine.addImageProvider("documentPreview", provider)
comp = QQmlComponent(engine)
comp.setData(QML, QUrl("qrc:/p.qml"))
host = comp.create()
win = QQuickWindow()
host.setParentItem(win.contentItem())
host.setWidth(400)
host.setHeight(300)
win.show()
pump(300)

for cache_on in (False, True):
    host.setProperty("cacheOn", cache_on)
    host.setProperty("imgSource", "image://documentPreview/current?revision=999")
    pump(300)
    provider.requests.clear()
    for _ in range(10):
        # 每次都设成同一个 URL —— 模拟「画面内容没变但属性被重新求值」
        host.setProperty("imgSource", "image://documentPreview/current?revision=999")
        pump(16)
    print(f"  cache={str(cache_on):<5} 同 URL 设 10 次 -> 重新请求 {len(provider.requests)} 次"
          f"{'   <<< 每次白重传一张纹理' if len(provider.requests) else ''}")

win.close()
