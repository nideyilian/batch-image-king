import copy
from PySide6.QtCore import QObject, Signal
# 导入新的Layer类作为主要实现
from app.models.layer_new import Layer as NewLayer
import time
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

        # 来源标记：由预设打开的文档会带上「哪张卡片、第几页」。
        # 用途是「同一张预设卡片只对应一套标签页」的去重判定
        # （见 PresetManagerViewModel.loadPreset）。
        # 空串 = 不是从预设打开的（新建 / 打开 .cmp / 复制出来的副本）。
        # ⚠️ 这两个字段**不进序列化**（DocumentSerializer 用显式键名），
        # 否则预设文件会被运行时状态污染。
        self.source_preset_id = ""
        self.source_preset_page = -1

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

    def save_state(self, action_name, coalesce_key=None):
        """保存当前状态到历史记录。

        coalesce_key 非空时，同一键在 400ms 内的连续快照会被合并成一条
        （拖滑块一次触发几十次属性变更，不合并会把撤销栈占满）。
        """
        # 使用各图层自己的 serialize()（普通/文字/异形图层均已实现），
        # 避免使用不存在的 to_dict 导致图层被序列化为 None，撤销后图层全部丢失。
        from app.utils.layer_tree import serialize_layer_tree

        state = {
            'canvas_width': self.canvas_width,
            'canvas_height': self.canvas_height,
            'layers': serialize_layer_tree(self.layers, lambda layer: layer.serialize()),
            'selected_layer_index': self.selected_layer_index,
            'selected_layer_indices': list(self.selected_layer_indices),
            'view_settings': copy.deepcopy(self.view_settings),
            'binding_groups': copy.deepcopy(self.binding_manager.serialize()),
            'layer_size_matches': copy.deepcopy(self.layer_size_match_manager.serialize()),
        }
        self._history_manager.save_state(action_name, state, coalesce_key=coalesce_key)

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
        self.view_settings = copy.deepcopy(state.get('view_settings', self.view_settings))

        # 命中测试缓存需要随撤销/重做的结构变化失效
        self.bump_hit_test_version()

        # 恢复图层
        from app.models.layer_new import Layer as NewLayer
        import logging
        logger = logging.getLogger(__name__)
        restored = []
        # ⚠️ 这里**不能**传 ``parent=self``。
        #
        # 正常创建路径 ``add_layer`` 是不传 parent 的（见 document_layers.py）：
        # 图层只由 ``self.layers`` 这个 Python 列表持有，C++ 侧不是 Document 的子对象。
        # 而旧版 ``_restore_state`` 传了 ``parent=self``，于是撤销恢复出来的图层
        # 被挂进了 Document 的 C++ 子对象树 —— 与创建路径形成两套所有权模型：
        #
        #   创建：Python 列表持有 → 从列表移除即可回收
        #   恢复：C++ 树持有    → 从列表移除后仍被 Document 攥着，永不释放
        #
        # 实测（docs/audit/_probe_undo_leak.py，5 图层文档「改属性 + 撤销」20 轮）：
        # Layer 对象 5 → 100，doc.children() 4 → 104，95 个孤儿图层的 parent() 仍是 Document。
        # 用户侧就是「操作多几下就卡死」——每轮撤销常驻一份图层 + 图像缓存。
        #
        # 改为不传 parent，与创建路径对齐后：40 轮撤销仍是 5 个 Layer、0 孤儿，
        # children 稳定在「4 个管理器 + 当前图层数」。
        try:
            from app.utils.layer_tree import deserialize_layer_tree

            restored = deserialize_layer_tree(
                state.get('layers', []),
                lambda layer_data, parent=None: NewLayer.from_dict(layer_data, parent=None),
                parent=None,
            )
        except Exception as error:
            logger.warning("撤销/重做恢复图层树失败，回退到扁平恢复: %s", error)
            for idx, layer_data in enumerate(state.get('layers', [])):
                if layer_data is None:
                    logger.warning("撤销/重做恢复时第 %d 个图层数据为空，已跳过", idx)
                    continue
                try:
                    layer = NewLayer.from_dict(layer_data, parent=None)
                except Exception as e:
                    logger.warning("撤销/重做恢复时第 %d 个图层反序列化失败，已跳过: %s", idx, e)
                    continue
                restored.append(layer)
        old_layers = list(self.layers)
        self.layers = restored
        # 旧图层若曾被挂到树上（老版本存的历史、或别处传了 parent），这里兜底摘干净。
        self._release_layers(old_layers)
        # 恢复出来的图层必须接回 document_changed，否则撤销后再改属性不会重绘。
        self._attach_layer_signals(restored)
        try:
            self.binding_manager.deserialize(state.get('binding_groups', {}) or {}, self.layers)
        except Exception as error:
            logger.warning("撤销/重做恢复绑定组失败: %s", error)
        try:
            self.layer_size_match_manager.deserialize(state.get('layer_size_matches', {}) or {})
        except Exception as error:
            logger.warning("撤销/重做恢复尺寸匹配失败: %s", error)

    def _release_layers(self, layers) -> None:
        """把一批图层从文档的 C++ 子对象树上摘下来并交给事件循环销毁。

        为什么必须两步（``setParent(None)`` + ``deleteLater``）：
        - 只 ``deleteLater``：PySide 删除 QObject 时会连带删除其 C++ 子树，
          但这里图层是 Document 的**子对象**，父对象还活着，删除会延迟到父对象析构 ——
          等于没删。
        - 只 ``setParent(None)``：脱离父对象后若无 Python 引用就该被回收，
          但 Qt 对象由 C++ 侧持有，PySide 不保证立即释放，仍需 deleteLater 收口。

        必须容忍异常：撤销是高频路径，任何一层对象已失效（例如已被父对象连带销毁）
        都不能让撤销本身失败。
        """
        for layer in layers:
            if layer is None:
                continue
            try:
                layer.setParent(None)
            except (RuntimeError, TypeError, AttributeError):
                # 已经脱离或底层对象已销毁，跳过
                pass
            try:
                layer.deleteLater()
            except (RuntimeError, TypeError, AttributeError):
                pass

    def _attach_layer_signals(self, layers) -> None:
        """给恢复出来的图层接回 ``changed`` 信号。

        ``deserialize`` 只负责还原属性，不建信号连接；而 ``add_layer`` /
        ``add_existing_layer`` 都会 ``layer.changed.connect(self.document_changed.emit)``。
        撤销走的是 deserialize 路径，旧实现漏了这一步 ——
        实测撤销后的图层 ``changed`` 接收者数为 **0**，
        于是撤销之后直接改该图层的属性（例如拖一下）不会触发任何重绘，
        界面看着「没反应」，用户会以为卡住了。

        重复连接是安全的：同一个信号重复连到同一个槽只会投递一次。
        """
        for layer in layers:
            if layer is None:
                continue
            signal = getattr(layer, "changed", None)
            if signal is None:
                continue
            try:
                signal.connect(self.document_changed.emit)
            except (RuntimeError, TypeError):
                pass

    def create_new(self, width, height):
        """创建新文档。

        画布尺寸必须在这里拦住：``export_image`` 早就有 16~32768 的校验，
        但 ``create_new`` 没有，于是 ``create_new(0, 0)`` 能成功，
        渲染出 0×0 图像，一直拖到导出才报「画布尺寸无效」——校验放错了层。
        这里的下限与 ``resizeCanvas`` 保持一致，避免两套口径。
        """
        width = int(width)
        height = int(height)
        # 先判上限再判下限，否则 (40000, 10) 这类会报「不能小于 16」误导排查
        if width > 32768 or height > 32768:
            raise ValueError(f"画布尺寸不能大于 32768×32768（收到 {width}×{height}）")
        if width < 16 or height < 16:
            raise ValueError(f"画布尺寸不能小于 16×16（收到 {width}×{height}）")
        self.canvas_width = width
        self.canvas_height = height
        self.layers = []
        self.selected_layer_index = -1
        self.selected_layer_indices = []
        self.current_file_path = None
        self.is_modified = False
        self.bump_hit_test_version()
        self.document_changed.emit()
