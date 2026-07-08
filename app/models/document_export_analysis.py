"""``DocumentExportAnalysis`` mixin：文档状态预分析。

本 mixin 负责：

- ``_analyze_document_for_export``: 完整的文档状态预分析，返回给批量导出
  阶段使用的 dict（含 binding_enabled / layer_analysis / export_mode 等）。
- ``_get_binding_common_categories``: 取所有绑定组的公共分类（仅被
  ``_analyze_document_for_export`` 内部调用）。

所有方法仅依赖 ``self`` 的状态（``layers`` / ``binding_manager`` 等），
不直接修改图层，单独可测。
"""
from __future__ import annotations

import logging
from typing import List

logger = logging.getLogger(__name__)


class DocumentExportAnalysis:
    """Document 导出相关：状态预分析子 mixin。"""

    def _analyze_document_for_export(self) -> dict:
        """完整的文档状态预分析 - 为导出提供全面的状态信息"""
        from app.utils.print_utils import safe_print as _safe_print  # noqa: F401
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
        all_group_categories = set()
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
                # 注意：原文件此处引用了 is_text_layer_virtual_path 但未 import，
                # 属于预存 NameError 风险。这里补上正确的 import。
                from app.utils.text_layer_virtual_path import is_text_layer_virtual_path
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
                logger.debug("静默异常已忽略: except Exception: in document_export_analysis.py")
                pass

            if not group_categories:
                print(f"[绑定分析] ⚠️  绑定组 {group.name} 没有可用分类，可能文件结构不匹配")
                # 🔧 关键修复：输出详细的文件分类调试信息
                print(f"[绑定分析]     文件分类详情: {temp_group.file_categories}")
                continue

            group_categories_set = set(group_categories)
            all_group_categories.update(group_categories_set)

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

        # 🔧 关键修复：公共分类取交集，但如果交集为空，则回退到并集，
        # 避免多个绑定组分类不完全相同时批量导出直接进入标准模式导致绑定失效。
        # 批量导出预计算阶段会在每个绑定组内部按可用分类再匹配，确保预览和导出的行为一致。
        if not common_categories:
            common_categories = all_group_categories
            print(f"[绑定分析] ⚠️ 交集为空，回退到并集分类: {sorted(list(common_categories))}")

        result = sorted(list(common_categories))
        print(f"[绑定分析] ✅ 找到 {len(result)} 个可用分类: {result}")

        return result
