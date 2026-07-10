import logging

logger = logging.getLogger(__name__)
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
    from app.models.shaped_layer_new import ShapedLayer

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

class LayerPanelSelection(object):
    """Mixin for layer_panel_selection (split from LayerPanel)."""

    def update_layers(self):
        """更新图层列表 - 优化版本"""
        if self._is_export_ui_frozen():
            print("[图层面板] update_layers: 批量导出运行中，跳过更新")
            return
        # 如果没有文档，清空列表并禁用控件
        if not self.document:
            print("[图层面板] update_layers: 文档为None，清空列表")
            self._clear_layer_list()
            self._set_controls_enabled(False)
            return

        if not self.document.layers:
            print("[图层面板] update_layers: 文档无图层，清空列表")
            self._clear_layer_list()
            self._set_controls_enabled(False)
            return

        print(f"[图层面板] update_layers: 文档图层数={len(self.document.layers)}, 列表项数={self.layer_list.count()}")

        # 当前选中的图层索引（支持多选，首选图层作为主选中）
        ui_selected = self._ordered_selected_indices_from_ui()
        if len(ui_selected) > 1:
            self._selected_layer_indices = list(ui_selected)
            try:
                if hasattr(self.document, 'select_layers'):
                    self.document.select_layers(ui_selected, primary_index=ui_selected[0])
            except Exception:
                logger.warning("静默异常已忽略: except in ui/layer_panel_selection.py", exc_info=True)
                pass
        selected_indices = self._sanitize_selected_indices()
        selected_index = selected_indices[0] if selected_indices else -1
        print(f"[图层面板] update_layers: 选中图层索引={selected_indices}")

        # 尝试增量更新而非完整重建
        can_incremental = self._can_incremental_update()
        print(f"[图层面板] update_layers: 能否增量更新={can_incremental}")

        if can_incremental:
            print("[图层面板] update_layers: 执行增量更新")
            self._incremental_update(selected_indices, selected_index)
        else:
            print("[图层面板] update_layers: 执行完整重建")
            self._full_rebuild(selected_indices, selected_index)

        print(f"[图层面板] update_layers: 更新完成，列表项数={self.layer_list.count()}")

        # 启用控件
        self._set_controls_enabled(True)

        # 延迟刷新图标状态，确保所有组件都已正确创建
        QTimer.singleShot(50, self.refresh_all_icons)

    def _can_incremental_update(self):
        """判断是否可以进行增量更新"""
        # 分组会影响折叠/缩进/索引映射，统一重建更稳。
        return False

    def _actual_index_for_item(self, item):
        if item is None:
            return -1
        value = item.data(Qt.UserRole)
        try:
            return int(value)
        except (TypeError, ValueError):
            return -1

    def _actual_index_for_row(self, row):
        if row < 0 or row >= self.layer_list.count():
            return -1
        return self._actual_index_for_item(self.layer_list.item(row))

    def _incremental_update(self, selected_indices, primary_index):
        """增量更新图层列表"""
        selected_set = set(selected_indices)
        self._selection_sync_in_progress = True
        # 只更新必要的属性，不重新创建所有项
        try:
            for i in range(self.layer_list.count()):
                list_item = self.layer_list.item(i)
                layer_widget = self.layer_list.itemWidget(list_item)

                if layer_widget:
                    # 计算真实图层索引
                    real_index = len(self.document.layers) - 1 - i

                    if 0 <= real_index < len(self.document.layers):
                        # 更新图层数据引用
                        layer_widget.layer = self.document.layers[real_index]
                        layer_widget.index = real_index

                        # 更新选中状态
                        is_selected = real_index in selected_set
                        if layer_widget.is_selected != is_selected:
                            layer_widget.set_selected(is_selected)
                        list_item.setSelected(is_selected)

                        # 更新图层显示信息（但不重新创建UI）
                        layer_widget.update_labels()

                        # 如果是主选中的图层，设置为当前项
                        if real_index == primary_index:
                            self.layer_list.setCurrentItem(list_item)
                            self.layer_list.scrollToItem(list_item)
        finally:
            self._selection_sync_in_progress = False

    def _clear_layer_list(self):
        """安全清空图层列表。

        直接用 QListWidget.clear() 销毁通过 setItemWidget 设置的自定义
        LayerItem（含自定义 paintEvent）时，Qt 会在释放 widget 的 C++ 对象
        过程中访问已失效的 Python 对象，导致 native access violation 并让
        程序闪退。更危险的是，用 shiboken6.delete 强制立即释放这些 widget
        会留下悬空指针，造成"延迟型"堆损坏——崩溃会在之后的任意 GUI 操作
        （例如再打开一个对话框）中才突然爆发，极难定位。

        安全做法（业界标准）：
        1. 对每个 item 先调用 setItemWidget(item, None)，解除 Qt 内部对
           widget 的引用，使随后的 clear() 不会重复释放该 widget；
        2. 用 deleteLater() 让 Qt 在事件循环中按自己的节奏安全销毁 widget，
           绝不手动立即 delete；
        3. 最后 takeItem 移除 item，并以 clear() 兜底。
        """
        while self.layer_list.count() > 0:
            item = self.layer_list.item(0)
            if item is None:
                break
            widget = self.layer_list.itemWidget(item)
            if widget is not None:
                try:
                    # 关键：解除 Qt 对 widget 的内部引用，避免 clear() 时重复释放
                    self.layer_list.setItemWidget(item, None)
                except Exception:
                    pass
                try:
                    # 让 Qt 在事件循环中安全销毁，不要立即强制 delete
                    widget.deleteLater()
                except Exception:
                    pass
            self.layer_list.takeItem(0)
        # 兜底：此时 itemWidgets 已清空，clear() 不会再触碰已释放的 widget
        try:
            self.layer_list.clear()
        except Exception:
            pass

    def _full_rebuild(self, selected_indices, primary_index):
        """完整重建图层列表"""
        print(f"[图层面板] _full_rebuild: 开始重建，图层数={len(self.document.layers)}")
        selected_set = set(selected_indices)

        # 从顶部到底部填充列表 (界面中最上面的图层是列表索引0)
        self._selection_sync_in_progress = True
        try:
            # 清空列表会触发 itemSelectionChanged，必须在同步保护内执行。
            # 用安全清空方法替代 QListWidget.clear()，规避 native 崩溃。
            self._clear_layer_list()
            print(f"[图层面板] _full_rebuild: 已清空列表")

            for i, (real_index, layer, depth) in enumerate(display_entries(self.document.layers)):
                print(f"[图层面板] _full_rebuild: 创建图层项 {i}: {layer.name} (真实索引={real_index})")

                try:
                    # 创建列表项
                    item = QListWidgetItem()

                    # 创建自定义小部件
                    widget = LayerItem(layer, real_index, self, depth=depth)

                    # 设置项目大小
                    item.setSizeHint(widget.sizeHint())
                    item.setData(Qt.UserRole, real_index)

                    # 添加到列表
                    self.layer_list.addItem(item)
                    self.layer_list.setItemWidget(item, widget)
                    print(f"[图层面板] _full_rebuild: 已添加图层项到列表，当前列表项数={self.layer_list.count()}")

                    # 设置选中状态（支持多选）
                    is_selected = real_index in selected_set
                    widget.set_selected(is_selected)
                    item.setSelected(is_selected)

                    # 如果是主选中的图层，设置为当前项
                    if real_index == primary_index:
                        self.layer_list.setCurrentItem(item)
                        # 滚动到选中的图层
                        self.layer_list.scrollToItem(item)
                        print(f"[图层面板] _full_rebuild: 设置图层 {layer.name} 为主选中状态")

                except Exception as e:
                    print(f"[图层面板] _full_rebuild: 创建图层项时出错: {e}")
                    import traceback
                    traceback.print_exc()
        finally:
            self._selection_sync_in_progress = False

        print(f"[图层面板] _full_rebuild: 重建完成，列表项数={self.layer_list.count()}")

        # 如果有选中的图层，更新界面
        if primary_index >= 0 and primary_index < len(self.document.layers):
            print(f"[图层面板] _full_rebuild: 图层已选中: {self.document.layers[primary_index].name}")

    def layer_selected(self, item):
        """图层选中事件处理"""
        # 如果没有文档，不做任何处理
        if not self.document:
            print("警告: document为空，无法处理图层选择")
            return

        actual_index = self._actual_index_for_item(item)
        if not (0 <= actual_index < len(self.document.layers)):
            return

        modifiers = QApplication.keyboardModifiers()
        current_selected = set(self._get_selected_indices_from_ui())

        if modifiers & Qt.ControlModifier:
            # Ctrl：追加/取消选择，保持首选图层顺序
            if actual_index in current_selected and actual_index not in self._selected_layer_indices:
                self._selected_layer_indices.append(actual_index)
            elif actual_index not in current_selected:
                self._selected_layer_indices = [idx for idx in self._selected_layer_indices if idx != actual_index]
        elif modifiers & Qt.ShiftModifier:
            # Shift：范围选择，已有顺序保持在前，新选中的追加
            ordered_existing = [idx for idx in self._selected_layer_indices if idx in current_selected]
            for idx in self._ordered_selected_indices_from_ui():
                if idx not in ordered_existing:
                    ordered_existing.append(idx)
            self._selected_layer_indices = ordered_existing
        else:
            # 普通点击：重置为单选
            self._selected_layer_indices = [actual_index]

        self._selected_layer_indices = self._sanitize_selected_indices()
        self._refresh_layer_widgets_selection()
        self._sync_primary_selection_to_document()
        self._update_selected_layer_controls()

    def _toggle_group_expanded_for_item(self, item):
        if not self.document:
            return
        actual_index = self._actual_index_for_item(item)
        if not (0 <= actual_index < len(self.document.layers)):
            return
        layer = self.document.layers[actual_index]
        if not is_layer_group(layer):
            return
        layer.expanded = not getattr(layer, 'expanded', True)
        self.document.document_changed.emit()
        self._schedule_update()

    def add_layer(self):
        """添加新图层 - 直接添加默认图层，无弹窗"""
        if self.document.canvas_width == 0 or self.document.canvas_height == 0:
            return

        try:
            # 直接调用文档的add_layer方法，传递所需参数
            layer_name = f"图层 {len(self.document.layers) + 1}"

            # 调用文档的add_layer方法，传递所需的参数
            layer = self.document.add_layer(
                name=layer_name,
                x=0,
                y=0,
                width=200,
                height=200,
                image_source=None,
                use_original_size=False,
                is_folder=True
            )

            # 更新UI
            self._schedule_update()

        except Exception as e:
            print(f"添加图层时出错: {e}")

    def get_selected_indices(self):
        """获取选中的图层索引列表"""
        if self.document is None:
            return []
        ui_selection = self._ordered_selected_indices_from_ui()
        if len(ui_selection) > 1:
            return list(ui_selection)
        doc_selection = getattr(self.document, 'selected_layer_indices', [])
        if doc_selection and len(doc_selection) > 1:
            return list(doc_selection)
        if self._selected_layer_indices and len(self._selected_layer_indices) > 1:
            return list(self._selected_layer_indices)
        if ui_selection:
            return list(ui_selection)
        if doc_selection:
            return list(doc_selection)
        if self._selected_layer_indices:
            return list(self._selected_layer_indices)
        if self.document.selected_layer_index >= 0:
            return [self.document.selected_layer_index]
        return []

    def _ordered_selected_indices_from_ui(self):
        """按列表显示顺序获取选中的实际图层索引。"""
        selected = []
        for i in range(self.layer_list.count()):
            item = self.layer_list.item(i)
            if item and item.isSelected():
                actual = self._actual_index_for_item(item)
                if 0 <= actual < len(self.document.layers):
                    selected.append(actual)
        return selected

    def _get_selected_indices_from_ui(self):
        """获取当前UI选中的图层索引集合。"""
        return self._ordered_selected_indices_from_ui()

    def _sanitize_selected_indices(self):
        """过滤无效索引并在必要时回退到文档主选中图层。"""
        if not self.document:
            self._selected_layer_indices = []
            return []
        max_index = len(self.document.layers) - 1
        sanitized = []
        for idx in self._selected_layer_indices:
            if 0 <= idx <= max_index and idx not in sanitized:
                sanitized.append(idx)
        if not sanitized and 0 <= self.document.selected_layer_index <= max_index:
            sanitized = [self.document.selected_layer_index]
        self._selected_layer_indices = sanitized
        return sanitized

    def _refresh_layer_widgets_selection(self):
        """同步列表项和自定义图层项的选中高亮状态。"""
        if not self.document:
            return
        selected_set = set(self._selected_layer_indices)
        self._selection_sync_in_progress = True
        try:
            for i in range(self.layer_list.count()):
                list_item = self.layer_list.item(i)
                widget = self.layer_list.itemWidget(list_item)
                actual = self._actual_index_for_item(list_item)
                is_selected = actual in selected_set
                if list_item is not None:
                    list_item.setSelected(is_selected)
                if widget and hasattr(widget, 'set_selected'):
                    widget.set_selected(is_selected)
        finally:
            self._selection_sync_in_progress = False

    def _sync_primary_selection_to_document(self):
        """将首选图层同步给文档，保持与现有单选逻辑兼容。"""
        if not self.document:
            return
        primary_index = self._selected_layer_indices[0] if self._selected_layer_indices else -1
        current_selection = list(getattr(self.document, 'selected_layer_indices', []))
        if primary_index != self.document.selected_layer_index or current_selection != self._selected_layer_indices:
            self._selection_sync_in_progress = True
            try:
                if hasattr(self.document, 'select_layers'):
                    self.document.select_layers(self._selected_layer_indices, primary_index=primary_index)
                else:
                    self.document.select_layer(primary_index)
            finally:
                self._selection_sync_in_progress = False

    def _update_selected_layer_controls(self):
        """根据当前主选中图层刷新控制区状态。"""
        if not self.document or not self._selected_layer_indices:
            self.selected_layer = None
            self.delete_btn.setEnabled(False)
            self.up_btn.setEnabled(False)
            self.down_btn.setEnabled(False)
            return

        primary_index = self._selected_layer_indices[0]
        if not (0 <= primary_index < len(self.document.layers)):
            return

        self.selected_layer = self.document.layers[primary_index]

        locked = is_effectively_locked(self.selected_layer, self.document.layers)
        self.delete_btn.setEnabled(not locked)
        self.up_btn.setEnabled(primary_index > 0 and not locked)
        self.down_btn.setEnabled(primary_index < len(self.document.layers) - 1 and not locked)

    def _on_layer_list_selection_changed(self):
        """处理列表选择变化（键盘选择、程序同步等场景）。"""
        if self._selection_sync_in_progress or self._updating or not self.document:
            return
        ui_selected = self._ordered_selected_indices_from_ui()
        if not ui_selected:
            self._selected_layer_indices = []
            self._update_selected_layer_controls()
            return

        # 保留已存在选择顺序，将新选择追加到末尾
        ordered_existing = [idx for idx in self._selected_layer_indices if idx in ui_selected]
        for idx in ui_selected:
            if idx not in ordered_existing:
                ordered_existing.append(idx)
        self._selected_layer_indices = ordered_existing

        self._refresh_layer_widgets_selection()
        self._sync_primary_selection_to_document()
        self._update_selected_layer_controls()

    def select_all_layers(self):
        """选择当前文档中的所有图层。"""
        if not self.document:
            return
        self._selected_layer_indices = list(range(len(self.document.layers)))
        self._refresh_layer_widgets_selection()
        self._sync_primary_selection_to_document()
        self._update_selected_layer_controls()

    def select_layer(self, index):
        """选择单个图层，供控制器和旧调用路径使用。"""
        if not self.document or not (0 <= index < len(self.document.layers)):
            return
        self._selected_layer_indices = [index]
        self._refresh_layer_widgets_selection()
        self._sync_primary_selection_to_document()
        self._update_selected_layer_controls()

    def delete_layer(self):
        """删除选中的图层，支持多选并跳过锁定图层。"""
        if not self.document:
            return
        selected_indices = []
        for idx in self.get_selected_indices():
            if not (0 <= idx < len(self.document.layers)):
                continue
            layer = self.document.layers[idx]
            if is_effectively_locked(layer, self.document.layers):
                continue
            selected_indices.append(idx)
        if not selected_indices:
            return
        self.document.save_state("批量删除图层前" if len(selected_indices) > 1 else "删除图层前")
        delete_indices = set(selected_indices)
        for idx in selected_indices:
            layer = self.document.layers[idx]
            if is_layer_group(layer):
                gid = getattr(layer, 'group_id', None)
                delete_indices.update(
                    child_idx for child_idx, child in enumerate(self.document.layers)
                    if get_parent_group_id(child) == str(gid)
                )
        for idx in sorted(delete_indices, reverse=True):
            layer_to_remove = self.document.layers[idx]
            if hasattr(self.document, 'binding_manager') and self.document.binding_manager:
                self.document.binding_manager.remove_layer_from_group(layer_to_remove)
            del self.document.layers[idx]
        fallback = min(min(delete_indices), len(self.document.layers) - 1) if self.document.layers else -1
        if hasattr(self.document, 'select_layers'):
            self.document.select_layers([fallback] if fallback >= 0 else [])
        else:
            self.document.selected_layer_index = fallback
        self.document.document_changed.emit()
        self.document.layer_changed.emit()
        self.document.save_state("批量删除图层" if len(selected_indices) > 1 else "删除图层")

    def group_selected_layers(self):
        """把当前选中的普通图层建立为一个基础组。"""
        if not self.document:
            return
        ui_selection = self._ordered_selected_indices_from_ui()
        doc_selection = list(getattr(self.document, 'selected_layer_indices', []) or [])
        panel_selection = list(self._selected_layer_indices or [])
        if len(ui_selection) > 1:
            source_selection = ui_selection
        elif len(doc_selection) > 1:
            source_selection = doc_selection
        elif len(panel_selection) > 1:
            source_selection = panel_selection
        else:
            source_selection = self.get_selected_indices()
        selected_indices = sorted({
            idx for idx in source_selection
            if 0 <= idx < len(self.document.layers)
        })
        movable = [
            idx for idx in selected_indices
            if (not is_layer_group(self.document.layers[idx]))
            and not get_parent_group_id(self.document.layers[idx])
            and not is_effectively_locked(self.document.layers[idx], self.document.layers)
        ]
        if len(movable) < 2:
            self._show_status_message("请选择至少两个未分组且未锁定的图层")
            return

        group = LayerGroup(name=f"图层组 {sum(1 for layer in self.document.layers if is_layer_group(layer)) + 1}")
        self.document.save_state("建立图层组前")
        selected_layers = [self.document.layers[idx] for idx in movable]
        selected_set = set(movable)
        insert_at = min(movable)
        remaining = [
            layer for idx, layer in enumerate(self.document.layers)
            if idx not in selected_set
        ]
        for layer in selected_layers:
            set_parent_group_id(layer, group.group_id)
        removed_before_insert = sum(1 for idx in movable if idx < insert_at)
        insert_at = max(0, insert_at - removed_before_insert)
        self.document.layers = remaining[:insert_at] + [group] + selected_layers + remaining[insert_at:]
        new_group_index = self.document.layers.index(group)
        if hasattr(self.document, 'select_layers'):
            self.document.select_layers([new_group_index], primary_index=new_group_index)
        else:
            self.document.selected_layer_index = new_group_index
        self.document.layer_changed.emit()
        self.document.document_changed.emit()
        self.document.save_state("建立图层组")

    def ungroup_selected_groups(self):
        """解除当前选中组，子图层留在原位置。"""
        if not self.document:
            return
        selected_groups = [
            idx for idx in self.get_selected_indices()
            if 0 <= idx < len(self.document.layers) and is_layer_group(self.document.layers[idx])
        ]
        if not selected_groups:
            return
        self.document.save_state("解散图层组前")
        child_selection = []
        for idx in sorted(selected_groups, reverse=True):
            group = self.document.layers[idx]
            gid = str(getattr(group, 'group_id', '') or '')
            del self.document.layers[idx]
            for child_idx, child in enumerate(self.document.layers):
                if get_parent_group_id(child) == gid:
                    set_parent_group_id(child, None)
                    child_selection.append(child_idx)
        child_selection = sorted(set(child_selection))
        if hasattr(self.document, 'select_layers'):
            self.document.select_layers(child_selection, primary_index=child_selection[0] if child_selection else -1)
        self.document.layer_changed.emit()
        self.document.document_changed.emit()
        self.document.save_state("解散图层组")

    def move_layer_up(self):
        """上移图层"""
        if self.document.selected_layer_index > 0:
            # 交换当前图层和上一个图层的位置
            from_index = self.document.selected_layer_index
            to_index = from_index - 1
            self.document.move_layer(from_index, to_index)
            self._schedule_update()

    def move_layer_down(self):
        """下移图层"""
        if self.document.selected_layer_index < len(self.document.layers) - 1:
            # 交换当前图层和下一个图层的位置
            from_index = self.document.selected_layer_index
            to_index = from_index + 1
            self.document.move_layer(from_index, to_index)
            self._schedule_update()

    def randomize_all(self):
        """随机化所有图层"""
        if self.document:
            self.document.randomize_all_layers()
            # 随机化后刷新绑定状态显示
            self.refresh_binding_status()
            self._refresh_binding_debug_panel(force=True)

    def open_binding_manager(self):
        """打开绑定管理器"""
        if not self.document:
            return

        try:
            from app.ui.binding_manager_dialog import LayerBindingManagerDialog
            dialog = LayerBindingManagerDialog(self.document, self)
            result = dialog.exec()

            # 刷新图层显示（更新绑定状态）
            self._schedule_update()
            # 强制更新所有图层项的绑定状态
            self.refresh_binding_status()
            self._refresh_binding_debug_panel(force=True)

        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"打开绑定管理器时出错: {str(e)}")
            print(f"打开绑定管理器出错: {e}")

    def open_size_match_manager(self):
        """打开图层大小匹配管理器"""
        if not self.document:
            return
        try:
            from app.ui.layer_size_match_dialog import LayerSizeMatchDialog
            dialog = LayerSizeMatchDialog(self.document, self)
            dialog.exec()
            self._schedule_update()
        except Exception as e:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(self, "错误", f"打开图层大小匹配管理器时出错: {str(e)}")
            print(f"打开图层大小匹配管理器出错: {e}")

    def _toggle_binding_debug_panel(self, enabled: bool):
        """切换绑定调试面板显示（仅调试模式可见）。"""
        if not self._binding_debug_mode:
            return
        self.binding_debug_panel.setVisible(bool(enabled))

        binding_manager = getattr(self.document, 'binding_manager', None) if self.document else None
        if binding_manager and hasattr(binding_manager, 'set_debug_trace_enabled'):
            binding_manager.set_debug_trace_enabled(bool(enabled))

        if enabled:
            self._refresh_binding_debug_panel(force=True)
            self._binding_debug_timer.start()
        else:
            self._binding_debug_timer.stop()

    def _clear_binding_debug_panel(self):
        """清空绑定调试记录。"""
        binding_manager = getattr(self.document, 'binding_manager', None) if self.document else None
        if binding_manager and hasattr(binding_manager, 'clear_debug_traces'):
            binding_manager.clear_debug_traces()
        self._binding_debug_last_text = ""
        if hasattr(self, 'binding_debug_text') and self.binding_debug_text:
            self.binding_debug_text.clear()

    def _refresh_binding_debug_panel(self, force: bool = False):
        """刷新绑定调试面板内容。"""
        if not self._binding_debug_mode:
            return
        if not hasattr(self, 'binding_debug_panel') or not self.binding_debug_panel.isVisible():
            return

        binding_manager = getattr(self.document, 'binding_manager', None) if self.document else None
        if not binding_manager or not hasattr(binding_manager, 'get_debug_trace_text'):
            return

        try:
            debug_text = binding_manager.get_debug_trace_text(limit=120)
            if force or debug_text != self._binding_debug_last_text:
                self.binding_debug_text.setPlainText(debug_text)
                self.binding_debug_last_text = debug_text
                cursor = self.binding_debug_text.textCursor()
                cursor.movePosition(cursor.End)
                self.binding_debug_text.setTextCursor(cursor)
        except Exception as e:
            print(f"[图层面板] 刷新绑定调试面板失败: {e}")

    def refresh_binding_status(self):
        """刷新所有图层项的绑定状态显示"""
        try:
            for i in range(self.layer_list.count()):
                item = self.layer_list.item(i)
                if item:
                    widget = self.layer_list.itemWidget(item)
                    if isinstance(widget, LayerItem):
                        widget.update_bind_icon()
                        widget.update_lock_icon()  # 同时刷新锁定图标
        except Exception as e:
            print(f"刷新绑定状态时出错: {e}")

    def refresh_all_icons(self):
        """刷新所有图层项的图标状态"""
        if self._is_export_ui_frozen():
            print("[图层面板] refresh_all_icons: 批量导出运行中，跳过图标刷新")
            return
        try:
            for i in range(self.layer_list.count()):
                item = self.layer_list.item(i)
                if item:
                    widget = self.layer_list.itemWidget(item)
                    if isinstance(widget, LayerItem):
                        # 强制刷新所有图标状态
                        widget.update_bind_icon()
                        widget.update_lock_icon()
                        widget.update_visibility_icon()
                        # 确保可见性按钮状态正确
                        widget.visibility_btn.setChecked(widget.layer.visible)
        except Exception as e:
            print(f"刷新所有图标时出错: {e}")
