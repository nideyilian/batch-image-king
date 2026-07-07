from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                           QPushButton, QListWidget, QListWidgetItem, QCheckBox,
                           QAbstractItemView, QInputDialog, QMenu, QApplication,
                           QDialog, QDialogButtonBox, QTextEdit, QSizePolicy)
from PySide6.QtCore import Qt, Signal, QTimer, QRect, QPoint
from PySide6.QtGui import QIcon, QPixmap, QColor, QPainter, QDropEvent, QPen, QBrush
import sys
import os
import builtins

_LAYER_PANEL_DEBUG = (
    os.environ.get("BTPW_LAYER_PANEL_DEBUG", "0") == "1"
    or os.environ.get("BTPW_UI_DEBUG", "0") == "1"
)
_LAYER_PANEL_ALWAYS_LOG_KEYWORDS = (
    "出错", "错误", "失败", "警告", "异常",
    "error", "failed", "warning", "exception", "Traceback",
)


def print(*args, **kwargs):
    if _LAYER_PANEL_DEBUG:
        builtins.print(*args, **kwargs)
        return
    try:
        message = " ".join(str(arg) for arg in args)
    except Exception:
        message = ""
    if any(keyword in message for keyword in _LAYER_PANEL_ALWAYS_LOG_KEYWORDS):
        builtins.print(*args, **kwargs)

# 注释掉冲突的导入，使用本文件中定义的类
# sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
# from app.views.layer_panel import LayerPanel, LayerItem
try:
    from app.models.shaped_layer_new import ShapedLayer
except ImportError:
    from app.models.shaped_layer import ShapedLayer

from app.ui.icon_manager import IconManager, create_random_button, create_lock_button, create_visibility_button
from app.ui.visual_hierarchy import VisualHierarchy
from app.ui.shaped_layer_panel import ShapedLayerPanel
from app.models.layer_group import LayerGroup
from app.utils.layer_tree import (
    display_entries,
    get_parent_group_id,
    is_effectively_locked,
    is_layer_group,
    set_parent_group_id,
)

from app.ui.drag_drop_layer_list import DragDropLayerList
from app.ui.layer_item import LayerItem

class LayerPanelOps(object):
    """Mixin for layer_panel_ops (split from LayerPanel)."""

    def show_context_menu(self, position):
        """显示图层右键菜单"""
        if not self.document or not self.layer_list.count():
            return

        menu = QMenu()

        # 获取当前选中项
        item = self.layer_list.itemAt(position)
        if not item:
            # 如果没有点击在图层项上，提供有限选项
            add_action = menu.addAction("添加图层")

            # 如果有剪贴板内容，允许粘贴
            paste_action = None
            if self._get_main_window() and hasattr(self._get_main_window(), 'layer_clipboard') and self._get_main_window().layer_clipboard:
                paste_action = menu.addAction("粘贴图层")

            action = menu.exec_(self.layer_list.mapToGlobal(position))
            if action == add_action:
                self.add_layer()
            elif paste_action and action == paste_action:
                self._paste_layer()
            return

        # 确定图层索引（不自动选中，保持当前选中状态）
        actual_index = self._actual_index_for_item(item)
        if not (0 <= actual_index < len(self.document.layers)):
            return

        # 获取右键点击的图层实例（不改变当前选中状态）
        layer = self.document.layers[actual_index]

        # 基础操作
        rename_action = menu.addAction("重命名")
        edit_text_action = None
        try:
            from app.models.text_layer import TextLayer
            if isinstance(layer, TextLayer):
                edit_text_action = menu.addAction("编辑文案")
        except Exception:
            edit_text_action = None

        menu.addSeparator()

        selected_indices = self.get_selected_indices()
        has_multi_selection = len(selected_indices) > 1
        if has_multi_selection:
            multi_menu = menu.addMenu(f"多图层操作 ({len(selected_indices)})")
            group_action = multi_menu.addAction("从所选图层建立组")
            show_selected_action = multi_menu.addAction("显示选中图层")
            hide_selected_action = multi_menu.addAction("隐藏选中图层")
            multi_menu.addSeparator()
            lock_selected_action = multi_menu.addAction("锁定选中图层")
            unlock_selected_action = multi_menu.addAction("解锁选中图层")
            multi_menu.addSeparator()
            distribute_h_action = multi_menu.addAction("水平等距分布")
            distribute_v_action = multi_menu.addAction("垂直等距分布")
            multi_menu.addSeparator()
            same_size_action = multi_menu.addAction("匹配首选图层尺寸")
        else:
            group_action = None
            show_selected_action = None
            hide_selected_action = None
            lock_selected_action = None
            unlock_selected_action = None
            distribute_h_action = None
            distribute_v_action = None
            same_size_action = None

        # 复制粘贴操作
        copy_action = menu.addAction("复制图层")

        # 检查是否有剪贴板内容
        main_window = self._get_main_window()
        paste_action = None
        if main_window and hasattr(main_window, 'layer_clipboard') and main_window.layer_clipboard:
            paste_action = menu.addAction("粘贴图层")

        menu.addSeparator()

        # 图层样式操作
        copy_style_action = menu.addAction("复制图层样式")

        # 检查是否有样式剪贴板内容
        paste_style_action = None
        if main_window and hasattr(main_window, 'layer_style_clipboard') and main_window.layer_style_clipboard:
            paste_style_action = menu.addAction("粘贴图层样式")

        menu.addSeparator()

        # 图层操作
        ungroup_action = None
        if is_layer_group(layer):
            ungroup_action = menu.addAction("解散组")
        delete_action = menu.addAction("删除图层")

        menu.addSeparator()

        # 随机与锁定
        randomize_action = menu.addAction("随机更换图像")
        randomize_action.setToolTip("同名图层将选择相同核心名称的图片")

        lock_action = menu.addAction("锁定图层" if not layer.locked else "解锁图层")

        menu.addSeparator()

        # 图层效果选项
        effects_action = menu.addAction("编辑图层效果...")

        # 异形图层编辑选项
        try:
            from app.models.shaped_layer_new import ShapedLayer
        except ImportError:
            from app.models.shaped_layer import ShapedLayer
        if isinstance(layer, ShapedLayer):
            shaped_action = menu.addAction("编辑异形图层...")

        # 执行菜单并获取所选操作
        action = menu.exec_(self.layer_list.mapToGlobal(position))

        # 处理用户选择（操作被右键点击的图层，不改变当前选中状态）
        if has_multi_selection and action == group_action:
            self.group_selected_layers()
        elif ungroup_action and action == ungroup_action:
            self.ungroup_selected_groups()
        elif action == rename_action:
            self.rename_layer_at_index(actual_index)
        elif edit_text_action and action == edit_text_action:
            self.edit_text_layer_at_index(actual_index)
        elif has_multi_selection and action == show_selected_action:
            self.set_selected_layers_visible(True)
        elif has_multi_selection and action == hide_selected_action:
            self.set_selected_layers_visible(False)
        elif has_multi_selection and action == lock_selected_action:
            self.set_selected_layers_locked(True)
        elif has_multi_selection and action == unlock_selected_action:
            self.set_selected_layers_locked(False)
        elif has_multi_selection and action == distribute_h_action:
            self.align_layers("distribute_horizontal")
        elif has_multi_selection and action == distribute_v_action:
            self.align_layers("distribute_vertical")
        elif has_multi_selection and action == same_size_action:
            self.align_layers("same_size")
        elif action == copy_action:
            self._copy_layer_at_index(actual_index)
        elif paste_action and action == paste_action:
            self._paste_layer()
        elif action == copy_style_action:
            self._copy_layer_style_at_index(actual_index)
        elif paste_style_action and action == paste_style_action:
            self._paste_layer_style_at_index(actual_index)
        elif action == delete_action:
            self.delete_layer_at_index(actual_index)
        elif action == randomize_action:
            self.randomize_layer_at_index(actual_index)
        elif action == lock_action:
            self.toggle_layer_lock_at_index(actual_index)
        elif action == effects_action:
            self.edit_layer_effects_at_index(actual_index)
        elif 'shaped_action' in locals() and action == shaped_action:
            self.edit_shaped_layer_at_index(actual_index)

    def edit_text_layer_at_index(self, index):
        """编辑指定索引的文字图层文案。"""
        try:
            if not self.document or index < 0 or index >= len(self.document.layers):
                return

            layer = self.document.layers[index]
            from app.models.text_layer import TextLayer
            if not isinstance(layer, TextLayer):
                return

            main_window = self._get_main_window()
            if main_window and hasattr(main_window, 'edit_text_layer'):
                main_window.edit_text_layer(index)

        except Exception as e:
            print(f"编辑文字图层文案时出错: {e}")

    def edit_shaped_layer_at_index(self, index):
        """编辑指定索引的异形图层"""
        try:
            if not self.document or index < 0 or index >= len(self.document.layers):
                return

            layer = self.document.layers[index]
            if not isinstance(layer, ShapedLayer):
                return

            # 选中该图层，属性面板会自动显示异形图层控件
            self.document.selected_layer_index = index

            # 获取主窗口并确保属性面板可见
            main_window = self._get_main_window()
            if main_window and hasattr(main_window, 'properties_dock'):
                main_window.properties_dock.show()
                main_window.properties_dock.raise_()

        except Exception as e:
            print(f"编辑异形图层时出错: {e}")

    def _get_main_window(self):
        """获取主窗口引用"""
        parent = self.parent()
        while parent:
            if hasattr(parent, 'layer_clipboard'):  # 主窗口特征
                return parent
            parent = parent.parent()
        return None

    def _copy_layer(self):
        """复制图层"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'copy_layer'):
            main_window.copy_layer()

    def _paste_layer(self):
        """粘贴图层"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'paste_layer'):
            main_window.paste_layer()

    def _copy_layer_style(self):
        """复制图层样式"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'copy_layer_style'):
            main_window.copy_layer_style()

    def _paste_layer_style(self):
        """粘贴图层样式"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'paste_layer_style'):
            main_window.paste_layer_style()

    def rename_layer(self):
        """重命名图层"""
        if self.document.selected_layer_index < 0:
            return

        layer = self.document.layers[self.document.selected_layer_index]

        new_name, ok = QInputDialog.getText(self, "重命名图层",
                                          "图层名称:", text=layer.name)
        if ok and new_name:
            layer.name = new_name
            self._schedule_update()

    def randomize_layer(self):
        """随机化选中的图层图像"""
        if self.document.selected_layer_index < 0:
            return

        layer = self.document.layers[self.document.selected_layer_index]
        self._randomize_single_layer_with_restrictions(layer)
        self.document.document_changed.emit()

    def edit_layer_effects(self):
        if self.document.selected_layer_index < 0:
            return
        from app.ui.layer_effects_dialog import LayerEffectsDialog
        dialog = LayerEffectsDialog(self.document, self)
        if dialog.exec():
            self.document.document_changed.emit()

    def edit_layer_effects_at_index(self, layer_index):
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return
        original_selected_index = self.document.selected_layer_index
        self.document.selected_layer_index = layer_index
        try:
            from app.ui.layer_effects_dialog import LayerEffectsDialog
            dialog = LayerEffectsDialog(self.document, self)
            if dialog.exec():
                self.document.document_changed.emit()
        finally:
            self.document.selected_layer_index = original_selected_index

    def edit_shaped_layer_at_index(self, layer_index):
        """编辑指定索引的异形图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        try:
            from app.models.shaped_layer_new import ShapedLayer
        except ImportError:
            from app.models.shaped_layer import ShapedLayer

        layer = self.document.layers[layer_index]
        if not isinstance(layer, ShapedLayer):
            return

        original_selected_index = self.document.selected_layer_index
        self.document.selected_layer_index = layer_index
        try:
            from app.ui.shaped_layer_panel import ShapedLayerDialog
            dialog = ShapedLayerDialog(layer, self)
            if dialog.exec():
                self.document.document_changed.emit()
        finally:
            self.document.selected_layer_index = original_selected_index

    def rename_layer_at_index(self, layer_index):
        """重命名指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        layer = self.document.layers[layer_index]
        main_window = self._get_main_window()
        if main_window:
            # 临时选中要重命名的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.rename_layer()
            finally:
                self.document.selected_layer_index = original_selected_index

    def _copy_layer_at_index(self, layer_index):
        """复制指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        main_window = self._get_main_window()
        if main_window:
            # 临时选中要复制的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.copy_layer()
            finally:
                self.document.selected_layer_index = original_selected_index

    def _copy_layer_style_at_index(self, layer_index):
        """复制指定索引图层的样式"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        main_window = self._get_main_window()
        if main_window:
            # 临时选中要复制样式的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.copy_layer_style()
            finally:
                self.document.selected_layer_index = original_selected_index

    def _paste_layer_style_at_index(self, layer_index):
        """粘贴样式到指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        main_window = self._get_main_window()
        if main_window:
            # 临时选中要粘贴样式的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.paste_layer_style()
            finally:
                self.document.selected_layer_index = original_selected_index

    def delete_layer_at_index(self, layer_index):
        """删除指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        main_window = self._get_main_window()
        if main_window:
            # 临时选中要删除的图层
            original_selected_index = self.document.selected_layer_index
            self.document.selected_layer_index = layer_index
            try:
                main_window.delete_layer()
            finally:
                # 删除后不需要恢复选中状态，因为图层已被删除
                pass

    def randomize_layer_at_index(self, layer_index):
        """随机化指定索引的图层"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        layer = self.document.layers[layer_index]
        self._randomize_single_layer_with_restrictions(layer)
        self.document.document_changed.emit()

    def _randomize_single_layer_with_restrictions(self, layer):
        """使用文件限制随机化单个图层"""
        try:
            # 检查是否是文字图层
            from app.models.text_layer import TextLayer
            if isinstance(layer, TextLayer):
                layer.randomize_text()
                print(f"[图层面板] 随机化文字图层: {layer.name}")
                return

            # 普通图层处理
            # 首先确保绑定管理器分析了文件限制
            if hasattr(self.document, 'binding_manager') and self.document.binding_manager.global_enabled:
                print(f"[图层面板] 为单图层随机化分析文件限制...")
                self.document.binding_manager.analyze_and_restrict_layer_files(self.document.layers)

                # 检查是否是绑定图层
                if self.document.binding_manager.is_layer_bound(layer):
                    print(f"[图层面板] 图层 '{layer.name}' 是绑定图层，使用绑定组随机化")
                    # 绑定图层：使用绑定管理器处理
                    bound_layers_mapping = self.document.binding_manager.randomize_bound_layers(self.document.layers)
                    if id(layer) in bound_layers_mapping:
                        print(f"[图层面板] 绑定图层 '{layer.name}' 已更新")
                    else:
                        print(f"[图层面板] 警告：绑定图层 '{layer.name}' 未在绑定结果中")
                else:
                    # 非绑定图层：使用文件限制
                    restricted_files = self.document.binding_manager.get_layer_file_restrictions(layer)
                    if restricted_files:
                        print(f"[图层面板] 图层 '{layer.name}' 使用文件限制随机化，可选文件: {len(restricted_files)} 个")
                        layer.get_random_image(force_random=True, restrict_to_bound_files=restricted_files)
                    else:
                        print(f"[图层面板] 图层 '{layer.name}' 无文件限制，正常随机化")
                        layer.get_random_image(force_random=True)
            else:
                # 没有绑定管理器或未启用，正常随机化
                print(f"[图层面板] 图层 '{layer.name}' 正常随机化（无绑定管理器）")
                layer.get_random_image(force_random=True)

        except Exception as e:
            print(f"[图层面板] 随机化图层 '{layer.name}' 时出错: {e}")
            import traceback
            traceback.print_exc()
            # 出错时回退到正常随机化
            layer.get_random_image(force_random=True)

    def toggle_layer_lock_at_index(self, layer_index):
        """切换指定索引图层的锁定状态"""
        if layer_index < 0 or layer_index >= len(self.document.layers):
            return

        layer = self.document.layers[layer_index]
        layer.locked = not layer.locked
        self.document.document_changed.emit()
        self._schedule_update()

    def toggle_layer_lock(self):
        """切换当前选中图层的锁定状态"""
        if self.document.selected_layer_index < 0:
            return

        layer = self.document.layers[self.document.selected_layer_index]
        layer.locked = not layer.locked

        # 通知文档已更改
        self.document.document_changed.emit()

        # 更新图层列表
        self._schedule_update()

    def on_layer_moved(self, source_index, target_index):
        """处理图层拖放移动"""
        source_actual_index = self._actual_index_for_row(source_index)
        target_actual_index = self._actual_index_for_row(target_index)
        if not (0 <= source_actual_index < len(self.document.layers)) or not (0 <= target_actual_index < len(self.document.layers)):
            self._schedule_update()
            return
        selected_indices = self.get_selected_indices()

        if source_actual_index in selected_indices and len(selected_indices) > 1:
            selected_indices = [
                idx for idx in selected_indices
                if 0 <= idx < len(self.document.layers) and not getattr(self.document.layers[idx], 'locked', False)
            ]
            if not selected_indices:
                return
            self.document.save_state("批量拖放重排序图层前")
            selected_objects = [self.document.layers[idx] for idx in sorted(selected_indices)]
            remaining = [
                layer for idx, layer in enumerate(self.document.layers)
                if idx not in set(selected_indices)
            ]
            removed_before_target = sum(1 for idx in selected_indices if idx < target_actual_index)
            insert_at = max(0, min(len(remaining), target_actual_index - removed_before_target))
            self.document.layers = remaining[:insert_at] + selected_objects + remaining[insert_at:]
            new_selection = []
            for layer in selected_objects:
                new_idx = self.document.layers.index(layer)
                new_selection.append(new_idx)
            if hasattr(self.document, 'select_layers'):
                self.document.select_layers(new_selection, primary_index=new_selection[0] if new_selection else -1)
            self.document.layer_changed.emit()
            self.document.document_changed.emit()
            self.document.save_state("批量拖放重排序图层")
        else:
            # 移动图层
            self.document.move_layer(source_actual_index, target_actual_index)
            self.document.document_changed.emit()

    def set_document(self, document):
        """设置面板关联的文档并刷新显示"""
        print(f"[图层面板] 设置文档: {'null' if document is None else '有效文档'}")
        self._update_timer.stop()
        self._update_pending = False

        # 如果有旧文档，断开连接
        if self.document:
            try:
                self.document.layer_changed.disconnect(self._schedule_update)
                if hasattr(self.document, 'document_changed'):
                    self.document.document_changed.disconnect(self.update_layers_and_binding_status)
                if hasattr(self.document, 'layers_changed'):
                    self.document.layers_changed.disconnect(self.refresh_binding_status)
                if hasattr(self.document, 'layer_selected'):
                    self.document.layer_selected.disconnect(self.on_layer_selected_from_document)
                if hasattr(self.document, 'layers_selection_changed'):
                    self.document.layers_selection_changed.disconnect(self.on_layers_selection_changed_from_document)
                print(f"[图层面板] 已断开旧文档信号连接")
            except Exception as e:
                print(f"[图层面板] 断开旧文档信号连接时出错: {e}")

        # 设置新文档
        self.document = document
        self._selected_layer_indices = []
        if self._binding_debug_mode and self.binding_debug_toggle and self.document:
            bm = getattr(self.document, 'binding_manager', None)
            if bm and hasattr(bm, 'set_debug_trace_enabled'):
                bm.set_debug_trace_enabled(bool(self.binding_debug_toggle.isChecked()))

        # 如果新文档不为空，连接信号并更新界面
        if self.document:
            print(f"[图层面板] 连接新文档信号，图层数量: {len(self.document.layers)}")

            # 连接文档信号
            self.document.layer_changed.connect(self._schedule_update)

            # 连接文档更改信号
            if hasattr(self.document, 'document_changed'):
                self.document.document_changed.connect(self.update_layers_and_binding_status)

            # 连接layers_changed信号到绑定状态刷新
            if hasattr(self.document, 'layers_changed'):
                self.document.layers_changed.connect(self.refresh_binding_status)

            # 连接layer_selected信号来更新选中状态
            if hasattr(self.document, 'layer_selected'):
                self.document.layer_selected.connect(self.on_layer_selected_from_document)
            if hasattr(self.document, 'layers_selection_changed'):
                self.document.layers_selection_changed.connect(self.on_layers_selection_changed_from_document)

            # 立即更新图层列表显示
            print(f"[图层面板] 立即更新图层列表")
            self._schedule_update()

            # 启用控件
            self._set_controls_enabled(True)

            print(f"[图层面板] 文档设置完成，图层数量: {len(self.document.layers)}")
        else:
            print(f"[图层面板] 清空图层列表")
            # 清空列表
            self.layer_list.clear()
            self._selected_layer_indices = []
            # 禁用控件
            self._set_controls_enabled(False)
            if self._binding_debug_mode:
                self._binding_debug_timer.stop()
                self._binding_debug_last_text = ""
                if hasattr(self, 'binding_debug_text') and self.binding_debug_text:
                    self.binding_debug_text.clear()

    def update_layers_and_binding_status(self):
        """统一更新图层列表和绑定状态"""
        if self._is_export_ui_frozen():
            print("[图层面板] update_layers_and_binding_status: 批量导出运行中，跳过")
            return
        self._schedule_update()
        # 延迟刷新绑定状态，确保图层列表已更新
        QTimer.singleShot(10, self.refresh_binding_status)

    def on_layer_selected_from_document(self, selected_index):
        """处理来自Document的图层选中信号"""
        print(f"Document发出图层选中信号: 索引={selected_index}")
        if self._selection_sync_in_progress:
            return

        doc_selection = list(getattr(self.document, 'selected_layer_indices', []))
        if doc_selection:
            self._selected_layer_indices = doc_selection
        elif 0 <= selected_index < len(self.document.layers):
            self._selected_layer_indices = [selected_index]
        else:
            self._selected_layer_indices = []

        self._refresh_layer_widgets_selection()
        self._update_selected_layer_controls()

    def on_layers_selection_changed_from_document(self, selected_indices):
        """处理来自Document的多图层选中信号。"""
        if self._selection_sync_in_progress:
            return
        self._selected_layer_indices = [
            idx for idx in list(selected_indices or [])
            if self.document and 0 <= idx < len(self.document.layers)
        ]
        self._refresh_layer_widgets_selection()
        self._update_selected_layer_controls()

