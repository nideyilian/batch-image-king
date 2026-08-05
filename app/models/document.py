import os
import random
import json
import pickle
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
from PIL.Image import Resampling, Transpose
import numpy as np
from PySide6.QtCore import QObject, Signal
import re
import glob
import gc
# 导入新的Layer类作为主要实现
from app.models.layer_new import Layer as NewLayer
from app.models.document_blend import BlendMode
from app.models.document_blend import Blender
from typing import List, Tuple
from app.models.binding_manager import BindingGroup
import time
import hashlib
from app.utils.render_diagnostics import log_branch, log_sampling
from app.utils.print_utils import safe_print as _safe_print
from app.models.layer_size_match_manager import LayerSizeMatchManager

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print

# 方法拆分 mixin（保持 Document 类对外接口完全不变）
from app.models.document_layers import DocumentLayers
from app.models.document_randomize import DocumentRandomize
from app.models.document_render import DocumentRender
from app.models.document_export import DocumentExport

def needs_cropping(bounds, image):
    """检查给定的边界是否需要裁剪

    Args:
        bounds: 边界元组 (left, top, right, bottom)
        image: PIL图像对象

    Returns:
        bool: 是否需要裁剪
    """
    left, top, right, bottom = bounds
    return (left > 0 or top > 0 or right < image.width or bottom < image.height)



class Document(DocumentLayers, DocumentRandomize, DocumentRender, DocumentExport, QObject):
    """文档模型，包含画布和图层信息

    说明：为降低单文件体积与维护成本，原 Document 的图层管理、随机化、
    渲染、导出等方法已拆分到独立的 mixin 模块（document_layers /
    document_randomize / document_render / document_export），通过多重继承
    组合回 Document。对外接口（方法名、信号、实例化方式）完全保持不变。
    """

    # 信号定义
    document_changed = Signal()  # 文档内容变化信号
    layer_changed = Signal()     # 图层列表变化信号
    history_changed = Signal()   # 历史记录变化信号
    layer_selected = Signal(int) # 图层选中信号，传递选中的图层索引
    layers_selection_changed = Signal(list)  # 多图层选中信号，传递选中的图层索引列表
    layers_changed = Signal()    # 图层内容变化信号
    layer_updated = Signal(int)  # 单个图层更新信号，传递图层索引

    # 批量导出相关信号
    export_progress_updated = Signal(int)  # 导出进度更新信号，传递当前进度值
    file_exported = Signal(str)            # 单个文件导出完成信号，传递文件信息
    export_stage_updated = Signal(str)     # 导出阶段更新信号，传递阶段名称

    def __init__(self, parent=None):
        super().__init__(parent)

        # 父对象
        self.parent = parent

        # 是否已修改
        self.is_modified = False

        # ===== 重构：使用DocumentHistory管理历史记录 =====
        from app.models.document_history import DocumentHistory
        self._history_manager = DocumentHistory(max_history=20, parent=self)
        self._history_manager.history_changed.connect(self.history_changed.emit)

        # 保留旧接口兼容性（委托给_history_manager）
        self.history = []  # 保留以防某些地方直接访问
        self.history_index = -1  # 保留以防某些地方直接访问
        self.max_history = 20  # 保留以防某些地方直接访问

        # ===== 重构：使用DocumentSerializer管理序列化 =====
        from app.models.document_serializer import DocumentSerializer
        self._serializer = DocumentSerializer(parent=self)

        # 渲染统一走 app.services.render_service（FastRenderer 单一路出口）。

        # ===== 重构：使用BatchExportCoordinator协调导出 =====
        from app.models.batch_export_coordinator import BatchExportCoordinator
        self._export_coordinator = BatchExportCoordinator(parent=self)

        # 画布尺寸
        self.canvas_width = 800
        self.canvas_height = 600

        # 图层列表
        self.layers = []
        self.selected_layer_index = -1
        self.selected_layer_indices = []

        # 当前文件路径
        self.current_file_path = None

        # 导出设置
        self.export_settings = self._build_default_export_settings()

        # 导出错误信息
        self._last_export_error = None  # 存储最后一次导出错误信息
        self._last_export_report = None  # 结构化导出报告（迭代1）
        self._export_report_history = []  # 最近N次导出报告（迭代3.1）

        # 缓存刷新标记
        self._needs_cache_refresh = False
        # 快速首帧标记：随机化等整体变更后先低质量即时出图，后台补全全质量
        self._quick_first_frame = False

        # 命中测试版本：任何影响“画布点击层级/几何/可见性/锁定/分身/组结构”
        # 的变更都必须递增它。预览点击命中缓存以该版本为准，而不是只看
        # 图层数量，避免“画面已刷新但点击仍命中旧层级/旧矩形”的问题。
        self.hit_test_version = 0

        # 最近一次变更上下文（用于UI增量刷新）
        self._last_change_context = None

        # 视图设置（标尺/参考线/吸附/视图变换）
        self.view_settings = {
            'show_rulers': True,
            'show_guides': True,
            'horizontal_guides': [],
            'vertical_guides': [],
            'snap_to_guides': True,
            'ruler_size': 20,
            'zoom_factor': 1.0,
            'offset_x': 0,
            'offset_y': 0,
        }

        # 图层绑定管理器
        from app.models.binding_manager import LayerBindingManager
        self.binding_manager = LayerBindingManager()
        self.layer_size_match_manager = LayerSizeMatchManager(parent=self)

    def _build_default_export_settings(self) -> dict:
        return {
            'format': 'jpg',
            'format_index': 1,
            'directory': '',
            'last_directory': '',
            'template': 'output_{number}',
            'filename_template': 'output_{number}',
            'count': 10,
            'use_date': True,
            'date_format': '%Y%m%d',
            'date_format_index': 0,
            'custom_text': 'export',
            'use_layer_name': False,
            'layer_index': 0,
            'number_format': '{number:04d}',
            'number_format_index': 0,
            'max_file_size_kb': 299,
            'use_current_time_for_path': False,
            'randomize_all': True,  # 是否随机所有图层
            'force_opaque': False,  # 是否强制不透明（用于JPEG格式）
            # 迭代3：动态尝试预算
            'dynamic_budget_enabled': True,
            'dynamic_budget_binding_enabled': True,
            'dynamic_budget_standard_enabled': True,
            'dynamic_budget_min_ratio': 0.8,
            'dynamic_budget_max_ratio': 3.0,
            'dynamic_budget_check_interval': 25,
            'dynamic_budget_min_samples': 40,
            'dynamic_budget_expand_step': 0.2,
            'dynamic_budget_shrink_step': 0.1,
            'dynamic_budget_low_success_rate': 0.15,
            'dynamic_budget_high_success_rate': 0.65,
            'dynamic_budget_high_duplicate_rate': 0.75,
            'dynamic_budget_low_duplicate_rate': 0.30,
            'dynamic_budget_recent_n': 12,
            'export_report_history_limit': 80,
            # 导出写盘策略（迭代4中的I/O优化前置）
            'io_profile': 'balanced',  # speed | balanced | size
            'export_quality_profile': 'quality',  # quality | balanced | speed | size
            'allow_lossy_size_reduction': False,
            'export_backend': 'auto',
            'png_compress_level_override': -1,  # -1 表示自动
            'jpeg_quality_override': 0,  # 0 表示自动
            'auto_runtime_tuning_enabled': True,
            'freeze_preview_during_export': True,
            # 批导读盘优化：预读与会话缓存
            'batch_preload_enabled': True,
            'batch_preload_max_images': 120,
            'batch_preload_memory_mb': 384,
            # 大批量导出隔离：主进程只负责 UI，导出放到独立 Worker 进程
            'export_external_worker_enabled': True,
            'export_worker_min_count': 200,
            'export_worker_resume_enabled': True,
            # 批量导出安全保护：防止过多任务导致卡死/闪退
            'export_safety_enabled': True,
            'export_safety_memory_guard_ratio': 0.40,
            'export_safety_max_consecutive_failures': 8,
            'export_safety_failure_rate_limit': 0.45,
            'export_safety_failure_rate_min_samples': 12,
            'export_safety_stall_timeout_seconds': 180,
        }

    def set_change_context(self, source: str, layer_index: int = -1, fields=None, reason: str = ""):
        """记录最近一次变更上下文，供UI做增量刷新判断。"""
        self._last_change_context = {
            "source": source,
            "layer_index": layer_index,
            "fields": fields,
            "reason": reason,
            "ts": time.time(),
        }

    def get_change_context(self, max_age_ms: int = 1200):
        """读取最近一次变更上下文，超过最大年龄返回 None。"""
        ctx = self._last_change_context
        if ctx is None:
            return None
        if (time.time() - ctx.get("ts", 0)) * 1000 > max_age_ms:
            return None
        return ctx

    def clear_change_context(self):
        self._last_change_context = None

    def bump_hit_test_version(self):
        """递增命中测试版本，强制预览点击缓存失效。

        应在以下操作后调用：图层增删、上下移动、显示/隐藏、锁定/解锁、
        位置/尺寸/旋转变化、形状/路径/圆角变化、分身参数变化、组结构变化。
        """
        self.hit_test_version = getattr(self, "hit_test_version", 0) + 1

    def get_view_settings(self):
        return self.view_settings

    def set_view_settings(self, settings):
        if not isinstance(settings, dict):
            return
        self.view_settings.update(settings)
        self.document_changed.emit()

    def save_state(self, action_name):
        """保存当前状态到历史记录"""
        # 使用各图层自己的 serialize()（普通/文字/异形图层均已实现），
        # 避免使用不存在的 to_dict 导致图层被序列化为 None，撤销后图层全部丢失。
        from app.utils.layer_tree import serialize_layer_tree

        state = {
            'canvas_width': self.canvas_width,
            'canvas_height': self.canvas_height,
            'layers': serialize_layer_tree(self.layers, lambda layer: layer.serialize()),
            'selected_layer_index': self.selected_layer_index,
            'selected_layer_indices': list(self.selected_layer_indices),
        }
        self._history_manager.save_state(action_name, state)

    def can_undo(self):
        return self._history_manager.can_undo()

    def can_redo(self):
        return self._history_manager.can_redo()

    def undo(self):
        """撤销操作"""
        state = self._history_manager.undo()
        if state:
            self._restore_state(state)
            self.history_changed.emit()
            self.layer_changed.emit()
            return True
        return False

    def redo(self):
        """重做操作"""
        state = self._history_manager.redo()
        if state:
            self._restore_state(state)
            self.history_changed.emit()
            self.layer_changed.emit()
            return True
        return False

    def _restore_state(self, state):
        """恢复状态"""
        self.canvas_width = state.get('canvas_width', self.canvas_width)
        self.canvas_height = state.get('canvas_height', self.canvas_height)
        self.selected_layer_index = state.get('selected_layer_index', -1)
        self.selected_layer_indices = list(state.get('selected_layer_indices', []))

        # 命中测试缓存需要随撤销/重做的结构变化失效
        self.bump_hit_test_version()

        # 恢复图层
        from app.models.layer_new import Layer as NewLayer
        import logging
        logger = logging.getLogger(__name__)
        restored = []
        try:
            from app.utils.layer_tree import deserialize_layer_tree

            restored = deserialize_layer_tree(
                state.get('layers', []),
                lambda layer_data, parent=None: NewLayer.from_dict(layer_data, parent=parent),
                parent=self,
            )
        except Exception as error:
            logger.warning("撤销/重做恢复图层树失败，回退到扁平恢复: %s", error)
            for idx, layer_data in enumerate(state.get('layers', [])):
                if layer_data is None:
                    logger.warning("撤销/重做恢复时第 %d 个图层数据为空，已跳过", idx)
                    continue
                try:
                    layer = NewLayer.from_dict(layer_data)
                except Exception as e:
                    logger.warning("撤销/重做恢复时第 %d 个图层反序列化失败，已跳过: %s", idx, e)
                    continue
                restored.append(layer)
        self.layers = restored

    def create_new(self, width, height):
        """创建新文档"""
        self.canvas_width = width
        self.canvas_height = height
        self.layers = []
        self.selected_layer_index = -1
        self.selected_layer_indices = []
        self.current_file_path = None
        self.is_modified = False
        self.bump_hit_test_version()
        self.document_changed.emit()
