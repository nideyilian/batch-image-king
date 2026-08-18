"""Automated replacement for the manual desktop smoke checklist."""

from __future__ import annotations

import os
import tempfile

import pytest
from PIL import Image

from app.models.document import Document
from app.models.layer_properties import ShapeType
from app.models.shaped_layer_new import ShapedLayer
from app.models.text_layer import TextLayer

pytestmark = pytest.mark.integration


def _make_source_image(path: str, color=(32, 144, 220, 255), size=(96, 72)) -> str:
    Image.new("RGBA", size, color).save(path)
    return path


def test_manual_workflow_create_save_load_export_and_batch():
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        src = _make_source_image(os.path.join(tmp, "source.png"))
        doc_path = os.path.join(tmp, "workflow.cmp")
        single_out = os.path.join(tmp, "single.png")
        batch_dir = os.path.join(tmp, "batch")
        os.makedirs(batch_dir, exist_ok=True)

        doc = Document()
        doc.canvas_width = 360
        doc.canvas_height = 240

        image_layer = doc.add_layer(
            name="图片层",
            x=20,
            y=24,
            width=96,
            height=72,
            image_source=src,
            use_original_size=True,
            is_folder=False,
        )
        assert image_layer is not None

        text_layer = TextLayer(name="文案层", x=140, y=38, width=160, height=60)
        text_layer.set_text_lines(["批图王手测"])
        doc.add_text_layer(text_layer)

        shaped_layer = ShapedLayer(
            name="异形层",
            x=210,
            y=120,
            width=72,
            height=72,
            image_source=src,
            use_original_size=False,
            is_folder=False,
            shape_type=ShapeType.CIRCLE,
        )
        doc.add_shaped_layer(shaped_layer)
        assert len(doc.layers) == 3

        rendered = doc.render_document()
        assert rendered is not None
        assert rendered.size == (360, 240)

        assert doc.save_document(doc_path) is True
        loaded = Document()
        assert loaded.load_document(doc_path) is True
        assert len(loaded.layers) == 3

        assert loaded.export_image(single_out) is True
        with Image.open(single_out) as exported:
            assert exported.size == (360, 240)

        assert loaded.batch_export(
            directory=batch_dir,
            count=2,
            filename_template="smoke_{number:02d}",
            file_format="png",
            use_high_performance=False,
            use_smart_sampling=False,
        ) is True
        exported_files = sorted(name for name in os.listdir(batch_dir) if name.endswith(".png"))
        assert exported_files == ["smoke_01.png", "smoke_02.png"]
