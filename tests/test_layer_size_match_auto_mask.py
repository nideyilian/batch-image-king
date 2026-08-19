"""图层大小匹配 - 自动遮罩单元测试。

覆盖：
- 大黑色矩形被挖成透明孔
- 白色边框保留
- 小黑字（细线）不被挖
- 小黑点不被挖
- 黑色区域过大时不挖
- 自动遮罩关闭时不改变图像
- 缓存 key 纳入自动遮罩参数
- 自动遮罩后 _detect_inner_holes 能识别孔位 bbox
- Manager 序列化/旧文件兼容自动遮罩默认字段

纯逻辑测试，无需 GUI/Qt/真实文件 I/O，标记 @pytest.mark.unit。
"""

import os
import sys

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import fast_renderer_surface as surface_module  # noqa: E402
from app.utils.fast_renderer_surface import (  # noqa: E402
    FastRendererSurface,
    _auto_mask_key_part,
    _make_hole_cache_key,
)
from app.models.layer_size_match_manager import (  # noqa: E402
    LayerSizeMatchManager,
    AUTO_MASK_DEFAULTS,
)

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# 测试图像构造辅助
# --------------------------------------------------------------------------- #
def _build_color_canvas(w=400, h=300, blocks=None, border_color=None, border=0):
    """构造不透明彩色画布，可放置黑色块并可选外扩彩色边框。

    blocks: list of (x, y, bw, bh) 黑色矩形（RGB=0, alpha=255）。
    border_color: (r,g,b) 在黑色块外扩 border 像素处绘制该色环，用于验证边框保留。
    """
    blocks = blocks or []
    rgba = np.full((h, w, 4), 255, np.uint8)
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = 255  # 默认白底不透明
    for (bx, by, bw, bh) in blocks:
        rgba[by:by + bh, bx:bx + bw] = (0, 0, 0, 255)
    if border_color is not None and border > 0:
        for (bx, by, bw, bh) in blocks:
            # 在黑色块四周外扩 border 像素绘制彩色环
            x0, y0 = max(0, bx - border), max(0, by - border)
            x1, y1 = min(w, bx + bw + border), min(h, by + bh + border)
            rgba[y0:by, x0:x1] = (*border_color, 255)
            rgba[by + bh:y1, x0:x1] = (*border_color, 255)
            rgba[y0:y1, x0:bx] = (*border_color, 255)
            rgba[y0:y1, bx + bw:x1] = (*border_color, 255)
    return Image.fromarray(rgba, "RGBA")


def _enabled_relation(**overrides):
    rel = dict(AUTO_MASK_DEFAULTS)
    rel["auto_mask_enabled"] = True
    # 将短名映射为 relation 实际使用的 auto_mask_* 字段
    key_map = {
        "enabled": "auto_mask_enabled",
        "mode": "auto_mask_mode",
        "threshold": "auto_mask_threshold",
        "tolerance": "auto_mask_tolerance",
        "min_area_ratio": "auto_mask_min_area_ratio",
        "max_area_ratio": "auto_mask_max_area_ratio",
        "keep_border": "auto_mask_keep_border",
        "edge_refine": "auto_mask_edge_refine",
    }
    for k, v in overrides.items():
        rel[key_map.get(k, k)] = v
    return rel


# --------------------------------------------------------------------------- #
# 自动遮罩算法
# --------------------------------------------------------------------------- #
class TestAutoMaskBigBlackRect:
    def test_big_black_rect_becomes_transparent_hole(self):
        fr = FastRendererSurface()
        img = _build_color_canvas(blocks=[(100, 100, 120, 80)])
        rel = _enabled_relation(edge_refine=False, keep_border=False)
        masked = fr.apply_auto_mask(img, rel)
        arr = np.array(masked)
        # 黑色块内部 alpha 应为 0（透明）
        assert int(arr[140, 140, 3]) == 0
        # 白色底区域 alpha 仍为 255
        assert int(arr[10, 10, 3]) == 255

    def test_holes_detected_after_auto_mask(self):
        fr = FastRendererSurface()
        img = _build_color_canvas(blocks=[(100, 100, 120, 80)])
        rel = _enabled_relation(edge_refine=False, keep_border=False)
        masked = fr.apply_auto_mask(img, rel)
        holes = fr._detect_inner_holes(masked)
        assert len(holes) == 1
        assert holes[0]["bbox"] == (100, 100, 220, 180)


class TestAutoMaskWhiteBorder:
    def test_white_border_preserved(self):
        fr = FastRendererSurface()
        # 黑色块外扩 4px 绿色边框，验证遮罩不吞掉边框
        img = _build_color_canvas(
            blocks=[(100, 100, 120, 80)], border_color=(0, 200, 0), border=4
        )
        rel = _enabled_relation(keep_border=True, edge_refine=False)
        masked = fr.apply_auto_mask(img, rel)
        arr = np.array(masked)
        # 绿色边框像素（位于黑色块左侧外 2px 处）保持绿色不透明
        assert tuple(int(v) for v in arr[140, 98]) == (0, 200, 0, 255)

    def test_keep_border_shrinks_hole_by_one_px(self):
        fr = FastRendererSurface()
        img = _build_color_canvas(blocks=[(100, 100, 120, 80)])
        rel_no = _enabled_relation(keep_border=False, edge_refine=False)
        rel_yes = _enabled_relation(keep_border=True, edge_refine=False)
        masked_no = fr.apply_auto_mask(img, rel_no)
        masked_yes = fr.apply_auto_mask(img, rel_yes)
        h_no = fr._detect_inner_holes(masked_no)[0]["bbox"]
        h_yes = fr._detect_inner_holes(masked_yes)[0]["bbox"]
        # 保留边框使孔每侧缩小 1px（整体 2px）
        assert h_yes[0] == h_no[0] + 1
        assert h_yes[1] == h_no[1] + 1
        assert h_yes[2] == h_no[2] - 1
        assert h_yes[3] == h_no[3] - 1


class TestAutoMaskSmallRegionsFiltered:
    def test_small_text_line_not_dug(self):
        fr = FastRendererSurface()
        img = _build_color_canvas(blocks=[(170, 140, 2, 60)])  # 细黑线
        rel = _enabled_relation(edge_refine=False)
        masked = fr.apply_auto_mask(img, rel)
        arr = np.array(masked)
        # 细线区域 alpha 仍不透明（未被挖）
        assert int(arr[170, 171, 3]) == 255

    def test_small_dot_not_dug(self):
        fr = FastRendererSurface()
        img = _build_color_canvas(blocks=[(196, 140, 8, 8)])  # 小黑点
        rel = _enabled_relation(edge_refine=False)
        masked = fr.apply_auto_mask(img, rel)
        arr = np.array(masked)
        assert int(arr[144, 200, 3]) == 255


class TestAutoMaskTooLarge:
    def test_too_large_region_not_dug(self):
        fr = FastRendererSurface()
        # 覆盖约 90% 的黑色区域，超过 max_area_ratio(0.75)
        img = _build_color_canvas(blocks=[(10, 10, 380, 270)])
        rel = _enabled_relation(edge_refine=False)
        masked = fr.apply_auto_mask(img, rel)
        # 过大 -> mask 为空 -> 原图不变
        assert np.array_equal(np.array(masked), np.array(img))


class TestAutoMaskDisabled:
    def test_disabled_unchanged(self):
        fr = FastRendererSurface()
        img = _build_color_canvas(blocks=[(100, 100, 120, 80)])
        rel = dict(AUTO_MASK_DEFAULTS)  # auto_mask_enabled=False
        rel["auto_mask_enabled"] = False
        masked = fr.apply_auto_mask(img, rel)
        assert np.array_equal(np.array(masked), np.array(img))

    def test_unsupported_mode_unchanged(self):
        fr = FastRendererSurface()
        img = _build_color_canvas(blocks=[(100, 100, 120, 80)])
        rel = _enabled_relation(auto_mask_mode="unknown_mode")
        masked = fr.apply_auto_mask(img, rel)
        assert np.array_equal(np.array(masked), np.array(img))


# --------------------------------------------------------------------------- #
# 缓存键
# --------------------------------------------------------------------------- #
class TestAutoMaskCacheKey:
    def test_key_part_empty_when_disabled(self):
        rel = dict(AUTO_MASK_DEFAULTS)
        assert _auto_mask_key_part(rel) == ""

    def test_key_part_contains_params_when_enabled(self):
        rel = _enabled_relation(threshold=40, tolerance=20)
        part = _auto_mask_key_part(rel)
        assert "am1" in part
        assert "th40" in part
        assert "tol20" in part
        assert "kb1" in part
        assert "er1" in part

    def test_hole_cache_key_includes_auto_mask_params(self):
        rel = _enabled_relation(threshold=40)
        key = _make_hole_cache_key(1, 2, "surf", _auto_mask_key_part(rel))
        assert "th40" in key
        base_key = _make_hole_cache_key(1, 2, "surf")
        assert "th40" not in base_key


# --------------------------------------------------------------------------- #
# Manager 兼容
# --------------------------------------------------------------------------- #
class TestAutoMaskManagerCompat:
    def test_new_relation_has_auto_mask_defaults(self):
        mgr = LayerSizeMatchManager()
        mgr.add_relation("A", ["B"], auto_mask={"auto_mask_enabled": True})
        rel = mgr.relations[0]
        assert rel["auto_mask_enabled"] is True
        assert rel["auto_mask_mode"] == "black_placeholder"
        assert rel["auto_mask_threshold"] == 32
        assert rel["auto_mask_tolerance"] == 18
        assert rel["auto_mask_keep_border"] is True
        assert rel["auto_mask_edge_refine"] is True

    def test_old_file_deserialize_disables_auto_mask(self):
        mgr = LayerSizeMatchManager()
        # 旧文件：relation 不含任何 auto_mask 字段
        mgr.deserialize({
            "global_enabled": True,
            "relations": [{
                "id": "r1",
                "source_layer_name": "A",
                "target_layer_name": "B",
                "target_layer_names": ["B"],
                "enabled": True,
                "padding": 1,
                "one_to_many": False,
                "auto_rotate": False,
            }],
        })
        rel = mgr.relations[0]
        assert rel["auto_mask_enabled"] is False
        assert rel["auto_mask_mode"] == "black_placeholder"

    def test_active_relation_exposes_auto_mask_fields(self):
        mgr = LayerSizeMatchManager()
        mgr.set_global_enabled(True)
        mgr.add_relation("A", ["B"], auto_mask={"auto_mask_enabled": True, "auto_mask_threshold": 50})
        active = mgr.get_active_relations()
        assert active[0]["auto_mask_enabled"] is True
        assert active[0]["auto_mask_threshold"] == 50

    def test_serialize_roundtrip_preserves_auto_mask(self):
        mgr = LayerSizeMatchManager()
        mgr.add_relation("A", ["B"], auto_mask={"auto_mask_enabled": True, "auto_mask_threshold": 60})
        data = mgr.serialize()
        mgr2 = LayerSizeMatchManager()
        mgr2.deserialize(data)
        assert mgr2.relations[0]["auto_mask_enabled"] is True
        assert mgr2.relations[0]["auto_mask_threshold"] == 60
