from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QFrame, QSizePolicy, QFormLayout)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QRect, QEasingCurve, QTimer
from PySide6.QtGui import QFont
from app.ui.design_tokens import Tokens

class CollapsibleGroupBox(QFrame):
    """可折叠的分组控件"""

    def __init__(self, title="", collapsed=False, parent=None):
        super().__init__(parent)
        self.collapsed = collapsed
        self.content_widget = None
        self.animation = None

        self.setup_ui(title)

    def setup_ui(self, title):
        """设置UI"""
        self.setFrameStyle(QFrame.Box)
        self.setStyleSheet(f"""
            CollapsibleGroupBox {{
                border: 1px solid {Tokens.BORDER_PRIMARY};
                border-radius: {Tokens.CARD_RADIUS}px;
                margin-top: 3px;
                background-color: {Tokens.BG_SECONDARY};
            }}
            CollapsibleGroupBox[collapsed="true"] {{
                background-color: {Tokens.BG_SECONDARY};
            }}
        """)

        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 标题栏
        self.title_frame = QFrame()
        self.title_frame.setFixedHeight(Tokens.HEADER_HEIGHT)
        self.title_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {Tokens.BG_TERTIARY};
                border-top-left-radius: {Tokens.CARD_RADIUS}px;
                border-top-right-radius: {Tokens.CARD_RADIUS}px;
                border-bottom: 1px solid {Tokens.BORDER_SOFT};
            }}
            QFrame:hover {{
                background-color: {Tokens.BG_HOVER};
            }}
        """)

        self.title_layout = QHBoxLayout(self.title_frame)
        self.title_layout.setContentsMargins(*Tokens.HEADER_MARGINS)
        self.title_layout.setSpacing(Tokens.SEGMENT_GAP)

        # 标题文本
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color: {Tokens.TEXT_PRIMARY}; font-weight: {Tokens.FONT_WEIGHT_BOLD}; background: transparent;"
        )
        font = self.title_label.font()
        font.setPointSize(Tokens.FONT_SIZE_BASE)
        self.title_label.setFont(font)

        self.title_layout.addWidget(self.title_label)
        self.title_layout.addStretch()

        # 展开/收起按钮放在右侧，匹配参考图的折叠箭头位置
        self.toggle_button = QPushButton()
        self.toggle_button.setFixedSize(Tokens.COLLAPSE_BUTTON_SIZE, Tokens.COLLAPSE_BUTTON_SIZE)
        self.toggle_button.setFlat(True)
        self.toggle_button.clicked.connect(self.toggle_collapsed)
        self.title_layout.addWidget(self.toggle_button)
        self.update_toggle_button()

        # 使整个标题栏可点击
        self.title_frame.mousePressEvent = self.title_clicked

        self.main_layout.addWidget(self.title_frame)

        # 内容容器
        self.content_container = QFrame()
        self.content_container.setStyleSheet(f"""
            QFrame {{
                background-color: {Tokens.BG_SECONDARY};
                border: none;
                border-radius: 0px;
            }}
        """)

        self.container_layout = QVBoxLayout(self.content_container)
        self.container_layout.setContentsMargins(*Tokens.GROUP_CONTENT_MARGINS)
        self.container_layout.setSpacing(Tokens.ROW_GAP)

        self.main_layout.addWidget(self.content_container)

        # 设置初始状态
        if self.collapsed:
            self.content_container.setVisible(False)
            self.setProperty("collapsed", "true")
        else:
            self.setProperty("collapsed", "false")

        self.update_toggle_button()

        # 让标题栏上的文字标签、摘要等子控件鼠标事件穿透到标题栏本身，
        # 否则点击标题文字区域时 QLabel 会消费鼠标事件且不向父标题栏冒泡，
        # 导致只有最右侧箭头按钮能折叠/展开（用户点击标题栏主体无反应）。
        for child in self.title_frame.findChildren(QWidget):
            if child is not self.toggle_button:
                child.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def set_content_widget(self, widget):
        """设置内容控件"""
        if self.content_widget:
            self.container_layout.removeWidget(self.content_widget)

        self.content_widget = widget
        if widget:
            self.container_layout.addWidget(widget)

    def add_content_layout(self, layout):
        """添加内容布局"""
        self.container_layout.addLayout(layout)

    def title_clicked(self, event):
        """标题栏点击事件"""
        if event.button() == Qt.LeftButton:
            self.toggle_collapsed()

    def toggle_collapsed(self):
        """切换折叠状态"""
        self.collapsed = not self.collapsed

        if self.collapsed:
            self.content_container.setVisible(False)
            self.setProperty("collapsed", "true")
        else:
            self.content_container.setVisible(True)
            self.setProperty("collapsed", "false")

        self.update_toggle_button()
        self.style().unpolish(self)
        self.style().polish(self)

    def update_toggle_button(self):
        """更新展开/收起按钮"""
        if self.collapsed:
            self.toggle_button.setText("⌄")
            self.toggle_button.setToolTip("展开")
        else:
            self.toggle_button.setText("⌃")
            self.toggle_button.setToolTip("收起")

        self.toggle_button.setStyleSheet(f"""
            QPushButton {{
                background: transparent;
                border: none;
                color: {Tokens.TEXT_PRIMARY};
                /* 折叠组标题。原来写 `FONT_SIZE_BASE + 1` = 14px，
                   算术偏移出来的值不在档位上（等于绕过规范）。
                   语义上它就是区块标题，直接用 SIDEBAR_TITLE_FONT_SIZE(14)。 */
                font-size: {Tokens.SIDEBAR_TITLE_FONT_SIZE}px;
                font-weight: {Tokens.FONT_WEIGHT_BOLD};
                text-align: center;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {Tokens.ACCENT_HOVER};
                background-color: rgba(255, 255, 255, 0.07);
                border-radius: {Tokens.INDICATOR_RADIUS}px;
            }}
        """)

    def set_collapsed(self, collapsed):
        """设置折叠状态"""
        if self.collapsed != collapsed:
            self.toggle_collapsed()

    def is_collapsed(self):
        """获取折叠状态"""
        return self.collapsed
