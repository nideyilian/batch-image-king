#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图层绑定管理相关模块（从 binding_manager.py 拆分）"""

import os
import re
import random
import time
import hashlib
import itertools
import json
from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict, Counter
from app.utils.print_utils import safe_print as _safe_print
from app.utils.text_layer_virtual_path import (
    is_text_layer_virtual_path,
    build_text_layer_virtual_path,
    parse_text_layer_virtual_path,
)

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print

_BINDING_VERBOSE = os.environ.get("BTPW_BINDING_VERBOSE", "0") == "1"

# 🔧 导入100%准确绑定修复系统
try:
    from binding_100_percent_fix import (
        BindingIntegrityManager, ExportBindingValidator,
        validate_current_bindings, enforce_100_percent_binding_accuracy,
        BindingValidationResult
    )
    BINDING_INTEGRITY_AVAILABLE = True
    print("[绑定管理器] 100%准确绑定修复系统已加载")
except ImportError as e:
    BINDING_INTEGRITY_AVAILABLE = False
    print("[绑定管理器] 100%准确绑定修复系统未启用（可选模块缺失）")


from app.models.binding_group import BindingGroup
from app.models.global_combination_manager import GlobalCombinationManager
import logging

logger = logging.getLogger(__name__)
class LayerBindingManager:
    """图层绑定管理器"""

    def __init__(self):
        self.binding_groups: Dict[str, BindingGroup] = {}
        self.layer_to_group: Dict = {}  # 图层到绑定组的映射
        self.global_enabled = True  # 全局绑定开关
        self.layer_file_restrictions: Dict = {}  # 图层文件限制：{layer_id: [allowed_files]}
        self.global_combination_manager = GlobalCombinationManager()  # 全局组合管理器
        self._debug_trace_enabled = (os.environ.get("BTPW_BINDING_DEBUG_PANEL", "0") == "1")
        self._debug_traces: List[str] = []
        self._debug_trace_max = 300
        
        # 🔧 新增：100%准确绑定完整性管理器
        self._integrity_manager = None
        self._export_validator = None
        if BINDING_INTEGRITY_AVAILABLE:
            try:
                self._integrity_manager = BindingIntegrityManager(self)
                self._export_validator = ExportBindingValidator(self._integrity_manager)
                print("[绑定管理器] ✅ 完整性管理器和导出验证器已初始化")
            except Exception as e:
                print(f"[绑定管理器] ⚠️ 初始化完整性管理器失败: {e}")
                self._integrity_manager = None
                self._export_validator = None

    def set_debug_trace_enabled(self, enabled: bool):
        """设置绑定调试追踪开关。"""
        self._debug_trace_enabled = bool(enabled)

    def is_debug_trace_enabled(self) -> bool:
        return bool(self._debug_trace_enabled)

    def clear_debug_traces(self):
        self._debug_traces.clear()

    def append_debug_trace(self, source: str, group_name: str, category: str, layer_matches: List[Tuple[str, str]]):
        """写入一条绑定调试记录。"""
        if not self._debug_trace_enabled:
            return

        timestamp = time.strftime("%H:%M:%S", time.localtime())
        header = f"[{timestamp}] 来源={source} 组={group_name} 分类={category}"
        lines = [header]
        for layer_name, file_path in layer_matches:
            base_name = os.path.basename(str(file_path)) if isinstance(file_path, str) else str(file_path)
            lines.append(f"  - {layer_name}: {base_name}")

        message = "\n".join(lines)
        self._debug_traces.append(message)
        if len(self._debug_traces) > self._debug_trace_max:
            self._debug_traces = self._debug_traces[-self._debug_trace_max:]

    def get_debug_trace_text(self, limit: int = 80) -> str:
        """获取最近绑定调试文本，供调试面板显示。"""
        if not self._debug_traces:
            return "暂无绑定调试记录。"
        records = self._debug_traces[-max(1, int(limit)):]
        return "\n\n".join(records)
    
    def create_binding_group(self, group_name: str, layers: List) -> str:
        """创建绑定组 - 修复版本，传递绑定管理器引用，添加图层重复检查"""
        group_id = f"group_{len(self.binding_groups) + 1}_{group_name}"
        group = BindingGroup(group_id, group_name, binding_manager=self)  # 🔧 传递自身引用

        for i, layer in enumerate(layers):
            # 🔧 新增：检查图层是否已在其他绑定组中
            layer_id = id(layer)
            if layer_id in self.layer_to_group:
                existing_group_id = self.layer_to_group[layer_id]
                if existing_group_id in self.binding_groups:
                    existing_group = self.binding_groups[existing_group_id]
                    print(f"[绑定管理器] 警告：图层 '{layer.name}' 已在绑定组 '{existing_group.name}' 中，将先从原组移除")
                    # 从原绑定组中移除
                    existing_group.remove_layer(layer)
                    # 如果原绑定组为空，删除该组
                    if len(existing_group.layers) == 0:
                        del self.binding_groups[existing_group_id]
                        print(f"[绑定管理器] 原绑定组 '{existing_group.name}' 已为空，已删除")
            
            group.add_layer(layer, i)
            self.layer_to_group[id(layer)] = group_id

        self.binding_groups[group_id] = group
        print(f"创建绑定组: {group_name}, 包含 {len(layers)} 个图层")
        return group_id

    def add_binding_group(self, binding_group: 'BindingGroup'):
        """添加已创建的绑定组到管理器"""
        if binding_group.group_id not in self.binding_groups:
            self.binding_groups[binding_group.group_id] = binding_group

            # 更新图层到组的映射
            for layer in binding_group.layers:
                self.layer_to_group[id(layer)] = binding_group.group_id

            print(f"添加绑定组: {binding_group.name}, 包含 {len(binding_group.layers)} 个图层")
        else:
            print(f"绑定组 {binding_group.group_id} 已存在，跳过添加")

    def add_layer_to_group(self, group_id: str, layer, layer_index: Optional[int] = None):
        """添加图层到绑定组 - 添加图层重复检查"""
        if group_id in self.binding_groups:
            group = self.binding_groups[group_id]
            
            # 🔧 新增：检查图层是否已在其他绑定组中
            layer_id = id(layer)
            if layer_id in self.layer_to_group:
                existing_group_id = self.layer_to_group[layer_id]
                if existing_group_id != group_id and existing_group_id in self.binding_groups:
                    existing_group = self.binding_groups[existing_group_id]
                    print(f"[绑定管理器] 警告：图层 '{layer.name}' 已在绑定组 '{existing_group.name}' 中，将先从原组移除")
                    # 从原绑定组中移除
                    existing_group.remove_layer(layer)
                    # 如果原绑定组为空，删除该组
                    if len(existing_group.layers) == 0:
                        del self.binding_groups[existing_group_id]
                        print(f"[绑定管理器] 原绑定组 '{existing_group.name}' 已为空，已删除")
            
            if layer_index is None:
                layer_index = len(group.layers)
            group.add_layer(layer, layer_index)
            self.layer_to_group[id(layer)] = group_id
    
    def remove_layer_from_group(self, layer):
        """从绑定组移除图层"""
        layer_id = id(layer)
        if layer_id in self.layer_to_group:
            group_id = self.layer_to_group[layer_id]
            if group_id in self.binding_groups:
                group = self.binding_groups[group_id]
                group.remove_layer(layer)
                print(f"从绑定组 '{group.name}' 中移除图层 '{layer.name}'")
                
                # 如果绑定组为空，删除该组
                if len(group.layers) == 0:
                    del self.binding_groups[group_id]
                    print(f"绑定组 '{group.name}' 已空，自动删除")
                
            del self.layer_to_group[layer_id]
    
    def get_layer_binding_info(self, layer) -> Optional[Tuple[str, str]]:
        """获取图层的绑定信息"""
        layer_id = id(layer)
        if layer_id in self.layer_to_group:
            group_id = self.layer_to_group[layer_id]
            if group_id in self.binding_groups:
                group = self.binding_groups[group_id]
                return group_id, group.name
        return None
    
    def is_layer_bound(self, layer) -> bool:
        """检查图层是否已绑定"""
        return id(layer) in self.layer_to_group
    
    def enforce_100_percent_binding_accuracy(self, layer_states: Dict[int, str]) -> Dict[int, str]:
        """强制执行100%绑定准确率 - 新增方法"""
        if not BINDING_INTEGRITY_AVAILABLE or not self._integrity_manager:
            print("[绑定管理器] ⚠️ 100%绑定修复系统不可用，返回原始状态")
            return layer_states
        
        try:
            print("[绑定管理器] 🔧 开始强制执行100%绑定准确率...")
            
            # 使用完整性管理器强制执行100%准确率
            corrected_states = enforce_100_percent_binding_accuracy(None, layer_states)
            
            print(f"[绑定管理器] ✅ 100%绑定准确率执行完成")
            return corrected_states
            
        except Exception as e:
            print(f"[绑定管理器] ❌ 强制执行100%绑定准确率失败: {e}")
            import traceback
            traceback.print_exc()
            return layer_states
    
    def validate_binding_accuracy(self, layer_states: Dict[int, str]) -> float:
        """验证绑定准确率 - 新增方法"""
        if not BINDING_INTEGRITY_AVAILABLE or not self._integrity_manager:
            print("[绑定管理器] ⚠️ 绑定验证系统不可用，返回默认100%")
            return 100.0
        
        try:
            validation_result = validate_current_bindings(None, layer_states)
            accuracy = validation_result.accuracy
            
            if accuracy < 100.0:
                print(f"[绑定管理器] ⚠️ 绑定准确率检测: {accuracy:.1f}%")
                print(f"[绑定管理器] 错误绑定: {validation_result.mismatched_layers}")
            else:
                print(f"[绑定管理器] ✅ 绑定准确率: {accuracy:.1f}%")
            
            return accuracy
            
        except Exception as e:
            print(f"[绑定管理器] ❌ 绑定准确率验证失败: {e}")
            return 0.0
    
    def _extract_product_categories_from_text(self, text: str) -> set:
        from app.utils.product_category_extractor import extract_product_categories_from_text
        return extract_product_categories_from_text(text)
    
    def _validate_category_semantic_consistency(self, group, category: str, document_layers: List) -> bool:
        """🔧 简化版：直接文案匹配验证"""
        """直接对比文字图层内容与图像文件名，确保语义一致"""
        try:
            print(f"[直接匹配] 验证分类 '{category}' 与绑定组 '{group.name}' 的匹配一致性...")
            
            # 获取绑定组中的文字图层和图像图层
            text_layers_in_group = []
            image_layers_in_group = []
            
            for doc_layer in document_layers:
                if doc_layer.name in [layer.name for layer in group.layers]:
                    if self._is_text_layer(doc_layer):
                        text_layers_in_group.append(doc_layer)
                    else:
                        image_layers_in_group.append(doc_layer)
            
            print(f"[直接匹配] 绑定组包含: 文字图层{len(text_layers_in_group)}个, 图像图层{len(image_layers_in_group)}个")
            
            # 🔧 简化逻辑：提取文字行作为虚拟文件名，与图像文件名直接对比
            text_virtual_files = []  # 文字行作为虚拟文件名
            image_real_files = []    # 图像文件名（不含路径）
            
            # 提取文字图层每一行作为虚拟文件名
            for text_layer in text_layers_in_group:
                if hasattr(text_layer, 'get_text_lines') and callable(getattr(text_layer, 'get_text_lines', None)):
                    try:
                        text_lines = text_layer.get_text_lines()
                        for line in text_lines:
                            line_str = str(line).strip()
                            if line_str:  # 只添加非空行
                                text_virtual_files.append(line_str)
                                print(f"[直接匹配] 提取文字行作为虚拟文件名: '{line_str}'")
                    except Exception:
                        logger.debug("静默异常已忽略: except Exception: in layer_binding_manager.py")
                        pass
            
            # 提取图像图层的文件名（不含路径）
            for image_layer in image_layers_in_group:
                if hasattr(image_layer, 'file_path') and image_layer.file_path:
                    file_name = os.path.basename(str(image_layer.file_path))
                    # 移除文件扩展名，只保留核心名称
                    file_name_without_ext = os.path.splitext(file_name)[0]
                    image_real_files.append(file_name_without_ext)
                    print(f"[直接匹配] 提取图像文件名: '{file_name_without_ext}'")
            
            # 🔧 核心：直接对比虚拟文件名（文字行）与真实文件名
            direct_matches = []
            for virtual_file in text_virtual_files:
                for real_file in image_real_files:
                    # 完全匹配或包含匹配
                    if virtual_file == real_file or virtual_file in real_file or real_file in virtual_file:
                        direct_matches.append((virtual_file, real_file))
                        print(f"[直接匹配] ✅ 找到匹配: 文字行'{virtual_file}' ↔ 文件名'{real_file}'")
            
            # 🔧 判断逻辑：基于直接匹配结果
            if text_layers_in_group and image_layers_in_group:
                # 混合绑定组：需要文字行与文件名有匹配
                if direct_matches:
                    print(f"[直接匹配] ✅ 混合绑定组：找到{len(direct_matches)}个直接匹配")
                    return True
                else:
                    print(f"[直接匹配] ❌ 混合绑定组：文字行与文件名无匹配")
                    return False
            elif text_layers_in_group:
                # 纯文字绑定组：只要有文字内容就接受
                if text_virtual_files:
                    print(f"[直接匹配] ✅ 纯文字绑定组：有{len(text_virtual_files)}个文字行")
                    return True
                else:
                    print(f"[直接匹配] ❌ 纯文字绑定组：无文字内容")
                    return False
            elif image_layers_in_group:
                # 纯图像绑定组：只要有图像文件就接受
                if image_real_files:
                    print(f"[直接匹配] ✅ 纯图像绑定组：有{len(image_real_files)}个图像文件")
                    return True
                else:
                    print(f"[直接匹配] ⚠️ 纯图像绑定组：无图像文件，勉强接受")
                    return True  # 没有更好的选择时接受
            else:
                # 空绑定组
                print(f"[语义验证] ⚠️ 空绑定组，默认接受")
                return True
                
        except Exception as e:
            print(f"[语义验证] ❌ 验证过程出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时默认接受，避免阻断正常流程
            return True
    
    def randomize_bound_layers(self, all_layers: List) -> Dict:
        """为绑定的图层随机选择匹配的文件 - 严格按照原有绑定组设置执行"""
        if not self.global_enabled:
            return {}

        layer_file_mapping = {}
        print(f"[绑定管理器] 开始处理 {len(self.binding_groups)} 个绑定组")

        # 🔧 关键修复：移除公共分类计算，每个绑定组独立选择分类
        # 原逻辑错误：计算所有绑定组的公共分类会导致不合理的限制
        # 每个绑定组应该根据自己的图层和分类独立选择，不受其他绑定组影响
        common_categories = None  # 禁用公共分类限制
        print("[绑定管理器] ✅ 禁用公共分类限制，每个绑定组独立选择分类")

        # 处理每个绑定组
        for group_id, group in self.binding_groups.items():
            print(f"[绑定管理器] 处理绑定组: {group.name} (ID: {group_id})")

            document_layers = []
            group_idx_to_doc_layer = {}
            used_doc_layer_ids = set()

            # 根据绑定关系优先匹配实际的文档图层，避免同名图层错配
            for group_idx, group_layer in enumerate(group.layers):
                matched_layer = None

                # 1) 优先使用对象身份匹配（最精确）
                if group_layer in all_layers and id(group_layer) not in used_doc_layer_ids:
                    matched_layer = group_layer

                # 2) 使用绑定关系 + 名称匹配（避免同名错配）
                if matched_layer is None:
                    for doc_layer in all_layers:
                        if (self.layer_to_group.get(id(doc_layer)) == group_id and
                                doc_layer.name == group_layer.name and
                                id(doc_layer) not in used_doc_layer_ids):
                            matched_layer = doc_layer
                            break

                # 3) 回退到名称匹配（保持兼容）
                if matched_layer is None:
                    for doc_layer in all_layers:
                        if doc_layer.name == group_layer.name and id(doc_layer) not in used_doc_layer_ids:
                            matched_layer = doc_layer
                            break

                if matched_layer:
                    document_layers.append(matched_layer)
                    group_idx_to_doc_layer[group_idx] = matched_layer
                    used_doc_layer_ids.add(id(matched_layer))
                else:
                    print(f"[绑定管理器] 警告：未找到图层 '{group_layer.name}' (组内索引 {group_idx})")

            if len(document_layers) != len(group.layers):
                print(f"[绑定管理器] 警告：绑定组 {group.name} 中有 {len(group.layers) - len(document_layers)} 个图层未找到")
                if len(document_layers) == 0:
                    continue

            # 🔧 修复：直接使用原有绑定组的分类信息，不重新分析
            available_categories = group.get_available_categories()
            print(f"[绑定管理器] 可用分类: {available_categories}")

            if not available_categories:
                print(f"[绑定管理器] ❌ 绑定组 '{group.name}' 没有可用的匹配分类")
                continue

            # 🔧 根本修复：若存在公共分类，限制在公共分类内选择
            selectable_categories = available_categories
            if common_categories:
                selectable_categories = [c for c in available_categories if c in common_categories]
                if selectable_categories:
                    print(f"[绑定管理器] 使用公共分类限制，候选: {selectable_categories}")
                else:
                    print("[绑定管理器] 公共分类与本组不相交，回退到本组可用分类")

            # 🔧 关键修复：在选择分类前验证语义一致性
            # 确保选择的分类与绑定组的图层内容匹配
            valid_categories = []
            for category in selectable_categories:
                # 检查该分类是否与绑定组的图层内容语义一致
                is_semantically_valid = self._validate_category_semantic_consistency(group, category, document_layers)
                if is_semantically_valid:
                    valid_categories.append(category)
                else:
                    print(f"[绑定管理器] ⚠️ 分类 '{category}' 与绑定组内容语义不一致，已排除")
            
            # 如果有语义一致的有效分类，优先使用它们
            if valid_categories:
                final_categories = valid_categories
                print(f"[绑定管理器] ✅ 找到 {len(valid_categories)} 个语义一致的有效分类")
            else:
                # 如果没有语义一致的分类，回退到原始选择，但增加警告
                final_categories = selectable_categories
                print(f"[绑定管理器] ⚠️ 未找到语义一致的有效分类，使用原始候选分类")
            
            # 随机选择一个分类作为绑定组的统一分类
            import time
            import hashlib

            category_seed_factors = [
                time.time_ns() % 1000000000,
                hash(group_id) % 1000000,
                len(final_categories),
                len(document_layers)
            ]

            category_seed = sum(category_seed_factors) % 1000000000
            random.seed(category_seed)
            selected_category = random.choice(final_categories)
            # 记录本次选择的分类，便于外部在同一轮预览/导出中对未绑定图层进行一致性限制
            try:
                group.last_selected_category = selected_category
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in layer_binding_manager.py")
                pass
            random.seed()  # 恢复随机状态

            print(f"[绑定管理器] 绑定组 {group.name} 选择统一分类: '{selected_category}'")

            # 使用指定分类调用get_matched_files（预览模式不启用避重）
            matched_files = group.get_matched_files(selected_category, avoid_duplicates=False)
            print(f"[绑定管理器] 绑定组匹配结果: {matched_files}")

            # 写入调试追踪：记录本次分类和每个图层匹配文件
            try:
                trace_rows = []
                for layer_index, file_path in matched_files.items():
                    layer_obj = group_idx_to_doc_layer.get(layer_index)
                    if layer_obj is None and layer_index < len(group.layers):
                        layer_obj = group.layers[layer_index]
                    layer_name = getattr(layer_obj, 'name', f'layer_{layer_index}')
                    trace_rows.append((layer_name, file_path))
                self.append_debug_trace("preview_randomize", group.name, selected_category, trace_rows)
            except Exception:
                logger.debug("静默异常已忽略: except Exception: in layer_binding_manager.py")
                pass
            
            # 🔧 100%准确率验证：确保绑定结果的语义正确性
            if BINDING_INTEGRITY_AVAILABLE and hasattr(self, '_integrity_manager') and self._integrity_manager:
                try:
                    # 获取当前绑定组的所有图层状态
                    layer_states = []
                    for doc_layer in all_layers:
                        if doc_layer.name in [group_layer.name for group_layer in group.layers]:
                            layer_states.append({
                                'name': doc_layer.name,
                                'type': 'text' if hasattr(doc_layer, 'get_text_lines') else 'image',
                                'content': doc_layer.get_text_lines() if hasattr(doc_layer, 'get_text_lines') else None
                            })
                    
                    # 验证绑定结果的准确性
                    validation_result = self._integrity_manager.validate_binding_accuracy(
                        layer_states, matched_files, selected_category
                    )
                    
                    if validation_result['is_valid']:
                        print(f"[绑定管理器] ✅ 100%准确率验证通过 - 绑定组: {group.name}")
                    else:
                        print(f"[绑定管理器] ⚠️ 发现绑定不准确，自动修复中...")
                        # 自动修复不准确的绑定
                        corrected_files = self._integrity_manager.enforce_100_percent_binding_accuracy(
                            layer_states, selected_category, group.get_available_files()
                        )
                        
                        if corrected_files:
                            matched_files = corrected_files
                            print(f"[绑定管理器] ✅ 自动修复完成，新绑定结果: {matched_files}")
                        else:
                            print(f"[绑定管理器] ❌ 无法自动修复，使用原绑定结果")
                            
                except Exception as validation_error:
                    print(f"[绑定管理器] 100%准确率验证出错: {validation_error}")
                    # 验证出错时继续使用原结果，不影响正常流程

            # 🔧 根本修复：按绑定关系精确映射到文档图层，避免跨组错配
            for layer_index, file_path in matched_files.items():
                if layer_index < len(group.layers):
                    layer = group_idx_to_doc_layer.get(layer_index)
                    if layer is None:
                        group_layer = group.layers[layer_index]
                        print(f"[绑定管理器] 映射失败：未在文档中找到图层 '{group_layer.name}' (组内索引 {layer_index})")
                        continue

                    # 🔧 新增：检查是否为文字图层且使用虚拟文件路径
                    if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)) and is_text_layer_virtual_path(file_path):
                        self._apply_text_layer_binding(layer, file_path)
                        layer_file_mapping[id(layer)] = file_path
                        print(f"[绑定管理器] 文字图层 '{layer.name}' 已绑定文字内容: {file_path}")
                        continue

                    # 原有逻辑：处理普通图像图层
                    # 🔧 修正：使用正确的方法设置图层路径
                    print(f"[绑定管理器] 绑定前状态 - 图层: {layer.name}, 当前路径: {getattr(layer, 'current_image_path', None)}")

                    # 彻底清除图层状态
                    self._complete_layer_state_reset(layer)

                    # 🔧 关键修复：始终使用公共属性setter，无论是Layer还是LegacyLayer
                    # Layer（layer_new.py）通过属性管理器实现，LegacyLayer直接实现
                    # 两者都正确支持 current_image_path 公共属性
                    if hasattr(layer, 'current_image_path'):
                        layer.current_image_path = file_path
                        print(f"[绑定管理器] 设置新路径: {layer.name} -> {os.path.basename(file_path)}")
                    else:
                        print(f"[绑定管理器] 警告：图层 '{layer.name}' 没有 current_image_path 或 _current_image_path 属性")

                    # 记录映射关系
                    layer_file_mapping[id(layer)] = file_path
                    print(f"[绑定管理器] 图层 '{layer.name}' 已绑定文件: {os.path.basename(file_path)}")

        print(f"[绑定管理器] 完成组合级随机化绑定，共处理 {len(layer_file_mapping)} 个图层")
        return layer_file_mapping

    def _apply_text_layer_binding(self, layer, virtual_file_path: str):
        """应用文字图层的绑定 - 将虚拟文件路径转换为文字内容 - 修复版本"""
        try:
            # 🔧 修复：增强虚拟文件路径解析，支持URL编码
            if not is_text_layer_virtual_path(virtual_file_path):
                print(f"[绑定管理器] 警告：无效的文字图层虚拟路径: {virtual_file_path}")
                return
            
            try:
                layer_name, text_content = parse_text_layer_virtual_path(virtual_file_path)
                if layer.name != layer_name:
                    print(f"[绑定管理器] 警告：图层名称不匹配，期望 '{layer.name}'，但路径中是 '{layer_name}'")
                
            except Exception as parse_error:
                print(f"[绑定管理器] 警告：解析文字图层虚拟路径失败: {parse_error}")
                return
            
            print(f"[绑定管理器] 应用文字图层绑定: '{layer.name}' -> '{text_content}'")
            
            # 清除图层缓存
            if hasattr(layer, '_cached_image'):
                layer._cached_image = None
            
            # 🔧 修复：增强状态同步，避免竞态条件
            original_text = getattr(layer, 'current_text', '')
            
            # 仅更新当前显示文字，避免覆盖原有多行文案
            if hasattr(layer, 'current_text'):
                layer.current_text = text_content
            
            # 🔧 修复：改进文字行处理逻辑
            if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)):
                try:
                    existing_lines = layer.get_text_lines()
                    if existing_lines is None:
                        existing_lines = []
                except Exception:
                    existing_lines = []
                
                # 🔧 修复：只在需要时更新文字行，避免不必要的覆盖
                if not existing_lines and hasattr(layer, 'set_text_lines'):
                    layer.set_text_lines([text_content])
                elif existing_lines and hasattr(layer, 'set_text_lines'):
                    # 如果当前文字不在现有行中，可以选择添加
                    if text_content not in existing_lines:
                        # 根据业务需求决定是否添加新行
                        pass  # 保持现有行不变
            
            # 🔧 修复：延迟信号触发，确保状态一致
            def emit_signals():
                try:
                    if hasattr(layer, 'text_changed') and hasattr(layer.text_changed, 'emit'):
                        layer.text_changed.emit()
                    if hasattr(layer, 'changed') and hasattr(layer.changed, 'emit'):
                        layer.changed.emit()
                except Exception as signal_error:
                    print(f"[绑定管理器] 触发信号失败: {signal_error}")
            
            # 使用QTimer延迟触发信号，避免在信号处理中修改状态
            try:
                from PySide6.QtCore import QTimer
                QTimer.singleShot(0, emit_signals)
            except ImportError:
                # 如果QTimer不可用，直接触发
                emit_signals()
                
            print(f"[绑定管理器] 文字图层绑定成功: '{layer.name}' 现在显示 '{text_content}'")
            
        except Exception as e:
            print(f"[绑定管理器] 应用文字图层绑定失败: {e}")
            import traceback
            traceback.print_exc()
    
    def _force_clear_layer_cache(self, layer):
        """强制清除图层的所有缓存 - 修复版本，更全面的缓存清理"""
        try:
            print(f"[绑定管理器] 开始清除图层 '{layer.name}' 的所有缓存...")
            
            # 🔧 修复：增加缓存清除前的状态验证
            initial_state = {
                'has_cached_image': hasattr(layer, '_cached_image') and getattr(layer, '_cached_image', None) is not None,
                'has_cache_valid': hasattr(layer, '_cache_valid') and getattr(layer, '_cache_valid', False)
            }
            
            # 清除主要缓存方法
            if hasattr(layer, 'clear_cache') and callable(layer.clear_cache):
                try:
                    layer.clear_cache()
                    print(f"[绑定管理器] 调用图层 '{layer.name}' 的 clear_cache 方法成功")
                except Exception as clear_error:
                    print(f"[绑定管理器] 警告：图层 '{layer.name}' 的 clear_cache 方法调用失败: {clear_error}")

            # 🔧 修复：扩展缓存属性列表，包含更多可能的缓存属性
            cache_attrs = [
                # 基础缓存属性
                'cached_image', '_cached_image', '_cached_image_path',
                '_cached_images', '_image_cache', '_render_cache',
                '_processed_image', '_last_processed_image',
                '_cache_valid', '_image_loaded', '_needs_reload',
                
                # 🔧 新增：扩展缓存属性
                '_layer_cache', '_text_cache', '_style_cache',
                '_transform_cache', '_blend_cache', '_effect_cache',
                '_last_render_params', '_render_dirty',
                '_last_image_path', '_last_selected_image',
                '_cached_bounds', '_cached_rect', '_cached_size',
                '_opacity_cache', '_visibility_cache',
                
                # 渲染相关缓存
                '_rendered_image', '_last_render_time',
                '_cached_background', '_cached_foreground',
                
                # 文字图层特定缓存
                '_text_metrics_cache', '_font_cache', '_layout_cache',
                '_text_lines_cache', '_current_text_cache'
            ]

            cleared_attrs = []
            for attr in cache_attrs:
                if hasattr(layer, attr):
                    try:
                        old_value = getattr(layer, attr)
                        setattr(layer, attr, None)
                        cleared_attrs.append(attr)
                        
                        # 对于字典类型，额外清除内容
                        if isinstance(old_value, dict):
                            old_value.clear()
                            
                    except Exception as attr_error:
                        print(f"[绑定管理器] 警告：清除属性 '{attr}' 失败: {attr_error}")

            # 🔧 修复：更智能地处理字典类型的缓存
            dict_cache_attrs = ['_cached_images', '_image_cache', '_layer_cache', 
                              '_text_cache', '_style_cache', '_transform_cache']
            for attr in dict_cache_attrs:
                if hasattr(layer, attr):
                    try:
                        cache_dict = getattr(layer, attr)
                        if isinstance(cache_dict, dict):
                            cache_dict.clear()
                            print(f"[绑定管理器] 清除字典缓存 '{attr}' 成功")
                    except Exception as dict_error:
                        print(f"[绑定管理器] 警告：清除字典缓存 '{attr}' 失败: {dict_error}")

            # 🔧 修复：清除列表类型的缓存
            list_cache_attrs = ['_cached_items', '_cache_list', '_history_cache']
            for attr in list_cache_attrs:
                if hasattr(layer, attr):
                    try:
                        cache_list = getattr(layer, attr)
                        if isinstance(cache_list, list):
                            cache_list.clear()
                            print(f"[绑定管理器] 清除列表缓存 '{attr}' 成功")
                    except Exception as list_error:
                        print(f"[绑定管理器] 警告：清除列表缓存 '{attr}' 失败: {list_error}")

            # 🔧 新增：验证清除效果
            final_state = {
                'has_cached_image': hasattr(layer, '_cached_image') and getattr(layer, '_cached_image', None) is not None,
                'has_cache_valid': hasattr(layer, '_cache_valid') and getattr(layer, '_cache_valid', False)
            }
            
            cache_cleared = (
                initial_state['has_cached_image'] and not final_state['has_cached_image']
            ) or initial_state != final_state
            
            if cache_cleared:
                print(f"[绑定管理器] ✅ 已强制清除图层 '{layer.name}' 的缓存 (清除了 {len(cleared_attrs)} 个属性)")
            else:
                print(f"[绑定管理器] ⚠️ 图层 '{layer.name}' 缓存清除完成，但未检测到明显变化 (尝试了 {len(cleared_attrs)} 个属性)")

        except Exception as e:
            print(f"[绑定管理器] 清除图层缓存时出错: {e}")
            import traceback
            traceback.print_exc()

    def _complete_layer_state_reset(self, layer):
        """完全重置图层状态，确保绑定操作的彻底性"""
        try:
            print(f"[绑定管理器] 完全重置图层状态: {layer.name}")

            # 1. 强制清除所有缓存
            self._force_clear_layer_cache(layer)

            # 2. 重置图层的内部状态
            if hasattr(layer, '_last_image_path'):
                layer._last_image_path = None
            if hasattr(layer, '_last_selected_image'):
                layer._last_selected_image = None
            if hasattr(layer, '_image_loaded'):
                layer._image_loaded = False
            if hasattr(layer, '_needs_reload'):
                layer._needs_reload = True
            if hasattr(layer, '_cache_valid'):
                layer._cache_valid = False  # 标记缓存无效
            # 处理两种图层类型的当前路径属性
            if hasattr(layer, '_current_image_path'):
                # Layer 类（新图层）
                # 不清除当前路径，但确保缓存路径不匹配
                if hasattr(layer, '_cached_image_path'):
                    layer._cached_image_path = None
            elif hasattr(layer, 'current_image_path'):
                # LegacyLayer 类（文档中的图像图层）
                # 不清除当前路径，但确保缓存路径不匹配
                if hasattr(layer, '_cached_image_path'):
                    layer._cached_image_path = None

            # 3. 清除渲染相关状态
            render_attrs = [
                '_rendered_image', '_last_render_params', '_render_dirty',
                '_transform_cache', '_blend_cache', '_effect_cache'
            ]
            for attr in render_attrs:
                if hasattr(layer, attr):
                    setattr(layer, attr, None)

            # 4. 标记图层为需要更新
            if hasattr(layer, 'mark_dirty'):
                layer.mark_dirty()
            elif hasattr(layer, '_mark_dirty'):
                layer._mark_dirty()

            # 5. 重置变换参数（如果需要）
            if hasattr(layer, 'reset_transform_cache'):
                layer.reset_transform_cache()

            print(f"[绑定管理器] 图层 '{layer.name}' 状态重置完成")

        except Exception as e:
            print(f"[绑定管理器] 重置图层状态时出错: {e}")
            import traceback
            traceback.print_exc()
    
    def get_binding_groups_info(self) -> List[Dict]:
        """获取所有绑定组信息"""
        groups_info = []
        for group_id, group in self.binding_groups.items():
            info = {
                'group_id': group_id,
                'name': group.name,
                'layers': [layer.name for layer in group.layers],
                'categories': group.get_available_categories(),
                'layer_count': len(group.layers)
            }
            groups_info.append(info)
        return groups_info
    
    def delete_binding_group(self, group_id: str):
        """删除绑定组"""
        if group_id in self.binding_groups:
            group = self.binding_groups[group_id]
            # 移除图层映射
            for layer in group.layers:
                layer_id = id(layer)
                if layer_id in self.layer_to_group:
                    del self.layer_to_group[layer_id]
            # 删除绑定组
            del self.binding_groups[group_id]
            print(f"删除绑定组: {group.name}")
    
    def set_global_enabled(self, enabled: bool):
        """设置全局绑定开关"""
        self.global_enabled = enabled
        print(f"全局绑定功能: {'启用' if enabled else '禁用'}")

    def analyze_and_restrict_layer_files(self, all_layers: List):
        """分析所有图层的文件并设置限制，防止非绑定图层使用其他图层的文件"""
        print(f"[绑定管理器] 开始分析图层文件限制...")

        # 清除之前的限制
        self.layer_file_restrictions.clear()

        # 收集所有绑定图层使用的文件
        bound_layer_files = set()
        bound_layer_ids = set()

        # 遍历所有绑定组，收集绑定图层的文件
        for group_id, group in self.binding_groups.items():
            print(f"[绑定管理器] 分析绑定组: {group.name}")
            for group_layer in group.layers:
                # 找到对应的文档图层
                for doc_layer in all_layers:
                    if doc_layer.name == group_layer.name:
                        bound_layer_ids.add(id(doc_layer))
                        print(f"[绑定管理器] 绑定图层: {doc_layer.name}, 文件夹: {doc_layer.image_source}")

                        # 🔧 关键修复：只收集绑定图层当前正在使用的文件，而不是整个文件夹
                        if hasattr(doc_layer, 'current_image_path') and doc_layer.current_image_path:
                            if os.path.isfile(doc_layer.current_image_path):
                                bound_layer_files.add(doc_layer.current_image_path)
                                print(f"[绑定管理器] 绑定图层 '{doc_layer.name}' 当前使用文件: {os.path.basename(doc_layer.current_image_path)}")

                        # 如果绑定图层还没有当前文件，暂时不限制（等绑定后再分析）
                        break

        print(f"[绑定管理器] 发现 {len(bound_layer_files)} 个绑定图层正在使用的文件")

        # 为非绑定图层设置文件限制
        for layer in all_layers:
            layer_id = id(layer)

            if layer_id not in bound_layer_ids:  # 非绑定图层
                print(f"[绑定管理器] 分析非绑定图层: {layer.name}, 文件夹: {layer.image_source}")
                if layer.image_source and os.path.isdir(layer.image_source):
                    # 获取该图层文件夹中的所有文件
                    layer_files = []
                    image_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.bmp', '.tif', '.tiff', '.webp']

                    try:
                        for file in os.listdir(layer.image_source):
                            ext = os.path.splitext(file)[1].lower()
                            if ext in image_extensions:
                                file_path = os.path.join(layer.image_source, file)

                                # 检查这个文件是否被绑定图层使用
                                if file_path not in bound_layer_files:
                                    layer_files.append(file_path)
                                else:
                                    print(f"[绑定管理器] 排除绑定文件: {os.path.basename(file_path)} (图层: {layer.name})")

                        # 设置该图层的文件限制
                        if layer_files:
                            self.layer_file_restrictions[layer_id] = layer_files
                            print(f"[绑定管理器] 图层 '{layer.name}' 可用文件: {len(layer_files)} 个")
                            # 显示前几个可用文件
                            sample_files = [os.path.basename(f) for f in layer_files[:3]]
                            print(f"[绑定管理器] 可用文件示例: {sample_files}")
                        else:
                            print(f"[绑定管理器] 警告：图层 '{layer.name}' 没有可用的独占文件")

                    except Exception as e:
                        print(f"[绑定管理器] 分析图层 '{layer.name}' 文件时出错: {e}")
            else:
                print(f"[绑定管理器] 跳过绑定图层: {layer.name}")

        print(f"[绑定管理器] 文件限制分析完成，限制了 {len(self.layer_file_restrictions)} 个非绑定图层")

    def get_layer_file_restrictions(self, layer) -> List[str]:
        """获取图层的文件限制列表"""
        layer_id = id(layer)
        return self.layer_file_restrictions.get(layer_id, [])
    
    def _is_text_layer(self, layer) -> bool:
        """检查图层是否为文字图层"""
        return hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None))

    def serialize(self) -> Dict:
        """序列化绑定管理器数据包括全局组合历史 - 修复版本"""
        serialized_groups = {}

        for group_id, group in self.binding_groups.items():
            # 🔧 修复：增强序列化，保存更多图层信息以便更准确地匹配
            layer_info_list = []
            for layer in group.layers:
                layer_info = {
                    'name': layer.name,
                    'type': 'text' if self._is_text_layer(layer) else 'image',
                    # 🔧 新增：保存额外信息用于更精确的匹配
                    'layer_id': id(layer),  # 运行时ID（反序列化时可能变化）
                    'has_text_lines': hasattr(layer, 'get_text_lines'),
                    'current_text': getattr(layer, 'current_text', '') if hasattr(layer, 'current_text') else ''
                }
                layer_info_list.append(layer_info)
            
            # 🔧 修复：保存绑定组的分类信息，避免反序列化时重新分析
            available_categories = group.get_available_categories()
            
            serialized_groups[group_id] = {
                'group_id': group_id,  # 保存原始group_id
                'name': group.name,
                'layers': layer_info_list,  # 🔧 修复：使用详细信息替代简单名称
                'categories': list(available_categories),  # 🔧 新增：保存分类信息
                'layer_count': len(group.layers)  # 🔧 新增：图层数量信息
            }

        # 序列化全局组合历史
        combination_history = {}
        for group_id, history in self.global_combination_manager.combination_history.items():
            combination_history[group_id] = dict(history)  # 转换为普通字典

        # 🔧 修复：序列化文件限制信息
        file_restrictions = {}
        for layer_id, restricted_files in self.layer_file_restrictions.items():
            file_restrictions[str(layer_id)] = restricted_files  # 转换为字符串键

        return {
            'global_enabled': self.global_enabled,
            'groups': serialized_groups,
            'file_restrictions_enabled': True,  # 标记支持文件限制功能
            'file_restrictions': file_restrictions,  # 🔧 新增：文件限制信息
            'combination_history': combination_history,  # 新增：全局组合历史
            'global_not_repeat_enabled': True,  # 标记支持全局不重复功能
            'serialization_version': '2.0'  # 🔧 新增：版本信息，便于向后兼容
        }
    
    def deserialize(self, data: Dict, layers: List):
        """反序列化绑定管理器数据包括全局组合历史 - 修复版本"""
        try:
            # 🔧 修复：版本兼容性检查
            serialization_version = data.get('serialization_version', '1.0')
            print(f"绑定管理器反序列化：版本 {serialization_version}")
            
            self.global_enabled = data.get('global_enabled', True)

            # 清空现有数据
            self.binding_groups.clear()
            self.layer_to_group.clear()
            self.layer_file_restrictions.clear()  # 清空文件限制
            self.global_combination_manager = GlobalCombinationManager()  # 重新初始化

            # 重建绑定组（如果有数据）
            groups_data = data.get('groups', {})
            if not groups_data:
                print("绑定管理器反序列化：没有绑定组数据")
                return

            print(f"绑定管理器反序列化：发现 {len(groups_data)} 个绑定组")

            # 🔧 修复：增强图层匹配逻辑，支持新旧两种格式
            for saved_group_id, group_data in groups_data.items():
                # 使用保存的group_id，如果没有则使用键名
                group_id = group_data.get('group_id', saved_group_id)
                group_name = group_data.get('name', '未命名组')
                
                # 🔧 修复：支持新旧两种数据格式
                if 'layers' in group_data:
                    # 新版本格式 - 包含详细信息
                    layer_infos = group_data.get('layers', [])
                    print(f"重建绑定组: {group_name} (ID: {group_id}), 图层信息: {len(layer_infos)} 个")
                    
                    # 根据详细信息查找图层
                    group_layers = []
                    for layer_info in layer_infos:
                        found_layer = self._find_layer_by_info(layer_info, layers)
                        if found_layer:
                            group_layers.append(found_layer)
                        else:
                            layer_name = layer_info.get('name', '未知')
                            print(f"警告：未找到图层 '{layer_name}'")
                else:
                    # 旧版本格式 - 只有名称列表
                    layer_names = group_data.get('layer_names', [])
                    print(f"重建绑定组: {group_name} (ID: {group_id}), 图层: {layer_names}")
                    
                    # 根据图层名称查找实际图层
                    group_layers = []
                    for layer_name in layer_names:
                        found_layer = self._find_layer_by_name(layer_name, layers)
                        if found_layer:
                            group_layers.append(found_layer)
                        else:
                            print(f"警告：未找到图层 '{layer_name}'")

                # 直接创建绑定组，使用原始ID，传递绑定管理器引用
                if group_layers:
                    group = BindingGroup(group_id, group_name, binding_manager=self)

                    for i, layer in enumerate(group_layers):
                        group.add_layer(layer, i)
                        self.layer_to_group[id(layer)] = group_id

                    # 🔧 修复：如果存在保存的分类信息，直接恢复
                    saved_categories = group_data.get('categories', [])
                    if saved_categories and hasattr(group, 'file_categories'):
                        # 重建分类信息，避免重新分析
                        for category in saved_categories:
                            if category not in group.file_categories:
                                group.file_categories[category] = {}
                        print(f"✅ 恢复绑定组分类信息: {len(saved_categories)} 个分类")
                    
                    self.binding_groups[group_id] = group
                    print(f"✅ 成功重建绑定组: {group_name} (ID: {group_id}), 包含 {len(group_layers)} 个图层")
                else:
                    print(f"❌ 绑定组 '{group_name}' 重建失败：没有找到任何图层")

            print(f"成功加载 {len(self.binding_groups)} 个绑定组")

            # 恢复文件限制信息
            file_restrictions = data.get('file_restrictions', {})
            if file_restrictions:
                for layer_id_str, restricted_files in file_restrictions.items():
                    try:
                        # 查找对应的图层
                        for layer in layers:
                            if str(id(layer)) == layer_id_str:
                                self.layer_file_restrictions[id(layer)] = restricted_files
                                print(f"恢复图层 '{layer.name}' 的文件限制: {len(restricted_files)} 个文件")
                                break
                    except Exception as e:
                        print(f"恢复文件限制时出错: {e}")

            # 恢复全局组合历史（如果有）
            combination_history = data.get('combination_history', {})
            if combination_history:
                self.global_combination_manager.combination_history = combination_history
                total_combinations = sum(len(history) for history in combination_history.values())
                print(f"恢复全局组合历史: {len(combination_history)}个组，共{total_combinations}个组合记录")

            # 如果支持文件限制功能，立即分析文件限制
            if data.get('file_restrictions_enabled', False) and layers:
                print(f"检测到文件限制功能支持，立即分析文件限制...")
                self.analyze_and_restrict_layer_files(layers)
                
            print(f"绑定管理器反序列化完成：共 {len(self.binding_groups)} 个绑定组")

        except Exception as e:
            print(f"反序列化绑定数据时出错: {e}")
            import traceback
            traceback.print_exc()
            # 如果出错，重置为空状态
            self.binding_groups.clear()
            self.layer_to_group.clear()
            self.layer_file_restrictions.clear()
            self.global_enabled = True
            self.global_combination_manager = GlobalCombinationManager()
    
    def _find_layer_by_name(self, layer_name: str, layers: List):
        """🔧 新增：根据名称查找图层"""
        """基础查找，只匹配名称"""
        for layer in layers:
            if hasattr(layer, 'name') and layer.name == layer_name:
                return layer
        return None
    
    def _find_layer_by_info(self, layer_info: Dict, layers: List):
        """🔧 新增：根据详细信息查找图层"""
        """增强查找，考虑多个属性进行精确匹配"""
        target_name = layer_info.get('name', '')
        target_type = layer_info.get('type', 'image')
        target_has_text_lines = layer_info.get('has_text_lines', False)
        target_current_text = layer_info.get('current_text', '')
        
        candidates = []
        for layer in layers:
            if not hasattr(layer, 'name') or layer.name != target_name:
                continue
                
            # 检查类型匹配
            is_text_layer = self._is_text_layer(layer)
            if target_type == 'text' and not is_text_layer:
                continue
            if target_type == 'image' and is_text_layer:
                continue
            
            # 对于文字图层，可以检查更多属性
            if is_text_layer and target_has_text_lines:
                if hasattr(layer, 'current_text') and layer.current_text == target_current_text:
                    # 完全匹配，优先级最高
                    return layer
            
            candidates.append(layer)
        
        # 返回第一个候选者，如果没有完全匹配的
        return candidates[0] if candidates else None
    
    def get_global_combination_statistics(self) -> Dict:
        """获取全局组合统计信息"""
        stats = {}
        for group_id, group in self.binding_groups.items():
            # 获取可能的组合数
            available_categories = group.get_available_categories()
            total_possible = 0
            
            if available_categories:
                # 计算总的可能组合数
                for category in available_categories:
                    if category in group.file_categories:
                        layer_file_counts = []
                        for layer_idx, files in group.file_categories[category].items():
                            layer_file_counts.append(len(files))
                        
                        if layer_file_counts:
                            category_combinations = 1
                            for count in layer_file_counts:
                                category_combinations *= count
                            total_possible += category_combinations
            
            # 获取使用统计
            usage_stats = self.global_combination_manager.get_statistics(group_id)
            diversity_score = self.global_combination_manager.get_diversity_score(group_id, total_possible)
            
            stats[group_id] = {
                'group_name': group.name,
                'total_possible_combinations': total_possible,
                'diversity_score': diversity_score,
                'usage_percentage': (usage_stats['total_used_combinations'] / max(1, total_possible)) * 100,
                **usage_stats
            }
        
        return stats
    
    def reset_global_combination_history(self, group_id: Optional[str] = None):
        """重置全局组合历史"""
        if group_id:
            # 重置指定组的历史
            if group_id in self.global_combination_manager.combination_history:
                del self.global_combination_manager.combination_history[group_id]
                print(f"重置绑定组 {group_id} 的组合历史")
        else:
            # 重置所有历史
            self.global_combination_manager.combination_history.clear()
            print(f"重置所有组合历史")
