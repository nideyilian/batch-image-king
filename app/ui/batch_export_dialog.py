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


class BatchExportDialog(QDialog):
    """批量导出对话框"""

    SETTINGS_ORG = "批图王"
    SETTINGS_APP = "BatchExportDialog"
    SETTINGS_KEY = "last_settings"

    def __init__(self, document, parent=None):
        super().__init__(parent)

        self.document = document
        self._host_parent = parent
        self.directory = document.export_settings.get('last_directory', "")

        # 初始化取消标志
        self.export_canceled = False
        self._export_running = False
        self._export_total_count = 0
        self._export_started_at = None
        self._last_exported_file_hint = ""
        self._progress_phase_hint = "准备导出"
        self._last_dynamic_budget_recommendation = None
        self._export_trace_path_announced = False
        self._updating_current_date_path = False
        self._progress_refresh_timer = QTimer(self)
        self._progress_refresh_timer.setInterval(500)
        self._progress_refresh_timer.timeout.connect(self._refresh_progress_display)

        self.setWindowTitle("批量导出图像")
        self.setMinimumWidth(760)

        self.setup_ui()
        self.load_settings()  # 加载上一次的设置

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
    

    def setup_ui(self):
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
        self.calculated_count_label.setStyleSheet("color: #2F9CF4; font-weight: bold; margin-left: 10px;")
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
        hint.setStyleSheet("color: #8E8E93;")
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
        dynamic_hint.setStyleSheet("color: #8E8E93; font-size: 11px;")
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
        self.dynamic_budget_recommend_btn.clicked.connect(self.recommend_dynamic_budget_params)
        auto_tune_row.addWidget(self.dynamic_budget_recommend_btn)
        self.dynamic_budget_apply_btn = QPushButton("一键应用推荐")
        self.dynamic_budget_apply_btn.setEnabled(False)
        self.dynamic_budget_apply_btn.clicked.connect(self.apply_recommended_dynamic_budget_params)
        auto_tune_row.addWidget(self.dynamic_budget_apply_btn)
        auto_tune_row.addStretch()
        dynamic_layout.addLayout(auto_tune_row)

        self.dynamic_budget_recommend_label = QLabel("自动调参：暂无推荐。可在完成多次导出后生成。")
        self.dynamic_budget_recommend_label.setWordWrap(True)
        self.dynamic_budget_recommend_label.setStyleSheet("color: #8E8E93; font-size: 11px;")
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
        format_label.setStyleSheet("font-weight: bold;")
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
        layer_info_label.setStyleSheet("color: #30D158; font-style: italic;")
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
        self.filename_preview.setStyleSheet("font-weight: bold; color: #2F9CF4;")
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
        mode_description_label.setStyleSheet("color: #8E8E93; font-size: 11px; margin-top: 5px;")
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
        hint_unique.setStyleSheet("color: #8E8E93; font-size: 11px;")
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
        self.current_time_path_hint.setStyleSheet("color: #8E8E93;")
        current_time_layout.addWidget(self.current_time_path_hint)
        current_time_layout.addStretch()
        form_layout.addRow("", current_time_layout)

        layout.addLayout(form_layout)

        # 添加保存设置和打开目录按钮
        settings_layout = QHBoxLayout()

        self.save_config_btn = QPushButton("保存")
        self.save_config_btn.setToolTip("保存当前设置到当前标签页")
        self.save_config_btn.clicked.connect(self.save_config)
        settings_layout.addWidget(self.save_config_btn)

        # 添加打开输出文件夹按钮
        self.open_dir_btn = QPushButton("打开输出文件夹")
        self.open_dir_btn.setToolTip("打开当前设置的导出目录")
        self.open_dir_btn.clicked.connect(self.open_output_directory)
        # 初始状态下禁用，直到选择了有效目录
        self.open_dir_btn.setEnabled(False)
        settings_layout.addWidget(self.open_dir_btn)

        layout.addLayout(settings_layout)

        # 按钮区域
        self.button_box = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.button_box.accepted.connect(self.accept)
        self.button_box.rejected.connect(self.reject)
        self.minimize_btn = QPushButton("缩小到标签")
        self.minimize_btn.setToolTip("隐藏导出窗口，任务继续在后台运行")
        self.minimize_btn.clicked.connect(self.minimize_to_tab)
        self.minimize_btn.setEnabled(False)
        self.button_box.addButton(self.minimize_btn, QDialogButtonBox.ActionRole)

        # 设置按钮中文文本
        self.button_box.button(QDialogButtonBox.Ok).setText("确定")
        self.button_box.button(QDialogButtonBox.Cancel).setText("取消")

        # 默认禁用确认按钮，直到选择导出目录
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)

        layout.addWidget(self.button_box)

        # 内嵌导出进度区（替代独立QProgressDialog）
        self.progress_container = QGroupBox("导出进度")
        progress_layout = QVBoxLayout(self.progress_container)
        self.progress_status_label = QLabel("准备导出...")
        progress_layout.addWidget(self.progress_status_label)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        progress_layout.addWidget(self.progress_bar)
        progress_btn_layout = QHBoxLayout()
        progress_btn_layout.addStretch()
        self.progress_cancel_btn = QPushButton("取消导出")
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
            lb.setStyleSheet("color: #8E8E93;")
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
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)

            # 如果目录不存在，添加提示信息
            if not os.path.isdir(path):
                self.path_edit.setStyleSheet("color: #FF8A3D;")  # 橙色提示
                self.path_edit.setToolTip("目录不存在，将在导出时自动创建")
                # 目录不存在时禁用打开目录按钮
                if hasattr(self, 'open_dir_btn'):
                    self.open_dir_btn.setEnabled(False)
            else:
                self.path_edit.setStyleSheet("")
                self.path_edit.setToolTip("")
                # 目录存在时启用打开目录按钮
                if hasattr(self, 'open_dir_btn'):
                    self.open_dir_btn.setEnabled(True)
        else:
            # 如果路径为空，则禁用确认按钮和打开目录按钮
            self.directory = ""
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
            if hasattr(self, 'open_dir_btn'):
                self.open_dir_btn.setEnabled(False)
            self.path_edit.setStyleSheet("")
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
            self.path_edit.setStyleSheet("")  # 清除可能的样式
            self.path_edit.setToolTip("")     # 清除可能的提示
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
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

    def accept(self):
        """确认导出"""
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

        # 注意：不要在这里调用super().accept()
        # 导出完成后会在export_completed中调用

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
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(False)
            self.button_box.button(QDialogButtonBox.Cancel).setEnabled(False)
            self._set_tab_runtime_status("正在批量导出")
            self._update_performance_diagnostics(clear_only=True)
        else:
            self.progress_cancel_btn.setEnabled(False)
            self.minimize_btn.setEnabled(False)
            self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
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
            pass

    def minimize_to_tab(self):
        """缩小到对应标签：隐藏窗口但保持后台导出"""
        if self._export_running:
            self._notify_non_blocking("已缩小到标签：导出任务仍在后台运行", 4000)
        self.hide()
        try:
            print(message)
        except Exception:
            pass

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
                self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)

        # 更新预览
        self.update_preview()
        self.update_traverse_mode_display()

    def _current_directory_text(self):
        """获取当前导出目录文本，优先使用输入框中的最新值。"""
        if hasattr(self, 'path_edit'):
            return self.path_edit.text().strip()
        return str(self.directory or '').strip()

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
                pass

    def save_config(self):
        """保存当前设置到当前标签页"""
        # 直接保存设置到document
        self.save_settings(mark_document=True)
        try:
            if hasattr(self.document, 'save_state'):
                self.document.save_state("保存批量导出设置")
        except Exception:
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
                self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)

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
                    # 窗口生命周期结束时忽略回调
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
                result = BatchExportDialog.execute_export_request(
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
            pass

        # 断开文档的进度信号连接
        if hasattr(self.document, 'export_progress_updated'):
            try:
                self.document.export_progress_updated.disconnect(self.update_progress)
            except:
                pass
        if hasattr(self.document, 'file_exported'):
            try:
                self.document.file_exported.disconnect(self.update_progress_text)
            except:
                pass
        if hasattr(self.document, 'export_stage_updated'):
            try:
                self.document.export_stage_updated.disconnect(self.update_export_stage)
            except:
                pass

        # 不立即结束UI：等待后台线程实际停止后再统一走 export_completed

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
                pass
        if hasattr(self.document, 'file_exported'):
            try:
                self.document.file_exported.disconnect(self.update_progress_text)
            except:
                pass
        if hasattr(self.document, 'export_stage_updated'):
            try:
                self.document.export_stage_updated.disconnect(self.update_export_stage)
            except:
                pass
        self._set_export_running_ui(False)
        self._update_performance_diagnostics(clear_only=False)
        try:
            self.recommend_dynamic_budget_params()
        except Exception:
            pass

        # 启用按钮
        self.button_box.button(QDialogButtonBox.Ok).setEnabled(True)
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
                pass
            message = f"导出完成：{self.path_edit.text()}"
            try:
                adj = getattr(self.document, '_last_export_adjustment', None)
                if adj and isinstance(adj, dict):
                    requested = adj.get('requested')
                    planned = adj.get('planned')
                    if requested and planned is not None and planned < requested:
                        message += f"（实际 {planned} / 请求 {requested}）"
            except Exception:
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
                if total_combinations > 1000:
                    self.calculated_count_label.setStyleSheet("color: #FF8A3D; font-weight: bold; margin-left: 10px;")
                    self.calculated_count_label.setText(f"(将导出 {total_combinations} 个组合 - 数量较大)")
                elif total_combinations > 10000:
                    self.calculated_count_label.setStyleSheet("color: #FF453A; font-weight: bold; margin-left: 10px;")
                    self.calculated_count_label.setText(f"(将导出 {total_combinations} 个组合 - 注意数量很大!)")
                else:
                    self.calculated_count_label.setStyleSheet("color: #2F9CF4; font-weight: bold; margin-left: 10px;")

            except Exception as e:
                print(f"计算组合数量失败: {e}")
                self.calculated_count_label.setText("(无法计算组合数)")
                self.calculated_count_label.setStyleSheet("color: #8E8E93; font-weight: bold; margin-left: 10px;")

                # 仍然禁用数量输入框
                self.count_spin.setEnabled(False)
                self.count_spin.setToolTip("遍历模式下将自动导出所有可能的组合")
        else:
            # 随机模式：恢复正常状态
            self.calculated_count_label.setText("")
            self.count_spin.setEnabled(True)
            self.count_spin.setToolTip("要导出的图像数量")

    def get_traverse_mode(self):
        """获取当前是否为遍历模式"""
        return self.traverse_export_check.isChecked()
