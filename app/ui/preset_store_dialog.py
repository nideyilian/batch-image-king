import os
import datetime

from PySide6.QtWidgets import (
    QDialog, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QLineEdit,
    QComboBox, QScrollArea, QFrame, QMenu, QMessageBox, QFileDialog, QInputDialog,
    QSizePolicy
)
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap

from app.ui.preset_manager_dialog import PresetSaveDialog
from app.ui.preset_run_dialog import PresetRunDialog
from app.utils.preset_manager import PresetManager
from app.utils.preset_thumbnail_service import PresetThumbnailService


CARD_WIDTH = 236


class PresetCardWidget(QFrame):
    edit_requested = Signal(str)
    run_requested = Signal(str)
    export_requested = Signal(str)
    delete_requested = Signal(str)
    duplicate_requested = Signal(str)
    rename_requested = Signal(str)
    open_folder_requested = Signal(str)

    def __init__(self, summary, thumbnail_path, parent=None):
        super().__init__(parent)
        self.summary = summary
        self.preset_id = summary.get('id', '')
        self.setFixedWidth(CARD_WIDTH)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Maximum)
        self.setObjectName("PresetCard")
        self.setStyleSheet("""
            QFrame#PresetCard {
                background-color: #252B33;
                border: 1px solid #3A424D;
                border-radius: 8px;
            }
            QFrame#PresetCard:hover {
                border-color: #5D6B7C;
            }
            QLabel#MetaLabel {
                color: #9AA6B2;
                font-size: 12px;
            }
            QPushButton {
                padding: 5px 8px;
            }
        """)
        self.setup_ui(thumbnail_path)

    def setup_ui(self, thumbnail_path):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        self.thumbnail = QLabel()
        self.thumbnail.setFixedSize(CARD_WIDTH - 20, CARD_WIDTH - 20)
        self.thumbnail.setAlignment(Qt.AlignCenter)
        self.thumbnail.setStyleSheet("background-color: #1D2229; border-radius: 6px;")
        if thumbnail_path and os.path.exists(thumbnail_path):
            pixmap = QPixmap(thumbnail_path)
            self.thumbnail.setPixmap(pixmap.scaled(self.thumbnail.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        else:
            self.thumbnail.setText("无缩略图")
        layout.addWidget(self.thumbnail)

        name = QLabel(self.summary.get('name', '未命名预设'))
        name.setWordWrap(True)
        name.setStyleSheet("font-weight: bold; font-size: 14px; color: #EEF2F6;")
        layout.addWidget(name)

        description = QLabel(self.summary.get('description', '') or "暂无描述")
        description.setWordWrap(True)
        description.setMaximumHeight(44)
        description.setObjectName("MetaLabel")
        layout.addWidget(description)

        meta = QLabel(self._meta_text())
        meta.setWordWrap(True)
        meta.setObjectName("MetaLabel")
        layout.addWidget(meta)

        actions = QHBoxLayout()
        edit_btn = QPushButton("编辑")
        edit_btn.clicked.connect(lambda: self.edit_requested.emit(self.preset_id))
        run_btn = QPushButton("运行")
        run_btn.setStyleSheet("background-color: #2F8F5B; color: white; font-weight: bold;")
        run_btn.clicked.connect(lambda: self.run_requested.emit(self.preset_id))
        more_btn = QPushButton("更多")
        more_btn.clicked.connect(self.show_more_menu)
        actions.addWidget(edit_btn)
        actions.addWidget(run_btn)
        actions.addWidget(more_btn)
        layout.addLayout(actions)

    def show_more_menu(self):
        menu = QMenu(self)
        rename_action = menu.addAction("重命名")
        duplicate_action = menu.addAction("复制预设")
        export_action = menu.addAction("导出预设")
        folder_action = menu.addAction("打开所在目录")
        menu.addSeparator()
        delete_action = menu.addAction("删除预设")
        chosen = menu.exec_(self.mapToGlobal(self.rect().bottomRight()))
        if chosen == rename_action:
            self.rename_requested.emit(self.preset_id)
        elif chosen == duplicate_action:
            self.duplicate_requested.emit(self.preset_id)
        elif chosen == export_action:
            self.export_requested.emit(self.preset_id)
        elif chosen == folder_action:
            self.open_folder_requested.emit(self.preset_id)
        elif chosen == delete_action:
            self.delete_requested.emit(self.preset_id)

    def _meta_text(self):
        doc_count = self.summary.get('document_count', 0)
        sizes = " / ".join(self.summary.get('canvas_sizes', [])[:2]) or "未知尺寸"
        modified = self._date_text(self.summary.get('modified_at', ''))
        runs = int(self.summary.get('run_count') or 0)
        return f"{doc_count} 个标签页 | {sizes}\n修改 {modified} | 运行 {runs} 次"

    def _date_text(self, value):
        if not value:
            return "未知"
        try:
            return datetime.datetime.fromisoformat(value).strftime("%Y-%m-%d")
        except Exception:
            return str(value).split("T")[0]


class MasonryPresetGrid(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cards = []
        self.column_layouts = []
        self._reflowing = False
        self.main_layout = QHBoxLayout(self)
        self.main_layout.setContentsMargins(14, 14, 14, 14)
        self.main_layout.setSpacing(14)

    def set_cards(self, cards):
        self._reflowing = True
        try:
            self._clear_columns(delete_cards=True)
            self.cards = cards
        finally:
            self._reflowing = False
        self.reflow()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.reflow()

    def reflow(self):
        if self._reflowing:
            return
        self._reflowing = True
        try:
            self._reflow()
        finally:
            self._reflowing = False

    def _reflow(self):
        self._clear_columns(delete_cards=False)
        available = max(self.width(), CARD_WIDTH)
        column_count = max(1, available // (CARD_WIDTH + 14))
        heights = [0] * column_count

        for _ in range(column_count):
            column_widget = QWidget()
            column_widget.setFixedWidth(CARD_WIDTH)
            column_widget.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.MinimumExpanding)
            column_layout = QVBoxLayout(column_widget)
            column_layout.setContentsMargins(0, 0, 0, 0)
            column_layout.setSpacing(14)
            column_layout.addStretch()
            self.main_layout.addWidget(column_widget)
            self.column_layouts.append(column_layout)

        for card in self.cards:
            column_index = min(range(column_count), key=lambda idx: heights[idx])
            layout = self.column_layouts[column_index]
            layout.insertWidget(layout.count() - 1, card)
            card.setVisible(True)
            heights[column_index] += card.sizeHint().height() + 14

        self.main_layout.addStretch()
        content_height = max(heights) + self.main_layout.contentsMargins().top() + self.main_layout.contentsMargins().bottom()
        self.setMinimumHeight(max(1, content_height))
        self.adjustSize()
        self.updateGeometry()
        self.update()

    def _clear_columns(self, delete_cards=False):
        for column_layout in self.column_layouts:
            while column_layout.count():
                item = column_layout.takeAt(0)
                widget = item.widget()
                if widget:
                    if delete_cards:
                        widget.deleteLater()
                    else:
                        widget.setParent(None)

        while self.main_layout.count():
            item = self.main_layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()
        self.column_layouts = []


class PresetStoreDialog(QDialog):
    preset_edit_requested = Signal(str)

    def __init__(self, main_window=None, parent=None):
        super().__init__(parent)
        self.main_window = main_window
        self.preset_manager = getattr(main_window, 'preset_manager', None) or PresetManager()
        self.thumbnail_service = PresetThumbnailService(self.preset_manager)
        self.all_summaries = []

        self.setWindowTitle("预设中心")
        self.setMinimumSize(980, 680)
        self.setup_ui()
        self.refresh_presets()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(10)

        header = QHBoxLayout()
        title = QLabel("预设中心")
        title.setStyleSheet("font-size: 22px; font-weight: bold;")
        header.addWidget(title)
        header.addStretch()
        save_btn = QPushButton("保存当前为预设")
        save_btn.clicked.connect(self.save_current_tabs)
        import_btn = QPushButton("导入")
        import_btn.clicked.connect(self.import_preset)
        export_all_btn = QPushButton("导出合集")
        export_all_btn.clicked.connect(self.export_all_presets)
        header.addWidget(save_btn)
        header.addWidget(import_btn)
        header.addWidget(export_all_btn)
        layout.addLayout(header)

        filters = QHBoxLayout()
        self.search_edit = QLineEdit()
        self.search_edit.setPlaceholderText("搜索预设名称、描述或标签...")
        self.search_edit.textChanged.connect(self.apply_filters)
        self.type_combo = QComboBox()
        self.type_combo.addItem("全部类型", "all")
        self.type_combo.addItem("单文档", "single_document")
        self.type_combo.addItem("多标签页", "multi_document")
        self.type_combo.currentIndexChanged.connect(self.apply_filters)
        self.sort_combo = QComboBox()
        self.sort_combo.addItem("最近创建", "created")
        self.sort_combo.addItem("最近修改", "modified")
        self.sort_combo.addItem("最近运行", "used")
        self.sort_combo.addItem("运行次数", "runs")
        self.sort_combo.addItem("名称", "name")
        self.sort_combo.currentIndexChanged.connect(self.apply_filters)
        filters.addWidget(self.search_edit, 1)
        filters.addWidget(self.type_combo)
        filters.addWidget(self.sort_combo)
        layout.addLayout(filters)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.grid = MasonryPresetGrid()
        self.scroll_area.setWidget(self.grid)
        layout.addWidget(self.scroll_area, 1)

        self.empty_widget = QWidget()
        empty_layout = QVBoxLayout(self.empty_widget)
        empty_layout.setAlignment(Qt.AlignCenter)
        empty_title = QLabel("还没有预设")
        empty_title.setAlignment(Qt.AlignCenter)
        empty_title.setStyleSheet("font-size: 18px; font-weight: bold; color: #EEF2F6;")
        empty_desc = QLabel("保存当前标签页为预设，或导入已有预设合集。")
        empty_desc.setAlignment(Qt.AlignCenter)
        empty_desc.setStyleSheet("color: #9AA6B2;")
        empty_actions = QHBoxLayout()
        empty_save = QPushButton("保存当前为预设")
        empty_save.clicked.connect(self.save_current_tabs)
        empty_import = QPushButton("导入预设")
        empty_import.clicked.connect(self.import_preset)
        empty_actions.addWidget(empty_save)
        empty_actions.addWidget(empty_import)
        empty_layout.addWidget(empty_title)
        empty_layout.addWidget(empty_desc)
        empty_layout.addLayout(empty_actions)
        layout.addWidget(self.empty_widget, 1)
        self.empty_widget.hide()

        bottom = QHBoxLayout()
        bottom.addStretch()
        close_btn = QPushButton("关闭")
        close_btn.clicked.connect(self.reject)
        bottom.addWidget(close_btn)
        layout.addLayout(bottom)

    def refresh_presets(self):
        self.all_summaries = []
        for preset in self.preset_manager.get_all_presets():
            summary = self.preset_manager.get_preset_summary(preset.get('id'))
            if summary:
                self.all_summaries.append(summary)
        self.apply_filters()

    def apply_filters(self):
        text = self.search_edit.text().strip().lower()
        type_filter = self.type_combo.currentData()
        summaries = []
        for summary in self.all_summaries:
            haystack = " ".join([
                summary.get('name', ''),
                summary.get('description', ''),
                " ".join(summary.get('tags', []) or []),
            ]).lower()
            if text and text not in haystack:
                continue
            if type_filter != "all" and summary.get('type') != type_filter:
                continue
            summaries.append(summary)

        sort_key = self.sort_combo.currentData()
        reverse = sort_key != "name"
        key_map = {
            "created": lambda s: s.get('created_at', ''),
            "modified": lambda s: s.get('modified_at', ''),
            "used": lambda s: s.get('last_used_at', ''),
            "runs": lambda s: int(s.get('run_count') or 0),
            "name": lambda s: s.get('name', ''),
        }
        summaries.sort(key=key_map.get(sort_key, key_map["created"]), reverse=reverse)
        self.render_cards(summaries)

    def render_cards(self, summaries):
        cards = []
        for summary in summaries:
            thumb = self.thumbnail_service.get_thumbnail_path(summary.get('id'))
            card = PresetCardWidget(summary, thumb)
            card.edit_requested.connect(self.edit_preset)
            card.run_requested.connect(self.run_preset)
            card.export_requested.connect(self.export_preset)
            card.delete_requested.connect(self.delete_preset)
            card.duplicate_requested.connect(self.duplicate_preset)
            card.rename_requested.connect(self.rename_preset)
            card.open_folder_requested.connect(self.open_preset_folder)
            cards.append(card)
        self.grid.set_cards(cards)
        has_cards = bool(cards)
        self.scroll_area.setVisible(has_cards)
        self.empty_widget.setVisible(not has_cards)
        if has_cards:
            self.grid.updateGeometry()
            self.grid.repaint()
            self.scroll_area.viewport().update()

    def edit_preset(self, preset_id):
        self.preset_edit_requested.emit(preset_id)

    def run_preset(self, preset_id):
        dialog = PresetRunDialog(self.preset_manager, preset_id, self)
        if dialog.exec() == QDialog.Accepted:
            dialog.run_exports()
            self.refresh_presets()

    def save_current_tabs(self):
        if not self.main_window or self.main_window.tab_widget.count() == 0:
            QMessageBox.warning(self, "保存预设", "没有打开的标签页")
            return
        dialog = PresetSaveDialog(self.main_window, self)
        if dialog.exec() != QDialog.Accepted:
            return
        info = dialog.get_preset_info()
        selected_tabs = dialog.get_selected_tabs()
        documents = []
        for tab_index in selected_tabs:
            if hasattr(self.main_window, '_sync_document_view_settings_from_tab'):
                self.main_window._sync_document_view_settings_from_tab(tab_index)
            doc = self.main_window.document_manager.get_document(tab_index)
            if doc:
                tab_name = self.main_window.tab_widget.tabText(tab_index)
                if tab_name.endswith(" *"):
                    tab_name = tab_name[:-2]
                doc.tab_name = tab_name
                doc.original_tab_name = tab_name
                documents.append(doc)
        global_settings = self.main_window.get_global_settings() if hasattr(self.main_window, 'get_global_settings') else {}
        result = self.preset_manager.save_preset_documents(
            info["name"],
            info["description"],
            documents,
            global_settings
        )
        if isinstance(result, dict) and result.get("duplicate"):
            if QMessageBox.question(self, "预设名称已存在", f"已存在名为 '{result['name']}' 的预设，是否更新？") == QMessageBox.Yes:
                self.preset_manager.delete_preset(result["existing_id"])
                result = self.preset_manager.save_preset_documents(info["name"], info["description"], documents, global_settings)
            else:
                return
        if result:
            self.refresh_presets()
            QMessageBox.information(self, "保存预设", "预设已保存。")
        else:
            QMessageBox.warning(self, "保存预设", "保存预设失败。")

    def rename_preset(self, preset_id):
        summary = self.preset_manager.get_preset_summary(preset_id) or {}
        new_name, ok = QInputDialog.getText(self, "重命名预设", "输入新名称:", text=summary.get('name', ''))
        if ok and new_name.strip():
            if self.preset_manager.update_preset(preset_id, name=new_name.strip()):
                self.refresh_presets()

    def duplicate_preset(self, preset_id):
        new_id = self.preset_manager.duplicate_preset(preset_id)
        if new_id:
            self.refresh_presets()
        else:
            QMessageBox.warning(self, "复制预设", "复制预设失败。")

    def delete_preset(self, preset_id):
        summary = self.preset_manager.get_preset_summary(preset_id) or {}
        name = summary.get('name', '该预设')
        if QMessageBox.question(self, "删除预设", f"确定要删除 '{name}' 吗？此操作无法撤销。") != QMessageBox.Yes:
            return
        if self.preset_manager.delete_preset(preset_id):
            self.refresh_presets()
        else:
            QMessageBox.warning(self, "删除预设", "删除预设失败。")

    def export_preset(self, preset_id):
        summary = self.preset_manager.get_preset_summary(preset_id) or {}
        default_name = f"{summary.get('name', 'preset')}.preset"
        path, _ = QFileDialog.getSaveFileName(self, "导出预设", default_name, "预设文件 (*.preset *.pst);;所有文件 (*)")
        if not path:
            return
        if not path.lower().endswith(('.preset', '.pst')):
            path += '.preset'
        if not self.preset_manager.export_preset(preset_id, path):
            QMessageBox.warning(self, "导出预设", "导出预设失败。")

    def import_preset(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入预设", "", "预设文件 (*.preset *.pst);;所有文件 (*)")
        if not path:
            return
        preset_id = self.preset_manager.import_preset(path)
        if preset_id:
            self.refresh_presets()
        else:
            QMessageBox.warning(self, "导入预设", "导入预设失败，文件可能已损坏或格式不正确。")

    def export_all_presets(self):
        path, _ = QFileDialog.getSaveFileName(self, "导出预设合集", "预设合集.preset", "预设合集文件 (*.preset);;所有文件 (*)")
        if not path:
            return
        if not path.lower().endswith('.preset'):
            path += '.preset'
        count = self.preset_manager.export_all_presets(path)
        if count <= 0:
            QMessageBox.warning(self, "导出合集", "没有可导出的预设。")

    def open_preset_folder(self, preset_id):
        folder = self.preset_manager.get_presets_dir()
        if os.path.isdir(folder):
            os.startfile(folder)
