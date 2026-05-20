#!/usr/bin/env python3
"""
智能图层选择器
为预计算导出提供智能的图像选择策略
"""

import random
import os
from typing import List, Optional


class SmartLayerSelector:
    """智能图层选择器，用于为图层智能选择图像"""
    
    def __init__(self, image_pool: List[str], layer_name: str = ""):
        """
        初始化智能选择器
        
        Args:
            image_pool: 图像文件路径列表
            layer_name: 图层名称（用于调试）
        """
        self.image_pool = image_pool.copy() if image_pool else []
        self.layer_name = layer_name
        self.current_index = 0
        self.used_images = set()
        
        # 打乱图像池以增加随机性
        if self.image_pool:
            random.shuffle(self.image_pool)
            
        print(f"[智能选择器] 为图层 '{layer_name}' 初始化，图像池: {len(self.image_pool)} 个文件")
    
    def select_next_file(self) -> Optional[str]:
        """
        选择下一个图像文件
        
        Returns:
            选中的图像文件路径，如果没有可用文件则返回None
        """
        if not self.image_pool:
            return None
        
        # 如果所有图像都用过了，重置使用记录
        if len(self.used_images) >= len(self.image_pool):
            self.used_images.clear()
            self.current_index = 0
            # 重新打乱以增加变化
            random.shuffle(self.image_pool)
            print(f"[智能选择器] 图层 '{self.layer_name}' 重置选择器，重新打乱图像池")
        
        # 循环选择，确保不重复
        attempts = 0
        max_attempts = len(self.image_pool)
        
        while attempts < max_attempts:
            selected_file = self.image_pool[self.current_index]
            self.current_index = (self.current_index + 1) % len(self.image_pool)
            
            # 检查文件是否存在且未被使用
            if os.path.isfile(selected_file) and selected_file not in self.used_images:
                self.used_images.add(selected_file)
                print(f"[智能选择器] 图层 '{self.layer_name}' 选择: {os.path.basename(selected_file)}")
                return selected_file
            
            attempts += 1
        
        # 如果所有尝试都失败，返回第一个有效文件
        for file_path in self.image_pool:
            if os.path.isfile(file_path):
                print(f"[智能选择器] 图层 '{self.layer_name}' 备用选择: {os.path.basename(file_path)}")
                return file_path
        
        print(f"[智能选择器] 警告：图层 '{self.layer_name}' 没有可用的图像文件")
        return None
    
    def get_random_file(self) -> Optional[str]:
        """
        随机选择一个图像文件（不考虑使用历史）
        
        Returns:
            随机选中的图像文件路径
        """
        if not self.image_pool:
            return None
        
        # 过滤出存在的文件
        valid_files = [f for f in self.image_pool if os.path.isfile(f)]
        
        if not valid_files:
            print(f"[智能选择器] 警告：图层 '{self.layer_name}' 没有有效的图像文件")
            return None
        
        selected_file = random.choice(valid_files)
        print(f"[智能选择器] 图层 '{self.layer_name}' 随机选择: {os.path.basename(selected_file)}")
        return selected_file
    
    def reset(self):
        """重置选择器状态"""
        self.current_index = 0
        self.used_images.clear()
        if self.image_pool:
            random.shuffle(self.image_pool)
        print(f"[智能选择器] 图层 '{self.layer_name}' 选择器已重置")
    
    def get_pool_size(self) -> int:
        """获取图像池大小"""
        return len(self.image_pool)
    
    def get_available_count(self) -> int:
        """获取可用图像数量"""
        return len([f for f in self.image_pool if os.path.isfile(f)])
    
    def get_used_count(self) -> int:
        """获取已使用图像数量"""
        return len(self.used_images)
    
    def is_exhausted(self) -> bool:
        """检查是否所有图像都已使用"""
        available_count = self.get_available_count()
        return available_count > 0 and len(self.used_images) >= available_count
    
    def get_status(self) -> dict:
        """获取选择器状态信息"""
        return {
            'layer_name': self.layer_name,
            'pool_size': self.get_pool_size(),
            'available_count': self.get_available_count(),
            'used_count': self.get_used_count(),
            'current_index': self.current_index,
            'is_exhausted': self.is_exhausted()
        }


class SmartLayerSelectorManager:
    """智能图层选择器管理器"""
    
    def __init__(self):
        self.selectors = {}
    
    def create_selector(self, layer_id: str, image_pool: List[str], layer_name: str = "") -> SmartLayerSelector:
        """创建并注册一个选择器"""
        selector = SmartLayerSelector(image_pool, layer_name)
        self.selectors[layer_id] = selector
        return selector
    
    def get_selector(self, layer_id: str) -> Optional[SmartLayerSelector]:
        """获取指定的选择器"""
        return self.selectors.get(layer_id)
    
    def reset_all(self):
        """重置所有选择器"""
        for selector in self.selectors.values():
            selector.reset()
        print(f"[选择器管理器] 已重置所有 {len(self.selectors)} 个选择器")
    
    def clear(self):
        """清除所有选择器"""
        self.selectors.clear()
        print(f"[选择器管理器] 已清除所有选择器")
    
    def get_status_summary(self) -> dict:
        """获取所有选择器的状态摘要"""
        summary = {
            'total_selectors': len(self.selectors),
            'selectors': {}
        }
        
        for layer_id, selector in self.selectors.items():
            summary['selectors'][layer_id] = selector.get_status()
        
        return summary


# 全局选择器管理器实例
_global_selector_manager = None


def get_global_selector_manager() -> SmartLayerSelectorManager:
    """获取全局选择器管理器实例"""
    global _global_selector_manager
    if _global_selector_manager is None:
        _global_selector_manager = SmartLayerSelectorManager()
    return _global_selector_manager


def create_smart_selector(layer_id: str, image_pool: List[str], layer_name: str = "") -> SmartLayerSelector:
    """便捷函数：创建智能选择器"""
    manager = get_global_selector_manager()
    return manager.create_selector(layer_id, image_pool, layer_name)


def get_smart_selector(layer_id: str) -> Optional[SmartLayerSelector]:
    """便捷函数：获取智能选择器"""
    manager = get_global_selector_manager()
    return manager.get_selector(layer_id)


def reset_all_selectors():
    """便捷函数：重置所有选择器"""
    manager = get_global_selector_manager()
    manager.reset_all()


def clear_all_selectors():
    """便捷函数：清除所有选择器"""
    manager = get_global_selector_manager()
    manager.clear()
