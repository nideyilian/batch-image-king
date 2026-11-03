"""用慢速 provider 放大换源窗口，验证 retainWhileLoading 是否真的消除空白帧。

真实场景里 requestImage 要 1.4~2.7ms（全图 Smooth 重采样）+ 纹理上传，
换源到新帧可见之间的空窗就够渲染 1~2 帧。这里把 provider 人为放慢到 30ms，
再用 grabWindow 逐帧取像素，数出「画布变空白」的帧数。
"""
import os
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

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


class SlowProvider(PreviewImageProvider):
    def __init__(self, delay_ms=30):
        super().__init__()
        self.delay_ms = delay_ms

    def requestImage(self, image_id, size, requested_size):  # noqa: N802
        time.sleep(self.delay_ms / 1000.0)
        return super().requestImage(image_id, size, requested_size)


QML = b'''
import QtQuick

Item {
    id: host
    width: 200
    height: 200
    property url imgSource: ""

    Image {
        id: img
        anchors.fill: parent
        source: host.imgSource
        asynchronous: true
        cache: false
        smooth: true
        sourceSize.width: 200
        sourceSize.height: 200
    }
}
'''

# 生成一张纯亮色图，空白帧（无纹理）会是窗口底色（默认黑/透明）
def bright(marker):
    img = QImage(200, 200, QImage.Format_RGBA8888)
    # 每帧颜色略变，便于区分是旧帧还是新帧
    img.fill(0xFF000000 | (0x80 + marker * 3) << 16 | 0x606060)
    return img


def run_case(retain_value):
    provider = SlowProvider()
    provider.set_image(bright(1))

    engine = QQmlApplicationEngine()
    engine.addImageProvider("documentPreview", provider)
    comp = QQmlComponent(engine)

    # retainWhileLoading 用 property 注入，避免两份 QML
    qml = QML.replace(b"cache: false", b"cache: false\n        retainWhileLoading: host.retain")
    qml = qml.replace(b"property url imgSource: \"\"",
                      b"property url imgSource: \"\"\n    property bool retain: false")
    comp.setData(qml, QUrl("qrc:/p.qml"))
    if comp.isError():
        for e in comp.errors():
            print("QML ERR:", e.toString())
        return None
    host = comp.create()
    host.setProperty("retain", retain_value)

    win = QQuickWindow()
    host.setParentItem(win.contentItem())
    win.resize(200, 200)
    win.show()
    pump(400)

    host.setProperty("imgSource", "image://documentPreview/current?revision=1")
    pump(600)

    blank = 0
    total = 0
    for rev in range(2, 9):
        host.setProperty("imgSource", f"image://documentPreview/current?revision={rev}")
        # 在换源后的空窗里取几帧
        for _ in range(3):
            pump(8)
            grab = win.grabWindow()
            if grab.isNull():
                continue
            total += 1
            # 取中心像素亮度；空白帧会是窗口底色（接近 0）
            c = grab.pixelColor(100, 100)
            if c.red() + c.green() + c.blue() < 40:
                blank += 1
    win.close()
    pump(100)
    return blank, total


print("=== 慢速 provider（30ms/次，模拟真实解码+重采样+上传）===")
print("拖动时连换 7 次源，每次换源后取 3 帧共 21 帧\n")
for retain in (False, True):
    result = run_case(retain)
    if result is None:
        continue
    blank, total = result
    print(f"  retainWhileLoading={str(retain):<5}  空白/近黑帧 {blank}/{total}"
          f"{'   <<< 就是肉眼看到的「闪」' if blank > 2 else '   无明显空白帧'}")
