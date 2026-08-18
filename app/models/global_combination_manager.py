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


class GlobalCombinationManager:
    """全局组合历史管理器 - 实现真正的全局不重复随机化"""
    
    def __init__(self):
        self.combination_history = {}  # 全局组合使用历史: {group_id: {combination_hash: use_count}}
        self.category_usage_history = {}  # 分类使用历史: {group_id: {category: use_count}}
        self.category_combination_history = {}  # 分类组合历史: {group_id: {category: {combo_hash: count}}}
        self.category_pattern_history = {}  # 跨分类模式历史: {pattern_hash: use_count}
        self.recent_category_sequence = []  # 最近使用的分类序列
        self.max_history_size = 10000  # 最大历史记录数量
        self.diversity_threshold = 0.7  # 多样性阈值：70%的组合用过后才允许重复
        self.max_recent_sequence = 10  # 最大最近序列长度
        
    def generate_combination_hash(self, file_paths: List[str]) -> str:
        """生成文件组合的唯一哈希值"""
        # 使用文件名（不含路径）生成哈希，确保相同组合总是产生相同哈希
        file_names = [os.path.basename(path) for path in sorted(file_paths)]
        combination_str = '|'.join(file_names)
        return hashlib.md5(combination_str.encode()).hexdigest()[:16]
    
    def is_combination_fresh(self, group_id: str, file_paths: List[str]) -> bool:
        """检查组合是否是全新的（从未使用过）"""
        combo_hash = self.generate_combination_hash(file_paths)
        if group_id not in self.combination_history:
            return True
        return combo_hash not in self.combination_history[group_id]
    
    def get_combination_usage_count(self, group_id: str, file_paths: List[str]) -> int:
        """获取组合的使用次数"""
        combo_hash = self.generate_combination_hash(file_paths)
        if group_id not in self.combination_history:
            return 0
        return self.combination_history[group_id].get(combo_hash, 0)
    
    def record_combination_usage(self, group_id: str, file_paths: List[str], category: str = None):
        """记录组合使用情况，包括分类信息和跨分类模式"""
        combo_hash = self.generate_combination_hash(file_paths)
        
        # 记录全局组合使用
        if group_id not in self.combination_history:
            self.combination_history[group_id] = {}
        current_count = self.combination_history[group_id].get(combo_hash, 0)
        self.combination_history[group_id][combo_hash] = current_count + 1
        
        # 记录分类使用统计
        if category:
            if group_id not in self.category_usage_history:
                self.category_usage_history[group_id] = {}
            if group_id not in self.category_combination_history:
                self.category_combination_history[group_id] = {}
            
            # 统计分类使用次数
            category_count = self.category_usage_history[group_id].get(category, 0)
            self.category_usage_history[group_id][category] = category_count + 1
            
            # 统计分类内组合使用
            if category not in self.category_combination_history[group_id]:
                self.category_combination_history[group_id][category] = {}
            cat_combo_count = self.category_combination_history[group_id][category].get(combo_hash, 0)
            self.category_combination_history[group_id][category][combo_hash] = cat_combo_count + 1
            
            # 🚀 新增：记录跨分类模式
            self._record_category_pattern(category)
        
        # 清理历史记录，防止内存过大
        self._cleanup_history(group_id)
        
        file_names = [os.path.basename(path) for path in file_paths]
        category_info = f", 分类: {category}" if category else ""
        print(f"[全局组合管理器] 记录组合使用: {group_id} -> {file_names}{category_info} (使用次数: {current_count + 1})")
    
    def _record_category_pattern(self, category: str):
        """记录分类使用模式，用于跨分类避重"""
        # 添加到最近序列
        self.recent_category_sequence.append(category)
        
        # 保持序列长度
        if len(self.recent_category_sequence) > self.max_recent_sequence:
            self.recent_category_sequence.pop(0)
        
        # 生成模式哈希（最近3个分类的组合）
        if len(self.recent_category_sequence) >= 3:
            pattern = '|'.join(self.recent_category_sequence[-3:])
            pattern_hash = hashlib.md5(pattern.encode()).hexdigest()[:8]
            
            if pattern_hash not in self.category_pattern_history:
                self.category_pattern_history[pattern_hash] = 0
            self.category_pattern_history[pattern_hash] += 1
            
            print(f"[跨分类模式] 记录模式: {pattern} -> 使用{self.category_pattern_history[pattern_hash]}次")
    
    def is_category_pattern_overused(self, candidate_category: str, threshold: int = 3) -> bool:
        """检查待选分类是否会形成过度使用的模式"""
        if len(self.recent_category_sequence) < 2:
            return False
        
        # 构建潜在模式
        potential_pattern = '|'.join(self.recent_category_sequence[-2:] + [candidate_category])
        pattern_hash = hashlib.md5(potential_pattern.encode()).hexdigest()[:8]
        
        usage_count = self.category_pattern_history.get(pattern_hash, 0)
        is_overused = usage_count >= threshold
        
        if is_overused:
            print(f"[跨分类模式] 模式 '{potential_pattern}' 已使用{usage_count}次，超过阈值{threshold}")
        
        return is_overused
    
    def get_pattern_aware_category_score(self, category: str) -> float:
        """获取考虑模式避重的分类评分"""
        base_score = 1.0
        
        # 检查是否会形成过度使用的模式
        if self.is_category_pattern_overused(category, threshold=2):
            base_score *= 0.3  # 大幅降低评分
        elif self.is_category_pattern_overused(category, threshold=1):
            base_score *= 0.7  # 适度降低评分
        
        # 检查最近是否使用过相同分类
        if (len(self.recent_category_sequence) > 0 and 
            self.recent_category_sequence[-1] == category):
            base_score *= 0.5  # 避免连续使用相同分类
        
        return base_score
    
    def get_category_usage_count(self, group_id: str, category: str) -> int:
        """获取分类的使用次数"""
        if group_id not in self.category_usage_history:
            return 0
        return self.category_usage_history[group_id].get(category, 0)
    
    def get_category_diversity_score(self, group_id: str, category: str, total_possible_combinations: int) -> float:
        """获取分类的多样性分数"""
        if (group_id not in self.category_combination_history or 
            category not in self.category_combination_history[group_id] or
            total_possible_combinations == 0):
            return 1.0
        
        used_combinations = len(self.category_combination_history[group_id][category])
        return max(0.0, 1.0 - (used_combinations / total_possible_combinations))
    
    def get_least_used_categories(self, group_id: str, categories: List[str], count: int = None) -> List[str]:
        """获取使用次数最少的分类列表"""
        if not categories:
            return []
        
        # 按使用次数排序
        category_usage = [(cat, self.get_category_usage_count(group_id, cat)) for cat in categories]
        category_usage.sort(key=lambda x: x[1])  # 按使用次数升序
        
        result = [cat for cat, _ in category_usage]
        if count is not None:
            result = result[:count]
            
        return result
    
    def _cleanup_history(self, group_id: str):
        """清理历史记录，保持合理大小"""
        if group_id not in self.combination_history:
            return
            
        history = self.combination_history[group_id]
        if len(history) > self.max_history_size:
            # 保留使用次数最少的组合记录
            sorted_combos = sorted(history.items(), key=lambda x: x[1])
            keep_count = int(self.max_history_size * 0.8)  # 保留80%
            self.combination_history[group_id] = dict(sorted_combos[:keep_count])
            print(f"[全局组合管理器] 清理历史记录: {group_id}, 保留 {keep_count} 条记录")
    
    def get_diversity_score(self, group_id: str, total_possible_combinations: int) -> float:
        """计算当前多样性得分（0-1，1表示完全多样化）"""
        if group_id not in self.combination_history or total_possible_combinations == 0:
            return 1.0
        
        used_combinations = len(self.combination_history[group_id])
        return min(1.0, used_combinations / total_possible_combinations)
    
    def should_prioritize_fresh_combinations(self, group_id: str, total_possible: int) -> bool:
        """是否应该优先选择全新组合"""
        diversity_score = self.get_diversity_score(group_id, total_possible)
        return diversity_score < self.diversity_threshold
    
    def get_statistics(self, group_id: str) -> Dict:
        """获取组合使用统计信息"""
        if group_id not in self.combination_history:
            return {
                'total_used_combinations': 0,
                'total_usage_count': 0,
                'most_used_count': 0,
                'least_used_count': 0
            }
        
        history = self.combination_history[group_id]
        usage_counts = list(history.values())
        
        return {
            'total_used_combinations': len(history),
            'total_usage_count': sum(usage_counts),
            'most_used_count': max(usage_counts) if usage_counts else 0,
            'least_used_count': min(usage_counts) if usage_counts else 0
        }


