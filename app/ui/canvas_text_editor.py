# -*- coding: utf-8 -*-
"""画布就地文字编辑器（Photoshop 风格）。

双击画布上的文字图层后，在该图层矩形位置打开一个 QTextEdit 直接编辑：
- 点击画布其他位置（失焦）提交编辑并关闭；
- Esc 取消编辑（恢复原文字）；
- 绑定模式下 Enter 提交、Shift+Enter 换行；非绑定模式 Enter 直接换行；
- Ctrl+滚轮（+Shift 步进 5）调整选中文字的独立字号（混合字号）。
"""
from PySide6.QtWidgets import QTextEdit
from PySide6.QtGui import QTextCharFormat, QTextCursor, QTextOption, QFont, QColor, QPainter
from PySide6.QtCore import Qt, QTimer, Signal, QPoint
from app.ui.tokens_v2 import Color
from app.constants import DEFAULT_TEXT_FONT_FAMILY


class CanvasTextEditor(QTextEdit):
    """覆盖在文字图层上的就地编辑器。"""

    def __init__(self, canvas, layer, layer_rect, zoom_factor, click_pos=None):
        super().__init__(canvas)
        self._canvas = canvas
        self._layer = layer
        self._zoom = max(0.1, float(zoom_factor))
        self._binding_enabled = bool(getattr(layer, "text_binding_enabled", True))
        self._prev_auto_fit = bool(getattr(layer, "auto_fit_text_box", True))
        self._original_text_lines = list(layer.get_text_lines()) if hasattr(layer, "get_text_lines") else []
        self._original_current_text = str(getattr(layer, "current_text", "") or "")
        self._original_text_color_ranges = (
            layer.get_text_color_ranges() if hasattr(layer, "get_text_color_ranges") else []
        )
        self._original_font_size_ranges = (
            layer.get_font_size_ranges() if hasattr(layer, "get_font_size_ranges") else []
        )
        self._committed = False
        self._closed = False

        # 编辑期间固定文本框尺寸，避免打字时图层尺寸抖动
        try:
            layer.auto_fit_text_box = False
        except Exception:
            pass

        self.setFrameShape(QTextEdit.NoFrame)
        # 画布内直接编辑文字的浮层：半透明底让下层图像可见，
        # 虚线框表示「这是一个临时编辑区」。颜色走令牌，与主题保持一致。
        self.setStyleSheet(
            f"QTextEdit {{"
            f"  background-color: {Color.surface_2};"
            f"  color: {Color.text_primary};"
            f"  border: 1px dashed {Color.border_focus};"
            f"  padding: 2px;"
            f"}}"
        )
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setWordWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
        self.setCursorWidth(max(1, int(2 * self._zoom)))

        family = str(getattr(layer, "font_family", "") or DEFAULT_TEXT_FONT_FAMILY)
        resolver = getattr(layer, "_resolve_font_family", None)
        if callable(resolver):
            family = str(resolver(family) or family)
        base_font = QFont(family)
        base_size = max(1, int(round(int(getattr(layer, "font_size", 24)) * self._zoom)))
        base_font.setPixelSize(base_size)
        self.setFont(base_font)

        self.setPlainText(str(getattr(layer, "current_text", "") or ""))
        self._apply_size_ranges_to_editor()

        if click_pos is not None:
            local = QPoint(
                click_pos.x() - layer_rect.x(),
                click_pos.y() - layer_rect.y(),
            )
            try:
                cursor = self.cursorForPosition(local)
                self.setTextCursor(cursor)
            except Exception:
                pass

        self._sync_timer = QTimer(self)
        self._sync_timer.setSingleShot(True)
        self._sync_timer.setInterval(200)
        self._sync_timer.timeout.connect(self._live_sync)

        self.textChanged.connect(self._on_text_changed)
        self.setAttribute(Qt.WA_DeleteOnClose)

    # ------------------------------------------------------------------
    # 对外接口
    # ------------------------------------------------------------------

    def update_geometry(self, layer_rect=None, zoom_factor=None):
        """画布缩放/平移后同步编辑器位置、尺寸与字号。"""
        if layer_rect is None:
            return
        if zoom_factor is not None:
            self._zoom = max(0.1, float(zoom_factor))
            base_font = QFont(self.font())
            base_size = max(
                1, int(round(int(getattr(self._layer, "font_size", 24)) * self._zoom))
            )
            base_font.setPixelSize(base_size)
            self.setFont(base_font)
            self.setCursorWidth(max(1, int(2 * self._zoom)))
            self._apply_size_ranges_to_editor()
        self.move(layer_rect.x(), layer_rect.y())
        self.resize(max(20, layer_rect.width()), max(20, layer_rect.height()))

    def is_closed(self):
        return self._closed

    # ------------------------------------------------------------------
    # 内部逻辑
    # ------------------------------------------------------------------

    def _on_text_changed(self):
        if self._committed or self._closed:
            return
        if not self._sync_timer.isActive():
            self._sync_timer.start()

    def _live_sync(self):
        """防抖地把编辑器文本实时同步到图层（画布预览跟随）。"""
        if self._committed or self._closed or self._layer is None:
            return
        text = self.toPlainText()
        try:
            if text != getattr(self._layer, "current_text", None):
                self._layer.current_text = text
        except Exception:
            pass

    def _apply_size_ranges_to_editor(self):
        """把图层已有的混合字号区间同步到编辑器字符格式。"""
        layer = self._layer
        if layer is None or not hasattr(layer, "get_font_size_ranges"):
            return
        try:
            ranges = layer.get_font_size_ranges()
        except Exception:
            return
        if not ranges:
            return
        cursor = self.textCursor()
        cursor.setPosition(0)
        for item in ranges:
            start = max(0, int(item["start"]))
            end = min(len(self.toPlainText()), int(item["end"]))
            if end <= start:
                continue
            fmt = QTextCharFormat()
            font = QFont(self.font())
            font.setPixelSize(max(1, int(round(int(item["size"]) * self._zoom))))
            fmt.setFont(font)
            cursor.setPosition(start)
            cursor.setPosition(end, QTextCursor.MoveMode.KeepAnchor)
            cursor.mergeCharFormat(fmt)
        cursor.clearSelection()
        cursor.setPosition(0)
        self.setTextCursor(cursor)

    def _adjust_selected_font_size(self, delta):
        """调整选中文字的独立字号（混合字号）。"""
        layer = self._layer
        if layer is None or not hasattr(layer, "set_font_size_range"):
            return
        cursor = self.textCursor()
        if not cursor.hasSelection():
            return
        start = min(cursor.position(), cursor.anchor())
        end = max(cursor.position(), cursor.anchor())
        try:
            current_size = layer.font_size_for_text_index(start)
        except Exception:
            current_size = int(getattr(layer, "font_size", 24))
        new_size = max(6, min(240, current_size + delta))
        if new_size == current_size:
            return
        try:
            layer.set_font_size_range(start, end, new_size)
        except Exception:
            return
        fmt = QTextCharFormat()
        font = QFont(self.font())
        font.setPixelSize(max(1, int(round(new_size * self._zoom))))
        fmt.setFont(font)
        cursor.mergeCharFormat(fmt)
        self.setTextCursor(cursor)
        self._canvas.document.document_changed.emit()

    def _commit(self):
        """提交编辑并关闭编辑器。"""
        if self._committed or self._closed:
            return
        self._committed = True
        if self._sync_timer.isActive():
            self._sync_timer.stop()

        layer = self._layer
        text = self.toPlainText()
        if layer is not None:
            try:
                lines = layer.parse_text_input_to_lines(text) if hasattr(layer, "parse_text_input_to_lines") else [text]
                current_text = lines[0] if lines else ""
                if text != self._original_current_text and hasattr(layer, "replace_text_style_ranges"):
                    from app.utils.text_style_ranges import remap_text_style_ranges
                    colors, sizes = remap_text_style_ranges(
                        self._original_current_text,
                        current_text,
                        self._original_text_color_ranges,
                        self._original_font_size_ranges,
                    )
                else:
                    colors = layer.get_text_color_ranges() if hasattr(layer, "get_text_color_ranges") else []
                    sizes = layer.get_font_size_ranges() if hasattr(layer, "get_font_size_ranges") else []
                layer.set_text_lines(lines)
                layer.set_current_text(current_text, force=True)
                if hasattr(layer, "replace_text_style_ranges"):
                    layer.replace_text_style_ranges(colors, sizes)
                if hasattr(layer, "auto_fit_text_box"):
                    layer.auto_fit_text_box = self._prev_auto_fit
                if hasattr(layer, "_update_text_box_size_if_needed"):
                    layer._update_text_box_size_if_needed()
                self._canvas.document.document_changed.emit()
                try:
                    self._canvas.document.save_state("编辑文字")
                except Exception:
                    pass
            except Exception:
                pass
        self._close_editor()

    def _cancel(self):
        """取消编辑，恢复图层文字。"""
        if self._committed or self._closed:
            return
        self._committed = True
        if self._sync_timer.isActive():
            self._sync_timer.stop()
        layer = self._layer
        if layer is not None:
            try:
                layer.auto_fit_text_box = self._prev_auto_fit
                layer.set_text_lines(list(self._original_text_lines))
                layer.set_current_text(self._original_current_text, force=True)
                if hasattr(layer, "replace_text_style_ranges"):
                    layer.replace_text_style_ranges(
                        list(self._original_text_color_ranges),
                        list(self._original_font_size_ranges),
                    )
                layer._cached_image = None
                layer.changed.emit()
                self._canvas.document.document_changed.emit()
            except Exception:
                pass
        self._close_editor()

    def _close_editor(self):
        if self._closed:
            return
        self._closed = True
        canvas = self._canvas
        if getattr(canvas, "_text_editor", None) is self:
            canvas._text_editor = None
        try:
            self.close()
        except Exception:
            pass
        self.deleteLater()

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def keyPressEvent(self, event):
        key = event.key()
        if key == Qt.Key_Escape:
            self._cancel()
            event.accept()
            return
        if self._binding_enabled and key in (Qt.Key_Return, Qt.Key_Enter):
            if not (event.modifiers() & Qt.ShiftModifier):
                self._commit()
                event.accept()
                return
        super().keyPressEvent(event)

    def wheelEvent(self, event):
        if event.modifiers() & Qt.ControlModifier:
            delta = 1 if event.angleDelta().y() > 0 else -1
            if event.modifiers() & Qt.ShiftModifier:
                delta *= 5
            self._adjust_selected_font_size(delta)
            event.accept()
            return
        super().wheelEvent(event)

    def focusOutEvent(self, event):
        if not self._committed and not self._closed:
            QTimer.singleShot(0, self._commit)
        super().focusOutEvent(event)
