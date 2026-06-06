#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dialog A2 shell for the enhanced font selector."""

from PySide6.QtWidgets import QDialog, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from app.ui.dialog_a2 import DialogA2
from app.ui.enhanced_font_selector import EnhancedFontSelector


class FontPickerDialogA2(QDialog):
    """Wrap EnhancedFontSelector in the shared Dialog A2 modal structure."""

    def __init__(
        self,
        parent=None,
        initial_font="",
        preview_text="",
        selector_factory=EnhancedFontSelector,
    ):
        super().__init__(parent)
        self._selected_font = initial_font or ""
        self.setWindowTitle("选择字体")
        self.setModal(True)
        self.resize(460, 680)
        DialogA2.apply(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(DialogA2.OUTER_MARGIN, DialogA2.OUTER_MARGIN, DialogA2.OUTER_MARGIN, DialogA2.OUTER_MARGIN)
        root.setSpacing(DialogA2.CONTENT_GAP)

        self.title_label = QLabel("选择字体")
        self.title_label.setProperty("role", "dialogTitle")
        root.addWidget(self.title_label)

        card = QFrame()
        card.setProperty("role", "dialogCard")
        card_layout = QVBoxLayout(card)
        card_layout.setContentsMargins(*DialogA2.CARD_MARGIN)
        card_layout.setSpacing(DialogA2.CARD_GAP)

        self.selector = selector_factory(card)
        if initial_font and hasattr(self.selector, "set_current_font"):
            self.selector.set_current_font(initial_font)
        if preview_text and hasattr(self.selector, "preview_text_edit"):
            self.selector.preview_text_edit.setText(preview_text)
        if hasattr(self.selector, "font_changed"):
            self.selector.font_changed.connect(self._on_font_changed)
        card_layout.addWidget(self.selector)
        root.addWidget(card, 1)

        footer = QFrame()
        footer.setProperty("role", "dialogFooter")
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addStretch()
        self.ok_button = QPushButton("确定")
        self.cancel_button = QPushButton("取消")
        DialogA2.mark_primary(self.ok_button)
        DialogA2.mark_secondary(self.cancel_button)
        self.ok_button.clicked.connect(self.accept)
        self.cancel_button.clicked.connect(self.reject)
        footer_layout.addWidget(self.ok_button)
        footer_layout.addWidget(self.cancel_button)
        root.addWidget(footer)

    def selected_font(self):
        if self._selected_font:
            return self._selected_font
        if hasattr(self.selector, "get_current_font"):
            return self.selector.get_current_font()
        return getattr(self.selector, "current_font", "")

    def _on_font_changed(self, font_name):
        self._selected_font = font_name
