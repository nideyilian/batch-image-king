#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BindingGroup 子 mixin 3: 可用分类 + 多样性 + 语义验证

从原 binding_group.py 拆分。涵盖：
- get_available_categories: 三种模式（混合/纯文字/纯图像）选择可用分类
- analyze_category_diversity: 多样性分析（依赖 _binding_manager.global_combination_manager）
- get_highest_diversity_categories: 多样性最高的分类列表
- select_random_category: 随机选一个可用分类
- _validate_category_semantic_consistency: 直接文案匹配验证
"""

import random
import os
import logging
from typing import Dict, List, Optional

from app.utils.print_utils import safe_print as _safe_print
from app.utils.text_layer_virtual_path import is_text_layer_virtual_path

logger = logging.getLogger(__name__)

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print


class BindingGroupCategorySelection:
    """可用分类 + 多样性 + 语义验证（拆分自 BindingGroup）。"""

    def get_available_categories(self) -> List[str]:
        """获取可用的文件分类列表 - 优化混合绑定组的分类选择"""
        if not self.file_categories:
            return []

        available_categories = []

        # 🔧 新增：分析绑定组的图层构成
        text_layers = [layer for layer in self.layers if self._is_text_layer(layer)]
        image_layers = [layer for layer in self.layers if not self._is_text_layer(layer)]

        print(f"[绑定组分类分析] 绑定组 '{self.name}' 构成: 文字图层{len(text_layers)}个, 图像图层{len(image_layers)}个")

        if text_layers and image_layers:
            # 🔧 优化混合模式：支持跨分类智能匹配
            print("[绑定组分类分析] 使用优化混合模式分类逻辑")

            # 分别收集图像分类和文字分类
            image_categories = set()
            text_categories = set()

            for category_name, layer_files in self.file_categories.items():
                has_image_layer = False
                has_text_layer = False

                for layer_idx, files in layer_files.items():
                    if layer_idx < len(self.layers) and len(files) > 0:
                        layer = self.layers[layer_idx]
                        if self._is_text_layer(layer):
                            has_text_layer = True
                        else:
                            has_image_layer = True

                if has_image_layer:
                    image_categories.add(category_name)
                if has_text_layer:
                    text_categories.add(category_name)

            print(f"[绑定组分类分析] 图像分类: {len(image_categories)}个, 文字分类: {len(text_categories)}个")

            # 🔧 策略1：优先使用图像分类（保证图像图层正常工作）
            for category_name in image_categories:
                # 检查该图像分类是否对所有图像图层都可用
                image_layers_covered = 0
                text_layers_covered = 0

                for layer_idx in range(len(self.layers)):
                    if layer_idx < len(self.layers):
                        layer = self.layers[layer_idx]
                        if not self._is_text_layer(layer):  # 图像图层
                            if (category_name in self.file_categories and
                                layer_idx in self.file_categories[category_name] and
                                len(self.file_categories[category_name][layer_idx]) > 0):
                                image_layers_covered += 1
                        else:  # 文字图层
                            if (category_name in self.file_categories and
                                layer_idx in self.file_categories[category_name] and
                                len(self.file_categories[category_name][layer_idx]) > 0):
                                text_layers_covered += 1

                # 如果该分类覆盖所有图像图层，且（如果有文字图层）也覆盖所有文字图层，则可用
                # 🔧 修复：严格检查文字图层匹配，防止非同类绑定
                if image_layers_covered == len(image_layers):
                    if not text_layers or text_layers_covered == len(text_layers):
                        available_categories.append(category_name)
                        print(f"[绑定组分类分析] 图像分类 '{category_name}' 可用: 覆盖{image_layers_covered}图像/{text_layers_covered}文字")
                    else:
                        print(f"[绑定组分类分析] 图像分类 '{category_name}' 排除: 文字图层不匹配 ({text_layers_covered}/{len(text_layers)})")

            # 🔧 策略2：如果图像分类太少，添加一些文字分类以增加多样性
            # 🔧 关键修复：但只添加有图像支撑的文字分类，避免纯文字分类污染
            if len(available_categories) < 2 and text_categories:
                # 选择有图像支撑的文字分类
                for category_name in text_categories:
                    if category_name not in available_categories:
                        # 检查这个文字分类是否有对应的图像文件支撑
                        has_image_support = False
                        if category_name in self.file_categories:
                            for layer_idx, files in self.file_categories[category_name].items():
                                if any(isinstance(f, str) and not is_text_layer_virtual_path(f) for f in files):
                                    has_image_support = True
                                    break

                        if has_image_support:
                            available_categories.append(category_name)
                            print(f"[绑定组分类分析] 添加有图像支撑的文字分类 '{category_name}' 增加多样性")
                            break  # 只添加一个有图像支撑的文字分类
                        else:
                            print(f"[绑定组分类分析] 跳过纯文字分类 '{category_name}' (无图像支撑)")

            # 🔧 策略3：如果还是没有可用分类，放宽条件
            if not available_categories and image_categories:
                # 选择覆盖率最高的图像分类
                best_category = None
                best_coverage = 0

                for category_name in image_categories:
                    coverage = 0
                    for layer_idx in range(len(self.layers)):
                        if layer_idx < len(self.layers):
                            layer = self.layers[layer_idx]
                            if not self._is_text_layer(layer):
                                if (category_name in self.file_categories and
                                    layer_idx in self.file_categories[category_name] and
                                    len(self.file_categories[category_name][layer_idx]) > 0):
                                    coverage += 1

                    coverage_ratio = coverage / len(image_layers) if image_layers else 0
                    if coverage_ratio > best_coverage:
                        best_coverage = coverage_ratio
                        best_category = category_name

                if best_category and best_coverage >= 0.5:  # 至少50%覆盖
                    # 🔧 修复：放宽条件时也必须检查文字图层兼容性
                    is_text_compatible = True
                    if text_layers:
                        text_covered = 0
                        for layer_idx in range(len(self.layers)):
                            layer = self.layers[layer_idx]
                            if self._is_text_layer(layer):
                                if (best_category in self.file_categories and
                                    layer_idx in self.file_categories[best_category]):
                                    text_covered += 1

                        if text_covered < len(text_layers):
                            is_text_compatible = False
                            print(f"[绑定组分类分析] 放宽条件失败: 最佳分类 '{best_category}' 与文字图层不兼容")

                    if is_text_compatible:
                        available_categories.append(best_category)
                        print(f"[绑定组分类分析] 放宽条件，选择最佳图像分类 '{best_category}': 覆盖率{best_coverage:.1%}")

        elif text_layers:
            # 🔧 纯文字图层模式：使用宽松匹配
            print("[绑定组分类分析] 使用纯文字图层模式")

            for category_name, layer_files in self.file_categories.items():
                # 只要有文字图层有这个分类即可
                text_layer_covered = False
                for layer_idx, files in layer_files.items():
                    if (layer_idx < len(self.layers) and
                        self._is_text_layer(self.layers[layer_idx]) and
                        len(files) > 0):
                        text_layer_covered = True
                        break

                if text_layer_covered:
                    available_categories.append(category_name)
                    print(f"[绑定组分类分析] 分类 '{category_name}' 符合纯文字模式条件")

        else:
            # 🔧 纯图像图层模式：使用严格匹配（原有逻辑）
            print("[绑定组分类分析] 使用纯图像图层模式")

            for core_name, layer_files in self.file_categories.items():
                # 检查是否所有图层都有这个分类的文件（严格匹配）
                if len(layer_files) >= len(self.layers):
                    # 确保每个图层都至少有一个文件
                    if all(len(files) > 0 for files in layer_files.values()):
                        available_categories.append(core_name)
                        print(f"[绑定组分类分析] 分类 '{core_name}' 符合纯图像模式条件")

        print(f"[绑定组分类分析] 最终可用分类: {available_categories}")
        return available_categories

    def analyze_category_diversity(self) -> Dict[str, Dict]:
        """分析每个分类的内部组合多样性"""
        diversity_info = {}
        available_categories = self.get_available_categories()

        for category in available_categories:
            if category not in self.file_categories:
                continue

            # 计算该分类的理论组合数
            layer_file_counts = []
            layer_indices = sorted(self.file_categories[category].keys())

            for layer_idx in layer_indices:
                file_count = len(self.file_categories[category][layer_idx])
                layer_file_counts.append(file_count)

            # 计算总组合数
            total_combinations = 1
            for count in layer_file_counts:
                total_combinations *= count

            # 获取该分类的使用历史
            used_count = 0
            if hasattr(self, '_binding_manager') and self._binding_manager:
                global_mgr = self._binding_manager.global_combination_manager
                if global_mgr and self.group_id in global_mgr.combination_history:
                    # 统计该分类的组合使用次数
                    for combo_hash, usage in global_mgr.combination_history[self.group_id].items():
                        # 需要判断这个组合是否属于当前分类
                        # 这里我们用启发式方法：假设分类内的组合相对平均分布
                        used_count += usage

            # 计算多样性指标
            diversity_score = max(0.0, 1.0 - (used_count / max(1, total_combinations)))

            diversity_info[category] = {
                'total_combinations': total_combinations,
                'layer_file_counts': layer_file_counts,
                'used_count': used_count,
                'diversity_score': diversity_score,  # 0-1，1表示完全未使用
                'avg_files_per_layer': sum(layer_file_counts) / len(layer_file_counts) if layer_file_counts else 0
            }

            print(f"[绑定组多样性] 分类'{category}': 总组合{total_combinations}, 已用{used_count}, 多样性{diversity_score:.3f}")

        return diversity_info

    def get_highest_diversity_categories(self, count: int = None) -> List[str]:
        """获取多样性最高的分类列表"""
        diversity_info = self.analyze_category_diversity()
        if not diversity_info:
            return self.get_available_categories()

        # 按多样性分数和总组合数排序
        sorted_categories = sorted(
            diversity_info.items(),
            key=lambda x: (x[1]['diversity_score'], x[1]['total_combinations']),
            reverse=True
        )

        categories = [cat for cat, info in sorted_categories]
        if count is not None:
            categories = categories[:count]

        print(f"[绑定组多样性] 推荐使用分类: {categories[:5]}")
        return categories

    def select_random_category(self) -> Optional[str]:
        """随机选择一个文件分类"""
        available = self.get_available_categories()
        if not available:
            return None

        selected = random.choice(available)
        self.last_selected_category = selected
        return selected

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

            # 🔧 简化验证1：提取所有文字内容作为虚拟文件名
            text_virtual_files = []
            for text_layer in text_layers_in_group:
                if hasattr(text_layer, 'get_text_lines') and callable(getattr(text_layer, 'get_text_lines', None)):
                    try:
                        text_lines = text_layer.get_text_lines()
                        for line in text_lines:
                            line_str = str(line).strip()
                            if line_str:
                                # 创建虚拟文件名格式：text_行内容
                                virtual_filename = f"text_{line_str}"
                                text_virtual_files.append(virtual_filename)
                                print(f"[直接匹配] 文字虚拟文件: '{virtual_filename}'")
                    except Exception:
                        logger.debug("静默异常已忽略: except Exception: in binding_group.py")
                        pass

                # 也检查current_text
                if hasattr(text_layer, 'current_text') and text_layer.current_text:
                    current_text = str(text_layer.current_text).strip()
                    if current_text:
                        virtual_filename = f"text_{current_text}"
                        if virtual_filename not in text_virtual_files:
                            text_virtual_files.append(virtual_filename)
                            print(f"[直接匹配] 当前文字虚拟文件: '{virtual_filename}'")

            # 🔧 简化验证2：提取图像文件名（不含路径）
            image_filenames = []
            if category in group.file_categories:
                for layer_idx, files in group.file_categories[category].items():
                    if layer_idx < len(group.layers) and not self._is_text_layer(group.layers[layer_idx]):
                        for file_path in files:
                            if isinstance(file_path, str) and not is_text_layer_virtual_path(file_path):
                                # 提取文件名（不含路径）
                                filename = os.path.basename(file_path)
                                # 移除文件扩展名
                                filename_no_ext = os.path.splitext(filename)[0]
                                image_filenames.append(filename_no_ext)
                                print(f"[直接匹配] 图像文件: '{filename_no_ext}'")

            # 🔧 简化验证3：直接对比文字虚拟文件和图像文件名
            direct_matches = []
            if text_virtual_files and image_filenames:
                for text_file in text_virtual_files:
                    text_content = text_file.replace('text_', '')
                    for image_file in image_filenames:
                        # 检查文字内容是否在图像文件名中，或者图像文件名在文字内容中
                        if (text_content in image_file or
                            image_file in text_content or
                            self._calculate_similarity(text_content, image_file) > 0.5):
                            direct_matches.append((text_content, image_file))
                            print(f"[直接匹配] ✅ 找到匹配: '{text_content}' <-> '{image_file}'")

            # 🔧 简化判断逻辑
            if text_layers_in_group and image_layers_in_group:
                # 混合绑定组：需要文字和图像有直接匹配
                if direct_matches:
                    print(f"[直接匹配] ✅ 混合绑定组：找到 {len(direct_matches)} 个直接匹配")
                    return True
                else:
                    print(f"[直接匹配] ❌ 混合绑定组：文字和图像无直接匹配")
                    return False
            elif text_layers_in_group:
                # 纯文字绑定组：只要有文字内容即可
                if text_virtual_files:
                    print(f"[直接匹配] ✅ 纯文字绑定组：有 {len(text_virtual_files)} 个文字内容")
                    return True
                else:
                    print(f"[直接匹配] ❌ 纯文字绑定组：无文字内容")
                    return False
            elif image_layers_in_group:
                # 纯图像绑定组：只要有图像文件即可
                if image_filenames:
                    print(f"[直接匹配] ✅ 纯图像绑定组：有 {len(image_filenames)} 个图像文件")
                    return True
                else:
                    print(f"[直接匹配] ❌ 纯图像绑定组：无图像文件")
                    return False
            else:
                # 空绑定组
                print(f"[直接匹配] ⚠️ 空绑定组，默认接受")
                return True

        except Exception as e:
            print(f"[直接匹配] ❌ 验证过程出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时默认接受，避免阻断正常流程
            return True
