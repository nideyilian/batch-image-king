"""图层大小匹配 - 内孔检测核心单元测试（阶段一：加速与精准化）。

覆盖：
- 无透明孔：返回空
- 单个矩形孔：bbox 准确
- 多个孔：数量和排序稳定
- 半透明边缘孔：自适应阈值能识别完整
- 倾斜孔：角度有效，bbox 不明显偏大
- 小噪点孔：被过滤
- OpenCV 失败时 fallback 旧算法

纯逻辑测试，无需 GUI/Qt/真实文件 I/O，标记 @pytest.mark.unit。
"""

import os
import sys
import math

import numpy as np
import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils import fast_renderer_surface as surface_module  # noqa: E402
from app.utils.fast_renderer_surface import FastRendererSurface  # noqa: E402

pytestmark = pytest.mark.unit


# --------------------------------------------------------------------------- #
# 测试图像构造辅助
# --------------------------------------------------------------------------- #
def _build_frame(canvas=(400, 300), holes=None, feather=0, ring_alpha=80):
    """构造一个“不透明框 + 透明孔”的图像。

    - 整张画布默认不透明（alpha=255），保证孔被框包裹（不与边界连通）。
    - 每个 hole 用 (x, y, w, h) 描述。
    - feather==0：孔内部完全透明（alpha=0），边界清晰。
    - feather>0：孔整体先置为半透明（ring_alpha），再把内部 feather 像素完全透明，
      形成“半透明边缘环”，用于模拟“半透明边缘孔”。
    """
    holes = holes or []
    h, w = canvas
    alpha = np.full((h, w), 255, np.uint8)
    for (hx, hy, hw, hh) in holes:
        alpha[hy:hy + hh, hx:hx + hw] = ring_alpha if feather > 0 else 0
    if feather > 0:
        for (hx, hy, hw, hh) in holes:
            if hw > 2 * feather and hh > 2 * feather:
                # 内部 feather 像素完全透明（孔核心），外圈保留半透明环
                alpha[hy + feather:hy + hh - feather, hx + feather:hx + hw - feather] = 0
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 3] = alpha
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = 220
    return Image.fromarray(rgba, 'RGBA')


def _build_tilted_hole(canvas=(400, 300), cx=200, cy=150, rw=200, rh=100, angle_deg=30):
    """构造一个旋转矩形孔（硬边 alpha），用于验证自动倾斜。"""
    h, w = canvas
    alpha = np.full((h, w), 255, np.uint8)
    a = math.radians(angle_deg)
    yy, xx = np.mgrid[0:h, 0:w]
    dx = xx - cx
    dy = yy - cy
    # 旋转 -angle，使矩形在局部坐标对齐坐标轴
    rx = dx * math.cos(-a) - dy * math.sin(-a)
    ry = dx * math.sin(-a) + dy * math.cos(-a)
    inside = (np.abs(rx) <= rw / 2.0) & (np.abs(ry) <= rh / 2.0)
    alpha[inside] = 0
    rgba = np.zeros((h, w, 4), np.uint8)
    rgba[..., 3] = alpha
    rgba[..., 0] = rgba[..., 1] = rgba[..., 2] = 220
    return Image.fromarray(rgba, 'RGBA')


# --------------------------------------------------------------------------- #
# 测试
# --------------------------------------------------------------------------- #
class TestHoleDetectionEmpty:
    def test_no_transparent_hole_returns_empty(self):
        fr = FastRendererSurface()
        img = _build_frame(canvas=(300, 200), holes=[])
        holes = fr._detect_inner_holes(img)
        assert holes == []


class TestHoleDetectionSingle:
    def test_single_rectangle_hole_bbox_accurate(self):
        fr = FastRendererSurface()
        img = _build_frame(canvas=(400, 300), holes=[(100, 100, 80, 60)])
        holes = fr._detect_inner_holes(img)
        assert len(holes) == 1
        bbox = holes[0]['bbox']
        assert bbox == (100, 100, 180, 160)
        # cv2.contourArea 对清晰矩形返回约 (W-1)*(H-1)，允许小幅偏差
        assert abs(holes[0]['area'] - 80 * 60) <= 240


class TestHoleDetectionMultiple:
    def test_multiple_holes_count_and_stable_sort(self):
        fr = FastRendererSurface()
        holes_def = [
            (40, 40, 60, 60),
            (40, 200, 60, 60),
            (200, 40, 60, 60),
        ]
        img = _build_frame(canvas=(400, 300), holes=holes_def)
        holes = fr._detect_inner_holes(img)
        assert len(holes) == 3

        ordered = fr._sort_holes_left_to_right_then_top_to_bottom(holes)
        ordered_bboxes = [h['bbox'] for h in ordered]
        # 列1 在 x=40：先上(40,40)后下(40,200)；列2 在 x=200：(200,40)
        expected = [
            (40, 40, 100, 100),
            (40, 200, 100, 260),
            (200, 40, 260, 100),
        ]
        assert ordered_bboxes == expected

        # 排序稳定性：再跑一次结果一致
        ordered2 = fr._sort_holes_left_to_right_then_top_to_bottom(holes)
        assert [h['bbox'] for h in ordered2] == expected


class TestHoleDetectionSemiTransparent:
    def test_adaptive_threshold_recovers_full_hole(self):
        fr = FastRendererSurface()
        # 大画布 + 较小孔，使默认阈值检测结果面积 < 1.5% 画布，触发自适应回退
        img = _build_frame(
            canvas=(600, 600),
            holes=[(270, 280, 60, 40)],
            feather=4,
            ring_alpha=80,
        )
        # 默认阈值（6）只识别到孔核心（边缘半透明被忽略）
        core = fr._detect_inner_holes(img, alpha_threshold=6)
        assert len(core) == 1
        core_w = core[0]['bbox'][2] - core[0]['bbox'][0]
        core_h = core[0]['bbox'][3] - core[0]['bbox'][1]

        # 走与渲染管线一致的自适应流程
        refined = fr._refine_holes_with_adaptive_alpha_threshold(img, core)
        assert len(refined) == 1
        rb = refined[0]['bbox']
        refined_w = rb[2] - rb[0]
        refined_h = rb[3] - rb[1]

        # 自适应阈值应恢复出更完整的孔（含半透明边缘）
        assert refined_w > core_w
        assert refined_h > core_h
        # 且不应过度放大（接近真实孔尺寸 60x40）
        assert refined_w <= 62
        assert refined_h <= 42


class TestHoleDetectionTilted:
    def test_tilted_hole_angle_valid_and_bbox_not_oversized(self):
        fr = FastRendererSurface()
        # 注意：旋转矩形需完全位于画布内部，否则会被新逻辑判定为“与外部边界连通的
        # 透明背景”而排除（这是期望行为）。此处 rw/rh 取值保证孔不接触边界。
        img = _build_tilted_hole(
            canvas=(400, 300), cx=150, cy=150, rw=160, rh=80, angle_deg=30
        )
        holes = fr._detect_inner_holes(img)
        assert len(holes) == 1
        hole = holes[0]
        assert hole['angle_valid'] is True
        # 角度有效且接近真实倾角（允许像素化误差）
        assert 20.0 < abs(hole['angle_deg']) < 40.0
        # 最小外接尺寸接近真实矩形（160x80）
        assert 150 <= hole['oriented_w'] <= 170
        assert 72 <= hole['oriented_h'] <= 88
        # 轴对齐 bbox 是倾斜矩形的外切框，不应异常放大
        bbox = hole['bbox']
        bbox_w = bbox[2] - bbox[0]
        bbox_h = bbox[3] - bbox[1]
        assert 168 <= bbox_w <= 192
        assert 140 <= bbox_h <= 162
        # 旋转后所需尺寸应明显小于轴对齐 bbox（说明倾斜匹配能减少留白）
        assert hole['oriented_w'] < bbox_w
        assert hole['oriented_h'] < bbox_h


class TestHoleDetectionNoise:
    def test_small_noise_hole_filtered(self):
        fr = FastRendererSurface()
        img = _build_frame(
            canvas=(400, 300),
            holes=[(150, 110, 120, 80), (50, 50, 4, 4)],
        )
        holes = fr._detect_inner_holes(img)
        # 4x4 噪点（面积 16 < 噪点过滤阈值 24）应被过滤，仅保留大孔
        assert len(holes) == 1
        assert holes[0]['area'] >= 9000


class TestHoleDetectionFallback:
    def test_fallback_used_when_cv2_unavailable(self, monkeypatch):
        monkeypatch.setattr(surface_module, "_CV2_AVAILABLE", False)
        fr = FastRendererSurface()
        img = _build_frame(canvas=(400, 300), holes=[(100, 100, 80, 60)])
        holes = fr._detect_inner_holes(img)
        # 回退纯 Python 实现应仍能正确识别矩形孔
        assert len(holes) == 1
        assert holes[0]['bbox'] == (100, 100, 180, 160)


class TestHoleCacheKey:
    def test_cache_key_includes_detection_params(self):
        key = surface_module._make_hole_cache_key(1, 2, "surf")
        assert "th6" in key
        assert "mk3" in key
        assert "nf24" in key
        assert "ar4" in key


class TestHoleDetectionExternalBackground:
    def test_transparent_outer_canvas_does_not_become_hole(self):
        """回归：整张图透明 + 中间不透明框 + 框内挖孔，只应识别内部孔。

        修复前 OpenCV 路径会把“与外部边界连通的整张透明背景”误判为内孔。
        """
        fr = FastRendererSurface()
        h, w = 240, 320
        alpha = np.zeros((h, w), np.uint8)
        alpha[40:200, 60:260] = 255   # 不透明框
        alpha[90:150, 120:200] = 0    # 框内透明孔

        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[..., 3] = alpha
        rgba[..., :3] = 220
        img = Image.fromarray(rgba, "RGBA")

        holes = fr._detect_inner_holes(img)
        assert len(holes) == 1
        assert holes[0]["bbox"] == (120, 90, 200, 150)
