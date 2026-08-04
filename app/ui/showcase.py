"""
组件库可视化画廊（Component Showcase）

集中展示 app/ui/components 下全部 shadcn/ui 风格组件，以及 Theme 令牌的实际取值，
用于设计评审、组件验收与开发参考。支持暗 / 亮主题实时切换。

用法：
    1) 独立预览（不启动主程序）：
        python app/ui/showcase.py
    2) 在程序内打开（可加菜单/快捷键）：
        from app.ui.showcase import open_showcase
        open_showcase(parent=main_window)
"""
from __future__ import annotations

import os
import sys

from PySide6.QtWidgets import (
    QMainWindow, QWidget, QApplication, QVBoxLayout, QHBoxLayout,
    QScrollArea, QLabel, QGridLayout, QSizePolicy,
)
from PySide6.QtCore import Qt

from app.ui.theme import Theme
from app.ui.theme.provider import get_palette
from app.ui.dark_theme import CursorDarkTheme
from app.ui.components import (
    Button, Card, CardHeader, CardTitle, CardDescription,
    CardContent, CardFooter, Input, Label, field, Tabs, Select,
    Checkbox, RadioButton, Slider, Switch, Badge, Alert, Separator, ProgressBar,
    IconLabel, Heading, H1, H2, H3, Text, Lead, Muted, Small, Code, Blockquote, Kbd,
)
from app.ui.components.button import VARIANTS, SIZES


def _icon(name: str):
    """安全获取图标，失败时返回 None（避免资源缺失导致画廊崩溃）。"""
    try:
        from app.ui.icon_manager import IconManager
        return IconManager.get_icon(name, 16, "secondary")
    except Exception:
        return None


class ComponentShowcase(QMainWindow):
    """组件画廊主窗口。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("批图王 · 组件库画廊 (shadcn/ui)")
        self.resize(1080, 760)
        self._build_ui()
        self._apply_theme()

    # ------------------------------------------------------------------ UI
    def _build_ui(self):
        root = QWidget()
        self.setCentralWidget(root)
        root_layout = QVBoxLayout(root)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # 顶部工具条
        toolbar = self._build_toolbar()
        root_layout.addWidget(toolbar)

        # 滚动内容
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(
            Theme.spacing("lg"), Theme.spacing("lg"),
            Theme.spacing("lg"), Theme.spacing("lg"))
        content_layout.setSpacing(Theme.spacing("xl"))

        content_layout.addWidget(self._intro())

        content_layout.addWidget(self._section_buttons())
        content_layout.addWidget(self._section_cards())
        content_layout.addWidget(self._section_inputs())
        content_layout.addWidget(self._section_controls())
        content_layout.addWidget(self._section_feedback())
        content_layout.addWidget(self._section_tabs())
        content_layout.addWidget(self._section_icons())
        content_layout.addWidget(self._section_typography())
        content_layout.addWidget(self._section_colors())

        content_layout.addStretch(1)
        scroll.setWidget(content)
        root_layout.addWidget(scroll, 1)

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        bar.setProperty("role", "section")
        h = QHBoxLayout(bar)
        h.setContentsMargins(
            Theme.spacing("lg"), Theme.spacing("md"),
            Theme.spacing("lg"), Theme.spacing("md"))
        title = Label("组件库 · Design System")
        title.setProperty("role", "card-title")
        h.addWidget(title)
        h.addStretch(1)

        self.theme_btn = Button("切换到亮色", variant="outline", size="sm")
        self.theme_btn.clicked.connect(self._toggle_theme)
        h.addWidget(self.theme_btn)
        return bar

    # ------------------------------------------------------------------ 区块
    def _intro(self) -> QWidget:
        card = Card()
        header = CardHeader()
        header.add_widget(CardTitle("shadcn/ui 风格组件库"))
        header.add_widget(CardDescription(
            "所有组件均经全局 QSS 与 Theme 令牌驱动，修改 tokens.py 即可全局换肤。"
            "上方按钮可实时切换暗 / 亮主题。"))
        card.add_widget(header)
        return card

    def _section(self, title: str, desc: str, body: QWidget) -> QWidget:
        card = Card()
        header = CardHeader()
        header.add_widget(CardTitle(title))
        if desc:
            header.add_widget(CardDescription(desc))
        card.add_widget(header)
        content = CardContent()
        content.add_widget(body)
        card.add_widget(content)
        return card

    def _section_buttons(self) -> QWidget:
        grid = QGridLayout()
        grid.setSpacing(Theme.spacing("md"))
        # 表头：尺寸
        grid.addWidget(Label("变体 \\ 尺寸", muted=True), 0, 0)
        for c, sz in enumerate(SIZES, start=1):
            grid.addWidget(Label(sz, muted=True), 0, c)
        # 每个变体一行
        for r, var in enumerate(VARIANTS, start=1):
            grid.addWidget(Label(var, muted=True), r, 0)
            for c, sz in enumerate(SIZES, start=1):
                grid.addWidget(Button(var, variant=var, size=sz), r, c)

        # 补充：禁用态 / 图标按钮 / 带图标
        extra = QHBoxLayout()
        extra.setSpacing(Theme.spacing("md"))
        disabled = Button("已禁用", variant="default")
        disabled.setEnabled(False)
        extra.addWidget(disabled)
        extra.addWidget(Button("图标", variant="secondary", size="icon", icon=_icon("settings")))
        extra.addWidget(Button("保存", variant="default", icon=_icon("plus")))
        extra.addWidget(Button("链接样式", variant="link"))
        extra.addStretch(1)

        wrap = QVBoxLayout()
        wrap.setSpacing(Theme.spacing("md"))
        wrap.addLayout(grid)
        wrap.addLayout(extra)
        body = QWidget()
        body.setLayout(wrap)
        return self._section("Buttons 按钮", "变体：default/secondary/outline/ghost/destructive/link；尺寸：sm/default/lg/icon。", body)

    def _section_cards(self) -> QWidget:
        card = Card()
        header = CardHeader()
        header.add_widget(CardTitle("卡片标题 CardTitle"))
        header.add_widget(CardDescription("这是一段卡片描述文字 CardDescription。"))
        card.add_widget(header)
        content = CardContent()
        content.add_widget(Label("卡片正文区域，可放置任意控件。", muted=True))
        content.add_widget(Input(placeholder="卡片内的输入示例"))
        card.add_widget(content)
        footer = CardFooter()
        footer.add_widget(Button("取消", variant="ghost", size="sm"))
        footer.add_widget(Button("确定", variant="default", size="sm"))
        card.add_widget(footer)
        body = QWidget()
        b = QHBoxLayout(body)
        b.setContentsMargins(0, 0, 0, 0)
        b.addWidget(card)
        b.addStretch(1)
        return self._section("Card 卡片", "结构：Card > CardHeader(CardTitle, CardDescription) + CardContent + CardFooter。", body)

    def _section_inputs(self) -> QWidget:
        form = QVBoxLayout()
        form.setSpacing(Theme.spacing("md"))

        row1 = field("文档名称", Input(placeholder="未命名文档"))
        row2 = field("导出格式", Select(items=["PNG", "JPG", "WEBP", "TIFF"]))
        row3 = field("分辨率", Input(placeholder="1920 × 1080"))

        disabled = Input(placeholder="禁用态")
        disabled.setEnabled(False)
        row4 = field("只读字段", disabled)

        form.addWidget(row1)
        form.addWidget(row2)
        form.addWidget(row3)
        form.addWidget(row4)
        body = QWidget()
        body.setLayout(form)
        return self._section("Inputs & Forms 输入与表单", "Input / Select / Label / field()，统一由全局 QSS 驱动。", body)

    def _section_controls(self) -> QWidget:
        left = QVBoxLayout()
        left.setSpacing(Theme.spacing("sm"))
        left.addWidget(Label("选择类", muted=True))
        left.addWidget(Checkbox("启用随机图"))
        left.addWidget(Checkbox("启用随机文案"))
        rb1, rb2 = RadioButton("填充"), RadioButton("适应")
        rb1.setChecked(True)
        left.addWidget(rb1)
        left.addWidget(rb2)

        right = QVBoxLayout()
        right.setSpacing(Theme.spacing("sm"))
        right.addWidget(Label("滑块 / 开关", muted=True))
        slider = Slider(Qt.Horizontal)
        slider.setRange(0, 100)
        slider.setValue(60)
        right.addWidget(slider)
        for label in ("描边", "圆角", "绑定"):
            h = QHBoxLayout()
            h.setSpacing(Theme.spacing("sm"))
            sw = Switch()
            sw.setChecked(True)
            h.addWidget(sw)
            h.addWidget(Label(label))
            h.addStretch(1)
            right.addLayout(h)

        body = QWidget()
        h = QHBoxLayout(body)
        h.setSpacing(Theme.spacing("xl"))
        h.addLayout(left)
        h.addLayout(right)
        h.addStretch(1)
        return self._section("Controls 基础控件", "Checkbox / RadioButton / Slider / Switch（全程序统一开关）。", body)

    def _section_feedback(self) -> QWidget:
        badges = QHBoxLayout()
        badges.setSpacing(Theme.spacing("sm"))
        for v in Badge.VARIANTS:
            badges.addWidget(Badge(v, variant=v))
        badges.addStretch(1)

        alerts = QVBoxLayout()
        alerts.setSpacing(Theme.spacing("sm"))
        for v, (t, d) in {
            "default": ("提示", "这是默认提示信息。"),
            "info": ("信息", "这是一条信息提示。"),
            "success": ("成功", "操作已成功完成。"),
            "warning": ("警告", "请注意潜在的问题。"),
            "destructive": ("错误", "操作失败，请重试。"),
        }.items():
            alerts.addWidget(Alert(t, d, variant=v))

        progress = QHBoxLayout()
        progress.setSpacing(Theme.spacing("md"))
        pbar = ProgressBar()
        pbar.set_progress(65)
        progress.addWidget(pbar)
        progress.addWidget(Label("65%", muted=True))
        progress.addStretch(1)

        body = QVBoxLayout()
        body.setSpacing(Theme.spacing("lg"))
        body.addLayout(badges)
        body.addWidget(Separator())
        body.addLayout(alerts)
        body.addWidget(Separator())
        body.addLayout(progress)
        wrap = QWidget()
        wrap.setLayout(body)
        return self._section("Feedback 反馈组件", "Badge / Alert / Separator / ProgressBar。", wrap)

    def _section_tabs(self) -> QWidget:
        tabs = Tabs()
        for name in ("基础", "高级", "批量"):
            page = QWidget()
            v = QVBoxLayout(page)
            v.setSpacing(Theme.spacing("md"))
            v.addWidget(Label(f"{name} 标签页内容", muted=True))
            v.addWidget(Input(placeholder=f"{name} 设置项"))
            v.addWidget(Button(f"应用{name}", variant="secondary", size="sm"))
            v.addStretch(1)
            tabs.add_tab(page, name)
        body = QWidget()
        b = QHBoxLayout(body)
        b.setContentsMargins(0, 0, 0, 0)
        b.addWidget(tabs)
        return self._section("Tabs 标签页", "基于 QTabWidget，外观由全局 QSS 驱动。", body)

    def _section_icons(self) -> QWidget:
        from app.ui.icon_manager import ICON_SVGS
        names = sorted(ICON_SVGS.keys())

        # 颜色变体示例
        color_row = QHBoxLayout()
        color_row.setSpacing(Theme.spacing("lg"))
        for token in ("foreground", "primary", "muted", "success", "destructive"):
            col = QVBoxLayout()
            col.setSpacing(4)
            col.setAlignment(Qt.AlignCenter)
            col.addWidget(IconLabel("settings", 22, token))
            col.addWidget(Small(token))
            color_row.addLayout(col)
        color_row.addStretch(1)

        # 全量图标网格
        grid = QGridLayout()
        grid.setSpacing(Theme.spacing("sm"))
        cols = 8
        for i, name in enumerate(names):
            r, c = divmod(i, cols)
            cell = QVBoxLayout()
            cell.setSpacing(2)
            cell.setAlignment(Qt.AlignCenter)
            cell.addWidget(IconLabel(name, 20, "foreground"))
            cell.addWidget(Small(name))
            grid.addLayout(cell, r, c)

        grid_wrap = QWidget()
        grid_wrap.setLayout(grid)

        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(0, 0, 0, 0)
        b.setSpacing(Theme.spacing("md"))
        b.addLayout(color_row)
        b.addWidget(Separator())
        b.addWidget(grid_wrap)
        return self._section(
            "Icons 图标",
            "基于 lucide 风格内嵌 SVG，颜色取自主题令牌，主题切换自动重绘；封装于 app.ui.components.icon。",
            body)

    def _section_typography(self) -> QWidget:
        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(0, 0, 0, 0)
        b.setSpacing(Theme.spacing("sm"))

        b.addWidget(H1("一级标题 Heading 1"))
        b.addWidget(H2("二级标题 Heading 2"))
        b.addWidget(H3("三级标题 Heading 3"))
        b.addWidget(Lead("引导段落 Lead：用于页面或区块开头，字号更大、颜色更弱，引导用户阅读。"))
        b.addWidget(Text("正文 Text：常规阅读文本，使用前景色与基础字号，支持长段落自动换行，行高舒适。"))
        b.addWidget(Muted("次要文本 Muted：用于辅助说明、注释、字段备注等弱信息。"))
        b.addWidget(Small("小字 Small：用于极小的辅助信息，如脚注、版本号。"))
        b.addWidget(Code("pip install -r requirements.txt"))

        bq = Blockquote("引用 Blockquote：用于引用他人观点或文档摘录，左侧强调线，颜色更弱。")
        b.addWidget(bq)

        kbd_row = QHBoxLayout()
        kbd_row.setSpacing(Theme.spacing("sm"))
        kbd_row.addWidget(Label("快捷键示例：", muted=True))
        kbd_row.addWidget(Kbd("Ctrl"))
        kbd_row.addWidget(Kbd("Shift"))
        kbd_row.addWidget(Kbd("S"))
        kbd_row.addStretch(1)
        b.addLayout(kbd_row)

        return self._section(
            "Typography 排版",
            "Heading(H1/H2/H3) / Text / Lead / Muted / Small / Code / Blockquote / Kbd，全部由全局 QSS 的 role 驱动。",
            body)

    def _section_colors(self) -> QWidget:
        # 语义令牌色板
        token_names = [
            "background", "foreground", "card", "popover", "primary",
            "secondary", "muted", "accent", "destructive", "border", "input", "ring",
        ]
        grid = QGridLayout()
        grid.setSpacing(Theme.spacing("sm"))
        cols = 4
        for i, name in enumerate(token_names):
            r, c = divmod(i, cols)
            grid.addWidget(self._swatch(Theme.color(name), name), r, c)

        # 图表配色（8 色）
        chart_row = QHBoxLayout()
        chart_row.setSpacing(Theme.spacing("sm"))
        for i in range(8):
            chart_row.addWidget(self._swatch(Theme.chart_color(i), f"chart {i}"))
        chart_row.addStretch(1)

        body = QVBoxLayout()
        body.setSpacing(Theme.spacing("md"))
        body.addWidget(Label("语义令牌 Semantic Tokens", muted=True))
        body.addLayout(grid)
        body.addWidget(Separator())
        body.addWidget(Label("图表配色 Chart Colors", muted=True))
        body.addLayout(chart_row)
        wrap = QWidget()
        wrap.setLayout(body)
        return self._section("Colors 令牌色板", "实时反映当前主题下的 Theme 取值；切换主题后此处同步刷新。", wrap)

    def _swatch(self, color: str, name: str) -> QWidget:
        box = QVBoxLayout()
        box.setSpacing(4)
        chip = QLabel()
        chip.setFixedSize(64, 40)
        chip.setStyleSheet(
            f"background:{color}; border-radius:6px; "
            f"border:1px solid {Theme.color('border')};")
        box.addWidget(chip, alignment=Qt.AlignHCenter)
        name_lbl = Label(name, muted=True)
        name_lbl.setAlignment(Qt.AlignHCenter)
        box.addWidget(name_lbl, alignment=Qt.AlignHCenter)
        val = Label(color, muted=True)
        val.setAlignment(Qt.AlignHCenter)
        box.addWidget(val, alignment=Qt.AlignHCenter)
        w = QWidget()
        w.setLayout(box)
        return w

    # ------------------------------------------------------------------ 主题
    def _toggle_theme(self):
        Theme.toggle_mode()
        self._apply_theme()
        self.theme_btn.setText("切换到暗色" if Theme.mode() == "light" else "切换到亮色")

    def _apply_theme(self):
        app = QApplication.instance()
        if app is None:
            return
        app.setStyleSheet(CursorDarkTheme.get_complete_style())
        app.setPalette(get_palette())
        # 强制刷新所有控件以反映新配色
        for w in app.allWidgets():
            w.style().polish(w)


def open_showcase(parent=None) -> ComponentShowcase:
    """在程序内打开组件画廊（返回窗口实例，调用方负责保活引用）。"""
    w = ComponentShowcase(parent)
    w.show()
    w.raise_()
    w.activateWindow()
    return w


if __name__ == "__main__":
    # 独立运行：把项目根加入 sys.path，使 `app.*` 包可导入
    ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)

    app = QApplication(sys.argv)
    from PySide6.QtGui import QFont
    app.setFont(QFont(Theme.font("family")))
    win = ComponentShowcase()
    win.show()
    win.raise_()
    win.activateWindow()
    sys.exit(app.exec())
