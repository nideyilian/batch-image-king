"""10 个方案的完整主界面渲染。

还原批图王真实工作区结构：
  菜单栏 / 工具栏 / 左侧图层面板 / 中央画布 / 右侧属性面板 / 底部状态栏

同一个界面骨架，只换设计语言，便于横向比较。
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tools"))

from themes_10 import THEMES  # noqa: E402

OUT = ROOT / "docs" / "themes-10-main-ui.png"

# 画布上那几张"图"的填充色（中性，不抢主题色）
ART = ["#3B4A5E", "#5E4A3B", "#3B5E4A", "#5E3B4A"]


def _is_light(h: str) -> bool:
    h = h.lstrip("#")
    if len(h) < 6:
        return False
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return (0.2126 * r + 0.7152 * g + 0.0722 * b) > 150


def qss(t) -> str:
    light = _is_light(t["bg"])
    on_accent = "#FFFFFF"
    if t["key"] == "07":
        on_accent = "#0B0B0B"

    bw = t["border_w"]
    b_css = f"{bw}px solid {t['border']}" if bw else "none"
    fam = '"Microsoft YaHei UI","Microsoft YaHei",sans-serif'
    r = t["radius"]
    ch = t["ctrl_h"]

    # 画布区：比底色再暗/亮一点，突出工作区
    canvas_bg = "#0A0B0C" if not light else "#E8EAED"
    if t["key"] == "03":
        canvas_bg = "#0B1220"
    if t["key"] == "04":
        canvas_bg = "#141110"
    if t["key"] == "07":
        canvas_bg = "#000000"
    if t["key"] == "09":
        canvas_bg = "#0D1214"
    if t["key"] == "02":
        canvas_bg = "#1A1A1A"

    return f"""
    QWidget#root {{ background: {t['bg']}; }}
    QLabel {{ color: {t['text']}; font-family: {fam}; font-size: {t['fs']}px; }}
    QLabel#appname {{ font-size: {t['fs']}px; font-weight: 700; }}
    QLabel#sec {{ font-size: {t['fs']}px; font-weight: 600; color: {t['text2']}; }}
    QLabel#muted {{ color: {t['muted']}; font-size: {t['fs'] - 2}px; }}
    QLabel#tab-active {{ color: {t['text']}; font-weight: 600; }}
    QLabel#tab {{ color: {t['muted']}; }}

    /* 菜单栏 */
    QWidget#menubar {{ background: {t['s1']}; border: none;
                       border-bottom: {bw if bw else 1}px solid {t['border']}; }}

    /* 工具栏 */
    QWidget#toolbar {{ background: {t['s1']}; border: none;
                       border-bottom: {bw if bw else 1}px solid {t['border']}; }}
    QPushButton#tool {{
        background: transparent; border: none; color: {t['text2']};
        padding: 0 9px; min-height: {ch - 4}px; border-radius: {max(2, r - 2)}px;
        font-family: {fam}; font-size: {t['fs']}px;
    }}
    QPushButton#tool:hover {{ background: {t['s3']}; color: {t['text']}; }}
    QPushButton#toolOn {{ background: {t['accent']}; color: {on_accent}; border: none;
        padding: 0 9px; min-height: {ch - 4}px; border-radius: {max(2, r - 2)}px;
        font-family: {fam}; font-size: {t['fs']}px; }}

    /* 面板 */
    QWidget#panel {{ background: {t['s1']}; border: none; }}
    QWidget#panelBorder {{ background: {t['s1']};
        border-left: {bw if bw else 1}px solid {t['border']}; }}

    /* 图层行 */
    QLabel#layerSel {{ background: {t.get('sel_bg', t['accent'])}; color: {t.get('sel_fg', on_accent)};
        border-radius: {max(2, r - 2)}px; padding-left: 6px; }}
    QLabel#layer {{ color: {t['text']}; padding-left: 6px; }}
    QLabel#layerDim {{ color: {t['muted']}; padding-left: 6px; }}

    /* 画布 */
    QWidget#canvas {{ background: {canvas_bg}; }}
    QWidget#artboard {{ background: #FFFFFF; border: none; }}

    /* 输入 */
    QLineEdit {{
        font-family: {fam}; font-size: {t['fs']}px; min-height: {ch - 4}px;
        padding: 0 8px; background: {t['s3']}; color: {t['text']};
        border: {b_css}; border-radius: {max(2, r - 2)}px;
    }}

    /* 主按钮 */
    QPushButton#primary {{
        background: {t['accent']}; color: {on_accent}; border: none;
        min-height: {ch}px; padding: 0 {t['pad']}px;
        border-radius: {r}px; font-family: {fam}; font-size: {t['fs']}px; font-weight: 600;
    }}

    /* 状态栏 */
    QWidget#statusbar {{ background: {t['s1']}; border: none;
                         border-top: {bw if bw else 1}px solid {t['border']}; }}
    """


def build_ui(t):
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
        QFrame,
    )
    from PySide6.QtCore import Qt

    fam = '"Microsoft YaHei UI","Microsoft YaHei",sans-serif'
    root = QWidget()
    root.setObjectName("root")
    outer = QVBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    # ---------- 菜单栏 ----------
    mb = QWidget()
    mb.setObjectName("menubar")
    mbl = QHBoxLayout(mb)
    mbl.setContentsMargins(10, 3, 10, 3)
    mbl.setSpacing(14)
    name = QLabel("批图王")
    name.setObjectName("appname")
    mbl.addWidget(name)
    for m in ("文件", "编辑", "图层", "画布", "预设", "视图", "帮助"):
        lb = QLabel(m)
        lb.setObjectName("tab")
        mbl.addWidget(lb)
    mbl.addStretch()
    ver = QLabel("v1.2.0")
    ver.setObjectName("muted")
    mbl.addWidget(ver)
    outer.addWidget(mb)

    # ---------- 工具栏 ----------
    tb = QWidget()
    tb.setObjectName("toolbar")
    tbl = QHBoxLayout(tb)
    tbl.setContentsMargins(8, 4, 8, 4)
    tbl.setSpacing(2)
    for label, on in (("新建", False), ("打开", False), ("保存", False),
                      ("撤销", False), ("重做", False),
                      ("文字", True), ("异形", False), ("图片", False),
                      ("对齐", False), ("批量导出", False)):
        b = QPushButton(label)
        b.setObjectName("toolOn" if on else "tool")
        tbl.addWidget(b)
    tbl.addStretch()
    for label in ("标尺", "参考线", "缩放 100%"):
        b = QPushButton(label)
        b.setObjectName("tool")
        tbl.addWidget(b)
    outer.addWidget(tb)

    # ---------- 主体 ----------
    body = QWidget()
    bl = QHBoxLayout(body)
    bl.setContentsMargins(0, 0, 0, 0)
    bl.setSpacing(0)

    # --- 左：图层面板 ---
    left = QWidget()
    left.setObjectName("panel")
    left.setFixedWidth(196)
    ll = QVBoxLayout(left)
    ll.setContentsMargins(t["pad"] - 4, t["pad"] - 4, t["pad"] - 4, t["pad"] - 4)
    ll.setSpacing(t["gap"] - 4)

    lh = QLabel("图层")
    lh.setObjectName("sec")
    ll.addWidget(lh)

    layers = [
        ("主标题文字", True, False),
        ("商品图 01", False, False),
        ("促销标签", False, False),
        ("背景图层", False, True),
        ("阴影效果", False, True),
    ]
    for text, selected, dim in layers:
        row = QLabel(("● " if selected else "○ ") + text)
        row.setObjectName("layerSel" if selected else ("layerDim" if dim else "layer"))
        row.setFixedHeight(t["ctrl_h"] - 4)
        ll.addWidget(row)

    ll.addSpacing(4)
    cnt = QLabel(f"共 {len(layers)} 层 · 1 层隐藏")
    cnt.setObjectName("muted")
    ll.addWidget(cnt)
    ll.addStretch()
    bl.addWidget(left)

    # --- 中：画布 ---
    canvas = QWidget()
    canvas.setObjectName("canvas")
    cl = QVBoxLayout(canvas)
    cl.setContentsMargins(0, 0, 0, 0)
    cl.setSpacing(0)

    # 标签页条
    tabbar = QWidget()
    tabbar.setObjectName("panel")
    tbl2 = QHBoxLayout(tabbar)
    tbl2.setContentsMargins(10, 4, 10, 4)
    tbl2.setSpacing(16)
    t1 = QLabel("未命名-1 ●")
    t1.setObjectName("tab-active")
    tbl2.addWidget(t1)
    t2 = QLabel("促销图-A")
    t2.setObjectName("tab")
    tbl2.addWidget(t2)
    tbl2.addStretch()
    cl.addWidget(tabbar)

    # 画布区域（居中放画板）
    area = QWidget()
    area.setObjectName("canvas")
    al = QVBoxLayout(area)
    al.setContentsMargins(36, 28, 36, 28)
    al.addStretch()

    board = QWidget()
    board.setObjectName("artboard")
    board.setFixedSize(300, 220)
    bd = QVBoxLayout(board)
    bd.setContentsMargins(0, 0, 0, 0)
    bd.setSpacing(0)

    # 画板里放模拟的图层内容
    from PySide6.QtWidgets import QLabel as _L
    art1 = _L("")
    art1.setFixedHeight(130)
    art1.setStyleSheet(f"background:{ART[0]};")
    bd.addWidget(art1)

    band = _L("  限时特惠 · 全场 5 折")
    band.setFixedHeight(46)
    band.setAlignment(Qt.AlignVCenter)
    band.setStyleSheet(
        f"background:{ART[1]}; color:#FFFFFF; font-family:{fam}; "
        f"font-size:{t['fs'] + 3}px; font-weight:700;"
    )
    bd.addWidget(band)

    foot = _L("")
    foot.setFixedHeight(44)
    foot.setStyleSheet(f"background:{ART[2]};")
    bd.addWidget(foot)

    al.addWidget(board, alignment=Qt.AlignHCenter)
    al.addStretch()
    cl.addWidget(area)
    bl.addWidget(canvas, 1)

    # --- 右：属性面板 ---
    right = QWidget()
    right.setObjectName("panelBorder")
    right.setFixedWidth(230)
    rl = QVBoxLayout(right)
    rl.setContentsMargins(t["pad"] - 4, t["pad"] - 4, t["pad"] - 4, t["pad"] - 4)
    rl.setSpacing(t["gap"] - 4)

    rh = QLabel("属性 · 文字图层")
    rh.setObjectName("sec")
    rl.addWidget(rh)

    for label, val in (("内容", "限时特惠 · 全场 5 折"),
                       ("字体", "思源黑体 Bold"),
                       ("字号", "48 px")):
        lb = QLabel(label)
        lb.setObjectName("muted")
        rl.addWidget(lb)
        e = QLineEdit(val)
        rl.addWidget(e)

    rl.addSpacing(2)
    lb2 = QLabel("位置与尺寸")
    lb2.setObjectName("sec")
    rl.addWidget(lb2)

    xy = QHBoxLayout()
    xy.setSpacing(6)
    e1 = QLineEdit("120")
    e2 = QLineEdit("260")
    xy.addWidget(e1)
    xy.addWidget(e2)
    rl.addLayout(xy)

    rl.addSpacing(2)
    b = QPushButton("应用到全部图层")
    b.setObjectName("primary")
    rl.addWidget(b)

    rl.addStretch()
    bl.addWidget(right)

    outer.addWidget(body, 1)

    # ---------- 状态栏 ----------
    sb = QWidget()
    sb.setObjectName("statusbar")
    sbl = QHBoxLayout(sb)
    sbl.setContentsMargins(10, 3, 10, 3)
    sbl.setSpacing(16)
    s1 = QLabel("1200 × 900 px · 72 dpi")
    s1.setObjectName("muted")
    sbl.addWidget(s1)
    s2 = QLabel("已选中：主标题文字")
    s2.setObjectName("muted")
    sbl.addWidget(s2)
    sbl.addStretch()
    s3 = QLabel("就绪")
    s3.setObjectName("muted")
    sbl.addWidget(s3)
    outer.addWidget(sb)

    return root




def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtGui import QFontDatabase

    app = QApplication.instance() or QApplication(sys.argv)
    for p in (r"C:/Windows/Fonts/msyh.ttc", r"C:/Windows/Fonts/msyhbd.ttc"):
        QFontDatabase.addApplicationFont(p)

    from _compose import compose
    ok = compose(app, THEMES, build_ui, qss, OUT, cell_size=(860, 550), head_h=30, gap=8)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
