"""验证闪烁机制：Image 每帧换 URL 时旧帧是否被保留。

对应 Main.qml documentPreview 现状：
    source: workspace.previewSource    <- 每帧变化 (?revision=N)
    asynchronous: true
    cache: false
    # retainWhileLoading 未设置，Qt 默认 False
"""
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QEventLoop, QTimer, QUrl
from PySide6.QtGui import QGuiApplication
from PySide6.QtQml import QQmlApplicationEngine, QQmlComponent
from PySide6.QtQuick import QQuickWindow

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
    property bool retain: false
    property int st: img.status
    property real pw: img.paintedWidth

    Image {
        id: img
        anchors.fill: parent
        source: host.imgSource
        asynchronous: true
        cache: false
        retainWhileLoading: host.retain
    }
}
'''

png = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "app", "qml", "preview.png"))
base = QUrl.fromLocalFile(png).toString()
print("测试图:", png, "存在:", os.path.exists(png))

engine = QQmlApplicationEngine()
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
pump(200)

for retain in (False, True):
    host.setProperty("retain", retain)

    host.setProperty("imgSource", base + "?revision=1")
    pump(600)
    st0 = host.property("st")
    pw0 = host.property("pw")

    host.setProperty("imgSource", base + "?revision=2")
    pump(1)
    st1 = host.property("st")
    pw1 = host.property("pw")

    print(f"\nretainWhileLoading = {retain}")
    print(f"  换源前      status={LABELS.get(st0, st0):<8} paintedWidth={pw0:.0f}")
    print(f"  换源后 1ms  status={LABELS.get(st1, st1):<8} paintedWidth={pw1:.0f}")
    if st1 == 0 or pw1 == 0:
        print("  >>> 旧帧被清空：这一帧画出空白/底色 —— 拖动时每帧如此就是「闪」")
    else:
        print("  >>> 旧帧保留，无空白帧")
    pump(500)

win.close()
