"""trusted_pickle 受限反序列化安全测试。

验证目标：
1. 经典 pickle RCE 载荷（os.system / builtins.eval / getattr / __import__ /
   subprocess.Popen 等）必须被 RestrictedUnpickler 拒绝。
2. 合法的应用数据（原始类型容器 + app.* 枚举 + 标准库安全类型）必须正常加载。
3. 真实文档/预设往返在受限加载器下不回归。
"""

from __future__ import annotations

import datetime
import io
import pickle
from collections import OrderedDict
from pathlib import Path

import pytest

from app.utils.trusted_pickle import RestrictedUnpickler, load_trusted_pickle


def _global_bytes(module: str, name: str) -> bytes:
    """构造一个仅含 GLOBAL 引用的最小 pickle 载荷（不执行任何代码）。"""
    # PROTO(2) + GLOBAL(module\\nname\\n) + STOP
    return b"\x80\x02c" + module.encode("utf-8") + b"\n" + name.encode("utf-8") + b"\n."


def _loads_restricted(payload: bytes):
    return RestrictedUnpickler(io.BytesIO(payload)).load()


@pytest.mark.unit
@pytest.mark.parametrize(
    "module,name",
    [
        ("os", "system"),
        ("os", "popen"),
        ("posix", "system"),
        ("nt", "system"),
        ("subprocess", "Popen"),
        ("subprocess", "call"),
        ("builtins", "eval"),
        ("builtins", "exec"),
        ("builtins", "__import__"),
        ("builtins", "getattr"),
        ("builtins", "open"),
        ("builtins", "compile"),
        ("builtins", "globals"),
        ("builtins", "locals"),
        ("builtins", "vars"),
        ("sys", "modules"),
        ("shutil", "rmtree"),
        ("pathlib", "Path"),
    ],
)
def test_malicious_global_rejected(module, name):
    with pytest.raises(pickle.UnpicklingError):
        _loads_restricted(_global_bytes(module, name))


@pytest.mark.unit
def test_safe_primitives_and_app_classes_accepted():
    # 纯内置容器类型
    assert _loads_restricted(_global_bytes("builtins", "dict")) is dict
    assert _loads_restricted(_global_bytes("builtins", "list")) is list
    assert _loads_restricted(_global_bytes("builtins", "tuple")) is tuple
    # app.* 命名空间（ShapeType 是 .cmp 实际引用的枚举）
    from app.models.layer_properties import ShapeType

    assert _loads_restricted(_global_bytes("app.models.layer_properties", "ShapeType")) is ShapeType


@pytest.mark.unit
def test_legitimate_data_round_trip_through_restricted_loader():
    from app.models.layer_properties import ShapeType

    payload = {
        "canvas_width": 800,
        "canvas_height": 600,
        "layers": [
            {
                "name": "图片图层1",
                "x": 10,
                "y": 20,
                "width": 300,
                "height": 200,
                "opacity": 0.8,
                "blend_mode": 4,
            },
            {
                "name": "异形1",
                "shape_type": ShapeType.RECTANGLE,
            },
        ],
        "export_settings": OrderedDict(
            [
                ("file_format", "png"),
                ("created_at", datetime.datetime(2026, 8, 14, 10, 30)),
            ]
        ),
        "tags": frozenset({"batch", "demo"}),
    }
    buf = io.BytesIO()
    pickle.dump(payload, buf)
    buf.seek(0)
    loaded = RestrictedUnpickler(buf).load()
    assert loaded["canvas_width"] == 800
    assert loaded["layers"][1]["shape_type"] is ShapeType.RECTANGLE
    assert isinstance(loaded["export_settings"], OrderedDict)
    assert loaded["export_settings"]["created_at"] == datetime.datetime(2026, 8, 14, 10, 30)


@pytest.mark.integration
def test_document_round_trip_via_load_trusted_pickle(tmp_path: Path):
    """真实文档序列化后必须能被受限加载器读回（图层数/字段不丢失）。"""
    import tempfile

    from app.models.document import Document
    from app.models.document_serializer import DocumentSerializer
    from app.models.layer_new import Layer
    from app.models.shaped_layer_new import ShapedLayer
    from app.models.text_layer import TextLayer

    doc = Document(parent=None)
    doc.create_new(800, 600)

    def attach(layer):
        try:
            layer.changed.connect(doc.document_changed.emit)
        except Exception:
            pass
        doc.layers.append(layer)

    img = Layer(parent=doc)
    img.name = "图片图层1"
    img.x, img.y, img.width, img.height = 10, 20, 300, 200
    img.blend_mode = 4
    img.opacity = 0.8
    attach(img)

    txt = TextLayer(parent=doc)
    txt.text = "第一行\n第二行"
    txt.font_size = 36
    txt.stroke_enabled = True
    txt.stroke_width = 3
    attach(txt)

    shp = ShapedLayer(parent=doc)
    shp.name = "异形1"
    attach(shp)

    data = DocumentSerializer.prepare_document_data(doc)
    path = tmp_path / "roundtrip.cmp"
    with open(path, "wb") as f:
        pickle.dump(data, f)

    with open(path, "rb") as f:
        loaded = load_trusted_pickle(f, str(path))

    assert loaded["canvas_width"] == 800
    assert loaded["canvas_height"] == 600
    assert len(loaded["layers"]) == 3
    names = [layer.get("name") for layer in loaded["layers"]]
    assert "图片图层1" in names
    assert "异形1" in names


@pytest.mark.integration
def test_bundled_initial_preset_loads(tmp_path: Path):
    """仓库自带的初始 presets 文件必须能被受限加载器读回。"""
    repo_root = Path(__file__).resolve().parents[1]
    preset_path = repo_root / "presets"
    if not preset_path.exists():
        pytest.skip("仓库缺少初始 presets 文件")
    with open(preset_path, "rb") as f:
        data = load_trusted_pickle(f, str(preset_path))
    assert isinstance(data, dict)
    assert data.get("canvas_width") or "layers" in data
