"""shadcn/ui 风格图标组件。

封装 ``app.ui.icon_manager.IconManager``（基于 lucide 风格内嵌 SVG），
提供主题色图标组件 ``IconLabel``，颜色随 ``Theme.mode`` 自动取令牌值，
主题切换时自动重新渲染。

依赖：``app.ui.icon_manager``（已内置约 40 个常用图标）。
"""
import weakref

from PySide6.QtWidgets import QLabel
from PySide6.QtCore import Qt

from app.ui.theme import Theme

# 图标可使用的语义令牌（颜色来源）
ICON_COLORS = (
    "foreground", "muted", "primary", "secondary",
    "destructive", "success", "card-foreground", "warning",
)


def _icon_color(token: str) -> str:
    """把语义令牌转换为 Hex 颜色，IconManager 接受十六进制字符串。"""
    try:
        return Theme.color(token, Theme.color("foreground"))
    except Exception:
        return Theme.color("foreground")


class IconLabel(QLabel):
    """主题色 SVG 图标标签，尺寸与颜色可配，主题切换自动刷新。

    示例::

        IconLabel("settings", 18, "primary")
        IconLabel("save", 16)                       # 默认 foreground
        lbl.set_icon("trash", 20, "destructive")    # 运行时更换
    """

    def __init__(self, name: str = "", size: int = 16,
                 color: str = "foreground", parent=None):
        super().__init__(parent)
        self._name = name
        self._size = size
        self._color = color if color in ICON_COLORS else "foreground"
        self.setObjectName("IconLabel")
        self.setAlignment(Qt.AlignCenter)
        self.set_property_role()
        self._render()

        # 主题切换时自动重绘（弱引用，避免回调泄漏）
        def _cb(weak):
            def _on_change(_mode=None):
                w = weak()
                if w is not None:
                    w._render()
            return _on_change
        Theme.on_change(_cb(weakref.ref(self)))

    def set_property_role(self):
        self.setProperty("role", "icon")

    # ---- 公共 API ----
    def set_icon(self, name: str, size: int = None, color: str = None):
        self._name = name
        if size is not None:
            self._size = size
        if color is not None:
            self._color = color if color in ICON_COLORS else "foreground"
        self._render()

    name = property(lambda self: self._name)
    size = property(lambda self: self._size)
    color_token = property(lambda self: self._color)

    # ---- 内部渲染 ----
    def _render(self):
        if not self._name:
            self.clear()
            return
        from app.ui.icon_manager import IconManager
        icon = IconManager.get_icon(self._name, self._size, _icon_color(self._color))
        pm = icon.pixmap(self._size, self._size) if not icon.isNull() else None
        if pm is not None and not pm.isNull():
            self.setPixmap(pm)
            self.setFixedSize(self._size, self._size)
        else:
            # 取不到图标时回退为名称首字符，保证布局不塌陷
            self.setText(self._name[:1])
            self.setFixedSize(self._size, self._size)


# 别名与便捷工厂
Icon = IconLabel


def icon(name: str, size: int = 16, color: str = "foreground") -> IconLabel:
    """便捷工厂：``icon("save", 18, "primary")``。"""
    return IconLabel(name, size, color)
