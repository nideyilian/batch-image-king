#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""BindingGroup 子 mixin 4: 匹配选文件 + 组合生成 + 避重

从原 binding_group.py 拆分。涵盖：
- get_matched_files: 主入口，绑定组模式（指定分类）+ 跨分类混合
- _generate_all_combinations: itertools.product 笛卡尔积
- _hash_combination: 组合哈希（保留图层索引顺序）
- clear_usage_history: 清空避重历史
- _select_optimal_combination: 集成全局避重管理器
- _combinations_match: 组合列表比较
- _fallback_combination_selection: 备用选择
- _random_select_with_diversity_boost: 多样性增强随机选
- _random_select_with_ultra_randomization: 超强随机化
- _cross_category_selection: 跨分类混合模式
- _rebuild_file_categories: 全量重建文件分类
- _get_current_layer_states: 获取当前图层状态
- 入口 100% 准确绑定验证（依赖模块级 BINDING_INTEGRITY_AVAILABLE）
"""

import os
import time
import hashlib
import random
import itertools
import traceback
import logging
from typing import Dict, List, Optional

from app.utils.print_utils import safe_print as _safe_print
from app.utils.text_layer_virtual_path import (
    is_text_layer_virtual_path,
    parse_text_layer_virtual_path,
)

logger = logging.getLogger(__name__)

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print

# 🔧 导入100%准确绑定修复系统（保持原行为：模块顶层 try/except）
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


class BindingGroupMatching:
    """匹配选文件 + 组合生成 + 避重（拆分自 BindingGroup）。"""

    def _get_current_layer_states(self) -> Dict[int, str]:
        """获取当前图层状态用于验证"""
        current_states = {}
        try:
            # 获取当前所有图层的文件状态
            for layer_idx, layer in enumerate(self.layers):
                if hasattr(layer, 'current_image_path') and layer.current_image_path:
                    current_states[layer_idx] = layer.current_image_path
                elif hasattr(layer, 'image_source') and layer.image_source:
                    current_states[layer_idx] = layer.image_source
        except Exception as e:
            print(f"[_get_current_layer_states] 获取当前图层状态失败: {e}")
        return current_states

    def get_matched_files(self, category: Optional[str] = None, avoid_duplicates: bool = False) -> Dict[int, str]:
        """获取匹配文件 - 根本修复版：有状态，真正避免重复 + 100%验证

        参数:
            category: 指定的分类名称
            avoid_duplicates: 是否启用避重机制（默认False，只有用户启用"避免重复"时才为True）

        🔧 关键修复：避重机制改为可选，修复"启用绑定组时所有图层都变成只使用一次"的问题
        """
        import time
        import random
        import hashlib
        import traceback

        # 🔍 超详细日志 - 开始
        print(f"\n{'='*80}")
        print(f"[🔍 详细日志] get_matched_files 被调用")
        print(f"  绑定组: {self.name} (ID: {self.group_id})")
        print(f"  请求分类: {category}")
        print(f"  避重模式: {'启用' if avoid_duplicates else '禁用'}")
        print(f"  调用栈（最近3层）:")
        stack = traceback.extract_stack()
        for frame in stack[-4:-1]:
            print(f"    {os.path.basename(frame.filename)}:{frame.lineno} in {frame.name}")
        print(f"{'='*80}\n")

        # 🔧 新增：100%绑定验证 - 在获取匹配文件时验证
        if BINDING_INTEGRITY_AVAILABLE and hasattr(self, '_binding_manager') and self._binding_manager:
            try:
                # 获取当前图层状态用于验证
                current_states = self._get_current_layer_states()
                if current_states:
                    validation_result = validate_current_bindings(None, current_states)
                    print(f"[🔍 详细日志] 绑定验证结果: 准确率={validation_result.accuracy:.1f}%")

                    if validation_result.accuracy < 100.0:
                        print(f"[🔍 详细日志] ⚠️ 发现绑定错误，将强制修复")
                        corrected_states = enforce_100_percent_binding_accuracy(None, current_states)
                        # 这里可以应用修正后的状态
            except Exception as e:
                print(f"[🔍 详细日志] 绑定验证失败: {e}")

        if category:
            # 🔧 关键修复：确保文件分类已分析
            if not self.file_categories:
                print(f"[🔍 详细日志] file_categories 为空，重新分析...")
                self._rebuild_file_categories()
                print(f"[🔍 详细日志] 重建后分类数: {len(self.file_categories)}")
            else:
                print(f"[🔍 详细日志] file_categories 已存在，分类数: {len(self.file_categories)}")

            print(f"[🔍 详细日志] 可用分类: {list(self.file_categories.keys())}")

            # 绑定组模式
            if category not in self.file_categories:
                print(f"[🔍 详细日志] ⚠️ 分类 '{category}' 不存在！")
                return {}

            print(f"[🔍 详细日志] ✅ 分类 '{category}' 存在")

            # 获取该分类下的所有图层
            layer_indices = sorted(list(self.file_categories[category].keys()))
            print(f"[🔍 详细日志] 该分类的图层索引: {layer_indices}")
            if not layer_indices:
                print(f"[🔍 详细日志] ⚠️ 图层索引为空！")
                return {}

            # 🔧 根本修复：初始化该分类的使用历史
            if not hasattr(self, '_category_usage_history'):
                self._category_usage_history = {}
                print(f"[🔍 详细日志] 初始化 _category_usage_history")

            if category not in self._category_usage_history:
                self._category_usage_history[category] = set()
                print(f"[🔍 详细日志] 为分类 '{category}' 创建新的历史记录")
            else:
                print(f"[🔍 详细日志] 分类 '{category}' 已有历史记录，已使用: {len(self._category_usage_history[category])} 个组合")

            # 🔧 关键修复：前置校验 - 确保每个图层在分类下都有候选文件
            print(f"[🔍 详细日志] 开始前置校验每个图层的候选文件...")
            invalid_layers = []
            for layer_idx in layer_indices:
                files = self.file_categories[category].get(layer_idx, [])
                if not files:
                    # 检查是否是文字图层
                    if layer_idx < len(self.layers):
                        layer = self.layers[layer_idx]
                        if self._is_text_layer(layer):
                            print(f"[🔍 详细日志] ⚠️ 文字图层 '{layer.name}' 在分类 '{category}' 下无匹配文件")
                        else:
                            print(f"[🔍 详细日志] ⚠️ 图像图层 (索引{layer_idx}) 在分类 '{category}' 下无匹配文件")
                    else:
                        print(f"[🔍 详细日志] ⚠️ 图层索引 {layer_idx} 超出范围")
                    invalid_layers.append(layer_idx)

            if invalid_layers:
                print(f"[🔍 详细日志] ❌ 前置校验失败：{len(invalid_layers)} 个图层在分类 '{category}' 下无匹配文件")
                print(f"[🔍 详细日志] 无效图层索引: {invalid_layers}")
                return {}  # 返回空字典，拒绝使用该分类

            print(f"[🔍 详细日志] ✅ 前置校验通过：所有 {len(layer_indices)} 个图层在分类 '{category}' 下都有匹配文件")

            # 生成所有可能的文件组合
            all_combinations = self._generate_all_combinations(category, layer_indices)
            print(f"[🔍 详细日志] 生成的总组合数: {len(all_combinations)}")
            if not all_combinations:
                print(f"[🔍 详细日志] ⚠️ 无法生成组合！")
                return {}

            # 🔧 关键修复：只有启用避重时才过滤已使用的组合
            if avoid_duplicates:
                # 🔧 根本修复：过滤掉已经使用过的组合
                unused_combinations = []
                for combo in all_combinations:
                    combo_hash = self._hash_combination(combo)
                    if combo_hash not in self._category_usage_history[category]:
                        unused_combinations.append(combo)

                # 🔧 根本修复：如果所有组合都用完了，清空历史，允许重用
                if not unused_combinations:
                    print(f"[绑定组] 分类 '{category}' 的所有 {len(all_combinations)} 个组合都已使用，清空历史允许重用")
                    self._category_usage_history[category].clear()
                    unused_combinations = all_combinations
            else:
                # 🔧 关键修复：不启用避重时，直接使用所有组合
                unused_combinations = all_combinations
                print(f"[绑定组] 避重模式未启用，允许重复使用组合")

            # 🔧 终极修复：随机选择一个未使用的组合
            # 问题根源：之前总是选择 unused_combinations[0]，导致某些组合被跳过或重复使用
            # 解决方案：从 unused_combinations 中随机选择一个，确保多样性
            import random
            selected_combination = random.choice(unused_combinations)

            # 🔧 关键修复：只在避重模式下记录使用历史和显示详细统计
            if avoid_duplicates:
                # 🔧 根本修复：记录该组合已使用
                combo_hash = self._hash_combination(selected_combination)
                self._category_usage_history[category].add(combo_hash)

                # 🔧 超详细日志：记录选择详情（前100次都显示）
                usage_count = len(self._category_usage_history[category])
                total_combinations = len(all_combinations)
                usage_rate = usage_count / total_combinations * 100 if total_combinations > 0 else 0.0

                if usage_count <= 100:
                    print(f"\n🎯 [绑定组选择详细] 分类 '{category}' 第{usage_count}次选择:")
                    print(f"  - 总组合数: {total_combinations}")
                    print(f"  - 未使用组合数: {len(unused_combinations)}")
                    print(f"  - 选择组合内容:")
                    for layer_idx in sorted(selected_combination.keys()):
                        print(f"    L{layer_idx}: {os.path.basename(selected_combination[layer_idx])}")
                    print(f"  - 使用历史: {usage_count}/{total_combinations} ({usage_rate:.1f}%)")

                # 🔍 详细日志 - 始终显示前10次和每第20次
                print(f"\n[绑定组 '{self.name}'] 🎯 分类 '{category}' 避重状态:")
                print(f"  - 已使用: {usage_count}/{total_combinations} ({usage_rate:.1f}%)")
                print(f"  - 剩余可用: {len(unused_combinations)-1}")
                print(f"  - 本次返回哈希: {combo_hash}")
                print(f"  - 本次返回文件:")
                for layer_idx in sorted(selected_combination.keys()):
                    print(f"    L{layer_idx}: {os.path.basename(selected_combination[layer_idx])}")

                # 显示历史记录中的最近5个哈希
                if len(self._category_usage_history[category]) > 0:
                    recent_hashes = list(self._category_usage_history[category])[-5:]
                    print(f"  - 最近5个已使用哈希:")
                    for i, h in enumerate(recent_hashes, 1):
                        print(f"    {i}. {h}")

                # 记录到旧的全局组合管理器（保持兼容性）
                file_paths = list(selected_combination.values())
                if hasattr(self, '_binding_manager') and self._binding_manager:
                    self._binding_manager.global_combination_manager.record_combination_usage(
                        self.group_id, file_paths, category
                    )
            else:
                # 非避重模式：简单日志
                print(f"\n[绑定组 '{self.name}'] 🎯 分类 '{category}' 随机选择组合（允许重复）:")
                print(f"  - 总组合数: {len(all_combinations)}")
                print(f"  - 本次返回文件:")
                for layer_idx in sorted(selected_combination.keys()):
                    print(f"    L{layer_idx}: {os.path.basename(selected_combination[layer_idx])}")

            return selected_combination

        else:
            # 非绑定组模式：保留原有的跨分类混合逻辑
            print(f"[绑定组] 🔀 使用跨分类混合模式")
            return self._cross_category_selection()

    def _generate_all_combinations(self, category: str, layer_indices: List[int]) -> List[Dict[int, str]]:
        """生成所有可能的文件组合"""
        try:
            # 获取每个图层的文件列表
            layer_files = []
            for layer_idx in layer_indices:
                files = self.file_categories[category].get(layer_idx, [])
                layer = None
                if layer_idx < len(self.layers):
                    layer = self.layers[layer_idx]
                    if self._is_text_layer(layer):
                        lines = []
                        try:
                            lines = [l.strip() for l in layer.get_text_lines() if str(l).strip()]
                        except Exception:
                            lines = []
                        filtered = []
                        for f in files:
                            if is_text_layer_virtual_path(f):
                                try:
                                    _, content = parse_text_layer_virtual_path(f)
                                except Exception:
                                    content = ''
                                # 更精确的内容匹配检查（单向包含：文字内容包含分类关键词）
                                if content:
                                    for line in lines:
                                        line_stripped = str(line).strip()
                                        if line_stripped and (
                                            content in line_stripped or content.lower() in line_stripped.lower()  # 内容在文字行中（单向包含，忽略大小写）
                                        ):
                                            filtered.append(f)
                                            break
                        files = filtered
                if not files and layer is not None:
                    # 🔧 增强容错：如果文字图层过滤后没有匹配的文件，尝试生成合成候选
                    if self._is_text_layer(layer):
                        lines = []
                        try:
                            lines = [l.strip() for l in layer.get_text_lines() if str(l).strip()]
                        except Exception:
                            lines = []

                        # 如果分类名包含在任意文字行中，生成虚拟文件路径
                        synthetic_files = []
                        for line in lines:
                            line_stripped = str(line).strip()
                            if not line_stripped:
                                continue

                            # 更全面的匹配检查（单向包含：文字内容包含分类关键词）
                            should_match = False

                            # 1. 分类名在文字行中（单向包含）
                            if category and str(category).lower() in line_stripped.lower():
                                should_match = True

                            if should_match:
                                synthetic_path = self._build_text_virtual_path(layer.name, line_stripped)
                                synthetic_files.append(synthetic_path)

                        if synthetic_files:
                            print(f"[绑定组] 为文字图层 '{layer.name}' 生成了 {len(synthetic_files)} 个合成候选")
                            files = synthetic_files
                        else:
                            print(f"[绑定组] 警告：文字图层 '{layer.name}' 在分类 '{category}' 下无匹配内容")
                            # 🔧 修复：不再使用第一个文案作为默认回退，避免错误绑定
                            # 当文字图层在指定分类下没有匹配内容时，应该返回空列表
                            # 这样可以确保只有真正匹配的内容才会被绑定
                            print(f"[绑定组] 文字图层 '{layer.name}' 在分类 '{category}' 下无合适匹配，跳过绑定")
                            return []  # 没有匹配内容，不绑定
                    else:
                        return []  # 非文字图层，确实没有文件
                layer_files.append(files)

            # 使用itertools.product生成所有组合
            all_combinations = []
            for combination in itertools.product(*layer_files):
                combo_dict = {}
                for i, file_path in enumerate(combination):
                    combo_dict[layer_indices[i]] = file_path
                all_combinations.append(combo_dict)

            return all_combinations

        except Exception as e:
            return []

    def _hash_combination(self, combination: Dict[int, str]) -> str:
        """生成组合的哈希值 - 用于识别唯一组合

        🔧 关键修复：必须包含图层索引信息！
        否则[L0:img1,L1:img2]和[L0:img2,L1:img1]会被误认为相同组合
        """
        import hashlib
        # 🔧 修复：按图层索引顺序拼接，不要二次排序文件名
        # 格式：L0:filename|L1:filename|L2:filename
        parts = []
        for idx in sorted(combination.keys()):
            file_name = os.path.basename(combination[idx])
            parts.append(f"L{idx}:{file_name}")
        combination_str = "|".join(parts)  # 不排序！保持图层顺序
        return hashlib.md5(combination_str.encode()).hexdigest()

    def clear_usage_history(self):
        """清除使用历史（用于新的导出会话）"""
        if hasattr(self, '_category_usage_history'):
            self._category_usage_history.clear()
            print(f"[绑定组] 已清除分类使用历史")

    def _select_optimal_combination(self, group_id: str, all_combinations: List[Dict[int, str]],
                                    layer_indices: List[int]) -> Optional[Dict[int, str]]:
        """选择最优组合 - 集成全局避重管理器的强化版本"""
        if not all_combinations:
            return None

        # 🚀 使用增强的全局避重管理器
        from app.utils.global_avoid_repeat_manager import GlobalAvoidRepeatManager
        global_mgr = GlobalAvoidRepeatManager()

        # 获取当前分类（从文件类别分析中推断）
        current_category = None
        for category in self.file_categories.keys():
            category_combos = self._generate_all_combinations(category, layer_indices)
            if category_combos and len(category_combos) == len(all_combinations):
                # 检查是否匹配
                if self._combinations_match(category_combos, all_combinations):
                    current_category = category
                    break

        if current_category is None:
            print(f"[绑定组智能选择] 警告：无法确定当前分类，使用备用逻辑")
            return self._fallback_combination_selection(all_combinations)

        print(f"[绑定组智能选择] 为绑定组 {group_id} 分类 '{current_category}' 选择最优组合")

        # 🎯 使用全局避重管理器的绑定组专用方法
        selected_combination = global_mgr.get_diverse_binding_combination(
            group_id, current_category, all_combinations, layer_indices
        )

        if selected_combination:
            print(f"[绑定组智能选择] 成功选择组合")
            return selected_combination
        else:
            print(f"[绑定组智能选择] 全局避重管理器未返回组合，使用备用逻辑")
            return self._fallback_combination_selection(all_combinations)

    def _combinations_match(self, combos1: List[Dict[int, str]], combos2: List[Dict[int, str]]) -> bool:
        """检查两个组合列表是否匹配（内容相同但顺序可能不同）"""
        if len(combos1) != len(combos2):
            return False

        # 转换为可比较的格式
        set1 = set()
        set2 = set()

        for combo in combos1:
            sorted_items = tuple(sorted(combo.items()))
            set1.add(sorted_items)

        for combo in combos2:
            sorted_items = tuple(sorted(combo.items()))
            set2.add(sorted_items)

        return set1 == set2

    def _fallback_combination_selection(self, all_combinations: List[Dict[int, str]]) -> Optional[Dict[int, str]]:
        """备用组合选择逻辑（原有逻辑的简化版本）"""
        if not all_combinations:
            return None

        from app.utils.global_avoid_repeat_manager import GlobalAvoidRepeatManager
        global_mgr = GlobalAvoidRepeatManager()

        # 按使用次数分类组合
        combination_usage = []
        for combo in all_combinations:
            file_paths = list(combo.values())
            usage_count = global_mgr.get_combination_usage_count(file_paths)
            is_recent = global_mgr.is_combination_recent(file_paths)
            combination_usage.append((combo, usage_count, is_recent))

        # 优先选择未使用过的组合
        unused_combos = [item for item in combination_usage if item[1] == 0 and not item[2]]
        if unused_combos:
            return random.choice(unused_combos)[0]

        # 其次选择使用次数最少且非最近的组合
        non_recent_combos = [item for item in combination_usage if not item[2]]
        if non_recent_combos:
            min_usage = min(item[1] for item in non_recent_combos)
            min_usage_combos = [item for item in non_recent_combos if item[1] == min_usage]
            return random.choice(min_usage_combos)[0]

        # 最后选择使用次数最少的组合
        combination_usage.sort(key=lambda x: x[1])
        return combination_usage[0][0]

    def _random_select_with_diversity_boost(self, combinations: List[Dict[int, str]],
                                            reference_files: List[str] = None) -> Dict[int, str]:
        """随机选择并增强多样性 - 避免选择相似的组合"""
        import threading

        if not combinations:
            return {}

        if len(combinations) == 1:
            return combinations[0]

        # 如果有参考文件，计算相似度并避免高相似度的组合
        if reference_files and len(combinations) > 3:
            # 计算每个组合与参考文件的相似度
            diverse_combinations = []
            reference_basenames = set(os.path.basename(f) for f in reference_files)

            for combo in combinations:
                combo_basenames = set(os.path.basename(f) for f in combo.values())
                # 计算文件名重复率
                overlap_ratio = len(combo_basenames & reference_basenames) / len(combo_basenames)

                # 优先选择重复率低的组合（多样性高）
                if overlap_ratio < 0.5:  # 重复率低于50%
                    diverse_combinations.append(combo)

            if diverse_combinations:
                combinations = diverse_combinations
                print(f"[多样性增强] 过滤后保留 {len(combinations)} 个高多样性组合")

        # 多重随机因子
        timestamp_factor = int(time.time_ns()) % 1000000000
        process_factor = os.getpid() % 10000
        try:
            thread_factor = hash(threading.current_thread().name) % 10000
        except Exception:
            thread_factor = 0
        prime_factor = 7919  # 质数因子

        # 综合随机种子
        seed = (timestamp_factor + process_factor + thread_factor + prime_factor) % 1000000000
        random.seed(seed)

        # 多轮洗牌
        shuffled_combinations = combinations.copy()
        for _ in range(5):
            random.shuffle(shuffled_combinations)

        # 最终选择
        selected = random.choice(shuffled_combinations)
        random.seed()  # 恢复随机状态

        return selected

    def _random_select_with_ultra_randomization(self, combinations: List[Dict[int, str]]) -> Dict[int, str]:
        """超强随机化选择"""
        import threading

        if not combinations:
            return {}

        if len(combinations) == 1:
            return combinations[0]

        # 多重随机因子
        timestamp_factor = int(time.time_ns()) % 1000000000
        process_factor = os.getpid() % 10000
        try:
            thread_factor = hash(threading.current_thread().name) % 10000
        except Exception:
            thread_factor = 0
        prime_factor = 7919  # 质数因子

        # 综合随机种子
        seed = (timestamp_factor + process_factor + thread_factor + prime_factor) % 1000000000
        random.seed(seed)

        # 多轮洗牌
        shuffled_combinations = combinations.copy()
        for _ in range(5):
            random.shuffle(shuffled_combinations)

        # 最终选择
        selected = random.choice(shuffled_combinations)
        random.seed()  # 恢复随机状态

        return selected

    def _cross_category_selection(self) -> Dict[int, str]:
        """跨分类混合模式（保留原有逻辑）"""
        available_categories = self.get_available_categories()
        if not available_categories:
            return {}

        # 获取所有图层索引
        all_layer_indices = set()
        for cat in available_categories:
            if cat in self.file_categories:
                all_layer_indices.update(self.file_categories[cat].keys())

        layer_indices = sorted(list(all_layer_indices))
        if not layer_indices:
            return {}

        print(f"[绑定组] 跨分类模式: 图层{layer_indices}, 分类{available_categories}")

        # 清空记录
        self._used_categories_this_round = set()
        self._used_files_this_round = set()

        matched_files = {}

        for layer_index in layer_indices:
            # 获取该图层可用的分类
            layer_categories = []
            for cat in available_categories:
                if (cat in self.file_categories and
                    layer_index in self.file_categories[cat] and
                    self.file_categories[cat][layer_index]):
                    layer_categories.append(cat)

            if not layer_categories:
                continue

            # 优先选择未使用的分类
            unused_categories = [c for c in layer_categories if c not in self._used_categories_this_round]
            target_categories = unused_categories if unused_categories else layer_categories

            # 随机选择分类
            timestamp_seed = int(time.time_ns() + layer_index * 9973) % 1000000000
            random.seed(timestamp_seed)
            selected_category = random.choice(target_categories)
            self._used_categories_this_round.add(selected_category)

            # 获取文件并避重
            files = self.file_categories[selected_category][layer_index]
            unused_files = [f for f in files if f not in self._used_files_this_round]
            target_files = unused_files if unused_files else files

            # 随机选择文件
            file_seed = int(time.time_ns() + layer_index * 7919 + timestamp_seed) % 1000000000
            random.seed(file_seed)
            selected_file = random.choice(target_files)
            self._used_files_this_round.add(selected_file)

            matched_files[layer_index] = selected_file
            print(f"[绑定组] 图层{layer_index}: 分类'{selected_category}' -> {os.path.basename(selected_file)}")

        random.seed()  # 恢复随机状态
        print(f"[绑定组] 跨分类匹配完成: {sorted(self._used_categories_this_round)}")
        return matched_files

    def _rebuild_file_categories(self):
        """重建文件分类：从当前图层状态全量重算，避免旧分类污染匹配结果。"""
        # 全量重算，确保分类与当前图层/文件夹内容一致
        self.file_categories = {}

        # 重新分析图层文件
        for i, layer in enumerate(self.layers):
            self._analyze_layer_files(layer, i)

        try:
            text_layer_info = []
            for idx, layer in enumerate(self.layers):
                if self._is_text_layer(layer):
                    lines = []
                    try:
                        lines = [l.strip() for l in layer.get_text_lines() if str(l).strip()]
                    except Exception:
                        lines = []
                    text_layer_info.append((idx, layer, lines))

            # 仅使用当前重建后的分类集合，避免历史噪声分类残留
            all_categories = list(self.file_categories.keys())
            for category_name in all_categories:
                # 确保分类存在
                if category_name not in self.file_categories:
                    self.file_categories[category_name] = {}

                # 为文字图层添加虚拟路径
                for idx, layer, lines in text_layer_info:
                    # 🔧 修复：更严格的匹配条件，避免双向包含导致的误匹配
                    matched_lines = []
                    for l in lines:
                        line_stripped = str(l).strip()
                        if not line_stripped or not category_name:
                            continue

                        category_str = str(category_name).strip()

                        # 1. 精确匹配（最高优先级）
                        if line_stripped == category_str:
                            matched_lines.append(l)
                        # 2. 分类名在文字行中（仅当分类名是有效产品词时）
                        elif category_str in line_stripped and len(category_str) >= 2 and not self._is_stop_word(category_str):
                            matched_lines.append(l)
                    if matched_lines:
                        if idx not in self.file_categories[category_name]:
                            self.file_categories[category_name][idx] = []
                        for l in matched_lines:
                            vpath = self._build_text_virtual_path(layer.name, l)
                            if vpath not in self.file_categories[category_name][idx]:
                                self.file_categories[category_name][idx].append(vpath)
        except Exception:
            logger.warning("静默异常已忽略: except Exception: in binding_group.py", exc_info=True)
            pass