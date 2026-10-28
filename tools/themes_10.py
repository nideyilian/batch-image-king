"""10 个视觉方向对照图。

每个方案用同一组控件渲染（按钮 / 输入框 / 列表 / 卡片），
差异只来自设计语言本身：底色体系、边框策略、圆角、间距节奏、强调色。

参考来源均为成熟产品，不是凭空配色。
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "_themes_10.png"

# ---------------------------------------------------------------------------
# 10 个方案
# ---------------------------------------------------------------------------
THEMES = [
    dict(
        key="01", sel_bg="#1F2437", sel_fg="#E4E7FF", name="墨黑极简", ref="Linear / Vercel",
        note="近纯黑，无边框靠亮度分层，字距收紧",
        bg="#08090A", s1="#0F1011", s2="#161719", s3="#1D1F21",
        text="#F7F8F8", text2="#B4BCC6", muted="#7A838D",
        accent="#5E6AD2", accent_h="#4F5ABF", danger="#C4342B",
        border="#23252A", border_w=0, radius=6, ctrl_h=30,
        gap=10, pad=14, fs=13, fw_title=600,
    ),
    dict(
        key="02", sel_bg="#094771", sel_fg="#FFFFFF", name="石板·编辑器", ref="VS Code Dark+",
        note="经典编辑器灰，方正直角，密度高",
        bg="#1E1E1E", s1="#252526", s2="#2D2D30", s3="#3C3C3C",
        text="#D4D4D4", text2="#C0C0C0", muted="#9A9A9A",
        accent="#0C5A8F", accent_h="#1177BB", danger="#A33A32",
        border="#3C3C3C", border_w=1, radius=2, ctrl_h=28,
        gap=8, pad=12, fs=13, fw_title=600,
    ),
    dict(
        key="03", sel_bg="#1E3358", sel_fg="#DCE8FF", name="深蓝夜", ref="Night Owl / Raycast",
        note="蓝调底，冷感专业，适合长时间盯屏",
        bg="#0F1729", s1="#16213E", s2="#1B2A4A", s3="#22345A",
        text="#E8F0FF", text2="#B6C6E3", muted="#7E92B8",
        accent="#2166C9", accent_h="#3A7AE8", danger="#D14343",
        border="#24365C", border_w=0, radius=8, ctrl_h=30,
        gap=12, pad=14, fs=13, fw_title=600,
    ),
    dict(
        key="04", sel_bg="#3A2A22", sel_fg="#FFE4D6", name="暖炭·护眼", ref="Anthropic / 暖色系",
        note="暖灰底减蓝光，长时间用眼更舒适",
        bg="#1A1714", s1="#221E1A", s2="#2B2622", s3="#352F2A",
        text="#F0E9E0", text2="#CFC4B6", muted="#9C9083",
        accent="#B85A3C", accent_h="#C4674A", danger="#B03A2E",
        border="#3A332C", border_w=0, radius=8, ctrl_h=30,
        gap=12, pad=14, fs=13, fw_title=600,
    ),
    dict(
        key="05", sel_bg="#2E2A4D", sel_fg="#E8E4FF", btn_fg="#FFFFFF", name="玻璃拟态", ref="Figma / macOS Big Sur",
        note="半透明层叠，圆角大，浮层感强",
        bg="#171922", s1="#232634", s2="#2B2F40", s3="#343A4D",
        text="#F5F6FA", text2="#C3C7D4", muted="#9096A8",
        accent="#6D55E0", accent_h="#6A50E8", danger="#E5484D",
        border="#3E4459", border_w=1, radius=12, ctrl_h=32,
        gap=12, pad=16, fs=13, fw_title=600,
    ),
    dict(
        key="06", sel_bg="#E4EDFD", sel_fg="#1A3E8C", name="亮色·清爽", ref="Notion / Linear Light",
        note="浅灰白底，彩色强调，白天办公友好",
        bg="#FBFBFC", s1="#FFFFFF", s2="#F4F5F7", s3="#EDEFF2",
        text="#1A1D21", text2="#4A5058", muted="#5F6771",
        accent="#2563EB", accent_h="#1D4FD1", danger="#C4342B",
        border="#E3E6EA", border_w=1, radius=6, ctrl_h=30,
        gap=12, pad=14, fs=13, fw_title=600,
    ),
    dict(
        key="07", sel_bg="#003A6B", sel_fg="#FFFFFF", name="高对比·无障碍", ref="WCAG AAA / 强可视",
        note="纯黑底 + 高亮文字，视力不佳也看得清",
        bg="#000000", s1="#0B0B0B", s2="#161616", s3="#1F1F1F",
        text="#FFFFFF", text2="#E0E0E0", muted="#B0B0B0",
        accent="#4DA3FF", accent_h="#66B0FF", danger="#FF6B61",
        border="#4A4A4A", border_w=1, radius=4, ctrl_h=32,
        gap=14, pad=16, fs=14, fw_title=700,
    ),
    dict(
        key="08", sel_bg="#33285A", sel_fg="#F0E8FF", name="深紫·创意", ref="剪映 / 创意工具",
        note="紫调底有设计感，适合创作类产品",
        bg="#14101C", s1="#1C1726", s2="#231D31", s3="#2C243D",
        text="#F2EDFF", text2="#C9BFE0", muted="#9285AD",
        accent="#7C5FE0", accent_h="#9575F0", danger="#E5484D",
        border="#332A47", border_w=0, radius=10, ctrl_h=32,
        gap=14, pad=16, fs=13, fw_title=600,
    ),
    dict(
        key="09", sel_bg="#164E48", sel_fg="#D5FFF8", name="青灰·工业", ref="工业软件 / 刀塔风",
        note="青绿灰底，工具感强，不易审美疲劳",
        bg="#12171A", s1="#192024", s2="#202A2F", s3="#28353B",
        text="#E4EDF0", text2="#B2C0C6", muted="#7D8D95",
        accent="#0E7367", accent_h="#20BFA9", danger="#D9534F",
        border="#2E3B42", border_w=0, radius=4, ctrl_h=30,
        gap=12, pad=14, fs=13, fw_title=600,
    ),
    dict(
        key="10", sel_bg="#F0E4D4", sel_fg="#7A3E06", name="米白·纸感", ref="Bear / 纸质阅读器",
        note="暖白底，柔和护眼，偏人文气质",
        bg="#F5F2ED", s1="#FFFDFA", s2="#EDE8E0", s3="#E3DCD2",
        text="#2B2620", text2="#544B41", muted="#6B6156",
        accent="#B45309", accent_h="#9C4708", danger="#B03A2E",
        border="#DAD2C6", border_w=1, radius=6, ctrl_h=30,
        gap=12, pad=14, fs=13, fw_title=600,
    ),
]


def sheet_qss(t) -> str:
    # 浅色方案的主按钮文字要反色
    def is_light(hex_or_rgba: str) -> bool:
        h = hex_or_rgba.lstrip("#")
        if len(h) < 6:
            return False
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        return (0.2126 * r + 0.7152 * g + 0.0722 * b) > 150

    on_accent = "#0B0B0B" if is_light(t["accent"]) and t["key"] == "07" else "#FFFFFF"
    if t["key"] in ("06", "10"):
        on_accent = "#FFFFFF"

    bw = t["border_w"]
    border_css = f"{bw}px solid {t['border']}" if bw else "none"
    card_border = f"1px solid {t['border']}" if bw else "none"

    return f"""
    QWidget#sheet {{ background: {t['bg']}; }}
    QLabel {{ color: {t['text']}; font-family: "Microsoft YaHei UI","Microsoft YaHei",sans-serif;
              font-size: {t['fs']}px; }}
    QLabel#name {{ font-size: {t['fs'] + 4}px; font-weight: {t['fw_title']}; }}
    QLabel#ref  {{ color: {t['muted']}; font-size: {t['fs'] - 1}px; }}
    QLabel#note {{ color: {t['muted']}; font-size: {t['fs'] - 1}px; }}
    QLabel#sec  {{ font-size: {t['fs']}; font-weight: 600; color: {t['text2']}; }}
    QLabel#muted{{ color: {t['muted']}; font-size: {t['fs'] - 1}px; }}

    QWidget#card {{
        background: {t['s1']};
        border: {card_border};
        border-radius: {t['radius'] + 2}px;
    }}

    QPushButton {{
        font-family: "Microsoft YaHei UI","Microsoft YaHei",sans-serif;
        font-size: {t['fs']}px;
        min-height: {t['ctrl_h']}px; padding: 0 {t['pad']}px;
        border-radius: {t['radius']}px;
        border: {border_css};
        background: {t['s3']}; color: {t['text']};
    }}
    QPushButton#primary {{ background: {t['accent']}; color: {on_accent}; border: none; }}
    QPushButton#danger  {{ background: {t['danger']}; color: #FFFFFF; border: none; }}
    QPushButton#ghost   {{ background: transparent; border: none; color: {t['text2']}; }}

    QLineEdit {{
        font-family: "Microsoft YaHei UI","Microsoft YaHei",sans-serif;
        font-size: {t['fs']}px;
        min-height: {t['ctrl_h']}px; padding: 0 10px;
        background: {t['s3']}; color: {t['text']};
        border: {border_css}; border-radius: {t['radius']}px;
    }}
    QLineEdit#focus {{ border: 1px solid {t['accent']}; }}

    QListWidget {{
        background: transparent; border: none; outline: none;
        font-family: "Microsoft YaHei UI","Microsoft YaHei",sans-serif;
        font-size: {t['fs']}px; color: {t['text']};
    }}
    QListWidget::item {{ min-height: {t['ctrl_h'] - 2}px; padding-left: 10px;
                         border-radius: {max(2, t['radius'] - 2)}px; }}
    QListWidget::item:selected {{ background: {t.get('sel_bg', t['accent'])}; color: {t.get('sel_fg', on_accent)}; }}
    """


def build_sheet(t):
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
        QLineEdit, QListWidget, QFrame,
    )

    w = QWidget()
    w.setObjectName("sheet")
    lay = QVBoxLayout(w)
    lay.setContentsMargins(t["pad"], t["pad"] - 2, t["pad"], t["pad"] - 2)
    lay.setSpacing(t["gap"] - 2)

    # 头部
    head = QHBoxLayout()
    head.setSpacing(8)
    num = QLabel(t["key"])
    num.setObjectName("ref")
    head.addWidget(num)
    nm = QLabel(t["name"])
    nm.setObjectName("name")
    head.addWidget(nm)
    head.addStretch()
    rf = QLabel(t["ref"])
    rf.setObjectName("ref")
    head.addWidget(rf)
    lay.addLayout(head)

    note = QLabel(t["note"])
    note.setObjectName("note")
    lay.addWidget(note)

    # 卡片
    card = QWidget()
    card.setObjectName("card")
    cl = QVBoxLayout(card)
    cl.setContentsMargins(t["pad"], t["pad"] - 2, t["pad"], t["pad"] - 2)
    cl.setSpacing(t["gap"] - 4)

    sec = QLabel("图层属性")
    sec.setObjectName("sec")
    cl.addWidget(sec)

    e1 = QLineEdit("主标题文字")
    cl.addWidget(e1)

    e2 = QLineEdit("聚焦中")
    e2.setObjectName("focus")
    cl.addWidget(e2)

    lst = QListWidget()
    for s in ("主标题文字", "商品图 01", "促销标签"):
        lst.addItem(s)
    lst.setCurrentRow(0)
    lst.setFixedHeight((t["ctrl_h"] - 2) * 3 + 4)
    cl.addWidget(lst)

    lay.addWidget(card)

    # 按钮行
    row = QHBoxLayout()
    row.setSpacing(t["gap"] - 4)
    b1 = QPushButton("导出")
    b1.setObjectName("primary")
    b2 = QPushButton("取消")
    b3 = QPushButton("更多")
    b3.setObjectName("ghost")
    row.addWidget(b1)
    row.addWidget(b2)
    row.addWidget(b3)
    row.addStretch()
    lay.addLayout(row)

    lay.addStretch()
    return w


def main():
    from PySide6.QtWidgets import QApplication, QWidget, QGridLayout, QVBoxLayout
    from PySide6.QtGui import QFontDatabase, QPixmap
    from PySide6.QtCore import QCoreApplication

    app = QApplication.instance() or QApplication(sys.argv)
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(p)

    root = QWidget()
    root.setStyleSheet("#root{background:#000}")
    root.setObjectName("root")
    grid = QGridLayout(root)
    grid.setContentsMargins(0, 0, 0, 0)
    grid.setSpacing(2)

    CELL_W, CELL_H = 500, 372
    for i, t in enumerate(THEMES):
        wrap = QWidget()
        wl = QVBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        inner = build_sheet(t)
        wl.addWidget(inner)
        wrap.setStyleSheet(sheet_qss(t))
        wrap.setFixedSize(CELL_W, CELL_H)
        grid.addWidget(wrap, i // 2, i % 2)

    rows = (len(THEMES) + 1) // 2
    root.resize(CELL_W * 2 + 2, CELL_H * rows + 2 * (rows - 1))
    root.show()
    for _ in range(20):
        QCoreApplication.processEvents()

    pm = QPixmap(root.size())
    pm.fill()
    root.render(pm)
    ok = pm.save(str(OUT), "PNG")
    print(f"已生成: {OUT}  ok={ok}  {pm.width()}x{pm.height()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
