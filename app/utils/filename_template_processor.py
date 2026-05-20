"""
统一的文件名模板处理器
消除文件名模板处理相关的代码重复，提供标准化的模板处理接口
"""

import re
import os
import hashlib
from typing import Dict, Any, List, Optional, Union, Tuple


class FilenameTemplateProcessor:
    """统一的文件名模板处理器"""
    
    # 支持的占位符列表
    SUPPORTED_PLACEHOLDERS = {
        'number': '文件编号',
        'index': '索引编号（从0开始）',
        'count': '总数量',
        'layer': '主图层名称',
        'layers': '所有图层名称组合',
        'combo': '组合哈希值',
        'layer_name': '图层名称',
        'image_name': '图像名称',
        'binding_info': '绑定信息',
        'combination_hash': '组合哈希',
    }
    
    # 非法字符映射
    ILLEGAL_CHARS = {
        '<': '_', '>': '_', ':': '_', '"': '_', 
        '/': '_', '\\': '_', '|': '_', '?': '_', '*': '_',
        '，': '', ',': ''  # 移除逗号
    }
    
    @classmethod
    def process_template(cls, template: str, context: Dict[str, Any]) -> str:
        """
        处理文件名模板，替换所有占位符
        
        Args:
            template: 文件名模板
            context: 替换上下文，包含所有可用的替换值
            
        Returns:
            处理后的文件名
        """
        try:
            # 清理模板，保护占位符
            processed_template = cls._sanitize_template(template)
            
            # 处理带格式的 {placeholder:format} 占位符
            processed_template = cls._process_formatted_placeholders(processed_template, context)
            
            # 处理基本占位符
            processed_template = cls._process_basic_placeholders(processed_template, context)
            
            # 最终清理
            processed_template = cls._clean_filename(processed_template)
            
            return processed_template
            
        except Exception as e:
            # 如果处理失败，返回安全的默认文件名
            print(f"文件名模板处理失败: {e}")
            return cls._generate_fallback_filename(context)
    
    @classmethod
    def _sanitize_template(cls, template: str) -> str:
        """清理文件名模板，移除非法字符但保护占位符"""
        # 先保存所有占位符（包括带格式的）
        placeholder_pattern = r'\{[a-zA-Z_][a-zA-Z0-9_]*(?::[^}]+)?\}'
        placeholders = re.findall(placeholder_pattern, template)
        
        # 使用临时标记替换占位符
        temp_markers = {}
        for i, placeholder in enumerate(placeholders):
            marker = f"TEMPPLACEHOLDER{i}"
            template = template.replace(placeholder, marker)
            temp_markers[marker] = placeholder
        
        # 清理非法字符
        for illegal_char, replacement in cls.ILLEGAL_CHARS.items():
            template = template.replace(illegal_char, replacement)
        
        # 恢复占位符
        for marker, placeholder in temp_markers.items():
            template = template.replace(marker, placeholder)
        
        return template
    
    @classmethod
    def _process_formatted_placeholders(cls, template: str, context: Dict[str, Any]) -> str:
        """处理带格式的占位符，如 {number:04d}"""
        
        def replace_formatted_placeholder(match):
            full_match = match.group(0)
            placeholder_name = match.group(1)
            format_spec = match.group(2)

            if placeholder_name == 'layer' and str(format_spec).isdigit():
                return full_match
            
            try:
                # 获取值
                value = cls._get_context_value(placeholder_name, context)
                if value is None:
                    return str(context.get('number', 1))  # 默认回退
                
                # 应用格式
                if format_spec:
                    try:
                        # 处理数字格式
                        if isinstance(value, (int, float)):
                            return format(value, format_spec)
                        # 处理字符串格式
                        elif isinstance(value, str):
                            # 尝试转换为数字再格式化
                            try:
                                num_value = int(value)
                                return format(num_value, format_spec)
                            except ValueError:
                                return value
                        else:
                            return str(value)
                    except (ValueError, TypeError):
                        return str(value)
                else:
                    return str(value)
                    
            except Exception as e:
                print(f"处理格式化占位符 {full_match} 失败: {e}")
                return str(context.get('number', 1))
        
        # 匹配 {placeholder:format} 格式。{layer:0} 是索引型占位符，
        # 需要留给 _process_basic_placeholders 处理；{number:04d}/{number:d}
        # 是合法序号格式，不能因为以数字开头而跳过。
        formatted_pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*):([^}]+)\}'
        return re.sub(formatted_pattern, replace_formatted_placeholder, template)
    
    @classmethod
    def _process_basic_placeholders(cls, template: str, context: Dict[str, Any]) -> str:
        """处理基本占位符"""
        
        # 处理索引型占位符，如 {layer:0}, {layer:1}
        index_pattern = r'\{([a-zA-Z_]+):(\d+)\}'
        def replace_indexed_placeholder(match):
            placeholder_type = match.group(1)
            index = int(match.group(2))
            
            try:
                if placeholder_type == 'layer':
                    # 优先从layer_states中获取（这是最常见的情况）
                    layer_states = context.get('layer_states', {})
                    
                    if index in layer_states:
                        layer_info = layer_states[index]
                        result = cls._extract_layer_name(layer_info)
                        return result
                    
                    # 回退到layers列表
                    layers = context.get('layers', [])
                    if 0 <= index < len(layers):
                        layer_info = layers[index]
                        result = cls._extract_layer_name(layer_info)
                        return result
                    
                    # 如果都找不到，返回默认值
                    return f"layer{index}"
                
                # 其他索引型占位符可以在这里扩展
                return f"{placeholder_type}{index}"
                
            except Exception as e:
                print(f"处理索引占位符失败: {e}, placeholder: {placeholder_type}:{index}")
                return f"{placeholder_type}{index}"
        
        template = re.sub(index_pattern, replace_indexed_placeholder, template)
        
        # 处理基本占位符（按长度排序，避免短占位符替换长占位符的一部分）
        basic_replacements = {
            '{combination_hash}': lambda: str(context.get('combination_hash', '')),
            '{binding_info}': lambda: str(context.get('binding_info', '')),
            '{layer_name}': lambda: str(context.get('layer_name', 'layer')),
            '{image_name}': lambda: str(context.get('image_name', 'image')),
            '{layers}': lambda: cls._get_combined_layer_names(context),
            '{number}': lambda: str(context.get('number', 1)),
            '{index}': lambda: str(context.get('index', context.get('number', 1))),
            '{count}': lambda: str(context.get('count', 1)),
            '{layer}': lambda: cls._get_main_layer_name(context),
            '{combo}': lambda: cls._generate_combo_hash(context),
        }
        
        # 按占位符长度降序排序，确保长的占位符先被替换
        sorted_placeholders = sorted(basic_replacements.items(), 
                                    key=lambda x: len(x[0]), 
                                    reverse=True)
        
        for placeholder, value_func in sorted_placeholders:
            if placeholder in template:
                try:
                    value = value_func()
                    template = template.replace(placeholder, value)
                except Exception as e:
                    print(f"处理占位符 {placeholder} 失败: {e}")
                    template = template.replace(placeholder, 'unknown')
        
        return template
    
    @classmethod
    def _get_context_value(cls, key: str, context: Dict[str, Any]) -> Any:
        """从上下文中获取值"""
        # 直接键查找
        if key in context:
            return context[key]
        
        # 特殊处理
        if key == 'index' and 'number' in context:
            return context['number']
        
        # 默认值
        defaults = {
            'number': 1,
            'index': 1,
            'count': 1,
            'layer': 'layer',
            'layers': 'layers',
        }
        
        return defaults.get(key)
    
    @classmethod
    def _extract_layer_name(cls, layer_info: Union[Dict, Any, str]) -> str:
        """从图层信息中提取图层名称 - 修复版本，增强对实际文件名的获取"""
        try:
            # 如果是字符串（文件路径），直接处理
            if isinstance(layer_info, str):
                if layer_info:  # 确保不是空字符串
                    print(f"[文件名模板] 处理文件路径: {layer_info}")
                    basename = os.path.basename(layer_info)
                    name = os.path.splitext(basename)[0]
                    cleaned_name = cls._extract_main_filename(name)
                    print(f"[文件名模板] 提取的文件名: {cleaned_name}")
                    return cleaned_name
                else:
                    return 'layer'
            
            # 如果是字典，尝试从不同字段获取名称
            elif isinstance(layer_info, dict):
                # 🔧 关键修复：优先从 current_image_path 获取实际文件名
                if 'current_image_path' in layer_info and layer_info['current_image_path']:
                    path = layer_info['current_image_path']
                    print(f"[文件名模板] 从字典中获取路径: {path}")
                    basename = os.path.basename(path)
                    name = os.path.splitext(basename)[0]
                    cleaned_name = cls._extract_main_filename(name)
                    print(f"[文件名模板] 字典中提取的文件名: {cleaned_name}")
                    return cleaned_name
                # 如果没有路径，尝试使用图层名称
                elif 'name' in layer_info:
                    return str(layer_info['name'])
                elif 'layer_name' in layer_info:
                    return str(layer_info['layer_name'])
            
            # 如果是对象，尝试获取属性
            elif hasattr(layer_info, 'current_image_path'):
                # 🔧 关键修复：优先从实际的图像路径获取文件名
                if layer_info.current_image_path:
                    path = layer_info.current_image_path
                    print(f"[文件名模板] 从对象中获取路径: {path}")
                    basename = os.path.basename(path)
                    name = os.path.splitext(basename)[0]
                    cleaned_name = cls._extract_main_filename(name)
                    print(f"[文件名模板] 对象中提取的文件名: {cleaned_name}")
                    return cleaned_name
                # 如果没有路径，尝试使用图层名称
                elif hasattr(layer_info, 'name'):
                    return str(layer_info.name)
            elif hasattr(layer_info, 'name'):
                return str(layer_info.name)
            
            print(f"[文件名模板] 无法从 layer_info 中提取有效信息，使用默认名称")
            return 'layer'
            
        except Exception as e:
            print(f"[文件名模板] 提取图层名称失败: {e}, layer_info类型: {type(layer_info)}, 内容: {layer_info}")
            return 'layer'
    
    @classmethod
    def _get_main_layer_name(cls, context: Dict[str, Any]) -> str:
        """获取主图层名称 - 修复版本，增强对实际文件名的获取"""
        try:
            print(f"[文件名模板] 获取主图层名称，上下文: {list(context.keys())}")
            
            # 🔧 关键修复：优先从 layer_states 中获取（最常见的数据结构）
            layer_states = context.get('layer_states', {})
            if layer_states:
                print(f"[文件名模板] 找到 layer_states，包含 {len(layer_states)} 个图层")
                # 获取第一个图层的信息
                for layer_idx, layer_info in layer_states.items():
                    name = cls._extract_layer_name(layer_info)
                    if name and name != 'layer':
                        print(f"[文件名模板] 从 layer_states 获取主图层名称: {name}")
                        return name
            
            # 从图层列表中获取第一个有效图层
            layers = context.get('layers', [])
            if layers:
                print(f"[文件名模板] 找到 layers 列表，包含 {len(layers)} 个图层")
                for layer_info in layers:
                    name = cls._extract_layer_name(layer_info)
                    if name and name != 'layer':
                        print(f"[文件名模板] 从 layers 获取主图层名称: {name}")
                        return name
            
            # 从单个图层信息获取
            if 'layer_info' in context:
                print(f"[文件名模板] 找到 layer_info")
                name = cls._extract_layer_name(context['layer_info'])
                if name and name != 'layer':
                    print(f"[文件名模板] 从 layer_info 获取主图层名称: {name}")
                    return name
            
            # 🔧 关键修复：检查是否有直接指定的图层名称
            if 'layer_name' in context and context['layer_name']:
                print(f"[文件名模板] 找到直接指定的 layer_name: {context['layer_name']}")
                return str(context['layer_name'])
            
            print(f"[文件名模板] 未找到有效的图层名称，使用默认值")
            return 'layer'
            
        except Exception as e:
            print(f"[文件名模板] 获取主图层名称失败: {e}")
            return 'layer'
    
    @classmethod
    def _get_combined_layer_names(cls, context: Dict[str, Any]) -> str:
        """获取组合的图层名称 - 修复版本，增强对实际文件名的获取"""
        try:
            layer_names = []
            print(f"[文件名模板] 获取组合图层名称")
            
            # 🔧 关键修复：优先从 layer_states 获取（处理字符串路径）
            layer_states = context.get('layer_states', {})
            if layer_states:
                print(f"[文件名模板] 从 layer_states 处理 {len(layer_states)} 个图层")
                for layer_idx, layer_info in sorted(layer_states.items()):
                    name = cls._extract_layer_name(layer_info)
                    if name and name != 'layer' and name not in layer_names:
                        layer_names.append(name)
                        print(f"[文件名模板] 添加图层名称: {name}")
            
            # 从图层列表获取
            layers = context.get('layers', [])
            if layers and not layer_names:  # 只有在 layer_states 没有结果时才使用
                print(f"[文件名模板] 从 layers 处理 {len(layers)} 个图层")
                for layer_info in layers:
                    name = cls._extract_layer_name(layer_info)
                    if name and name != 'layer' and name not in layer_names:
                        layer_names.append(name)
                        print(f"[文件名模板] 添加图层名称: {name}")
            
            # 限制最多3个图层名，避免文件名过长
            if layer_names:
                combined_name = "-".join(layer_names[:3])
                cleaned_name = cls._clean_filename(combined_name)
                print(f"[文件名模板] 生成组合名称: {cleaned_name}")
                return cleaned_name
            else:
                print(f"[文件名模板] 未找到有效的图层名称，使用默认值")
                return "layers"
            
        except Exception as e:
            print(f"[文件名模板] 获取组合图层名称失败: {e}")
            return 'layers'
    
    @classmethod
    def _generate_combo_hash(cls, context: Dict[str, Any]) -> str:
        """生成组合哈希值"""
        try:
            # 收集用于生成哈希的信息
            hash_parts = []
            
            # 从图层状态获取
            layer_states = context.get('layer_states', {})
            for layer_idx, layer_info in layer_states.items():
                # 处理字符串路径（最常见的情况）
                if isinstance(layer_info, str):
                    basename = os.path.basename(layer_info)
                    hash_parts.append(f"{layer_idx}:{basename}")
                # 处理字典格式
                elif isinstance(layer_info, dict) and layer_info.get('current_image_path'):
                    path = layer_info['current_image_path']
                    basename = os.path.basename(path)
                    hash_parts.append(f"{layer_idx}:{basename}")
                # 处理对象格式
                elif hasattr(layer_info, 'current_image_path') and layer_info.current_image_path:
                    path = layer_info.current_image_path
                    basename = os.path.basename(path)
                    hash_parts.append(f"{layer_idx}:{basename}")
            
            # 如果没有图层信息，使用其他可用信息
            if not hash_parts:
                for key in ['number', 'index', 'layer_name']:
                    if key in context:
                        hash_parts.append(f"{key}:{context[key]}")
            
            # 生成哈希
            if hash_parts:
                combo_str = "_".join(hash_parts)
                return hashlib.md5(combo_str.encode('utf-8')).hexdigest()[:8]
            else:
                # 使用当前时间作为回退
                import time
                return hashlib.md5(str(time.time()).encode('utf-8')).hexdigest()[:8]
                
        except Exception as e:
            print(f"生成组合哈希失败: {e}")
            return "combo"
    
    @classmethod
    def _extract_main_filename(cls, filename: str) -> str:
        """提取主要文件名，去除序号等后缀"""
        try:
            # 移除常见的序号和复制标记模式
            patterns = [
                r'\s*\(副本\)\s*',    # 中文副本标记
                r'\s*\(copy\)\s*',    # 英文copy标记（括号内）
                r'\s+copy\s*',        # 空格+copy
                r'_copy\s*',          # 下划线+copy
                r'-copy\s*',          # 连字符+copy
                r'_\d+$',             # 结尾的 _数字
                r'-\d+$',             # 结尾的 -数字
                r'\(\d+\)$',          # 结尾的 (数字)
                r'_副本$',            # 结尾的 _副本
            ]
            
            result = filename
            for pattern in patterns:
                result = re.sub(pattern, '', result, flags=re.IGNORECASE)
            
            # 清理多余的空格和下划线
            result = re.sub(r'\s+', ' ', result).strip()
            result = re.sub(r'_+', '_', result).strip('_')
            
            # 如果结果为空，返回原文件名
            return result if result else filename
            
        except Exception:
            return filename
    
    @classmethod
    def _clean_filename(cls, filename: str) -> str:
        """清理文件名，移除非法字符"""
        try:
            # 应用非法字符替换
            result = filename
            for illegal_char, replacement in cls.ILLEGAL_CHARS.items():
                result = result.replace(illegal_char, replacement)
            
            # 移除连续的下划线
            result = re.sub(r'_+', '_', result)
            
            # 移除开头和结尾的下划线
            result = result.strip('_')
            
            # 确保不为空
            return result if result else 'file'
            
        except Exception:
            return 'file'
    
    @classmethod
    def _generate_fallback_filename(cls, context: Dict[str, Any]) -> str:
        """生成回退文件名"""
        try:
            number = context.get('number', 1)
            return f"batch_{number:04d}"
        except Exception:
            return "export_file"
    
    @classmethod
    def create_context(cls, **kwargs) -> Dict[str, Any]:
        """创建模板处理上下文"""
        return {
            'number': kwargs.get('number', 1),
            'index': kwargs.get('index', kwargs.get('number', 1)),
            'count': kwargs.get('count', 1),
            'layers': kwargs.get('layers', []),
            'layer_states': kwargs.get('layer_states', {}),
            'layer_info': kwargs.get('layer_info'),
            'layer_name': kwargs.get('layer_name', ''),
            'image_name': kwargs.get('image_name', ''),
            'binding_info': kwargs.get('binding_info', ''),
            'combination_hash': kwargs.get('combination_hash', ''),
            **kwargs  # 包含其他自定义参数
        }
    
    @classmethod
    def validate_template(cls, template: str) -> Tuple[bool, str]:
        """
        验证模板格式是否正确
        
        Returns:
            (是否有效, 错误信息)
        """
        try:
            # 检查基本格式
            if not template or not isinstance(template, str):
                return False, "模板不能为空"
            
            # 检查占位符格式
            placeholder_pattern = r'\{([a-zA-Z_][a-zA-Z0-9_]*(?::[^}]+)?)\}'
            placeholders = re.findall(placeholder_pattern, template)
            
            # 检查未关闭的占位符
            open_braces = template.count('{')
            close_braces = template.count('}')
            if open_braces != close_braces:
                return False, "占位符括号不匹配"
            
            # 检查是否包含至少一个有效占位符
            has_valid_placeholder = False
            for placeholder in placeholders:
                placeholder_name = placeholder.split(':')[0]
                if placeholder_name in cls.SUPPORTED_PLACEHOLDERS:
                    has_valid_placeholder = True
                    break
            
            if placeholders and not has_valid_placeholder:
                return False, f"没有找到有效的占位符。支持的占位符: {list(cls.SUPPORTED_PLACEHOLDERS.keys())}"
            
            return True, ""
            
        except Exception as e:
            return False, f"模板验证失败: {e}"
    
    @classmethod
    def get_placeholder_help(cls) -> str:
        """获取占位符帮助信息"""
        help_text = "支持的占位符:\n"
        for placeholder, description in cls.SUPPORTED_PLACEHOLDERS.items():
            help_text += f"  {{{placeholder}}} - {description}\n"
        
        help_text += "\n格式化示例:\n"
        help_text += "  {number:04d} - 四位数字，不足补零\n"
        help_text += "  {layer:0} - 第一个图层的名称\n"
        help_text += "  {layer:1} - 第二个图层的名称\n"
        
        return help_text
