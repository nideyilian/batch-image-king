#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批图王 · 共享 UI 原语（阶段 2）

仅收录「有独立行为、且会在至少三个界面复用」的控件，避免过度抽象：
- InlineAlert：表单 / 字段内部的行内错误 / 警告提示（替代笼统弹窗）。
- EmptyState：无文档 / 无图层 / 无预设等空状态占位。
- ToastHost：统一成功 / 警告 / 失败提示，不打断工作流。

样式全部引用 design_tokens，禁止使用裸颜色值。
"""

from PySide6.QtWidgets import QFrame, QLabel, QPushButton, QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from PySide6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, QObject

from app.ui.design_tokens import Tokens
from app.ui.icon_manager import IconManager


_STATUS_COLORS = {
    "success": Tokens.SUCCESS,
    "warning": Tokens.WARNING,
    "error": Tokens.ERROR,
    "info": Tokens.INFO,
}
_STATUS_ICONS = {
    "success": "success",
    "warning": "warning",
    "error": "error",
    "info": "info",
}


class InlineAlert(QFrame):
    """行内提示：用于字段附近的错误 / 警告，不打断操作。"""

    def __init__(self, level="error", text="", parent=None):
        super().__init__(parent)
        self.setProperty("role", "inlineAlert")
        self._level = level
        self._icon = QLabel()
        self._icon.setFixedSize(16, 16)
        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setProperty("role", "inlineAlertText")
        self._label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

        row = QHBoxLayout(self)
        row.setContentsMargins(10, 8, 10, 8)
        row.setSpacing(8)
        row.addWidget(self._icon)
        row.addWidget(self._label)
        self.set_level(level)
        self.set_text(text)

    def set_level(self, level):
        self._level = level
        color = _STATUS_COLORS.get(level, Tokens.INFO)
        icon = IconManager.get_icon(_STATUS_ICONS.get(level, "info"), 16, color)
        if not icon.isNull():
            self._icon.setPixmap(icon.pixmap(16, 16))
        self.setStyleSheet(f"""
            QFrame[role="inlineAlert"] {{
                background-color: {Tokens.BG_SECONDARY};
                border: 1px solid {color};
                border-left: 3px solid {color};
                border-radius: 6px;
            }}
            QLabel[role="inlineAlertText"] {{
                color: {Tokens.TEXT_PRIMARY};
                background: transparent;
                font-size: {Tokens.FIELD_LABEL_FONT_SIZE}px;
            }}
        """)

    def set_text(self, text):
        self._label.setText(text)
        self.setVisible(bool(text))


class EmptyState(QFrame):
    """空状态占位：图标 + 标题 + 描述 + 可选主操作按钮。"""

    def __init__(self, icon_name="file", title="", description="", parent=None):
        super().__init__(parent)
        self.setProperty("role", "emptyState")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self._icon = QLabel()
        self._icon.setFixedSize(48, 48)
        self._title = QLabel(title)
        self._title.setProperty("role", "featureTitle")
        self._title.setAlignment(Qt.AlignCenter)
        self._desc = QLabel(description)
        self._desc.setProperty("role", "summaryLabel")
        self._desc.setAlignment(Qt.AlignCenter)
        self._desc.setWordWrap(True)
        self._action = QPushButton()
        self._action.setProperty("variant", "primary")
        self._action.setVisible(False)

        col = QVBoxLayout(self)
        col.setAlignment(Qt.AlignCenter)
        col.setSpacing(10)
        col.addStretch(1)
        col.addWidget(self._icon, 0, Qt.AlignCenter)
        col.addWidget(self._title, 0, Qt.AlignCenter)
        col.addWidget(self._desc, 0, Qt.AlignCenter)
        col.addWidget(self._action, 0, Qt.AlignCenter)
        col.addStretch(1)

        self.set_icon(icon_name)
        self.set_title(title)
        self.set_description(description)
        self.setStyleSheet(f"""
            QFrame[role="emptyState"] {{
                background: transparent;
                border: none;
            }}
            QLabel[role="featureTitle"] {{
                color: {Tokens.TEXT_PRIMARY};
                font-size: {Tokens.FEATURE_TITLE_FONT_SIZE}px;
                font-weight: {Tokens.FONT_WEIGHT_BOLD};
            }}
            QLabel[role="summaryLabel"] {{
                color: {Tokens.TEXT_MUTED};
                font-size: {Tokens.FIELD_LABEL_FONT_SIZE}px;
            }}
        """)

    def set_icon(self, icon_name):
        icon = IconManager.get_icon(icon_name, 48, Tokens.TEXT_MUTED)
        if not icon.isNull():
            self._icon.setPixmap(icon.pixmap(48, 48))

    def set_title(self, title):
        self._title.setText(title)

    def set_description(self, description):
        self._desc.setText(description)

    def set_action(self, text, slot):
        self._action.setText(text)
        self._action.setVisible(bool(text))
        if self._action.receivers(self._action.clicked) > 0:
            self._action.clicked.disconnect()
        if slot:
            self._action.clicked.connect(slot)


class _ToastCard(QFrame):
    """ToastHost 内部的单条提示卡片。"""

    def __init__(self, message, kind, parent=None):
        super().__init__(parent)
        color = _STATUS_COLORS.get(kind, Tokens.INFO)
        self._icon = QLabel()
        self._icon.setFixedSize(18, 18)
        icon = IconManager.get_icon(_STATUS_ICONS.get(kind, "info"), 18, color)
        if not icon.isNull():
            self._icon.setPixmap(icon.pixmap(18, 18))
        self._label = QLabel(message)
        self._label.setProperty("role", "toastText")
        self._label.setWordWrap(True)

        row = QHBoxLayout(self)
        row.setContentsMargins(12, 9, 12, 9)
        row.setSpacing(8)
        row.addWidget(self._icon)
        row.addWidget(self._label)

        self.setStyleSheet(f"""
            QFrame {{
                background-color: {Tokens.BG_ELEVATED};
                border: 1px solid {color};
                border-radius: 8px;
            }}
            QLabel[role="toastText"] {{
                color: {Tokens.TEXT_PRIMARY};
                background: transparent;
                font-size: {Tokens.FONT_SIZE_BASE}px;
                font-weight: {Tokens.FONT_WEIGHT_MEDIUM};
            }}
        """)

    def fade_out(self):
        effect = self.graphicsEffect()
        if effect is not None:
            anim = QPropertyAnimation(effect, b"opacity", self)
            anim.setDuration(Tokens.MOTION_MS)
            anim.setStartValue(1.0)
            anim.setEndValue(0.0)
            anim.setEasingCurve(QEasingCurve.OutCubic)
            anim.finished.connect(self.deleteLater)
            anim.start()
        else:
            self.deleteLater()


class ToastHost(QObject):
    """统一 Toast 宿主：在父控件底部居中堆叠显示提示，自动淡出。

    用法：
        ToastHost.show(parent_widget, "已导出 100 张图片", "success")
    """

    _overlay = None

    @classmethod
    def _ensure_overlay(cls, parent):
        if cls._overlay is not None and cls._overlay.parent() is parent and parent is not None:
            return cls._overlay
        overlay = QWidget(parent)
        overlay.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        overlay.setAttribute(Qt.WA_TranslucentBackground, True)
        layout = QVBoxLayout(overlay)
        layout.setContentsMargins(0, 0, 0, 24)
        layout.setSpacing(8)
        layout.addStretch(1)
        layout.setAlignment(Qt.AlignHCenter)
        cls._overlay = overlay
        return overlay

    @classmethod
    def show(cls, parent, message, kind="info", duration=3000):
        if parent is None:
            return
        overlay = cls._ensure_overlay(parent)
        card = _ToastCard(message, kind, overlay)
        overlay.layout().addWidget(card)
        overlay.resize(parent.size())
        overlay.show()
        overlay.raise_()
        QTimer.singleShot(max(800, duration), lambda: cls._dismiss(card))

    @classmethod
    def _dismiss(cls, card):
        if card is not None and not card.isHidden():
            card.fade_out()
