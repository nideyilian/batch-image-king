"""验证闪烁：image:// provider 每帧换 URL 时，画布纹理会不会出现空帧。

现状（Main.qml documentPreview）：
    source: workspace.previewSource    (= image://documentPreview/current?revision=N)
    asynchronous: true
    cache: false                        <- 每帧都丢弃旧纹理缓存
    retainWhileLoading 未设置 (Qt 默认 False)
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QGuiApplication, QImage
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickWindow

from app.qml.preview_image_provider import PreviewImageProvider

app = QGuiApplication.instance() or QGuiApplication([])
LABELS = {0: "Null", 1: "Ready", 2: "Loading", 3: "Error"}


def pump(ms):
    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()


QML = b'''
import QtQuick

Item {
    id: host
    width: 400
    height: 300
    property url imgSource: ""
    property bool cacheOn: false
    property bool retain: false
    property int st: img.status
    property real pw: img.paintedWidth

    Image {
        id: img
        anchors.fill: parent
        source: host.imgSource
        asynchronous: true
        cache: host.cacheOn
        retainWhileLoading: host.retain
    }
}
'''

provider = PreviewImageProvider()
provider.set_image(QImage(960, 1200, QImage.Format_RGBA8888))

engine = QQmlApplicationEngine()
engine.addImageProvider("documentPreview", provider)
comp = QQmlComponent(engine)
comp.setData(QML, QUrl("qrc:/probe.qml"))
if comp.isError():
    for e in comp.errors():
        print("ERR", e.toString())
    sys.exit(1)
host = comp.create()

win = QQuickWindow()
host.setParentItem(win.contentItem())
host.setWidth(400)
host.setHeight(300)
win.resize(400, 300)
win.show()
pump(300)


def run(cache_on, retain, steps=12, gap_ms=16):
    host.setProperty("cacheOn", cache_on)
    host.setProperty("retain", retain)
    rev = 1
    host.setProperty("imgSource", f"image://documentPreview/current?revision={rev}")
    pump(600)
    statuses = []
    for _ in range(steps):
        rev += 1
        host.setProperty("imgSource", f"image://documentPreview/current?revision={rev}")
        pump(gap_ms)
        statuses.append(host.property("st"))
    blanks = sum(1 for s in statuses if s == 0)
    loadings = sum(1 for s in statuses if s == 2)
    return blanks, loadings, statuses


print("=== image:// provider 连续换源 12 次（每 16ms 一次，模拟 60fps 拖动）===\n")
for cache_on in (False, True):
    for retain in (False, True):
        blanks, loadings, seq = run(cache_on, retain)
        desc = " ".join(LABELS.get(s, str(s))[:4] for s in seq[:12])
        flag = "  <<< 空帧！画布会闪" if blanks else ""
        print(f"cache={str(cache_on):<5} retain={str(retain):<5} 空帧={blanks:<2} 加载中={loadings:<2}  {desc}{flag}")

print("\n=== 参考：现状是 cache=false + retain 未设(=False) ===")
win.close()
