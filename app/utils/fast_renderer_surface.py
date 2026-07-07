"""
真正有效的快速渲染器（优化版本）
解决实际使用中的性能问题，不降低质量
集成智能渲染缓存系统
"""

import time
import hashlib
import threading
import os
import builtins
from collections import OrderedDict, deque
from functools import wraps
from typing import Optional, Dict, Any, Tuple
import math
from PIL import Image
import numpy as np
import weakref
import gc

# 默认关闭快速渲染器调试输出，避免预览阶段高频 I/O 导致掉帧
_FAST_RENDERER_DEBUG = os.environ.get("BTPW_FAST_RENDERER_DEBUG", "0") == "1"
# 默认关闭批量渲染高频日志，避免导出阶段控制台 I/O 成为瓶颈
_BATCH_RENDER_VERBOSE = os.environ.get("BTPW_BATCH_RENDER_VERBOSE", "0") == "1"
try:
    _INTERACTIVE_PREVIEW_MAX_EDGE = max(480, int(os.environ.get("BTPW_INTERACTIVE_PREVIEW_MAX_EDGE", "1200")))
except Exception:
    _INTERACTIVE_PREVIEW_MAX_EDGE = 1200
# 内孔检测算法版本号：用于缓存键，避免算法升级后命中旧检测结果
_SIZE_MATCH_HOLE_DETECT_VER = "v10"
# 自动倾斜最小触发角（度）：小于该值视为不倾斜，减少误判抖动
_AUTO_ROTATE_MIN_DEG = 4.0


def print(*args, **kwargs):
    if _FAST_RENDERER_DEBUG:
        builtins.print(*args, **kwargs)


def _serialized_preview(method):
    @wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._preview_render_lock:
            return method(self, *args, **kwargs)
    return wrapper


# 导入新的智能缓存系统
from .intelligent_render_cache import get_intelligent_cache
# 导入智能内存管理系统
from .intelligent_memory_manager import get_memory_manager, register_image_for_tracking
from .render_diagnostics import log_branch



class FastRendererSurface(object):
    """Mixin for fast_renderer_surface (split from FastRenderer)."""

    def _get_layer_surface_for_size(
        self,
        layer,
        document,
        target_w: int,
        target_h: int,
        was_just_loaded: bool = False,
        rotation_override: Optional[float] = None
    ) -> Optional[Image.Image]:
        """按指定尺寸重新生成图层 surface（避免二次缩放引起模糊）。"""
        target_w = max(1, int(target_w))
        target_h = max(1, int(target_h))
        try:
            base_surface_key = self._build_layer_surface_key(layer, document, was_just_loaded)
        except Exception:
            base_surface_key = f"fallback_{id(layer)}"
        rot_key = "none" if rotation_override is None else f"{float(rotation_override):.4f}"
        override_cache_key = f"{id(document)}:{id(layer)}:{base_surface_key}:size:{target_w}x{target_h}:rot:{rot_key}"

        with self._size_override_surface_lock:
            cached = self._size_override_surface_cache.get(override_cache_key)
            if cached is not None:
                self._size_override_surface_cache.move_to_end(override_cache_key)
                if isinstance(cached, dict):
                    img = cached.get("image")
                    setattr(layer, "_render_offset_x", int(cached.get("offset_x", 0)))
                    setattr(layer, "_render_offset_y", int(cached.get("offset_y", 0)))
                    return img.copy() if img is not None else None
                # 兼容历史缓存结构（仅图片）
                setattr(layer, "_render_offset_x", 0)
                setattr(layer, "_render_offset_y", 0)
                return cached.copy()

        # 文字图层不走此路径
        if hasattr(layer, 'get_text_lines'):
            return self._get_layer_surface_cached(layer, document, was_just_loaded)

        # 优先从当前文件路径直接加载并按目标尺寸处理
        current_image_path = None
        if hasattr(layer, '_current_image_path') and getattr(layer, '_current_image_path', None):
            current_image_path = layer._current_image_path
        elif hasattr(layer, 'current_image_path'):
            try:
                current_image_path = layer.current_image_path
            except Exception:
                current_image_path = None

        if not current_image_path or (not os.path.isfile(current_image_path)):
            # 无有效路径时回退旧逻辑
            fallback = self._get_layer_surface_cached(layer, document, was_just_loaded)
            if fallback is not None:
                # 导出与预览统一：回退分支也必须先裁透明边再覆盖缩放，避免留白
                fallback = self._resize_cover_from_content(fallback, target_w, target_h)
            return fallback

        original_w = int(getattr(layer, 'width', target_w) or target_w)
        original_h = int(getattr(layer, 'height', target_h) or target_h)
        original_rotation = float(getattr(layer, 'rotation', 0.0) or 0.0) if hasattr(layer, 'rotation') else 0.0
        layer_image = None

        try:
            # 临时替换尺寸，仅用于本次重取图像，随后恢复
            if hasattr(layer, '_property_manager') and hasattr(layer._property_manager, '_properties'):
                props = layer._property_manager._properties
                if 'width' in props and 'height' in props:
                    props['width']['value'] = target_w
                    props['height']['value'] = target_h
            elif hasattr(layer, '_width') and hasattr(layer, '_height'):
                layer._width = target_w
                layer._height = target_h
            else:
                # 最后兜底：可能触发信号，但确保功能可用
                try:
                    layer.width = target_w
                    layer.height = target_h
                except Exception:
                    pass

            if rotation_override is not None:
                try:
                    rot = float(rotation_override)
                except Exception:
                    rot = original_rotation
                if hasattr(layer, '_property_manager') and hasattr(layer._property_manager, '_properties'):
                    props = layer._property_manager._properties
                    if 'rotation' in props:
                        props['rotation']['value'] = rot
                elif hasattr(layer, '_rotation'):
                    layer._rotation = rot
                else:
                    try:
                        layer.rotation = rot
                    except Exception:
                        pass

            raw_image = self._get_layer_image(layer, document, was_just_loaded)
            if raw_image is None:
                return None
            if hasattr(layer, 'apply_effects') and callable(layer.apply_effects):
                raw_image = layer.apply_effects(raw_image)
            layer_image = raw_image
        finally:
            # 恢复原尺寸，避免污染图层状态
            try:
                if hasattr(layer, '_property_manager') and hasattr(layer._property_manager, '_properties'):
                    props = layer._property_manager._properties
                    if 'width' in props and 'height' in props:
                        props['width']['value'] = original_w
                        props['height']['value'] = original_h
                elif hasattr(layer, '_width') and hasattr(layer, '_height'):
                    layer._width = original_w
                    layer._height = original_h
                else:
                    try:
                        layer.width = original_w
                        layer.height = original_h
                    except Exception:
                        pass

                if rotation_override is not None:
                    if hasattr(layer, '_property_manager') and hasattr(layer._property_manager, '_properties'):
                        props = layer._property_manager._properties
                        if 'rotation' in props:
                            props['rotation']['value'] = original_rotation
                    elif hasattr(layer, '_rotation'):
                        layer._rotation = original_rotation
                    else:
                        try:
                            layer.rotation = original_rotation
                        except Exception:
                            pass
            except Exception:
                pass

        if layer_image is not None:
            # 关键修复：先裁掉透明边再覆盖缩放，避免匹配后留白
            layer_image = self._resize_cover_from_content(layer_image, target_w, target_h)
        if layer_image is not None:
            with self._size_override_surface_lock:
                self._size_override_surface_cache[override_cache_key] = {
                    "image": layer_image.copy(),
                    "offset_x": int(getattr(layer, "_render_offset_x", 0)),
                    "offset_y": int(getattr(layer, "_render_offset_y", 0)),
                }
                self._size_override_surface_cache.move_to_end(override_cache_key)
                while len(self._size_override_surface_cache) > self._max_size_override_surface_entries:
                    self._size_override_surface_cache.popitem(last=False)
        return layer_image

    def _resize_cover_keep_ratio(self, image: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """
        等比覆盖缩放：保持比例，不拉伸，必要时中心裁剪以填满目标区域。
        """
        target_w = max(1, int(target_w))
        target_h = max(1, int(target_h))
        src_w, src_h = image.size
        if src_w <= 0 or src_h <= 0:
            return image
        if src_w == target_w and src_h == target_h:
            return image

        scale = max(target_w / src_w, target_h / src_h)
        resized_w = max(1, int(round(src_w * scale)))
        resized_h = max(1, int(round(src_h * scale)))
        try:
            if image.mode == 'RGBA':
                from app.utils.rgba_resampler import resize_rgba_premultiplied
                resized = resize_rgba_premultiplied(image, (resized_w, resized_h), Image.Resampling.LANCZOS)
            else:
                resized = image.resize((resized_w, resized_h), Image.Resampling.LANCZOS)
        except Exception:
            resized = image.resize((resized_w, resized_h))

        left = max(0, (resized_w - target_w) // 2)
        top = max(0, (resized_h - target_h) // 2)
        right = min(resized_w, left + target_w)
        bottom = min(resized_h, top + target_h)
        cropped = resized.crop((left, top, right, bottom))
        if cropped.size != (target_w, target_h):
            try:
                if cropped.mode == 'RGBA':
                    from app.utils.rgba_resampler import resize_rgba_premultiplied
                    cropped = resize_rgba_premultiplied(cropped, (target_w, target_h), Image.Resampling.LANCZOS)
                else:
                    cropped = cropped.resize((target_w, target_h), Image.Resampling.LANCZOS)
            except Exception:
                cropped = cropped.resize((target_w, target_h))
        return cropped

    def _crop_nontransparent_bbox(self, image: Image.Image) -> Image.Image:
        """裁掉图像四周透明边，避免匹配后留白。"""
        try:
            rgba = image if image.mode == 'RGBA' else image.convert('RGBA')
            alpha = np.array(rgba.split()[3])
            ys, xs = np.where(alpha > 0)
            if xs.size == 0 or ys.size == 0:
                return rgba
            left = int(xs.min())
            right = int(xs.max()) + 1
            top = int(ys.min())
            bottom = int(ys.max()) + 1
            if left <= 0 and top <= 0 and right >= rgba.width and bottom >= rgba.height:
                return rgba
            cropped = rgba.crop((left, top, right, bottom))
            return cropped if cropped.size[0] > 0 and cropped.size[1] > 0 else rgba
        except Exception:
            return image

    def _resize_cover_from_content(self, image: Image.Image, target_w: int, target_h: int) -> Image.Image:
        """先按非透明内容裁边，再等比覆盖缩放到目标尺寸。"""
        trimmed = self._crop_nontransparent_bbox(image)
        return self._resize_cover_keep_ratio(trimmed, target_w, target_h)

    def _normalize_angle_180(self, angle: float) -> float:
        """归一化角度到 (-180, 180]。"""
        a = float(angle)
        while a <= -180.0:
            a += 360.0
        while a > 180.0:
            a -= 360.0
        return a

    def _pick_min_delta_rotation(self, target_angle: float, reference_angle: float) -> float:
        """从等价角中选与参考角差值最小的角度，并将旋转差限制在 ±90°。"""
        ref = self._normalize_angle_180(reference_angle)
        candidates = []
        for k in (-2, -1, 0, 1, 2):
            candidates.append(float(target_angle) + 180.0 * float(k))
        best_delta = None
        best_abs = None
        for c in candidates:
            delta = self._normalize_angle_180(c - ref)
            # 矩形方向 180° 周期等价：优先把差值折叠到 [-90, 90]
            if delta > 90.0:
                delta -= 180.0
            elif delta < -90.0:
                delta += 180.0
            abs_delta = abs(delta)
            if best_delta is None or abs_delta < best_abs:
                best_delta = delta
                best_abs = abs_delta
        if best_delta is None:
            return self._normalize_angle_180(ref)
        return self._normalize_angle_180(ref + best_delta)

    def _to_small_tilt_by_axis(self, raw_angle_deg: float, bbox_w: int, bbox_h: int) -> float:
        """
        将主轴角度转换为“相对主方向的小倾角”。
        - 自动选择最接近的主方向基准轴（0° 水平 / 90° 垂直）
        - 若两者接近，使用 bbox 长宽作为稳定性兜底
        返回值限制在 [-90, 90]，并优先最小绝对值。
        """
        a = self._normalize_angle_180(raw_angle_deg)
        # 角度以 180° 为等价周期，先计算相对两条主轴的最小差值
        tilt_h = self._normalize_angle_180(a)
        if tilt_h > 90.0:
            tilt_h -= 180.0
        elif tilt_h < -90.0:
            tilt_h += 180.0

        tilt_v = self._normalize_angle_180(a - 90.0)
        if tilt_v > 90.0:
            tilt_v -= 180.0
        elif tilt_v < -90.0:
            tilt_v += 180.0

        abs_h = abs(float(tilt_h))
        abs_v = abs(float(tilt_v))

        # 两轴都接近时，使用 bbox 方向作为稳定兜底，避免角度在预览中抖动跳变
        if abs(abs_h - abs_v) <= 3.0:
            tilt = float(tilt_v if int(bbox_h) >= int(bbox_w) else tilt_h)
        else:
            tilt = float(tilt_h if abs_h <= abs_v else tilt_v)

        if tilt > 90.0:
            tilt -= 180.0
        elif tilt < -90.0:
            tilt += 180.0
        return float(tilt)

    def _estimate_oriented_size(
        self,
        points_xy,
        center_x: float,
        center_y: float,
        rotation_deg: float
    ) -> Tuple[int, int]:
        """
        在给定旋转角下估算连通域在局部坐标系中的宽高。
        说明：
        - rotation_deg 与图层 rotation 语义保持一致（顺时针为正）
        - 返回最小为 1x1，且做轻量边界余量，减少裁切
        """
        if not points_xy:
            return 1, 1
        theta = math.radians(float(rotation_deg))
        ux = math.cos(theta)
        uy = math.sin(theta)
        vx = -math.sin(theta)
        vy = math.cos(theta)

        min_u = None
        max_u = None
        min_v = None
        max_v = None

        for px, py in points_xy:
            dx = float(px) - float(center_x)
            dy = float(py) - float(center_y)
            pu = dx * ux + dy * uy
            pv = dx * vx + dy * vy
            if min_u is None or pu < min_u:
                min_u = pu
            if max_u is None or pu > max_u:
                max_u = pu
            if min_v is None or pv < min_v:
                min_v = pv
            if max_v is None or pv > max_v:
                max_v = pv

        if min_u is None or max_u is None or min_v is None or max_v is None:
            return 1, 1

        # +1 像素把离散点覆盖为像素区间；再加 1 像素冗余减少边缘抽样裁切
        ow = max(1, int(math.ceil((max_u - min_u) + 1.0)) + 1)
        oh = max(1, int(math.ceil((max_v - min_v) + 1.0)) + 1)
        return ow, oh

    def _oriented_bbox_metrics(self, points_xy, center_x: float, center_y: float, rotation_deg: float) -> Tuple[int, int, float]:
        """计算给定旋转角下的最小包围宽高与面积。"""
        ow, oh = self._estimate_oriented_size(points_xy, center_x, center_y, rotation_deg)
        return int(ow), int(oh), float(max(1, int(ow) * int(oh)))

    def _estimate_tilt_from_min_rect(
        self,
        points_xy,
        center_x: float,
        center_y: float,
        axis_w: int,
        axis_h: int,
        seed_angle_deg: float
    ) -> Tuple[float, int, int, float]:
        """
        基于“最小面积倾斜矩形 vs 轴对齐矩形”估计倾角。
        返回 (tilt_deg, oriented_w, oriented_h, area_gain)。
        """
        axis_area = float(max(1, int(axis_w) * int(axis_h)))
        best_angle = float(seed_angle_deg)
        best_w, best_h, best_area = self._oriented_bbox_metrics(points_xy, center_x, center_y, best_angle)

        # 分两轮搜索：粗搜 + 精搜（围绕最佳角）
        coarse_step = 3.0
        for i in range(-15, 16):
            a = float(seed_angle_deg) + float(i) * coarse_step
            w, h, area = self._oriented_bbox_metrics(points_xy, center_x, center_y, a)
            if area < best_area:
                best_angle, best_w, best_h, best_area = float(a), int(w), int(h), float(area)

        fine_step = 0.6
        for i in range(-12, 13):
            a = float(best_angle) + float(i) * fine_step
            w, h, area = self._oriented_bbox_metrics(points_xy, center_x, center_y, a)
            if area < best_area:
                best_angle, best_w, best_h, best_area = float(a), int(w), int(h), float(area)

        # 统一转换为相对主轴的小倾角（[-90, 90]）
        tilt = self._to_small_tilt_by_axis(best_angle, axis_w, axis_h)
        oriented_w, oriented_h, oriented_area = self._oriented_bbox_metrics(points_xy, center_x, center_y, tilt)
        area_gain = max(0.0, (axis_area - oriented_area) / axis_area)
        return float(tilt), int(oriented_w), int(oriented_h), float(area_gain)

    def _binary_dilate_3x3(self, mask: np.ndarray) -> np.ndarray:
        """3x3 膨胀（bool）。"""
        h, w = mask.shape
        padded = np.pad(mask, ((1, 1), (1, 1)), mode='constant', constant_values=False)
        out = np.zeros((h, w), dtype=bool)
        for dy in range(3):
            for dx in range(3):
                out |= padded[dy:dy + h, dx:dx + w]
        return out

    def _binary_erode_3x3(self, mask: np.ndarray) -> np.ndarray:
        """3x3 腐蚀（bool）。"""
        h, w = mask.shape
        padded = np.pad(mask, ((1, 1), (1, 1)), mode='constant', constant_values=False)
        out = np.ones((h, w), dtype=bool)
        for dy in range(3):
            for dx in range(3):
                out &= padded[dy:dy + h, dx:dx + w]
        return out

    def _close_opaque_mask(self, opaque: np.ndarray) -> np.ndarray:
        """对不透明区域做一次闭运算，封堵细小裂缝，减少孔位偶发漏检。"""
        return self._binary_erode_3x3(self._binary_dilate_3x3(opaque))

    def _classify_hole_shape(self, bbox_w: int, bbox_h: int) -> str:
        """按宽高比粗分类：square / horizontal_rect / vertical_rect。"""
        w = max(1.0, float(bbox_w))
        h = max(1.0, float(bbox_h))
        ratio = w / h
        if 0.85 <= ratio <= 1.18:
            return "square"
        return "horizontal_rect" if ratio > 1.0 else "vertical_rect"

    def _sort_holes_left_to_right_then_top_to_bottom(self, holes):
        """
        孔位排序规则（业务固定）：
        1) 先按“左到右”分列
        2) 列内按“上到下”
        """
        if not holes:
            return []
        widths = []
        for h in holes:
            try:
                l, t, r, b = h.get('bbox', (0, 0, 1, 1))
                widths.append(max(1, int(r - l)))
            except Exception:
                widths.append(1)
        median_w = float(np.median(np.asarray(widths, dtype=np.float32))) if widths else 1.0
        col_tol = max(8.0, median_w * 0.45)
        ordered = sorted(holes, key=lambda h: (float(h.get('center_x', 0.0)), float(h.get('center_y', 0.0))))
        cols = []
        for hole in ordered:
            cx = float(hole.get('center_x', 0.0))
            placed = False
            for col in cols:
                if abs(cx - col['anchor_x']) <= col_tol:
                    col['items'].append(hole)
                    col['anchor_x'] = (col['anchor_x'] * float(col['count']) + cx) / float(col['count'] + 1)
                    col['count'] += 1
                    placed = True
                    break
            if not placed:
                cols.append({'anchor_x': cx, 'count': 1, 'items': [hole]})
        cols.sort(key=lambda c: float(c['anchor_x']))
        flattened = []
        for col in cols:
            col_items = sorted(col['items'], key=lambda h: float(h.get('center_y', 0.0)))
            flattened.extend(col_items)
        return flattened

    def _sort_layers_left_to_right_then_top_to_bottom(self, layers):
        """目标图层排序：先左到右分列，再列内上到下。"""
        if not layers:
            return []
        widths = [max(1, int(getattr(l, 'width', 1) or 1)) for l in layers]
        median_w = float(np.median(np.asarray(widths, dtype=np.float32))) if widths else 1.0
        col_tol = max(8.0, median_w * 0.45)
        ordered = sorted(layers, key=lambda l: (float(getattr(l, 'x', 0.0)), float(getattr(l, 'y', 0.0))))
        cols = []
        for layer in ordered:
            cx = float(getattr(layer, 'x', 0.0))
            placed = False
            for col in cols:
                if abs(cx - col['anchor_x']) <= col_tol:
                    col['items'].append(layer)
                    col['anchor_x'] = (col['anchor_x'] * float(col['count']) + cx) / float(col['count'] + 1)
                    col['count'] += 1
                    placed = True
                    break
            if not placed:
                cols.append({'anchor_x': cx, 'count': 1, 'items': [layer]})
        cols.sort(key=lambda c: float(c['anchor_x']))
        flattened = []
        for col in cols:
            col_items = sorted(col['items'], key=lambda l: float(getattr(l, 'y', 0.0)))
            flattened.extend(col_items)
        return flattened

    def _ensure_rect_covers_hole_bbox(
        self,
        source_x: int,
        source_y: int,
        hole_bbox: Tuple[int, int, int, int],
        x: int,
        y: int,
        width: int,
        height: int,
        extra_margin: int = 0
    ) -> Tuple[int, int, int, int]:
        """
        兜底校验：确保填充矩形至少完整覆盖挖孔 bbox（含可选额外边距）。
        用于避免“已匹配但仍留透明区域”。
        """
        try:
            left, top, right, bottom = hole_bbox
            need_l = int(source_x + left - max(0, int(extra_margin)))
            need_t = int(source_y + top - max(0, int(extra_margin)))
            need_r = int(source_x + right + max(0, int(extra_margin)))
            need_b = int(source_y + bottom + max(0, int(extra_margin)))

            x0 = int(x)
            y0 = int(y)
            x1 = int(x0 + max(1, int(width)))
            y1 = int(y0 + max(1, int(height)))

            if x0 > need_l:
                x0 = need_l
            if y0 > need_t:
                y0 = need_t
            if x1 < need_r:
                x1 = need_r
            if y1 < need_b:
                y1 = need_b

            out_w = max(1, int(x1 - x0))
            out_h = max(1, int(y1 - y0))
            return int(x0), int(y0), int(out_w), int(out_h)
        except Exception:
            return int(x), int(y), max(1, int(width)), max(1, int(height))

    def _build_size_match_overrides(self, document, visible_layers, was_just_loaded: bool = False) -> Dict[int, Dict[str, Any]]:
        """根据图层大小匹配配置构建临时覆写，不修改原始图层参数。"""
        overrides: Dict[int, Dict[str, Any]] = {}
        export_trace_enabled = bool(getattr(document, '_export_debug_trace_enabled', False))
        export_trace_task = str(getattr(document, '_export_debug_trace_task', '') or '')
        export_trace_file = str(getattr(document, '_export_debug_trace_file', '') or '')

        def _emit_size_match_trace(message: str):
            if not export_trace_enabled:
                return
            line = f"[导出调试] {str(message)}"
            try:
                builtins.print(line)
            except Exception:
                pass
            if export_trace_file:
                try:
                    with open(export_trace_file, 'a', encoding='utf-8') as f:
                        f.write(line + "\n")
                except Exception:
                    pass

        manager = getattr(document, 'layer_size_match_manager', None)
        if not manager or not getattr(manager, 'global_enabled', False):
            _emit_size_match_trace(f"任务={export_trace_task} 图层匹配关闭或管理器不可用")
            return overrides

        try:
            active_relations = manager.get_active_relations() if hasattr(manager, 'get_active_relations') else []
        except Exception:
            active_relations = []
        if not active_relations:
            _emit_size_match_trace(f"任务={export_trace_task} 图层匹配无有效关系")
            return overrides

        layer_by_name = {}
        for layer in visible_layers:
            name = str(getattr(layer, 'name', '')).strip()
            if name and name not in layer_by_name:
                layer_by_name[name] = layer

        for relation in active_relations:
            source_name = str(relation.get('source_layer_name', '')).strip()
            source_layer = layer_by_name.get(source_name)
            if source_layer is None or hasattr(source_layer, 'get_text_lines'):
                _emit_size_match_trace(
                    f"任务={export_trace_task} 匹配关系跳过 source={source_name} 原因=source_missing_or_text"
                )
                continue

            holes = self._get_inner_holes_cached(source_layer, document, was_just_loaded)
            _emit_size_match_trace(
                f"任务={export_trace_task} 匹配关系 source={source_name} 孔位数量={len(holes)}"
            )

            source_w = int(getattr(source_layer, 'width', 1) or 1)
            source_h = int(getattr(source_layer, 'height', 1) or 1)

            target_names = relation.get('target_layer_names') or []
            if not isinstance(target_names, list) or not target_names:
                legacy_target = str(relation.get('target_layer_name', '')).strip()
                target_names = [legacy_target] if legacy_target else []
            targets = []
            for name in target_names:
                layer_obj = layer_by_name.get(str(name).strip())
                if layer_obj is None or hasattr(layer_obj, 'get_text_lines'):
                    continue
                targets.append(layer_obj)
            if not targets:
                _emit_size_match_trace(
                    f"任务={export_trace_task} 匹配关系 source={source_name} 原因=target_missing"
                )
                continue
            one_to_many = bool(relation.get('one_to_many', False))
            auto_rotate = bool(relation.get('auto_rotate', False))
            # 兼容旧数据：历史版本可能出现“多目标但one_to_many未开启”的关系。
            # 若仅按一对一处理会导致只有第一个目标层生效，其余图层位置/尺寸不匹配。
            effective_one_to_many = bool(one_to_many or len(targets) > 1)

            # 自动识别挖孔数量：一对多下，多余填充层自动隐藏
            if effective_one_to_many and (not holes):
                for target_layer in targets:
                    overrides[id(target_layer)] = {'visible': False}
                    _emit_size_match_trace(
                        f"任务={export_trace_task} source={source_name} target={getattr(target_layer, 'name', '')} "
                        f"孔位为空 -> hide"
                    )
                continue
            if not holes:
                _emit_size_match_trace(f"任务={export_trace_task} source={source_name} 孔位为空 -> 跳过")
                continue

            positions_info, _ = self._get_layer_positions_info_cached(source_layer, document)
            if not positions_info:
                continue
            source_x, source_y, _ = positions_info[0]
            padding = max(0, int(relation.get('padding', 1)))

            # 阶段1：只负责“目标图层 <-> 挖孔”配对，不参与任何角度计算
            if effective_one_to_many:
                # 过滤噪点内孔，优先选面积较大的有效孔，再按方向排序配对
                source_area = max(1, source_w * source_h)
                min_area = max(64, int(source_area * 0.0004))
                significant = [h for h in holes if int(h.get('area', 0)) >= min_area]
                if len(significant) < len(targets):
                    # 降低阈值重试，避免合法小孔被误滤掉导致“某一孔偶发不填充”
                    min_area_soft = max(16, int(source_area * 0.00008))
                    significant = [h for h in holes if int(h.get('area', 0)) >= min_area_soft]
                if len(significant) < len(targets):
                    # 仍不足时使用全部孔位，优先保证“识别出的孔位完整参与”
                    significant = list(holes)
                ordered_holes = self._sort_holes_left_to_right_then_top_to_bottom(significant)
                targets = self._sort_layers_left_to_right_then_top_to_bottom(targets)
                target_count = len(targets)
                hole_count = len(ordered_holes)
                pair_plan = []
                if hole_count <= 0:
                    pair_plan = []
                elif hole_count >= target_count:
                    # 孔位充足：按顺序一一配对
                    pair_plan = [(targets[i], ordered_holes[i]) for i in range(target_count)]
                else:
                    # 孔位不足：优先保证全部目标层有匹配，避免“一对多只生效第一个”
                    # 采用均匀复用映射，保持空间顺序语义
                    if target_count <= 1:
                        pair_plan = [(targets[0], ordered_holes[0])]
                    elif hole_count == 1:
                        pair_plan = [(t, ordered_holes[0]) for t in targets]
                    else:
                        for i, target_layer in enumerate(targets):
                            mapped = int(round((float(i) * float(hole_count - 1)) / float(target_count - 1)))
                            hole_idx = max(0, min(hole_count - 1, mapped))
                            pair_plan.append((target_layer, ordered_holes[hole_idx]))
            else:
                ordered_holes = self._sort_holes_left_to_right_then_top_to_bottom(holes)
                pair_plan = [(targets[0], ordered_holes[0])]

            # 阶段2：基于已完成配对的结果，逐孔计算旋转与尺寸
            for target_layer, hole in pair_plan:
                left, top, right, bottom = hole['bbox']
                rotation = None
                # 自动倾斜与一对多完全解耦：只要该孔角度可信，就独立应用其角度
                if auto_rotate and bool(hole.get('angle_valid', False)):
                    raw_angle = float(hole.get('angle_deg', 0.0))
                    base_rotation = float(getattr(target_layer, 'rotation', 0.0) or 0.0)
                    candidate_rotation = self._pick_min_delta_rotation(raw_angle, base_rotation)
                    delta_rotation = self._normalize_angle_180(candidate_rotation - base_rotation)
                    if abs(float(delta_rotation)) >= float(_AUTO_ROTATE_MIN_DEG):
                        rotation = candidate_rotation

                if auto_rotate and rotation is not None:
                    # 旋转匹配路径：使用孔中心 + 局部坐标系尺寸，避免按轴对齐 bbox 导致偏大/偏移
                    cx = float(hole.get('bbox_center_x', (left + right) * 0.5))
                    cy = float(hole.get('bbox_center_y', (top + bottom) * 0.5))
                    ow = int(hole.get('oriented_w', max(1, int(right - left))))
                    oh = int(hole.get('oriented_h', max(1, int(bottom - top))))
                    # 旋转时保守外扩 + 覆盖校验兜底，避免过度放大又防止留白
                    safety_expand = max(3, int(round(min(ow, oh) * 0.018)))
                    width = max(1, int(ow + padding * 2 + safety_expand * 2))
                    height = max(1, int(oh + padding * 2 + safety_expand * 2))
                    x = int(round(source_x + cx - (width * 0.5)))
                    y = int(round(source_y + cy - (height * 0.5)))
                else:
                    # 非旋转路径保持原逻辑，保证旧模板行为稳定
                    bw = max(1, int(right - left))
                    bh = max(1, int(bottom - top))
                    # 优先完整填充：非旋转路径也增加轻量外扩，避免留白/细缝
                    safety_expand = max(1, int(round(min(bw, bh) * 0.01)))
                    x = int(source_x + left - padding - safety_expand)
                    y = int(source_y + top - padding - safety_expand)
                    width = max(1, int(bw + padding * 2 + safety_expand * 2))
                    height = max(1, int(bh + padding * 2 + safety_expand * 2))

                # 透明检查兜底（几何版）：强制覆盖挖孔 bbox，避免残留透明
                x, y, width, height = self._ensure_rect_covers_hole_bbox(
                    source_x=source_x,
                    source_y=source_y,
                    hole_bbox=(left, top, right, bottom),
                    x=x,
                    y=y,
                    width=width,
                    height=height,
                    extra_margin=max(0, int(padding + (2 if (auto_rotate and rotation is not None) else 0)))
                )

                # 倾斜后保底：围绕中心轻量二次放大，消除极端模板边缘残留透明
                if auto_rotate and rotation is not None:
                    cx_box = float(x) + float(width) * 0.5
                    cy_box = float(y) + float(height) * 0.5
                    grow_scale = 1.05
                    width = max(1, int(math.ceil(float(width) * grow_scale)) + 2)
                    height = max(1, int(math.ceil(float(height) * grow_scale)) + 2)
                    x = int(round(cx_box - float(width) * 0.5))
                    y = int(round(cy_box - float(height) * 0.5))
                # 最终兜底外扩：优先保证“不留白”，允许轻微重叠
                final_guard = max(2, int(round(min(width, height) * 0.012)))
                if auto_rotate and rotation is not None:
                    final_guard += 2
                elif effective_one_to_many:
                    final_guard += 1
                if final_guard > 0:
                    cx_box = float(x) + float(width) * 0.5
                    cy_box = float(y) + float(height) * 0.5
                    width = max(1, int(width + final_guard * 2))
                    height = max(1, int(height + final_guard * 2))
                    x = int(round(cx_box - float(width) * 0.5))
                    y = int(round(cy_box - float(height) * 0.5))

                overrides[id(target_layer)] = {
                    'x': x,
                    'y': y,
                    'width': width,
                    'height': height,
                    'rotation': rotation,
                }
                _emit_size_match_trace(
                    f"任务={export_trace_task} source={source_name} target={getattr(target_layer, 'name', '')} "
                    f"孔位bbox=({left},{top},{right},{bottom}) 最终匹配矩形=({x},{y},{width},{height}) "
                    f"旋转={rotation}"
                )

        return overrides

    def _detect_inner_holes(self, image: Image.Image, alpha_threshold: int = 6):
        """检测所有内孔并返回边界、面积与角度信息。"""
        try:
            if image.mode != 'RGBA':
                image = image.convert('RGBA')
            alpha = np.array(image.split()[3])
            if alpha.size == 0:
                return []

            transparent = alpha <= int(alpha_threshold)
            if not transparent.any():
                return []

            # 修复偶发漏检：若边框存在极细裂缝，外部背景会“漏进”内孔导致孔丢失
            # 先对不透明区域做轻量闭运算，再反推透明区域，可显著提升稳定性。
            try:
                opaque = alpha > int(alpha_threshold)
                if opaque.any():
                    opaque = self._close_opaque_mask(opaque)
                    transparent = ~opaque
            except Exception:
                pass

            h, w = transparent.shape
            background = np.zeros_like(transparent, dtype=bool)
            q = deque()

            for x in range(w):
                if transparent[0, x]:
                    background[0, x] = True
                    q.append((0, x))
                if transparent[h - 1, x] and not background[h - 1, x]:
                    background[h - 1, x] = True
                    q.append((h - 1, x))
            for y in range(h):
                if transparent[y, 0] and not background[y, 0]:
                    background[y, 0] = True
                    q.append((y, 0))
                if transparent[y, w - 1] and not background[y, w - 1]:
                    background[y, w - 1] = True
                    q.append((y, w - 1))

            while q:
                cy, cx = q.popleft()
                for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                    if ny < 0 or ny >= h or nx < 0 or nx >= w:
                        continue
                    if background[ny, nx] or (not transparent[ny, nx]):
                        continue
                    background[ny, nx] = True
                    q.append((ny, nx))

            holes = transparent & (~background)
            if not holes.any():
                return []

            visited = np.zeros_like(holes, dtype=bool)
            result = []
            ys, xs = np.where(holes)
            for y0, x0 in zip(ys, xs):
                if visited[y0, x0]:
                    continue
                q = deque([(y0, x0)])
                visited[y0, x0] = True
                area = 0
                min_x = max_x = x0
                min_y = max_y = y0
                points_xy = []

                while q:
                    cy, cx = q.popleft()
                    area += 1
                    points_xy.append((cx, cy))
                    if cx < min_x:
                        min_x = cx
                    if cx > max_x:
                        max_x = cx
                    if cy < min_y:
                        min_y = cy
                    if cy > max_y:
                        max_y = cy
                    for ny, nx in ((cy - 1, cx), (cy + 1, cx), (cy, cx - 1), (cy, cx + 1)):
                        if ny < 0 or ny >= h or nx < 0 or nx >= w:
                            continue
                        if visited[ny, nx] or (not holes[ny, nx]):
                            continue
                        visited[ny, nx] = True
                        q.append((ny, nx))

                bw = max_x - min_x + 1
                bh = max_y - min_y + 1
                bbox_area = max(1, bw * bh)
                fill_ratio = float(area) / float(bbox_area)
                rect_like = (fill_ratio >= 0.55 and area >= 30 and bw >= 8 and bh >= 8)
                angle_deg = 0.0
                angle_valid = False
                oriented_w = max(1, int(bw))
                oriented_h = max(1, int(bh))
                center_x = float((min_x + max_x) / 2.0)
                center_y = float((min_y + max_y) / 2.0)
                bbox_center_x = float((min_x + max_x) / 2.0)
                bbox_center_y = float((min_y + max_y) / 2.0)
                if area >= 20 and bw >= 6 and bh >= 6:
                    arr = np.asarray(points_xy, dtype=np.float32)
                    mx = float(np.mean(arr[:, 0]))
                    my = float(np.mean(arr[:, 1]))
                    center_x = float(mx)
                    center_y = float(my)
                    dx = arr[:, 0] - mx
                    dy = arr[:, 1] - my
                    cov_xx = float(np.mean(dx * dx))
                    cov_yy = float(np.mean(dy * dy))
                    cov_xy = float(np.mean(dx * dy))
                    area_anisotropy = abs(cov_xx - cov_yy) / max(1e-6, (cov_xx + cov_yy))
                    area_raw_angle = math.degrees(0.5 * math.atan2(2.0 * cov_xy, cov_xx - cov_yy))

                    # 边界主轴通常比区域主轴更贴近“孔框方向”，可提升倾角稳定性
                    boundary_points = []
                    for px, py in points_xy:
                        if (
                            px <= 0 or py <= 0 or px >= (w - 1) or py >= (h - 1)
                            or (not holes[py - 1, px]) or (not holes[py + 1, px])
                            or (not holes[py, px - 1]) or (not holes[py, px + 1])
                        ):
                            boundary_points.append((px, py))
                    boundary_anisotropy = 0.0
                    boundary_raw_angle = area_raw_angle
                    if len(boundary_points) >= 16:
                        barr = np.asarray(boundary_points, dtype=np.float32)
                        bmx = float(np.mean(barr[:, 0]))
                        bmy = float(np.mean(barr[:, 1]))
                        bdx = barr[:, 0] - bmx
                        bdy = barr[:, 1] - bmy
                        bcov_xx = float(np.mean(bdx * bdx))
                        bcov_yy = float(np.mean(bdy * bdy))
                        bcov_xy = float(np.mean(bdx * bdy))
                        boundary_anisotropy = abs(bcov_xx - bcov_yy) / max(1e-6, (bcov_xx + bcov_yy))
                        boundary_raw_angle = math.degrees(0.5 * math.atan2(2.0 * bcov_xy, bcov_xx - bcov_yy))

                    aspect = max(float(bw), float(bh)) / max(1.0, min(float(bw), float(bh)))
                    use_boundary = bool(boundary_anisotropy >= area_anisotropy * 0.92 and len(boundary_points) >= 16)
                    chosen_raw_angle = boundary_raw_angle if use_boundary else area_raw_angle
                    chosen_anisotropy = max(area_anisotropy, boundary_anisotropy)
                    angle_deg, est_w, est_h, area_gain = self._estimate_tilt_from_min_rect(
                        points_xy=points_xy,
                        center_x=center_x,
                        center_y=center_y,
                        axis_w=bw,
                        axis_h=bh,
                        seed_angle_deg=chosen_raw_angle
                    )

                    # 近似正方形且各向异性弱时，不做自动倾斜，避免误判
                    if aspect < 1.10 and chosen_anisotropy < 0.028:
                        angle_deg = 0.0
                        angle_valid = False
                    else:
                        # 防误判：
                        # 1) 小角度死区（<4°）视为不倾斜
                        # 2) 旋转收益很小（局部包围面积改善不足）也视为不倾斜
                        if abs(float(angle_deg)) < float(_AUTO_ROTATE_MIN_DEG) or area_gain < 0.015:
                            angle_deg = 0.0
                            angle_valid = False
                        else:
                            angle_valid = True
                            oriented_w = int(est_w)
                            oriented_h = int(est_h)

                result.append({
                    'bbox': (min_x, min_y, max_x + 1, max_y + 1),
                    'area': int(area),
                    'bbox_w': int(bw),
                    'bbox_h': int(bh),
                    'shape_type': self._classify_hole_shape(bw, bh),
                    'center_x': float(center_x),
                    'center_y': float(center_y),
                    'bbox_center_x': float(bbox_center_x),
                    'bbox_center_y': float(bbox_center_y),
                    'rect_like': bool(rect_like),
                    'angle_valid': bool(angle_valid),
                    'angle_deg': float(angle_deg),
                    'oriented_w': int(oriented_w),
                    'oriented_h': int(oriented_h),
                })

            return result
        except Exception:
            return []

    def _get_inner_holes_cached(self, source_layer, document, was_just_loaded: bool = False):
        """获取内孔检测结果缓存，降低预览时重复连通域分析开销。"""
        try:
            source_surface_key = self._build_layer_surface_key(source_layer, document, was_just_loaded)
        except Exception:
            source_surface_key = f"fallback_{id(source_layer)}"
        cache_key = f"{id(document)}:{id(source_layer)}:{source_surface_key}:{_SIZE_MATCH_HOLE_DETECT_VER}"

        with self._size_match_holes_lock:
            cached = self._size_match_holes_cache.get(cache_key)
            if cached is not None:
                self._size_match_holes_cache.move_to_end(cache_key)
                return [dict(h) for h in cached]

        source_image = self._get_layer_surface_cached(source_layer, document, was_just_loaded)
        if source_image is None:
            return []
        holes = self._detect_inner_holes(source_image)
        holes = self._refine_holes_with_adaptive_alpha_threshold(source_image, holes)

        with self._size_match_holes_lock:
            self._size_match_holes_cache[cache_key] = [dict(h) for h in holes]
            self._size_match_holes_cache.move_to_end(cache_key)
            while len(self._size_match_holes_cache) > self._max_size_match_holes_entries:
                self._size_match_holes_cache.popitem(last=False)
        return holes

    def _refine_holes_with_adaptive_alpha_threshold(self, source_image: Image.Image, holes):
        """
        对“半透明孔位”做自适应阈值回退，避免孔 bbox 被误识别成细条。
        场景：模板孔位存在羽化/半透明边缘，固定阈值(<=6)会低估孔尺寸。
        """
        try:
            if source_image is None:
                return holes or []
            source_w = int(getattr(source_image, 'width', 0) or 0)
            source_h = int(getattr(source_image, 'height', 0) or 0)
            source_area = max(1, source_w * source_h)

            base_holes = list(holes or [])
            base_total = int(sum(max(0, int(h.get('area', 0))) for h in base_holes))

            # 经验阈值：当已识别面积足够时，不做额外回退，避免无谓计算
            if base_holes and base_total >= int(source_area * 0.015):
                return base_holes

            best_holes = base_holes
            best_total = base_total
            # 从保守到激进逐步放宽透明阈值
            candidate_thresholds = (12, 20, 28, 36, 48, 64, 80, 96)

            for th in candidate_thresholds:
                candidate = self._detect_inner_holes(source_image, alpha_threshold=int(th))
                if not candidate:
                    continue
                total_area = int(sum(max(0, int(h.get('area', 0))) for h in candidate))
                if total_area <= best_total:
                    continue
                # 防止阈值过高把大块区域误识别为孔位
                if total_area >= int(source_area * 0.82):
                    continue
                max_area = max([int(h.get('area', 0)) for h in candidate] or [0])
                if max_area < int(source_area * 0.002):
                    continue
                best_holes = candidate
                best_total = total_area

            return best_holes
        except Exception:
            return holes or []

    def _build_layer_positions_key(self, layer, document) -> str:
        """构建图层位置缓存键（仅包含影响分身/填充位置的参数）"""
        try:
            parts = [
                f"doc:{id(document)}",
                f"layer:{id(layer)}",
                f"canvas:{document.canvas_width}x{document.canvas_height}",
                f"base:{getattr(layer, 'x', 0)},{getattr(layer, 'y', 0)}",
                f"size:{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}",
                f"clone:{int(bool(getattr(layer, 'clone_enabled', False)))}",
                f"fill:{int(bool(getattr(layer, 'clone_fill_enabled', False)))}",
                f"fill_spacing:{getattr(layer, 'clone_fill_spacing', 0)}",
                f"fill_angle:{float(getattr(layer, 'clone_fill_angle', 0.0)):.3f}",
                f"fill_mode:{getattr(layer, 'clone_fill_mode', 'grid')}",
                f"fill_margin:{getattr(layer, 'clone_fill_margin', 0)}",
                f"mirror:{getattr(layer, 'clone_mirror_mode', 'none')}",
                f"rnd_dx:{getattr(layer, '_current_random_offset_x', 0)}",
                f"rnd_dy:{getattr(layer, '_current_random_offset_y', 0)}",
                f"rnd_scale:{float(getattr(layer, '_current_random_scale', 1.0)):.6f}",
                f"rnd_rot:{float(getattr(layer, '_current_random_rotation', 0.0)):.3f}",
            ]
            return hashlib.md5("|".join([str(p) for p in parts]).encode('utf-8')).hexdigest()
        except Exception:
            return f"fallback_layer_positions_{id(layer)}_{time.time()}"

    def _get_layer_positions_info_cached(self, layer, document):
        """获取图层位置缓存，必要时重新计算"""
        cache_key = self._build_layer_positions_key(layer, document)
        entry_key = f"{id(document)}:{id(layer)}"
        with self._layer_positions_lock:
            entry = self._layer_positions_cache.get(entry_key)
            if entry and entry.get("cache_key") == cache_key:
                self._layer_positions_cache.move_to_end(entry_key)
                positions_info = entry.get("positions_info", [])
                mirror_mode = entry.get("mirror_mode", "none")
                return positions_info[:], mirror_mode

        positions_info, mirror_mode = self._calculate_layer_positions_info(layer, document)
        with self._layer_positions_lock:
            self._layer_positions_cache[entry_key] = {
                "cache_key": cache_key,
                "positions_info": positions_info[:],
                "mirror_mode": mirror_mode
            }
            self._layer_positions_cache.move_to_end(entry_key)
            while len(self._layer_positions_cache) > self._max_layer_positions_entries:
                self._layer_positions_cache.popitem(last=False)
        return positions_info, mirror_mode

    def _calculate_layer_positions_info(self, layer, document):
        """计算图层分身/填充位置信息"""
        clone_positions = []
        is_clone_enabled = hasattr(layer, 'clone_enabled') and layer.clone_enabled
        if is_clone_enabled and hasattr(layer, 'get_effective_clone_positions'):
            try:
                clone_positions = layer.get_effective_clone_positions()
            except Exception as e:
                print(f"[快速渲染] 获取分身位置失败: {e}")
                if hasattr(layer, 'get_effective_position'):
                    clone_positions = [layer.get_effective_position()]
                else:
                    clone_positions = [(getattr(layer, 'x', 0), getattr(layer, 'y', 0))]
        else:
            if hasattr(layer, 'get_effective_position'):
                clone_positions = [layer.get_effective_position()]
            else:
                clone_positions = [(getattr(layer, 'x', 0), getattr(layer, 'y', 0))]

        fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
        if fill_enabled:
            spacing = int(getattr(layer, 'clone_fill_spacing', 0))
            angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
            mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
            dx = max(1, int(getattr(layer, 'width', 0) + spacing))
            dy = max(1, int(getattr(layer, 'height', 0) + spacing))
            positions = []
            cx = document.canvas_width / 2.0
            cy = document.canvas_height / 2.0
            base_x = getattr(layer, 'x', 0)
            base_y = getattr(layer, 'y', 0)
            import math
            angle = math.radians(angle_deg % 360.0)
            start_y = -getattr(layer, 'height', 0)
            end_y = document.canvas_height + getattr(layer, 'height', 0)
            if mode == 'border':
                w = getattr(layer, 'width', 0)
                h = getattr(layer, 'height', 0)
                margin = int(getattr(layer, 'clone_fill_margin', 0))
                effective_width = document.canvas_width - 2 * margin
                effective_height = document.canvas_height - 2 * margin
                top_bottom_count = max(2, (effective_width + dx) // dx)
                left_right_count = max(2, (effective_height + dy) // dy)
                top_bottom_spacing = (effective_width - w) / (top_bottom_count - 1) if top_bottom_count > 1 else 0
                left_right_spacing = (effective_height - h) / (left_right_count - 1) if left_right_count > 1 else 0
                for i in range(top_bottom_count):
                    x = margin + int(i * top_bottom_spacing)
                    if x <= document.canvas_width - w - margin:
                        positions.append((x, margin))
                for i in range(top_bottom_count):
                    x = margin + int(i * top_bottom_spacing)
                    if x <= document.canvas_width - w - margin:
                        positions.append((x, document.canvas_height - h - margin))
                for i in range(1, left_right_count - 1):
                    y = margin + int(i * left_right_spacing)
                    if margin < y < document.canvas_height - h - margin:
                        positions.append((margin, y))
                for i in range(1, left_right_count - 1):
                    y = margin + int(i * left_right_spacing)
                    if margin < y < document.canvas_height - h - margin:
                        positions.append((document.canvas_width - w - margin, y))
            else:
                step_y = dy
                i_row = 0
                for row_y in range(start_y, end_y + 1, step_y):
                    offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                    for col_x in range(-getattr(layer, 'width', 0), document.canvas_width + getattr(layer, 'width', 0) + 1, dx):
                        x0 = base_x + col_x + offset
                        y0 = base_y + row_y
                        if angle != 0.0:
                            rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                            ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                            x = int(rx)
                            y = int(ry)
                        else:
                            x = x0
                            y = y0
                        positions.append((x, y))
                    i_row += 1
            clone_positions = positions if positions else clone_positions

        positions_info = [(x, y, False) for (x, y) in clone_positions]
        mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
        if mirror_mode and mirror_mode != 'none':
            base = clone_positions[:]
            min_x = min([x for x, _ in base])
            max_x = max([x + layer.width for x, _ in base])
            min_y = min([y for _, y in base])
            max_y = max([y + layer.height for _, y in base])
            group_width = max_x - min_x
            group_height = max_y - min_y
            if mirror_mode == 'horizontal':
                mirrored_left = document.canvas_width - (min_x + group_width)
                for x, y in base:
                    offset_x = x - min_x
                    positions_info.append((mirrored_left + offset_x, y, True))
            elif mirror_mode == 'vertical':
                mirrored_top = document.canvas_height - (min_y + group_height)
                for x, y in base:
                    offset_y = y - min_y
                    positions_info.append((x, mirrored_top + offset_y, True))
        return positions_info, mirror_mode

    def _build_layer_surface_key(self, layer, document, was_just_loaded: bool = False) -> str:
        """构建图层surface缓存键（仅包含影响图层图像像素的参数）"""
        try:
            layer_parts = [
                "vec_pipe_ver:v5",
                f"src:{getattr(layer, 'image_source', '')}",
                f"current:{getattr(layer, '_current_image_path', '') or getattr(layer, 'current_image_path', '')}",
                f"size:{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}",
                f"fit:{getattr(layer, 'fit_mode', 0)}",
                f"crop:{getattr(layer, 'crop_direction', 0)}",
                f"use_orig:{int(bool(getattr(layer, 'use_original_size', False)))}",
                f"flip_h:{int(bool(getattr(layer, 'flip_horizontal', False)))}",
                f"flip_v:{int(bool(getattr(layer, 'flip_vertical', False)))}",
                f"rot:{float(getattr(layer, 'rotation', 0.0)):.3f}",
                # 样式参数（关键：缺失会导致圆角/描边更新后仍命中旧缓存）
                f"corner:{int(getattr(layer, 'corner_radius', getattr(layer, '_corner_radius', 0)))}",
                f"stroke_on:{int(bool(getattr(layer, 'stroke_enabled', getattr(layer, '_stroke_enabled', False))))}",
                f"stroke_type:{int(getattr(layer, 'stroke_type', getattr(layer, '_stroke_type', 0)))}",
                f"stroke_w:{int(getattr(layer, 'stroke_width', getattr(layer, '_stroke_width', 0)))}",
                f"stroke_c:{str(getattr(layer, 'stroke_color', getattr(layer, '_stroke_color', (0, 0, 0, 255))))}",
                f"overlay_on:{int(bool(getattr(layer, 'color_overlay_enabled', getattr(layer, '_color_overlay_enabled', False))))}",
                f"overlay_c:{str(getattr(layer, 'color_overlay_color', getattr(layer, '_color_overlay_color', (255, 255, 255, 255))))}",
                f"overlay_op:{float(getattr(layer, 'color_overlay_opacity', getattr(layer, '_color_overlay_opacity', 1.0))):.4f}",
                f"grad_on:{int(bool(getattr(layer, 'gradient_overlay_enabled', getattr(layer, '_gradient_overlay_enabled', False))))}",
                f"grad_colors:{str(getattr(layer, 'gradient_overlay_colors', getattr(layer, '_gradient_overlay_colors', [])))}",
                f"grad_angle:{float(getattr(layer, 'gradient_overlay_angle', getattr(layer, '_gradient_overlay_angle', 0.0))):.3f}",
                f"grad_op:{float(getattr(layer, 'gradient_overlay_opacity', getattr(layer, '_gradient_overlay_opacity', 1.0))):.4f}",
                f"rnd_dx:{getattr(layer, '_current_random_offset_x', 0)}",
                f"rnd_dy:{getattr(layer, '_current_random_offset_y', 0)}",
                f"rnd_scale:{float(getattr(layer, '_current_random_scale', 1.0)):.6f}",
                f"rnd_rot:{float(getattr(layer, '_current_random_rotation', 0.0)):.3f}",
                f"text:{hashlib.md5(str(getattr(layer, 'current_text', '')).encode('utf-8')).hexdigest()[:8]}",
                f"shape:{getattr(getattr(layer, 'shape_type', ''), 'value', getattr(layer, 'shape_type', ''))}",
                f"trap:{getattr(layer, 'trapezoid_top_width', '')},{getattr(layer, 'trapezoid_bottom_width', '')},{getattr(layer, 'trapezoid_slope_side', '')}",
                f"poly:{getattr(layer, 'polygon_rotation', '')},{getattr(layer, 'polygon_corner_radius', '')}",
            ]
            self._append_text_surface_key_parts(layer, layer_parts)
            raw_key = "|".join([str(p) for p in layer_parts])
            return hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        except Exception:
            return f"fallback_layer_surface_{id(layer)}_{time.time()}"

    def _append_text_surface_key_parts(self, layer, parts):
        """Add text-layer fields that change rendered pixels to a surface key."""
        if not hasattr(layer, 'current_text') and not hasattr(layer, 'get_text_lines'):
            return
        text_lines = getattr(layer, 'text_lines', None)
        if text_lines is None and hasattr(layer, 'get_text_lines'):
            try:
                text_lines = layer.get_text_lines()
            except Exception:
                text_lines = None
        parts.extend([
            f"text_lines:{hashlib.md5(str(text_lines or '').encode('utf-8')).hexdigest()[:10]}",
            f"font_family:{getattr(layer, 'font_family', '')}",
            f"font_size:{getattr(layer, 'font_size', '')}",
            f"font_style:{getattr(layer, 'font_style', '')}",
            f"text_color:{getattr(layer, 'text_color', '')}",
            f"text_color_ranges:{getattr(layer, 'text_color_ranges', getattr(layer, '_text_color_ranges', []))}",
            f"text_align:{getattr(layer, 'text_align', '')}",
            f"line_spacing:{getattr(layer, 'line_spacing', '')}",
            f"letter_spacing:{getattr(layer, 'letter_spacing', '')}",
            f"text_padding:{getattr(layer, 'text_box_padding', '')}",
            f"auto_fit:{int(bool(getattr(layer, 'auto_fit_text_box', False)))}",
            f"vertical:{int(bool(getattr(layer, 'vertical_layout', False)))}",
            f"text_gradient:{int(bool(getattr(layer, 'gradient_enabled', False)))}",
            f"text_gradient_type:{getattr(layer, 'gradient_type', '')}",
            f"text_gradient_dir:{getattr(layer, 'gradient_direction', '')}",
            f"text_gradient_angle:{getattr(layer, 'gradient_angle', '')}",
            f"text_gradient_start:{getattr(layer, 'gradient_start_color', '')}",
            f"text_gradient_end:{getattr(layer, 'gradient_end_color', '')}",
            f"text_gradient_center:{getattr(layer, 'gradient_center_x', '')},{getattr(layer, 'gradient_center_y', '')}",
            f"text_bg:{int(bool(getattr(layer, 'background_enabled', False)))}",
            f"text_bg_color:{getattr(layer, 'background_color', '')}",
            f"text_bg_padding:{getattr(layer, 'background_padding', '')}",
            f"supersample:{int(bool(getattr(layer, 'supersample_enabled', False)))}:{getattr(layer, 'supersample_scale', '')}",
            f"shadow:{int(bool(getattr(layer, 'shadow_enabled', False)))}:{getattr(layer, 'shadow_offset_x', '')}:{getattr(layer, 'shadow_offset_y', '')}:{getattr(layer, 'shadow_blur', '')}:{getattr(layer, 'shadow_color', '')}",
            f"glow:{int(bool(getattr(layer, 'glow_enabled', False)))}:{getattr(layer, 'glow_strength', '')}:{getattr(layer, 'glow_radius', '')}",
        ])

    def _get_layer_surface_cached(self, layer, document, was_just_loaded: bool = False) -> Optional[Image.Image]:
        """获取图层surface缓存；未命中时重新生成并缓存"""
        cache_key = self._build_layer_surface_key(layer, document, was_just_loaded)
        is_batch_session = bool(getattr(document, '_is_batch_export_running', False))
        entry_key = f"{id(document)}:{id(layer)}"
        export_entry_key = f"export:{cache_key}"

        if is_batch_session:
            with self._export_layer_surface_lock:
                export_entry = self._export_layer_surface_cache.get(export_entry_key)
                if export_entry:
                    self._export_layer_surface_cache.move_to_end(export_entry_key)
                    export_image = export_entry.get("image")
                    if export_image is not None:
                        setattr(layer, "_render_offset_x", int(export_entry.get("offset_x", 0)))
                        setattr(layer, "_render_offset_y", int(export_entry.get("offset_y", 0)))
                        FastRenderer._inc_batch_metric("export_layer_cache_hits")
                        return export_image.copy()
            FastRenderer._inc_batch_metric("export_layer_cache_misses")

        with self._layer_surface_lock:
            entry = self._layer_surface_cache.get(entry_key)
            if entry and entry.get("cache_key") == cache_key:
                self._layer_surface_cache.move_to_end(entry_key)
                image = entry.get("image")
                if image is not None:
                    setattr(layer, "_render_offset_x", int(entry.get("offset_x", 0)))
                    setattr(layer, "_render_offset_y", int(entry.get("offset_y", 0)))
                    if is_batch_session:
                        FastRenderer._inc_batch_metric("layer_surface_cache_hits")
                    return image.copy()
        if is_batch_session:
            FastRenderer._inc_batch_metric("layer_surface_cache_misses")

        layer_image = self._get_layer_image(layer, document, was_just_loaded)
        if layer_image is None:
            return None

        if hasattr(layer, 'apply_effects') and callable(layer.apply_effects):
            if is_batch_session:
                FastRenderer._inc_batch_metric("apply_effects_calls")
            layer_image = layer.apply_effects(layer_image)
            if layer_image is None:
                return None

        if is_batch_session:
            with self._export_layer_surface_lock:
                self._set_cache_value_unlocked(
                    self._export_layer_surface_cache,
                    self._export_layer_surface_entry_bytes,
                    "_export_layer_surface_bytes",
                    export_entry_key,
                    {
                        "cache_key": cache_key,
                        "image": layer_image.copy(),
                        "offset_x": int(getattr(layer, "_render_offset_x", 0)),
                        "offset_y": int(getattr(layer, "_render_offset_y", 0)),
                    },
                    self._max_export_layer_surface_entries,
                    self._max_export_layer_surface_bytes,
                )

        with self._layer_surface_lock:
            self._layer_surface_cache[entry_key] = {
                "cache_key": cache_key,
                "image": layer_image.copy(),
                "offset_x": int(getattr(layer, "_render_offset_x", 0)),
                "offset_y": int(getattr(layer, "_render_offset_y", 0)),
            }
            self._layer_surface_cache.move_to_end(entry_key)
            while len(self._layer_surface_cache) > self._max_layer_surface_entries:
                self._layer_surface_cache.popitem(last=False)

        return layer_image

    def _clear_layer_surface_cache(self):
        """清空图层surface缓存"""
        with self._layer_surface_lock:
            self._layer_surface_cache.clear()
        with self._export_layer_surface_lock:
            self._clear_budgeted_cache_unlocked(
                self._export_layer_surface_cache,
                self._export_layer_surface_entry_bytes,
                "_export_layer_surface_bytes",
            )
    
    def _clear_layer_positions_cache(self):
        """清空图层位置缓存"""
        with self._layer_positions_lock:
            self._layer_positions_cache.clear()

    def _clear_interactive_base_cache(self):
        """清空交互增量预览底图缓存"""
        with self._interactive_base_lock:
            self._interactive_base_cache.clear()

    def _clear_interactive_layer_surface_cache(self):
        """清空交互活动图层缓存（变换优先路径）。"""
        with self._interactive_layer_surface_lock:
            self._interactive_layer_surface_cache.clear()

    def _clear_size_match_caches(self):
        """清空大小匹配相关缓存。"""
        with self._size_match_holes_lock:
            self._size_match_holes_cache.clear()
        with self._size_override_surface_lock:
            self._size_override_surface_cache.clear()

    def _invalidate_interactive_base_for_document(self, document):
        """清理指定文档的交互底图缓存"""
        doc_prefix = f"{id(document)}:"
        with self._interactive_base_lock:
            keys_to_remove = [k for k in self._interactive_base_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._interactive_base_cache.pop(k, None)

    def _invalidate_interactive_layer_surfaces_for_document(self, document):
        """清理指定文档的交互活动图层缓存。"""
        doc_prefix = f"{id(document)}:"
        with self._interactive_layer_surface_lock:
            keys_to_remove = [
                k for k in self._interactive_layer_surface_cache.keys()
                if str(k).startswith(doc_prefix)
            ]
            for k in keys_to_remove:
                self._interactive_layer_surface_cache.pop(k, None)

    def _invalidate_size_match_caches_for_document(self, document):
        """仅清理指定文档的大小匹配缓存。"""
        doc_prefix = f"{id(document)}:"
        with self._size_match_holes_lock:
            keys_to_remove = [k for k in self._size_match_holes_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._size_match_holes_cache.pop(k, None)
        with self._size_override_surface_lock:
            keys_to_remove = [k for k in self._size_override_surface_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._size_override_surface_cache.pop(k, None)

    def _clear_batch_session_caches(self):
        """清空批量导出会话缓存。"""
        with self._batch_raw_image_lock:
            self._clear_budgeted_cache_unlocked(
                self._batch_raw_image_cache,
                self._batch_raw_image_entry_bytes,
                "_batch_raw_image_bytes",
            )
        with self._batch_processed_image_lock:
            self._clear_budgeted_cache_unlocked(
                self._batch_processed_image_cache,
                self._batch_processed_image_entry_bytes,
                "_batch_processed_image_bytes",
            )
        with self._export_layer_surface_lock:
            self._clear_budgeted_cache_unlocked(
                self._export_layer_surface_cache,
                self._export_layer_surface_entry_bytes,
                "_export_layer_surface_bytes",
            )

    def _invalidate_batch_session_caches_for_document(self, document):
        """清理指定文档的批量导出会话缓存。"""
        doc_prefix = f"{id(document)}:"
        with self._batch_raw_image_lock:
            keys_to_remove = [k for k in self._batch_raw_image_cache.keys() if str(k).startswith(doc_prefix)]
            self._remove_cache_keys_unlocked(
                self._batch_raw_image_cache,
                self._batch_raw_image_entry_bytes,
                "_batch_raw_image_bytes",
                keys_to_remove,
            )
        with self._batch_processed_image_lock:
            keys_to_remove = [k for k in self._batch_processed_image_cache.keys() if str(k).startswith(doc_prefix)]
            self._remove_cache_keys_unlocked(
                self._batch_processed_image_cache,
                self._batch_processed_image_entry_bytes,
                "_batch_processed_image_bytes",
                keys_to_remove,
            )

    def _get_batch_processed_cache_key(self, document, layer, image_path: str) -> str:
        parts = [
            f"{id(document)}",
            f"path:{image_path}",
            f"size:{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}",
            f"fit:{getattr(layer, 'fit_mode', 0)}",
            f"crop:{getattr(layer, 'crop_direction', 0)}",
            f"use_orig:{int(bool(getattr(layer, 'use_original_size', False)))}",
            f"rot:{float(getattr(layer, 'rotation', 0.0)):.3f}",
            f"flip_h:{int(bool(getattr(layer, 'flip_horizontal', False)))}",
            f"flip_v:{int(bool(getattr(layer, 'flip_vertical', False)))}",
            f"rnd_scale:{float(getattr(layer, '_current_random_scale', 1.0)):.6f}",
            f"rnd_rot:{float(getattr(layer, '_current_random_rotation', 0.0)):.3f}",
        ]
        return "|".join([str(p) for p in parts])

    def _build_layer_interactive_surface_key(self, layer, document, was_just_loaded: bool = False) -> str:
        """构建交互活动图层缓存键（只包含几何与变换所需字段）。"""
        try:
            parts = [
                f"src:{getattr(layer, 'image_source', '')}",
                f"current:{getattr(layer, '_current_image_path', '') or getattr(layer, 'current_image_path', '')}",
                f"size:{getattr(layer, 'width', 0)}x{getattr(layer, 'height', 0)}",
                f"fit:{getattr(layer, 'fit_mode', 0)}",
                f"crop:{getattr(layer, 'crop_direction', 0)}",
                f"use_orig:{int(bool(getattr(layer, 'use_original_size', False)))}",
                f"flip_h:{int(bool(getattr(layer, 'flip_horizontal', False)))}",
                f"flip_v:{int(bool(getattr(layer, 'flip_vertical', False)))}",
                f"rot:{float(getattr(layer, 'rotation', 0.0)):.3f}",
                f"rnd_scale:{float(getattr(layer, '_current_random_scale', 1.0)):.6f}",
                f"rnd_rot:{float(getattr(layer, '_current_random_rotation', 0.0)):.3f}",
                f"shape:{getattr(getattr(layer, 'shape_type', ''), 'value', getattr(layer, 'shape_type', ''))}",
                f"trap:{getattr(layer, 'trapezoid_top_width', '')},{getattr(layer, 'trapezoid_bottom_width', '')},{getattr(layer, 'trapezoid_slope_side', '')}",
                f"poly:{getattr(layer, 'polygon_rotation', '')},{getattr(layer, 'polygon_corner_radius', '')}",
                f"stroke_on:{int(bool(getattr(layer, 'stroke_enabled', getattr(layer, '_stroke_enabled', False))))}",
                f"stroke_w:{int(getattr(layer, 'stroke_width', getattr(layer, '_stroke_width', 0)))}",
                f"stroke_c:{str(getattr(layer, 'stroke_color', getattr(layer, '_stroke_color', (0, 0, 0, 255))))}",
                f"overlay_on:{int(bool(getattr(layer, 'color_overlay_enabled', getattr(layer, '_color_overlay_enabled', False))))}",
                f"overlay_c:{str(getattr(layer, 'color_overlay_color', getattr(layer, '_color_overlay_color', (255, 255, 255, 255))))}",
                f"overlay_op:{float(getattr(layer, 'color_overlay_opacity', getattr(layer, '_color_overlay_opacity', 1.0))):.4f}",
                f"grad_on:{int(bool(getattr(layer, 'gradient_overlay_enabled', getattr(layer, '_gradient_overlay_enabled', False))))}",
                f"grad_colors:{str(getattr(layer, 'gradient_overlay_colors', getattr(layer, '_gradient_overlay_colors', [])))}",
                f"grad_angle:{float(getattr(layer, 'gradient_overlay_angle', getattr(layer, '_gradient_overlay_angle', 0.0))):.3f}",
                f"grad_op:{float(getattr(layer, 'gradient_overlay_opacity', getattr(layer, '_gradient_overlay_opacity', 1.0))):.4f}",
                f"just_loaded:{int(bool(was_just_loaded))}",
            ]
            self._append_text_surface_key_parts(layer, parts)
            raw_key = "|".join([str(p) for p in parts])
            return hashlib.md5(raw_key.encode('utf-8')).hexdigest()
        except Exception:
            return f"fallback_interactive_surface_{id(layer)}_{time.time()}"

    def _apply_interactive_transform_only(self, layer, image: Image.Image) -> Optional[Image.Image]:
        """交互期仅应用必要几何：形状裁切 + 变换；跳过描边/叠加等重特效。"""
        if image is None:
            return None
        try:
            result = image.convert('RGBA') if image.mode != 'RGBA' else image.copy()

            shape_type_val = getattr(getattr(layer, 'shape_type', None), 'value', getattr(layer, 'shape_type', ''))
            has_non_rect_shape = str(shape_type_val) not in ("", "rectangle", "ShapeType.RECTANGLE")
            if has_non_rect_shape and hasattr(layer, '_apply_shape_mask') and callable(getattr(layer, '_apply_shape_mask', None)):
                try:
                    result = layer._apply_shape_mask(result)
                except Exception:
                    # 形状裁切失败时保守回退原图，避免交互中断
                    pass

            if hasattr(layer, '_apply_transformations') and callable(getattr(layer, '_apply_transformations', None)):
                result = layer._apply_transformations(result)

            return result
        except Exception:
            return image

    def _get_layer_surface_interactive_cached(self, layer, document, was_just_loaded: bool = False) -> Optional[Image.Image]:
        """获取交互期活动图层surface：仅重算几何/变换，跳过复杂特效。"""
        cache_key = self._build_layer_interactive_surface_key(layer, document, was_just_loaded)
        entry_key = f"{id(document)}:{id(layer)}"

        with self._interactive_layer_surface_lock:
            entry = self._interactive_layer_surface_cache.get(entry_key)
            if entry and entry.get("cache_key") == cache_key:
                self._interactive_layer_surface_cache.move_to_end(entry_key)
                cached = entry.get("image")
                if cached is not None:
                    return cached.copy()

        base_image = self._get_interactive_cached_base_image(layer)
        if base_image is None:
            base_image = self._get_layer_image(layer, document, was_just_loaded)
        if base_image is None:
            return None

        surface = self._apply_interactive_transform_only(layer, base_image)
        if surface is None:
            return None

        with self._interactive_layer_surface_lock:
            self._interactive_layer_surface_cache[entry_key] = {
                "cache_key": cache_key,
                "image": surface.copy()
            }
            self._interactive_layer_surface_cache.move_to_end(entry_key)
            while len(self._interactive_layer_surface_cache) > self._max_interactive_layer_surface_entries:
                self._interactive_layer_surface_cache.popitem(last=False)

        return surface

    def _get_interactive_cached_base_image(self, layer) -> Optional[Image.Image]:
        """Reuse an existing layer image during active dragging/resizing.

        This avoids repeated disk reads and high-quality resize/effect work while
        the mouse is still moving. The normal high-quality refresh after idle still
        recomputes from the authoritative layer state.
        """
        try:
            cached = getattr(layer, "_cached_image", None) or getattr(layer, "cached_image", None)
            if cached is None:
                return None
            image = cached.copy()
            target_w = max(1, int(getattr(layer, "width", image.width) or image.width))
            target_h = max(1, int(getattr(layer, "height", image.height) or image.height))
            if image.size != (target_w, target_h):
                if image.mode == 'RGBA':
                    from app.utils.rgba_resampler import resize_rgba_premultiplied
                    image = resize_rgba_premultiplied(image, (target_w, target_h), Image.Resampling.BILINEAR)
                else:
                    image = image.resize((target_w, target_h), Image.Resampling.BILINEAR)
            return image
        except Exception:
            return None

    def _get_batch_preloaded_raw_image(self, document, image_path: str):
        """优先从执行器预读缓存获取原图。"""
        preload_cache = getattr(document, '_batch_preloaded_images', None)
        if isinstance(preload_cache, dict):
            img = preload_cache.get(image_path)
            if img is not None:
                return img.copy()
        return None

    def _build_interactive_base_key(self, document, active_layer_index: int, interactive_low_quality: bool) -> str:
        """构建交互增量预览底图缓存键。"""
        parts = [
            f"{id(document)}:{active_layer_index}",
            f"canvas:{document.canvas_width}x{document.canvas_height}",
            f"lowq:{int(bool(interactive_low_quality))}",
            f"scale:{self._get_interactive_render_scale(document, True, interactive_low_quality):.4f}",
        ]
        for idx, layer in enumerate(document.layers):
            if idx == active_layer_index or layer is None or not getattr(layer, 'visible', True):
                continue
            parts.append(self._build_layer_surface_key(layer, document, was_just_loaded=False))
            parts.append(self._build_layer_positions_key(layer, document))
            parts.append(f"opacity:{float(getattr(layer, 'opacity', 1.0)):.4f}")
            parts.append(f"blend:{self._get_layer_blend_mode(layer)}")
        return hashlib.md5("|".join(parts).encode('utf-8')).hexdigest()

    def _get_or_build_interaction_base(
        self,
        document,
        active_layer_index: int,
        force_refresh: bool,
        interactive_low_quality: bool
    ) -> Optional[Image.Image]:
        """获取或构建交互静态底图（不包含当前操作图层）。"""
        cache_key = self._build_interactive_base_key(document, active_layer_index, interactive_low_quality)
        entry_key = f"{id(document)}:{active_layer_index}"
        with self._interactive_base_lock:
            entry = self._interactive_base_cache.get(entry_key)
            if not force_refresh and entry and entry.get("cache_key") == cache_key:
                self._interactive_base_cache.move_to_end(entry_key)
                image = entry.get("image")
                if image is not None:
                    return image.copy()

        image = self._fast_render(
            document=document,
            preview_mode=True,
            was_just_loaded=False,
            low_quality_preview=interactive_low_quality,
            skip_layer_index=active_layer_index
        )
        if image is None:
            return None

        with self._interactive_base_lock:
            self._interactive_base_cache[entry_key] = {
                "cache_key": cache_key,
                "image": image.copy()
            }
            self._interactive_base_cache.move_to_end(entry_key)
            while len(self._interactive_base_cache) > self._max_interactive_base_entries:
                self._interactive_base_cache.popitem(last=False)
        return image

    def _invalidate_layer_surfaces_for_document(self, document):
        """仅清理指定文档的图层surface缓存"""
        doc_prefix = f"{id(document)}:"
        with self._layer_surface_lock:
            keys_to_remove = [k for k in self._layer_surface_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._layer_surface_cache.pop(k, None)
        with self._export_layer_surface_lock:
            keys_to_remove = [k for k in self._export_layer_surface_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._export_layer_surface_cache.pop(k, None)
        with self._layer_positions_lock:
            keys_to_remove = [k for k in self._layer_positions_cache.keys() if str(k).startswith(doc_prefix)]
            for k in keys_to_remove:
                self._layer_positions_cache.pop(k, None)

