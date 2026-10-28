"""组件库/图标库展示素材渲染（离屏，生成 PNG 供 HTML 图库引用）。

只做一件事：把项目里真实的组件实例渲染成图片，保证展示页不是"我手画的仿制品"。
"""
import os
import sys
import traceback

os.environ["QT_QPA_PLATFORM"] = "offscreen"
ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
OUT = os.path.join(ROOT, "_gallery_assets")
os.makedirs(OUT, exist_ok=True)

from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QFontDatabase, QFont, QPixmap, QColor
from PySide6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QGridLayout, QSizePolicy,
)

app = QApplication([])

# 离屏模式下 Qt 找不到系统字体族，手动注册（否则中文全是方块）
for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc",
          r"C:\Windows\Fonts\segoeui.ttf", r"C:\Windows\Fonts\consola.ttf"):
    if os.path.exists(p):
        QFontDatabase.addApplicationFont(p)

from app.ui.dark_theme import CursorDarkTheme
from app.ui.theme import apply_theme

CursorDarkTheme.apply(app) if hasattr(CursorDarkTheme, "apply") else None
apply_theme(app)

from app.ui.components import (
    Button, button, Card, CardHeader, CardTitle, CardDescription, CardContent,
    Input, Label, Checkbox, RadioButton, Slider, Switch, Badge, Alert,
    Separator, ProgressBar, Skeleton, Spinner, EmptyState, Toast,
    H1, H2, H3, Text, Muted, Small, Code, Kbd,
    IconButton, SegmentedControl, ButtonGroup, Toggle,
    NumberInput, Textarea, ComboBox, ColorSwatch, Field,
    Table, FileDropZone,
)
from app.ui.icon_library import icon, IconName

log = []


def shot(widget, name, pad=16, bg="#0A0B0D"):
    """把控件渲染成 PNG（带留白，避免贴边）。

    用 grab() 而不是 render(QPainter)：离屏模式下 render 遇到部分子控件
    （QToolButton / QComboBox 弹层相关）会整进程静默退出，grab 不会。
    """
    print("  -> render", name, flush=True)
    widget.setAttribute(Qt.WA_DontShowOnScreen, True)
    widget.adjustSize()
    widget.resize(max(widget.sizeHint().width(), widget.width()),
                  max(widget.sizeHint().height(), widget.height()))
    src = widget.grab()
    w, h = src.width() + pad * 2, src.height() + pad * 2
    pm = QPixmap(w, h)
    pm.fill(QColor(bg))
    from PySide6.QtGui import QPainter
    painter = QPainter(pm)
    painter.drawPixmap(pad, pad, src)
    painter.end()
    path = os.path.join(OUT, name)
    pm.save(path)
    log.append((name, pm.width(), pm.height()))
    print("     saved", w, h, flush=True)
    return path


def panel(title, note=""):
    w = QWidget()
    v = QVBoxLayout(w)
    v.setContentsMargins(20, 18, 20, 20)
    v.setSpacing(12)
    if title:
        t = QLabel(title)
        t.setStyleSheet("color:#B4BCC6;font-size:11px;letter-spacing:.4px;")
        v.addWidget(t)
    return w, v


def row(*widgets, spacing=10):
    box = QWidget()
    h = QHBoxLayout(box)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(spacing)
    for x in widgets:
        if isinstance(x, str):
            w = QLabel(x)
            w.setStyleSheet("color:#6B7079;font-size:11px;")
            h.addWidget(w)
        else:
            h.addWidget(x)
    h.addStretch(1)
    return box


# ── 1. 按钮变体 ────────────────────────────────────────────────
try:
    w, v = panel("BUTTON / variant")
    v.addWidget(row(*[Button(vr, variant=vr) for vr in
                      ("default", "secondary", "outline", "ghost", "destructive", "link")]))
    v.addWidget(row("size：", Button("SM", size="sm"), Button("DEFAULT", size="default"),
                    Button("LG", size="lg")))
    v.addWidget(row("state：", Button("normal"), Button("disabled"),
                    Button("primary", variant="default")))
    dis = Button("已禁用")
    dis.setEnabled(False)
    v.layout().itemAt(2).widget().layout().addWidget(dis)
    shot(w, "buttons.png")
except Exception:
    log.append(("buttons.png", "FAIL", traceback.format_exc()[-300:]))

# ── 2. 图标按钮 + 分段控件 ──────────────────────────────────────
try:
    w, v = panel("ICON BUTTON / SEGMENTED")
    grp = ButtonGroup()
    for nm, tip in (("undo", "撤销"), ("redo", "重做"), ("save", "保存"),
                    ("copy", "复制"), ("delete", "删除")):
        grp.add_button(IconButton(nm, tip))
    v.addWidget(grp)
    seg = SegmentedControl([("fit", "适应"), ("100", "100%"), ("200", "200%")])
    v.addWidget(row("分段：", seg))
    tg = Toggle("网格", icon=icon("sort"))
    tg.setChecked(True)
    v.addWidget(row("切换：", tg))
    shot(w, "icon_buttons.png")
except Exception:
    log.append(("icon_buttons.png", "FAIL", traceback.format_exc()[-300:]))

# ── 3. 表单控件 ────────────────────────────────────────────────
try:
    w, v = panel("FORM CONTROLS")
    g = QGridLayout()
    g.setHorizontalSpacing(16)
    g.setVerticalSpacing(10)
    g.addWidget(Label("图层名称"), 0, 0)
    g.addWidget(Input(placeholder="未命名图层"), 0, 1)
    g.addWidget(Label("画布宽度"), 1, 0)
    ni = NumberInput(value=1080, maximum=9999, suffix=" px")
    g.addWidget(ni, 1, 1)
    g.addWidget(Label("导出格式"), 2, 0)
    cb = ComboBox(items=["PNG", "JPG", "WEBP"])
    g.addWidget(cb, 2, 1)
    g.addWidget(Label("透明度"), 3, 0)
    sl = Slider(Qt.Horizontal)
    sl.setValue(80)
    g.addWidget(sl, 3, 1)
    v.addLayout(g)
    v.addWidget(row(Checkbox("包含隐藏图层"), Checkbox("导出后打开目录"),
                    RadioButton("单张"), RadioButton("批量"), Switch()))
    ta = Textarea(placeholder="批量文案，一行一条…")
    ta.setFixedHeight(56)
    v.addWidget(ta)
    shot(w, "forms.png")
except Exception:
    log.append(("forms.png", "FAIL", traceback.format_exc()[-300:]))

# ── 4. 反馈类 ──────────────────────────────────────────────────
try:
    w, v = panel("FEEDBACK")
    br = QWidget()
    bh = QHBoxLayout(br)
    bh.setContentsMargins(0, 0, 0, 0)
    bh.setSpacing(8)
    for vr in ("default", "primary", "success", "warning", "destructive", "outline"):
        bh.addWidget(Badge(vr, vr))
    bh.addStretch(1)
    v.addWidget(br)
    v.addWidget(Alert("批量导出完成", "成功 128 张，跳过 3 张（源图缺失）", variant="success"))
    v.addWidget(Alert("源图路径失效", "有 3 个图层指向的文件已不存在", variant="destructive"))
    pb = ProgressBar()
    pb.set_progress(64)
    v.addWidget(pb)
    v.addWidget(Skeleton(height=10))
    shot(w, "feedback.png")
except Exception:
    log.append(("feedback.png", "FAIL", traceback.format_exc()[-300:]))

# ── 5. 卡片 + 排版 ────────────────────────────────────────────
try:
    w, v = panel("CARD / TYPOGRAPHY")
    c = Card()
    hd = CardHeader()
    hd.add_widget(CardTitle("导出设置"))
    hd.add_widget(CardDescription("配置批量导出的尺寸、格式与命名规则"))
    c.add_widget(hd)
    body = CardContent()
    body.add_widget(Text("输出目录：D:/output/2026-10-28"))
    body.add_widget(Muted("命名规则  {{序号}}_{{时间戳}}"))
    c.add_widget(body)
    v.addWidget(c)
    v.addWidget(H1("H1 一级标题"))
    v.addWidget(H3("H3 区块标题"))
    v.addWidget(row(Text("正文 13px"), Muted("次要 B4BCC6"), Small("辅助 11px"),
                    Code("{{序号}}"), Kbd("Ctrl+S")))
    w.setFixedWidth(430)
    shot(w, "card_type.png")
except Exception:
    log.append(("card_type.png", "FAIL", traceback.format_exc()[-300:]))

# ── 6. mdi6 图标（真实 qtawesome 渲染）────────────────────────
try:
    from app.ui.icon_library import HAS_QTawesome
    from app.ui.tokens_v2 import Color as C
    names = [k for k in vars(IconName) if k.isupper()]
    cols = 8
    cell, gap = 44, 8
    pad = 18
    rows = (len(names) + cols - 1) // cols
    cap = 16
    W = pad * 2 + cols * cell + (cols - 1) * gap
    Hh = pad * 2 + rows * (cell + cap + 6)
    pm = QPixmap(W, Hh)
    pm.fill(QColor("#0A0B0D"))
    from PySide6.QtGui import QPainter, QFont as F
    p = QPainter(pm)
    small = F("Microsoft YaHei UI", 6)
    for i, k in enumerate(names):
        r, c0 = divmod(i, cols)
        x = pad + c0 * (cell + gap)
        y = pad + r * (cell + cap + 6)
        ic = icon(getattr(IconName, k), color=C.text_secondary)
        ic.paint(p, x + (cell - 20) // 2, y + (cell - 20) // 2, 20, 20)
        p.setFont(small)
        p.setPen(QColor("#6B7079"))
        p.drawText(x - 4, y + cell + 10, cell + 8, cap,
                   Qt.AlignHCenter | Qt.AlignTop, k.lower().replace("_", ""))
    p.end()
    pm.save(os.path.join(OUT, "icons_mdi6.png"))
    log.append(("icons_mdi6.png", W, Hh))
except Exception:
    log.append(("icons_mdi6.png", "FAIL", traceback.format_exc()[-300:]))

print("\n".join(f"{n}: {a}x{b}" if isinstance(a, int) else f"{n}: {a} {b}"
                for n, a, b in log))
