#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Reusable A v2 styling tokens for right-side property panels."""


class PropertyPanelA2:
    """Design tokens and QSS roles for dense dark property panels."""

    PANEL_MARGIN = 8
    CARD_GAP = 6
    CARD_RADIUS = 7
    HEADER_HEIGHT = 36
    BODY_MARGINS = (10, 8, 10, 8)
    SUBPANEL_MARGINS = (8, 6, 8, 6)
    ROW_GAP = 6
    SECTION_GAP = 8
    CONTROL_HEIGHT = 30
    TEXT_AREA_HEIGHT = 96
    LABEL_WIDTH = 58
    SECONDARY_LABEL_WIDTH = 40
    POSITION_LABEL_WIDTH = 22
    SPIN_WIDTH = 76
    COLOR_SWATCH_SIZE = 30
    ICON_BUTTON_WIDTH = 42
    FONT_BUTTON_MIN_WIDTH = 56
    SWITCH_SIZE = (52, 30)

    PANEL_BG = "#181818"
    CARD_BG = "#202123"
    HEADER_BG = "#2A2B2E"
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

    @classmethod
    def stylesheet(cls, root_selector="#IntegratedTextPanel"):
        """Return QSS for widgets that opt into A v2 property roles."""
        return f"""
            {root_selector} {{
                background: {cls.PANEL_BG};
                color: {cls.TEXT_PRIMARY};
                font-size: 12px;
            }}
            {root_selector} QLabel {{
                color: {cls.TEXT_PRIMARY};
                background: transparent;
            }}
            {root_selector} QFrame[role="section"] {{
                background-color: {cls.CARD_BG};
                border: 1px solid {cls.BORDER};
                border-radius: {cls.CARD_RADIUS}px;
            }}
            {root_selector} QFrame[role="sectionHeader"] {{
                background-color: {cls.HEADER_BG};
                border: none;
                border-bottom: 1px solid {cls.BORDER_SOFT};
                border-top-left-radius: {cls.CARD_RADIUS}px;
                border-top-right-radius: {cls.CARD_RADIUS}px;
            }}
            {root_selector} QFrame[role="sectionBody"] {{
                background-color: transparent;
                border: none;
            }}
            {root_selector} QFrame[role="subPanel"] {{
                background-color: {cls.CONTROL_BG};
                border: 1px solid {cls.BORDER_SOFT};
                border-radius: 6px;
            }}
            {root_selector} QFrame[role="coreDivider"] {{
                background-color: {cls.BORDER_SOFT};
                border: none;
            }}
            {root_selector} QLabel[role="sectionTitle"] {{
                color: #FFFFFF;
                font-size: 13px;
                font-weight: 700;
            }}
            {root_selector} QLabel[role="summaryLabel"] {{
                color: {cls.TEXT_MUTED};
                font-size: 11px;
            }}
            {root_selector} QLabel[role="fieldLabel"] {{
                color: {cls.TEXT_PRIMARY};
                font-size: 12px;
                font-weight: 700;
            }}
            {root_selector} QLabel[role="mutedLabel"] {{
                color: {cls.TEXT_MUTED};
                font-size: 11px;
                font-weight: 700;
            }}
            {root_selector} QPushButton,
            {root_selector} QToolButton {{
                min-height: {cls.CONTROL_HEIGHT}px;
                border: 1px solid {cls.BORDER_CONTROL};
                border-radius: 4px;
                background-color: {cls.CONTROL_BG_ALT};
                color: {cls.TEXT_PRIMARY};
                padding: 3px 8px;
            }}
            {root_selector} QPushButton:hover,
            {root_selector} QToolButton:hover {{
                background-color: {cls.CONTROL_BG_HOVER};
                border-color: {cls.ACCENT_HOVER};
            }}
            {root_selector} QPushButton:pressed,
            {root_selector} QToolButton:pressed {{
                background-color: {cls.ACCENT_PRESSED};
                border-color: {cls.ACCENT};
            }}
            {root_selector} QPushButton:disabled,
            {root_selector} QToolButton:disabled {{
                color: {cls.TEXT_DISABLED};
                background-color: #20252B;
                border-color: #252528;
            }}
            {root_selector} QPushButton[segmentButton="true"] {{
                min-height: {cls.CONTROL_HEIGHT}px;
                max-height: {cls.CONTROL_HEIGHT}px;
                padding: 3px 6px;
                background-color: {cls.CONTROL_BG_ALT};
                font-size: 12px;
            }}
            {root_selector} QPushButton[segmentButton="true"]:checked {{
                background-color: {cls.ACCENT};
                border-color: {cls.ACCENT_HOVER};
                color: #FFFFFF;
                font-weight: 700;
            }}
            {root_selector} QPushButton[compactValue="true"] {{
                min-height: {cls.CONTROL_HEIGHT}px;
                max-height: {cls.CONTROL_HEIGHT}px;
                background-color: {cls.CONTROL_BG};
                border-color: {cls.BORDER_SOFT};
                font-weight: 700;
            }}
            {root_selector} QTextEdit,
            {root_selector} QLineEdit,
            {root_selector} QComboBox,
            {root_selector} QSpinBox {{
                background-color: {cls.CONTROL_BG};
                color: #E9EEF3;
                border: 1px solid {cls.BORDER_CONTROL};
                border-radius: 4px;
                selection-background-color: #0E76D8;
                padding: 3px 6px;
            }}
            {root_selector} QTextEdit:focus,
            {root_selector} QLineEdit:focus,
            {root_selector} QComboBox:focus,
            {root_selector} QSpinBox:focus {{
                border-color: {cls.ACCENT};
            }}
            {root_selector} QCheckBox {{
                color: {cls.TEXT_PRIMARY};
                spacing: 6px;
            }}
            {root_selector} QCheckBox::indicator {{
                width: 15px;
                height: 15px;
                border-radius: 3px;
                border: 1px solid #58636F;
                background: #2F2F2F;
            }}
            {root_selector} QCheckBox::indicator:checked {{
                background: {cls.ACCENT};
                border-color: {cls.ACCENT_HOVER};
            }}
            {root_selector} QSlider::groove:horizontal {{
                height: 4px;
                background: {cls.BORDER_CONTROL};
                border-radius: 2px;
            }}
            {root_selector} QSlider::sub-page:horizontal {{
                background: {cls.ACCENT};
                border-radius: 2px;
            }}
            {root_selector} QSlider::handle:horizontal {{
                background: {cls.ACCENT_HOVER};
                width: 16px;
                height: 16px;
                margin: -6px 0;
                border-radius: 8px;
            }}
        """
