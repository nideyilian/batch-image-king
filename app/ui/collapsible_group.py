from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QFrame, QSizePolicy, QFormLayout)
from PySide6.QtCore import Qt, Signal, QPropertyAnimation, QRect, QEasingCurve, QTimer
from PySide6.QtGui import QFont
from app.ui.dark_theme import CursorDarkTheme

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
                border: 1px solid #3A3A3D;
                border-radius: 6px;
                margin-top: 3px;
                background-color: #202123;
            }}
            CollapsibleGroupBox[collapsed="true"] {{
                background-color: #202123;
            }}
        """)

        # 主布局
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(0, 0, 0, 0)
        self.main_layout.setSpacing(0)

        # 标题栏
        self.title_frame = QFrame()
        self.title_frame.setFixedHeight(32)
        self.title_frame.setStyleSheet(f"""
            QFrame {{
                background-color: #2A2A2C;
                border-top-left-radius: 6px;
                border-top-right-radius: 6px;
                border-bottom: 1px solid #34363A;
            }}
            QFrame:hover {{
                background-color: #303034;
            }}
        """)

        title_layout = QHBoxLayout(self.title_frame)
        title_layout.setContentsMargins(8, 4, 7, 4)
        title_layout.setSpacing(4)

        # 标题文本
        self.title_label = QLabel(title)
        self.title_label.setStyleSheet(
            f"color: {CursorDarkTheme.TEXT_PRIMARY}; font-weight: 700; background: transparent;"
        )
        font = self.title_label.font()
        font.setPointSize(10)
        self.title_label.setFont(font)

        title_layout.addWidget(self.title_label)
        title_layout.addStretch()

        # 展开/收起按钮放在右侧，匹配参考图的折叠箭头位置
        self.toggle_button = QPushButton()
        self.toggle_button.setFixedSize(18, 18)
        self.toggle_button.setFlat(True)
        self.toggle_button.clicked.connect(self.toggle_collapsed)
        title_layout.addWidget(self.toggle_button)
        self.update_toggle_button()

        # 使整个标题栏可点击
        self.title_frame.mousePressEvent = self.title_clicked

        self.main_layout.addWidget(self.title_frame)

        # 内容容器
        self.content_container = QFrame()
        self.content_container.setStyleSheet(f"""
            QFrame {{
                background-color: #202123;
                border: none;
                border-radius: 0px;
            }}
        """)

        self.container_layout = QVBoxLayout(self.content_container)
        self.container_layout.setContentsMargins(8, 8, 8, 9)
        self.container_layout.setSpacing(6)

        self.main_layout.addWidget(self.content_container)

        # 设置初始状态
        if self.collapsed:
            self.content_container.setVisible(False)
            self.setProperty("collapsed", "true")
        else:
            self.setProperty("collapsed", "false")

        self.update_toggle_button()

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
                color: {CursorDarkTheme.TEXT_PRIMARY};
                font-size: 14px;
                font-weight: 700;
                text-align: center;
                padding: 0px;
            }}
            QPushButton:hover {{
                color: {CursorDarkTheme.ACCENT_HOVER};
                background-color: rgba(255, 255, 255, 0.07);
                border-radius: 4px;
            }}
        """)

    def set_collapsed(self, collapsed):
        """设置折叠状态"""
        if self.collapsed != collapsed:
            self.toggle_collapsed()

    def is_collapsed(self):
        """获取折叠状态"""
        return self.collapsed
