import copy
import uuid

from PySide6.QtCore import QObject, Signal


class LayerGroup(QObject):
    """Non-rendering layer folder used to organize adjacent layers."""

    changed = Signal()

    def __init__(self, name="图层组", visible=True, locked=False, expanded=True, group_id=None, parent=None):
        super().__init__(parent)
        self.group_id = str(group_id or uuid.uuid4())
        self._name = name
        self._visible = bool(visible)
        self._locked = bool(locked)
        self._expanded = bool(expanded)
        self.children = []

    @property
    def name(self):
        return self._name

    @name.setter
    def name(self, value):
        self._name = str(value or "图层组")
        self.changed.emit()

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = bool(value)
        self.changed.emit()

    @property
    def locked(self):
        return self._locked

    @locked.setter
    def locked(self, value):
        self._locked = bool(value)
        self.changed.emit()

    @property
    def expanded(self):
        return self._expanded

    @expanded.setter
    def expanded(self, value):
        self._expanded = bool(value)
        self.changed.emit()

    def serialize(self):
        return {
            "type": "group",
            "name": self.name,
            "visible": self.visible,
            "locked": self.locked,
            "expanded": self.expanded,
            "group_id": self.group_id,
            "children": [],
        }

    @classmethod
    def deserialize(cls, data, parent=None):
        return cls(
            name=data.get("name", "图层组"),
            visible=data.get("visible", True),
            locked=data.get("locked", False),
            expanded=data.get("expanded", True),
            group_id=data.get("group_id"),
            parent=parent,
        )

    def duplicate(self, parent=None):
        data = copy.deepcopy(self.serialize())
        data.pop("group_id", None)
        return self.deserialize(data, parent=parent)
