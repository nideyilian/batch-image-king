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


class DocumentRandomize:
    """Document 方法拆分 mixin，保持与 Document 完全兼容（通过多重继承组合）。"""

    def randomize_all_layers(self):
        """为所有可见图层重新随机选择图片/文字，严格按照绑定组设置执行"""
        # 只获取可见图层进行处理
        try:
            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            visible_layers = [
                layer for layer in self.layers
                if not is_layer_group(layer) and is_effectively_visible(layer, self.layers)
            ]
        except Exception:
            visible_layers = [layer for layer in self.layers if getattr(layer, 'visible', True)]

        # 预览随机化必须以绑定管理器为主链路，不能依赖导出模式推断
        # 否则公共分类分析失败时会被降级为标准随机化，导致绑定看似失效
        if hasattr(self, 'binding_manager') and self.binding_manager and self.binding_manager.global_enabled:
            print("[随机化] 🔗 绑定管理器已启用，按绑定规则执行预览随机化")
            try:
                from app.models.text_layer import TextLayer

                # 先分析文件限制，再一次性为所有绑定组选择组合
                self.binding_manager.analyze_and_restrict_layer_files(self.layers)
                bound_layer_mapping = self.binding_manager.randomize_bound_layers(self.layers)
                print(f"[随机化] 绑定管理器已更新 {len(bound_layer_mapping)} 个绑定图层")

                # 未由绑定映射覆盖的可见图层，按各自规则随机化
                for layer in visible_layers:
                    if isinstance(layer, TextLayer):
                        # 文字图层若已被绑定映射处理（text_layer://），这里不重复覆盖
                        if id(layer) in bound_layer_mapping:
                            continue
                        layer.randomize_text()
                        continue

                    # 图像图层：绑定图层已由 randomize_bound_layers 处理
                    if self.binding_manager.is_layer_bound(layer):
                        continue

                    # 非绑定图层遵守文件限制，避免抢占绑定图层文件
                    restricted_files = self.binding_manager.get_layer_file_restrictions(layer)
                    if restricted_files:
                        layer.get_random_image(force_random=True, restrict_to_bound_files=restricted_files)
                    else:
                        layer.get_random_image(force_random=True)
            except Exception as e:
                print(f"[随机化] ⚠️ 绑定链路执行失败，回退到基础随机化: {e}")
                for layer in visible_layers:
                    from app.models.text_layer import TextLayer
                    if isinstance(layer, TextLayer):
                        layer.randomize_text()
                    else:
                        layer.get_random_image(force_random=True)
        else:
            print(f"[随机化] ⚠️ 绑定管理器未启用，所有图层独立随机化")
            # 处理所有可见图层，正常随机化
            for layer in visible_layers:
                # 检查是否是文字图层
                from app.models.text_layer import TextLayer
                if isinstance(layer, TextLayer):
                    # 文字图层，随机选择文字
                    layer.randomize_text()
                else:
                    # 普通图层，强制随机化图片选择
                    layer.get_random_image(force_random=True)

        # 为所有可见图层生成随机变换参数
        for layer in visible_layers:
            if hasattr(layer, 'generate_random_transform_params'):
                layer.generate_random_transform_params()

        # 使渲染缓存失效，确保预览窗口显示最新的随机变化
        # 🔧 优化：随机化只标记需要刷新，不再粗粒度清除图层 surface 缓存。
        # 图层 surface 缓存的 key 已包含图片路径与变换参数，换图/变换的图层
        # 会自动 miss 重新解码，未变化的图层直接命中缓存，避免全量重解码导致数秒延迟。
        self._needs_cache_refresh = True

        # 快速首帧：随机化后先以低质量即时出图（点击立即刷新），再由后台补全全质量
        self._quick_first_frame = True

        # 强制发送文档变化信号，确保UI更新
        self.document_changed.emit()
        self.layer_changed.emit()  # 也发送图层变化信号
    


    def _randomize_text_layer_with_binding_categories(self, text_layer, binding_categories: List[str]):
        """在绑定组公共分类限制下随机化文字图层"""
        from app.models.text_layer import TextLayer
        
        if not isinstance(text_layer, TextLayer):
            return
            
        text_lines = text_layer.get_text_lines()
        if not text_lines:
            return
        
        # 🔧 关键修复：只选择包含绑定组公共分类关键词的文字
        eligible_texts = []
        
        for text_line in text_lines:
            text_stripped = str(text_line).strip()
            if not text_stripped:
                continue
                
            # 检查文字内容是否包含任何绑定组公共分类关键词
            for category in binding_categories:
                if category in text_stripped:
                    eligible_texts.append(text_stripped)
                    break
        
        if eligible_texts:
            # 从符合条件的文字中随机选择
            selected_text = random.choice(eligible_texts)
            text_layer.current_text = selected_text
            print(f"[绑定组文字限制] 文字图层 '{text_layer.name}' 从 {len(eligible_texts)} 个符合分类的文字中选择: {selected_text}")
        else:
            # 如果没有符合分类的文字，不要强制使用分类名称，保持原有文字
            # 强制使用分类名称会导致文字内容被改为商品类别，这不是用户期望的行为
            # 例如：分类是"半身裙"，但文字图层不应该被强制改为"半身裙"
            
            # 使用原始文字，保持用户设置的内容不变
            if text_lines:
                default_text = text_lines[0]
                text_layer.current_text = default_text
                print(f"[绑定组文字限制] 文字图层 '{text_layer.name}' 保持原有文字: {default_text}")
            else:
                # 如果没有文字行，保持当前文字不变
                print(f"[绑定组文字限制] 文字图层 '{text_layer.name}' 保持当前文字: {text_layer.current_text}")
    


    def _randomize_image_layer_with_binding_categories(self, image_layer, binding_categories: List[str]):
        """在绑定组公共分类限制下随机化普通图层"""
        if not image_layer.image_source or not os.path.isdir(image_layer.image_source):
            return
        
        # 🔧 关键修复：只选择文件名包含绑定组公共分类关键词的图像
        eligible_files = []
        
        try:
            for file in os.listdir(image_layer.image_source):
                ext = os.path.splitext(file)[1].lower()
                if ext not in ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tiff']:
                    continue
                    
                filename_without_ext = os.path.splitext(file)[0]
                
                # 检查文件名是否包含任何绑定组公共分类关键词
                for category in binding_categories:
                    if category in filename_without_ext:
                        eligible_files.append(file)
                        break
        except Exception as e:
            print(f"[绑定组图像限制] 扫描图层 '{image_layer.name}' 文件时出错: {e}")
            return
        
        if eligible_files:
            # 从符合条件的文件中随机选择
            selected_file = random.choice(eligible_files)
            file_path = os.path.join(image_layer.image_source, selected_file)
            
            # 🔧 关键修复：使用公共属性setter设置图像路径
            if hasattr(image_layer, 'current_image_path'):
                image_layer.current_image_path = file_path
            else:
                # 如果没有该属性，尝试其他方法
                try:
                    image_layer.get_random_image(force_random=True)
                except:
                    logger.debug("静默异常已忽略: except: in document_randomize.py")
                    pass
            
            # 清除缓存
            image_layer.cached_image = None
            if hasattr(image_layer, '_cached_image_path'):
                image_layer._cached_image_path = None
                
            print(f"[绑定组图像限制] 图层 '{image_layer.name}' 从 {len(eligible_files)} 个符合分类的图像中选择: {selected_file}")
        else:
            # 未找到符合分类的图像时，不再跨类随机，保持当前状态避免破坏组合一致性
            print(f"[绑定组图像限制] 图层 '{image_layer.name}' 无符合分类的图像，跳过随机以保持绑定一致性")



    def _scale_content_to_fit(self, image, target_width, target_height):
        """对内容等比缩放以适应目标区域，不裁剪
        
        参数:
            image: PIL图像对象
            target_width: 目标宽度
            target_height: 目标高度
            
        返回:
            处理后的PIL图像对象，大小与目标相同，内容按比例缩放居中
        """
        if not image:
            return None
            
        # 创建透明背景
        result = Image.new('RGBA', (target_width, target_height), (0, 0, 0, 0))
        
        # 计算原始图像和目标区域的宽高比
        original_ratio = image.width / image.height
        target_ratio = target_width / target_height
        
        if original_ratio > target_ratio:
            # 原图更宽，以宽度为基准调整
            new_width = target_width
            new_height = int(new_width / original_ratio)
            resized = image.resize((new_width, new_height), Resampling.BICUBIC)
            
            # 垂直居中放置
            y_offset = (target_height - new_height) // 2
            result.paste(resized, (0, y_offset), resized)
            
            print(f"智能缩放不裁剪: 原图更宽, 缩放尺寸 {new_width}x{new_height}")
            print(f"智能缩放不裁剪: 最终尺寸 {target_width}x{target_height}, 内容位置 (0, {y_offset})")
        else:
            # 原图更高或等比例，以高度为基准调整
            new_height = target_height
            new_width = int(original_ratio * new_height)
            resized = image.resize((new_width, new_height), Resampling.BICUBIC)
            
            # 水平居中放置
            x_offset = (target_width - new_width) // 2
            result.paste(resized, (x_offset, 0), resized)
            
            print(f"智能缩放不裁剪: 原图更高, 缩放尺寸 {new_width}x{new_height}")
            print(f"智能缩放不裁剪: 最终尺寸 {target_width}x{target_height}, 内容位置 ({x_offset}, 0)")
            
        return result
    


    def _process_image_for_layer(self, image, target_width, target_height):
        """处理图像以适应目标尺寸，智能裁剪模式(保持纵横比)
        
        参数:
            image: PIL图像对象
            target_width: 目标宽度
            target_height: 目标高度
            
        返回:
            处理后的PIL图像对象
        """
        if not image:
            return None
            
        # 计算原始图像和目标区域的宽高比
        original_ratio = image.width / image.height
        target_ratio = target_width / target_height
        
        if original_ratio > target_ratio:
            # 原图更宽，以高度为基准调整
            new_height = target_height
            new_width = int(original_ratio * new_height)
            # 居中裁剪
            left = (new_width - target_width) // 2
            right = left + target_width
            resized = image.resize((new_width, new_height), Resampling.BICUBIC)
            
            print(f"智能缩放裁剪: 原图更宽, 缩放尺寸 {new_width}x{new_height}")
            print(f"裁剪: 区域 ({left}, 0, {right}, {target_height})")
            
            cropped = resized.crop((left, 0, right, target_height))
            print(f"裁剪后尺寸: {cropped.width}x{cropped.height}, 期望尺寸: {target_width}x{target_height}")
            return cropped
        else:
            # 原图更高，以宽度为基准调整
            new_width = target_width
            new_height = int(new_width / original_ratio)
            # 居中裁剪
            top = (new_height - target_height) // 2
            bottom = top + target_height
            resized = image.resize((new_width, new_height), Resampling.BICUBIC)
            
            print(f"智能缩放裁剪: 原图更高, 缩放尺寸 {new_width}x{new_height}")
            print(f"裁剪: 区域 (0, {top}, {target_width}, {bottom})")
            
            cropped = resized.crop((0, top, target_width, bottom))
            print(f"裁剪后尺寸: {cropped.width}x{cropped.height}, 期望尺寸: {target_width}x{target_height}")
            return cropped
    


    def _optimize_memory(self):
        """优化内存使用，减少内存占用"""
        try:
            from app.utils.memory_manager import get_memory_manager
            memory_manager = get_memory_manager()

            # 记录优化前的内存使用
            memory_before = memory_manager.get_memory_usage()

            # 清除图层缓存
            for layer in self.layers:
                if hasattr(layer, 'clear_cache'):
                    layer.clear_cache()
                elif hasattr(layer, '_cached_images'):
                    layer._cached_images = {}

            # 使用内存管理器进行清理
            freed_mb = memory_manager.force_cleanup()

            print(f"文档内存优化完成: 释放 {freed_mb} MB")

        except ImportError:
            # 回退到原有的简单清理方式
            import gc
            for layer in self.layers:
                if hasattr(layer, 'clear_cache'):
                    layer.clear_cache()
                elif hasattr(layer, '_cached_images'):
                    layer._cached_images = {}
            gc.collect()
            print("内存优化完成（简化模式）")
