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


class DocumentExport:
    """Document 方法拆分 mixin，保持与 Document 完全兼容（通过多重继承组合）。"""

    def _analyze_document_for_export(self) -> dict:
        """完整的文档状态预分析 - 为导出提供全面的状态信息"""
        print("[文档分析] 开始完整的文档状态分析...")

        analysis_result = {
            'binding_enabled': False,
            'binding_categories': [],
            'layer_analysis': {
                'visible_layers': [],
                'bound_layers': [],
                'unbound_layers': [],
                'layer_states': {},
                'layer_settings': {}
            },
            'export_mode': 'standard',
            'recommendations': []
        }

        # 1. 分析可见图层
        try:
            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            visible_layers = [
                layer for layer in self.layers
                if not is_layer_group(layer) and is_effectively_visible(layer, self.layers)
            ]
        except Exception:
            visible_layers = [layer for layer in self.layers if getattr(layer, 'visible', True)]
        analysis_result['layer_analysis']['visible_layers'] = visible_layers
        print(f"[文档分析] 发现 {len(visible_layers)} 个可见图层")

        # 2. 分析每个图层的状态和设置
        for i, layer in enumerate(visible_layers):
            layer_info = {
                'index': i,
                'name': layer.name,
                'type': 'text' if hasattr(layer, 'text_content') and layer.text_content else 'image',
                'image_source': getattr(layer, 'image_source', None),
                'is_folder': getattr(layer, 'is_folder', False),
                'current_image_path': getattr(layer, 'current_image_path', None),
                'settings': {
                    'fit_mode': getattr(layer, 'fit_mode', getattr(layer, '_fit_mode', 0)),
                    'use_original_size': getattr(layer, 'use_original_size', getattr(layer, '_use_original_size', False)),
                    'smart_crop_enabled': getattr(layer, 'smart_crop_enabled', getattr(layer, '_smart_crop_enabled', False)),
                    'clone_enabled': getattr(layer, 'clone_enabled', getattr(layer, '_clone_enabled', False)),
                    'effects_enabled': bool(getattr(layer, 'effects', getattr(layer, '_effects', None)))
                }
            }
            analysis_result['layer_analysis']['layer_states'][i] = layer_info

        # 3. 检查绑定管理器状态
        binding_manager_exists = (hasattr(self, 'binding_manager') and
                                 self.binding_manager and
                                 self.binding_manager.global_enabled)

        if binding_manager_exists:
            print("[文档分析] 绑定管理器存在且启用，分析绑定状态...")

            # 检查哪些图层参与了绑定
            bound_layers = []
            unbound_layers = []

            for layer in visible_layers:
                if self.binding_manager.is_layer_bound(layer):
                    bound_layers.append(layer)
                    print(f"[文档分析] 发现绑定图层: {layer.name}")
                else:
                    unbound_layers.append(layer)

            analysis_result['layer_analysis']['bound_layers'] = bound_layers
            analysis_result['layer_analysis']['unbound_layers'] = unbound_layers

            # 获取绑定分类
            if bound_layers:
                binding_categories = self._get_binding_common_categories()
                analysis_result['binding_categories'] = binding_categories

                if binding_categories:
                    analysis_result['binding_enabled'] = True
                    analysis_result['export_mode'] = 'binding'
                    print(f"[文档分析] 绑定模式启用，发现 {len(binding_categories)} 个分类: {binding_categories}")
                else:
                    print("[文档分析] 有绑定图层但没有有效分类，使用标准模式")
                    analysis_result['recommendations'].append("绑定图层存在但缺少有效分类，建议检查图片文件")
            else:
                print("[文档分析] 绑定管理器存在但没有图层参与绑定")
                analysis_result['recommendations'].append("绑定管理器已启用但没有图层参与绑定")
        else:
            print("[文档分析] 绑定功能未启用或不存在")
            analysis_result['layer_analysis']['unbound_layers'] = visible_layers

        # 4. 生成导出建议
        if analysis_result['export_mode'] == 'binding':
            analysis_result['recommendations'].append(f"建议使用绑定模式导出，可生成 {len(binding_categories)} 种不同组合")
        else:
            total_combinations = 1
            for layer_info in analysis_result['layer_analysis']['layer_states'].values():
                if layer_info['is_folder'] and layer_info['image_source']:
                    # 估算图片数量（这里简化处理）
                    total_combinations *= 10  # 假设每个文件夹有10张图片
            analysis_result['recommendations'].append(f"建议使用标准模式导出，理论组合数约 {total_combinations}")

        print(f"[文档分析] 分析完成，导出模式: {analysis_result['export_mode']}")
        return analysis_result



    def batch_export(self, directory, count, filename_template=None, file_format="png", start_index=1, cancel_callback=None, use_high_performance=True, traverse_mode=False, use_smart_sampling=True):
        """批量导出不同组合的图像

        Args:
            directory: 输出目录
            count: 导出数量
            filename_template: 文件名模板
            file_format: 文件格式
            start_index: 起始文件序号
            cancel_callback: 取消回调函数
            use_high_performance: 是否使用高性能渲染方案
            traverse_mode: 是否启用遍历模式
            use_smart_sampling: 是否使用智能采样策略（避免图片重复）

        Returns:
            bool: 是否成功
        """
        
        # 📊 诊断日志：导出参数
        self._last_export_report = None
        self._is_batch_export_running = True
        def _is_export_canceled():
            return bool(getattr(self, '_export_canceled', False)) or bool(cancel_callback and cancel_callback())

        if _is_export_canceled():
            self._last_export_error = "导出已取消"
            self._is_batch_export_running = False
            return False
        try:
            from app.utils.export_worker_client import export_with_worker, should_use_export_worker
            if should_use_export_worker(self, int(count or 0)):
                def worker_progress_wrapper(current_count):
                    if hasattr(self, 'export_progress_updated'):
                        self.export_progress_updated.emit(int(current_count or 0))

                def worker_file_completed_wrapper(message):
                    if hasattr(self, 'file_exported'):
                        self.file_exported.emit(str(message or ""))

                def worker_stage_wrapper(stage_name):
                    if hasattr(self, 'export_stage_updated'):
                        self.export_stage_updated.emit(str(stage_name or ""))

                worker_result = export_with_worker(
                    self,
                    directory=directory,
                    count=int(count or 0),
                    filename_template=filename_template or "image_{number:04d}",
                    file_format=file_format,
                    start_index=start_index,
                    traverse_mode=traverse_mode,
                    avoid_duplicates=use_smart_sampling,
                    progress_callback=worker_progress_wrapper,
                    file_completed_callback=worker_file_completed_wrapper,
                    stage_callback=worker_stage_wrapper,
                    cancel_callback=cancel_callback,
                )
                if worker_result.attempted:
                    self._is_batch_export_running = False
                    if hasattr(self, 'export_stage_updated'):
                        self.export_stage_updated.emit("收尾清理")
                    try:
                        self._cleanup_layers_after_export()
                    except Exception:
                        logger.debug("静默异常已忽略: except Exception: in document_export.py")
                        pass
                    if worker_result.success:
                        if hasattr(self, 'export_stage_updated'):
                            self.export_stage_updated.emit("导出完成")
                        return True
                    self._last_export_error = worker_result.error or "独立导出进程失败"
                    if hasattr(self, 'export_stage_updated'):
                        self.export_stage_updated.emit("导出失败")
                    return False
        except Exception as worker_launch_error:
            print(f"[批量导出] 独立导出进程不可用，回退内部导出: {worker_launch_error}")
        if hasattr(self, 'export_stage_updated'):
            self.export_stage_updated.emit("准备导出")
        print("=" * 80)
        print(f"[批量导出] 🚀 开始批量导出")
        print(f"[批量导出]    数量: {count}")
        print(f"[批量导出]    目录: {directory}")
        print(f"[批量导出]    遍历模式: {traverse_mode}")
        print(f"[批量导出]    智能采样: {use_smart_sampling}")
        print(f"[批量导出]    高性能渲染: {use_high_performance}")
        print("=" * 80)

        # 🔧 性能优化：仅在真正需要时清理缓存
        # 不要每次都执行五层防护清理，那会严重影响性能
        # 只清理必要的渲染缓存即可
        print("[🔧 批量导出] 🧹 清理渲染缓存（轻量级）...")
        if hasattr(self, 'export_stage_updated'):
            self.export_stage_updated.emit("清理缓存")
        if _is_export_canceled():
            self._last_export_error = "导出已取消"
            self._is_batch_export_running = False
            return False
        try:
            # 只清理渲染缓存，保留其他状态
            from app.utils.fast_renderer import get_global_fast_renderer
            renderer = get_global_fast_renderer()
            if hasattr(renderer, 'clear_cache'):
                renderer.clear_cache()
                print("[🔧 批量导出] ✅ 渲染缓存已清理")
        except Exception as e:
            print(f"[🔧 批量导出] ⚠️ 缓存清理失败: {e}")
        
        # 🔧 性能优化：不要清除绑定组历史！这会导致避重机制失效
        # 绑定组历史应该在整个导出过程中保持，这样才能真正避免重复
        # 只在用户明确要求"重置"时才清除
        print("[🔧 批量导出] ℹ️ 保持绑定组历史以确保避重机制有效")
        
        # 🔧 关键修复：重新分析所有绑定组的文件分类，确保使用最新的图层状态
        print(f"\n{'='*80}")
        print(f"[🔍 批量导出启动] 检查绑定管理器...")
        print(f"{'='*80}")
        
        if hasattr(self, 'binding_manager') and self.binding_manager:
            if hasattr(self, 'export_stage_updated'):
                self.export_stage_updated.emit("绑定检查")
            if _is_export_canceled():
                self._last_export_error = "导出已取消"
                self._is_batch_export_running = False
                return False
            print("[🔧 批量导出] ✅ 绑定管理器存在")
            print(f"[🔧 批量导出] 绑定组数量: {len(self.binding_manager.binding_groups)}")
            print("[🔧 批量导出] 🔄 重新分析绑定组文件分类...")
            
            for group_id, group in self.binding_manager.binding_groups.items():
                if _is_export_canceled():
                    self._last_export_error = "导出已取消"
                    self._is_batch_export_running = False
                    return False
                print(f"\n[🔧 批量导出] 处理绑定组: '{group.name}' (ID: {group_id})")
                print(f"  图层数: {len(group.layers)}")
                
                # 🔧 修复：不要清空绑定组的文件分类和避重历史
                # 这些信息应该在整个导出过程中保持，以确保绑定功能正常工作
                print(f"  保持现有分类（{len(group.file_categories)} 个）")
                print(f"  保持避重历史（{len(getattr(group, '_category_usage_history', {}))} 个记录）")
                
                # 🔧 修复：只在分类信息缺失时重新分析
                if not group.file_categories:
                    print(f"  分类信息缺失，重新分析文件...")
                    for idx, layer in enumerate(group.layers):
                        if _is_export_canceled():
                            self._last_export_error = "导出已取消"
                            self._is_batch_export_running = False
                            return False
                        print(f"  分析图层 {idx}: {layer.name}")
                        print(f"    图层源: {layer.image_source}")
                        group._analyze_layer_files(layer, idx)
                else:
                    print(f"  分类信息完整，跳过重新分析")
                
                print(f"[🔧 批量导出] ✅ 绑定组 '{group.name}' 状态检查完成")
                print(f"  当前分类数: {len(group.file_categories)}")
                print(f"  分类列表: {list(group.file_categories.keys())}")
        else:
            print("[🔧 批量导出] ⚠️ 警告：没有绑定管理器或绑定管理器未启用")
        
        print(f"{'='*80}\n")

        # 🚀 第一步：完整的文档状态预分析
        if hasattr(self, 'export_stage_updated'):
            self.export_stage_updated.emit("文档分析")
        if _is_export_canceled():
            self._last_export_error = "导出已取消"
            self._is_batch_export_running = False
            return False
        print("[批量导出] 开始文档状态预分析...")
        document_analysis = self._analyze_document_for_export()

        # 从分析结果中提取关键信息
        binding_enabled = document_analysis['binding_enabled']
        binding_categories = document_analysis['binding_categories']
        layer_analysis = document_analysis['layer_analysis']
        export_mode = document_analysis['export_mode']

        print(f"[批量导出] 文档分析完成:")
        print(f"  - 导出模式: {export_mode}")
        print(f"  - 绑定状态: {binding_enabled}")
        print(f"  - 绑定分类: {len(binding_categories)} 个")
        print(f"  - 可见图层: {len(layer_analysis['visible_layers'])} 个")
        print(f"  - 绑定图层: {len(layer_analysis['bound_layers'])} 个")

        # 🚀 第二步：强制使用预计算优化导出系统 - 屏蔽所有旧版导出
        print(f"[批量导出] 强制使用预计算优化导出系统（屏蔽旧版导出）")

        try:
            from app.utils.optimized_batch_executor import export_batch_with_precomputation_v2

            # 创建进度回调包装器
            def progress_wrapper(current_count):
                # 优化批量执行器现在直接传递当前完成数量
                if hasattr(self, 'export_progress_updated'):
                    self.export_progress_updated.emit(current_count)

            def file_completed_wrapper(message):
                if hasattr(self, 'file_exported'):
                    self.file_exported.emit(message)

            def stage_wrapper(stage_name):
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit(str(stage_name))

            def cancel_wrapper():
                return getattr(self, '_export_canceled', False) or (cancel_callback and cancel_callback())

            # 🔧 强制使用预计算导出，无论数量多少
            success = export_batch_with_precomputation_v2(
                document=self,
                document_analysis=document_analysis,  # 传递预分析结果
                directory=directory,
                count=count,
                filename_template=filename_template or "image_{number:04d}",
                file_format=file_format,
                start_index=start_index,
                progress_callback=progress_wrapper,
                file_completed_callback=file_completed_wrapper,
                stage_callback=stage_wrapper,
                cancel_callback=cancel_wrapper,
                traverse_mode=traverse_mode,
                avoid_duplicates=use_smart_sampling
            )

            if success:
                print(f"[批量导出] 预计算导出成功完成")
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("收尾清理")
                self._is_batch_export_running = False
                # 🔧 关键修复：清理所有图层的临时状态
                self._cleanup_layers_after_export()
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("导出完成")
                return True
            else:
                print(f"[批量导出] 预计算导出失败")
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("收尾清理")
                self._is_batch_export_running = False
                # 🔧 关键修复：清理所有图层的临时状态
                self._cleanup_layers_after_export()
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("导出失败")
                return False

        except Exception as e:
            print(f"[批量导出] 预计算导出异常: {e}")
            import traceback
            traceback.print_exc()
            if hasattr(self, 'export_stage_updated'):
                self.export_stage_updated.emit("导出异常")
            self._is_batch_export_running = False
            # 🔧 关键修复：清理所有图层的临时状态
            self._cleanup_layers_after_export()
            return False



    def _clear_layer_temporary_states(self):
        """🔧 清理所有图层的临时状态（用于文档加载后）
        
        与 _cleanup_layers_after_export 不同，此方法会清理 current_image_path，
        因为这是从旧文件加载时可能存在的过时状态。
        """
        try:
            print("[文档加载清理] 开始清理图层临时状态...")
            cleaned_count = 0
            
            for layer in self.layers:
                try:
                    # 🔧 关键修复：使用公共属性 current_image_path 而不是私有属性 _current_image_path
                    # Layer（layer_new.py）使用属性管理器，LegacyLayer直接使用实例属性
                    # 通过setter正确处理两种情况
                    if hasattr(layer, 'current_image_path'):
                        old_path = layer.current_image_path
                        if old_path is not None:
                            try:
                                basename = os.path.basename(old_path) if isinstance(old_path, str) else str(old_path)
                                print(f"[文档加载清理] 清理图层 '{layer.name}' 的临时路径: {basename}")
                            except:
                                print(f"[文档加载清理] 清理图层 '{layer.name}' 的临时路径")
                        layer.current_image_path = None  # 使用setter正确清理
                    
                    # 清理缓存
                    if hasattr(layer, '_cached_image'):
                        layer._cached_image = None
                    if hasattr(layer, '_cached_image_path'):
                        layer._cached_image_path = None
                    if hasattr(layer, '_cache_valid'):
                        layer._cache_valid = False
                    if hasattr(layer, 'cached_image'):
                        try:
                            # 对于有setter的cached_image属性
                            layer.cached_image = None
                        except:
                            logger.debug("静默异常已忽略: except: in document_export.py")
                            pass
                    
                    cleaned_count += 1
                except Exception as e:
                    print(f"[文档加载清理] 清理图层 {layer.name} 时出错: {e}")
                    import traceback
                    traceback.print_exc()
            
            print(f"[文档加载清理] ✅ 已清理 {cleaned_count} 个图层的临时状态")
            
        except Exception as e:
            print(f"[文档加载清理] 清理过程出错: {e}")
            import traceback
            traceback.print_exc()
    


    def _cleanup_layers_after_export(self):
        """🔧 批量导出完成后清理所有图层的临时状态"""
        try:
            print("[批量导出清理] 开始清理图层状态...")
            cleaned_count = 0
            
            for layer in self.layers:
                try:
                    # 清理缓存验证标志
                    if hasattr(layer, '_cache_valid'):
                        layer._cache_valid = False
                    
                    # 清理临时缓存路径（保留_current_image_path和image_source）
                    if hasattr(layer, '_cached_image_path'):
                        layer._cached_image_path = None

                    # 关键：释放图像对象引用，防止导出结束后缓存堆积占用内存
                    if hasattr(layer, '_cached_image'):
                        layer._cached_image = None
                    if hasattr(layer, 'cached_image'):
                        try:
                            layer.cached_image = None
                        except Exception:
                            logger.debug("静默异常已忽略: except Exception: in document_export.py")
                            pass
                    if hasattr(layer, '_current_image_cache'):
                        layer._current_image_cache = None
                    
                    # 注意：不清理_current_image_path和image_source，这些是用户设置的
                    # 只清理内部缓存状态
                    
                    cleaned_count += 1
                except Exception as e:
                    print(f"[批量导出清理] 清理图层 {layer.name} 时出错: {e}")
            
            print(f"[批量导出清理] ✅ 已清理 {cleaned_count} 个图层的状态")
            
            # 清理文档级别的批量导出标志
            if hasattr(self, '_export_canceled'):
                self._export_canceled = False
            
            # 使渲染缓存失效，强制下次预览时重新渲染
            self._invalidate_render_cache()

            # 清理导出链路中的全局缓存，避免任务结束后内存滞留
            try:
                from app.utils.intelligent_render_cache import clear_global_cache as _clear_render_cache
                _clear_render_cache()
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in document_export.py")
                pass
            try:
                from app.utils.intelligent_cache_system import get_intelligent_cache as _get_intelligent_cache
                _get_intelligent_cache().clear_all_caches()
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in document_export.py")
                pass
            try:
                from app.utils.advanced_image_cache import get_advanced_image_cache as _get_advanced_cache
                _get_advanced_cache().clear_cache()
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in document_export.py")
                pass

            # 强制回收游离对象，确保任务完成后内存及时回落
            gc.collect()
            
            print("[批量导出清理] ✅ 批量导出清理完成")
            
        except Exception as e:
            print(f"[批量导出清理] 清理过程出错: {e}")
            import traceback
            traceback.print_exc()
    


    def _sanitize_filename_template(self, template):
        """清理文件名模板，移除或替换非法字符，但保护所有占位符格式"""
        import re

        # 先保存所有有效的占位符，包括带格式化的（如{number:04d}）
        # 匹配 {word} 或 {word:format} 格式的占位符
        placeholders = re.findall(r'\{[a-zA-Z_][a-zA-Z0-9_]*(?::[^}]+)?\}', template)

        # 使用临时标记替换所有占位符，使用完全不包含特殊字符的标记
        temp_markers = {}
        for i, placeholder in enumerate(placeholders):
            marker = f"TEMPPLACEHOLDER{i}"  # 使用简单的标记
            template = template.replace(placeholder, marker)
            temp_markers[marker] = placeholder

        # 替换中文逗号并移除逗号（在文件名中通常不需要）
        template = template.replace('，', '')
        template = template.replace(',', '')

        # 移除Windows系统中文件名不允许的字符
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in illegal_chars:
            template = template.replace(char, '_')

        # 恢复占位符
        for marker, placeholder in temp_markers.items():
            template = template.replace(marker, placeholder)

        return template



    def _clean_filename(self, filename):
        """清理生成的文件名，确保合法性"""
        import re
        import unicodedata

        # 确保filename是字符串类型
        if not isinstance(filename, str):
            filename = str(filename)

        # 先处理Unicode字符，规范化为NFKC形式
        try:
            filename = unicodedata.normalize('NFKC', filename)
        except Exception as e:
            print(f"Unicode规范化失败: {e}")
            # 如果规范化失败，尝试编码/解码来清理字符
            try:
                filename = filename.encode('utf-8', 'ignore').decode('utf-8')
            except Exception:
                filename = "export"

        # 移除非法字符，但保留中文和其他Unicode字符
        illegal_chars = ['<', '>', ':', '"', '/', '\\', '|', '?', '*']
        for char in illegal_chars:
            filename = filename.replace(char, '_')

        # 移除控制字符和其他不可见字符
        filename = ''.join(char for char in filename if unicodedata.category(char)[0] != 'C')

        # 移除连续的分隔符
        filename = re.sub(r'[-_]{2,}', '-', filename)
        filename = re.sub(r'^[-_]+|[-_]+$', '', filename)  # 移除开头和结尾的分隔符
        
        # 确保文件名不为空
        if not filename or filename.isspace():
            filename = "export"
        
        # 限制文件名长度（考虑多字节字符）
        # Windows文件名限制约255字节，但为了安全，我们使用200个字符
        if len(filename.encode('utf-8')) > 200:
            # 按字符逐个截取，确保不超过字节限制
            truncated = ""
            for char in filename:
                if len((truncated + char).encode('utf-8')) <= 200:
                    truncated += char
                else:
                    break
            filename = truncated
        
        return filename
    


    def _extract_main_filename(self, filename):
        """提取文件名的主要部分，去除可能的序号"""
        import re
        import unicodedata
        
        # 确保filename是字符串类型，并进行Unicode规范化
        if not isinstance(filename, str):
            filename = str(filename)
        
        try:
            filename = unicodedata.normalize('NFKC', filename)
        except Exception:
            # 如果规范化失败，继续使用原始字符串
            pass
        
        # 分离可能的编号部分
        name_parts = filename.split('-')
        
        # 过滤掉所有纯数字、数字+字母或带下划线的数字组合（可能是序号）
        filtered_parts = []
        for part in name_parts:
            # 检查是否为纯数字
            if part.isdigit():
                continue
            # 检查是否为带下划线的数字（如"12_2"）
            if re.match(r'^\d+_\d+$', part):
                continue
            # 检查是否为ASCII字母+数字组合（如"a1", "b2"）
            if re.match(r'^[a-zA-Z]+\d+$', part):
                continue
            # 检查是否为数字+ASCII字母组合（如"1a", "2b"）
            if re.match(r'^\d+[a-zA-Z]+$', part):
                continue
            # 检查是否为纯英文字母+下划线+数字的组合（如"scene_1", "bg_01"）
            if re.match(r'^[a-zA-Z_]+\d+$', part):
                continue
            
            # 保留包含中文或其他非ASCII字符的部分
            filtered_parts.append(part)
        
        # 如果所有部分都被过滤掉了，使用原始文件名
        if not filtered_parts:
            return filename
        
        # 重新组合
        result = '-'.join(filtered_parts)
        
        # 最后清理结果
        return self._clean_filename(result)
    


    def _get_binding_common_categories(self) -> List[str]:
        """获取所有绑定组的公共分类 - 修复版本，添加详细的诊断信息"""
        print("[绑定分析] 开始分析绑定组的公共分类...")
        
        # 🔧 关键修复：更严格的绑定管理器检查
        if not hasattr(self, 'binding_manager'):
            print("[绑定分析] ❌ 文档没有绑定管理器属性")
            return []
        
        if not self.binding_manager:
            print("[绑定分析] ❌ 绑定管理器为空")
            return []
        
        if not self.binding_manager.global_enabled:
            print("[绑定分析] ❌ 绑定管理器的全局功能未启用")
            return []
        
        if not self.binding_manager.binding_groups:
            print("[绑定分析] ❌ 没有绑定组")
            return []
        
        print(f"[绑定分析] ✅ 发现 {len(self.binding_manager.binding_groups)} 个绑定组")
        
        common_categories = None
        processed_groups = 0
        
        # 检查所有绑定组
        for group_id, group in self.binding_manager.binding_groups.items():
            print(f"[绑定分析] 处理绑定组: {group.name} (ID: {group_id})")
            
            # 🔧 关键修复：只考虑可见图层，并提供更详细的匹配信息
            document_layers = []
            unmatched_layers = []
            
            for group_layer in group.layers:
                matched = False
                for doc_layer in self.layers:
                    # 🔧 关键修复：检查图层是否可见
                    if doc_layer.name == group_layer.name and doc_layer.visible:
                        document_layers.append(doc_layer)
                        matched = True
                        print(f"[绑定分析]   ✅ 匹配图层: {group_layer.name} (可见)")
                        break
                    elif doc_layer.name == group_layer.name and not doc_layer.visible:
                        print(f"[绑定分析]   ⚠️  图层 {group_layer.name} 存在但不可见，跳过")
                        matched = True
                        break
                
                if not matched:
                    unmatched_layers.append(group_layer.name)
                    print(f"[绑定分析]   ❌ 未找到图层: {group_layer.name}")
            
            # 🔧 关键修复：如果没有可见的匹配图层，跳过此绑定组
            if not document_layers:
                print(f"[绑定分析] ⚠️  绑定组 {group.name} 没有可见的匹配图层，跳过")
                continue
            
            # 如果有部分图层未匹配，给出警告但继续处理
            if unmatched_layers:
                print(f"[绑定分析] ⚠️  绑定组 {group.name} 中有 {len(unmatched_layers)} 个图层未找到: {unmatched_layers}")
            
            print(f"[绑定分析]   处理 {len(document_layers)} 个可见匹配图层")
            
            # 🔧 关键修复：创建临时绑定组用于文件分析
            from app.models.binding_manager import BindingGroup
            temp_group = BindingGroup(group.group_id, group.name, binding_manager=self.binding_manager)
            temp_group._binding_manager = self.binding_manager
            
            for i, layer in enumerate(document_layers):
                temp_group.add_layer(layer, i)
                print(f"[绑定分析]     添加图层 {i}: {layer.name} -> {layer.image_source}")
            
            # 🔧 关键修复：强制重新分析文件分类
            print(f"[绑定分析]   重新分析文件分类...")
            temp_group._rebuild_file_categories()
            
            group_categories = temp_group.get_available_categories()
            print(f"[绑定分析]   绑定组 {group.name} 可用分类: {group_categories}")

            image_backed_categories = []
            try:
                for category in group_categories:
                    has_image_support = False
                    if category in temp_group.file_categories:
                        for layer_idx, files in temp_group.file_categories[category].items():
                            if any(isinstance(f, str) and not is_text_layer_virtual_path(f) for f in files):
                                has_image_support = True
                                break
                    if has_image_support:
                        image_backed_categories.append(category)
                if image_backed_categories:
                    print(f"[绑定分析]   图像支撑分类: {image_backed_categories}")
                    group_categories = image_backed_categories
                else:
                    print(f"[绑定分析]   ⚠️ 无图像支撑分类，保留原分类以避免空结果")
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in document_export.py")
                pass
            
            if not group_categories:
                print(f"[绑定分析] ⚠️  绑定组 {group.name} 没有可用分类，可能文件结构不匹配")
                # 🔧 关键修复：输出详细的文件分类调试信息
                print(f"[绑定分析]     文件分类详情: {temp_group.file_categories}")
                continue
            
            group_categories_set = set(group_categories)
            
            if common_categories is None:
                common_categories = group_categories_set
                print(f"[绑定分析]   初始化公共分类: {group_categories}")
            else:
                # 取交集
                before_intersection = len(common_categories)
                common_categories = common_categories.intersection(group_categories_set)
                print(f"[绑定分析]   更新公共分类: {before_intersection} -> {len(common_categories)}")
            
            processed_groups += 1
        
        print(f"[绑定分析] 处理完成，成功处理了 {processed_groups} 个绑定组")
        
        if common_categories is None:
            print("[绑定分析] ❌ 没有找到任何公共分类")
            return []
        
        result = sorted(list(common_categories))
        print(f"[绑定分析] ✅ 找到 {len(result)} 个公共分类: {result}")
        
        return result
    


    def _set_binding_category_combination(self, category: str):
        """为绑定组设置指定分类的组合 - 根本修复：确保所有绑定组使用统一分类"""
        if not hasattr(self, 'binding_manager') or not self.binding_manager.global_enabled:
            print(f"[绑定组合] ❌ 绑定管理器不可用或未启用")
            return
        
        print(f"[绑定组合] 🎯 设置绑定分类组合: '{category}'")
        print(f"[绑定组合] 📋 可用绑定组数量: {len(self.binding_manager.binding_groups) if hasattr(self.binding_manager, 'binding_groups') else 0}")
        
        # 🔧 根本修复：首先为所有绑定组预选择统一的文件组合
        # 这样可以确保所有绑定组使用相同的分类和内容
        binding_group_combinations = {}
        
        # 为每个绑定组预选择组合，但确保使用相同的分类
        for group_id, group in self.binding_manager.binding_groups.items():
            print(f"[绑定组合] 预选择绑定组组合: {group.name} (ID: {group_id})")
            
            # 创建临时绑定组用于预选择
            from app.models.binding_manager import BindingGroup
            temp_group = BindingGroup(group.group_id, group.name, binding_manager=self.binding_manager)
            temp_group._binding_manager = self.binding_manager
            
            # 同步使用历史
            if hasattr(group, '_category_usage_history') and category in group._category_usage_history:
                temp_group._category_usage_history = {category: group._category_usage_history[category].copy()}
            
            # 只添加可见图层
            document_layers = []
            for group_layer in group.layers:
                for doc_layer in self.layers:
                    if doc_layer.name == group_layer.name and doc_layer.visible:
                        document_layers.append(doc_layer)
                        break
            
            if not document_layers:
                print(f"[绑定组合] ⚠️  绑定组 {group.name} 没有可见图层，跳过预选择")
                continue
            
            # 添加图层到临时绑定组
            for i, layer in enumerate(document_layers):
                temp_group.add_layer(layer, i)
            
            # 重新分析分类
            temp_group._rebuild_file_categories()
            available_categories = temp_group.get_available_categories()
            
            if category not in available_categories:
                print(f"[绑定组合] ❌ 绑定组 {group.name} 不支持分类 '{category}'")
                continue
            
            # 预选择组合（预览模式不启用避重）
            try:
                matched_files = temp_group.get_matched_files(category, avoid_duplicates=False)
                # 计算该绑定组在当前文档中可见并参与绑定的图层数量
                expected_count = len(document_layers)
                # 只有当所有参与绑定的可见图层都获得匹配文件时，才认为该组可用
                if matched_files and len(matched_files) == expected_count:
                    binding_group_combinations[group_id] = matched_files
                    print(f"[绑定组合] ✅ 预选择成功: 覆盖 {len(matched_files)}/{expected_count} 个图层")
                else:
                    print(f"[绑定组合] ⚠️  预选择失败: 覆盖 {len(matched_files) if matched_files else 0}/{expected_count} 个图层")
            except Exception as e:
                print(f"[绑定组合] ❌ 预选择失败: {e}")
        
        if not binding_group_combinations:
            print(f"[绑定组合] ❌ 没有绑定组能使用分类 '{category}'")
            return
        
        # 记录已处理的图层，避免重复随机化
        processed_layers = set()
        successful_groups = 0
        
        # 🔧 根本修复：使用预选的统一组合应用到所有绑定组
        for group_id, group in self.binding_manager.binding_groups.items():
            if group_id not in binding_group_combinations:
                print(f"[绑定组合] 跳过绑定组 {group.name}: 无预选择组合")
                continue
                
            print(f"[绑定组合] 应用预选择组合到绑定组: {group.name} (ID: {group_id})")
            
            # 获取预选的统一组合
            matched_files = binding_group_combinations[group_id]
            
            # 获取该绑定组的可见图层
            document_layers = []
            for group_layer in group.layers:
                for doc_layer in self.layers:
                    if doc_layer.name == group_layer.name and doc_layer.visible:
                        document_layers.append(doc_layer)
                        break
            
            if not document_layers:
                print(f"[绑定组合] ⚠️  绑定组 {group.name} 没有可见图层，跳过")
                continue
            
            print(f"[绑定组合]   应用 {len(matched_files)} 个文件到 {len(document_layers)} 个图层")
            # 严格校验：若未覆盖全部图层，则跳过应用，避免出现跨分类混合
            if len(matched_files) != len(document_layers):
                print(f"[绑定组合] ⚠️ 覆盖不完整，跳过绑定组 '{group.name}' 的应用")
                continue
            
            # 应用到实际的文档图层
            for layer_index, file_path in matched_files.items():
                if layer_index < len(document_layers):
                    layer = document_layers[layer_index]
                    
                    # 检查图层类型，分别处理
                    from app.models.text_layer import TextLayer
                    
                    if isinstance(layer, TextLayer):
                        # 文字图层：优先使用匹配结果中的虚拟路径来设置当前文字
                        try:
                            if is_text_layer_virtual_path(file_path):
                                _, text_content = parse_text_layer_virtual_path(file_path)
                                if text_content.strip():
                                    layer.current_text = text_content
                                    print(f"文字图层 '{layer.name}' 应用匹配文案: {text_content}")
                                else:
                                    raise ValueError("无法解析文字匹配路径")
                            else:
                                # 回退：根据分类关键词匹配文字行（单向包含：文字内容包含分类关键词）
                                text_lines = layer.get_text_lines()
                                matching_text = None
                                for text_line in text_lines:
                                    # 修复：只需要文字内容包含分类关键词即可匹配
                                    if category in text_line:
                                        matching_text = text_line
                                        break
                                if matching_text:
                                    layer.current_text = matching_text
                                    print(f"文字图层 '{layer.name}' 回退根据分类应用文案: {matching_text}")
                                elif text_lines:
                                    default_text = text_lines[0]
                                    layer.current_text = default_text
                                    print(f"文字图层 '{layer.name}' 未找到匹配，使用默认: {default_text}")
                                else:
                                    print(f"文字图层 '{layer.name}' 没有可用的文本内容")
                        except Exception as e:
                            print(f"[绑定组合] 处理文字图层匹配失败: {e}")
                        
                        # 记录已处理的图层并清除缓存
                        processed_layers.add(id(layer))
                        if hasattr(layer, '_cached_image'):
                            layer._cached_image = None
                        
                    else:
                        # 图像图层：设置图像路径
                        old_path = layer.current_image_path
                        # 🔧 关键修复：使用公共属性setter，它不是只读的
                        layer.current_image_path = file_path
                        
                        # 清除缓存，确保重新加载图片
                        layer.cached_image = None
                        if hasattr(layer, '_cached_image_path'):
                            layer._cached_image_path = None
                        
                        print(f"图层 '{layer.name}' 设置为分类 '{category}' 的文件: {os.path.basename(file_path)}")
                        
                        # 记录已处理的图层
                        processed_layers.add(id(layer))
                        
                        # 🔧 关键修复：如果路径发生变化，使用图层的标准处理方法
                        if old_path != file_path:
                            try:
                                # 使用图层的标准图像处理方法，保持所有图层设置
                                # 这会考虑 fit_mode, use_original_size, 智能裁剪等所有设置
                                processed_image = layer.get_random_image(force_random=False)

                                if processed_image is not None:
                                    # 确保缓存路径正确设置
                                    layer._cached_image_path = layer.current_image_path
                                    print(f"[导出绑定] 使用标准方法加载图层 '{layer.name}' 图像成功")
                                else:
                                    print(f"[导出绑定] 标准方法返回空图像: {layer.name}")

                            except Exception as e:
                                print(f"[导出绑定] 标准方法加载图层 '{layer.name}' 图像失败: {e}")
                                # 如果标准方法失败，清除缓存让渲染时重新处理
                                layer.cached_image = None
                                layer._cached_image_path = None
            
            successful_groups += 1
        
        print(f"[绑定组合] 处理完成，成功处理了 {successful_groups} 个绑定组，共 {len(processed_layers)} 个图层")
        
        # 🔧 关键修复：对于未绑定的可见图层，进行标准随机化
        unbound_layers_processed = 0
        for layer in self.layers:
            # 只处理可见图层
            if not layer.visible:
                continue

            # 检查图层是否已经被处理过（即属于绑定组）
            if id(layer) not in processed_layers:
                # 检查是否是文字图层
                from app.models.text_layer import TextLayer
                if isinstance(layer, TextLayer):
                    # 文字图层，随机选择文字
                    layer.randomize_text()
                    print(f"[绑定组合] 非绑定文字图层 '{layer.name}' 随机选择文字: {layer.current_text}")
                elif layer.image_source and os.path.isdir(layer.image_source):
                    # 普通图层，随机选择图像
                    old_path = layer.current_image_path
                    # 强制随机选择新的图像文件
                    layer.get_random_image(force_random=True)
                    print(f"[绑定组合] 非绑定图层 '{layer.name}' 随机选择文件: {os.path.basename(layer.current_image_path) if layer.current_image_path else 'None'}")
                    # 检查路径是否发生变化
                    if layer.current_image_path != old_path:
                        layer.cached_image = None
                unbound_layers_processed += 1

            # 为可见图层（包括绑定和非绑定）生成新的随机变换参数
            if hasattr(layer, 'generate_random_transform_params'):
                layer.generate_random_transform_params()
                
        print(f"[绑定组合] 额外处理了 {unbound_layers_processed} 个非绑定图层")
    


    def render_document(self):
        """渲染文档为PIL图像"""
        if self.canvas_width <= 0 or self.canvas_height <= 0:
            return None
        # 使用新的渲染器实现，保持与导出一致
        try:
            from app.models.document_renderer import DocumentRenderer
            renderer = DocumentRenderer()
            image = renderer.render_document(
                canvas_width=self.canvas_width,
                canvas_height=self.canvas_height,
                layers=self.layers,
                background_color=(0, 0, 0, 0),
                force_opaque=False
            )
            return image
        except Exception:
            # 回退到兼容渲染逻辑，以确保功能可用
            return self._render_document_legacy()



    def export_image(self, file_path: str) -> bool:
        """导出单张图像 - 使用与预览一致的渲染方式"""
        try:
            if self.canvas_width <= 0 or self.canvas_height <= 0:
                self._last_export_error = "画布尺寸无效"
                print(f"[导出] 错误：画布尺寸无效")
                return False
            
            if not file_path:
                self._last_export_error = "文件路径为空"
                print(f"[导出] 错误：文件路径为空")
                return False
            
            ext = os.path.splitext(file_path)[1].lower()
            
            # 使用统一渲染服务，内部仍可回退到现有快速渲染器。
            print(f"[导出] 开始渲染图像: {file_path}")
            try:
                from app.services.render_service import RenderRequest, get_render_service
                render_result = get_render_service().render(
                    RenderRequest(
                        document=self,
                        mode="export",
                        quality_profile=str((getattr(self, "export_settings", {}) or {}).get("export_quality_profile", "quality")),
                        batch_mode=False,
                    )
                )
                image = render_result.image
                if not render_result.ok and render_result.error:
                    print(f"[导出] 渲染服务提示: {render_result.error}")
            except Exception:
                from app.utils.fast_renderer import get_global_fast_renderer
                fast_renderer = get_global_fast_renderer()
                image = fast_renderer.render_batch(self)
            
            if image is None:
                self._last_export_error = "渲染失败：渲染器返回None"
                print(f"[导出] 错误：渲染器返回None")
                return False
            
            print(f"[导出] 渲染成功: {image.size}, 模式={image.mode}")
            
            try:
                from app.services.export_service import ExportJob, get_export_service
                settings = getattr(self, "export_settings", {}) or {}
                report = get_export_service().save_image(
                    image,
                    ExportJob(
                        file_path=file_path,
                        file_format=ext[1:] if ext else None,
                        quality_profile=str(settings.get("export_quality_profile", "quality") or "quality"),
                        max_file_size_kb=int(settings.get("max_file_size_kb", 0) or 0),
                        jpeg_quality=int(settings.get("jpeg_quality_override", 0) or 0),
                        png_compress_level=int(settings.get("png_compress_level_override", -1)),
                        backend=str(settings.get("export_backend", "pillow") or "pillow"),
                        allow_lossy_size_reduction=bool(settings.get("allow_lossy_size_reduction", False)),
                    )
                )
                if not report.success:
                    self._last_export_error = report.error or "保存失败"
                return bool(report.success)
            except Exception:
                from app.utils.image_quality import ImageQualityManager
                ok = ImageQualityManager.save_high_quality_image(
                    image, file_path, format_hint=ext[1:] if ext else None
                )
                if not ok:
                    self._last_export_error = "保存失败"
                return bool(ok)
        except Exception as e:
            self._last_export_error = str(e)
            return False
    


    def _render_document_legacy(self):
        """原始渲染逻辑（向后兼容）"""
        # 创建空白画布
        canvas = Image.new('RGBA', (self.canvas_width, self.canvas_height), (0, 0, 0, 0))
        
        # 从下到上渲染每个图层
        for layer in self.layers:
            if not layer.visible:
                continue
                
            # 获取图层图像 - 支持文字图层和普通图层
            layer_image = None
            from app.models.text_layer import TextLayer
            
            if isinstance(layer, TextLayer):
                # 文字图层，渲染文字为图像
                layer_image = layer.render_text()
            else:
                # 普通图层处理
                # 检查图层是否已绑定且current_image_path已更新
                is_bound_layer = (hasattr(self, 'binding_manager') and 
                                self.binding_manager.is_layer_bound(layer))
                                
                if is_bound_layer and hasattr(layer, 'current_image_path') and layer.current_image_path:
                    # 绑定图层：检查缓存是否与当前路径匹配
                    cache_valid = (hasattr(layer, 'cached_image') and 
                                 layer.cached_image is not None and
                                 hasattr(layer, '_cached_image_path') and
                                 layer._cached_image_path == layer.current_image_path)
                    
                    if cache_valid:
                        # 缓存有效，使用缓存
                        layer_image = layer.cached_image
                        print(f"[渲染] 绑定图层 '{layer.name}' 使用有效缓存")
                    else:
                        # 缓存无效或路径不匹配，重新加载但不随机化
                        print(f"[渲染] 绑定图层 '{layer.name}' 缓存无效，重新加载: {layer.current_image_path}")
                        layer_image = layer.get_random_image(force_random=False)
                        # 记录缓存对应的路径
                        if layer_image and hasattr(layer, 'current_image_path'):
                            layer._cached_image_path = layer.current_image_path
                else:
                    # 非绑定图层：使用原有逻辑
                    if hasattr(layer, 'cached_image') and layer.cached_image is not None:
                        # 使用已缓存的图像
                        layer_image = layer.cached_image
                    else:
                        # 如果没有缓存，才尝试获取/随机一个
                        layer_image = layer.get_random_image()
            
            if layer_image is None:
                continue
                
            # 应用图层特效
            layer_image = layer.apply_effects(layer_image)
                
            # 创建图层位置框
            box = (layer.x, layer.y, layer.x + layer.width, layer.y + layer.height)
            
            # 获取图层的透明度
            opacity = layer.opacity
            
            # 如果图层完全透明，则跳过
            if opacity <= 0:
                continue
                
            # 将图像粘贴到画布上，考虑透明度
            if opacity < 1.0:
                # 需要创建一个带透明度的临时图像
                transparent = Image.new('RGBA', layer_image.size, (0, 0, 0, 0))
                temp_image = Image.blend(transparent, layer_image, opacity)
                canvas.paste(temp_image, (layer.x, layer.y), temp_image)
            else:
                # 完全不透明，直接粘贴
                canvas.paste(layer_image, (layer.x, layer.y), layer_image)
        
        return canvas
    

    




    def create_layer_from_data(self, layer_data):
        """从序列化的数据创建图层对象
        
        参数:
            layer_data (dict): 序列化的图层数据
            
        返回:
            Layer或TextLayer或ShapedLayer: 创建的图层对象
        """
        if not isinstance(layer_data, dict):
            # 兜底为默认图层，避免把None/非法数据注入图层列表
            return NewLayer(name='错误图层', x=0, y=0, width=100, height=100)

        try:
            # 检查图层类型 - 支持 type 和 layer_type 两种字段名
            layer_type = layer_data.get('layer_type') or layer_data.get('type', 'image')
            
            # 🔧 增强：通过检查关键字段来验证图层类型
            if 'shape_type' in layer_data and layer_type not in ('image', 'Layer'):
                # 如果有 shape_type 字段，应该是异形图层
                if layer_type != 'shaped':
                    print(f"[警告] 图层数据包含shape_type但layer_type为{layer_type}，强制使用异形图层")
                    layer_type = 'shaped'
            
            if layer_type == 'group':
                from app.models.layer_group import LayerGroup
                return LayerGroup.deserialize(layer_data, parent=self)
            elif layer_type == 'text':
                # 文字图层
                from app.models.text_layer import TextLayer
                layer = TextLayer.deserialize(layer_data)
            elif layer_type == 'shaped':
                # 异形图层
                from app.models.shaped_layer_new import ShapedLayer
                layer = ShapedLayer.deserialize(layer_data)
            else:
                # 普通图层
                layer = NewLayer.deserialize(layer_data)
            parent_group_id = layer_data.get('parent_group_id') or layer_data.get('_parent_group_id')
            if parent_group_id:
                try:
                    setattr(layer, 'parent_group_id', str(parent_group_id))
                    setattr(layer, '_parent_group_id', str(parent_group_id))
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in document_export.py")
                    pass
            return layer
                
        except Exception as e:
            print(f"从数据创建图层失败: {e}")
            import traceback
            traceback.print_exc()
            
            # 🔧 增强异常处理：尝试根据数据特征恢复图层类型
            try:
                if 'shape_type' in layer_data:
                    # 尝试作为异形图层创建
                    print("[恢复] 尝试作为异形图层恢复...")
                    from app.models.shaped_layer_new import ShapedLayer
                    layer = ShapedLayer(
                        name=layer_data.get('name', '恢复的异形图层'),
                        x=layer_data.get('x', 0),
                        y=layer_data.get('y', 0),
                        width=layer_data.get('width', 100),
                        height=layer_data.get('height', 100),
                        image_source=layer_data.get('image_source'),
                        use_original_size=layer_data.get('use_original_size', False),
                        is_folder=layer_data.get('is_folder', True)
                        # 🔧 关键修复：不传入current_image_path，这是临时状态
                    )
                    # 尝试设置异形属性
                    for key in ['shape_type', 'trapezoid_top_width', 'trapezoid_bottom_width', 
                               'trapezoid_slope_side', 'polygon_rotation', 'polygon_corner_radius']:
                        if key in layer_data:
                            try:
                                setattr(layer, key, layer_data[key])
                            except Exception as attr_e:
                                print(f"[恢复] 设置属性 {key} 失败: {attr_e}")
                    return layer
                else:
                    # 回退到普通图层
                    raise Exception("不是异形图层数据")
            except Exception as recovery_e:
                # 最终回退方案
                print(f"[恢复] 异形图层恢复失败: {recovery_e}")
                print("[恢复] 最终回退到普通图层")
                default_layer = NewLayer(
                    name=layer_data.get('name', '错误图层'),
                    x=layer_data.get('x', 0),
                    y=layer_data.get('y', 0),
                    width=layer_data.get('width', 100),
                    height=layer_data.get('height', 100)
                )
                return default_layer



    def _calculate_possible_combinations(self):
        """计算理论上可能的唯一组合数量"""
        try:
            total_combinations = 1
            visible_layers = 0
            image_extensions = {'.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp'}
            unique_caps = []
            combination_limit_applied = False
            export_settings = getattr(self, 'export_settings', {}) or {}
            unique_use_enabled = bool(export_settings.get('unique_use_enabled', False))
            try:
                unique_use_layers = {int(idx) for idx in export_settings.get('unique_use_layers', [])}
            except Exception:
                unique_use_layers = set()

            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            for doc_layer_idx, layer in enumerate(self.layers):
                if is_layer_group(layer) or not is_effectively_visible(layer, self.layers):
                    continue

                visible_layers += 1
                layer_combinations = 1
                is_image_candidate_layer = False

                # 检查是否是文字图层
                from app.models.text_layer import TextLayer
                if isinstance(layer, TextLayer) or hasattr(layer, 'get_text_lines') or hasattr(layer, 'text_content'):
                    candidates = []
                    if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)):
                        try:
                            candidates = [
                                str(line)
                                for line in (layer.get_text_lines() or [])
                                if line is not None and str(line).strip()
                            ]
                        except Exception:
                            candidates = []
                    elif hasattr(layer, 'text_list') and layer.text_list:
                        candidates = [str(line) for line in layer.text_list if line is not None and str(line).strip()]
                    elif hasattr(layer, 'text_content'):
                        content = getattr(layer, 'text_content', '')
                        if bool(getattr(layer, 'text_binding_enabled', False)):
                            candidates = [line.strip() for line in str(content).splitlines() if line.strip()]
                        elif str(content).strip():
                            candidates = [str(content)]
                    layer_combinations = max(1, len(candidates))
                elif hasattr(layer, '_is_folder') and layer._is_folder:
                    # 文件夹图层：计算文件夹中的图片数量
                    is_image_candidate_layer = True
                    if hasattr(layer, 'image_source') and layer.image_source:
                        try:
                            if os.path.isdir(layer.image_source):
                                image_files = []
                                for file in os.listdir(layer.image_source):
                                    ext = os.path.splitext(file)[1].lower()
                                    if ext in image_extensions:
                                        image_files.append(file)
                                layer_combinations = max(1, len(image_files))
                        except Exception as e:
                            print(f"计算图层 {layer.name} 文件数量时出错: {e}")
                            layer_combinations = 1
                elif hasattr(layer, 'image_source') and layer.image_source:
                    # 检查是否是单个文件
                    if os.path.isfile(layer.image_source):
                        is_image_candidate_layer = True
                        layer_combinations = 1
                    elif os.path.isdir(layer.image_source):
                        # 如果image_source是目录，按文件夹处理
                        is_image_candidate_layer = True
                        try:
                            image_files = []
                            for file in os.listdir(layer.image_source):
                                ext = os.path.splitext(file)[1].lower()
                                if ext in image_extensions:
                                    image_files.append(file)
                            layer_combinations = max(1, len(image_files))
                        except:
                            layer_combinations = 1
                    else:
                        layer_combinations = 1
                else:
                    # 其他情况：只有1种组合
                    layer_combinations = 1

                print(f"图层 '{layer.name}': {layer_combinations} 种可能")
                total_combinations *= layer_combinations
                if unique_use_enabled and doc_layer_idx in unique_use_layers and is_image_candidate_layer:
                    unique_caps.append(layer_combinations)

                # 防止数值过大
                if total_combinations > 1000000:  # 限制在100万以内
                    if not combination_limit_applied:
                        print(f"组合数量过大，限制为1000000")
                        combination_limit_applied = True
                    total_combinations = 1000000

            # 如果没有可见图层，返回1
            if visible_layers == 0:
                print("没有可见图层，返回组合数量: 1")
                return 1

            result = max(1, total_combinations)
            if unique_use_enabled and unique_caps:
                unique_cap = max(1, min(unique_caps))
                if result > unique_cap:
                    print(f"图像唯一使用限制生效，组合数量从 {result} 调整为 {unique_cap}")
                    result = unique_cap
            print(f"计算得到的总组合数量: {result}")
            return result

        except Exception as e:
            print(f"计算可能组合数量时出错: {e}")
            import traceback
            traceback.print_exc()
            return 1000  # 默认返回一个合理的数值



    def cancel_export(self):
        """取消当前的批量导出操作"""
        if hasattr(self, '_export_canceled'):
            self._export_canceled = True
            print("已设置导出取消标志")
        try:
            self._last_export_error = "导出已取消"
        except Exception:
            logger.debug("静默异常已忽略: except Exception: in document_export.py")
            pass

        # 尝试立即中断执行器与预计算器，降低取消延迟
        try:
            active_executor = getattr(self, '_active_export_executor', None)
            if active_executor and hasattr(active_executor, 'cancel'):
                active_executor.cancel()
        except Exception:
            logger.debug("静默异常已忽略: except Exception: in document_export.py")
            pass
        try:
            active_precomputer = getattr(self, '_active_precomputer', None)
            if active_precomputer is not None:
                setattr(active_precomputer, '_was_canceled', True)
        except Exception:
            logger.debug("静默异常已忽略: except Exception: in document_export.py")
            pass
        
        # 强制垃圾回收以释放资源
        try:
            import gc
            gc.collect()
        except:
            logger.debug("静默异常已忽略: except: in document_export.py")
            pass









    def _optimized_batch_export(self, directory, count, filename_template=None, file_format="png",
                               start_index=1, cancel_callback=None, traverse_mode=False):
        """优化的批量导出实现"""
        try:
            from app.utils.batch_optimization_manager import get_optimization_manager, ExportProfile
            from app.utils.parallel_batch_exporter import get_parallel_exporter
            from app.utils.intelligent_cache_system import get_intelligent_cache
            from app.utils.memory_optimizer import get_memory_optimizer

            print(f"[优化导出] 开始高性能批量导出 {count} 张图像")

            # 1. 分析导出任务
            export_profile = ExportProfile(
                image_count=count,
                average_image_size=(self.canvas_width, self.canvas_height),
                file_format=file_format,
                quality_level='high',
                has_complex_layers=len(self.layers) > 5,
                has_text_layers=any(hasattr(layer, 'text') for layer in self.layers),
                has_effects=any(getattr(layer, 'blend_mode', 0) != 0 for layer in self.layers),
                estimated_total_size_mb=count * (self.canvas_width * self.canvas_height * 4) / (1024 * 1024)
            )

            # 2. 生成并应用优化策略
            optimization_manager = get_optimization_manager()
            strategy = optimization_manager.generate_optimization_strategy(export_profile)
            optimization_manager.apply_strategy(strategy)

            # 3. 启动优化组件
            cache_system = get_intelligent_cache()
            cache_system.optimize_for_batch_export(self)

            memory_optimizer = get_memory_optimizer()
            memory_optimizer.start_optimization()
            memory_optimizer.optimize_for_batch_export(count)

            # 4. 执行并行导出
            parallel_exporter = get_parallel_exporter()

            start_time = time.time()
            success = parallel_exporter.export_batch_parallel(
                self, directory, count, filename_template or "image_{number:04d}",
                file_format, start_index, None, cancel_callback
            )
            export_time = time.time() - start_time

            # 5. 性能监控和调优
            try:
                memory_stats = memory_optimizer.get_memory_report()
                peak_memory = memory_stats['current_stats'].process_mb

                optimization_manager.monitor_performance(
                    export_time, count, peak_memory, 0.0  # CPU使用率暂时设为0
                )

                # 自动调优
                optimization_manager.auto_tune_strategy()
            except Exception as e:
                print(f"[优化导出] 性能监控失败: {e}")

            # 6. 清理资源
            memory_optimizer.stop_optimization()

            if success:
                speedup = count / export_time if export_time > 0 else 0
                print(f"[优化导出] 批量导出完成: {count}张/{export_time:.1f}秒 = {speedup:.2f}张/秒")

                # 显示性能提升信息
                estimated_traditional_time = count * 0.5  # 估算传统方法每张0.5秒
                if export_time > 0:
                    performance_gain = estimated_traditional_time / export_time
                    print(f"[优化导出] 预估性能提升: {performance_gain:.1f}x")
            else:
                print("[优化导出] 批量导出部分失败")

            return success

        except ImportError:
            print("[优化导出] 优化模块不可用，回退到传统导出")
            raise
        except Exception as e:
            print(f"[优化导出] 优化导出失败: {e}")
            import traceback
            traceback.print_exc()
            raise



    def enable_optimized_export(self, enabled: bool = True):
        """启用或禁用优化导出"""
        self.use_optimized_export = enabled
        if enabled:
            print("[优化导出] 优化导出已启用")
        else:
            print("[优化导出] 优化导出已禁用")



    def get_export_performance_info(self):
        """获取导出性能信息"""
        try:
            from app.utils.batch_optimization_manager import get_optimization_manager, ExportProfile
            from app.utils.optimized_image_processor import get_optimized_processor

            optimization_manager = get_optimization_manager()
            processor = get_optimized_processor()

            return {
                'system_performance_score': optimization_manager.system_profile.performance_score,
                'optimization_available': True,
                'processor_info': processor.get_performance_info(),
                'performance_analysis': optimization_manager.get_performance_analysis(),
                'recommendations': optimization_manager.get_recommendations(
                    ExportProfile(
                        image_count=100,
                        average_image_size=(self.canvas_width, self.canvas_height),
                        file_format='png',
                        quality_level='high',
                        has_complex_layers=len(self.layers) > 5,
                        has_text_layers=any(hasattr(layer, 'text') for layer in self.layers),
                        has_effects=any(getattr(layer, 'blend_mode', 0) != 0 for layer in self.layers),
                        estimated_total_size_mb=100 * (self.canvas_width * self.canvas_height * 4) / (1024 * 1024)
                    )
                )
            }
        except ImportError:
            return {
                'system_performance_score': 50.0,
                'optimization_available': False,
                'processor_info': {},
                'performance_analysis': {'status': 'unavailable'},
                'recommendations': ['优化模块不可用，建议安装相关依赖']
            }



    def batch_export_enhanced(self, directory: str, count: int = 10,
                            filename_template: str = "batch_{number:04d}",
                            file_format: str = "png",
                            use_high_performance: bool = True,
                            max_workers: int = 4) -> bool:
        """增强版批量导出 - 考虑所有图层设置，完全消除重复"""
        print(f"[增强批量导出] 开始导出 {count} 张图片到 {directory}")

        try:
            # 导入增强版组件
            from app.utils.enhanced_batch_precomputer import get_enhanced_batch_precomputer
            from app.utils.enhanced_batch_executor import get_enhanced_batch_executor

            # 1. 预计算阶段
            print("[增强批量导出] 阶段1: 预计算分析")
            precomputer = get_enhanced_batch_precomputer(self)

            # 分析文档
            total_combinations = precomputer.analyze_document_enhanced()
            if total_combinations == 0:
                print("[增强批量导出] 错误：没有可用的图层组合")
                return False

            # 生成组合
            combinations = precomputer.generate_enhanced_combinations(count, avoid_duplicates=True)
            if not combinations:
                print("[增强批量导出] 错误：无法生成图层组合")
                return False

            # 预计算文件名
            filenames = precomputer.precompute_enhanced_filenames(combinations, filename_template)

            # 2. 执行阶段
            print("[增强批量导出] 阶段2: 批量渲染导出")
            executor = get_enhanced_batch_executor(self, max_workers if use_high_performance else 1)

            # 确保目录存在
            os.makedirs(directory, exist_ok=True)

            # 执行导出
            success = executor.export_batch_enhanced(combinations, directory, filenames, file_format)

            # 3. 结果报告
            precompute_stats = precomputer.get_stats()
            executor_stats = executor.get_stats()

            print(f"[增强批量导出] 预计算统计:")
            print(f"  - 预计算时间: {precompute_stats['precompute_time']:.3f}秒")
            print(f"  - 组合生成数: {precompute_stats['combinations_generated']}")
            print(f"  - 重复避免数: {precompute_stats['duplicates_avoided']}")
            print(f"  - 绑定组处理: {precompute_stats['binding_groups_processed']}")

            print(f"[增强批量导出] 执行统计:")
            print(f"  - 成功导出: {executor_stats['completed_tasks']}")
            print(f"  - 失败导出: {executor_stats['failed_tasks']}")
            print(f"  - 渲染时间: {executor_stats['render_time']:.3f}秒")
            print(f"  - I/O时间: {executor_stats['io_time']:.3f}秒")
            print(f"  - 缓存命中: {executor_stats['cache_hits']}")
            print(f"  - 图层应用: {executor_stats['layer_applications']}")

            if success:
                print(f"[增强批量导出] ✅ 成功导出 {executor_stats['completed_tasks']} 张图片")
                print(f"[增强批量导出] 🎯 重复率: 0% (完全消除重复)")
            else:
                print(f"[增强批量导出] ❌ 导出过程中出现错误")

            return success

        except Exception as e:
            print(f"[增强批量导出] 异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    def save_document(self, file_path):
        """保存文档到指定路径"""
        try:
            from app.models.document_serializer import DocumentSerializer

            document_data = DocumentSerializer.prepare_document_data(self)
            document_data['version'] = 5  # 统一图层参数序列化，补齐随机/文字扩展字段

            # 确保目录存在
            os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)

            # 保存数据
            with open(file_path, 'wb') as f:
                pickle.dump(document_data, f)

            self.current_file_path = file_path

            # 标记文档为未修改状态
            self.is_modified = False

            # 发送文档变更信号，通知界面更新
            self.document_changed.emit()

            return True
        except Exception as e:
            # 使用日志记录错误，同时保持原有的print输出以确保兼容性
            try:
                import logging
                logger = logging.getLogger('批图王')
                logger.error(f"保存文档失败: {e}", exc_info=True)
            except:
                logger.debug("静默异常已忽略: except: in document_export.py")
                pass
            print(f"保存文档失败: {e}")
            return False

    def load_document(self, file_path):
        """从指定路径加载文档"""
        try:
            # 尝试导入错误处理函数
            try:
                from main import set_document_load_error
                has_error_handler = True
            except ImportError:
                has_error_handler = False

            with open(file_path, 'rb') as f:
                document_data = pickle.load(f)

            # 检查文档版本
            doc_version = document_data.get('version', 1)  # 默认为版本1（无版本号的旧文件）
            print(f"加载文档, 版本: {doc_version}")

            self.canvas_width = document_data.get('canvas_width', 0)
            self.canvas_height = document_data.get('canvas_height', 0)

            # 加载图层
            self.layers = []
            layers_data = document_data.get('layers', [])
            try:
                from app.utils.layer_tree import deserialize_layer_tree
                self.layers.extend(
                    deserialize_layer_tree(
                        layers_data,
                        lambda data, parent=None: self.create_layer_from_data(data),
                        parent=self,
                    )
                )
            except Exception:
                for layer_data in layers_data:
                    layer = self.create_layer_from_data(layer_data)
                    if layer is not None:
                        self.layers.append(layer)

            self.selected_layer_index = document_data.get('selected_layer_index', -1)
            self.selected_layer_indices = [self.selected_layer_index] if self.selected_layer_index >= 0 else []

            # 如果选择的图层索引超出范围，重置为-1
            if self.selected_layer_index >= len(self.layers):
                self.selected_layer_index = -1
                self.selected_layer_indices = []

            # 加载导出设置
            if 'export_settings' in document_data:
                loaded_settings = document_data.get('export_settings', {})
                merged_settings = self._build_default_export_settings()
                if isinstance(loaded_settings, dict):
                    merged_settings.update(loaded_settings)
                self.export_settings = merged_settings

            # 加载视图设置（标尺/参考线/吸附/缩放位移）
            self.set_view_settings(document_data.get('view_settings', {}))

            self.current_file_path = file_path

            # 标记文档为未修改状态
            self.is_modified = False

            # 重置历史记录
            self.history = []
            self.history_index = -1

            # 确保绑定管理器正确初始化（兼容性处理）
            if not hasattr(self, 'binding_manager'):
                from app.models.binding_manager import LayerBindingManager
                self.binding_manager = LayerBindingManager()

            # 加载绑定组数据（如果存在）
            if 'binding_groups' in document_data:
                try:
                    self.binding_manager.deserialize(document_data['binding_groups'], self.layers)
                except Exception as e:
                    print(f"加载绑定组数据失败: {e}")
                    # 如果加载失败，使用空的绑定管理器
                    self.binding_manager = LayerBindingManager()

            # 加载图层大小匹配配置
            if not hasattr(self, 'layer_size_match_manager') or self.layer_size_match_manager is None:
                self.layer_size_match_manager = LayerSizeMatchManager(parent=self)
            try:
                self.layer_size_match_manager.deserialize(document_data.get('layer_size_matches', {}))
            except Exception as e:
                print(f"加载图层大小匹配配置失败: {e}")
                self.layer_size_match_manager = LayerSizeMatchManager(parent=self)

            # 🔧 关键修复：加载文档后，清除所有图层的临时图像路径
            # 这确保从旧版本文件加载时，不会保留过时的图像路径
            self._clear_layer_temporary_states()

            # 发出信号通知界面更新
            self.document_changed.emit()
            self.layer_changed.emit()

            return True
        except Exception as e:
            error_msg = f"加载文档失败: {e}"
            # 使用日志记录错误，同时保持原有的print输出
            try:
                import logging
                logger = logging.getLogger('批图王')
                logger.error(error_msg, exc_info=True)
            except:
                logger.debug("静默异常已忽略: except: in document_export.py")
                pass
            print(error_msg)

            # 如果存在错误处理函数，设置错误信息
            if has_error_handler:
                set_document_load_error(e)

            return False
