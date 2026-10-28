"""拼图主流程（被 themes_10_main_ui 调用）。

为什么分两步：
  1. 先按充足尺寸 (1000x640) 正常布局渲染每个方案
  2. 再把位图等比缩放到格子尺寸拼图

直接用 setFixedSize 把控件塞进小格子会让 sizeHint 放不下，
Qt 会把超出部分画到相邻格子，造成整张图错位。
"""
from __future__ import annotations


def render_one(app, build_ui, qss, t, w=1000, h=640, settle=18):
    from PySide6.QtGui import QPixmap
    from PySide6.QtCore import QCoreApplication

    win = build_ui(t)
    win.setStyleSheet(qss(t))
    win.resize(w, h)
    win.show()
    for _ in range(settle):
        QCoreApplication.processEvents()

    pm = QPixmap(win.size())
    pm.fill()
    win.render(pm)
    win.hide()
    win.deleteLater()
    QCoreApplication.processEvents()
    return pm


def compose(app, themes, build_ui, qss, out_path,
            render_size=(1000, 640), cell_size=(700, 448), head_h=26, gap=6, cols=2):
    from PySide6.QtGui import QPixmap, QPainter, QColor, QFont
    from PySide6.QtCore import Qt

    rw, rh = render_size
    cw, ch = cell_size

    shots = {}
    for t in themes:
        shots[t["key"]] = render_one(app, build_ui, qss, t, rw, rh)
        print(f"  渲染 {t['key']} {t['name']}")

    rows = (len(themes) + cols - 1) // cols
    total_w = cw * cols + gap * (cols + 1)
    total_h = (ch + head_h) * rows + gap * (rows + 1)

    sheet = QPixmap(total_w, total_h)
    sheet.fill(Qt.black)
    p = QPainter(sheet)
    p.setRenderHint(QPainter.SmoothPixmapTransform, True)
    p.setRenderHint(QPainter.Antialiasing, True)

    fam = "Microsoft YaHei UI"
    for i, t in enumerate(themes):
        r, c = divmod(i, cols)
        x = gap + c * (cw + gap)
        y = gap + r * (ch + head_h + gap)

        # 标题条
        p.fillRect(x, y, cw, head_h, QColor(t["s1"]))
        f = QFont(fam, 9)
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(t["text"]))
        p.drawText(x + 8, y, cw - 16, head_h, Qt.AlignLeft | Qt.AlignVCenter,
                   f"{t['key']}  {t['name']}")
        f2 = QFont(fam, 8)
        p.setFont(f2)
        p.setPen(QColor(t["muted"]))
        p.drawText(x + 8, y, cw - 16, head_h, Qt.AlignRight | Qt.AlignVCenter, t["ref"])

        # 界面（等比缩放到格子）
        scaled = shots[t["key"]].scaled(cw, ch, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
        p.drawPixmap(x, y + head_h, scaled)

    p.end()
    ok = sheet.save(str(out_path), "PNG")
    print(f"\n已生成: {out_path}  ok={ok}  {sheet.width()}x{sheet.height()}")
    return ok
