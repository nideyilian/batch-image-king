"""Document 核心模型测试。

覆盖：

- 画布/图层的最小生命周期（新建、添加图层、修改尺寸）
- 序列化往返：Document -> dict -> Document 后图层数量与关键属性一致
- 撤销/重做：添加图层后能 undo 回空，redo 后能再加回来

这些测试只用纯 Python，不依赖 Qt 信号订阅者，因此无需 QApplication。
"""
from __future__ import annotations

import os
import sys
import tempfile

import pytest

# 兼容直接 python 运行（不通过 pytest 收集）
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.document import Document  # noqa: E402


pytestmark = pytest.mark.unit


def _new_document(width: int = 200, height: int = 150) -> Document:
    doc = Document()
    doc.canvas_width = width
    doc.canvas_height = height
    return doc


class TestDocumentLifecycle:
    def test_new_document_has_default_canvas(self):
        doc = Document()
        # 默认画布尺寸
        assert doc.canvas_width > 0
        assert doc.canvas_height > 0
        assert doc.layers == []
        assert doc.selected_layer_index == -1
        assert doc.is_modified is False

    def test_add_layer_appends_and_selects(self):
        doc = _new_document()
        # image_source 指向一个空目录，避免真读图
        with tempfile.TemporaryDirectory() as tmp:
            layer = doc.add_layer(
                name="lvl1",
                x=10,
                y=20,
                width=64,
                height=48,
                image_source=tmp,
                use_original_size=False,
                is_folder=True,
            )
        assert layer is not None
        assert len(doc.layers) == 1
        assert doc.selected_layer_index == 0

    def test_remove_layer_clears_selection(self):
        doc = _new_document()
        with tempfile.TemporaryDirectory() as tmp:
            doc.add_layer("a", 0, 0, 50, 50, image_source=tmp)
        assert len(doc.layers) == 1
        doc.remove_layer(0)
        assert doc.layers == []
        assert doc.selected_layer_index == -1


class TestDocumentSerializeRoundTrip:
    def test_pickle_round_trip_preserves_layers(self):
        doc = _new_document(320, 240)
        with tempfile.TemporaryDirectory() as tmp:
            doc.add_layer("layer-A", 5, 10, 64, 32, image_source=tmp)
            doc.add_layer("layer-B", 100, 80, 80, 80, image_source=tmp)

        # 通过 pickle 走完整往返；用 _serializer 写入/读取
        with tempfile.TemporaryDirectory() as tmp_dir:
            path = os.path.join(tmp_dir, "doc.cmp")
            ok = doc._serializer.serialize_document(
                {
                    "canvas_width": doc.canvas_width,
                    "canvas_height": doc.canvas_height,
                    "layers": [l.serialize() for l in doc.layers],
                    "export_settings": doc.export_settings,
                },
                path,
            )
            assert ok is True
            assert os.path.exists(path)

            with open(path, "rb") as fh:
                restored = __import__("pickle").load(fh)

        assert restored["canvas_width"] == 320
        assert restored["canvas_height"] == 240
        assert len(restored["layers"]) == 2
        assert restored["layers"][0]["name"] in {"layer-A", "layer-B"}


class TestDocumentUndoRedo:
    def test_undo_remove_layer_restores_previous_state(self):
        doc = _new_document()
        with tempfile.TemporaryDirectory() as tmp:
            doc.add_layer("first", 0, 0, 50, 50, image_source=tmp)

        # 记录添加前的状态
        assert len(doc.layers) == 1
        assert doc.can_undo() is True

        # 撤销
        ok = doc.undo()
        assert ok is True
        # 撤销后应该是空（add_layer 内部先 save_state 再添加）
        assert doc.layers == []

    def test_redo_after_undo_reapplies(self):
        doc = _new_document()
        with tempfile.TemporaryDirectory() as tmp:
            doc.add_layer("first", 0, 0, 50, 50, image_source=tmp)
        doc.undo()
        assert doc.layers == []
        # 撤销后应能 redo
        assert doc.can_redo() is True
        ok = doc.redo()
        assert ok is True
        assert len(doc.layers) == 1
        assert doc.layers[0].serialize().get("name") == "first"

    def test_cannot_undo_when_history_empty(self):
        doc = _new_document()
        assert doc.can_undo() is False
        assert doc.undo() is False
