"""验证「导出期间拖拽卡死」：批量导出任务持文档锁的整段时长。

_BatchExportTask.run() 里 `with self.document_lock:` 包住了整个 batch_export，
而主线程 previewLiveGeometry / _set_layer_attrs 都要拿同一把锁。
"""
import os
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document

tmp = tempfile.mkdtemp()
doc = Document()
doc.create_new(1080, 1350)
for i in range(8):
    path = os.path.join(tmp, f"a{i}.png")
    Image.new("RGBA", (800, 600), (20 * i, 90, 160, 255)).save(path)
    doc.add_layer(f"L{i}", 40 + i * 20, 40 + i * 20, 800, 600, image_source=path)

lock = threading.RLock()

print("=== 模拟：导出线程持锁 -> 主线程拖拽 ===")


def export_worker(hold_seconds: float):
    with lock:
        time.sleep(hold_seconds)


results = []
for hold in (0.2, 0.5, 1.0):
    th = threading.Thread(target=export_worker, args=(hold,), daemon=True)
    th.start()
    time.sleep(0.02)  # 确保导出线程已拿到锁
    t = time.perf_counter()
    with lock:
        pass
    waited = (time.perf_counter() - t) * 1000
    results.append((hold, waited))
    print(f"  导出持锁 {hold*1000:6.0f}ms -> 主线程拖拽被阻塞 {waited:7.1f}ms"
          f"{'   <<< UI 完全冻结' if waited > 100 else ''}")
    th.join()

print("\n=== 真实导出一次，量出持锁总时长 ===")
out_dir = tempfile.mkdtemp()
t = time.perf_counter()
with lock:
    doc.batch_export(
        directory=out_dir,
        count=6,
        filename_template="test_{:03d}",
        file_format="png",
    )
elapsed = (time.perf_counter() - t) * 1000
files = len(os.listdir(out_dir))
print(f"  8 层 1080x1350 导出 6 张：{elapsed:.0f}ms（实际产出 {files} 张）")
print(f"  --> 这段时间主线程任何拖拽/改属性都会阻塞 {elapsed:.0f}ms（超过 3 帧无响应即感知为卡死）")
