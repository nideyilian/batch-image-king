"""量化 provider 里的重采样开销：sourceSize 与预览图尺寸不一致时每帧都重采样。

Main.qml documentPreview 的 sourceSize = 画布尺寸 × 缩放 × dpr（并被画布尺寸截断），
而预览图是画布尺寸 or 交互档尺寸。两者不一致时，requestImage 每次都要
做一次全图 SmoothTransformation。
"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSize
from PySide6.QtGui import QGuiApplication, QImage

from app.qml.preview_image_provider import PreviewImageProvider

app = QGuiApplication.instance() or QGuiApplication([])


def make(width, height):
    img = QImage(width, height, QImage.Format_RGBA8888)
    img.fill(0xFF203040)
    return img


def bench_request(src_size, req_size, n=25):
    provider = PreviewImageProvider()
    provider.set_image(make(*src_size))
    samples = []
    for _ in range(n):
        size = QSize()
        t = time.perf_counter()
        provider.requestImage("current", size, QSize(*req_size))
        samples.append((time.perf_counter() - t) * 1000)
    s = sorted(samples)
    return statistics.median(s), s[-1]


print("画布 1080x1350，dpr=1.25，预览图为交互档 960x1200 或全质量 1080x1350\n")
print(f"{'预览图':<14}{'sourceSize 请求':<20}{'中位耗时':<12}{'最大':<10}{'是否重采样'}")
print("-" * 74)

cases = [
    ((960, 1200), (405, 506)),   # 缩放 0.3
    ((960, 1200), (675, 844)),   # 缩放 0.5
    ((960, 1200), (918, 1148)),  # 缩放 0.68
    ((960, 1200), (1080, 1350)), # 缩放 1.0（sourceSize 被画布尺寸夹住，比预览图大）
    ((1080, 1350), (405, 506)),
    ((1080, 1350), (675, 844)),
    ((1080, 1350), (918, 1148)),
    ((1080, 1350), (1080, 1350)),  # 完全一致 -> 应跳过
]

for src, req in cases:
    med, mx = bench_request(src, req)
    resampled = not (req[0] >= src[0] and req[1] >= src[1])
    print(f"{str(src):<14}{str(req):<20}{med:>8.2f}ms  {mx:>7.2f}ms  "
          f"{'是（全图 Smooth）' if resampled else '否（直接返回）'}")

print("\n注：requestImage 在 Qt 里由图片加载线程调用，不在 GUI 主线程；")
print("    但它和下一帧的渲染抢 CPU，且与异步解码互相排队 —— 仍是掉帧来源。")
