"""自动换行的流式布局（Qt 官方经典实现）。

═══════════════════════════════════════════════════════════════════════════
为什么单独成文件
═══════════════════════════════════════════════════════════════════════════

`FlowLayout` 原本放在 `app/ui/components/layout.py`（shadcn 组件库）里。
2026-10-28 决定弃用 shadcn 组件库，但 FlowLayout **不是视觉组件**——
它是解决真实布局缺陷的布局原语：

图层面板底部 8 个工具按钮，dock 可缩到 145px（实际 176px），一行需要 210px。
用 QHBoxLayout 时 Qt 不会换行，按钮互相重叠（实测 add_btn 右边界 24、
delete_btn 起点 22，压了 2px），最后一个按钮被切掉 4px。

所以把它从组件库里**择出来独立保留**，而不是跟着组件库一起删掉。

═══════════════════════════════════════════════════════════════════════════
用法
═══════════════════════════════════════════════════════════════════════════

    from app.ui.flow_layout import FlowLayout

    bar = QWidget()
    layout = FlowLayout(bar, margin=0, h_spacing=2, v_spacing=2)
    layout.addWidget(button)      # 放不下自动换行
"""

from PySide6.QtCore import QPoint, QRect, QSize, Qt
from PySide6.QtWidgets import QLayout


class FlowLayout(QLayout):
    """自动换行的流式布局。

    为什么需要：图层面板底部有 8 个工具按钮，但 dock 可缩到 145px（实际 176px），
    一行需要 210px。用 QHBoxLayout 时 Qt 不会换行，只会让按钮互相重叠
    （实测 add_btn 右边界 24、delete_btn 起点 22，压了 2px），最后一个按钮被切掉 4px。

    做法：按容器实际宽度逐行摆放，放不下就换行；`heightForWidth` 让父布局
    拿到正确的行数高度，避免按钮被纵向压扁。

    这是 Qt 官方文档的经典 FlowLayout 实现，额外支持每行末尾留白（不拉伸）。
    """

    def __init__(self, parent=None, margin=0, h_spacing=2, v_spacing=2):
        super().__init__(parent)
        self._items = []
        self._h_spacing = h_spacing
        self._v_spacing = v_spacing
        self.setContentsMargins(margin, margin, margin, margin)

    # --- QLayout 必须实现的接口 ---
    def addItem(self, item):
        self._items.append(item)

    def count(self):
        return len(self._items)

    def itemAt(self, index):
        if 0 <= index < len(self._items):
            return self._items[index]
        return None

    def takeAt(self, index):
        if 0 <= index < len(self._items):
            return self._items.pop(index)
        return None

    def expandingDirections(self):
        return Qt.Orientation(0)

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        return self._do_layout(QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect):
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self):
        return self.minimumSize()

    def minimumSize(self):
        size = QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        size += QSize(margins.left() + margins.right(), margins.top() + margins.bottom())
        return size

    # --- 内部实现 ---
    @staticmethod
    def _item_size(item):
        """取 item 的布局尺寸。

        为什么不能直接用 sizeHint()：全局 QSS 给 QPushButton 设了
        ``min-height: 28px`` 和 padding，style 计算出的 sizeHint 会大于
        代码里 ``setFixedSize(24, 24)`` 的实际尺寸 ——
        结果每个按钮占 38px 高，行间距凭空多出 16px，按钮栏看着松垮。
        这里优先用控件的真实尺寸（fixed size 已生效），退化时才用 sizeHint。
        """
        widget = item.widget()
        if widget is not None:
            # PySide6 没有 hasFixedWidth()（那是 Qt C++ 的 QWidget::hasFixedWidth 内部接口），
            # 用 min == max 判断是否被 setFixedSize 锁定。
            fixed = (
                widget.minimumWidth() == widget.maximumWidth()
                and widget.minimumHeight() == widget.maximumHeight()
            )
            if fixed:
                return widget.size()
        return item.sizeHint()

    def _do_layout(self, rect, test_only):
        margins = self.contentsMargins()
        effective = rect.adjusted(
            margins.left(), margins.top(), -margins.right(), -margins.bottom()
        )
        x, y = effective.x(), effective.y()
        line_height = 0

        for item in self._items:
            hint = self._item_size(item)
            next_x = x + hint.width() + self._h_spacing
            if next_x - self._h_spacing > effective.right() + 1 and line_height > 0:
                # 本行放不下 → 换行
                x = effective.x()
                y = y + line_height + self._v_spacing
                next_x = x + hint.width() + self._h_spacing
                line_height = 0

            if not test_only:
                item.setGeometry(QRect(QPoint(x, y), hint))
            x = next_x
            line_height = max(line_height, hint.height())

        return y + line_height - rect.y() + margins.bottom()
