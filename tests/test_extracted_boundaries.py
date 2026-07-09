import hashlib

from PIL import Image


def test_render_cache_key_helpers_are_stable_for_layer_positions():
    from app.utils.render_cache_keys import build_layer_positions_key

    class Doc:
        canvas_width = 640
        canvas_height = 480

    class Layer:
        x = 10
        y = 20
        width = 100
        height = 80
        clone_enabled = True
        clone_fill_enabled = False
        clone_fill_spacing = 12
        clone_fill_angle = 15.5
        clone_fill_mode = "grid"
        clone_fill_margin = 3
        clone_mirror_mode = "horizontal"
        _current_random_offset_x = 1
        _current_random_offset_y = 2
        _current_random_scale = 1.25
        _current_random_rotation = 4.5

    key1 = build_layer_positions_key(Layer(), Doc())
    key2 = build_layer_positions_key(Layer(), Doc())

    assert key1 == key2
    assert len(key1) == 32


def test_batch_export_hashing_uses_sorted_layer_file_basenames():
    from app.utils.batch_export_hashing import generate_deterministic_hash

    layer_states = {
        2: r"D:\assets\b.png",
        1: r"D:\assets\a.png",
    }
    expected = hashlib.md5("L1:a.png|L2:b.png".encode("utf-8")).hexdigest()[:16]

    assert generate_deterministic_hash(layer_states) == expected


def test_text_auto_fit_padding_normalizes_alpha_bbox():
    from app.models.text_render_layout import normalize_auto_fit_padding

    image = Image.new("RGBA", (20, 20), (0, 0, 0, 0))
    image.paste(Image.new("RGBA", (4, 6), (255, 0, 0, 255)), (5, 7))

    normalized, size = normalize_auto_fit_padding(image, padding=3)

    assert normalized.size == (10, 12)
    assert size == (10, 12)
    assert normalized.getchannel("A").getbbox() == (3, 3, 7, 9)
