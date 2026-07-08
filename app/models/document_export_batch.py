"""``DocumentExportBatch`` mixin：批量导出主流程。

本 mixin 负责：

- ``batch_export``: 批量导出的主入口（含 worker 切换、回退、预分析、清理）。
- ``_clear_layer_temporary_states``: 加载后清理图层的临时随机状态。
- ``_cleanup_layers_after_export``: 导出后清理 + 失效渲染缓存。
- ``cancel_export``: 取消当前批量导出。

注意：``batch_export`` 内部有一个**闭包** ``_is_export_canceled()``，
它依赖 ``self._export_canceled`` 和 ``cancel_callback``，必须随
``batch_export`` 一起迁移。
"""
from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class DocumentExportBatch:
    """Document 导出相关：批量执行子 mixin。"""

    def batch_export(
        self,
        directory,
        count,
        filename_template=None,
        file_format="png",
        start_index=1,
        cancel_callback=None,
        use_high_performance=True,
        traverse_mode=False,
        use_smart_sampling=True,
    ):
        """批量导出不同组合的图像

        Args:
            directory: 输出目录
            count: 导出数量
            filename_template: 文件名模板
            file_format: 文件格式
            start_index: 起始文件序号
            cancel_callback: 取消回调函数
            use_high_performance: 是否使用高性能渲染方案
            traverse_mode: 是否启用遍历模式
            use_smart_sampling: 是否使用智能采样策略（避免图片重复）

        Returns:
            bool: 是否成功
        """

        # 📊 诊断日志：导出参数
        self._last_export_report = None
        self._is_batch_export_running = True

        def _is_export_canceled():
            return bool(getattr(self, '_export_canceled', False)) or bool(cancel_callback and cancel_callback())

        if _is_export_canceled():
            self._last_export_error = "导出已取消"
            self._is_batch_export_running = False
            return False
        try:
            from app.utils.export_worker_client import export_with_worker, should_use_export_worker
            if should_use_export_worker(self, int(count or 0)):
                def worker_progress_wrapper(current_count):
                    if hasattr(self, 'export_progress_updated'):
                        self.export_progress_updated.emit(int(current_count or 0))

                def worker_file_completed_wrapper(message):
                    if hasattr(self, 'file_exported'):
                        self.file_exported.emit(str(message or ""))

                def worker_stage_wrapper(stage_name):
                    if hasattr(self, 'export_stage_updated'):
                        self.export_stage_updated.emit(str(stage_name or ""))

                worker_result = export_with_worker(
                    self,
                    directory=directory,
                    count=int(count or 0),
                    filename_template=filename_template or "image_{number:04d}",
                    file_format=file_format,
                    start_index=start_index,
                    traverse_mode=traverse_mode,
                    avoid_duplicates=use_smart_sampling,
                    progress_callback=worker_progress_wrapper,
                    file_completed_callback=worker_file_completed_wrapper,
                    stage_callback=worker_stage_wrapper,
                    cancel_callback=cancel_callback,
                )
                if worker_result.attempted:
                    self._is_batch_export_running = False
                    if hasattr(self, 'export_stage_updated'):
                        self.export_stage_updated.emit("收尾清理")
                    try:
                        self._cleanup_layers_after_export()
                    except Exception:
                        logger.debug("静默异常已忽略: except Exception: in document_export_batch.py")
                        pass
                    if worker_result.success:
                        if hasattr(self, 'export_stage_updated'):
                            self.export_stage_updated.emit("导出完成")
                        return True
                    self._last_export_error = worker_result.error or "独立导出进程失败"
                    if hasattr(self, 'export_stage_updated'):
                        self.export_stage_updated.emit("导出失败")
                    return False
        except Exception as worker_launch_error:
            print(f"[批量导出] 独立导出进程不可用，回退内部导出: {worker_launch_error}")
        if hasattr(self, 'export_stage_updated'):
            self.export_stage_updated.emit("准备导出")
        print("=" * 80)
        print(f"[批量导出] 🚀 开始批量导出")
        print(f"[批量导出]    数量: {count}")
        print(f"[批量导出]    目录: {directory}")
        print(f"[批量导出]    遍历模式: {traverse_mode}")
        print(f"[批量导出]    智能采样: {use_smart_sampling}")
        print(f"[批量导出]    高性能渲染: {use_high_performance}")
        print("=" * 80)

        # 🔧 性能优化：仅在真正需要时清理缓存
        # 不要每次都执行五层防护清理，那会严重影响性能
        # 只清理必要的渲染缓存即可
        print("[🔧 批量导出] 🧹 清理渲染缓存（轻量级）...")
        if hasattr(self, 'export_stage_updated'):
            self.export_stage_updated.emit("清理缓存")
        if _is_export_canceled():
            self._last_export_error = "导出已取消"
            self._is_batch_export_running = False
            return False
        try:
            # 只清理渲染缓存，保留其他状态
            from app.utils.fast_renderer import get_global_fast_renderer
            renderer = get_global_fast_renderer()
            if hasattr(renderer, 'clear_cache'):
                renderer.clear_cache()
                print("[🔧 批量导出] ✅ 渲染缓存已清理")
        except Exception as e:
            print(f"[🔧 批量导出] ⚠️ 缓存清理失败: {e}")

        # 🔧 性能优化：不要清除绑定组历史！这会导致避重机制失效
        # 绑定组历史应该在整个导出过程中保持，这样才能真正避免重复
        # 只在用户明确要求"重置"时才清除
        print("[🔧 批量导出] ℹ️ 保持绑定组历史以确保避重机制有效")

        # 🔧 关键修复：重新分析所有绑定组的文件分类，确保使用最新的图层状态
        print(f"\n{'='*80}")
        print(f"[🔍 批量导出启动] 检查绑定管理器...")
        print(f"{'='*80}")

        if hasattr(self, 'binding_manager') and self.binding_manager:
            if hasattr(self, 'export_stage_updated'):
                self.export_stage_updated.emit("绑定检查")
            if _is_export_canceled():
                self._last_export_error = "导出已取消"
                self._is_batch_export_running = False
                return False
            print("[🔧 批量导出] ✅ 绑定管理器存在")
            print(f"[🔧 批量导出] 绑定组数量: {len(self.binding_manager.binding_groups)}")
            print("[🔧 批量导出] 🔄 重新分析绑定组文件分类...")

            for group_id, group in self.binding_manager.binding_groups.items():
                if _is_export_canceled():
                    self._last_export_error = "导出已取消"
                    self._is_batch_export_running = False
                    return False
                print(f"\n[🔧 批量导出] 处理绑定组: '{group.name}' (ID: {group_id})")
                print(f"  图层数: {len(group.layers)}")

                # 🔧 修复：不要清空绑定组的文件分类和避重历史
                # 这些信息应该在整个导出过程中保持，以确保绑定功能正常工作
                print(f"  保持现有分类（{len(group.file_categories)} 个）")
                print(f"  保持避重历史（{len(getattr(group, '_category_usage_history', {}))} 个记录）")

                # 🔧 修复：只在分类信息缺失时重新分析
                if not group.file_categories:
                    print(f"  分类信息缺失，重新分析文件...")
                    for idx, layer in enumerate(group.layers):
                        if _is_export_canceled():
                            self._last_export_error = "导出已取消"
                            self._is_batch_export_running = False
                            return False
                        print(f"  分析图层 {idx}: {layer.name}")
                        print(f"    图层源: {layer.image_source}")
                        group._analyze_layer_files(layer, idx)
                else:
                    print(f"  分类信息完整，跳过重新分析")

                print(f"[🔧 批量导出] ✅ 绑定组 '{group.name}' 状态检查完成")
                print(f"  当前分类数: {len(group.file_categories)}")
                print(f"  分类列表: {list(group.file_categories.keys())}")
        else:
            print("[🔧 批量导出] ⚠️ 警告：没有绑定管理器或绑定管理器未启用")

        print(f"{'='*80}\n")

        # 🚀 第一步：完整的文档状态预分析
        if hasattr(self, 'export_stage_updated'):
            self.export_stage_updated.emit("文档分析")
        if _is_export_canceled():
            self._last_export_error = "导出已取消"
            self._is_batch_export_running = False
            return False
        print("[批量导出] 开始文档状态预分析...")
        document_analysis = self._analyze_document_for_export()

        # 从分析结果中提取关键信息
        binding_enabled = document_analysis['binding_enabled']
        binding_categories = document_analysis['binding_categories']
        layer_analysis = document_analysis['layer_analysis']
        export_mode = document_analysis['export_mode']

        print(f"[批量导出] 文档分析完成:")
        print(f"  - 导出模式: {export_mode}")
        print(f"  - 绑定状态: {binding_enabled}")
        print(f"  - 绑定分类: {len(binding_categories)} 个")
        print(f"  - 可见图层: {len(layer_analysis['visible_layers'])} 个")
        print(f"  - 绑定图层: {len(layer_analysis['bound_layers'])} 个")

        # 🚀 第二步：强制使用预计算优化导出系统 - 屏蔽所有旧版导出
        print(f"[批量导出] 强制使用预计算优化导出系统（屏蔽旧版导出）")

        try:
            from app.utils.optimized_batch_executor import export_batch_with_precomputation_v2

            # 创建进度回调包装器
            def progress_wrapper(current_count):
                # 优化批量执行器现在直接传递当前完成数量
                if hasattr(self, 'export_progress_updated'):
                    self.export_progress_updated.emit(current_count)

            def file_completed_wrapper(message):
                if hasattr(self, 'file_exported'):
                    self.file_exported.emit(message)

            def stage_wrapper(stage_name):
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit(str(stage_name))

            def cancel_wrapper():
                return getattr(self, '_export_canceled', False) or (cancel_callback and cancel_callback())

            # 🔧 强制使用预计算导出，无论数量多少
            success = export_batch_with_precomputation_v2(
                document=self,
                document_analysis=document_analysis,  # 传递预分析结果
                directory=directory,
                count=count,
                filename_template=filename_template or "image_{number:04d}",
                file_format=file_format,
                start_index=start_index,
                progress_callback=progress_wrapper,
                file_completed_callback=file_completed_wrapper,
                stage_callback=stage_wrapper,
                cancel_callback=cancel_wrapper,
                traverse_mode=traverse_mode,
                avoid_duplicates=use_smart_sampling
            )

            if success:
                print(f"[批量导出] 预计算导出成功完成")
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("收尾清理")
                self._is_batch_export_running = False
                # 🔧 关键修复：清理所有图层的临时状态
                self._cleanup_layers_after_export()
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("导出完成")
                return True
            else:
                print(f"[批量导出] 预计算导出失败")
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("收尾清理")
                self._is_batch_export_running = False
                # 🔧 关键修复：清理所有图层的临时状态
                self._cleanup_layers_after_export()
                if hasattr(self, 'export_stage_updated'):
                    self.export_stage_updated.emit("导出失败")
                return False

        except Exception as e:
            print(f"[批量导出] 预计算导出异常: {e}")
            import traceback
            traceback.print_exc()
            if hasattr(self, 'export_stage_updated'):
                self.export_stage_updated.emit("导出异常")
            self._is_batch_export_running = False
            # 🔧 关键修复：清理所有图层的临时状态
            self._cleanup_layers_after_export()
            return False

    def _clear_layer_temporary_states(self):
        """加载文档后清理所有图层的临时状态"""
        try:
            from app.utils.layer_tree import is_layer_group
            cleared_count = 0
            for layer in self.layers:
                if is_layer_group(layer):
                    continue
                # 清理随机变换状态
                if hasattr(layer, '_current_random_offset_x'):
                    layer._current_random_offset_x = 0
                if hasattr(layer, '_current_random_offset_y'):
                    layer._current_random_offset_y = 0
                if hasattr(layer, '_current_random_scale'):
                    layer._current_random_scale = 1.0
                if hasattr(layer, '_current_random_rotation'):
                    layer._current_random_rotation = 0.0
                # 加载文档后清理 current_image_path（它是本次会话的临时状态）
                if hasattr(layer, '_current_image_path'):
                    layer._current_image_path = None
                if hasattr(layer, 'current_image_path'):
                    layer.current_image_path = None
                cleared_count += 1
            print(f"[批量导出] ✅ 清理了 {cleared_count} 个图层的临时状态")
        except Exception:
            logger.debug("静默异常已忽略: except Exception: in document_export_batch.py")
            pass

    def _cleanup_layers_after_export(self):
        """批量导出完成后清理所有图层的临时状态"""
        try:
            from app.utils.layer_tree import is_layer_group
            cleared_count = 0
            for layer in self.layers:
                if is_layer_group(layer):
                    continue
                # 不重置 _current_image_path（保留本次导出用的图，便于审计/重导）
                if hasattr(layer, '_cached_image'):
                    layer._cached_image = None
                if hasattr(layer, '_cached_image_path'):
                    layer._cached_image_path = None
                # 重置随机变换状态
                if hasattr(layer, '_current_random_offset_x'):
                    layer._current_random_offset_x = 0
                if hasattr(layer, '_current_random_offset_y'):
                    layer._current_random_offset_y = 0
                if hasattr(layer, '_current_random_scale'):
                    layer._current_random_scale = 1.0
                if hasattr(layer, '_current_random_rotation'):
                    layer._current_random_rotation = 0.0
                cleared_count += 1

            # 让后续预览/导出重新走完整渲染
            self._invalidate_render_cache()

            print(f"[批量导出] ✅ 导出后清理 {cleared_count} 个图层的临时状态")
        except Exception:
            logger.debug("静默异常已忽略: except Exception: in document_export_batch.py")
            pass

    def cancel_export(self):
        """取消正在进行的批量导出"""
        try:
            self._export_canceled = True
            # 取消活动执行器/预计算器（兼容旧路径）
            coordinator = getattr(self, '_export_coordinator', None)
            if coordinator is not None and hasattr(coordinator, 'cancel'):
                try:
                    coordinator.cancel()
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in document_export_batch.py")
            precomputer = getattr(self, '_batch_precomputer_v2', None)
            if precomputer is not None and hasattr(precomputer, 'cancel'):
                try:
                    precomputer.cancel()
                except Exception:
                    logger.debug("静默异常已忽略: except Exception: in document_export_batch.py")
            print("[批量导出] 🛑 收到取消信号")
        except Exception:
            logger.debug("静默异常已忽略: except Exception: in document_export_batch.py")
            pass
