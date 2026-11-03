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
    LayerIndexRole = Qt.UserRole + 12
    IconNameRole = Qt.UserRole + 13

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
        LayerIndexRole: QByteArray(b"layerIndex"),
        IconNameRole: QByteArray(b"iconName"),
    }

    def __init__(self, document=None, parent=None) -> None:
        super().__init__(parent)
        self._document = None
        # 上一次同步时的「行结构指纹」：((layer_index, depth), ...)。
        # 用来区分「只是属性变了」和「行数/顺序变了」—— 前者不该重建 delegate。
        self._last_structure: tuple = ()
        self.set_document(document)

    @property
    def document(self):
        return self._document

    def roleNames(self):  # noqa: N802 - Qt API
        return self._ROLE_NAMES

    def rowCount(self, parent=QModelIndex()):  # noqa: N802 - Qt API
        if parent.isValid() or self._document is None:
            return 0
        return len(self._display_entries())

    def _display_entries(self):
        if self._document is None:
            return []
        from app.utils.layer_tree import display_entries

        return display_entries(getattr(self._document, "layers", []))

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or self._document is None:
            return None
        row = index.row()
        entries = self._display_entries()
        if row < 0 or row >= len(entries):
            return None
        layer_index, layer, depth = entries[row]
        if role in (Qt.DisplayRole, self.NameRole):
            return str(getattr(layer, "name", "未命名图层"))
        if role == self.TypeNameRole:
            return self.layer_type_name(layer)
        if role == self.GlyphRole:
            return self.layer_glyph(layer)
        if role == self.IconNameRole:
            return self.layer_icon_name(layer)
        if role == self.AccentRole:
            return self.layer_accent(layer)
        if role == self.ShownRole:
            return bool(getattr(layer, "visible", True))
        if role == self.LockedRole:
            return bool(getattr(layer, "locked", False))
        if role == self.SelectedRole:
            return layer_index in list(getattr(self._document, "selected_layer_indices", []) or [])
        if role == self.DepthRole:
            return depth
        if role == self.IsGroupRole:
            from app.utils.layer_tree import is_layer_group
            return is_layer_group(layer)
        if role == self.ExpandedRole:
            return bool(getattr(layer, "expanded", True))
        if role == self.ParentExpandedRole:
            return True
        if role == self.LayerIndexRole:
            return layer_index
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
    def layer_icon_name(cls, layer) -> str:
        return {
            "图层组": "group",
            "文字": "type",
            "异形": "shapes",
            "图片": "image",
        }.get(cls.layer_type_name(layer), "circle-help")

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
        self._last_structure = self._structure_signature()
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

    def _structure_signature(self) -> tuple:
        """当前行结构指纹：(稳定图层 ID, 层级深度) 序列。

        ⚠️ 必须用 ``_layer_id`` 而不是文档里的索引。
        索引是「枚举位置」：把第 3 层移到顶层后，顶层那条记录的索引仍然是 0..N-1
        的一个值，用 (index, depth) 做指纹会认为「什么都没变」——
        实测正是如此（上移一层没触发任何刷新，面板显示与实际顺序脱节）。
        ``_layer_id`` 是图层自己的 uuid，跟着图层走，顺序变化必然反映到序列上。

        也不含名字/可见性/锁定/选中态：这些改了只需要 dataChanged，不需要重建 delegate。
        """
        try:
            return tuple(
                (str(getattr(layer, "_layer_id", id(layer))), depth)
                for _index, layer, depth in self._display_entries()
            )
        except Exception:
            return ()

    @Slot()
    def reset_from_document(self) -> None:
        """文档结构变化时同步模型。

        🔴 历史行为（已修）：无脑 ``beginResetModel/endResetModel``。
        ``_connect_document`` 把它挂在了 ``layer_changed`` 上，而
        ``_finish_arrangement``（每一次图层增删/排序/对齐/编组都会走）既发
        ``layer_changed`` 又自己调了一次 ``reset_from_document`` —— 等于一次排序
        触发两轮全表重建。QML 会把所有 delegate 销毁重建，
        用户看到的就是图层面板整块闪一下，滚动位置也会被打断。

        现在按结构指纹分流：
        - 行数/顺序/层级没变（改名、显隐、锁定、选中、透明度…）→ 只发 dataChanged，
          delegate 原地更新，不动其它行；
        - 结构真的变了 → 才 reset。
        """
        structure = self._structure_signature()
        if structure == self._last_structure:
            row_count = len(structure)
            if row_count:
                self.dataChanged.emit(
                    self.index(0, 0),
                    self.index(row_count - 1, 0),
                    list(self._ROLE_NAMES),
                )
            return
        self.beginResetModel()
        self._last_structure = structure
        self.endResetModel()

    def notify_row(self, row: int) -> None:
        display_row = next(
            (
                display_index
                for display_index, (layer_index, _layer, _depth) in enumerate(self._display_entries())
                if layer_index == row
            ),
            -1,
        )
        if display_row < 0:
            return
        model_index = self.index(display_row, 0)
        self.dataChanged.emit(model_index, model_index, list(self._ROLE_NAMES))

    def layer_at(self, row: int) -> Optional[object]:
        if self._document is None or row < 0 or row >= self.rowCount():
            return None
        return self._document.layers[row]
