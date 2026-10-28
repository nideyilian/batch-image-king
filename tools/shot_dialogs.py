"""批量截图核心对话框，用于视觉走查。

为什么每个对话框跑独立子进程：
  在同一进程里「构造 → 渲染 → close + deleteLater → 构造下一个」会段错误
  （exit 139）。单独构造每一个都正常，说明是 Qt 对象销毁与事件循环交互的
  生命周期问题。子进程隔离最省事且可靠 —— 崩一个不影响其余。

用法：
  python tools/shot_dialogs.py            # 全部
  python tools/shot_dialogs.py 01         # 只截编号 01
"""
import os
import subprocess
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUTDIR = ROOT / "docs" / "ui-review"

TARGETS = [
    ("01", "batch-export"),
    ("03", "binding-manager"),
    ("04", "preset-manager"),
    ("05", "canvas-preset"),
    ("06", "new-canvas"),
    ("07", "add-text-layer"),
]
NAMES = dict(TARGETS)


def build_dialog(key, outdir):
    """在当前进程里构造并截图一个对话框。由子进程调用。"""
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase, QFont, QPixmap
    from PySide6.QtCore import QCoreApplication

    app = QApplication.instance() or QApplication(sys.argv)
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(p)
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.dark_theme import CursorDarkTheme
    CursorDarkTheme.apply_to_application(app)

    from app.models.document import Document

    doc = Document()
    doc.canvas_width, doc.canvas_height = 1200, 900
    doc.export_settings = {}

    if key == "01":
        from app.ui.batch_export_dialog import BatchExportDialog
        d = BatchExportDialog(document=doc, parent=None)
    elif key == "03":
        from app.ui.binding_manager_dialog import BindingManagerDialog
        d = BindingManagerDialog(document=doc, parent=None)
    elif key == "04":
        from app.ui.preset_manager_dialog import PresetManagerDialog
        d = PresetManagerDialog(parent=None)
    elif key == "05":
        from app.ui.canvas_preset_dialog import CanvasPresetManagerDialog
        d = CanvasPresetManagerDialog(parent=None)
    elif key == "06":
        from app.ui.new_canvas_dialog import NewCanvasDialog
        d = NewCanvasDialog(parent=None)
    elif key == "07":
        from app.ui.add_text_layer_dialog_simple import AddTextLayerDialog
        d = AddTextLayerDialog(parent=None)
    else:
        raise SystemExit(f"未知编号 {key}")

    d.show()
    for _ in range(20):
        QCoreApplication.processEvents()

    w = max(d.width(), 200)
    h = max(d.height(), 120)
    pm = QPixmap(w, h)
    pm.fill()
    d.render(pm)
    path = outdir / f"{key}-{NAMES[key]}.png"
    ok = pm.save(str(path), "PNG")
    print(f"{'OK  ' if ok else 'FAIL'} {path.name} {w}x{h}")
    return 0 if ok else 1


def main():
    OUTDIR.mkdir(parents=True, exist_ok=True)

    if len(sys.argv) > 1 and sys.argv[1].startswith("--one="):
        key = sys.argv[1].split("=", 1)[1]
        return build_dialog(key, OUTDIR)

    only = sys.argv[1] if len(sys.argv) > 1 else None
    ok = fail = 0
    for key, name in TARGETS:
        if only and key != only:
            continue
        proc = subprocess.run(
            [sys.executable, __file__, f"--one={key}"],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            timeout=180,
        )
        lines = (proc.stdout or "").strip().splitlines()
        msg = lines[-1] if lines else "无输出"
        if proc.returncode == 0:
            ok += 1
            print(f"  {msg}")
        else:
            fail += 1
            err = (proc.stderr or "").strip().splitlines()
            print(f"  FAIL {key}-{name}  rc={proc.returncode}  {err[-1] if err else msg}")

    print(f"\n成功 {ok} / 失败 {fail} → {OUTDIR}")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
