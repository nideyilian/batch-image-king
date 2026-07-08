"""``DocumentExportFilename`` mixin：文件名模板处理 + 绑定组合应用 + 组合数估算。

本 mixin 负责：

- ``_sanitize_filename_template``: 清理文件名模板（保留占位符）。
- ``_clean_filename``: 清理生成的文件名（Unicode 规范化 + 非法字符）。
- ``_extract_main_filename``: 提取文件名主要部分（去序号）。
- ``_set_binding_category_combination``: 为绑定组设置指定分类的组合。
- ``_calculate_possible_combinations``: 估算可能的唯一组合数（被 UI 和测试直接调用）。

注意：原 ``_set_binding_category_combination`` 引用了
``is_text_layer_virtual_path`` / ``parse_text_layer_virtual_path`` 但未 import，
属于预存 NameError 风险。本 mixin 在文件顶部补上正确 import。
"""
from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)


class DocumentExportFilename:
    """Document 导出相关：文件名 + 绑定组合 + 组合数估算子 mixin。"""

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

    def _set_binding_category_combination(self, category: str):
        """为绑定组设置指定分类的组合 - 根本修复：确保所有绑定组使用统一分类"""
        # 预存 bug 修复：原文件引用了 is_text_layer_virtual_path / parse_text_layer_virtual_path
        # 但未 import。补上 module 顶部的 import 即可。
        from app.utils.text_layer_virtual_path import (
            is_text_layer_virtual_path,
            parse_text_layer_virtual_path,
        )

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
                                # 如果标准方法失败，清除缓存让渲染时重新加载
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
                        except Exception:
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
