"""真实操作走查：在真实窗口里按用户动线跑一遍，记录耗时与异常。

为什么不用离屏：离屏拿不到真实布局、真实 DPI、真实绘制，
测不出「点击后卡多久」「窗口缩放后是否错位」这类问题。

每个场景独立子进程运行，互不污染（同进程连续构造/销毁窗口在 Qt 下会段错误）。
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
OUTDIR = os.path.join(ROOT, "docs", "ui-review")
os.makedirs(OUTDIR, exist_ok=True)

ASSETS = os.path.join(ROOT, "_run_assets")


def _elapsed(t0: float) -> str:
    return f"{(time.time() - t0) * 1000:.0f}ms"


def _bootstrap():
    """建立应用 + 主题 + 主窗口，返回 (app, win)。"""
    from PySide6.QtGui import QFontDatabase, QFont
    from PySide6.QtWidgets import QApplication

    from app.ui.dark_theme import CursorDarkTheme

    app = QApplication.instance() or QApplication(sys.argv)
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(path)
    app.setFont(QFont("Microsoft YaHei UI", 9))
    CursorDarkTheme.apply_to_application(app)

    from app.main_window import MainWindow

    win = MainWindow()
    win.resize(1600, 1000)
    win.show()
    _pump(app, 20)
    return app, win


def _pump(app, n=10):
    from PySide6.QtCore import QCoreApplication

    for _ in range(n):
        QCoreApplication.processEvents()


def _shot(widget, name):
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QPixmap

    for _ in range(8):
        QCoreApplication.processEvents()
    pm = QPixmap(widget.size())
    pm.fill()
    widget.render(pm)
    path = os.path.join(OUTDIR, f"{name}.png")
    pm.save(path, "PNG")
    return path


# --------------------------------------------------------------------------
# 场景 1：启动
# --------------------------------------------------------------------------
def scenario_startup():
    report = {"scenario": "启动", "steps": []}
    t_all = time.time()

    t0 = time.time()
    app, win = _bootstrap()
    report["steps"].append({"步骤": "主窗口显示", "耗时": _elapsed(t0)})

    # 检查关键控件是否都在
    t0 = time.time()
    checks = {}
    checks["菜单栏"] = win.menuBar() is not None and len(win.menuBar().actions()) > 0
    checks["工具栏"] = bool(win.findChildren(type(win.findChild(__import__("PySide6.QtWidgets", fromlist=["QToolBar"]).QToolBar))) )
    from PySide6.QtWidgets import QTabWidget

    tabs = win.findChildren(QTabWidget)
    checks["标签栏"] = bool(tabs)
    report["steps"].append({"步骤": "关键控件检查", "耗时": _elapsed(t0), "结果": checks})

    _shot(win, "run-01-startup")
    report["总耗时"] = _elapsed(t_all)
    win.close()
    return report


# --------------------------------------------------------------------------
# 场景 2：建文档 + 加图层 + 渲染
# --------------------------------------------------------------------------
def scenario_edit_flow():
    report = {"scenario": "建文档→加图层→渲染", "steps": []}
    from app.models.document import Document
    from app.models.layer_new import Layer
    from app.models.text_layer import TextLayer

    app, win = _bootstrap()

    t0 = time.time()
    doc = Document(parent=win)
    doc.create_new(1200, 900)
    tab_index = win.create_new_tab(doc)
    _pump(app, 12)
    report["steps"].append({"步骤": "新建 1200x900 文档", "耗时": _elapsed(t0), "tab": tab_index})

    # 加一个图片图层（目录型素材源）
    t0 = time.time()
    layer = Layer(name="商品图", x=60, y=60, width=500, height=500, image_source=ASSETS)
    doc.add_layer("商品图", 60, 60, 500, 500, image_source=ASSETS)
    _pump(app, 6)
    report["steps"].append({"步骤": "添加图片图层", "耗时": _elapsed(t0), "图层数": len(doc.layers)})

    # 加一个文字图层
    t0 = time.time()
    tl = TextLayer(name="主标题", x=60, y=600, width=700, height=90)
    tl.current_text = "限时特惠 全场5折"
    tl.font_size = 56
    doc.add_text_layer(tl)
    _pump(app, 6)
    report["steps"].append({"步骤": "添加文字图层", "耗时": _elapsed(t0), "图层数": len(doc.layers)})

    # 渲染
    t0 = time.time()
    img = doc.render_composition()
    report["steps"].append(
        {
            "步骤": "渲染合成",
            "耗时": _elapsed(t0),
            "尺寸": list(img.size) if img else None,
            "成功": img is not None,
        }
    )

    # 再渲染一次（测缓存效果）
    t0 = time.time()
    img2 = doc.render_composition()
    report["steps"].append({"步骤": "二次渲染(缓存)", "耗时": _elapsed(t0), "成功": img2 is not None})

    if img:
        img.save(os.path.join(OUTDIR, "run-02-rendered.png"))

    _shot(win, "run-02-edit-flow")
    win.close()
    return report


# --------------------------------------------------------------------------
# 场景 3：批量导出真实执行
# --------------------------------------------------------------------------
def scenario_batch_export():
    report = {"scenario": "批量导出", "steps": []}
    from app.models.document import Document

    app, win = _bootstrap()

    doc = Document(parent=win)
    doc.create_new(800, 800)
    doc.add_layer("商品图", 0, 0, 800, 800, image_source=ASSETS)
    _pump(app, 8)

    from app.utils.optimized_batch_executor import OptimizedBatchExportManager

    out_dir = os.path.join(ROOT, "_run_output")
    if os.path.isdir(out_dir):
        for f in os.listdir(out_dir):
            os.remove(os.path.join(out_dir, f))
    os.makedirs(out_dir, exist_ok=True)

    # 真实调用链与 ExportWorker 一致：先分析文档，再执行导出
    analysis = doc._analyze_document_for_export()

    progress_hits = []
    degradations = {}

    t0 = time.time()
    try:
        ok = OptimizedBatchExportManager.export_batch_optimized_v2(
            document=doc,
            document_analysis=analysis,
            directory=out_dir,
            count=10,
            filename_template="batch_{number:04d}",
            file_format="jpg",
            progress_callback=lambda v: progress_hits.append(v),
        )
        report["steps"].append(
            {
                "步骤": "执行批量导出(10张)",
                "耗时": _elapsed(t0),
                "返回": ok,
                "进度回调次数": len(progress_hits),
                "最终进度": progress_hits[-1] if progress_hits else None,
            }
        )
    except Exception as e:
        report["error"] = f"{type(e).__name__}: {e}"
        report["traceback"] = traceback.format_exc()[-1500:]
        return report

    files = sorted(os.listdir(out_dir)) if os.path.isdir(out_dir) else []
    report["输出文件数"] = len(files)
    report["样例"] = files[:6]
    if files:
        sizes = [os.path.getsize(os.path.join(out_dir, f)) for f in files]
        report["体积KB"] = [round(s / 1024, 1) for s in sizes[:6]]
    win.close()
    return report


# --------------------------------------------------------------------------
# 场景 4：窗口缩放（真实 DPI 下的布局稳定性）
# --------------------------------------------------------------------------
def scenario_resize():
    report = {"scenario": "窗口缩放", "sizes": []}
    app, win = _bootstrap()

    from app.models.document import Document

    doc = Document(parent=win)
    doc.create_new(1200, 900)
    win.create_new_tab(doc)
    _pump(app, 10)

    for w, h, tag in [(1280, 800, "small"), (1600, 1000, "normal"), (2100, 1300, "large")]:
        t0 = time.time()
        win.resize(w, h)
        _pump(app, 14)
        actual = (win.width(), win.height())
        # 检查是否有子控件溢出父容器
        overflow = []
        from PySide6.QtWidgets import QWidget

        for child in win.findChildren(QWidget):
            if not child.isVisible() or child.width() <= 0:
                continue
            parent = child.parentWidget()
            if parent is None:
                continue
            if child.x() + child.width() > parent.width() + 2:
                overflow.append(f"{type(child).__name__}({child.x()}+{child.width()}>{parent.width()})")
        report["sizes"].append(
            {
                "请求": f"{w}x{h}",
                "实际": f"{actual[0]}x{actual[1]}",
                "耗时": _elapsed(t0),
                "溢出控件": overflow[:5],
                "溢出数": len(overflow),
            }
        )
        _shot(win, f"run-04-resize-{tag}")

    win.close()
    return report


SCENARIOS = {
    "startup": scenario_startup,
    "edit": scenario_edit_flow,
    "batch": scenario_batch_export,
    "resize": scenario_resize,
}


def main():
    if len(sys.argv) > 1:
        name = sys.argv[1]
        report = SCENARIOS[name]()
        print("@@REPORT@@" + json.dumps(report, ensure_ascii=False))
        return 0

    all_reports = []
    for name in SCENARIOS:
        proc = subprocess.run(
            [sys.executable, __file__, name],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=ROOT,
            env={**os.environ, "PYTHONIOENCODING": "utf-8"},
            timeout=420,
        )
        line = next(
            (l for l in proc.stdout.splitlines() if l.startswith("@@REPORT@@")), None
        )
        if line:
            all_reports.append(json.loads(line[len("@@REPORT@@"):]))
        else:
            tail = (proc.stdout or "")[-800:] + (proc.stderr or "")[-1200:]
            all_reports.append(
                {
                    "scenario": name,
                    "error": f"exit={proc.returncode}",
                    "traceback": tail,
                }
            )

    print(json.dumps(all_reports, ensure_ascii=False, indent=2))
    with open(os.path.join(ROOT, "_run_report.json"), "w", encoding="utf-8") as f:
        json.dump(all_reports, f, ensure_ascii=False, indent=2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
