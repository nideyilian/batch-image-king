from __future__ import annotations

from typing import Optional

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Slot


class LayerListModel(QAbstractListModel):
    NameRole = Qt.UserRole + 1
    TypeNameRole = Qt.UserRole + 2
    GlyphRole = Qt.UserRole + 3
    AccentRole = Qt.UserRole + 4
    ShownRole = Qt.UserRole + 5
    LockedRole = Qt.UserRole + 6
    SelectedRole = Qt.UserRole + 7
    DepthRole = Qt.UserRole + 8
    IsGroupRole = Qt.UserRole + 9
    ExpandedRole = Qt.UserRole + 10
    ParentExpandedRole = Qt.UserRole + 11

    _ROLE_NAMES = {
        NameRole: QByteArray(b"name"),
        TypeNameRole: QByteArray(b"typeName"),
        GlyphRole: QByteArray(b"glyph"),
        AccentRole: QByteArray(b"accent"),
        ShownRole: QByteArray(b"shown"),
        LockedRole: QByteArray(b"locked"),
        SelectedRole: QByteArray(b"selected"),
        DepthRole: QByteArray(b"depth"),
        IsGroupRole: QByteArray(b"isGroup"),
        ExpandedRole: QByteArray(b"expanded"),
        ParentExpandedRole: QByteArray(b"parentExpanded"),
    }

    def __init__(self, document=None, parent=None) -> None:
        super().__init__(parent)
        self._document = None
        self.set_document(document)

    @property
    def document(self):
        return self._document

    def roleNames(self):  # noqa: N802 - Qt API
        return self._ROLE_NAMES

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 - Qt API
        if parent.isValid() or self._document is None:
            return 0
        return len(getattr(self._document, "layers", []))

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self._document is None:
            return None
        row = index.row()
        layers = getattr(self._document, "layers", [])
        if row < 0 or row >= len(layers):
            return None
        layer = layers[row]
        if role in (Qt.DisplayRole, self.NameRole):
            return str(getattr(layer, "name", "未命名图层"))
        if role == self.TypeNameRole:
            return self.layer_type_name(layer)
        if role == self.GlyphRole:
            return self.layer_glyph(layer)
        if role == self.AccentRole:
            return self.layer_accent(layer)
        if role == self.ShownRole:
            return bool(getattr(layer, "visible", True))
        if role == self.LockedRole:
            return bool(getattr(layer, "locked", False))
        if role == self.SelectedRole:
            return row in list(getattr(self._document, "selected_layer_indices", []) or [])
        if role == self.DepthRole:
            from app.utils.layer_tree import get_parent_group_id
            return 1 if get_parent_group_id(layer) else 0
        if role == self.IsGroupRole:
            from app.utils.layer_tree import is_layer_group
            return is_layer_group(layer)
        if role == self.ExpandedRole:
            return bool(getattr(layer, "expanded", True))
        if role == self.ParentExpandedRole:
            from app.utils.layer_tree import get_parent_group_id, group_map
            group_id = get_parent_group_id(layer)
            if not group_id:
                return True
            group = group_map(getattr(self._document, "layers", [])).get(group_id)
            return bool(getattr(group, "expanded", True)) if group is not None else True
        return None

    @staticmethod
    def layer_type_name(layer) -> str:
        from app.models.layer_group import LayerGroup
        from app.models.shaped_layer_new import ShapedLayer
        from app.models.text_layer import TextLayer

        if isinstance(layer, LayerGroup):
            return "图层组"
        if isinstance(layer, TextLayer):
            return "文字"
        if isinstance(layer, ShapedLayer):
            return "异形"
        return "图片"

    @classmethod
    def layer_glyph(cls, layer) -> str:
        type_name = cls.layer_type_name(layer)
        return {
            "图层组": "\uE8B0",
            "文字": "\uE8D2",
            "异形": "\uF158",
            "图片": "\uEB9F",
        }.get(type_name, "\uE91B")

    @classmethod
    def layer_accent(cls, layer) -> str:
        return {
            "图层组": "#8e9894",
            "文字": "#46d7ad",
            "异形": "#f1786d",
            "图片": "#b9c4c0",
        }.get(cls.layer_type_name(layer), "#8e9894")

    def set_document(self, document) -> None:
        if document is self._document:
            return
        self._disconnect_document()
        self.beginResetModel()
        self._document = document
        self.endResetModel()
        self._connect_document()

    def _connect_document(self) -> None:
        if self._document is None:
            return
        for signal_name in ("layer_changed", "layers_changed", "layers_selection_changed"):
            signal = getattr(self._document, signal_name, None)
            if signal is not None:
                signal.connect(self.reset_from_document)

    def _disconnect_document(self) -> None:
        if self._document is None:
            return
        for signal_name in ("layer_changed", "layers_changed", "layers_selection_changed"):
            signal = getattr(self._document, signal_name, None)
            if signal is not None:
                try:
                    signal.disconnect(self.reset_from_document)
                except (RuntimeError, TypeError):
                    pass

    @Slot()
    def reset_from_document(self) -> None:
        self.beginResetModel()
        self.endResetModel()

    def notify_row(self, row: int) -> None:
        if row < 0 or row >= self.rowCount():
            return
        model_index = self.index(row, 0)
        self.dataChanged.emit(model_index, model_index, list(self._ROLE_NAMES))

    def layer_at(self, row: int) -> Optional[object]:
        if self._document is None or row < 0 or row >= self.rowCount():
            return None
        return self._document.layers[row]
