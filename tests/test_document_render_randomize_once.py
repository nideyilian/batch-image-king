"""回归测试：render_composition(random_mode=True) 只随机化一次。

历史版本在 document_render.py 的 render_composition 中先后执行了两次
randomize_all_layers()，导致随机模式下次次双重随机化。修复后必须只调用一次。
"""

from __future__ import annotations

import pytest

from app.models.document import Document
from app.models.layer_new import Layer

pytestmark = pytest.mark.integration


def test_render_composition_randomizes_layers_only_once(monkeypatch):
    doc = Document(parent=None)
    doc.create_new(200, 200)

    layer = Layer(parent=doc)
    layer.name = "图片"
    layer.x, layer.y, layer.width, layer.height = 0, 0, 100, 100
    doc.layers.append(layer)

    calls = {"n": 0}
    original = doc.randomize_all_layers

    def counting():
        # 先计数再调用原实现：即使原实现抛异常，计数也不丢失
        calls["n"] += 1
        return original()

    monkeypatch.setattr(doc, "randomize_all_layers", counting)

    try:
        doc.render_composition(
            random_mode=True,
            enable_gpu=False,
            use_advanced_quality=False,
        )
    except Exception:
        # 无真实图像源时渲染可能失败；本测试只关心随机化调用次数
        pass

    assert calls["n"] == 1, (
        f"randomize_all_layers 应只调用一次，实际调用 {calls['n']} 次（双重随机化回归）"
    )


def test_render_composition_random_mode_false_does_not_randomize(monkeypatch):
    doc = Document(parent=None)
    doc.create_new(200, 200)

    calls = {"n": 0}
    original = doc.randomize_all_layers

    def counting():
        calls["n"] += 1
        return original()

    monkeypatch.setattr(doc, "randomize_all_layers", counting)

    try:
        doc.render_composition(
            random_mode=False,
            enable_gpu=False,
            use_advanced_quality=False,
        )
    except Exception:
        pass

    assert calls["n"] == 0
