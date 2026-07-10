# -*- coding: utf-8 -*-
from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
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


class BatchExportDialogSettingsMixin:

    def _settings_store(self):
        return QSettings(self.SETTINGS_ORG, self.SETTINGS_APP)

    def _load_persisted_settings(self):
        try:
            raw = self._settings_store().value(self.SETTINGS_KEY, "", type=str)
            if not raw:
                return {}
            data = json.loads(raw)
            return data if isinstance(data, dict) else {}
        except Exception as e:
            print(f"读取批量导出持久化设置失败: {e}")
            return {}

    def _save_persisted_settings(self, settings):
        try:
            store = self._settings_store()
            store.setValue(self.SETTINGS_KEY, json.dumps(settings, ensure_ascii=False))
            store.sync()
        except Exception as e:
            print(f"保存批量导出持久化设置失败: {e}")

    def load_settings(self):
        """从document加载上一次的设置"""
        settings = {}
        document_settings = getattr(self.document, 'export_settings', {}) or {}
        settings.update(document_settings)
        persisted_settings = self._load_persisted_settings()
        has_document_export_config = bool(
            document_settings.get('batch_export_settings_saved')
            or document_settings.get('last_directory')
            or document_settings.get('directory')
        )
        if persisted_settings and not has_document_export_config:
            settings.update(persisted_settings)
        self.directory = settings.get('last_directory', self.directory)

        # 设置数量
        self.count_spin.setValue(settings.get('count', 10))

        # 日期设置
        self.use_date.setChecked(settings.get('use_date', True))
        self.date_format.setCurrentIndex(settings.get('date_format_index', 0))

        # 自定义文本
        self.custom_text.setText(settings.get('custom_text', 'export'))

        # 图层设置
        self.use_layer_name.setChecked(settings.get('use_layer_name', False))
        # 检查layer_index是否在有效范围内
        layer_index = settings.get('layer_index', 0)
        if 0 <= layer_index < self.layer_combo.count():
            self.layer_combo.setCurrentIndex(layer_index)

        # 序号格式
        number_format_index = settings.get('number_format_index', 0)
        if 0 <= number_format_index < self.number_format.count():
            self.number_format.setCurrentIndex(number_format_index)

        # 文件格式
        format_index = settings.get('format_index', 1)
        if 0 <= format_index < self.format_combo.count():
            self.format_combo.setCurrentIndex(format_index)

        # 最大文件大小（KB）
        self.max_file_size_spin.setValue(settings.get('max_file_size_kb', 299))
        if hasattr(self, 'quality_profile_combo'):
            profile = str(settings.get('export_quality_profile', 'quality') or 'quality')
            idx = self.quality_profile_combo.findData(profile)
            self.quality_profile_combo.setCurrentIndex(idx if idx >= 0 else 0)
        if not settings.get('export_backend'):
            settings['export_backend'] = 'pillow'

        if hasattr(self, 'memory_guard_combo'):
            memory_mode = str(settings.get('export_memory_guard_mode', 'auto') or 'auto')
            idx = self.memory_guard_combo.findData(memory_mode)
            self.memory_guard_combo.setCurrentIndex(idx if idx >= 0 else 0)
        if hasattr(self, 'memory_limit_spin'):
            self.memory_limit_spin.setValue(int(settings.get('export_memory_limit_mb', 4096) or 4096))
        if hasattr(self, 'memory_reserve_spin'):
            self.memory_reserve_spin.setValue(int(settings.get('export_memory_reserve_mb', 2048) or 2048))
        self._update_memory_guard_controls()

        if hasattr(self, 'use_current_time_for_path'):
            self.use_current_time_for_path.blockSignals(True)
            try:
                self.use_current_time_for_path.setChecked(settings.get('use_current_time_for_path', False))
            finally:
                self.use_current_time_for_path.blockSignals(False)

        if 'traverse_export' in settings:
            self.traverse_export_check.setChecked(bool(settings.get('traverse_export')))
        if 'smart_sampling' in settings:
            self.smart_sampling_check.setChecked(bool(settings.get('smart_sampling')))
        if 'unique_use_enabled' in settings:
            self.unique_use_enabled.setChecked(bool(settings.get('unique_use_enabled')))
            self._set_unique_checks_enabled(bool(settings.get('unique_use_enabled')))
        if 'unique_use_layers' in settings and isinstance(settings.get('unique_use_layers'), list):
            saved_unique_layers = {int(idx) for idx in settings.get('unique_use_layers', [])}
            for cb in getattr(self, 'unique_layer_checks', []):
                cb.setChecked(
                    bool(cb.property("unique_use_eligible"))
                    and int(cb.property("layer_index")) in saved_unique_layers
                )

        # 动态预算（默认自动）：不读取用户配置，不暴露手动调参
        self.dynamic_budget_enabled_check.setChecked(True)
        self.dynamic_budget_binding_check.setChecked(True)
        self.dynamic_budget_standard_check.setChecked(True)
        self.dynamic_budget_min_ratio_spin.setValue(0.8)
        self.dynamic_budget_max_ratio_spin.setValue(3.0)
        self.dynamic_budget_check_interval_spin.setValue(25)
        self.dynamic_budget_min_samples_spin.setValue(40)
        self.dynamic_budget_expand_step_spin.setValue(0.2)
        self.dynamic_budget_shrink_step_spin.setValue(0.1)
        self.dynamic_budget_low_success_spin.setValue(0.15)
        self.dynamic_budget_high_success_spin.setValue(0.65)
        self.dynamic_budget_high_duplicate_spin.setValue(0.75)
        self.dynamic_budget_low_duplicate_spin.setValue(0.30)
        self.dynamic_budget_recent_n_spin.setValue(12)
        self._set_dynamic_budget_controls_enabled(False)

        # 目录
        if self.directory:
            if hasattr(self, 'path_edit'):
                self.path_edit.setText(self.directory)
                if (
                    hasattr(self, 'use_current_time_for_path')
                    and self.use_current_time_for_path.isChecked()
                ):
                    self._apply_current_date_to_path_field()
            # 有目录时允许确定
            if hasattr(self, 'button_box'):
                self.ok_btn.setEnabled(True)

        # 更新预览
        self.update_preview()
        self.update_traverse_mode_display()

    def _collect_settings(self):
        """收集当前窗口设置。"""
        current_directory = self._current_directory_text()
        self.directory = current_directory
        return {
            'count': self.count_spin.value(),
            'use_date': self.use_date.isChecked(),
            'date_format_index': self.date_format.currentIndex(),
            'custom_text': self.custom_text.text(),
            'use_layer_name': self.use_layer_name.isChecked(),
            'layer_index': self.layer_combo.currentIndex(),
            'number_format_index': self.number_format.currentIndex(),
            'format_index': self.format_combo.currentIndex(),
            'last_directory': current_directory,
            'use_high_performance': True,
            'traverse_export': self.traverse_export_check.isChecked(),
            'smart_sampling': self.smart_sampling_check.isChecked(),
            'max_file_size_kb': self.max_file_size_spin.value(),
            'use_current_time_for_path': self.use_current_time_for_path.isChecked() if hasattr(self, 'use_current_time_for_path') else False,
            'export_quality_profile': self.quality_profile_combo.currentData() if hasattr(self, 'quality_profile_combo') else 'quality',
            'allow_lossy_size_reduction': bool(
                hasattr(self, 'quality_profile_combo')
                and self.quality_profile_combo.currentData() == 'size'
            ),
            'export_backend': 'pillow',
            # 性能策略改为程序自动调参（默认开启，不提供手动UI）
            'auto_runtime_tuning_enabled': True,
            'freeze_preview_during_export': True,
            'batch_preload_enabled': True,
            'export_memory_guard_mode': self.memory_guard_combo.currentData() if hasattr(self, 'memory_guard_combo') else 'auto',
            'export_memory_limit_mb': self.memory_limit_spin.value() if hasattr(self, 'memory_limit_spin') else 0,
            'export_memory_reserve_mb': self.memory_reserve_spin.value() if hasattr(self, 'memory_reserve_spin') else 2048,
            'unique_use_enabled': self.unique_use_enabled.isChecked(),
            'unique_use_layers': [
                int(cb.property("layer_index"))
                for cb in getattr(self, 'unique_layer_checks', [])
                if cb.isChecked() and bool(cb.property("unique_use_eligible"))
            ],
            # 动态预算（默认自动，固定开启）
            'dynamic_budget_enabled': True,
            'dynamic_budget_binding_enabled': True,
            'dynamic_budget_standard_enabled': True,
            'dynamic_budget_recent_n': 12,
            'batch_export_settings_saved': True,
        }

    def save_settings(self, mark_document=False):
        """保存当前设置到document和本机持久化配置。"""
        self.update_directory()
        settings = self._collect_settings()
        self.document.export_settings.update(settings)
        self._save_persisted_settings(settings)
        if mark_document:
            try:
                if hasattr(self.document, "set_modified"):
                    self.document.set_modified(True)
                else:
                    self.document.is_modified = True
            except Exception:
                logger.warning("静默异常已忽略: except in ui/batch_export_dialog_settings.py", exc_info=True)
                pass

    def save_config(self):
        """保存当前设置到当前标签页"""
        # 直接保存设置到document
        self.save_settings(mark_document=True)
        try:
            if hasattr(self.document, 'save_state'):
                self.document.save_state("保存批量导出设置")
        except Exception:
            logger.warning("静默异常已忽略: except in ui/batch_export_dialog_settings.py", exc_info=True)
            pass

        # 显示简短的保存成功提示
        QMessageBox.information(self, "成功", "设置已保存，并会在下次打开批量导出窗口时恢复")

    def apply_config(self, settings):
        """应用加载的配置设置"""
        # 导出数量
        if 'count' in settings:
            self.count_spin.setValue(settings['count'])

        # 日期设置
        if 'use_date' in settings:
            self.use_date.setChecked(settings['use_date'])

        # 日期格式
        if 'date_format_index' in settings:
            date_format_index = settings['date_format_index']
            if 0 <= date_format_index < self.date_format.count():
                self.date_format.setCurrentIndex(date_format_index)

        # 自定义文本
        if 'custom_text' in settings:
            self.custom_text.setText(settings['custom_text'])

        # 图层名称设置
        if 'use_layer_name' in settings:
            self.use_layer_name.setChecked(settings['use_layer_name'])

        # 图层索引
        if 'layer_index' in settings and 'use_layer_name' in settings and settings['use_layer_name']:
            layer_index = settings['layer_index']
            if 0 <= layer_index < self.layer_combo.count():
                self.layer_combo.setCurrentIndex(layer_index)

        # 序号格式
        if 'number_format_index' in settings:
            number_format_index = settings['number_format_index']
            if 0 <= number_format_index < self.number_format.count():
                self.number_format.setCurrentIndex(number_format_index)

        # 导出格式
        if 'format_index' in settings:
            format_index = settings['format_index']
            if 0 <= format_index < self.format_combo.count():
                self.format_combo.setCurrentIndex(format_index)

        if 'export_quality_profile' in settings and hasattr(self, 'quality_profile_combo'):
            idx = self.quality_profile_combo.findData(str(settings.get('export_quality_profile') or 'quality'))
            if idx >= 0:
                self.quality_profile_combo.setCurrentIndex(idx)

        # 目录
        if 'last_directory' in settings and settings['last_directory']:
            self.directory = settings['last_directory']
            if hasattr(self, 'path_edit'):
                self.path_edit.setText(self.directory)
                if (
                    hasattr(self, 'use_current_time_for_path')
                    and self.use_current_time_for_path.isChecked()
                ):
                    self._apply_current_date_to_path_field()
            if hasattr(self, 'button_box'):
                self.ok_btn.setEnabled(True)

        # 最大文件大小（KB）
        if 'max_file_size_kb' in settings:
            self.max_file_size_spin.setValue(settings['max_file_size_kb'])

        if 'use_current_time_for_path' in settings and hasattr(self, 'use_current_time_for_path'):
            self.use_current_time_for_path.setChecked(bool(settings['use_current_time_for_path']))

        if hasattr(self, 'memory_guard_combo'):
            memory_mode = str(settings.get('export_memory_guard_mode', 'auto') or 'auto')
            idx = self.memory_guard_combo.findData(memory_mode)
            self.memory_guard_combo.setCurrentIndex(idx if idx >= 0 else 0)
        if 'export_memory_limit_mb' in settings and hasattr(self, 'memory_limit_spin'):
            self.memory_limit_spin.setValue(int(settings.get('export_memory_limit_mb') or 4096))
        if 'export_memory_reserve_mb' in settings and hasattr(self, 'memory_reserve_spin'):
            self.memory_reserve_spin.setValue(int(settings.get('export_memory_reserve_mb') or 2048))
        self._update_memory_guard_controls()

        # 动态预算（默认自动）：强制回归默认，不应用外部自定义参数
        self.dynamic_budget_enabled_check.setChecked(True)
        self.dynamic_budget_binding_check.setChecked(True)
        self.dynamic_budget_standard_check.setChecked(True)
        self.dynamic_budget_min_ratio_spin.setValue(0.8)
        self.dynamic_budget_max_ratio_spin.setValue(3.0)
        self.dynamic_budget_check_interval_spin.setValue(25)
        self.dynamic_budget_min_samples_spin.setValue(40)
        self.dynamic_budget_expand_step_spin.setValue(0.2)
        self.dynamic_budget_shrink_step_spin.setValue(0.1)
        self.dynamic_budget_low_success_spin.setValue(0.15)
        self.dynamic_budget_high_success_spin.setValue(0.65)
        self.dynamic_budget_high_duplicate_spin.setValue(0.75)
        self.dynamic_budget_low_duplicate_spin.setValue(0.30)
        self.dynamic_budget_recent_n_spin.setValue(12)
        self._set_dynamic_budget_controls_enabled(False)

        # 遍历导出模式
        if 'traverse_export' in settings:
            self.traverse_export_check.setChecked(settings['traverse_export'])
        else:
            # 默认不启用遍历导出
            self.traverse_export_check.setChecked(False)

        # 智能采样模式
        if 'smart_sampling' in settings:
            self.smart_sampling_check.setChecked(settings['smart_sampling'])
        else:
            # 默认启用智能采样
            self.smart_sampling_check.setChecked(True)

        # 图像唯一使用设置
        if 'unique_use_enabled' in settings:
            self.unique_use_enabled.setChecked(settings['unique_use_enabled'])
            self._set_unique_checks_enabled(bool(settings['unique_use_enabled']))
        if 'unique_use_layers' in settings and isinstance(settings['unique_use_layers'], list):
            for cb in getattr(self, 'unique_layer_checks', []):
                cb.setChecked(False)
            for idx in settings['unique_use_layers']:
                for cb in getattr(self, 'unique_layer_checks', []):
                    if int(cb.property("layer_index")) == idx and bool(cb.property("unique_use_eligible")):
                        cb.setChecked(True)
                        break

        # 更新预览
        self.update_preview()

        # 更新遍历模式显示
        self.update_traverse_mode_display()

    def _current_directory_text(self):
        """获取当前导出目录文本，优先使用输入框中的最新值。"""
        if hasattr(self, 'path_edit'):
            return self.path_edit.text().strip()
        return str(self.directory or '').strip()