from PIL import Image

import pytest

from app.models.layer_new import Layer
from app.utils.fast_renderer import FastRenderer


pytestmark = pytest.mark.unit


def test_smart_fit_preserves_aspect_after_effects_pipeline():
    layer = Layer(width=100, height=100)
    layer.fit_mode = Layer.FIT_SMART_FIT
    layer._is_batch_mode = True
    layer._bleed_transparent_edges = lambda image: image

    source = Image.new("RGBA", (200, 100), (255, 0, 0, 255))
    processed = layer._process_image(source)
    assert processed.size == (100, 50)

    rendered = layer.apply_effects(processed)
    assert rendered.size == (100, 100)
    assert rendered.getchannel("A").getbbox() == (0, 25, 100, 75)


def test_fast_renderer_smart_fit_surface_keeps_letterbox():
    renderer = FastRenderer()
    source = Image.new("RGBA", (100, 50), (255, 0, 0, 255))

    surface = renderer._center_surface_on_canvas(source, 100, 100)

    assert surface.size == (100, 100)
    assert surface.getchannel("A").getbbox() == (0, 25, 100, 75)
