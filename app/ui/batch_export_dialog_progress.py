# -*- coding: utf-8 -*-
"""BatchExportDialog 方法 mixin：由拆分脚本生成，方法原属于 BatchExportDialog。"""
import logging

logger = logging.getLogger(__name__)
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QSpinBox, QLineEdit, QFormLayout,
                           QFileDialog, QDialogButtonBox, QComboBox, QCheckBox, QGroupBox, QMessageBox,
                           QInputDialog, QListWidget, QProgressBar, QListWidgetItem, QAbstractItemView, QWidget, QGridLayout,
                           QDoubleSpinBox)
from PySide6.QtCore import Qt, QMetaObject, Q_ARG, Slot, QTimer, QSettings, QRunnable, QThreadPool
import shiboken6
import datetime
import re
import os
import json
import time


class _BatchExportTask(QRunnable):
    """Run one batch export without touching Qt widgets from the worker thread."""

    def __init__(self, callback):
        super().__init__()
        self._callback = callback
        self.setAutoDelete(True)

    def run(self):
        self._callback()


class BatchExportDialogProgressMixin:

    def build_export_request(self):
        """Capture UI export settings into a plain dict for background workers."""
        output_dir = self._resolved_export_directory()
        if not output_dir:
            return None, "请选择导出目录"

        is_traverse_mode = self.traverse_export_check.isChecked()
        if is_traverse_mode:
            try:
                count = self.document._calculate_possible_combinations()
                if count <= 0:
                    return None, "没有可导出的组合"
            except Exception as e:
                return None, f"无法计算组合数量: {str(e)}"
        else:
            count = self.count_spin.value()
            if count <= 0:
                return None, "导出数量必须大于0"

        filename_template = self.get_filename_template()
        if not filename_template:
            return None, "请输入文件名模板"

        format_map = {0: 'png', 1: 'jpg', 2: 'bmp'}
        return {
            'directory': output_dir,
            'count': int(count),
            'filename_template': filename_template,
            'format_name': format_map.get(self.format_combo.currentIndex(), 'png'),
            'traverse_mode': bool(is_traverse_mode),
            'use_smart_sampling': bool(self.smart_sampling_check.isChecked()),
        }, ""

    @staticmethod
    def execute_export_request(document, request, cancel_callback=None):
        """Execute a captured export request without reading QWidget state."""
        if not isinstance(request, dict):
            return False

        output_dir = str(request.get('directory') or '').strip()
        if not output_dir:
            return False
        if not os.path.isdir(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        return document.batch_export(
            output_dir,
            int(request.get('count', 0) or 0),
            str(request.get('filename_template') or ''),
            str(request.get('format_name') or 'png'),
            start_index=1,
            cancel_callback=cancel_callback,
            use_high_performance=True,
            traverse_mode=bool(request.get('traverse_mode', False)),
            use_smart_sampling=bool(request.get('use_smart_sampling', True))
        )

    def _on_export_confirmed(self):
        """确认导出（由“确定”按钮触发，不关闭对话框）。

        注意：QDialog.accept() 在 PySide6 中是 C++ 槽，Python 端重写的 accept()
        无法覆盖其关闭对话框的默认行为，因此将导出确认逻辑放在独立方法中，
        由 ActionRole 的自定义按钮通过 clicked 信号调用。
        """
        directory = self._resolved_export_directory()
        if not directory:
            return

        # 如果目录不存在，尝试创建
        try:
            if not os.path.exists(directory):
                os.makedirs(directory)
                print(f"已创建导出目录: {directory}")
        except Exception as e:
            QMessageBox.warning(self, "错误", f"无法创建目录: {directory}\n错误: {str(e)}")
            return

        # 保存当前设置
        self.save_settings()

        # 开始批量导出
        self.start_export()

    def reject(self):
        """取消导出"""
        # 保存当前设置（即使取消也保存设置，这样下次打开仍能记住）
        self.save_settings()

        super().reject()

    def _notify_non_blocking(self, message, timeout_ms=6000):
        """非阻塞提示：优先状态栏，不弹阻塞对话框"""
        try:
            root = self.window()
            if root is not None and hasattr(root, 'statusBar'):
                status_bar = root.statusBar()
                if status_bar is not None:
                    status_bar.showMessage(str(message), int(timeout_ms))
        except Exception:
            logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
            pass

    def _get_main_window(self):
        """向上查找主窗口对象"""
        parent = self.parentWidget()
        if parent is None:
            try:
                parent = super().parent()
            except Exception:
                parent = self._host_parent
        while parent:
            if hasattr(parent, 'tab_widget') and hasattr(parent, 'document_manager'):
                return parent
            try:
                parent = parent.parent()
            except Exception:
                break
        return None

    def _set_tab_runtime_status(self, status_text):
        """更新当前文档标签页状态文本"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'set_document_runtime_status'):
            main_window.set_document_runtime_status(self.document, status_text)

    def _set_export_running_ui(self, running: bool, total: int = 0):
        """切换导出运行时UI状态"""
        self._export_running = bool(running)
        if running:
            self._export_total_count = max(1, int(total))
            self._export_started_at = time.time()
            self._last_exported_file_hint = ""
            self._progress_phase_hint = "预处理中"
            self._export_trace_path_announced = False
            self.progress_container.setVisible(True)
            self.progress_bar.setRange(0, self._export_total_count)
            self.progress_bar.setValue(0)
            self.progress_status_label.setText(self._build_progress_text(0, self._export_total_count))
            self._progress_refresh_timer.start()
            self.progress_cancel_btn.setEnabled(True)
            self.minimize_btn.setEnabled(True)
            self.ok_btn.setEnabled(False)
            self.button_box.button(QDialogButtonBox.Cancel).setEnabled(False)
            self._set_tab_runtime_status("正在批量导出")
            self._update_performance_diagnostics(clear_only=True)
        else:
            self.progress_cancel_btn.setEnabled(False)
            self.minimize_btn.setEnabled(False)
            self.ok_btn.setEnabled(True)
            self.button_box.button(QDialogButtonBox.Cancel).setEnabled(True)
            self._export_total_count = 0
            self._export_started_at = None
            self._last_exported_file_hint = ""
            self._progress_phase_hint = "准备导出"
            self._progress_refresh_timer.stop()
            self._set_tab_runtime_status("")

    def _format_duration(self, seconds: float) -> str:
        """将秒数格式化为 mm:ss 或 hh:mm:ss。"""
        total = max(0, int(seconds))
        hours = total // 3600
        minutes = (total % 3600) // 60
        secs = total % 60
        if hours > 0:
            return f"{hours:02d}:{minutes:02d}:{secs:02d}"
        return f"{minutes:02d}:{secs:02d}"

    def _format_bytes(self, byte_count: int) -> str:
        """格式化字节数，用于导出诊断。"""
        try:
            size = float(max(0, int(byte_count or 0)))
        except Exception:
            size = 0.0
        units = ["B", "KB", "MB", "GB"]
        unit_idx = 0
        while size >= 1024.0 and unit_idx < len(units) - 1:
            size /= 1024.0
            unit_idx += 1
        if unit_idx == 0:
            return f"{int(size)} {units[unit_idx]}"
        return f"{size:.1f} {units[unit_idx]}"

    def _sanitize_progress_text(self, text: str) -> str:
        """清洗文件进度文案，避免显示异常前缀。"""
        if not text:
            return ""
        cleaned = str(text).strip()
        cleaned = cleaned.lstrip(":： ").strip()
        return cleaned

    def _build_progress_text(self, current: int, total: int) -> str:
        """构建实时进度文案：当前进度 + 已耗时 + 预计剩余。"""
        total = max(1, int(total))
        current = max(0, min(total, int(current)))
        progress = (current / total) * 100.0

        elapsed = 0.0
        if self._export_started_at:
            elapsed = max(0.0, time.time() - self._export_started_at)
        elapsed_text = self._format_duration(elapsed)

        speed = (current / elapsed) if elapsed > 0 and current > 0 else 0.0
        if speed > 0:
            eta = (total - current) / speed
            eta_text = self._format_duration(eta)
            speed_text = f"{speed:.2f} 张/秒"
        else:
            eta_text = "--:--"
            speed_text = "-- 张/秒"

        main_text = (
            f"{self._progress_phase_hint}... {current}/{total} ({progress:.1f}%)  |  "
            f"已耗时 {elapsed_text}  |  预计剩余 {eta_text}  |  速度 {speed_text}"
        )
        if self._last_exported_file_hint:
            return f"{main_text}\n当前文件：{self._last_exported_file_hint}"
        return main_text

    def _refresh_progress_display(self):
        """定时刷新导出文案，确保预处理阶段也实时更新。"""
        if not self._export_running:
            return
        try:
            total = max(1, self._export_total_count)
            current = self.progress_bar.value()
            self.progress_status_label.setText(self._build_progress_text(current, total))
            if not self._export_trace_path_announced:
                trace_file = str(getattr(self.document, '_export_debug_trace_file', '') or '')
                if trace_file:
                    self._notify_non_blocking(f"导出调试日志: {trace_file}", 7000)
                    self._export_trace_path_announced = True
        except Exception:
            logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
            pass

    def minimize_to_tab(self):
        """缩小到对应标签：隐藏窗口但保持后台导出"""
        if self._export_running:
            self._notify_non_blocking("已缩小到标签：导出任务仍在后台运行", 4000)
        self.hide()
        try:
            print(message)
        except Exception:
            logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
            pass

    def start_export(self):
        """开始导出图像"""
        # 验证输入
        directory = self._resolved_export_directory()
        if not directory:
            QMessageBox.warning(self, "验证错误", "请选择导出目录")
            return

        if not os.path.isdir(directory):
            try:
                os.makedirs(directory)
                print(f"已创建导出目录: {directory}")
            except Exception as e:
                QMessageBox.warning(self, "验证错误", f"无法创建导出目录: {e}")
                return

        # 根据导出模式确定数量
        is_traverse_mode = self.traverse_export_check.isChecked()
        if is_traverse_mode:
            # 遍历模式：计算所有可能的组合数量
            try:
                count = self.document._calculate_possible_combinations()
                if count <= 0:
                    QMessageBox.warning(self, "验证错误", "没有可导出的组合")
                    return
                print(f"遍历模式：将导出 {count} 个组合")
            except Exception as e:
                QMessageBox.warning(self, "验证错误", f"无法计算组合数量: {str(e)}")
                return
        else:
            # 随机模式：使用用户指定的数量
            count = self.count_spin.value()
            if count <= 0:
                QMessageBox.warning(self, "验证错误", "导出数量必须大于0")
                return

        filename_template = self.get_filename_template()
        if not filename_template:
            QMessageBox.warning(self, "验证错误", "请输入文件名模板")
            return

        # 获取输出格式
        format_map = {0: 'png', 1: 'jpg', 2: 'bmp'}
        format_name = format_map.get(self.format_combo.currentIndex(), 'png')
        export_request = {
            'directory': directory,
            'count': int(count),
            'filename_template': filename_template,
            'format_name': format_name,
            'traverse_mode': bool(is_traverse_mode),
            'use_smart_sampling': bool(self.smart_sampling_check.isChecked()),
        }

        # 保存设置
        self.save_settings()

        # 清理上一次导出调整信息，避免提示残留
        try:
            if hasattr(self.document, '_last_export_adjustment'):
                self.document._last_export_adjustment = None
        except Exception:
            logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
            pass

        # 设置导出中的UI状态（内嵌进度区）
        self._set_export_running_ui(True, count)
        debug_trace_enabled = bool(
            os.environ.get("BTPW_EXPORT_TRACE", "0") == "1"
            or bool(self.document.export_settings.get('export_debug_trace', False))
        )
        if debug_trace_enabled:
            self._notify_non_blocking("导出调试模式已开启，日志将写入本地文件。", 4000)

        # 连接文档的进度信号
        if hasattr(self.document, 'export_progress_updated'):
            self.document.export_progress_updated.connect(self.update_progress)
        if hasattr(self.document, 'file_exported'):
            self.document.file_exported.connect(self.update_progress_text)
        if hasattr(self.document, 'export_stage_updated'):
            self.document.export_stage_updated.connect(self.update_export_stage)

        # 创建取消标志
        self.export_canceled = False

        # 同时重置document的取消标志
        if hasattr(self.document, '_export_canceled'):
            self.document._export_canceled = False

        # 在后台线程中执行导出操作
        def export_thread():
            def _safe_invoke_export_completed(ok: bool, err: str):
                """对话框可能已被销毁，安全回调 UI。"""
                try:
                    if not shiboken6.isValid(self):
                        return
                except Exception:
                    return
                try:
                    QMetaObject.invokeMethod(
                        self, "export_completed",
                        Qt.QueuedConnection,
                        Q_ARG(bool, bool(ok)),
                        Q_ARG(str, str(err or ""))
                    )
                except RuntimeError:
                    return

            try:
                # 执行批量导出前检查
                if self.export_canceled:
                    _safe_invoke_export_completed(False, "导出已取消")
                    return

                # 定义取消检查函数
                def check_canceled():
                    return (self.export_canceled or
                           (hasattr(self.document, '_export_canceled') and self.document._export_canceled))

                # 🔧 关键修复：直接一次性导出所有图片，不再分批处理
                # 这样可以确保避重机制在整个导出过程中生效，避免批次间重复
                print(f"[批量导出] 🚀 开始一次性导出 {count} 张图片（不分批）")
                result = self.execute_export_request(
                    self.document,
                    export_request,
                    cancel_callback=check_canceled
                )

                # 根据导出结果通知UI
                if result:
                    _safe_invoke_export_completed(True, "")
                else:
                    err = ""
                    try:
                        if self.export_canceled or (hasattr(self.document, '_export_canceled') and self.document._export_canceled):
                            err = "导出已取消"
                        else:
                            err = getattr(self.document, '_last_export_error', '') or "导出失败"
                    except Exception:
                        err = "导出已取消" if self.export_canceled else "导出失败"
                    _safe_invoke_export_completed(False, err)
            except Exception as e:
                print(f"导出错误: {e}")
                import traceback
                traceback.print_exc()

                # 更新UI
                _safe_invoke_export_completed(False, str(e))

        # 使用 Qt 线程池执行，后台任务不访问 QWidget 状态。
        self.export_task = _BatchExportTask(export_thread)
        QThreadPool.globalInstance().start(self.export_task)

    def cancel_export(self):
        """取消导出操作"""
        # 防止重复取消
        if hasattr(self, '_canceling') and self._canceling:
            return

        self._canceling = True
        self.export_canceled = True

        # 同时设置document的取消标志
        if hasattr(self.document, '_export_canceled'):
            self.document._export_canceled = True

        # 调用document的取消方法
        if hasattr(self.document, 'cancel_export'):
            self.document.cancel_export()

        print("用户取消导出操作")
        self._progress_phase_hint = "正在取消"
        self.progress_cancel_btn.setEnabled(False)
        try:
            total = max(1, self._export_total_count)
            self.progress_status_label.setText(
                self._build_progress_text(self.progress_bar.value(), total)
            )
        except Exception:
            logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
            pass

        # 断开文档的进度信号连接
        if hasattr(self.document, 'export_progress_updated'):
            try:
                self.document.export_progress_updated.disconnect(self.update_progress)
            except:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass
        if hasattr(self.document, 'file_exported'):
            try:
                self.document.file_exported.disconnect(self.update_progress_text)
            except:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass
        if hasattr(self.document, 'export_stage_updated'):
            try:
                self.document.export_stage_updated.disconnect(self.update_export_stage)
            except:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass

    @Slot(int)
    def update_progress(self, value):
        """更新进度条"""
        if not self._export_running:
            return
        try:
            total = max(1, self._export_total_count)
            v = int(value)
            if 0 <= v <= total:
                current = v
            else:
                # 兼容百分比信号
                current = int(round(max(0, min(100, v)) * total / 100.0))
            self.progress_bar.setValue(max(0, min(total, current)))
            self._progress_phase_hint = "正在导出" if self.progress_bar.value() > 0 else "预处理中"
            self.progress_status_label.setText(
                self._build_progress_text(self.progress_bar.value(), total)
            )
        except Exception:
            logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
            pass

    @Slot(str)
    def update_progress_text(self, text):
        """更新进度文本"""
        if self._export_running:
            try:
                total = max(1, self._export_total_count)
                hint = self._sanitize_progress_text(text)
                self._last_exported_file_hint = hint
                if hint:
                    self._progress_phase_hint = "正在导出"
                self.progress_status_label.setText(
                    self._build_progress_text(self.progress_bar.value(), total)
                )
            except Exception:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass

    @Slot(str)
    def update_export_stage(self, stage_name):
        """实时更新当前阶段名称。"""
        if not self._export_running:
            return
        try:
            stage = str(stage_name).strip()
            if not stage:
                return
            self._progress_phase_hint = stage
            total = max(1, self._export_total_count)
            self.progress_status_label.setText(
                self._build_progress_text(self.progress_bar.value(), total)
            )
            if stage in ("汇总统计", "导出完成"):
                self._update_performance_diagnostics(clear_only=False)
        except Exception:
            logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
            pass

    def _update_performance_diagnostics(self, clear_only=False):
        """更新导出性能诊断面板"""
        if clear_only:
            self.diag_count_label.setText("数量: -")
            self.diag_precompute_label.setText("预计算耗时: -")
            self.diag_render_label.setText("渲染耗时: -")
            self.diag_io_label.setText("写盘耗时: -")
            self.diag_throughput_label.setText("总吞吐: -")
            self.diag_policy_label.setText("策略: -")
            self.diag_pipeline_label.setText("流水线: -")
            self.diag_save_label.setText("保存: -")
            self.diag_safety_label.setText("保护: -")
            self.diag_error_label.setText("结果: -")
            self.performance_diag_group.setVisible(False)
            return

        stats = getattr(self.document, '_last_export_perf_stats', None)
        if not stats or not isinstance(stats, dict):
            self.performance_diag_group.setVisible(False)
            return

        precompute_time = float(stats.get('precompute_time', 0.0) or 0.0)
        render_time = float(stats.get('render_time', 0.0) or 0.0)
        io_time = float(stats.get('io_time', 0.0) or 0.0)
        throughput = float(stats.get('throughput', 0.0) or 0.0)
        exported_count = int(stats.get('exported_count', 0) or 0)
        total_time = float(stats.get('total_time', 0.0) or 0.0)
        report = getattr(self.document, '_last_export_report', None)
        summary = report.get('summary', {}) if isinstance(report, dict) else {}
        context = report.get('context', {}) if isinstance(report, dict) else {}
        extra = report.get('extra', {}) if isinstance(report, dict) else {}
        scheduler = extra.get('scheduler', {}) if isinstance(extra, dict) else {}

        requested_count = int(summary.get('requested_count', 0) or 0)
        planned_count = int(summary.get('planned_count', 0) or 0)
        report_exported = int(summary.get('exported_count', 0) or 0)
        success = bool(summary.get('success', stats.get('success', False)))
        canceled = bool(summary.get('canceled', False))
        error_message = str(summary.get('error_message', '') or getattr(self.document, '_last_export_error', '') or '')

        quality_profile = str(stats.get('quality_profile', '') or 'quality')
        profile_name_map = {
            'quality': '质量优先',
            'balanced': '均衡',
            'speed': '极速',
            'size': '压缩体积',
        }
        quality_name = profile_name_map.get(quality_profile, quality_profile)
        backend = str(stats.get('export_backend', '') or 'pillow')
        io_profile = str(stats.get('io_profile', '') or 'balanced')
        file_format = str(context.get('file_format', '') or '')
        written_bytes = int(stats.get('written_bytes', 0) or 0)

        max_pipeline = int(stats.get('max_pipeline_backlog', scheduler.get('max_pipeline_backlog', 0)) or 0)
        max_render = int(stats.get('max_render_backlog', scheduler.get('max_render_backlog', 0)) or 0)
        max_save = int(stats.get('max_save_backlog', scheduler.get('max_save_backlog', 0)) or 0)
        backpressure = int(stats.get('queue_backpressure_events', scheduler.get('queue_backpressure_events', 0)) or 0)
        scheduler_adjustments = int(stats.get('scheduler_adjustments', scheduler.get('adjustments', 0)) or 0)
        final_limit = int(stats.get('final_in_flight_limit', scheduler.get('final_in_flight_limit', 0)) or 0)
        io_workers = int(stats.get('io_workers', scheduler.get('io_workers', 0)) or 0)

        pillow_count = int(stats.get('pillow_save_count', 0) or 0)
        vips_count = int(stats.get('vips_save_count', 0) or 0)
        save_errors = int(stats.get('save_error_count', 0) or 0)
        service_time = float(stats.get('export_service_time', 0.0) or 0.0)
        preload_unique = int(stats.get('preload_unique_images', 0) or 0)
        preload_loaded = int(stats.get('preload_loaded_images', 0) or 0)
        preload_memory = float(stats.get('preload_memory_mb', 0.0) or 0.0)
        preload_skipped = int(stats.get('preload_skipped_by_memory', 0) or 0)

        safety_timeout = int(stats.get('safety_stopped_by_timeout', 0) or 0)
        safety_failures = int(stats.get('safety_stopped_by_failures', 0) or 0)
        safety_throttle = int(stats.get('safety_throttle_events', 0) or 0)
        memory_mode = str(stats.get('memory_guard_mode', '') or 'auto')
        memory_limit = float(stats.get('memory_limit_mb', 0.0) or 0.0)
        memory_peak = float(stats.get('memory_peak_mb', 0.0) or 0.0)
        memory_soft = int(stats.get('memory_soft_throttle_events', 0) or 0)
        memory_hard = int(stats.get('memory_hard_throttle_events', 0) or 0)
        memory_wait = float(stats.get('memory_wait_seconds', 0.0) or 0.0)
        memory_clears = int(stats.get('memory_cache_clear_events', 0) or 0)
        worker_seed = int(stats.get('worker_document_seed_available', 0) or 0)
        shared_renders = int(stats.get('shared_document_render_count', 0) or 0)
        worker_failures = int(stats.get('worker_document_create_failures', 0) or 0)
        mutation_warnings = int(stats.get('main_document_mutation_warnings', 0) or 0)
        safety_text = f"限流 {safety_throttle} 次"
        if safety_timeout:
            safety_text += "，超时保护触发"
        if safety_failures:
            safety_text += "，失败保护触发"
        safety_text += f"，快照 {'可用' if worker_seed else '不可用'}"
        if shared_renders:
            safety_text += f"，共享文档渲染 {shared_renders} 次"
        if worker_failures:
            safety_text += f"，worker创建失败 {worker_failures} 次"
        if mutation_warnings:
            safety_text += f"，主文档变更警告 {mutation_warnings} 个"
        if memory_limit > 0:
            safety_text += (
                f"，内存 {memory_peak:.0f}/{memory_limit:.0f}MB"
                f"（{memory_mode}，软/硬限流 {memory_soft}/{memory_hard}，等待 {memory_wait:.1f}s，清缓存 {memory_clears}）"
            )

        shown_exported = report_exported if report_exported else exported_count
        requested_text = str(requested_count) if requested_count else "-"
        planned_text = str(planned_count) if planned_count else "-"
        self.diag_precompute_label.setText(f"预计算耗时: {precompute_time:.3f}s")
        self.diag_render_label.setText(f"渲染耗时: {render_time:.3f}s")
        self.diag_io_label.setText(f"写盘耗时: {io_time:.3f}s（服务层 {service_time:.3f}s）")
        self.diag_throughput_label.setText(f"总吞吐: {throughput:.2f} 张/秒（总耗时 {total_time:.3f}s）")
        self.diag_count_label.setText(
            f"数量: 请求 {requested_text} / 计划 {planned_text} / 完成 {shown_exported}"
        )
        self.diag_policy_label.setText(
            f"策略: {quality_name}，后端 {backend}，I/O {io_profile}，格式 {file_format or '-'}"
        )
        self.diag_pipeline_label.setText(
            f"流水线: 峰值 {max_pipeline}（渲染 {max_render} / 写盘 {max_save}），"
            f"最终在途 {final_limit}，I/O线程 {io_workers}，背压 {backpressure}，调度 {scheduler_adjustments}"
        )
        self.diag_save_label.setText(
            f"保存: Pillow {pillow_count} / pyvips {vips_count} / 失败 {save_errors}，写入 {self._format_bytes(written_bytes)}；"
            f"预读 {preload_loaded}/{preload_unique}，{preload_memory:.1f}MB，内存跳过 {preload_skipped}"
        )
        self.diag_safety_label.setText(f"保护: {safety_text}")
        if canceled:
            result_text = "已取消"
        elif success:
            result_text = "成功"
        else:
            result_text = f"失败：{error_message or '未知错误'}"
        self.diag_error_label.setText(f"结果: {result_text}")
        self.performance_diag_group.setVisible(True)

    @Slot(bool, str)
    def export_completed(self, success, error_message=""):
        """导出完成后的回调"""
        # 安全断开文档进度信号
        if hasattr(self.document, 'export_progress_updated'):
            try:
                self.document.export_progress_updated.disconnect(self.update_progress)
            except:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass
        if hasattr(self.document, 'file_exported'):
            try:
                self.document.file_exported.disconnect(self.update_progress_text)
            except:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass
        if hasattr(self.document, 'export_stage_updated'):
            try:
                self.document.export_stage_updated.disconnect(self.update_export_stage)
            except:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass
        self._set_export_running_ui(False)
        self._update_performance_diagnostics(clear_only=False)
        try:
            self.recommend_dynamic_budget_params()
        except Exception:
            logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
            pass

        # 启用按钮
        self.ok_btn.setEnabled(True)
        self.button_box.button(QDialogButtonBox.Cancel).setEnabled(True)

        if success:
            # 导出成功后保留窗口，便于查看阶段耗时与性能统计
            self._progress_phase_hint = "导出完成"
            try:
                perf = getattr(self.document, '_last_export_perf_stats', None) or {}
                if isinstance(perf, dict):
                    exported_count = int(perf.get('exported_count', 0) or 0)
                    total_time = float(perf.get('total_time', 0.0) or 0.0)
                    self.progress_bar.setValue(max(0, exported_count or self.progress_bar.value()))
                    self.progress_status_label.setText(
                        f"导出完成... {exported_count}/{max(1, exported_count)} (100.0%)  |  "
                        f"总耗时 {self._format_duration(total_time)}  |  "
                        f"预计算/渲染/写盘耗时请查看下方诊断面板"
                    )
            except Exception:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass
            message = f"导出完成：{self.path_edit.text()}"
            try:
                adj = getattr(self.document, '_last_export_adjustment', None)
                if adj and isinstance(adj, dict):
                    requested = adj.get('requested')
                    planned = adj.get('planned')
                    if requested and planned is not None and planned < requested:
                        message += f"（实际 {planned} / 请求 {requested}）"
                    reasons = [
                        str(reason).strip()
                        for reason in (adj.get('reasons') or [])
                        if str(reason).strip()
                    ]
                    if reasons:
                        message += f"；原因：{'；'.join(reasons[:2])}"
            except Exception:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass

            try:
                perf = getattr(self.document, '_last_export_perf_stats', None)
                if perf and isinstance(perf, dict):
                    tp = float(perf.get('throughput', 0.0) or 0.0)
                    pre = float(perf.get('precompute_time', 0.0) or 0.0)
                    rnd = float(perf.get('render_time', 0.0) or 0.0)
                    io = float(perf.get('io_time', 0.0) or 0.0)
                    message += f" | 吞吐 {tp:.2f}张/秒（预计算{pre:.2f}s 渲染{rnd:.2f}s 写盘{io:.2f}s）"
            except Exception:
                logger.debug("静默异常已忽略: except in ui/batch_export_dialog_progress.py")
                pass

            self._notify_non_blocking(message, 8000)
        else:
            self._progress_phase_hint = "导出失败"
            if error_message == "导出已取消":
                self._notify_non_blocking("导出已取消", 5000)
            else:
                self._notify_non_blocking(f"导出失败：{error_message}", 10000)

    def open_output_directory(self):
        """打开输出目录"""
        output_dir = self._resolved_export_directory()
        if output_dir and os.path.exists(output_dir):
            try:
                import subprocess
                import platform

                system = platform.system()
                if system == "Windows":
                    os.startfile(output_dir)
                elif system == "Darwin":  # macOS
                    subprocess.run(["open", output_dir])
                else:  # Linux
                    subprocess.run(["xdg-open", output_dir])

                print(f"已打开输出目录: {output_dir}")
            except Exception as e:
                print(f"无法打开目录: {e}")
                QMessageBox.warning(self, "错误", f"无法打开目录: {output_dir}\n错误: {str(e)}")
        else:
            QMessageBox.warning(self, "错误", f"目录不存在: {output_dir}")

    def closeEvent(self, event):
        """窗口关闭事件"""
        if self._export_running:
            # 导出期间仅隐藏窗口，不自动取消，避免误触关闭导致导出中断
            self.hide()
            self._notify_non_blocking("导出仍在后台进行，未取消。", 4000)
            event.ignore()
            return
        # 保存设置
        self.save_settings()
        event.accept()

    def apply_export_params(self, params):
        """应用外部设置的导出参数

        Args:
            params: 从ExportParamsTemplate获取的参数对象
        """
        if not params:
            return

        # 设置输出格式
        format_index = self.format_combo.findText(params.output_format)
        if format_index >= 0:
            self.format_combo.setCurrentIndex(format_index)

        # 设置质量
        if hasattr(self, 'quality_spin'):
            self.quality_spin.setValue(params.quality)

        # 设置尺寸调整
        if hasattr(self, 'resize_check'):
            self.resize_check.setChecked(params.resize_enabled)

        if hasattr(self, 'resize_width') and hasattr(self, 'resize_height'):
            self.resize_width.setValue(params.resize_width)
            self.resize_height.setValue(params.resize_height)

        # 设置自动裁剪
        if hasattr(self, 'auto_crop_check'):
            self.auto_crop_check.setChecked(params.auto_crop_enabled)

        # 设置宽高比
        if hasattr(self, 'maintain_ratio_check'):
            self.maintain_ratio_check.setChecked(params.maintain_aspect_ratio)

        # 设置文件名模式
        if hasattr(self, 'pattern_edit'):
            self.pattern_edit.setText(params.filename_pattern)

        # 设置索引起始值和填充
        if hasattr(self, 'index_start_spin'):
            self.index_start_spin.setValue(params.index_start)

        if hasattr(self, 'index_padding_spin'):
            self.index_padding_spin.setValue(params.index_padding)

        # 设置效果
        if hasattr(self, 'apply_effects_check'):
            self.apply_effects_check.setChecked(params.apply_effects)

        # 设置是否合并图层
        if hasattr(self, 'flatten_check'):
            self.flatten_check.setChecked(params.flatten_layers)

    def do_export(self):
        """执行导出操作但不显示对话框，用于多线程导出

        Returns:
            bool: 是否成功导出
        """
        try:
            request, error_message = self.build_export_request()
            if not request:
                if error_message:
                    print(error_message)
                return False

            def check_canceled():
                return (self.export_canceled or
                       (hasattr(self.document, '_export_canceled') and self.document._export_canceled))

            result = BatchExportDialog.execute_export_request(
                self.document,
                request,
                cancel_callback=check_canceled,
            )
            return result

        except Exception as e:
            print(f"导出失败: {str(e)}")
            import traceback
            traceback.print_exc()
            return False
