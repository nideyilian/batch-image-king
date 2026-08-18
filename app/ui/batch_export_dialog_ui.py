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


def _set_semantic_status(widget, status=None):
    widget.setProperty("status", status)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


class BatchExportDialogUiMixin:


    def setup_ui(self):
        self.setProperty("role", "dialog")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        form_layout = QFormLayout()
        form_layout.setVerticalSpacing(8)

        # 基础导出参数（单行）：导出数量 + 导出格式 + 最大文件大小
        basic_export_layout = QHBoxLayout()
        basic_export_layout.setContentsMargins(0, 0, 0, 0)
        basic_export_layout.setSpacing(12)

        basic_export_layout.addWidget(QLabel("导出数量:"))
        self.count_spin = QSpinBox()
        self.count_spin.setRange(1, 100000)
        self.count_spin.setValue(10)
        self.count_spin.setToolTip("要导出的图像数量")
        basic_export_layout.addWidget(self.count_spin)

        self.calculated_count_label = QLabel("")
        self.calculated_count_label.setProperty("role", "status-value")
        _set_semantic_status(self.calculated_count_label, "info")
        basic_export_layout.addWidget(self.calculated_count_label)

        basic_export_layout.addSpacing(8)
        basic_export_layout.addWidget(QLabel("导出格式:"))
        self.format_combo = QComboBox()
        self.format_combo.addItem("PNG (*.png)")
        self.format_combo.addItem("JPEG (*.jpg)")
        self.format_combo.addItem("BMP (*.bmp)")
        self.format_combo.setCurrentIndex(1)
        basic_export_layout.addWidget(self.format_combo)

        basic_export_layout.addSpacing(8)
        basic_export_layout.addWidget(QLabel("最大文件大小(KB):"))
        self.max_file_size_spin = QSpinBox()
        self.max_file_size_spin.setRange(0, 102400)
        self.max_file_size_spin.setValue(299)
        self.max_file_size_spin.setToolTip("导出图片的最大文件大小（单位KB，0表示不限制）")
        basic_export_layout.addWidget(self.max_file_size_spin)
        hint = QLabel("0 表示不限制")
        hint.setProperty("role", "muted")
        basic_export_layout.addWidget(hint)

        basic_export_layout.addSpacing(8)
        basic_export_layout.addWidget(QLabel("质量策略:"))
        self.quality_profile_combo = QComboBox()
        self.quality_profile_combo.addItem("质量优先", "quality")
        self.quality_profile_combo.addItem("均衡", "balanced")
        self.quality_profile_combo.addItem("极速", "speed")
        self.quality_profile_combo.addItem("压缩体积", "size")
        self.quality_profile_combo.setCurrentIndex(0)
        self.quality_profile_combo.setToolTip("默认质量优先；只要设置了最大文件大小，所有质量策略都会优先遵循该上限。")
        basic_export_layout.addWidget(self.quality_profile_combo)
        basic_export_layout.addStretch()

        form_layout.addRow(basic_export_layout)

        memory_group = QGroupBox("内存保护")
        memory_layout = QHBoxLayout(memory_group)
        memory_layout.setContentsMargins(8, 8, 8, 8)
        memory_layout.setSpacing(10)
        memory_layout.addWidget(QLabel("模式:"))
        self.memory_guard_combo = QComboBox()
        self.memory_guard_combo.addItem("自动", "auto")
        self.memory_guard_combo.addItem("低内存", "low")
        self.memory_guard_combo.addItem("自定义", "custom")
        self.memory_guard_combo.addItem("关闭", "off")
        self.memory_guard_combo.setToolTip("自动会按系统剩余内存限速；低内存会关闭预读并降低并发；自定义可指定进程内存上限。")
        self.memory_guard_combo.currentIndexChanged.connect(self._update_memory_guard_controls)
        memory_layout.addWidget(self.memory_guard_combo)

        memory_layout.addWidget(QLabel("最大内存(MB):"))
        self.memory_limit_spin = QSpinBox()
        self.memory_limit_spin.setRange(512, 131072)
        self.memory_limit_spin.setSingleStep(256)
        self.memory_limit_spin.setValue(4096)
        self.memory_limit_spin.setToolTip("仅自定义模式生效。若低于程序当前基线，会自动按最低并发继续导出。")
        memory_layout.addWidget(self.memory_limit_spin)

        memory_layout.addWidget(QLabel("系统预留(MB):"))
        self.memory_reserve_spin = QSpinBox()
        self.memory_reserve_spin.setRange(512, 65536)
        self.memory_reserve_spin.setSingleStep(256)
        self.memory_reserve_spin.setValue(2048)
        self.memory_reserve_spin.setToolTip("自动和低内存模式会尽量给系统保留这部分内存，避免导出时拖慢系统。")
        memory_layout.addWidget(self.memory_reserve_spin)
        memory_layout.addStretch()
        form_layout.addRow(memory_group)

        # 动态预算（迭代3）
        self.dynamic_budget_group = QGroupBox("动态尝试预算（迭代3）")
        dynamic_layout = QVBoxLayout(self.dynamic_budget_group)
        dynamic_layout.setContentsMargins(8, 8, 8, 8)
        dynamic_layout.setSpacing(6)

        self.dynamic_budget_enabled_check = QCheckBox("启用动态预算（按实时成功率/重复率自动扩缩尝试上限）")
        dynamic_layout.addWidget(self.dynamic_budget_enabled_check)

        mode_row = QHBoxLayout()
        mode_row.setContentsMargins(12, 0, 0, 0)
        mode_row.setSpacing(10)
        self.dynamic_budget_binding_check = QCheckBox("绑定模式")
        self.dynamic_budget_standard_check = QCheckBox("标准模式")
        self.dynamic_budget_binding_check.setChecked(True)
        self.dynamic_budget_standard_check.setChecked(True)
        mode_row.addWidget(QLabel("作用模式:"))
        mode_row.addWidget(self.dynamic_budget_binding_check)
        mode_row.addWidget(self.dynamic_budget_standard_check)
        mode_row.addStretch()
        dynamic_layout.addLayout(mode_row)

        self.dynamic_budget_params_container = QWidget()
        params_layout = QGridLayout(self.dynamic_budget_params_container)
        params_layout.setContentsMargins(12, 0, 0, 0)
        params_layout.setHorizontalSpacing(10)
        params_layout.setVerticalSpacing(4)

        self.dynamic_budget_min_ratio_spin = QDoubleSpinBox()
        self.dynamic_budget_min_ratio_spin.setRange(0.2, 2.0)
        self.dynamic_budget_min_ratio_spin.setSingleStep(0.1)
        self.dynamic_budget_min_ratio_spin.setDecimals(2)
        self.dynamic_budget_min_ratio_spin.setValue(0.8)

        self.dynamic_budget_max_ratio_spin = QDoubleSpinBox()
        self.dynamic_budget_max_ratio_spin.setRange(1.0, 10.0)
        self.dynamic_budget_max_ratio_spin.setSingleStep(0.1)
        self.dynamic_budget_max_ratio_spin.setDecimals(2)
        self.dynamic_budget_max_ratio_spin.setValue(3.0)

        self.dynamic_budget_check_interval_spin = QSpinBox()
        self.dynamic_budget_check_interval_spin.setRange(5, 500)
        self.dynamic_budget_check_interval_spin.setValue(25)
        self.dynamic_budget_min_samples_spin = QSpinBox()
        self.dynamic_budget_min_samples_spin.setRange(10, 1000)
        self.dynamic_budget_min_samples_spin.setValue(40)

        self.dynamic_budget_expand_step_spin = QDoubleSpinBox()
        self.dynamic_budget_expand_step_spin.setRange(0.05, 1.0)
        self.dynamic_budget_expand_step_spin.setSingleStep(0.05)
        self.dynamic_budget_expand_step_spin.setDecimals(2)
        self.dynamic_budget_expand_step_spin.setValue(0.2)

        self.dynamic_budget_shrink_step_spin = QDoubleSpinBox()
        self.dynamic_budget_shrink_step_spin.setRange(0.01, 0.5)
        self.dynamic_budget_shrink_step_spin.setSingleStep(0.01)
        self.dynamic_budget_shrink_step_spin.setDecimals(2)
        self.dynamic_budget_shrink_step_spin.setValue(0.1)

        self.dynamic_budget_low_success_spin = QDoubleSpinBox()
        self.dynamic_budget_low_success_spin.setRange(0.01, 0.9)
        self.dynamic_budget_low_success_spin.setSingleStep(0.01)
        self.dynamic_budget_low_success_spin.setDecimals(2)
        self.dynamic_budget_low_success_spin.setValue(0.15)

        self.dynamic_budget_high_success_spin = QDoubleSpinBox()
        self.dynamic_budget_high_success_spin.setRange(0.1, 1.0)
        self.dynamic_budget_high_success_spin.setSingleStep(0.01)
        self.dynamic_budget_high_success_spin.setDecimals(2)
        self.dynamic_budget_high_success_spin.setValue(0.65)

        self.dynamic_budget_high_duplicate_spin = QDoubleSpinBox()
        self.dynamic_budget_high_duplicate_spin.setRange(0.1, 1.0)
        self.dynamic_budget_high_duplicate_spin.setSingleStep(0.01)
        self.dynamic_budget_high_duplicate_spin.setDecimals(2)
        self.dynamic_budget_high_duplicate_spin.setValue(0.75)

        self.dynamic_budget_low_duplicate_spin = QDoubleSpinBox()
        self.dynamic_budget_low_duplicate_spin.setRange(0.0, 0.9)
        self.dynamic_budget_low_duplicate_spin.setSingleStep(0.01)
        self.dynamic_budget_low_duplicate_spin.setDecimals(2)
        self.dynamic_budget_low_duplicate_spin.setValue(0.30)

        params_layout.addWidget(QLabel("预算下限比:"), 0, 0)
        params_layout.addWidget(self.dynamic_budget_min_ratio_spin, 0, 1)
        params_layout.addWidget(QLabel("预算上限比:"), 0, 2)
        params_layout.addWidget(self.dynamic_budget_max_ratio_spin, 0, 3)
        params_layout.addWidget(QLabel("检查间隔:"), 1, 0)
        params_layout.addWidget(self.dynamic_budget_check_interval_spin, 1, 1)
        params_layout.addWidget(QLabel("最小样本:"), 1, 2)
        params_layout.addWidget(self.dynamic_budget_min_samples_spin, 1, 3)
        params_layout.addWidget(QLabel("扩容步长:"), 2, 0)
        params_layout.addWidget(self.dynamic_budget_expand_step_spin, 2, 1)
        params_layout.addWidget(QLabel("收缩步长:"), 2, 2)
        params_layout.addWidget(self.dynamic_budget_shrink_step_spin, 2, 3)
        params_layout.addWidget(QLabel("低成功率阈值:"), 3, 0)
        params_layout.addWidget(self.dynamic_budget_low_success_spin, 3, 1)
        params_layout.addWidget(QLabel("高成功率阈值:"), 3, 2)
        params_layout.addWidget(self.dynamic_budget_high_success_spin, 3, 3)
        params_layout.addWidget(QLabel("高重复率阈值:"), 4, 0)
        params_layout.addWidget(self.dynamic_budget_high_duplicate_spin, 4, 1)
        params_layout.addWidget(QLabel("低重复率阈值:"), 4, 2)
        params_layout.addWidget(self.dynamic_budget_low_duplicate_spin, 4, 3)
        dynamic_layout.addWidget(self.dynamic_budget_params_container)

        dynamic_hint = QLabel("说明：动态预算只影响预计算尝试次数，不改变绑定规则或去重语义。")
        dynamic_hint.setProperty("role", "muted")
        dynamic_hint.setWordWrap(True)
        dynamic_layout.addWidget(dynamic_hint)

        auto_tune_row = QHBoxLayout()
        auto_tune_row.setContentsMargins(12, 0, 0, 0)
        auto_tune_row.setSpacing(8)
        auto_tune_row.addWidget(QLabel("自动调参样本数:"))
        self.dynamic_budget_recent_n_spin = QSpinBox()
        self.dynamic_budget_recent_n_spin.setRange(3, 80)
        self.dynamic_budget_recent_n_spin.setValue(12)
        auto_tune_row.addWidget(self.dynamic_budget_recent_n_spin)
        self.dynamic_budget_recommend_btn = QPushButton("生成推荐参数")
        self.dynamic_budget_recommend_btn.setProperty("variant", "secondary")
        self.dynamic_budget_recommend_btn.clicked.connect(self.recommend_dynamic_budget_params)
        auto_tune_row.addWidget(self.dynamic_budget_recommend_btn)
        self.dynamic_budget_apply_btn = QPushButton("一键应用推荐")
        self.dynamic_budget_apply_btn.setProperty("variant", "default")
        self.dynamic_budget_apply_btn.setEnabled(False)
        self.dynamic_budget_apply_btn.clicked.connect(self.apply_recommended_dynamic_budget_params)
        auto_tune_row.addWidget(self.dynamic_budget_apply_btn)
        auto_tune_row.addStretch()
        dynamic_layout.addLayout(auto_tune_row)

        self.dynamic_budget_recommend_label = QLabel("自动调参：暂无推荐。可在完成多次导出后生成。")
        self.dynamic_budget_recommend_label.setWordWrap(True)
        self.dynamic_budget_recommend_label.setProperty("role", "muted")
        dynamic_layout.addWidget(self.dynamic_budget_recommend_label)

        self.dynamic_budget_enabled_check.toggled.connect(self._set_dynamic_budget_controls_enabled)
        self._set_dynamic_budget_controls_enabled(True)
        # 需求调整：动态预算作为默认自动能力，不在导出窗口提供手动调参
        self.dynamic_budget_group.setVisible(False)

        form_layout.addRow(self.dynamic_budget_group)

        # 文件名规则组
        name_group = QGroupBox("文件名规则")
        name_layout = QVBoxLayout()

        # 格式说明
        format_label = QLabel("格式: 日期-自定义文本-图层文件名-序号")
        format_label.setProperty("role", "label")
        name_layout.addWidget(format_label)

        # 当前日期设置
        date_layout = QHBoxLayout()
        self.use_date = QCheckBox("添加当前日期")
        self.use_date.setChecked(True)
        date_layout.addWidget(self.use_date)

        self.date_format = QComboBox()
        self.date_format.addItem("YYYYMMDD (20240520)", "yyyyMMdd")
        self.date_format.addItem("YYYY-MM-DD (2024-05-20)", "yyyy-MM-dd")
        self.date_format.addItem("YYMMDD (240520)", "yyMMdd")
        self.date_format.setEnabled(True)
        date_layout.addWidget(self.date_format)

        self.use_date.toggled.connect(self.date_format.setEnabled)

        name_layout.addLayout(date_layout)

        # 自定义文本
        custom_layout = QHBoxLayout()
        custom_layout.addWidget(QLabel("自定义文本:"))
        self.custom_text = QLineEdit()
        self.custom_text.setText("export")
        custom_layout.addWidget(self.custom_text)
        name_layout.addLayout(custom_layout)

        # 图层文件名选择
        layer_layout = QHBoxLayout()
        self.use_layer_name = QCheckBox("使用图层文件名")
        self.use_layer_name.setChecked(False)
        layer_layout.addWidget(self.use_layer_name)

        self.layer_combo = QComboBox()
        self.update_layer_list()
        self.layer_combo.setEnabled(self.use_layer_name.isChecked())
        layer_layout.addWidget(self.layer_combo)

        self.use_layer_name.toggled.connect(self.layer_combo.setEnabled)

        # 提示标签，解释图层文件名将使用实际随机选择的图像文件名
        layer_info_label = QLabel("导出时将使用实际随机选择的图像文件名，而不是固定的图层名称")
        layer_info_label.setProperty("role", "success")
        name_layout.addWidget(layer_info_label)

        name_layout.addLayout(layer_layout)

        # 序号格式
        number_layout = QHBoxLayout()
        number_layout.addWidget(QLabel("序号格式:"))
        self.number_format = QComboBox()
        self.number_format.addItem("0001, 0002, ...", "{number:04d}")
        self.number_format.addItem("001, 002, ...", "{number:03d}")
        self.number_format.addItem("01, 02, ...", "{number:02d}")
        self.number_format.addItem("1, 2, ...", "{number:d}")
        number_layout.addWidget(self.number_format)
        name_layout.addLayout(number_layout)

        # 预览
        preview_layout = QHBoxLayout()
        preview_layout.addWidget(QLabel("文件名预览:"))
        self.filename_preview = QLabel()
        self.filename_preview.setProperty("role", "status-value")
        preview_layout.addWidget(self.filename_preview)
        name_layout.addLayout(preview_layout)

        # 添加更新预览的连接
        self.use_date.stateChanged.connect(self.update_preview)
        self.date_format.currentIndexChanged.connect(self.update_preview)
        self.custom_text.textChanged.connect(self.update_preview)
        self.use_layer_name.stateChanged.connect(self.update_preview)
        self.layer_combo.currentIndexChanged.connect(self.update_preview)
        self.number_format.currentIndexChanged.connect(self.update_preview)
        self.format_combo.currentIndexChanged.connect(self.update_preview)
        if hasattr(self, 'quality_profile_combo'):
            self.quality_profile_combo.currentIndexChanged.connect(self.update_preview)

        name_group.setLayout(name_layout)

        # 更新初始预览
        self.update_preview()

        # 导出模式选择
        mode_group = QGroupBox("导出模式")
        mode_layout = QVBoxLayout()
        mode_layout.setContentsMargins(8, 8, 8, 8)
        mode_layout.setSpacing(6)

        self.traverse_export_check = QCheckBox("遍历导出（导出所有可能组合）")
        self.traverse_export_check.setToolTip("启用后将导出所有可能的组合，而不是随机生成组合")
        self.traverse_export_check.stateChanged.connect(self.on_traverse_mode_changed)

        # 添加智能采样选项
        self.smart_sampling_check = QCheckBox("智能采样（避免图片重复使用）")
        self.smart_sampling_check.setToolTip("启用后将确保每个图层的图片使用次数尽可能均匀，避免某些图片被过度使用")
        self.smart_sampling_check.setChecked(True)  # 默认启用

        mode_options_layout = QHBoxLayout()
        mode_options_layout.setContentsMargins(0, 0, 0, 0)
        mode_options_layout.setSpacing(10)
        mode_options_layout.addWidget(self.traverse_export_check)
        mode_options_layout.addWidget(self.smart_sampling_check)
        mode_options_layout.addStretch()
        mode_layout.addLayout(mode_options_layout)

        # 添加说明文字
        mode_description_label = QLabel("• 随机：按数量生成；遍历：导出全部组合（数量自动计算）；智能采样：尽量均匀使用图片")
        mode_description_label.setProperty("role", "muted")
        mode_description_label.setWordWrap(True)
        mode_layout.addWidget(mode_description_label)

        mode_group.setLayout(mode_layout)

        # 指定图层“每张只用一次”功能
        unique_group = QGroupBox("图像唯一使用")
        unique_layout = QVBoxLayout()
        self.unique_use_enabled = QCheckBox("为指定图层启用：图像源中的每张图片仅使用一次")
        self.unique_use_enabled.setToolTip("选择的图层在本次导出中，每张图片只会被使用一次；数量将受限于这些图层各自的图片数量")
        unique_layout.addWidget(self.unique_use_enabled)

        self.unique_layer_checks = []
        self.unique_layers_container = QWidget()
        container_layout = QGridLayout(self.unique_layers_container)
        container_layout.setContentsMargins(12, 0, 0, 0)
        container_layout.setHorizontalSpacing(12)
        container_layout.setVerticalSpacing(4)
        for i, layer in enumerate(self.document.layers):
            cb = QCheckBox(f"{layer.name} (图层 {i+1})")
            cb.setProperty("layer_index", i)
            cb.setProperty("unique_use_eligible", self._is_unique_use_eligible_layer(layer))
            if not cb.property("unique_use_eligible"):
                cb.setToolTip("图像唯一使用仅适用于图片图层，文字图层的文案不会限制导出数量")
            cb.setChecked(False)
            self.unique_layer_checks.append(cb)
            row, col = divmod(i, 2)
            container_layout.addWidget(cb, row, col)

        # 初始状态设置：根据主开关状态设置容器启用状态
        self.unique_layers_container.setEnabled(self.unique_use_enabled.isChecked())
        unique_layout.addWidget(self.unique_layers_container)

        # 交互：启用时可选择图层
        self.unique_use_enabled.toggled.connect(self._set_unique_checks_enabled)

        hint_unique = QLabel("说明：若选择多个图层，则导出张数将受限于这些图层图片数量的最小值。")
        hint_unique.setProperty("role", "muted")
        unique_layout.addWidget(hint_unique)

        unique_group.setLayout(unique_layout)

        # 将主要模块改为左右分栏，降低整体高度
        modules_container = QWidget()
        modules_layout = QHBoxLayout(modules_container)
        modules_layout.setContentsMargins(0, 0, 0, 0)
        modules_layout.setSpacing(10)

        left_modules_layout = QVBoxLayout()
        left_modules_layout.setContentsMargins(0, 0, 0, 0)
        left_modules_layout.setSpacing(8)
        left_modules_layout.addWidget(name_group)
        left_modules_layout.addStretch()

        right_modules_layout = QVBoxLayout()
        right_modules_layout.setContentsMargins(0, 0, 0, 0)
        right_modules_layout.setSpacing(8)
        right_modules_layout.addWidget(mode_group)
        right_modules_layout.addWidget(unique_group)
        right_modules_layout.addStretch()

        modules_layout.addLayout(left_modules_layout, 3)
        modules_layout.addLayout(right_modules_layout, 2)
        form_layout.addRow(modules_container)

        # 导出路径
        path_layout = QHBoxLayout()

        self.path_edit = QLineEdit()
        self.path_edit.setReadOnly(False)  # 允许直接编辑
        self.path_edit.setPlaceholderText("选择或输入导出目录...")
        # 当路径输入框内容变化时，更新directory
        self.path_edit.textChanged.connect(self.update_directory)

        self.browse_btn = QPushButton("浏览...")
        self.browse_btn.setProperty("variant", "outline")
        self.browse_btn.clicked.connect(self.browse_directory)

        path_layout.addWidget(self.path_edit)
        path_layout.addWidget(self.browse_btn)

        form_layout.addRow("导出位置:", path_layout)

        current_time_layout = QHBoxLayout()
        self.use_current_time_for_path = QCheckBox("使用当前时间")
        self.use_current_time_for_path.setToolTip(
            "启用后，导出时会把导出位置路径中的8位日期替换为当天日期，例如 20260430"
        )
        self.use_current_time_for_path.setChecked(False)
        self.use_current_time_for_path.toggled.connect(self._on_use_current_time_for_path_toggled)
        current_time_layout.addWidget(self.use_current_time_for_path)
        self.current_time_path_hint = QLabel("路径中的 YYYYMMDD 日期会在导出时替换为当天")
        self.current_time_path_hint.setProperty("role", "muted")
        current_time_layout.addWidget(self.current_time_path_hint)
        current_time_layout.addStretch()
        form_layout.addRow("", current_time_layout)

        layout.addLayout(form_layout)

        # 添加保存设置和打开目录按钮
        settings_layout = QHBoxLayout()

        self.save_config_btn = QPushButton("保存")
        self.save_config_btn.setProperty("variant", "secondary")
        self.save_config_btn.setToolTip("保存当前设置到当前标签页")
        self.save_config_btn.clicked.connect(self.save_config)
        settings_layout.addWidget(self.save_config_btn)

        # 添加打开输出文件夹按钮
        self.open_dir_btn = QPushButton("打开输出文件夹")
        self.open_dir_btn.setProperty("variant", "secondary")
        self.open_dir_btn.setToolTip("打开当前设置的导出目录")
        self.open_dir_btn.clicked.connect(self.open_output_directory)
        # 初始状态下禁用，直到选择了有效目录
        self.open_dir_btn.setEnabled(False)
        settings_layout.addWidget(self.open_dir_btn)

        layout.addLayout(settings_layout)

        # 按钮区域
        # 使用 ActionRole 显式创建“确定”按钮，避免 QDialogButtonBox 的默认行为
        # 在点击 Ok 角色按钮时自动调用 QDialog.accept() 并关闭对话框。
        # 批量导出需要在后台线程启动后保持对话框打开以显示进度。
        self.button_box = QDialogButtonBox(QDialogButtonBox.Cancel)
        self.ok_btn = QPushButton("确定")
        self.ok_btn.setProperty("variant", "default")
        self.button_box.addButton(self.ok_btn, QDialogButtonBox.ActionRole)
        self.ok_btn.clicked.connect(self._on_export_confirmed)
        self.button_box.rejected.connect(self.reject)
        self.minimize_btn = QPushButton("缩小到标签")
        self.minimize_btn.setProperty("variant", "ghost")
        self.minimize_btn.setToolTip("隐藏导出窗口，任务继续在后台运行")
        self.minimize_btn.clicked.connect(self.minimize_to_tab)
        self.minimize_btn.setEnabled(False)
        self.button_box.addButton(self.minimize_btn, QDialogButtonBox.ActionRole)

        # 设置按钮中文文本
        self.ok_btn.setText("确定")
        self.button_box.button(QDialogButtonBox.Cancel).setText("取消")

        # 默认禁用确认按钮，直到选择导出目录
        self.ok_btn.setEnabled(False)

        layout.addWidget(self.button_box)

        # 内嵌导出进度区（替代独立QProgressDialog）
        self.progress_container = QGroupBox("导出进度")
        progress_layout = QVBoxLayout(self.progress_container)
        self.progress_status_label = QLabel("准备导出...")
        progress_layout.addWidget(self.progress_status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setProperty("role", "progress")
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        progress_btn_layout = QHBoxLayout()
        progress_btn_layout.addStretch()
        self.progress_cancel_btn = QPushButton("取消导出")
        self.progress_cancel_btn.setProperty("variant", "destructive")
        self.progress_cancel_btn.clicked.connect(self.cancel_export)
        self.progress_cancel_btn.setEnabled(False)
        progress_btn_layout.addWidget(self.progress_cancel_btn)
        progress_layout.addLayout(progress_btn_layout)
        self.progress_container.setVisible(False)
        layout.addWidget(self.progress_container)

        # 导出性能诊断面板（内部统计）
        self.performance_diag_group = QGroupBox("导出性能诊断")
        diag_layout = QVBoxLayout(self.performance_diag_group)
        diag_layout.setContentsMargins(8, 8, 8, 8)
        diag_layout.setSpacing(4)
        diag_grid = QGridLayout()
        diag_grid.setContentsMargins(0, 0, 0, 0)
        diag_grid.setHorizontalSpacing(12)
        diag_grid.setVerticalSpacing(4)
        self.diag_precompute_label = QLabel("预计算耗时: -")
        self.diag_render_label = QLabel("渲染耗时: -")
        self.diag_io_label = QLabel("写盘耗时: -")
        self.diag_throughput_label = QLabel("总吞吐: -")
        self.diag_count_label = QLabel("数量: -")
        self.diag_policy_label = QLabel("策略: -")
        self.diag_pipeline_label = QLabel("流水线: -")
        self.diag_save_label = QLabel("保存: -")
        self.diag_safety_label = QLabel("保护: -")
        self.diag_error_label = QLabel("结果: -")
        diag_labels = [
            self.diag_count_label,
            self.diag_precompute_label,
            self.diag_render_label,
            self.diag_io_label,
            self.diag_throughput_label,
            self.diag_policy_label,
            self.diag_pipeline_label,
            self.diag_save_label,
            self.diag_safety_label,
            self.diag_error_label,
        ]
        for lb in diag_labels:
            lb.setProperty("role", "muted")
            lb.setWordWrap(True)
        for row, lb in enumerate(diag_labels):
            diag_grid.addWidget(lb, row // 2, row % 2)
        diag_layout.addLayout(diag_grid)
        self.performance_diag_group.setVisible(False)
        layout.addWidget(self.performance_diag_group)

        # 初始化遍历模式状态（在所有控件创建完成后）
        self.update_traverse_mode_display()

    def _set_unique_checks_enabled(self, enabled: bool):
        if hasattr(self, 'unique_layers_container'):
            self.unique_layers_container.setEnabled(enabled)
        if hasattr(self, 'unique_layer_checks'):
            for cb in self.unique_layer_checks:
                cb.setEnabled(enabled and bool(cb.property("unique_use_eligible")))

    def _is_text_layer(self, layer) -> bool:
        try:
            if hasattr(layer, 'get_text_lines') and callable(getattr(layer, 'get_text_lines', None)):
                return True
            class_name = layer.__class__.__name__ if layer is not None else ""
            if class_name == "TextLayer":
                return True
            return bool(hasattr(layer, 'text_content') and not hasattr(layer, 'image_source'))
        except Exception:
            return False

    def _is_unique_use_eligible_layer(self, layer) -> bool:
        """图像唯一使用只允许图片图层参与，避免文字文案数量限制导出张数。"""
        try:
            if layer is None or self._is_text_layer(layer):
                return False
            source = getattr(layer, 'image_source', None) or getattr(layer, '_image_source', None)
            if source:
                return True
            paths = getattr(layer, 'image_paths', None)
            return bool(paths)
        except Exception:
            return False

    def _set_dynamic_budget_controls_enabled(self, enabled: bool):
        if hasattr(self, 'dynamic_budget_params_container'):
            self.dynamic_budget_params_container.setEnabled(bool(enabled))
        if hasattr(self, 'dynamic_budget_binding_check'):
            self.dynamic_budget_binding_check.setEnabled(bool(enabled))
        if hasattr(self, 'dynamic_budget_standard_check'):
            self.dynamic_budget_standard_check.setEnabled(bool(enabled))

    def _update_memory_guard_controls(self, *_args):
        if not hasattr(self, 'memory_guard_combo'):
            return
        mode = str(self.memory_guard_combo.currentData() or 'auto')
        custom_enabled = mode == 'custom'
        if hasattr(self, 'memory_limit_spin'):
            self.memory_limit_spin.setEnabled(custom_enabled)
        if hasattr(self, 'memory_reserve_spin'):
            self.memory_reserve_spin.setEnabled(mode in ('auto', 'low'))

    def _collect_recent_export_reports(self, n: int):
        history = getattr(self.document, '_export_report_history', None)
        if not isinstance(history, list) or not history:
            return []
        valid = [r for r in history if isinstance(r, dict)]
        if n <= 0:
            return valid
        return valid[-int(n):]

    def _build_dynamic_budget_recommendation(self, reports):
        if not reports:
            return None

        diagnostics = []
        for report in reports:
            extra = report.get('extra', {}) if isinstance(report, dict) else {}
            if not isinstance(extra, dict):
                continue
            diag = extra.get('precompute_diagnostics', {})
            if isinstance(diag, dict):
                diagnostics.append(diag)
        if not diagnostics:
            return None

        shortage_count = 0
        success_rates = []
        duplicate_rates = []
        expand_events = 0
        shrink_events = 0

        for d in diagnostics:
            sa = d.get('shortage_analysis', {}) if isinstance(d.get('shortage_analysis', {}), dict) else {}
            if int(sa.get('shortage_count', 0) or 0) > 0:
                shortage_count += 1
            success_rates.append(float(sa.get('success_rate', 0.0) or 0.0))
            duplicate_rates.append(float(sa.get('duplicate_rate', 0.0) or 0.0))

            db = d.get('dynamic_budget', {}) if isinstance(d.get('dynamic_budget', {}), dict) else {}
            expand_events += int(db.get('expanded_times', 0) or 0)
            shrink_events += int(db.get('shrunk_times', 0) or 0)

        if not success_rates:
            return None

        sample_size = len(diagnostics)
        shortage_ratio = shortage_count / max(1, sample_size)
        avg_success = sum(success_rates) / max(1, len(success_rates))
        avg_duplicate = sum(duplicate_rates) / max(1, len(duplicate_rates))

        rec = {
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
        }

        if shortage_ratio >= 0.5 or avg_success < 0.22:
            rec['dynamic_budget_max_ratio'] = 4.0
            rec['dynamic_budget_expand_step'] = 0.25
            rec['dynamic_budget_check_interval'] = 20
            rec['dynamic_budget_min_samples'] = 30
            rec['dynamic_budget_low_success_rate'] = 0.20
            rec['dynamic_budget_high_duplicate_rate'] = 0.68
        elif shortage_ratio <= 0.1 and avg_success > 0.6 and avg_duplicate < 0.35:
            rec['dynamic_budget_max_ratio'] = 2.4
            rec['dynamic_budget_expand_step'] = 0.15
            rec['dynamic_budget_shrink_step'] = 0.14
            rec['dynamic_budget_check_interval'] = 30
            rec['dynamic_budget_min_samples'] = 50
            rec['dynamic_budget_low_success_rate'] = 0.12

        if avg_duplicate > 0.72:
            rec['dynamic_budget_high_duplicate_rate'] = min(rec['dynamic_budget_high_duplicate_rate'], 0.66)
            rec['dynamic_budget_expand_step'] = max(rec['dynamic_budget_expand_step'], 0.25)
        elif avg_duplicate < 0.28:
            rec['dynamic_budget_low_duplicate_rate'] = 0.25

        if expand_events == 0 and shortage_ratio > 0.2:
            rec['dynamic_budget_check_interval'] = min(rec['dynamic_budget_check_interval'], 18)
            rec['dynamic_budget_min_samples'] = min(rec['dynamic_budget_min_samples'], 25)

        if shrink_events == 0 and shortage_ratio < 0.1 and avg_success > 0.7:
            rec['dynamic_budget_shrink_step'] = max(rec['dynamic_budget_shrink_step'], 0.15)

        rec['_meta'] = {
            'sample_size': sample_size,
            'shortage_ratio': shortage_ratio,
            'avg_success_rate': avg_success,
            'avg_duplicate_rate': avg_duplicate,
            'expand_events': expand_events,
            'shrink_events': shrink_events,
        }
        return rec

    def _set_dynamic_budget_controls_from_recommendation(self, rec: dict):
        self.dynamic_budget_enabled_check.setChecked(bool(rec.get('dynamic_budget_enabled', True)))
        self.dynamic_budget_binding_check.setChecked(bool(rec.get('dynamic_budget_binding_enabled', True)))
        self.dynamic_budget_standard_check.setChecked(bool(rec.get('dynamic_budget_standard_enabled', True)))
        self.dynamic_budget_min_ratio_spin.setValue(float(rec.get('dynamic_budget_min_ratio', 0.8)))
        self.dynamic_budget_max_ratio_spin.setValue(float(rec.get('dynamic_budget_max_ratio', 3.0)))
        self.dynamic_budget_check_interval_spin.setValue(int(rec.get('dynamic_budget_check_interval', 25)))
        self.dynamic_budget_min_samples_spin.setValue(int(rec.get('dynamic_budget_min_samples', 40)))
        self.dynamic_budget_expand_step_spin.setValue(float(rec.get('dynamic_budget_expand_step', 0.2)))
        self.dynamic_budget_shrink_step_spin.setValue(float(rec.get('dynamic_budget_shrink_step', 0.1)))
        self.dynamic_budget_low_success_spin.setValue(float(rec.get('dynamic_budget_low_success_rate', 0.15)))
        self.dynamic_budget_high_success_spin.setValue(float(rec.get('dynamic_budget_high_success_rate', 0.65)))
        self.dynamic_budget_high_duplicate_spin.setValue(float(rec.get('dynamic_budget_high_duplicate_rate', 0.75)))
        self.dynamic_budget_low_duplicate_spin.setValue(float(rec.get('dynamic_budget_low_duplicate_rate', 0.30)))
        self._set_dynamic_budget_controls_enabled(self.dynamic_budget_enabled_check.isChecked())

    def recommend_dynamic_budget_params(self):
        n = int(self.dynamic_budget_recent_n_spin.value())
        reports = self._collect_recent_export_reports(n)
        rec = self._build_dynamic_budget_recommendation(reports)
        if not rec:
            self.dynamic_budget_recommend_label.setText("自动调参：历史导出报告不足（需至少 1 条带预计算诊断数据的报告）。")
            self.dynamic_budget_apply_btn.setEnabled(False)
            self._last_dynamic_budget_recommendation = None
            return

        self._last_dynamic_budget_recommendation = rec
        self.dynamic_budget_apply_btn.setEnabled(True)
        meta = rec.get('_meta', {})
        self.dynamic_budget_recommend_label.setText(
            f"推荐已生成（样本{meta.get('sample_size', 0)}次，短缺率{meta.get('shortage_ratio', 0.0)*100:.1f}%，"
            f"成功率{meta.get('avg_success_rate', 0.0)*100:.1f}%，重复率{meta.get('avg_duplicate_rate', 0.0)*100:.1f}%）。"
        )

    def apply_recommended_dynamic_budget_params(self):
        rec = self._last_dynamic_budget_recommendation
        if not isinstance(rec, dict):
            self.recommend_dynamic_budget_params()
            rec = self._last_dynamic_budget_recommendation
        if not isinstance(rec, dict):
            return

        self._set_dynamic_budget_controls_from_recommendation(rec)
        self.save_settings()
        self.dynamic_budget_recommend_label.setText("推荐参数已应用并保存到当前标签页导出设置。")

    def update_layer_list(self):
        """更新图层列表"""
        self.layer_combo.clear()
        for i, layer in enumerate(self.document.layers):
            # 使用图层名称和索引
            self.layer_combo.addItem(f"{layer.name} (图层 {i+1})", i)

    def update_preview(self):
        """更新文件名预览"""
        # 构建预览文件名
        parts = []

        # 日期部分
        if self.use_date.isChecked():
            date_format = self.date_format.currentData()
            if date_format == "yyyyMMdd":
                date_str = datetime.datetime.now().strftime("%Y%m%d")
            elif date_format == "yyyy-MM-dd":
                date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            elif date_format == "yyMMdd":
                date_str = datetime.datetime.now().strftime("%y%m%d")
            parts.append(date_str)

        # 自定义文本
        custom = self.custom_text.text().strip()
        if custom:
            parts.append(custom)

        # 图层文件名（移除序号部分）
        if self.use_layer_name.isChecked() and self.layer_combo.count() > 0:
            layer_index = self.layer_combo.currentData()
            if 0 <= layer_index < len(self.document.layers):
                layer = self.document.layers[layer_index]
                if layer.current_image_path:
                    import re
                    import unicodedata

                    try:
                        # 安全地获取文件名，处理编码问题
                        basename = os.path.basename(layer.current_image_path)
                        if isinstance(basename, bytes):
                            basename = basename.decode('utf-8', 'ignore')
                        filename = os.path.splitext(basename)[0]

                        # Unicode规范化
                        try:
                            filename = unicodedata.normalize('NFKC', filename)
                        except Exception:
                            logger.warning("静默异常已忽略: except in ui/batch_export_dialog_ui.py", exc_info=True)
                            pass

                        # 使用Document类的方法来提取主文件名
                        clean_filename = self.document._extract_main_filename(filename)

                        # 再次检查是否为空
                        if not clean_filename or clean_filename.isspace():
                            clean_filename = filename

                        parts.append(clean_filename)
                    except Exception as e:
                        print(f"处理图层文件名时出错: {e}")
                        parts.append("[图层名称]")
                else:
                    # 显示占位符，表示将使用实际图像名称
                    parts.append("[实际图像名称]")

        # 序号
        number_format = self.number_format.currentData()
        number_example = number_format.format(number=1)
        parts.append(number_example)

        # 组合预览
        ext_map = {0: ".png", 1: ".jpg", 2: ".bmp"}
        ext = ext_map.get(self.format_combo.currentIndex(), ".png")
        preview = "-".join(parts) + ext
        self.filename_preview.setText(preview)

    def update_directory(self):
        """当用户直接编辑路径输入框时更新目录"""
        if getattr(self, '_updating_current_date_path', False):
            return
        path = self.path_edit.text().strip()
        if path:
            # 即使路径不存在也更新目录，导出时会自动创建
            self.directory = path
            self.ok_btn.setEnabled(True)

            # 如果目录不存在，添加提示信息
            if not os.path.isdir(path):
                _set_semantic_status(self.path_edit, "warning")
                self.path_edit.setToolTip("目录不存在，将在导出时自动创建")
                # 目录不存在时禁用打开目录按钮
                if hasattr(self, 'open_dir_btn'):
                    self.open_dir_btn.setEnabled(False)
            else:
                _set_semantic_status(self.path_edit)
                self.path_edit.setToolTip("")
                # 目录存在时启用打开目录按钮
                if hasattr(self, 'open_dir_btn'):
                    self.open_dir_btn.setEnabled(True)
        else:
            # 如果路径为空，则禁用确认按钮和打开目录按钮
            self.directory = ""
            self.ok_btn.setEnabled(False)
            if hasattr(self, 'open_dir_btn'):
                self.open_dir_btn.setEnabled(False)
            _set_semantic_status(self.path_edit)
            self.path_edit.setToolTip("")

    def _on_use_current_time_for_path_toggled(self, checked):
        self.update_directory()

    def _is_valid_yyyymmdd(self, value):
        try:
            datetime.datetime.strptime(value, "%Y%m%d")
            return True
        except Exception:
            return False

    def _replace_path_date_with_today(self, path):
        """把路径中的 YYYYMMDD 日期段替换为当天日期。"""
        if not path:
            return path

        today = datetime.datetime.now().strftime("%Y%m%d")

        def repl(match):
            value = match.group(0)
            return today if self._is_valid_yyyymmdd(value) else value

        return re.sub(r"(?<!\d)(?:19|20)\d{6}(?!\d)", repl, path)

    def _resolved_export_directory(self):
        directory = self.path_edit.text().strip() if hasattr(self, 'path_edit') else (self.directory or '').strip()
        if hasattr(self, 'use_current_time_for_path') and self.use_current_time_for_path.isChecked():
            return self._replace_path_date_with_today(directory)
        return directory

    def _apply_current_date_to_path_field(self):
        """兼容旧调用：不改写输入框，只刷新当前目录状态。"""
        if not hasattr(self, 'path_edit'):
            return
        self.update_directory()

    def browse_directory(self):
        """浏览选择导出目录"""
        directory = QFileDialog.getExistingDirectory(self, "选择导出目录")
        if directory:
            self.directory = directory
            self.path_edit.setText(directory)
            _set_semantic_status(self.path_edit)
            self.path_edit.setToolTip("")     # 清除可能的提示
            self.ok_btn.setEnabled(True)
            # 启用打开目录按钮
            if hasattr(self, 'open_dir_btn'):
                self.open_dir_btn.setEnabled(True)

    def get_filename_template(self):
        """获取文件名模板"""
        parts = []

        # 日期部分
        if self.use_date.isChecked():
            date_format = self.date_format.currentData()
            if date_format == "yyyyMMdd":
                date_str = datetime.datetime.now().strftime("%Y%m%d")
            elif date_format == "yyyy-MM-dd":
                date_str = datetime.datetime.now().strftime("%Y-%m-%d")
            elif date_format == "yyMMdd":
                date_str = datetime.datetime.now().strftime("%y%m%d")
            parts.append(date_str)

        # 自定义文本
        custom = self.custom_text.text().strip()
        if custom:
            parts.append(custom)

        # 图层文件名部分 - 使用指定图层的占位符
        if self.use_layer_name.isChecked() and self.layer_combo.count() > 0:
            layer_index = self.layer_combo.currentData()
            if 0 <= layer_index < len(self.document.layers):
                # 使用{layer:index}格式，指定具体的图层索引
                parts.append(f"{{layer:{layer_index}}}")
            else:
                # 回退到通用占位符
                parts.append("{layer}")

        # 序号
        number_format = self.number_format.currentData()
        parts.append(number_format)

        # 组合模板
        return "-".join(parts)

    def on_traverse_mode_changed(self):
        """当遍历模式状态改变时调用"""
        self.update_traverse_mode_display()

    def update_traverse_mode_display(self):
        """更新遍历模式的显示状态"""
        is_traverse_mode = self.traverse_export_check.isChecked()

        if is_traverse_mode:
            # 遍历模式：计算可能的组合数量
            try:
                total_combinations = self.document._calculate_possible_combinations()

                # 更新标签显示计算出的组合数
                self.calculated_count_label.setText(f"(将导出 {total_combinations} 个组合)")

                # 禁用数量输入框
                self.count_spin.setEnabled(False)
                self.count_spin.setToolTip("遍历模式下将自动导出所有可能的组合")

                # 如果组合数量很大，给出警告
                if total_combinations > 10000:
                    _set_semantic_status(self.calculated_count_label, "destructive")
                    self.calculated_count_label.setText(f"(将导出 {total_combinations} 个组合 - 注意数量很大!)")
                elif total_combinations > 1000:
                    _set_semantic_status(self.calculated_count_label, "warning")
                    self.calculated_count_label.setText(f"(将导出 {total_combinations} 个组合 - 数量较大)")
                else:
                    _set_semantic_status(self.calculated_count_label, "info")

            except Exception as e:
                print(f"计算组合数量失败: {e}")
                self.calculated_count_label.setText("(无法计算组合数)")
                _set_semantic_status(self.calculated_count_label, "muted")

                # 仍然禁用数量输入框
                self.count_spin.setEnabled(False)
                self.count_spin.setToolTip("遍历模式下将自动导出所有可能的组合")
        else:
            # 随机模式：恢复正常状态
            self.calculated_count_label.setText("")
            _set_semantic_status(self.calculated_count_label, "info")
            self.count_spin.setEnabled(True)
            self.count_spin.setToolTip("要导出的图像数量")
