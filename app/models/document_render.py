import os
import random
import json
import pickle
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
from PIL.Image import Resampling, Transpose
import numpy as np
from PySide6.QtCore import QObject, Signal
import re
import glob
import gc
from app.models.layer_new import Layer as NewLayer
from app.models.document_blend import BlendMode
from app.models.document_blend import Blender
from typing import List, Tuple
from app.models.binding_manager import BindingGroup
import time
import hashlib
from app.utils.render_diagnostics import log_branch, log_sampling
from app.utils.print_utils import safe_print as _safe_print
from app.models.layer_size_match_manager import LayerSizeMatchManager
import logging
logger = logging.getLogger(__name__)

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print


class DocumentRender:
    """Document 方法拆分 mixin，保持与 Document 完全兼容（通过多重继承组合）。"""

    def render_composition(self, random_mode=False, optimize_memory=False, use_advanced_quality=False, is_batch_mode=False, enable_gpu=True):
        """渲染当前图层组合 - 改进版本，支持GPU加速和高质量合成

        参数:
            random_mode: 是否使用随机图像
            optimize_memory: 是否在渲染后优化内存使用
            use_advanced_quality: 是否使用高级质量算法
            is_batch_mode: 是否批量模式（影响性能优化策略）
            enable_gpu: 是否启用GPU加速渲染

        返回:
            PIL.Image: 渲染后的图像
        """
        # 检查是否取消（渲染开始前）
        if hasattr(self, '_export_canceled') and self._export_canceled:
            print("[渲染] 渲染开始前检测到取消操作")
            return None

        # 🚀 GPU加速渲染尝试
        if enable_gpu and not is_batch_mode:  # 批量模式暂时不使用GPU以保证稳定性
            try:
                from app.utils.gpu_render_integration import get_gpu_integrator
                gpu_integrator = get_gpu_integrator()

                # 尝试GPU渲染
                gpu_result = gpu_integrator.render_composition_integrated(
                    self,
                    random_mode=random_mode,
                    optimize_memory=optimize_memory,
                    use_advanced_quality=use_advanced_quality,
                    is_batch_mode=is_batch_mode
                )

                if gpu_result is not None:
                    print("[渲染] GPU加速渲染成功")
                    if optimize_memory:
                        self.optimize_memory_usage()
                    return gpu_result
                else:
                    print("[渲染] GPU渲染失败，继续使用CPU渲染")

            except Exception as e:
                print(f"[渲染] GPU渲染异常，回退到CPU渲染: {e}")

        # 如果启用随机模式，先进行随机化
        if random_mode:
            print("[渲染] 启用随机模式，正在随机化所有图层...")
            self.randomize_all_layers()

        # 再次检查是否取消（随机化后）
        if hasattr(self, '_export_canceled') and self._export_canceled:
            print("[渲染] 随机化后检测到取消操作")
            return None

        # 创建一个空白画布
        composition = Image.new('RGBA', (self.canvas_width, self.canvas_height), (0, 0, 0, 0))

        # 导入高级合成管理器 - 使用缓存的实例
        advanced_compositor = None
        if use_advanced_quality:
            try:
                # 检查是否已有缓存的合成器
                if not hasattr(self, '_cached_compositor'):
                    from app.engines import get_advanced_compositor
                    AdvancedCompositorManager, CompositeQuality = get_advanced_compositor()

                    if AdvancedCompositorManager is not None:
                        self._cached_compositor = AdvancedCompositorManager(
                            quality=CompositeQuality.BALANCED,  # 使用平衡模式
                            enable_gpu=False,
                            cache_size=10  # 减少缓存大小
                        )
                        print("[INFO] 创建高级合成引擎缓存（平衡模式）")
                    else:
                        self._cached_compositor = None

                advanced_compositor = self._cached_compositor
                if advanced_compositor:
                    print("[DEBUG] 使用缓存的高级合成引擎")
                else:
                    print("[INFO] 高级合成引擎不可用，使用标准算法")
                    use_advanced_quality = False

            except Exception as e:
                print(f"[WARNING] 高级合成引擎初始化失败: {e}")
                use_advanced_quality = False
                advanced_compositor = None
        
        # 🔧 修复：严格按照绑定组设置执行随机化，不重新分析分类
        if random_mode:
            print("[渲染] 启用随机模式，严格按照绑定组设置执行...")
            self.randomize_all_layers()

        # 如果使用高级合成引擎
        if advanced_compositor:
            try:
                # 准备图层数据 - 使用与标准路径相同的逻辑
                layer_data = []
                from app.models.text_layer import TextLayer

                for layer_index, layer in enumerate(sorted(self.layers, key=lambda l: self.layers.index(l))):
                    # 每个图层开始前检查是否取消（高级合成路径）
                    if hasattr(self, '_export_canceled') and self._export_canceled:
                        print(f"[高级渲染] 处理图层 {layer_index+1} 时检测到取消操作")
                        if composition:
                            del composition
                        return None
                        
                    if not layer.visible:
                        continue

                    # 获取图层图像 - 与标准路径保持一致
                    layer_image = None
                    if isinstance(layer, TextLayer):
                        # 文字图层，渲染文字为图像
                        layer_image = layer.render_text()
                    else:
                        # 普通图层，获取图像
                        # 🔧 修复：随机模式下，图层应该已经被 randomize_all_layers 处理过
                        # 直接使用当前图像，避免重复随机化
                        if hasattr(layer, 'cached_image') and layer.cached_image is not None:
                            # 使用已缓存的图像
                            layer_image = layer.cached_image
                        else:
                            # 如果没有缓存，获取当前图像（可能是预设的组合）
                            layer_image = layer.get_image()

                    if layer_image is None:
                        continue

                    # 应用图层效果
                    if hasattr(layer, 'apply_effects') and callable(layer.apply_effects):
                        layer_image = layer.apply_effects(layer_image)

                    # 处理分身效果 - 与标准路径保持一致
                    is_clone_enabled = hasattr(layer, 'clone_enabled') and layer.clone_enabled
                    clone_positions = []

                    if is_clone_enabled and hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                        # 获取所有分身位置
                        try:
                            # 使用支持随机偏移的有效位置方法
                            if hasattr(layer, 'get_effective_clone_positions'):
                                clone_positions = layer.get_effective_clone_positions()
                            else:
                                clone_positions = layer.get_clone_positions()
                        except Exception as e:
                            print(f"获取分身位置失败: {e}")
                            clone_positions = [(layer.x, layer.y)]
                    else:
                        # 没有分身效果，使用原始位置
                        clone_positions = [(layer.x, layer.y)]

                    fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
                    if fill_enabled:
                        spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                        angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                        mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                        
                        # 获取实际使用的宽高（考虑自定义大小）
                        clone_elem_width = layer.width
                        clone_elem_height = layer.height
                        if (hasattr(layer, 'clone_custom_size_enabled') and layer.clone_custom_size_enabled and
                            hasattr(layer, 'clone_custom_width') and hasattr(layer, 'clone_custom_height')):
                            if layer.clone_custom_width > 0:
                                clone_elem_width = layer.clone_custom_width
                            if layer.clone_custom_height > 0:
                                clone_elem_height = layer.clone_custom_height
                        
                        dx = max(1, int(clone_elem_width + spacing))
                        dy = max(1, int(clone_elem_height + spacing))
                        positions = []
                        cx = self.canvas_width / 2.0
                        cy = self.canvas_height / 2.0
                        base_x = layer.x
                        base_y = layer.y
                        import math
                        angle = math.radians(angle_deg % 360.0)
                        if mode == 'border':
                            # 边框排列：确保四角有元素，行距列距统一，支持边距
                            margin = int(getattr(layer, 'clone_fill_margin', 0))  # 获取边距参数
                            positions = []
                            
                            # 应用边距到画布尺寸
                            effective_width = self.canvas_width - 2 * margin
                            effective_height = self.canvas_height - 2 * margin
                            
                            # 计算每边的元素数量，确保四角都有元素
                            # 顶部和底部：计算水平方向可以放置的元素数量（包括两端的角）
                            top_bottom_count = max(2, (effective_width + dx) // dx)  # 至少2个（两角）
                            # 左侧和右侧：计算垂直方向可以放置的元素数量（包括两端的角）
                            left_right_count = max(2, (effective_height + dy) // dy)  # 至少2个（两角）
                            
                            # 计算统一的间距，确保元素均匀分布
                            # effective_width/height 是画布减去边距后的有效区域
                            # clone_elem_width/height 是分身元素的实际尺寸
                            if top_bottom_count > 1:
                                top_bottom_spacing = (effective_width - clone_elem_width) / (top_bottom_count - 1)
                            else:
                                top_bottom_spacing = 0
                                
                            if left_right_count > 1:
                                left_right_spacing = (effective_height - clone_elem_height) / (left_right_count - 1)
                            else:
                                left_right_spacing = 0
                            
                            # 顶部边缘（包括左上角和右上角）
                            for i in range(top_bottom_count):
                                x = margin + int(i * top_bottom_spacing)
                                if x <= self.canvas_width - clone_elem_width - margin:  # 确保不超出有效区域
                                    positions.append((x, margin))
                            
                            # 底部边缘（包括左下角和右下角）
                            for i in range(top_bottom_count):
                                x = margin + int(i * top_bottom_spacing)
                                if x <= self.canvas_width - clone_elem_width - margin:  # 确保不超出有效区域
                                    positions.append((x, self.canvas_height - clone_elem_height - margin))
                            
                            # 左侧边缘（不包括已经放置的角落元素）
                            for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                                y = margin + int(i * left_right_spacing)
                                if margin < y < self.canvas_height - clone_elem_height - margin:  # 确保有效位置
                                    positions.append((margin, y))
                            
                            # 右侧边缘（不包括已经放置的角落元素）
                            for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                                y = margin + int(i * left_right_spacing)
                                if margin < y < self.canvas_height - clone_elem_height - margin:  # 确保有效位置
                                    positions.append((self.canvas_width - clone_elem_width - margin, y))
                        else:
                            start_y = -int(clone_elem_height)
                            end_y = self.canvas_height + int(clone_elem_height)
                            step_y = dy
                            i_row = 0
                            for row_y in range(start_y, end_y + 1, step_y):
                                offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                                for col_x in range(-int(clone_elem_width), self.canvas_width + int(clone_elem_width) + 1, dx):
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
                        
                        # 获取实际使用的宽高（考虑自定义大小）用于镜像计算
                        mirror_width = layer.width
                        mirror_height = layer.height
                        if (hasattr(layer, 'clone_custom_size_enabled') and layer.clone_custom_size_enabled and
                            hasattr(layer, 'clone_custom_width') and hasattr(layer, 'clone_custom_height')):
                            if layer.clone_custom_width > 0:
                                mirror_width = layer.clone_custom_width
                            if layer.clone_custom_height > 0:
                                mirror_height = layer.clone_custom_height
                        
                        min_x = min([x for x, _ in base])
                        max_x = max([x + mirror_width for x, _ in base])
                        min_y = min([y for _, y in base])
                        max_y = max([y + mirror_height for _, y in base])
                        group_width = max_x - min_x
                        group_height = max_y - min_y
                        if mirror_mode == 'horizontal':
                            mirrored_left = self.canvas_width - (min_x + group_width)
                            for x, y in base:
                                offset_x = x - min_x
                                positions_info.append((mirrored_left + offset_x, y, True))
                        elif mirror_mode == 'vertical':
                            mirrored_top = self.canvas_height - (min_y + group_height)
                            for x, y in base:
                                offset_y = y - min_y
                                positions_info.append((x, mirrored_top + offset_y, True))

                    from PIL import ImageOps
                    
                    # 检查是否需要调整分身大小
                    print(f"[快速渲染检查] 图层: {layer.name}")
                    print(f"  - 分身启用: {is_clone_enabled}")
                    print(f"  - 有 clone_custom_size_enabled: {hasattr(layer, 'clone_custom_size_enabled')}")
                    if hasattr(layer, 'clone_custom_size_enabled'):
                        print(f"  - clone_custom_size_enabled 值: {layer.clone_custom_size_enabled}")
                    print(f"  - 有 clone_custom_width: {hasattr(layer, 'clone_custom_width')}")
                    if hasattr(layer, 'clone_custom_width'):
                        print(f"  - clone_custom_width 值: {layer.clone_custom_width}")
                    print(f"  - 有 clone_custom_height: {hasattr(layer, 'clone_custom_height')}")
                    if hasattr(layer, 'clone_custom_height'):
                        print(f"  - clone_custom_height 值: {layer.clone_custom_height}")
                    
                    clone_resize_needed = (
                        is_clone_enabled and 
                        hasattr(layer, 'clone_custom_size_enabled') and 
                        layer.clone_custom_size_enabled and
                        hasattr(layer, 'clone_custom_width') and 
                        hasattr(layer, 'clone_custom_height') and
                        layer.clone_custom_width > 0 and 
                        layer.clone_custom_height > 0
                    )
                    print(f"  - 需要调整大小: {clone_resize_needed}")
                    
                    # 如果需要调整大小，准备调整后的图像
                    if clone_resize_needed:
                        try:
                            resized_layer_image = layer_image.resize(
                                (layer.clone_custom_width, layer.clone_custom_height),
                                Image.Resampling.LANCZOS
                            )
                            print(f"[快速渲染] 图层 '{layer.name}' 应用自定义分身大小: {layer.clone_custom_width}x{layer.clone_custom_height}")
                        except Exception as resize_error:
                            print(f"[快速渲染] 调整分身大小失败: {resize_error}，使用原图大小")
                            resized_layer_image = layer_image
                            clone_resize_needed = False
                    else:
                        resized_layer_image = layer_image
                    
                    for pos_x, pos_y, is_mirror in positions_info:
                        # 获取混合模式并转换为字符串
                        blend_mode = self._get_layer_blend_mode_string(layer)
                        
                        # 使用调整大小后的图像（如果启用了自定义大小）
                        img_to_use = resized_layer_image if clone_resize_needed else layer_image

                        layer_info = {
                            'image': ImageOps.mirror(img_to_use) if (is_mirror and mirror_mode == 'horizontal') else (ImageOps.flip(img_to_use) if (is_mirror and mirror_mode == 'vertical') else img_to_use),
                            'blend_mode': blend_mode,
                            'opacity': getattr(layer, 'opacity', 1.0),
                            'position': (pos_x, pos_y),
                            'mask': None
                        }
                        layer_data.append(layer_info)

                # 检查是否有有效的图层数据
                if not layer_data:
                    print("[WARNING] 没有有效的图层数据，使用空画布")
                    return composition

                print(f"[DEBUG] 准备合成 {len(layer_data)} 个图层")

                # 使用高级合成引擎
                composition = advanced_compositor.composite_layers(
                    layer_data,
                    (self.canvas_width, self.canvas_height),
                    (0, 0, 0, 0),
                    optimize_memory=optimize_memory
                )
                print("[INFO] 使用高级合成引擎完成渲染")

                # 如果需要优化内存，清理缓存
                if optimize_memory:
                    self._optimize_memory()

                return composition

            except Exception as e:
                print(f"[ERROR] 高级合成失败，回退到标准方法: {e}")
                import traceback
                traceback.print_exc()

        # 标准合成方法（后备）
        # 导入混合模式工具
        from app.models.document_blend import Blender, BlendMode

        # 性能优化：获取最优设置
        try:
            from app.utils.performance_optimizer import PerformanceOptimizer, PerformanceMonitor

            # 获取可见图层
            from app.utils.layer_tree import render_layers
            visible_layers = render_layers(self.layers)

            # 获取优化设置
            image_size = (self.canvas_width, self.canvas_height)
            layer_count = len(visible_layers)

            # 根据批量模式决定质量设置
            if is_batch_mode:
                # 批量模式使用性能优化设置
                perf_settings = PerformanceOptimizer.get_optimal_settings(
                    image_size, layer_count, is_batch_mode
                )
                print(f"[性能优化] 批量模式 - 图像尺寸: {image_size}, 图层数: {layer_count}")
                print(f"[性能优化] 批量设置: 抗锯齿={perf_settings['antialiasing_method']}, 质量={perf_settings['quality_level']}")
            else:
                # 非批量模式使用最高质量设置
                perf_settings = {
                    'edge_enhancement': True,
                    'subpixel_precision': True,
                    'antialiasing_method': 'smaa',  # 使用最高质量抗锯齿
                    'quality_level': 'high',
                    'use_threading': False,
                    'memory_optimization': False
                }
                print(f"[高质量渲染] 非批量模式 - 使用最高质量设置")

        except ImportError:
            # 后备设置
            perf_settings = {
                'edge_enhancement': True,
                'subpixel_precision': True,
                'antialiasing_method': 'smaa',
                'quality_level': 'high',
                'use_threading': False,
                'memory_optimization': False
            }
            from app.utils.layer_tree import render_layers
            visible_layers = render_layers(self.layers)

        # 绘制所有可见图层
        for layer_index, layer in enumerate(sorted(visible_layers, key=lambda l: self.layers.index(l))):
            # 每个图层开始前检查是否取消
            if hasattr(self, '_export_canceled') and self._export_canceled:
                print(f"[渲染] 处理图层 {layer_index+1}/{len(visible_layers)} 时检测到取消操作")
                if composition:
                    del composition
                return None
                
            if not layer.visible:
                continue
                
            # 获取图层图像 - 支持文字图层和普通图层
            layer_image = None
            from app.models.text_layer import TextLayer
            
            if isinstance(layer, TextLayer):
                # 文字图层，渲染文字为图像
                layer_image = layer.render_text()
            else:
                # 普通图层，获取图像
                if random_mode:
                    # 🔧 修复：随机模式下，图层应该已经被 randomize_all_layers 处理过
                    # 直接使用当前图像，避免重复随机化
                    if hasattr(layer, 'cached_image') and layer.cached_image is not None:
                        layer_image = layer.cached_image
                    else:
                        layer_image = layer.get_image()
                elif hasattr(layer, 'cached_image') and layer.cached_image is not None:
                    # 使用已缓存的图像
                    layer_image = layer.cached_image
                else:
                    # 如果没有缓存，获取当前图像（可能是预设的组合）
                    layer_image = layer.get_image()
                
            if layer_image is None:
                continue
                
            # 应用图层效果 - 批处理模式下设置批处理标志以优化性能
            if hasattr(layer, 'apply_effects') and callable(layer.apply_effects):
                if is_batch_mode:
                    # 批处理模式下设置批处理标志，减少日志输出
                    if hasattr(layer, '_is_batch_mode'):
                        layer._is_batch_mode = True
                layer_image = layer.apply_effects(layer_image)
                if is_batch_mode and hasattr(layer, '_is_batch_mode'):
                    layer._is_batch_mode = False
            
            # 判断是否启用了分身功能
            is_clone_enabled = hasattr(layer, 'clone_enabled') and layer.clone_enabled
            clone_positions = []
            
            if is_clone_enabled and hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                # 获取所有分身位置
                try:
                    # 使用支持随机偏移的有效位置方法
                    if hasattr(layer, 'get_effective_clone_positions'):
                        clone_positions = layer.get_effective_clone_positions()
                    else:
                        clone_positions = layer.get_clone_positions()
                    print(f"图层 '{layer.name}' 渲染分身，共 {len(clone_positions)} 个位置")
                except Exception as e:
                    print(f"获取分身位置出错: {e}")
                    is_clone_enabled = False
                    # 使用支持随机偏移的有效位置
                    if hasattr(layer, 'get_effective_position'):
                        clone_positions = [layer.get_effective_position()]
                    else:
                        clone_positions = [(layer.x, layer.y)]
            else:
                # 没有启用分身或方法不存在，使用单一位置
                # 使用支持随机偏移的有效位置
                if hasattr(layer, 'get_effective_position'):
                    clone_positions = [layer.get_effective_position()]
                else:
                    clone_positions = [(layer.x, layer.y)]

            fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
            if fill_enabled:
                spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                
                # 获取实际使用的宽高（考虑自定义大小）
                effective_width = layer.width
                effective_height = layer.height
                if (hasattr(layer, 'clone_custom_size_enabled') and layer.clone_custom_size_enabled and
                    hasattr(layer, 'clone_custom_width') and hasattr(layer, 'clone_custom_height')):
                    if layer.clone_custom_width > 0:
                        effective_width = layer.clone_custom_width
                    if layer.clone_custom_height > 0:
                        effective_height = layer.clone_custom_height
                
                dx = max(1, int(effective_width + spacing))
                dy = max(1, int(effective_height + spacing))
                positions = []
                cx = self.canvas_width / 2.0
                cy = self.canvas_height / 2.0
                base_x = layer.x
                base_y = layer.y
                import math
                angle = math.radians(angle_deg % 360.0)
                start_y = -layer.height
                end_y = self.canvas_height + layer.height
                if mode == 'border':
                    # 边框排列：确保四角有元素，行距列距统一
                    positions = []
                    
                    # 计算每边的元素数量，确保四角都有元素
                    # 顶部和底部：计算水平方向可以放置的元素数量（包括两端的角）
                    top_bottom_count = max(2, (self.canvas_width + dx) // dx)  # 至少2个（两角）
                    # 左侧和右侧：计算垂直方向可以放置的元素数量（包括两端的角）
                    left_right_count = max(2, (self.canvas_height + dy) // dy)  # 至少2个（两角）
                    
                    # 计算统一的间距，确保元素均匀分布
                    if top_bottom_count > 1:
                        top_bottom_spacing = (self.canvas_width - effective_width) / (top_bottom_count - 1)
                    else:
                        top_bottom_spacing = 0
                        
                    if left_right_count > 1:
                        left_right_spacing = (self.canvas_height - effective_height) / (left_right_count - 1)
                    else:
                        left_right_spacing = 0
                    
                    # 顶部边缘（包括左上角和右上角）
                    for i in range(top_bottom_count):
                        x = int(i * top_bottom_spacing)
                        if x <= self.canvas_width - effective_width:  # 确保不超出画布
                            positions.append((x, 0))
                    
                    # 底部边缘（包括左下角和右下角）
                    for i in range(top_bottom_count):
                        x = int(i * top_bottom_spacing)
                        if x <= self.canvas_width - effective_width:  # 确保不超出画布
                            positions.append((x, self.canvas_height - effective_height))
                    
                    # 左侧边缘（不包括已经放置的角落元素）
                    for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                        y = int(i * left_right_spacing)
                        if 0 < y < self.canvas_height - effective_height:  # 确保有效位置
                            positions.append((0, y))
                    
                    # 右侧边缘（不包括已经放置的角落元素）
                    for i in range(1, left_right_count - 1):  # 跳过第一个和最后一个（角落）
                        y = int(i * left_right_spacing)
                        if 0 < y < self.canvas_height - effective_height:  # 确保有效位置
                            positions.append((self.canvas_width - effective_width, y))
                else:
                    step_y = dy
                    i_row = 0
                    for row_y in range(start_y, end_y + 1, step_y):
                        offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                        for col_x in range(-int(effective_width), self.canvas_width + int(effective_width) + 1, dx):
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

            
            
            # 判断混合模式是否为正常模式
            is_normal_blend = (
                not hasattr(layer, 'blend_mode') or
                layer.blend_mode is None or
                layer.blend_mode == BlendMode.NORMAL or
                layer.blend_mode == "正常"
            )
            
            positions_info = [(x, y, False) for (x, y) in clone_positions]
            mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
            if mirror_mode and mirror_mode != 'none':
                base = clone_positions[:]
                
                # 获取实际使用的宽高（考虑自定义大小）
                mirror_width = layer.width
                mirror_height = layer.height
                if (hasattr(layer, 'clone_custom_size_enabled') and layer.clone_custom_size_enabled and
                    hasattr(layer, 'clone_custom_width') and hasattr(layer, 'clone_custom_height')):
                    if layer.clone_custom_width > 0:
                        mirror_width = layer.clone_custom_width
                    if layer.clone_custom_height > 0:
                        mirror_height = layer.clone_custom_height
                
                min_x = min([x for x, _ in base])
                max_x = max([x + mirror_width for x, _ in base])
                min_y = min([y for _, y in base])
                max_y = max([y + mirror_height for _, y in base])
                group_width = max_x - min_x
                group_height = max_y - min_y
                if mirror_mode == 'horizontal':
                    mirrored_left = self.canvas_width - (min_x + group_width)
                    for x, y in base:
                        offset_x = x - min_x
                        positions_info.append((mirrored_left + offset_x, y, True))
                elif mirror_mode == 'vertical':
                    mirrored_top = self.canvas_height - (min_y + group_height)
                    for x, y in base:
                        offset_y = y - min_y
                        positions_info.append((x, mirrored_top + offset_y, True))

            from PIL import ImageOps
            
            # 检查是否需要调整分身大小
            print(f"[渲染检查] 图层: {layer.name}")
            print(f"  - 分身启用: {is_clone_enabled}")
            print(f"  - 有 clone_custom_size_enabled: {hasattr(layer, 'clone_custom_size_enabled')}")
            if hasattr(layer, 'clone_custom_size_enabled'):
                print(f"  - clone_custom_size_enabled 值: {layer.clone_custom_size_enabled}")
            print(f"  - 有 clone_custom_width: {hasattr(layer, 'clone_custom_width')}")
            if hasattr(layer, 'clone_custom_width'):
                print(f"  - clone_custom_width 值: {layer.clone_custom_width}")
            print(f"  - 有 clone_custom_height: {hasattr(layer, 'clone_custom_height')}")
            if hasattr(layer, 'clone_custom_height'):
                print(f"  - clone_custom_height 值: {layer.clone_custom_height}")
            
            clone_resize_needed = (
                is_clone_enabled and 
                hasattr(layer, 'clone_custom_size_enabled') and 
                layer.clone_custom_size_enabled and
                hasattr(layer, 'clone_custom_width') and 
                hasattr(layer, 'clone_custom_height') and
                layer.clone_custom_width > 0 and 
                layer.clone_custom_height > 0
            )
            print(f"  - 需要调整大小: {clone_resize_needed}")
            
            # 如果需要调整大小，准备调整后的图像
            if clone_resize_needed:
                try:
                    resized_layer_image = layer_image.resize(
                        (layer.clone_custom_width, layer.clone_custom_height),
                        Image.Resampling.LANCZOS
                    )
                    print(f"[标准渲染] 图层 '{layer.name}' 应用自定义分身大小: {layer.clone_custom_width}x{layer.clone_custom_height}")
                except Exception as resize_error:
                    print(f"[标准渲染] 调整分身大小失败: {resize_error}，使用原图大小")
                    resized_layer_image = layer_image
                    clone_resize_needed = False
            else:
                resized_layer_image = layer_image
            
            for pos_x, pos_y, is_mirror in positions_info:
                try:
                    # 尝试使用高级合成器
                    from app.utils.unified_alpha_compositor import unified_alpha_compositor

                    # 确定混合模式
                    blend_mode_str = self._get_layer_blend_mode_string(layer)

                    # 修复：使用更稳定的合成方法
                    try:
                        # 使用调整大小后的图像（如果启用了自定义大小）
                        img_to_use = resized_layer_image if clone_resize_needed else layer_image
                        img_for_pos = ImageOps.mirror(img_to_use) if (is_mirror and mirror_mode == 'horizontal') else (ImageOps.flip(img_to_use) if (is_mirror and mirror_mode == 'vertical') else img_to_use)

                        # 智能暗化：半透明近黑/近灰覆盖自动切换为正片叠底
                        auto_blend = blend_mode_str
                        try:
                            sample_rgb = img_for_pos.convert('RGB').resize((1, 1), Image.BOX).getpixel((0, 0))
                            sample_a = img_for_pos.getchannel('A').resize((1, 1), Image.BOX).getpixel((0, 0)) / 255.0
                            r, g, b = sample_rgb
                            neutral = abs(r - g) < 3 and abs(g - b) < 3
                            near_black = max(r, g, b) < 12
                            if auto_blend == 'normal' and sample_a > 0.01 and neutral and (near_black or max(r, g, b) < 48):
                                auto_blend = 'multiply'
                        except Exception:
                            logger.warning("静默异常已忽略: except Exception: in document_render.py", exc_info=True)
                            pass

                        if is_batch_mode:
                            # 批量模式使用性能优化设置
                            composition = PerformanceOptimizer.optimize_composite_layer(
                                background=composition,
                                foreground=img_for_pos,
                                position=(pos_x, pos_y),
                                opacity=getattr(layer, 'opacity', 1.0),
                                blend_mode=auto_blend,
                                settings=perf_settings
                            )
                        else:
                            # 非批量模式也使用稳定的合成方法，启用边缘增强以匹配Photoshop效果
                            # 🔧 修复：禁用边缘增强以解决边缘像素缺失问题
                            # 之前的边缘增强算法会侵蚀图像边缘的Alpha通道
                            composition = unified_alpha_compositor.composite_layer(
                                background=composition,
                                foreground=img_for_pos,
                                position=(pos_x, pos_y),
                                opacity=getattr(layer, 'opacity', 1.0),
                                blend_mode=auto_blend,
                                edge_enhancement=False,
                                subpixel_precision=True,
                                use_srgb_blending=True  # 启用 Photoshop 风格混合
                            )
                    except Exception as composite_e:
                        print(f"[渲染] 高级合成失败: {composite_e}，使用简单合成")
                        # 回退到最简单的合成方法
                        try:
                            if img_for_pos.mode != 'RGBA':
                                img_for_pos = img_for_pos.convert('RGBA')

                            opacity = getattr(layer, 'opacity', 1.0)
                            if opacity < 1.0:
                                alpha = img_for_pos.split()[-1]
                                alpha = alpha.point(lambda p: int(p * opacity))
                                img_for_pos = img_for_pos.copy()
                                img_for_pos.putalpha(alpha)

                            composition.paste(img_for_pos, (pos_x, pos_y), img_for_pos)
                        except Exception as simple_e:
                            print(f"[渲染] 简单合成也失败: {simple_e}")
                            continue

                except ImportError:
                    # 后备方案：使用改进的传统方法
                    if is_normal_blend:
                        # 使用改进的alpha混合
                        composition = self._improved_layer_composite(
                            composition, img_for_pos, (pos_x, pos_y), layer.opacity
                        )
                    else:
                        # 创建临时图像用于混合模式
                        temp_image = Image.new('RGBA', composition.size, (0, 0, 0, 0))
                        if img_for_pos.mode == 'RGBA':
                            temp_image.paste(img_for_pos, (pos_x, pos_y), img_for_pos)
                        else:
                            temp_image.paste(img_for_pos, (pos_x, pos_y))

                        # 应用混合模式
                        composition = Blender.apply_blend_mode(composition, temp_image, layer.blend_mode, layer.opacity)
        
        # 如果需要优化内存，清理缓存
        if optimize_memory:
            self._optimize_memory()
            
        return composition



    def _improved_layer_composite(self, background: Image.Image, foreground: Image.Image,
                                 position: Tuple[int, int], opacity: float) -> Image.Image:
        """
        改进的图层合成方法 - 解决半透明和边缘问题的后备方案
        """
        import numpy as np

        # 确保图像格式
        if background.mode != 'RGBA':
            background = background.convert('RGBA')
        if foreground.mode != 'RGBA':
            foreground = foreground.convert('RGBA')

        # 获取位置和尺寸
        pos_x, pos_y = position
        fg_width, fg_height = foreground.size
        bg_width, bg_height = background.size

        # 计算有效区域
        src_x1 = max(0, -pos_x)
        src_y1 = max(0, -pos_y)
        src_x2 = min(fg_width, bg_width - pos_x)
        src_y2 = min(fg_height, bg_height - pos_y)

        dst_x1 = max(0, pos_x)
        dst_y1 = max(0, pos_y)
        dst_x2 = dst_x1 + (src_x2 - src_x1)
        dst_y2 = dst_y1 + (src_y2 - src_y1)

        # 检查是否有有效区域
        if src_x2 <= src_x1 or src_y2 <= src_y1:
            return background

        # 提取有效区域
        fg_crop = foreground.crop((src_x1, src_y1, src_x2, src_y2))
        bg_crop = background.crop((dst_x1, dst_y1, dst_x2, dst_y2))

        # 转换为浮点数组进行高精度计算
        bg_array = np.array(bg_crop, dtype=np.float64) / 255.0
        fg_array = np.array(fg_crop, dtype=np.float64) / 255.0

        # 应用不透明度
        if opacity < 1.0:
            fg_array[:,:,3] *= opacity

        # Porter-Duff "source over" 合成
        bg_rgb = bg_array[:,:,:3]
        bg_alpha = bg_array[:,:,3:4]
        fg_rgb = fg_array[:,:,:3]
        fg_alpha = fg_array[:,:,3:4]

        # 计算输出alpha
        result_alpha = fg_alpha + bg_alpha * (1 - fg_alpha)

        # 避免除零
        safe_alpha = np.where(result_alpha > 1e-12, result_alpha, 1e-12)

        # 计算输出颜色
        result_rgb = (fg_rgb * fg_alpha + bg_rgb * bg_alpha * (1 - fg_alpha)) / safe_alpha

        # 组合结果
        result_array = np.concatenate([result_rgb, result_alpha], axis=2)
        result_array = np.clip(result_array, 0, 1)

        # 🔧 修复：使用抖动转换以消除色阶分层
        try:
            from app.utils.unified_alpha_compositor import _float_to_uint8_with_dithering
            result_8bit = _float_to_uint8_with_dithering(result_array, use_dithering=True)
        except ImportError:
            # 后备方案：使用四舍五入
            result_8bit = np.round(result_array * 255.0).astype(np.uint8)
        
        composited = Image.fromarray(result_8bit, 'RGBA')

        # 将合成结果粘贴回原图
        result = background.copy()
        result.paste(composited, (dst_x1, dst_y1))

        return result



    def _invalidate_render_cache(self):
        """使渲染缓存失效"""
        try:
            from app.utils.fast_renderer import get_global_fast_renderer
            fast_renderer = get_global_fast_renderer()
            # 精确失效当前文档相关的智能缓存
            if hasattr(fast_renderer, 'invalidate_document_cache'):
                fast_renderer.invalidate_document_cache(self)
            # 标记需要缓存刷新，确保下一帧强制重渲染
            self._needs_cache_refresh = True
        except Exception:
            # 如果无法访问渲染器，仍然标记需要刷新
            self._needs_cache_refresh = True



    def _force_clear_all_caches(self):
        """强制清除所有可能的缓存，确保导出时没有重复"""
        print("[文档] 强制清除所有缓存...")

        # 清除图层缓存
        for layer in self.layers:
            cache_attrs = ['cached_image', '_cached_image', '_cached_image_path',
                          '_current_image_cache', 'current_image_path']
            for attr in cache_attrs:
                if hasattr(layer, attr):
                    setattr(layer, attr, None)

        # 清除绑定管理器缓存
        if self.binding_manager:
            for group in self.binding_manager.binding_groups.values():
                if hasattr(group, '_matched_files_cache'):
                    group._matched_files_cache.clear()
                if hasattr(group, '_session_seed'):
                    delattr(group, '_session_seed')
                if hasattr(group, 'layer_image_usage'):
                    for usage_dict in group.layer_image_usage.values():
                        usage_dict.clear()

        # 🔧 超级修复：清除快速渲染器和智能缓存系统
        try:
            from app.utils.fast_renderer import get_global_fast_renderer
            fast_renderer = get_global_fast_renderer()
            fast_renderer.invalidate_cache()
            print("[文档] 快速渲染器缓存已清除")
        except Exception as e:
            print(f"[文档] 清除快速渲染器缓存失败: {e}")

        try:
            from app.utils.intelligent_render_cache import get_intelligent_cache
            intelligent_cache = get_intelligent_cache()
            intelligent_cache.clear()
            print("[文档] 智能缓存系统已清除")
        except Exception as e:
            print(f"[文档] 清除智能缓存系统失败: {e}")

        print("[文档] 所有缓存已清除")



    def _get_layer_blend_mode_string(self, layer):
        """获取图层的混合模式字符串"""
        try:
            blend_mode = getattr(layer, 'blend_mode', 0)

            # 如果是None或无效值，返回normal
            if blend_mode is None:
                return 'normal'

            # 如果是数字，转换为字符串
            if isinstance(blend_mode, int):
                blend_mode_map = {
                    0: 'normal',
                    1: 'multiply',
                    2: 'screen',
                    3: 'overlay',
                    4: 'soft_light',
                    5: 'hard_light',
                    6: 'color_dodge',
                    7: 'color_burn',
                    8: 'darken',
                    9: 'lighten',
                    10: 'difference',
                    11: 'exclusion',
                    12: 'hue',
                    13: 'saturation',
                    14: 'color',
                    15: 'luminosity'
                }
                return blend_mode_map.get(blend_mode, 'normal')

            # 如果已经是字符串，直接返回
            return str(blend_mode)

        except Exception as e:
            print(f"获取混合模式失败: {e}")
            return 'normal'