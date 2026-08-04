#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
图层大小匹配管理对话框
"""

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QListWidget,
    QListWidgetItem, QFrame, QCheckBox, QComboBox, QSpinBox, QDoubleSpinBox,
    QMessageBox, QSplitter, QAbstractItemView, QGridLayout, QSizePolicy
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from app.ui.dialog_a2 import DialogA2
from app.ui.collapsible_group import CollapsibleGroupBox


class LayerSizeMatchDialog(QDialog):
    """图层大小匹配管理器对话框。"""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.manager = getattr(document, "layer_size_match_manager", None)
        self._syncing_targets = False
        self.setWindowTitle("图层大小匹配管理器")
        self.setMinimumSize(860, 620)
        self._setup_ui()
        self.refresh_layers()
        self.refresh_relations()
        self._update_action_buttons()

    def _setup_ui(self):
        DialogA2.apply(self)

        root = QVBoxLayout(self)
        root.setContentsMargins(
            DialogA2.OUTER_MARGIN,
            DialogA2.OUTER_MARGIN,
            DialogA2.OUTER_MARGIN,
            DialogA2.OUTER_MARGIN,
        )
        root.setSpacing(DialogA2.CONTENT_GAP)

        self.title_label = QLabel("图层大小匹配管理器")
        self.title_label.setProperty("role", "dialogTitle")
        root.addWidget(self.title_label)

        splitter = QSplitter(Qt.Horizontal)
        root.addWidget(splitter, 1)

        self.left_card = self._make_card()
        left_layout = QVBoxLayout(self.left_card)
        left_layout.setContentsMargins(*DialogA2.CARD_MARGIN)
        left_layout.setSpacing(DialogA2.CARD_GAP)

        left_header = QHBoxLayout()
        left_title = QLabel("现有匹配关系")
        left_title.setProperty("role", "sectionTitle")
        self.relations_summary_label = QLabel("暂无关系")
        self.relations_summary_label.setProperty("role", "hint")
        left_header.addWidget(left_title)
        left_header.addStretch()
        left_header.addWidget(self.relations_summary_label)
        left_layout.addLayout(left_header)

        self.relations_list = QListWidget()
        self.relations_list.currentItemChanged.connect(self._on_relation_selected)
        self.relations_list.setMinimumHeight(220)
        left_layout.addWidget(self.relations_list, 1)

        # 自动遮罩区：关系级辅助设置，置于关系列表与全局设置之间。
        # 不给 stretch，避免挤压下方全局设置。
        self.auto_mask_group = self._build_auto_mask_group()
        left_layout.addWidget(self.auto_mask_group)

        global_panel = QFrame()
        global_panel.setProperty("role", "dialogSubPanel")
        global_layout = QHBoxLayout(global_panel)
        global_layout.setContentsMargins(10, 8, 10, 8)
        global_layout.setSpacing(DialogA2.CONTENT_GAP)
        global_title = QLabel("全局设置")
        global_title.setProperty("role", "fieldLabel")
        global_layout.addWidget(global_title)
        global_layout.addStretch()
        self.global_enabled_cb = QCheckBox("启用图层大小匹配")
        self.global_enabled_cb.setChecked(bool(getattr(self.manager, "global_enabled", False)))
        self.global_enabled_cb.clicked.connect(self._toggle_global_enabled)
        global_layout.addWidget(self.global_enabled_cb)
        left_layout.addWidget(global_panel)
        splitter.addWidget(self.left_card)

        self.right_card = self._make_card()
        right_layout = QVBoxLayout(self.right_card)
        right_layout.setContentsMargins(*DialogA2.CARD_MARGIN)
        right_layout.setSpacing(DialogA2.CARD_GAP)

        edit_header = QLabel("创建/编辑匹配关系")
        edit_header.setProperty("role", "sectionTitle")
        right_layout.addWidget(edit_header)

        self.source_combo = QComboBox()
        self.source_combo.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        self.source_combo.currentTextChanged.connect(self._on_source_changed)
        right_layout.addLayout(self._field_row("上层图层(A)", self.source_combo))

        target_header = QHBoxLayout()
        self.target_count_label = QLabel("下层匹配图层(B): 已选 0 个 / 可选 0 个")
        self.target_count_label.setProperty("role", "fieldLabel")
        target_header.addWidget(self.target_count_label)
        target_header.addStretch()
        self.select_all_targets_btn = QPushButton("全选")
        self.clear_targets_btn = QPushButton("清空")
        self.select_all_targets_btn.setFixedSize(DialogA2.SMALL_BUTTON_WIDTH, DialogA2.CONTROL_HEIGHT)
        self.clear_targets_btn.setFixedSize(DialogA2.SMALL_BUTTON_WIDTH, DialogA2.CONTROL_HEIGHT)
        self.select_all_targets_btn.clicked.connect(self._select_all_targets)
        self.clear_targets_btn.clicked.connect(self._clear_selected_targets)
        target_header.addWidget(self.select_all_targets_btn)
        target_header.addWidget(self.clear_targets_btn)
        right_layout.addLayout(target_header)

        self.target_list = QListWidget()
        self.target_list.setSelectionMode(QAbstractItemView.MultiSelection)
        self.target_list.setMinimumHeight(150)
        self.target_list.itemSelectionChanged.connect(self._on_target_selection_changed)
        right_layout.addWidget(self.target_list, 1)

        options_panel = QFrame()
        options_panel.setProperty("role", "dialogSubPanel")
        options_layout = QVBoxLayout(options_panel)
        options_layout.setContentsMargins(10, 8, 10, 8)
        options_layout.setSpacing(8)

        option_row = QHBoxLayout()
        self.relation_enabled_cb = QCheckBox("关系启用")
        self.relation_enabled_cb.setChecked(True)
        self.one_to_many_cb = QCheckBox("一对多匹配")
        self.one_to_many_cb.setChecked(False)
        self.one_to_many_cb.toggled.connect(self._on_one_to_many_toggled)
        self.auto_rotate_cb = QCheckBox("自动倾斜")
        self.auto_rotate_cb.setChecked(False)
        option_row.addWidget(self.relation_enabled_cb)
        option_row.addWidget(self.one_to_many_cb)
        option_row.addWidget(self.auto_rotate_cb)
        option_row.addStretch()
        options_layout.addLayout(option_row)

        padding_row = QHBoxLayout()
        padding_row.setSpacing(DialogA2.CONTENT_GAP)
        padding_row.addWidget(self._field_label("边缘外扩"))
        self.padding_spin = QSpinBox()
        self.padding_spin.setRange(0, 20)
        self.padding_spin.setValue(1)
        self.padding_spin.setSuffix(" px")
        self.padding_spin.setFixedSize(100, DialogA2.CONTROL_HEIGHT)
        self.padding_spin.setToolTip("为避免镂空边缘出现缝隙，可增加1~2像素外扩。")
        padding_row.addWidget(self.padding_spin)
        padding_row.addStretch()
        options_layout.addLayout(padding_row)
        right_layout.addWidget(options_panel)

        buttons_row = QHBoxLayout()
        buttons_row.setSpacing(DialogA2.CONTENT_GAP)
        self.add_btn = QPushButton("新增关系")
        self.update_btn = QPushButton("更新关系")
        self.remove_btn = QPushButton("删除关系")
        for btn in (self.add_btn, self.update_btn, self.remove_btn):
            btn.setFixedHeight(DialogA2.CONTROL_HEIGHT)
            buttons_row.addWidget(btn)
        self.add_btn.clicked.connect(self._create_relation)
        self.update_btn.clicked.connect(self._update_relation)
        self.remove_btn.clicked.connect(self._remove_relation)
        right_layout.addLayout(buttons_row)

        tip = QLabel(
            "说明: A 图层需含透明镂空区域；一对多开启后会按镂空排序自动映射。"
        )
        tip.setWordWrap(True)
        tip.setProperty("role", "hint")
        right_layout.addWidget(tip)

        splitter.addWidget(self.right_card)
        splitter.setSizes([340, 420])

        self.footer_frame = QFrame()
        self.footer_frame.setProperty("role", "dialogFooter")
        footer_layout = QHBoxLayout(self.footer_frame)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        self.refresh_btn = QPushButton("刷新")
        DialogA2.mark_secondary(self.refresh_btn)
        self.refresh_btn.clicked.connect(self._refresh_all)
        footer_layout.addWidget(self.refresh_btn)
        footer_layout.addStretch()
        self.close_btn = QPushButton("关闭")
        DialogA2.mark_secondary(self.close_btn)
        self.close_btn.clicked.connect(self.accept)
        footer_layout.addWidget(self.close_btn)
        root.addWidget(self.footer_frame)

    def _make_card(self):
        card = QFrame()
        card.setProperty("role", "dialogCard")
        return card

    def _field_label(self, text):
        label = QLabel(text)
        label.setProperty("role", "fieldLabel")
        label.setFixedWidth(DialogA2.FIELD_LABEL_WIDTH)
        return label

    def _field_row(self, label_text, widget):
        row = QHBoxLayout()
        row.setSpacing(DialogA2.CONTENT_GAP)
        row.addWidget(self._field_label(label_text))
        row.addWidget(widget, 1)
        return row

    def _build_auto_mask_group(self):
        """构建自动遮罩折叠区（左侧关系级辅助设置，默认收起）。

        结构：启用 / 遮罩类型 / 黑色阈值 常显；
        颜色容差、区域范围、保留边框、边缘优化、生成遮罩副本 收入
        独立的“高级设置”折叠区，保持整体紧凑。
        """
        group = CollapsibleGroupBox("自动遮罩（可选前置）", collapsed=True)

        basic = QVBoxLayout()
        basic.setSpacing(8)

        self.auto_mask_enabled_cb = QCheckBox("启用自动遮罩")
        self.auto_mask_enabled_cb.setChecked(False)
        self.auto_mask_enabled_cb.toggled.connect(self._on_auto_mask_toggled)
        basic.addWidget(self.auto_mask_enabled_cb)

        mode_row = QHBoxLayout()
        mode_row.setSpacing(DialogA2.CONTENT_GAP)
        mode_row.addWidget(self._field_label("遮罩类型"))
        self.auto_mask_mode_combo = QComboBox()
        self.auto_mask_mode_combo.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        self.auto_mask_mode_combo.addItem("黑色占位块", "black_placeholder")
        self.auto_mask_mode_combo.setCurrentIndex(0)
        self.auto_mask_mode_combo.setEnabled(False)  # 当前仅支持黑色占位块
        mode_row.addWidget(self.auto_mask_mode_combo, 1)
        basic.addLayout(mode_row)

        thr_row = QHBoxLayout()
        thr_row.setSpacing(DialogA2.CONTENT_GAP)
        thr_row.addWidget(self._field_label("黑色阈值"))
        self.auto_mask_threshold_spin = QSpinBox()
        self.auto_mask_threshold_spin.setRange(0, 128)
        self.auto_mask_threshold_spin.setValue(32)
        self.auto_mask_threshold_spin.setSuffix(" 亮度")
        self.auto_mask_threshold_spin.setFixedSize(110, DialogA2.CONTROL_HEIGHT)
        self.auto_mask_threshold_spin.setToolTip("RGB 任一通道亮度 <= 该值即视为黑色。")
        thr_row.addWidget(self.auto_mask_threshold_spin)
        thr_row.addStretch()
        basic.addLayout(thr_row)

        # 高级设置：不要在自动遮罩折叠组里再嵌套 CollapsibleGroupBox。
        # 嵌套折叠容器在左侧窄栏里容易出现 sizeHint 未及时上抬，导致控件堆叠/裁剪。
        adv_frame = QFrame()
        adv_frame.setProperty("role", "dialogSubPanel")
        adv = QVBoxLayout(adv_frame)
        adv.setContentsMargins(10, 8, 10, 8)
        adv.setSpacing(8)

        adv_title = QLabel("高级设置")
        adv_title.setProperty("role", "fieldLabel")
        adv.addWidget(adv_title)

        adv_grid = QGridLayout()
        adv_grid.setContentsMargins(0, 0, 0, 0)
        adv_grid.setHorizontalSpacing(8)
        adv_grid.setVerticalSpacing(8)

        def _compact_label(text):
            label = QLabel(text)
            label.setProperty("role", "fieldLabel")
            label.setMinimumWidth(68)
            label.setSizePolicy(QSizePolicy.Minimum, QSizePolicy.Fixed)
            return label

        def _compact_spin(spin):
            spin.setMinimumHeight(DialogA2.CONTROL_HEIGHT)
            spin.setMinimumWidth(86)
            spin.setMaximumWidth(112)
            spin.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
            return spin

        self.auto_mask_tolerance_spin = QSpinBox()
        self.auto_mask_tolerance_spin.setRange(0, 64)
        self.auto_mask_tolerance_spin.setValue(18)
        self.auto_mask_tolerance_spin.setToolTip("RGB 通道最大差异 <= 该值才视为纯色块，抑制彩色噪点。")
        adv_grid.addWidget(_compact_label("颜色容差"), 0, 0)
        adv_grid.addWidget(_compact_spin(self.auto_mask_tolerance_spin), 0, 1, Qt.AlignLeft)

        self.auto_mask_min_area_spin = QDoubleSpinBox()
        self.auto_mask_min_area_spin.setRange(0.1, 5.0)
        self.auto_mask_min_area_spin.setDecimals(1)
        self.auto_mask_min_area_spin.setValue(0.2)
        self.auto_mask_min_area_spin.setSuffix(" %")
        self.auto_mask_min_area_spin.setToolTip("小于该占比的黑色区不挖（过滤小黑字/小噪点）。")
        adv_grid.addWidget(_compact_label("最小区域"), 1, 0)
        adv_grid.addWidget(_compact_spin(self.auto_mask_min_area_spin), 1, 1, Qt.AlignLeft)

        self.auto_mask_max_area_spin = QDoubleSpinBox()
        self.auto_mask_max_area_spin.setRange(10.0, 100.0)
        self.auto_mask_max_area_spin.setDecimals(1)
        self.auto_mask_max_area_spin.setValue(75.0)
        self.auto_mask_max_area_spin.setSuffix(" %")
        self.auto_mask_max_area_spin.setToolTip("大于该占比的黑色区不挖（防止整张黑底被误挖）。")
        adv_grid.addWidget(_compact_label("最大区域"), 2, 0)
        adv_grid.addWidget(_compact_spin(self.auto_mask_max_area_spin), 2, 1, Qt.AlignLeft)
        adv_grid.setColumnStretch(2, 1)
        adv.addLayout(adv_grid)

        self.auto_mask_keep_border_cb = QCheckBox("保留边框")
        self.auto_mask_keep_border_cb.setChecked(True)
        self.auto_mask_keep_border_cb.setToolTip("腐蚀 1px 黑色 mask，避免吞掉白色描边。")
        self.auto_mask_edge_refine_cb = QCheckBox("边缘优化")
        self.auto_mask_edge_refine_cb.setChecked(True)
        self.auto_mask_edge_refine_cb.setToolTip("轻微模糊 mask 边缘，减少黑边锯齿。")
        adv_flags = QHBoxLayout()
        adv_flags.setSpacing(DialogA2.CONTENT_GAP)
        adv_flags.addWidget(self.auto_mask_keep_border_cb)
        adv_flags.addWidget(self.auto_mask_edge_refine_cb)
        adv_flags.addStretch()
        adv.addLayout(adv_flags)

        self.bake_mask_btn = QPushButton("生成遮罩副本")
        DialogA2.mark_secondary(self.bake_mask_btn)
        self.bake_mask_btn.setFixedHeight(DialogA2.CONTROL_HEIGHT)
        self.bake_mask_btn.setMaximumWidth(132)
        self.bake_mask_btn.setToolTip("复制当前源图层并永久应用透明挖孔，原图层保持不变。")
        self.bake_mask_btn.clicked.connect(self._bake_auto_mask_copy)
        adv.addWidget(self.bake_mask_btn)
        adv_frame.setMinimumHeight(176)
        basic.addWidget(adv_frame)

        content = QFrame()
        content.setLayout(basic)
        group.set_content_widget(content)
        self._sync_auto_mask_enabled_state()
        return group

    def _sync_auto_mask_enabled_state(self):
        enabled = self.auto_mask_enabled_cb.isChecked()
        self.auto_mask_mode_combo.setEnabled(enabled)
        self.auto_mask_threshold_spin.setEnabled(enabled)
        self.auto_mask_tolerance_spin.setEnabled(enabled)
        self.auto_mask_min_area_spin.setEnabled(enabled)
        self.auto_mask_max_area_spin.setEnabled(enabled)
        self.auto_mask_keep_border_cb.setEnabled(enabled)
        self.auto_mask_edge_refine_cb.setEnabled(enabled)

    def _on_auto_mask_toggled(self, _checked):
        self._sync_auto_mask_enabled_state()
        self._update_action_buttons()

    def _collect_auto_mask(self):
        """从 UI 收集自动遮罩参数为 dict。"""
        return {
            "auto_mask_enabled": bool(self.auto_mask_enabled_cb.isChecked()),
            "auto_mask_mode": str(self.auto_mask_mode_combo.currentData() or "black_placeholder"),
            "auto_mask_threshold": int(self.auto_mask_threshold_spin.value()),
            "auto_mask_tolerance": int(self.auto_mask_tolerance_spin.value()),
            "auto_mask_min_area_ratio": float(self.auto_mask_min_area_spin.value()) / 100.0,
            "auto_mask_max_area_ratio": float(self.auto_mask_max_area_spin.value()) / 100.0,
            "auto_mask_keep_border": bool(self.auto_mask_keep_border_cb.isChecked()),
            "auto_mask_edge_refine": bool(self.auto_mask_edge_refine_cb.isChecked()),
        }

    def _apply_auto_mask_to_ui(self, data):
        """用 relation 数据回填自动遮罩 UI。"""
        self.auto_mask_enabled_cb.setChecked(bool(data.get("auto_mask_enabled", False)))
        mode = str(data.get("auto_mask_mode", "black_placeholder"))
        idx = self.auto_mask_mode_combo.findData(mode)
        if idx >= 0:
            self.auto_mask_mode_combo.setCurrentIndex(idx)
        else:
            self.auto_mask_mode_combo.setCurrentIndex(0)
        self.auto_mask_threshold_spin.setValue(max(0, int(data.get("auto_mask_threshold", 32))))
        self.auto_mask_tolerance_spin.setValue(max(0, int(data.get("auto_mask_tolerance", 18))))
        self.auto_mask_min_area_spin.setValue(float(data.get("auto_mask_min_area_ratio", 0.002)) * 100.0)
        self.auto_mask_max_area_spin.setValue(float(data.get("auto_mask_max_area_ratio", 0.75)) * 100.0)
        self.auto_mask_keep_border_cb.setChecked(bool(data.get("auto_mask_keep_border", True)))
        self.auto_mask_edge_refine_cb.setChecked(bool(data.get("auto_mask_edge_refine", True)))
        self._sync_auto_mask_enabled_state()

    def _bake_auto_mask_copy(self):
        """可选烘焙：复制当前源图层并永久应用透明挖孔，原图层保持不变。"""
        if not self.manager or not hasattr(self.document, "add_layer"):
            QMessageBox.information(self, "提示", "当前文档不支持生成遮罩副本。")
            return
        src = self.source_combo.currentText().strip()
        if not src:
            QMessageBox.information(self, "提示", "请先选择上层图层(A)。")
            return
        layer = None
        for l in getattr(self.document, "layers", []) or []:
            if str(getattr(l, "name", "")).strip() == src and not hasattr(l, "get_text_lines"):
                layer = l
                break
        if layer is None:
            QMessageBox.information(self, "提示", "未找到对应的图像源图层。")
            return
        # 取源图层 surface 并应用自动遮罩
        try:
            fr = getattr(self.document, "fast_renderer", None) or getattr(self.document, "renderer", None)
            if fr is None and hasattr(self.document, "_renderer"):
                fr = self.document._renderer
            if fr is None:
                from app.utils.fast_renderer import get_global_fast_renderer
                try:
                    fr = get_global_fast_renderer()
                except Exception:
                    fr = None
            if fr is None:
                QMessageBox.information(self, "提示", "无法访问渲染器，无法生成遮罩副本。")
                return
            surface = fr._get_layer_surface_cached(layer, self.document, False)
            if surface is None:
                QMessageBox.information(self, "提示", "源图层渲染失败。")
                return
            relation = self._collect_auto_mask()
            masked = fr._apply_auto_mask(surface, relation)
        except Exception as exc:  # pragma: no cover - 防御性
            QMessageBox.warning(self, "错误", f"生成遮罩副本失败: {exc}")
            return
        # 保存为 PNG 副本
        import os
        base_name = f"{src}_自动遮罩"
        doc_path = getattr(self.document, "current_file_path", None) or getattr(self.document, "file_path", None)
        out_dir = os.path.dirname(doc_path) if doc_path else os.getcwd()
        if not os.path.isdir(out_dir):
            out_dir = os.getcwd()
        out_path = os.path.join(out_dir, f"{base_name}.png")
        n = 1
        while os.path.exists(out_path):
            out_path = os.path.join(out_dir, f"{base_name}_{n}.png")
            n += 1
        try:
            masked.save(out_path, "PNG")
        except Exception as exc:  # pragma: no cover
            QMessageBox.warning(self, "错误", f"保存遮罩副本失败: {exc}")
            return
        w = int(getattr(masked, "width", 1) or 1)
        h = int(getattr(masked, "height", 1) or 1)
        self.document.add_layer(
            name=base_name,
            x=int(getattr(layer, "x", 0) or 0),
            y=int(getattr(layer, "y", 0) or 0),
            width=w,
            height=h,
            image_source=out_path,
            use_original_size=True,
            is_folder=False,
        )
        QMessageBox.information(self, "完成", f"已生成遮罩副本：\n{out_path}")
        self._invalidate_document_render()
        if hasattr(self, "refresh_layers"):
            self.refresh_layers()

    def refresh_layers(self):
        self.source_combo.clear()
        self.target_list.clear()
        layers = getattr(self.document, "layers", []) or []
        for layer in layers:
            if hasattr(layer, "get_text_lines"):  # 跳过文字图层
                continue
            name = str(getattr(layer, "name", "")).strip()
            if not name:
                continue
            self.source_combo.addItem(name)
            self.target_list.addItem(QListWidgetItem(name))
        self._sync_target_constraints()
        self._update_action_buttons()

    def refresh_relations(self):
        self.relations_list.clear()
        if not self.manager or not getattr(self.manager, "relations", None):
            item = QListWidgetItem("暂无匹配关系")
            item.setFlags(item.flags() & ~Qt.ItemIsSelectable)
            self.relations_list.addItem(item)
            if hasattr(self, "relations_summary_label"):
                self.relations_summary_label.setText("暂无关系")
            return
        if hasattr(self, "relations_summary_label"):
            self.relations_summary_label.setText(f"{len(self.manager.relations)} 条")
        for relation in self.manager.relations:
            src = relation.get("source_layer_name", "")
            targets = relation.get("target_layer_names", None)
            if not isinstance(targets, list) or not targets:
                legacy = str(relation.get("target_layer_name", "")).strip()
                targets = [legacy] if legacy else []
            enabled = "启用" if relation.get("enabled", True) else "禁用"
            padding = int(relation.get("padding", 1))
            one_to_many = bool(relation.get("one_to_many", False))
            auto_rotate = bool(relation.get("auto_rotate", False))
            mode_text = "一对多" if one_to_many else "一对一"
            tilt_text = "自动倾斜" if auto_rotate else "不倾斜"
            mask_text = "自动遮罩" if bool(relation.get("auto_mask_enabled", False)) else "无遮罩"
            dst_text = ", ".join([str(t) for t in targets]) if targets else "无目标"
            text = f"{src} -> [{dst_text}]  ({mode_text}, {tilt_text}, {mask_text}, {enabled}, 外扩{padding}px)"
            item = QListWidgetItem(text)
            item.setData(Qt.UserRole, dict(relation))
            self.relations_list.addItem(item)
        self._update_action_buttons()

    def _get_selected_targets(self):
        targets = []
        for item in self.target_list.selectedItems():
            name = str(item.text() or "").strip()
            if name and name not in targets:
                targets.append(name)
        return targets

    def _on_source_changed(self, _text):
        self._sync_target_constraints()
        self._update_action_buttons()

    def _sync_target_constraints(self):
        """上层图层不能在下层匹配列表中被选择。"""
        if self._syncing_targets:
            return
        self._syncing_targets = True
        try:
            source_name = self.source_combo.currentText().strip()
            disabled_color = QColor("#8b8b92")
            normal_color = QColor("#d0d0d0")
            for i in range(self.target_list.count()):
                item = self.target_list.item(i)
                if item is None:
                    continue
                is_same = (item.text().strip() == source_name and source_name != "")
                flags = item.flags()
                if is_same:
                    item.setSelected(False)
                    item.setFlags((flags & ~Qt.ItemIsSelectable & ~Qt.ItemIsEnabled))
                    item.setForeground(disabled_color)
                    item.setToolTip("该图层已作为上层图层(A)，不能作为下层匹配图层。")
                else:
                    item.setFlags(flags | Qt.ItemIsSelectable | Qt.ItemIsEnabled)
                    item.setForeground(normal_color)
                    item.setToolTip("")
        finally:
            self._syncing_targets = False
        self._update_target_count_label()

    def _on_one_to_many_toggled(self, enabled: bool):
        # 一对一模式下，最多保留一个已选目标，减少误操作
        if not enabled:
            selected = self.target_list.selectedItems()
            for item in selected[1:]:
                item.setSelected(False)
        self._update_action_buttons()

    def _on_target_selection_changed(self):
        if self._syncing_targets:
            return
        # 一对一时强制只保留最后一个选择
        if not self.one_to_many_cb.isChecked():
            selected = self.target_list.selectedItems()
            if len(selected) > 1:
                keep = selected[-1]
                self._syncing_targets = True
                try:
                    for item in selected:
                        item.setSelected(item is keep)
                finally:
                    self._syncing_targets = False
        self._update_target_count_label()
        self._update_action_buttons()

    def _select_all_targets(self):
        if not self.one_to_many_cb.isChecked():
            QMessageBox.information(self, "提示", "当前是一对一模式，请先开启一对多匹配再执行全选。")
            return
        self._syncing_targets = True
        try:
            for i in range(self.target_list.count()):
                item = self.target_list.item(i)
                if item.flags() & Qt.ItemIsEnabled:
                    item.setSelected(True)
        finally:
            self._syncing_targets = False
        self._update_target_count_label()
        self._update_action_buttons()

    def _clear_selected_targets(self):
        self._syncing_targets = True
        try:
            for item in self.target_list.selectedItems():
                item.setSelected(False)
        finally:
            self._syncing_targets = False
        self._update_target_count_label()
        self._update_action_buttons()

    def _update_target_count_label(self):
        if not hasattr(self, "target_count_label"):
            return
        selectable_count = 0
        selected_count = 0
        for i in range(self.target_list.count()):
            item = self.target_list.item(i)
            if item is None:
                continue
            is_enabled = bool(item.flags() & Qt.ItemIsEnabled)
            if is_enabled:
                selectable_count += 1
            if item.isSelected():
                selected_count += 1
        self.target_count_label.setText(f"下层匹配图层(B): 已选 {selected_count} 个 / 可选 {selectable_count} 个")

    def _update_action_buttons(self):
        selected_targets = self._get_selected_targets()
        has_source = bool(self.source_combo.currentText().strip())
        has_selection = bool(selected_targets) and has_source
        current_data = None
        current_item = self.relations_list.currentItem()
        if current_item is not None:
            current_data = current_item.data(Qt.UserRole)
        self.add_btn.setEnabled(has_selection)
        self.update_btn.setEnabled(has_selection and isinstance(current_data, dict))
        self.remove_btn.setEnabled(isinstance(current_data, dict))
        self.select_all_targets_btn.setEnabled(self.one_to_many_cb.isChecked())
        self._update_target_count_label()

    def _toggle_global_enabled(self):
        if not self.manager:
            return
        self.manager.set_global_enabled(self.global_enabled_cb.isChecked())
        self._invalidate_document_render()

    def _create_relation(self):
        if not self.manager:
            return
        src = self.source_combo.currentText().strip()
        targets = self._get_selected_targets()
        if not src or not targets:
            QMessageBox.warning(self, "提示", "请选择有效的图层A和至少一个图层B。")
            return
        if any(src == t for t in targets):
            QMessageBox.warning(self, "提示", "图层A和图层B不能是同一图层。")
            return
        if not self.one_to_many_cb.isChecked() and len(targets) > 1:
            targets = [targets[0]]
        self.manager.add_relation(
            source_layer_name=src,
            target_layer_names=targets,
            enabled=self.relation_enabled_cb.isChecked(),
            padding=self.padding_spin.value(),
            one_to_many=self.one_to_many_cb.isChecked(),
            auto_rotate=self.auto_rotate_cb.isChecked(),
            auto_mask=self._collect_auto_mask(),
        )
        self.refresh_relations()
        self._invalidate_document_render()
        self._update_action_buttons()

    def _update_relation(self):
        item = self.relations_list.currentItem()
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            return
        rid = str(data.get("id", ""))
        if not rid:
            return
        src = self.source_combo.currentText().strip()
        targets = self._get_selected_targets()
        if not src or not targets or any(src == t for t in targets):
            QMessageBox.warning(self, "提示", "请设置有效的图层A和至少一个不同的图层B。")
            return
        if not self.one_to_many_cb.isChecked() and len(targets) > 1:
            targets = [targets[0]]
        self.manager.update_relation(
            relation_id=rid,
            source_layer_name=src,
            target_layer_names=targets,
            enabled=self.relation_enabled_cb.isChecked(),
            padding=self.padding_spin.value(),
            one_to_many=self.one_to_many_cb.isChecked(),
            auto_rotate=self.auto_rotate_cb.isChecked(),
            auto_mask=self._collect_auto_mask(),
        )
        self.refresh_relations()
        self._invalidate_document_render()
        self._update_action_buttons()

    def _remove_relation(self):
        item = self.relations_list.currentItem()
        if not item:
            return
        data = item.data(Qt.UserRole)
        if not isinstance(data, dict):
            return
        rid = str(data.get("id", ""))
        if not rid:
            return
        self.manager.remove_relation(rid)
        self.refresh_relations()
        self._invalidate_document_render()
        self._update_action_buttons()

    def _on_relation_selected(self, current, _previous):
        if not current:
            return
        data = current.data(Qt.UserRole)
        if not isinstance(data, dict):
            return
        src = str(data.get("source_layer_name", ""))
        targets = data.get("target_layer_names", None)
        if not isinstance(targets, list) or not targets:
            legacy = str(data.get("target_layer_name", ""))
            targets = [legacy] if legacy else []
        enabled = bool(data.get("enabled", True))
        one_to_many = bool(data.get("one_to_many", False))
        auto_rotate = bool(data.get("auto_rotate", False))
        padding = int(data.get("padding", 1))
        src_idx = self.source_combo.findText(src)
        if src_idx >= 0:
            self.source_combo.setCurrentIndex(src_idx)
        self._sync_target_constraints()
        for i in range(self.target_list.count()):
            item = self.target_list.item(i)
            item.setSelected(item.text() in targets)
        self.relation_enabled_cb.setChecked(enabled)
        self.one_to_many_cb.setChecked(one_to_many)
        self.auto_rotate_cb.setChecked(auto_rotate)
        self.padding_spin.setValue(max(0, padding))
        self._apply_auto_mask_to_ui(data)
        self._update_action_buttons()

    def _refresh_all(self):
        self.refresh_layers()
        self.refresh_relations()
        self._update_action_buttons()

    def _invalidate_document_render(self):
        if hasattr(self.document, "_invalidate_render_cache"):
            self.document._invalidate_render_cache()
        if hasattr(self.document, "document_changed"):
            self.document.document_changed.emit()
