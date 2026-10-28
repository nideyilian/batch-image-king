"""真实窗口演示：载入素材 → 建图层 → 加文字 → 截真实屏幕。

用途：给杰哥看「实际使用中的界面长什么样」，不是离屏渲染的假图。
每一步都打时间戳，顺手确认交互没有卡顿或错位。

用法：
    python tools/demo_live.py
"""

from __future__ import annotations

import ctypes
import os
import sys
import time
from ctypes import wintypes

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.pop("QT_QPA_PLATFORM", None)

from PySide6.QtCore import QCoreApplication  # noqa: E402
from PySide6.QtGui import QFont, QFontDatabase  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

ASSETS = os.path.join(ROOT, "docs", "ui-review", "demo-assets")
OUT = os.path.join(ROOT, "docs", "ui-review")


def bring_to_front(hint: str = "") -> tuple[int, int, int, int] | None:
    """把本进程的顶层窗口置前，返回其物理像素矩形。

    为什么按 PID 而不是按标题找：MainWindow 的标题会随打开的文档变化
    （`绑定测试.cmp` / 未命名-1 等），按固定标题匹配必然失败。
    """
    u32 = ctypes.windll.user32
    pid = os.getpid()

    found: list[int] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def enum_proc(hwnd, _lparam):
        owner = wintypes.DWORD()
        u32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value != pid:
            return True
        if not u32.IsWindowVisible(hwnd):
            return True
        # 只要有标题的顶层窗口就算（排除 Qt 的内部隐藏窗口）
        length = u32.GetWindowTextLengthW(hwnd)
        if length > 0:
            found.append(hwnd)
        return True

    u32.EnumWindows(enum_proc, 0)
    if not found:
        return None

    hwnd = found[0]
    u32.ShowWindow(hwnd, 9)          # SW_RESTORE
    u32.SetForegroundWindow(hwnd)
    u32.BringWindowToTop(hwnd)
    time.sleep(0.9)
    r = wintypes.RECT()
    u32.GetWindowRect(hwnd, ctypes.byref(r))
    title_len = u32.GetWindowTextLengthW(hwnd)
    buf = ctypes.create_unicode_buffer(title_len + 1)
    u32.GetWindowTextW(hwnd, buf, title_len + 1)
    if hint:
        print(f"  窗口标题: {buf.value!r}")
    return r.left, r.top, r.right - r.left, r.bottom - r.top


def grab_window(rect, name: str) -> None:
    """按物理像素裁切真实屏幕。GetWindowRect 返回的就是物理像素，不要再乘 DPR。"""
    full = QApplication.primaryScreen().grabWindow(0)
    x, y, w, h = rect
    x, y = max(0, x), max(0, y)
    w = min(w, full.width() - x)
    h = min(h, full.height() - y)
    path = os.path.join(OUT, name)
    full.copy(x, y, w, h).save(path, "PNG")
    print(f"  截图: {name}  {w}x{h}")


def main() -> int:
    t0 = time.time()

    def stamp(msg: str) -> None:
        print(f"  [{(time.time() - t0) * 1000:6.0f}ms] {msg}")

    app = QApplication([])
    for path in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(path)
    app.setFont(QFont("Microsoft YaHei UI", 9))

    from app.ui.dark_theme import CursorDarkTheme

    CursorDarkTheme.apply_to_application(app)
    stamp("主题就绪")

    from app.main_window import MainWindow
    from app.models.document import Document

    win = MainWindow()
    win.resize(1500, 960)
    stamp("主窗口构造完成")

    doc = Document(parent=win)
    doc.create_new(900, 900)
    doc.name = "秋季大促-主图"
    win.create_new_tab(doc)
    stamp("新建 900x900 文档")

    # 1) 图片图层：真实素材目录
    doc.add_layer("商品主图", 0, 0, 900, 900, image_source=ASSETS)
    stamp("添加图片图层（真实素材 6 张）")

    # 2) 文字图层：走快速建层
    win.layer_controller.add_configured_text_layer(
        {
            "content": "秋季大促",
            "font_size": 96,
            "color": "#F7F8F8",
            "alignment": "center",
            "binding_enabled": False,
            "name": "主标题",
        }
    )
    stamp("添加主标题文字层")

    win.layer_controller.add_configured_text_layer(
        {
            "content": "全场 5 折起 · 仅限 3 天",
            "font_size": 44,
            "color": "#FF8A3D",
            "alignment": "center",
            "binding_enabled": False,
            "name": "副标题",
        }
    )
    stamp("添加副标题文字层")

    win.show()
    for _ in range(30):
        QCoreApplication.processEvents()
    stamp("窗口显示")

    # 让画布真正重绘一次
    tab = win.tab_widget.currentWidget()
    if hasattr(tab, "canvas"):
        tab.canvas.update()
    for _ in range(20):
        QCoreApplication.processEvents()

    rect = bring_to_front(hint="图像批量合成工具")
    if rect is None:
        print("  找不到窗口，跳过截图")
        return 1
    grab_window(rect, "demo-live-main.png")

    # 单独截左栏图层 / 右栏属性（放大看细节）
    for panel, name in ((win.layer_panel, "demo-live-layers.png"),
                        (win.properties_panel, "demo-live-props.png")):
        pm = panel.grab()
        pm.save(os.path.join(OUT, name), "PNG")
        print(f"  截图: {name}  {pm.width()}x{pm.height()}")

    print(f"\n图层数: {len(doc.layers)}")
    for layer in doc.layers:
        print(f"  {layer.name!r}  {layer.width}x{layer.height}")

    print("\n窗口保持打开 25 秒供查看...")
    deadline = time.time() + 25
    while time.time() < deadline:
        QCoreApplication.processEvents()
        time.sleep(0.05)

    win.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
