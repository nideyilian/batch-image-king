#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable Dialog A2 styling tokens for modal windows."""


class DialogA2:
    """Design tokens and helpers for dark, task-focused dialogs."""

    OUTER_MARGIN = 20
    CONTENT_GAP = 12
    CARD_MARGIN = (14, 12, 14, 12)
    CARD_GAP = 10
    CARD_RADIUS = 6
    CONTROL_HEIGHT = 32
    BUTTON_HEIGHT = 34
    BUTTON_WIDTH = 80
    SMALL_BUTTON_WIDTH = 56
    FIELD_LABEL_WIDTH = 82
    SWATCH_SIZE = 28
    PREVIEW_SWATCH_SIZE = 68

    TITLE_FONT_SIZE = 16
    SECTION_TITLE_FONT_SIZE = 13
    FIELD_FONT_SIZE = 12
    HINT_FONT_SIZE = 11

    PANEL_BG = "#181818"
    CARD_BG = "#202123"
    TITLE_BG = "#1B2230"
    SUBPANEL_BG = "#111315"
    CONTROL_BG = "#111315"
    CONTROL_BG_ALT = "#242526"
    CONTROL_BG_HOVER = "#303236"
    BORDER = "#303033"
    BORDER_SOFT = "#34383B"
    BORDER_CONTROL = "#3A3A3D"
    TEXT_PRIMARY = "#F4F4F5"
    TEXT_MUTED = "#8E95A3"
    TEXT_DISABLED = "#606064"
    ACCENT = "#2F9CF4"
    ACCENT_HOVER = "#55B2FF"
    ACCENT_PRESSED = "#1F7EC8"

    # 与 property_panel_a2 / design_tokens 对齐的语义别名（单一真源）
    TEXT_INVERTED = "#FFFFFF"
    TEXT_INPUT = "#E9EEF3"
    SELECTION_BG = "#0E76D8"
    DISABLED_CTL_BG = "#20252B"
    BORDER_SUBTLE = "#252528"
    BORDER_INDICATOR = "#52555B"
    BG_ELEVATED = "#2F2F2F"
    FONT_WEIGHT_BOLD = 700
    FONT_WEIGHT_MEDIUM = 600

    @classmethod
    def apply(cls, dialog):
        dialog.setProperty("dialogA2", True)
        dialog.setStyleSheet(cls.stylesheet())

    @classmethod
    def mark_primary(cls, button):
        button.setProperty("primaryButton", True)
        button.setFixedSize(cls.BUTTON_WIDTH, cls.BUTTON_HEIGHT)

    @classmethod
    def mark_secondary(cls, button):
        button.setProperty("secondaryButton", True)
        button.setFixedSize(cls.BUTTON_WIDTH, cls.BUTTON_HEIGHT)

    @classmethod
    def stylesheet(cls):
        return f"""
            QDialog[dialogA2="true"] {{
                background-color: {cls.PANEL_BG};
                color: {cls.TEXT_PRIMARY};
                font-size: {cls.FIELD_FONT_SIZE}px;
            }}
            QDialog[dialogA2="true"] QLabel {{
                color: {cls.TEXT_PRIMARY};
                background: transparent;
            }}
            QDialog[dialogA2="true"] QFrame[role="dialogCard"] {{
                background-color: {cls.CARD_BG};
                border: 1px solid {cls.BORDER};
                border-radius: {cls.CARD_RADIUS}px;
            }}
            QDialog[dialogA2="true"] QFrame[role="dialogSubPanel"] {{
                background-color: {cls.SUBPANEL_BG};
                border: 1px solid {cls.BORDER_SOFT};
                border-radius: {cls.CARD_RADIUS}px;
            }}
            QDialog[dialogA2="true"] QFrame[role="dialogFooter"] {{
                background-color: transparent;
                border: none;
            }}
            QDialog[dialogA2="true"] QLabel[role="dialogTitle"] {{
                color: {cls.TEXT_INVERTED};
                font-size: {cls.TITLE_FONT_SIZE}px;
                font-weight: {cls.FONT_WEIGHT_BOLD};
            }}
            QDialog[dialogA2="true"] QLabel[role="sectionTitle"] {{
                color: {cls.TEXT_INVERTED};
                font-size: {cls.SECTION_TITLE_FONT_SIZE}px;
                font-weight: {cls.FONT_WEIGHT_BOLD};
            }}
            QDialog[dialogA2="true"] QLabel[role="fieldLabel"] {{
                color: {cls.TEXT_PRIMARY};
                font-size: {cls.FIELD_FONT_SIZE}px;
                font-weight: {cls.FONT_WEIGHT_BOLD};
            }}
            QDialog[dialogA2="true"] QLabel[role="hint"] {{
                color: {cls.TEXT_MUTED};
                font-size: {cls.HINT_FONT_SIZE}px;
            }}
            QDialog[dialogA2="true"] QLineEdit,
            QDialog[dialogA2="true"] QSpinBox,
            QDialog[dialogA2="true"] QComboBox,
            QDialog[dialogA2="true"] QListWidget,
            QDialog[dialogA2="true"] QTextEdit {{
                min-height: {cls.CONTROL_HEIGHT}px;
                background-color: {cls.CONTROL_BG};
                color: {cls.TEXT_INPUT};
                border: 1px solid {cls.BORDER_CONTROL};
                border-radius: 4px;
                selection-background-color: {cls.SELECTION_BG};
                padding: 3px 6px;
            }}
            QDialog[dialogA2="true"] QListWidget::item {{
                min-height: 26px;
                padding: 4px 6px;
                border-radius: 3px;
            }}
            QDialog[dialogA2="true"] QListWidget::item:selected {{
                background-color: {cls.ACCENT};
                color: {cls.TEXT_INVERTED};
            }}
            QDialog[dialogA2="true"] QSplitter::handle {{
                background-color: {cls.BORDER};
                margin: 0 6px;
            }}
            QDialog[dialogA2="true"] QLineEdit:focus,
            QDialog[dialogA2="true"] QSpinBox:focus,
            QDialog[dialogA2="true"] QComboBox:focus,
            QDialog[dialogA2="true"] QTextEdit:focus {{
                border-color: {cls.ACCENT};
            }}
            QDialog[dialogA2="true"] QPushButton,
            QDialog[dialogA2="true"] QToolButton {{
                min-height: {cls.CONTROL_HEIGHT}px;
                border: 1px solid {cls.BORDER_CONTROL};
                border-radius: 4px;
                background-color: {cls.CONTROL_BG_ALT};
                color: {cls.TEXT_PRIMARY};
                font-size: {cls.FIELD_FONT_SIZE}px;
                font-weight: {cls.FONT_WEIGHT_MEDIUM};
                padding: 3px 10px;
            }}
            QDialog[dialogA2="true"] QPushButton:hover,
            QDialog[dialogA2="true"] QToolButton:hover {{
                background-color: {cls.CONTROL_BG_HOVER};
                border-color: {cls.ACCENT_HOVER};
            }}
            QDialog[dialogA2="true"] QPushButton:pressed,
            QDialog[dialogA2="true"] QToolButton:pressed {{
                background-color: {cls.ACCENT_PRESSED};
                border-color: {cls.ACCENT};
            }}
            QDialog[dialogA2="true"] QPushButton:disabled,
            QDialog[dialogA2="true"] QToolButton:disabled {{
                color: {cls.TEXT_DISABLED};
                background-color: {cls.DISABLED_CTL_BG};
                border-color: {cls.BORDER_SUBTLE};
            }}
            QDialog[dialogA2="true"] QPushButton[primaryButton="true"] {{
                min-width: {cls.BUTTON_WIDTH}px;
                min-height: {cls.BUTTON_HEIGHT}px;
                background-color: {cls.ACCENT};
                border-color: {cls.ACCENT_HOVER};
                color: {cls.TEXT_INVERTED};
                font-weight: {cls.FONT_WEIGHT_BOLD};
            }}
            QDialog[dialogA2="true"] QPushButton[primaryButton="true"]:hover {{
                background-color: {cls.ACCENT_HOVER};
                border-color: {cls.ACCENT_HOVER};
            }}
            QDialog[dialogA2="true"] QPushButton[secondaryButton="true"] {{
                min-width: {cls.BUTTON_WIDTH}px;
                min-height: {cls.BUTTON_HEIGHT}px;
                background-color: {cls.CONTROL_BG_ALT};
                border-color: {cls.BORDER_CONTROL};
            }}
            QDialog[dialogA2="true"] QCheckBox {{
                color: {cls.TEXT_PRIMARY};
                spacing: 6px;
            }}
            QDialog[dialogA2="true"] QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border-radius: 3px;
                border: 1px solid {cls.BORDER_INDICATOR};
                background: {cls.BG_ELEVATED};
            }}
            QDialog[dialogA2="true"] QCheckBox::indicator:checked {{
                background: {cls.ACCENT};
                border-color: {cls.ACCENT_HOVER};
            }}
            QDialog[dialogA2="true"] QTabWidget::pane {{
                border: 1px solid {cls.BORDER};
                border-radius: 4px;
                background-color: {cls.SUBPANEL_BG};
            }}
            QDialog[dialogA2="true"] QTabBar::tab {{
                background-color: {cls.CONTROL_BG};
                color: {cls.TEXT_PRIMARY};
                border: 1px solid {cls.BORDER};
                padding: 6px 12px;
                margin-right: 4px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QDialog[dialogA2="true"] QTabBar::tab:selected {{
                background-color: {cls.ACCENT};
                color: {cls.TEXT_INVERTED};
                font-weight: {cls.FONT_WEIGHT_BOLD};
            }}
        """
