"""Medium-size batch export stress coverage."""

from __future__ import annotations

import os
import tempfile

import pytest
from PIL import Image

from app.models.document import Document
from app.models.text_layer import TextLayer

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _make_assets(directory: str, prefix: str, count: int) -> str:
    os.makedirs(directory, exist_ok=True)
    for index in range(count):
        color = ((index * 41) % 255, (index * 67) % 255, (index * 89) % 255, 255)
        Image.new("RGBA", (64, 64), color).save(os.path.join(directory, f"{prefix}_{index:02d}.png"))
    return directory


def test_batch_export_medium_randomized_document_stress():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        assets_a = _make_assets(os.path.join(tmp, "a"), "a", 6)
        assets_b = _make_assets(os.path.join(tmp, "b"), "b", 5)
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)

        doc = Document()
        doc.canvas_width = 320
        doc.canvas_height = 220
        doc.add_layer("素材A", 10, 10, 96, 96, assets_a, use_original_size=False, is_folder=True)
        doc.add_layer("素材B", 150, 60, 96, 96, assets_b, use_original_size=False, is_folder=True)

        text_layer = TextLayer(name="随机文案", x=30, y=155, width=220, height=48)
        text_layer.text_binding_enabled = True
        text_layer.set_text_lines([f"文案 {i}" for i in range(8)])
        doc.add_text_layer(text_layer)

        ok = doc.batch_export(
            directory=out_dir,
            count=12,
            filename_template="stress_{number:03d}",
            file_format="png",
            use_high_performance=True,
            use_smart_sampling=True,
        )

        assert ok is True
        exported = sorted(name for name in os.listdir(out_dir) if name.endswith(".png"))
        assert len(exported) == 12
        assert exported[0] == "stress_001.png"
        assert exported[-1] == "stress_012.png"
        assert all(os.path.getsize(os.path.join(out_dir, name)) > 0 for name in exported)
