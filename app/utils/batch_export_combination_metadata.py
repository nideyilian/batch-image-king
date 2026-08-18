"""组合运行时元数据 mixin（从 BatchExportPrecomputerV2 抽取，方法体原样迁移）。

方法访问主类实例方法（self._resolve_layer_by_state_index / self._capture_clone_settings）
与同组逻辑，调用点均为 self._xxx，迁移后由主类实例兜底，行为零变化。

本组不使用 print / logger，无需镜像编码安全契约。
"""
import os
from typing import Any, Dict, Optional, Tuple


class BatchExportCombinationMetadataMixin:
    def _build_combination_runtime_metadata(
        self,
        layer_states: Dict[int, str],
        combination_index: int,
        category: Optional[str] = None
    ) -> Tuple[Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]], Dict[int, Dict[str, Any]]]:
        """
        为组合构建运行时元数据（随机变换/图层参数/分身参数）。
        统一标准模式与绑定模式的预计算行为，避免导出阶段状态漂移。
        """
        random_transforms: Dict[int, Dict[str, Any]] = {}
        layer_parameters: Dict[int, Dict[str, Any]] = {}
        layer_clone_settings: Dict[int, Dict[str, Any]] = {}
        category_key = str(category or "")

        import random
        for layer_idx, file_path in layer_states.items():
            layer = self._resolve_layer_by_state_index(layer_idx)
            if layer is None:
                continue

            # 文字图层不参与随机缩放/旋转
            is_text_layer = bool(hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)))

            # 使用稳定种子，保证预计算可复现
            random_seed = hash((
                int(combination_index),
                int(layer_idx),
                os.path.basename(str(file_path or "")),
                category_key,
            )) & 0x7FFFFFFF
            rng = random.Random(random_seed)

            if is_text_layer:
                transform_params = {
                    'random_offset_x': 0,
                    'random_offset_y': 0,
                    'random_scale': 1.0,
                    'random_rotation': 0.0,
                }
            else:
                if bool(getattr(layer, 'random_position_enabled', False)):
                    position_range = int(getattr(layer, 'random_position_range', 0) or 0)
                    offset_x = rng.randint(-position_range, position_range)
                    offset_y = rng.randint(-position_range, position_range)
                else:
                    offset_x = 0
                    offset_y = 0

                if bool(getattr(layer, 'random_scale_enabled', False)):
                    scale_min = float(getattr(layer, 'random_scale_min', 1.0) or 1.0)
                    scale_max = float(getattr(layer, 'random_scale_max', 1.0) or 1.0)
                    random_scale = rng.uniform(min(scale_min, scale_max), max(scale_min, scale_max))
                else:
                    random_scale = 1.0

                if bool(getattr(layer, 'random_rotation_enabled', False)):
                    rotate_range = float(getattr(layer, 'random_rotation_range', 0.0) or 0.0)
                    random_rotation = rng.uniform(-rotate_range, rotate_range)
                else:
                    random_rotation = 0.0

                transform_params = {
                    'random_offset_x': int(offset_x),
                    'random_offset_y': int(offset_y),
                    'random_scale': float(random_scale),
                    'random_rotation': float(random_rotation),
                }

            random_transforms[int(layer_idx)] = transform_params

            layer_parameters[int(layer_idx)] = {
                'opacity': getattr(layer, 'opacity', 1.0),
                'blend_mode': getattr(layer, 'blend_mode', 0),
                'x': getattr(layer, 'x', 0),
                'y': getattr(layer, 'y', 0),
                'width': getattr(layer, 'width', 100),
                'height': getattr(layer, 'height', 100),
                'fit_mode': getattr(layer, 'fit_mode', 0),
                'crop_direction': getattr(layer, 'crop_direction', 0),
                'corner_radius': getattr(layer, 'corner_radius', 0),
                'stroke_enabled': getattr(layer, 'stroke_enabled', False),
                'stroke_width': getattr(layer, 'stroke_width', 1),
                'stroke_color': getattr(layer, 'stroke_color', (0, 0, 0, 255)),
                'stroke_type': getattr(layer, 'stroke_type', 0),
                'color_overlay_enabled': getattr(layer, 'color_overlay_enabled', False),
                'color_overlay_color': getattr(layer, 'color_overlay_color', (255, 0, 0, 255)),
                'color_overlay_opacity': getattr(layer, 'color_overlay_opacity', 1.0),
                'gradient_overlay_enabled': getattr(layer, 'gradient_overlay_enabled', False),
                'gradient_overlay_colors': getattr(layer, 'gradient_overlay_colors', [(0, 0, 0, 255), (255, 255, 255, 255)]),
                'gradient_overlay_angle': getattr(layer, 'gradient_overlay_angle', 90.0),
                'gradient_overlay_opacity': getattr(layer, 'gradient_overlay_opacity', 1.0),
                'shape_type': getattr(getattr(layer, 'shape_type', None), 'value', getattr(layer, 'shape_type', 'rectangle')),
                'trapezoid_top_width': getattr(layer, 'trapezoid_top_width', 100),
                'trapezoid_bottom_width': getattr(layer, 'trapezoid_bottom_width', 80),
                'trapezoid_slope_side': getattr(layer, 'trapezoid_slope_side', 'right'),
                'polygon_rotation': getattr(layer, 'polygon_rotation', 0.0),
                'polygon_corner_radius': getattr(layer, 'polygon_corner_radius', 0),
                'rotation': getattr(layer, 'rotation', 0.0),
                'flip_horizontal': getattr(layer, 'flip_horizontal', False),
                'flip_vertical': getattr(layer, 'flip_vertical', False),
            }

            clone_settings = self._capture_clone_settings(layer)
            if clone_settings:
                layer_clone_settings[int(layer_idx)] = clone_settings

        return random_transforms, layer_parameters, layer_clone_settings
