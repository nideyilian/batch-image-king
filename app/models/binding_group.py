#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""图层绑定组（聚合类）

为降低单文件体积，原 BindingGroup 单一巨型类已拆分为 4 个聚焦子 mixin：

  - binding_group_cache.py             (BindingGroupCache)
      持久化文件夹分类索引 + 目录扫描 + 缓存失效
  - binding_group_layer_analysis.py    (BindingGroupLayerAnalysis)
      图层接入/移除/信号 + 文字/图像图层分析 + 关键词提取 + 文件名核心名
  - binding_group_category_selection.py (BindingGroupCategorySelection)
      可用分类 + 多样性分析 + 随机选分类 + 语义一致性验证
  - binding_group_matching.py          (BindingGroupMatching)
      匹配选文件 + 组合生成 + 避重 + 跨分类混合 + 全量重建

BindingGroup 通过多继承聚合上述 mixin，外部 `from app.models.binding_group
import BindingGroup` 写法继续有效。
"""

import os
import logging

from app.models.binding_group_cache import BindingGroupCache
from app.models.binding_group_layer_analysis import BindingGroupLayerAnalysis
from app.models.binding_group_category_selection import BindingGroupCategorySelection
from app.models.binding_group_matching import BindingGroupMatching

logger = logging.getLogger(__name__)


class BindingGroup(
    BindingGroupCache,
    BindingGroupLayerAnalysis,
    BindingGroupCategorySelection,
    BindingGroupMatching,
):
    """绑定组类（聚合类，行为与原单一类完全一致）。

    拆分前所有方法定义均保留在 4 个子 mixin 中；本类仅持有：

    - 类级文件夹分类索引缓存（_folder_category_index_*）
    - 实例属性（layers / file_categories / group_id / name / 等）

    方法解析顺序 (MRO) 保持原行为：Cache → LayerAnalysis → CategorySelection →
    Matching，确保方法在跨 mixin 调用时能正确找到 self 上的属性。
    """

    # 类级缓存（由 BindingGroupCache 使用，保留在这里以保证 id 一致）
    _folder_category_index_cache = {}  # type: dict
    _folder_category_index_dirty = False
    _folder_category_index_last_save_time = 0.0
    _folder_category_index_loaded = False

    def __init__(self, group_id: str, name: str, binding_manager=None):
        # 首次访问时确保磁盘上的持久化索引加载到类级缓存
        self._ensure_persistent_category_index_loaded()
        self.group_id = group_id
        self.name = name
        self.layers = []  # 绑定的图层列表
        self.file_categories = {}  # 文件分类：{核心名称: {图层索引: [文件路径列表]}}
        self.last_selected_category = None  # 上次选择的分类
        self._binding_manager = binding_manager  # 绑定管理器引用，用于获取文件限制

        # 🔧 根本修复：添加每个分类的使用历史，避免重复返回相同组合
        self._category_usage_history = {}  # {category: set of used combo hashes}
        # 记录信号连接，确保移除时不影响其他监听者
        self._signal_connections = {}  # {layer_id: {"text_changed": slot, "changed": slot}}


__all__ = ["BindingGroup"]
