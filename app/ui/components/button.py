"""
shadcn/ui 风格按钮组件。

所有视觉由全局 QSS（app.ui.theme.provider）按 variant / size 属性驱动，
本组件只负责设置语义属性，不在业务代码写死样式。

变体 variant：default(主色) / secondary / outline / ghost / destructive / link
尺寸 size   ：sm / default / lg / icon
"""
from PySide6.QtWidgets import QPushButton, QSizePolicy
from PySide6.QtCore import Qt

VARIANTS = ("default", "secondary", "outline", "ghost", "destructive", "link")
SIZES = ("sm", "default", "lg", "icon")


def button(text: str = "", variant: str = "default", size: str = "default",
           icon=None, tool_tip: str = None, parent=None) -> QPushButton:
    """创建 shadcn 风格按钮的便捷工厂函数。"""
    b = QPushButton(text, parent)
    b.setProperty("variant", variant if variant in VARIANTS else "default")
    b.setProperty("uiSize", size if size in SIZES else "default")
    b.setCursor(Qt.PointingHandCursor)
    if icon is not None:
        b.setIcon(icon)
    if tool_tip:
        b.setToolTip(tool_tip)
    if size == "icon":
        b.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
    return b


class Button(QPushButton):
    """shadcn/ui Button —— 用法与 button() 工厂一致，便于子类化。"""

    def __init__(self, text: str = "", variant: str = "default", size: str = "default",
                 icon=None, parent=None):
        super().__init__(text, parent)
        self.set_variant(variant)
        self.set_size(size)
        self.setCursor(Qt.PointingHandCursor)
        if icon is not None:
            self.setIcon(icon)

    def set_variant(self, variant: str) -> "Button":
        self.setProperty("variant", variant if variant in VARIANTS else "default")
        self.style().polish(self)
        return self

    def set_size(self, size: str) -> "Button":
        self.setProperty("uiSize", size if size in SIZES else "default")
        self.style().polish(self)
        return self
