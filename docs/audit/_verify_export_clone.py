"""验证副本导出后，报告类字段是否搬回主文档（降级/调整提示依赖它们）。"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PIL import Image
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def build():
    tmp = tempfile.mkdtemp()
    doc = Document()
    doc.create_new(400, 300)
    for i in range(3):
        path = os.path.join(tmp, f"i{i}.png")
        Image.new("RGBA", (200, 150), (60 * i, 90, 160, 255)).save(path)
        doc.add_layer(f"L{i}", 10 + i * 20, 10, 200, 150, image_source=path)
    return doc


doc = build()
doc._last_export_report = {"sentinel": "before"}
ws = WorkspaceViewModel(document=doc, preview_provider=PreviewImageProvider(), auto_render=False)

captured = {}


def runner(document, **kwargs):
    # 关键：runner 拿到的必须是**副本**，不是共享文档
    captured["is_clone"] = document is not doc
    captured["has_layers"] = len(document.layers)
    # 模拟导出过程往文档上写报告
    document._last_export_report = {"exported_count": 3, "failed_count": 0}
    document._last_precompute_diagnostics = {"degradations": {"X": 1}, "degradation_total": 2}
    document._last_export_adjustment = {"requested": 8, "planned": 3}
    document._last_export_error = ""
    return True


out = tempfile.mkdtemp()
vm = BatchExportViewModel(workspace=ws, runner=runner)
vm.outputDirectory = out
vm.count = 3
assert vm.startExport() is True

import time
deadline = time.monotonic() + 20
while vm.running and time.monotonic() < deadline:
    app.processEvents()
    time.sleep(0.01)
app.processEvents()

print("runner 拿到的是副本:", captured.get("is_clone"))
print("副本里有图层:", captured.get("has_layers"))
print("导出成功:", vm.succeeded)
print()
print("主文档上的报告字段是否搬回：")
for attr in ("_last_export_report", "_last_precompute_diagnostics", "_last_export_adjustment"):
    print(f"  {attr} = {getattr(doc, attr, '<缺失>')}")
print()
print("VM 上的降级/调整提示：")
print(f"  degradationSummary = {vm.degradationSummary!r}")
print(f"  adjustmentSummary  = {vm.adjustmentSummary!r}")

# 共享文档本身是否被导出过程污染（图层状态不该被改）
print()
print("共享文档图层数仍在:", len(doc.layers))
print("共享文档 _is_batch_export_running:", getattr(doc, "_is_batch_export_running", None))
