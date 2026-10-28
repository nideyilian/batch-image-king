"""组件规范总览图：把令牌 + 组件状态渲染成一张可评审的样张。

对照三列：
  A. 改造前（旧令牌 + 旧写法：重边框、紧间距）
  B. 仅换令牌（证明：只改颜色提升有限）
  C. 令牌 + 间距节奏 + 边框克制（真正的改造方式）
"""
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

OUT = ROOT / "docs" / "design-preview.png"


def style_for(tokens, mode: str) -> str:
    """mode: before | token_only | full"""
    if mode == "before":
        bg, s1, s2, s3 = "#181818", "#1F1F1F", "#242526", "#2F2F2F"
        text, text2, muted = "#F4F4F5", "#C7C7C9", "#8E8E93"
        accent, danger = "#2F9CF4", "#FF453A"
        border = "#303033"
        family = '"Segoe UI", "Microsoft YaHei", sans-serif'
        fs, h, r = 12, 30, 4
        border_w = 1
        pad = 12
        gap = 6
    else:
        bg, s1, s2, s3 = (tokens.Color.surface_base, tokens.Color.surface_1,
                          tokens.Color.surface_2, tokens.Color.surface_3)
        text, text2 = tokens.Color.text_primary, tokens.Color.text_secondary
        muted = tokens.Color.text_muted
        accent, danger = tokens.Color.accent, tokens.Color.danger
        border = tokens.Color.border_default
        family = tokens.Typography.family
        fs, r = tokens.Typography.size_base, tokens.Radius.md
        if mode == "token_only":
            h, border_w, pad, gap = 30, 1, 12, 6
        else:
            h, border_w, pad, gap = tokens.Size.control_h, 0, 16, 12

    return f"""
    QWidget#page {{ background: {bg}; }}
    QLabel {{ color: {text}; font-family: {family}; font-size: {fs}px; }}
    QLabel#title {{ font-size: {fs + 7}px; font-weight: 600; }}
    QLabel#section {{ font-size: {fs + 1}px; font-weight: 600; }}
    QLabel#muted {{ color: {muted}; font-size: {fs - 1}px; }}
    QLabel#cap {{ color: {muted}; font-size: 11px; }}

    QWidget#card {{
        background: {s1};
        border: {border_w}px solid {border};
        border-radius: {r + 2}px;
    }}
    QWidget#cardFlat {{
        background: {s1};
        border: none;
        border-radius: {r + 2}px;
    }}

    QPushButton {{
        font-family: {family}; font-size: {fs}px;
        min-height: {h}px; padding: 0 {pad}px;
        border-radius: {r}px; border: 1px solid {border};
        background: {s3}; color: {text};
    }}
    QPushButton#primary {{ background: {accent}; color: #FFFFFF; border: none; }}
    QPushButton#danger {{ background: {danger}; color: #FFFFFF; border: none; }}
    QPushButton#ghost {{ background: transparent; border: none; color: {text2}; }}
    QPushButton:disabled {{ background: {s2}; color: {muted}; }}

    QLineEdit {{
        font-family: {family}; font-size: {fs}px;
        min-height: {h}px; padding: 0 10px;
        background: {s3}; color: {text};
        border: 1px solid {border}; border-radius: {r}px;
    }}
    QLineEdit#focus {{ border: 1px solid {accent}; }}

    QListWidget {{
        background: transparent; border: none;
        font-family: {family}; font-size: {fs}px; color: {text};
        outline: none;
    }}
    QListWidget::item {{ min-height: {h}px; padding-left: 10px; border-radius: {r}px; }}
    QListWidget::item:selected {{ background: {accent}; color: #FFFFFF; }}

    QCheckBox {{ color: {text}; font-family: {family}; font-size: {fs}px; spacing: 6px; }}
    QCheckBox::indicator {{
        width: {h - 14}px; height: {h - 14}px;
        border: 1px solid {border}; border-radius: 4px; background: {s3};
    }}
    QCheckBox::indicator:checked {{ background: {accent}; border: 1px solid {accent}; }}
    QFrame#hline {{ background: {border}; max-height: 1px; border: none; }}
    """


def build_column(tokens, mode: str, title: str, subtitle: str):
    from PySide6.QtWidgets import (
        QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
        QListWidget, QCheckBox, QFrame,
    )

    if mode == "before":
        s1, s3, muted = "#1F1F1F", "#2F2F2F", "#8E8E93"
        card_name, pad, gap = "card", 12, 6
    else:
        s1 = tokens.Color.surface_1
        s3 = tokens.Color.surface_3
        muted = tokens.Color.text_muted
        pad = 16 if mode == "full" else 12
        gap = 12 if mode == "full" else 6
        card_name = "cardFlat" if mode == "full" else "card"

    col = QWidget()
    col.setObjectName("page")
    lay = QVBoxLayout(col)
    lay.setContentsMargins(18, 18, 18, 18)
    lay.setSpacing(10)

    t = QLabel(title)
    t.setObjectName("title")
    lay.addWidget(t)
    s = QLabel(subtitle)
    s.setObjectName("cap")
    lay.addWidget(s)
    lay.addSpacing(4)

    # --- 按钮组 ---
    sec = QLabel("按钮")
    sec.setObjectName("section")
    lay.addWidget(sec)

    row = QHBoxLayout()
    row.setSpacing(gap)
    for text, obj in (("主要", "primary"), ("次要", ""), ("更多", "ghost")):
        b = QPushButton(text)
        if obj:
            b.setObjectName(obj)
        row.addWidget(b)
    row.addStretch()
    lay.addLayout(row)

    row2 = QHBoxLayout()
    row2.setSpacing(gap)
    d = QPushButton("删除")
    d.setObjectName("danger")
    row2.addWidget(d)
    dis = QPushButton("禁用")
    dis.setEnabled(False)
    row2.addWidget(dis)
    row2.addStretch()
    lay.addLayout(row2)

    # --- 输入 ---
    sec2 = QLabel("输入")
    sec2.setObjectName("section")
    lay.addWidget(sec2)

    e1 = QLineEdit("主标题文字")
    lay.addWidget(e1)
    e2 = QLineEdit("聚焦态")
    e2.setObjectName("focus")
    lay.addWidget(e2)

    # --- 面板 ---
    card = QWidget()
    card.setObjectName(card_name)
    cl = QVBoxLayout(card)
    cl.setContentsMargins(pad, pad, pad, pad)
    cl.setSpacing(gap)

    h = QLabel("图层属性")
    h.setObjectName("section")
    cl.addWidget(h)

    lst = QListWidget()
    for name in ("主标题文字", "商品图_01", "促销标签"):
        lst.addItem(name)
    lst.setCurrentRow(0)
    lst.setFixedHeight(112)
    cl.addWidget(lst)

    line = QFrame()
    line.setObjectName("hline")
    if mode != "full":
        line.setVisible(False)
    cl.addWidget(line)

    cb = QCheckBox("保持素材不重复")
    cb.setChecked(True)
    cl.addWidget(cb)

    hint = QLabel("目录内 128 张图片")
    hint.setObjectName("muted")
    cl.addWidget(hint)

    lay.addWidget(card)
    lay.addStretch()
    return col


def main():
    from PySide6.QtWidgets import QApplication, QWidget, QHBoxLayout
    from PySide6.QtGui import QFontDatabase, QPixmap
    from PySide6.QtCore import QCoreApplication

    app = QApplication.instance() or QApplication(sys.argv)
    for p in (r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"):
        QFontDatabase.addApplicationFont(p)

    import app.ui.tokens_v2 as tokens

    specs = [
        ("before", "A · 改造前", "旧令牌 · 重边框 · 紧间距"),
        ("token_only", "B · 仅换令牌", "颜色达标，但观感提升有限"),
        ("full", "C · 完整改造", "令牌 + 间距节奏 + 去边框"),
    ]

    root = QWidget()
    root.resize(1020, 700)
    outer = QHBoxLayout(root)
    outer.setContentsMargins(0, 0, 0, 0)
    outer.setSpacing(0)

    for mode, title, sub in specs:
        wrap = QWidget()
        wl = QHBoxLayout(wrap)
        wl.setContentsMargins(0, 0, 0, 0)
        wl.addWidget(build_column(tokens, mode, title, sub))
        wrap.setStyleSheet(style_for(tokens, mode))
        outer.addWidget(wrap)

    root.show()
    for _ in range(15):
        QCoreApplication.processEvents()

    pm = QPixmap(root.size())
    pm.fill()
    root.render(pm)
    ok = pm.save(str(OUT), "PNG")
    print(f"已生成: {OUT}  ok={ok}  {pm.width()}x{pm.height()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
