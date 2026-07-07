#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图层绑定管理器（兼容入口）

为降低单文件体积，原 binding_manager.py 已拆分为：
  - binding_group.py            (BindingGroup)
  - global_combination_manager.py (GlobalCombinationManager)
  - layer_binding_manager.py    (LayerBindingManager)

本文件保留为兼容入口，重新导出全部公开类，外部
`from app.models.binding_manager import BindingGroup / LayerBindingManager`
等写法继续有效。
"""

from app.models.binding_group import BindingGroup
from app.models.global_combination_manager import GlobalCombinationManager
from app.models.layer_binding_manager import LayerBindingManager

__all__ = ["BindingGroup", "GlobalCombinationManager", "LayerBindingManager"]
