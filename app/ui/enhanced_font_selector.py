import logging

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (QWidget, QComboBox, QLineEdit, QVBoxLayout,
                               QHBoxLayout, QLabel, QPushButton, QListWidget,
                               QListWidgetItem, QSplitter, QGroupBox, QCheckBox,
                               QCompleter, QTabWidget, QTextEdit, QFrame, QSpinBox)
from PySide6.QtCore import Qt, Signal, QTimer, QStringListModel
from PySide6.QtGui import QFont, QIcon, QPixmap, QPainter, QColor, QPen
import json
import os
from typing import Dict, List, Optional
from pathlib import Path

from app.ui.design_spec import IconSize as _IconSize
from app.ui.tokens_v2 import Color


class EnhancedFontSelector(QWidget):
    """增强字体选择器组件：中文 / 英文 两个分类 Tab"""

    font_changed = Signal(str)  # 字体变更信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_font = ""
        self.favorite_fonts = []
        self.recent_fonts = []
        self.font_categories = {}
        self.all_fonts = []
        self.cn_names = {}
        self._syncing_selection = False

        # 创建预览更新定时器（防抖机制）
        from PySide6.QtCore import QTimer
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._delayed_update_preview)

        # 加载收藏字体
        self.load_favorites()
        self.load_recent_fonts()

        self.setup_ui()
        self.load_fonts()

    def setup_ui(self):
        """设置UI界面"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.setStyleSheet(f"""
            QWidget {{
                background-color: {Color.surface_1};
                color: {Color.text_primary};
            }}
            QLineEdit, QSpinBox, QListWidget, QTabWidget::pane {{
                background-color: {Color.surface_3};
                color: {Color.text_primary};
                border: 1px solid {Color.border_strong};
                border-radius: 4px;
            }}
            QListWidget::item:selected {{
                background-color: {Color.surface_selected};
                color: {Color.text_on_selected};
            }}
            QPushButton {{
                background-color: {Color.surface_3};
                color: {Color.text_primary};
                border: 1px solid {Color.border_strong};
                border-radius: 4px;
                padding: 4px 8px;
            }}
            QPushButton:hover {{
                background-color: {Color.surface_hover};
            }}
            QTabBar::tab {{
                background-color: {Color.surface_3};
                color: {Color.text_primary};
                border: 1px solid {Color.border_strong};
                padding: 6px 12px;
                margin-right: 4px;
                border-top-left-radius: 4px;
                border-top-right-radius: 4px;
            }}
            QTabBar::tab:selected {{
                background-color: {Color.accent};
                color: {Color.text_on_accent};
            }}
        """)

        # 顶部搜索区域
        search_layout = QHBoxLayout()

        # 搜索框
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索字体名（支持模糊匹配）")
        self.search_edit.textChanged.connect(self.filter_fonts)
        search_layout.addWidget(self.search_edit)

        # 收藏按钮
        self.favorite_btn = QPushButton("★")
        self.favorite_btn.setFixedSize(_IconSize.MD, _IconSize.MD)
        self.favorite_btn.setCheckable(True)
        self.favorite_btn.setToolTip("收藏/取消收藏当前字体")
        self.favorite_btn.clicked.connect(self.toggle_favorite)
        search_layout.addWidget(self.favorite_btn)

        layout.addLayout(search_layout)

        # 主内容区域 - 中文 / 英文 两个分类 Tab
        self.tab_widget = QTabWidget()

        self.chinese_fonts_list = QListWidget()
        self.chinese_fonts_list.itemClicked.connect(self.on_font_selected)
        self.chinese_fonts_list.itemSelectionChanged.connect(lambda: self._on_current_item_changed(self.chinese_fonts_list))
        self.tab_widget.addTab(self.chinese_fonts_list, f"中文 (0)")

        self.english_fonts_list = QListWidget()
        self.english_fonts_list.itemClicked.connect(self.on_font_selected)
        self.english_fonts_list.itemSelectionChanged.connect(lambda: self._on_current_item_changed(self.english_fonts_list))
        self.tab_widget.addTab(self.english_fonts_list, f"英文 (0)")

        layout.addWidget(self.tab_widget)

        # 字体预览区域
        preview_group = QGroupBox("字体预览")
        preview_layout = QVBoxLayout(preview_group)

        # 预览文本输入
        self.preview_text_edit = QLineEdit("批图王 Font Preview 字体预览 AaBb123")
        self.preview_text_edit.setPlaceholderText("输入预览文本...")
        self.preview_text_edit.textChanged.connect(self.update_preview)
        preview_layout.addWidget(self.preview_text_edit)

        # 预览显示
        self.preview_label = QLabel("字体预览")
        self.preview_label.setMinimumHeight(80)
        self.preview_label.setAlignment(Qt.AlignCenter)
        self.preview_label.setStyleSheet(f"""
            QLabel {{
                border: 1px solid {Color.border_strong};
                border-radius: 5px;
                background-color: {Color.surface_base};
                color: {Color.text_primary};
                padding: 10px;
                font-size: 24px;
            }}
        """)
        preview_layout.addWidget(self.preview_label)

        # 预览控制
        preview_control_layout = QHBoxLayout()

        self.preview_size_spin = QSpinBox()
        self.preview_size_spin.setRange(12, 72)
        self.preview_size_spin.setValue(24)
        self.preview_size_spin.valueChanged.connect(self.update_preview)
        preview_control_layout.addWidget(QLabel("大小:"))
        preview_control_layout.addWidget(self.preview_size_spin)

        self.bold_check = QCheckBox("粗体")
        self.bold_check.stateChanged.connect(self.update_preview)
        preview_control_layout.addWidget(self.bold_check)

        self.italic_check = QCheckBox("斜体")
        self.italic_check.stateChanged.connect(self.update_preview)
        preview_control_layout.addWidget(self.italic_check)

        preview_control_layout.addStretch()
        preview_layout.addLayout(preview_control_layout)

        layout.addWidget(preview_group)

    def load_fonts(self):
        """加载字体列表"""
        # 创建临时TextLayer获取字体
        from app.models.text_layer import TextLayer
        text_layer = TextLayer()

        # 获取所有字体与分类
        self.all_fonts = text_layer.get_system_fonts()
        self.font_categories = text_layer.get_categorized_fonts()
        self.cn_names = text_layer.get_font_cn_names()

        # 填充列表
        self.populate_font_lists()

        # 更新标签页标题
        self.update_tab_titles()

    def populate_font_lists(self):
        """填充字体列表"""
        # 中文字体
        self.chinese_fonts_list.clear()
        for font in self.font_categories.get('chinese', []):
            display = self._font_display_name(font)
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, font)
            if font in self.favorite_fonts:
                item.setText(f"★ {display}")
            self.chinese_fonts_list.addItem(item)

        # 英文字体
        self.english_fonts_list.clear()
        for font in self.font_categories.get('english', []):
            display = self._font_display_name(font)
            item = QListWidgetItem(display)
            item.setData(Qt.UserRole, font)
            if font in self.favorite_fonts:
                item.setText(f"★ {display}")
            self.english_fonts_list.addItem(item)

        # 收藏/最近列表
        self.update_favorite_list()
        self.update_recent_list()

    def update_favorite_list(self):
        """更新收藏字体列表"""
        if not hasattr(self, "favorite_fonts_list"):
            return
        self.favorite_fonts_list.clear()
        for font in self.favorite_fonts:
            if font in self.all_fonts:
                item = QListWidgetItem(f"★ {self._font_display_name(font)}")
                item.setData(Qt.UserRole, font)
                self.favorite_fonts_list.addItem(item)

    def update_recent_list(self):
        """更新最近字体列表"""
        if not hasattr(self, "recent_fonts_list"):
            return
        was_syncing = self._syncing_selection
        was_blocked = self.recent_fonts_list.blockSignals(True)
        self._syncing_selection = True
        try:
            self.recent_fonts_list.clear()
            for font in self.recent_fonts:
                if font in self.all_fonts:
                    item = QListWidgetItem(self._font_display_name(font))
                    item.setData(Qt.UserRole, font)
                    self.recent_fonts_list.addItem(item)
        finally:
            self.recent_fonts_list.blockSignals(was_blocked)
            self._syncing_selection = was_syncing

    def update_tab_titles(self):
        """更新标签页标题"""
        self.tab_widget.setTabText(0, f"中文 ({len(self.font_categories.get('chinese', []))})")
        self.tab_widget.setTabText(1, f"英文 ({len(self.font_categories.get('english', []))})")

    def filter_fonts(self, text):
        """过滤字体"""
        if not text.strip():
            self.populate_font_lists()
            return

        # 在中文字体列表中过滤
        self.chinese_fonts_list.clear()
        for font in self.font_categories.get('chinese', []):
            if self._font_match(font, text):
                display = self._font_display_name(font)
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, font)
                if font in self.favorite_fonts:
                    item.setText(f"★ {display}")
                self.chinese_fonts_list.addItem(item)

        # 在英文字体列表中过滤
        self.english_fonts_list.clear()
        for font in self.font_categories.get('english', []):
            if self._font_match(font, text):
                display = self._font_display_name(font)
                item = QListWidgetItem(display)
                item.setData(Qt.UserRole, font)
                if font in self.favorite_fonts:
                    item.setText(f"★ {display}")
                self.english_fonts_list.addItem(item)

        # 在收藏字体列表中过滤
        if hasattr(self, "favorite_fonts_list"):
            self.favorite_fonts_list.clear()
            for font in self.favorite_fonts:
                if font in self.all_fonts and self._font_match(font, text):
                    item = QListWidgetItem(f"★ {self._font_display_name(font)}")
                    item.setData(Qt.UserRole, font)
                    self.favorite_fonts_list.addItem(item)

        # 在最近字体列表中过滤
        if hasattr(self, "recent_fonts_list"):
            self.recent_fonts_list.clear()
            for font in self.recent_fonts:
                if font in self.all_fonts and self._font_match(font, text):
                    item = QListWidgetItem(self._font_display_name(font))
                    item.setData(Qt.UserRole, font)
                    self.recent_fonts_list.addItem(item)

    def on_font_selected(self, item):
        """字体被选中"""
        font_name = item.data(Qt.UserRole)
        if font_name:
            self.set_current_font(font_name)

    def _on_current_item_changed(self, list_widget: QListWidget):
        """列表选中项变化时实时更新预览（键盘上下键也生效）。"""
        if self._syncing_selection:
            return
        item = list_widget.currentItem()
        if not item:
            return
        font_name = item.data(Qt.UserRole)
        if font_name and font_name != self.current_font:
            self.set_current_font(font_name)

    def set_current_font(self, font_name):
        """设置当前字体"""
        self.current_font = font_name
        was_syncing = self._syncing_selection
        self._syncing_selection = True
        try:
            self._push_recent_font(font_name)
            self._select_font_in_lists(font_name)
        finally:
            self._syncing_selection = was_syncing
        self.update_favorite_button()
        self.update_preview()
        self.font_changed.emit(font_name)

    def get_current_font(self):
        """获取当前字体"""
        return self.current_font

    def _select_font_in_list(self, list_widget: QListWidget, font_name: str):
        for i in range(list_widget.count()):
            item = list_widget.item(i)
            if item and item.data(Qt.UserRole) == font_name:
                list_widget.setCurrentItem(item)
                break

    def _select_font_in_lists(self, font_name: str):
        """在所有分类列表中高亮当前字体，不影响搜索过滤条件。"""
        if not font_name:
            return
        was_syncing = self._syncing_selection
        self._syncing_selection = True
        try:
            self._select_font_in_list(self.chinese_fonts_list, font_name)
            self._select_font_in_list(self.english_fonts_list, font_name)
            for list_name in ("favorite_fonts_list", "recent_fonts_list"):
                widget = getattr(self, list_name, None)
                if widget is not None:
                    self._select_font_in_list(widget, font_name)
        finally:
            self._syncing_selection = was_syncing

    def update_favorite_button(self):
        """更新收藏按钮状态"""
        self.favorite_btn.setChecked(self.current_font in self.favorite_fonts)

    def toggle_favorite(self):
        """切换收藏状态"""
        if not self.current_font:
            return

        if self.current_font in self.favorite_fonts:
            self.favorite_fonts.remove(self.current_font)
        else:
            self.favorite_fonts.append(self.current_font)

        self.save_favorites()
        self.populate_font_lists()
        self.update_favorite_button()

    def update_preview(self):
        """更新字体预览 - 使用防抖机制"""
        # 重置定时器，实现防抖
        if self._preview_timer.isActive():
            self._preview_timer.stop()
        self._preview_timer.start(100)  # 100ms延迟

    def _delayed_update_preview(self):
        """延迟更新字体预览（实际执行预览更新）"""
        if not self.current_font:
            return

        preview_text = self.preview_text_edit.text() or "字体预览"
        font_size = self.preview_size_spin.value()

        # 创建字体
        font = QFont(self.current_font, font_size)
        if self.bold_check.isChecked():
            font.setBold(True)
        if self.italic_check.isChecked():
            font.setItalic(True)

        self.preview_label.setFont(font)
        self.preview_label.setText(preview_text)

    def load_favorites(self):
        """加载收藏字体"""
        try:
            config_dir = Path.home() / ".config" / "批图王"
            config_dir.mkdir(parents=True, exist_ok=True)

            favorites_file = config_dir / "favorite_fonts.json"
            if favorites_file.exists():
                with open(favorites_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.favorite_fonts = data.get('favorites', [])
        except Exception:
            self.favorite_fonts = []

    def save_favorites(self):
        """保存收藏字体"""
        try:
            config_dir = Path.home() / ".config" / "批图王"
            config_dir.mkdir(parents=True, exist_ok=True)

            favorites_file = config_dir / "favorite_fonts.json"
            with open(favorites_file, 'w', encoding='utf-8') as f:
                json.dump({'favorites': self.favorite_fonts}, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.warning("静默异常已忽略: except in ui/enhanced_font_selector.py", exc_info=True)
            pass

    def load_recent_fonts(self):
        """加载最近字体"""
        try:
            config_dir = Path.home() / ".config" / "批图王"
            config_dir.mkdir(parents=True, exist_ok=True)
            recent_file = config_dir / "recent_fonts.json"
            if recent_file.exists():
                with open(recent_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    fonts = data.get("recent", [])
                    self.recent_fonts = [f for f in fonts if isinstance(f, str) and f.strip()]
        except Exception:
            self.recent_fonts = []

    def _push_recent_font(self, font_name: str):
        if not font_name:
            return
        self.recent_fonts = [f for f in self.recent_fonts if f != font_name]
        self.recent_fonts.insert(0, font_name)
        self.recent_fonts = self.recent_fonts[:12]
        self.update_recent_list()
        self.save_recent_fonts()

    def save_recent_fonts(self):
        """保存最近字体"""
        try:
            config_dir = Path.home() / ".config" / "批图王"
            config_dir.mkdir(parents=True, exist_ok=True)
            recent_file = config_dir / "recent_fonts.json"
            with open(recent_file, "w", encoding="utf-8") as f:
                json.dump({"recent": self.recent_fonts}, f, ensure_ascii=False, indent=2)
        except Exception:
            logger.warning("静默异常已忽略: except in ui/enhanced_font_selector.py", exc_info=True)
            pass

    def _font_display_name(self, font_name: str) -> str:
        cn_name = self.cn_names.get(font_name)
        if cn_name:
            return f"{cn_name} ({font_name})"
        return font_name

    def _font_match(self, font_name: str, query: str) -> bool:
        q = (query or "").strip().lower()
        if not q:
            return True
        display = self._font_display_name(font_name).lower()
        return q in font_name.lower() or q in display
