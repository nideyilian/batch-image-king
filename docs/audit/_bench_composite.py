"""探测：为什么 low_quality_preview=True（所谓快速路径）反而慢 2 倍。"""
import os
import statistics
import sys
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.utils.fast_renderer import get_global_fast_renderer

r = get_global_fast_renderer()


def bench(label, fn, n=15):
    for _ in range(3):
        fn()
    out = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        out.append((time.perf_counter() - t) * 1000)
    s = sorted(out)
    print(f"  {label:<48} median={statistics.median(s):7.2f}ms  max={s[-1]:7.2f}ms")
    return statistics.median(s)


print("=== 单次合成开销（底图 960x1200，前层 500x400）===")
bg_small = Image.new("RGBA", (960, 1200), (0, 0, 0, 0))
fg = Image.new("RGBA", (500, 400), (200, 100, 50, 220))

fast = bench("low_quality_preview=True  (_standard_composite_logic)", lambda: r._fast_composite(
    bg_small, fg, 100, 120, 0.9, True, "normal", low_quality_preview=True))
slow = bench("low_quality_preview=False (UnifiedAlphaCompositor)", lambda: r._fast_composite(
    bg_small, fg, 100, 120, 0.9, True, "normal", low_quality_preview=False))
print(f"  --> 所谓「低质量」路径比全质量路径慢 {fast/slow:.2f} 倍\n")

print("=== 全画布合成（12 层叠满，模拟真实拖动一帧）===")
bg_big = Image.new("RGBA", (1080, 1350), (0, 0, 0, 0))
fg_big = Image.new("RGBA", (1080, 1350), (200, 100, 50, 200))
a = bench("low_quality=True  整画布合成", lambda: r._fast_composite(
    bg_big, fg_big, 0, 0, 1.0, True, "normal", low_quality_preview=True), 8)
b = bench("low_quality=False 整画布合成", lambda: r._fast_composite(
    bg_big, fg_big, 0, 0, 1.0, True, "normal", low_quality_preview=False), 8)
print(f"  --> 倍数 {a/b:.2f}x")

print("\n=== 两条路径内部对比 ===")
import inspect
from app.utils.fast_renderer_composite import FastRendererComposite
src = inspect.getsource(FastRendererComposite._standard_composite_logic)
print("  _standard_composite_logic 行数:", len(src.splitlines()))
print("  含 numpy:", "numpy" in src or "np." in src)
print("  含 sRGB/convert:", "srgb" in src.lower())
