"""序列化收敛回归测试：预设应用与 .cmp 打开必须走同一套恢复逻辑。

历史问题：预设应用路径（create_document_from_preset_data -> create_layer_from_data）
逐条扁平创建图层，不处理分组 children 递归结构，导致带分组的文档应用预设时
组内子图层全部丢失（document_serializer 的 restore_document_data 无此问题）。
"""

from __future__ import annotations

import pickle
from pathlib import Path

import pytest

from app.models.document import Document
from app.models.document_serializer import DocumentSerializer
from app.models.layer_group import LayerGroup
from app.models.layer_new import Layer
from app.utils.preset_document_loader import (
    create_document_from_preset_data,
    documents_from_preset_data,
)
from app.utils.preset_manager import PresetManager

pytestmark = pytest.mark.integration


def _build_grouped_document() -> Document:
    """文档：组A（含子1、子2）+ 顶层图层。"""
    doc = Document(parent=None)
    doc.create_new(400, 300)

    grp = LayerGroup(parent=doc)
    grp.name = "组A"
    doc.layers.append(grp)

    def mk(name, x):
        layer = Layer(parent=doc)
        layer.name = name
        layer.x, layer.y, layer.width, layer.height = x, 0, 50, 50
        return layer

    c1 = mk("子1", 10)
    c1.parent_group_id = grp.group_id
    c2 = mk("子2", 70)
    c2.parent_group_id = grp.group_id
    top = mk("顶层", 200)
    doc.layers.extend([c1, c2, top])
    return doc


def _count_grouped_layers(doc) -> int:
    """统计带 parent_group_id 的分组子图层（扁平列表语义）。"""
    return sum(1 for layer in doc.layers if getattr(layer, "parent_group_id", None))


def test_preset_apply_preserves_layer_group_children():
    """核心回归：预设应用路径不得丢失分组内子图层。"""
    doc = _build_grouped_document()
    data = DocumentSerializer.prepare_document_data(doc)

    restored = create_document_from_preset_data(data, parent=None)
    assert len(restored.layers) == 4, f"应恢复 4 个图层，实际 {len(restored.layers)}"
    assert _count_grouped_layers(restored) == 2, "组内子图层丢失（P2-10 回归）"
    names = {getattr(layer, "name", "") for layer in restored.layers}
    assert {"组A", "子1", "子2", "顶层"} <= names


def test_preset_restore_matches_cmp_open_path():
    """两条恢复路径必须产出等价的图层结构。"""
    doc = _build_grouped_document()
    data = DocumentSerializer.prepare_document_data(doc)

    via_cmp = Document(parent=None)
    via_cmp.create_new(400, 300)
    assert DocumentSerializer.restore_document_data(via_cmp, data)

    via_preset = create_document_from_preset_data(data, parent=None)

    def snapshot(d):
        return [
            (type(layer).__name__, getattr(layer, "name", ""), getattr(layer, "parent_group_id", None))
            for layer in d.layers
        ]

    assert snapshot(via_preset) == snapshot(via_cmp)


def test_single_document_preset_roundtrip(tmp_path: Path):
    """单文档预设：save -> load(trusted pickle) -> restore，字段不丢失。"""
    doc = _build_grouped_document()
    doc.export_settings["file_format"] = "png"
    doc.set_view_settings({"zoom": 1.5})
    doc.selected_layer_index = 2

    pm = PresetManager(app_dir=str(tmp_path / "appdata"), copy_initial=False)
    preset_id = pm.save_preset_from_document("往返单文档", doc)
    assert preset_id

    preset_data = pm.load_preset(preset_id)
    documents = documents_from_preset_data(preset_data, parent=None)
    assert len(documents) == 1
    restored = documents[0]

    assert (restored.canvas_width, restored.canvas_height) == (400, 300)
    assert restored.export_settings.get("file_format") == "png"
    assert restored.selected_layer_index == 2
    assert len(restored.layers) == 4
    assert _count_grouped_layers(restored) == 2


def test_multi_document_preset_roundtrip(tmp_path: Path):
    """多文档预设包装结构：documents 列表内每个文档同样保留分组层级。"""
    pm = PresetManager(app_dir=str(tmp_path / "appdata"), copy_initial=False)
    docs = [_build_grouped_document(), _build_grouped_document()]
    preset_id = pm.save_preset_documents("往返多文档", "desc", docs)
    assert preset_id

    preset_data = pm.load_preset(preset_id)
    assert isinstance(preset_data.get("documents"), list)

    documents = documents_from_preset_data(preset_data, parent=None)
    assert len(documents) == 2
    for restored in documents:
        assert len(restored.layers) == 4
        assert _count_grouped_layers(restored) == 2


def test_document_data_restores_via_trusted_pickle_roundtrip(tmp_path: Path):
    """prepare_document_data 产出经受限反序列化后仍可完整恢复。"""
    from app.utils.trusted_pickle import load_trusted_pickle

    doc = _build_grouped_document()
    data = DocumentSerializer.prepare_document_data(doc)

    path = tmp_path / "doc.cmp"
    with open(path, "wb") as f:
        pickle.dump(data, f)
    with open(path, "rb") as f:
        loaded = load_trusted_pickle(f, str(path))

    restored = create_document_from_preset_data(loaded, parent=None)
    assert len(restored.layers) == 4
    assert _count_grouped_layers(restored) == 2
