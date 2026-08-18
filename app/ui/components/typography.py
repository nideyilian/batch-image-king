"""shadcn/ui 风格排版组件（Typography）。

以 ``QLabel`` 为基类，全部通过全局 QSS 的 ``role`` / ``level`` 属性选择器驱动，
字号、字重、颜色严格对齐 ``app/ui/theme/tokens.py`` 的字体令牌。

组件清单：
- ``Heading``  / ``H1`` ``H2`` ``H3``  标题（1/2/3 级）
- ``Text``                        正文
- ``Lead``                        引导段落（区块开头）
- ``Muted``                      次要文本
- ``Small``                      小字（脚注级）
- ``Code``                       内联代码
- ``Blockquote``                 引用
- ``Kbd``                        键盘按键

全部组件均自动换行，主题切换时由全局 QSS 即时换肤。
"""
from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

from app.ui.theme import Theme


def _polish(w):
    try:
        w.style().unpolish(w)
        w.style().polish(w)
    except Exception:
        pass


class Heading(QLabel):
    """标题：level=1/2/3 对应 h1/h2/h3。"""
    LEVELS = (1, 2, 3)

    def __init__(self, text: str = "", level: int = 1, parent=None):
        super().__init__(text, parent)
        self.setObjectName("Heading")
        self.setProperty("role", "heading")
        self.set_level(level)
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def set_level(self, level: int):
        self.setProperty("level", str(level if level in self.LEVELS else 1))
        _polish(self)


class H1(Heading):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, 1, parent)


class H2(Heading):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, 2, parent)


class H3(Heading):
    def __init__(self, text: str = "", parent=None):
        super().__init__(text, 3, parent)


class Text(QLabel):
    """正文：前景色 + 基础字号，支持长段落自动换行。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Text")
        self.setProperty("role", "text")
        self.setWordWrap(True)
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)


class Lead(QLabel):
    """引导段落：区块或页面开头，字号更大、颜色更弱。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Lead")
        self.setProperty("role", "lead")
        self.setWordWrap(True)


class Muted(QLabel):
    """次要文本：辅助说明、注释、字段备注。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Muted")
        self.setProperty("role", "muted")
        self.setWordWrap(True)


class Small(QLabel):
    """小字：极小的辅助信息，如脚注。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Small")
        self.setProperty("role", "small")
        self.setWordWrap(True)


class Code(QLabel):
    """内联代码：等宽字体 + 浅色背景胶囊。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Code")
        self.setProperty("role", "code")
        self.setTextInteractionFlags(Qt.TextSelectableByMouse)

    def set_text(self, text: str):
        self.setText(text)


class Blockquote(QLabel):
    """引用：左侧强调线，颜色更弱，用于摘录他人观点或文档。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Blockquote")
        self.setProperty("role", "blockquote")
        self.setWordWrap(True)


class Kbd(QLabel):
    """键盘按键：小号等宽胶囊，用于展示快捷键。"""

    def __init__(self, text: str = "", parent=None):
        super().__init__(text, parent)
        self.setObjectName("Kbd")
        self.setProperty("role", "kbd")
