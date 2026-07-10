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

class LayerPanelAlign(object):
    """Mixin for layer_panel_align (split from LayerPanel)."""

    def clear_layer_cache(self, layer):
        """清除图层的图像缓存，处理不同的缓存属性命名"""
        if hasattr(layer, '_cached_image'):
            layer._cached_image = None
        if hasattr(layer, 'cached_image'):
            layer.cached_image = None

    def _show_status_message(self, message, timeout=2000):
        """在主窗口状态栏展示简短反馈。"""
        main_window = self._get_main_window()
        if main_window and hasattr(main_window, 'statusBar'):
            main_window.statusBar().showMessage(message, timeout)

    def _valid_selected_indices(self):
        """获取去重后的有效选中图层索引。"""
        if not self.document:
            return []
        valid_indices = []
        for idx in self.get_selected_indices():
            if 0 <= idx < len(self.document.layers) and idx not in valid_indices:
                valid_indices.append(idx)
        return valid_indices

    def _finalize_multi_layer_operation(self, action_name, changed_layers):
        """统一完成多图层操作的缓存、历史和刷新。"""
        if not changed_layers:
            return False
        for layer in changed_layers:
            self.clear_layer_cache(layer)
        if hasattr(self.document, '_needs_cache_refresh'):
            self.document._needs_cache_refresh = True
        self.document.document_changed.emit()
        self.document.layer_changed.emit()
        self.document.save_state(action_name)
        if hasattr(self, 'refresh_all_icons'):
            self.refresh_all_icons()
        self._refresh_layer_widgets_selection()
        self._update_selected_layer_controls()
        return True

    def set_selected_layers_visible(self, visible):
        """批量设置选中图层可见性。"""
        self.document.save_state("批量显示图层前" if visible else "批量隐藏图层前")
        changed_layers = []
        for idx in self._valid_selected_indices():
            layer = self.document.layers[idx]
            if getattr(layer, 'visible', True) != visible:
                layer.visible = visible
                changed_layers.append(layer)

        if self._finalize_multi_layer_operation("批量显示图层" if visible else "批量隐藏图层", changed_layers):
            action_text = "显示" if visible else "隐藏"
            self._show_status_message(f"已{action_text} {len(changed_layers)} 个图层", 2000)

    def set_selected_layers_locked(self, locked):
        """批量设置选中图层锁定状态。"""
        self.document.save_state("批量锁定图层前" if locked else "批量解锁图层前")
        changed_layers = []
        for idx in self._valid_selected_indices():
            layer = self.document.layers[idx]
            if getattr(layer, 'locked', False) != locked:
                layer.locked = locked
                changed_layers.append(layer)

        if self._finalize_multi_layer_operation("批量锁定图层" if locked else "批量解锁图层", changed_layers):
            action_text = "锁定" if locked else "解锁"
            self._show_status_message(f"已{action_text} {len(changed_layers)} 个图层", 2000)

    def align_layers(self, align_type):
        """对齐图层到画板"""
        if not self.document or not hasattr(self.document, 'layers') or not self.document.layers:
            return

        # 获取当前选中的图层索引（支持多选）
        selected_indices = self.get_selected_indices()
        selected_index = selected_indices[0] if selected_indices else self.document.selected_layer_index
        if selected_index < 0:
            return

        # 多选对齐：以首选图层为基准，仅移动/缩放其余选中图层
        if len(selected_indices) > 1:
            self._align_layers_to_reference(selected_indices, align_type)
            return

        # 保存当前状态
        self.document.save_state("对齐图层前")

        # 获取当前选中的图层
        layer = self.document.layers[selected_index]

        # 检查图层是否锁定
        if layer.locked:
            return  # 如果图层锁定，不执行任何对齐操作

        # 获取画布尺寸
        canvas_width = self.document.canvas_width
        canvas_height = self.document.canvas_height

        # 是否需要清除缓存
        need_clear_cache = False

        # 检查是否启用了分身功能
        is_clone_enabled = (hasattr(layer, 'clone_enabled') and layer.clone_enabled and
                           hasattr(layer, 'clone_rows') and layer.clone_rows > 0 and
                           hasattr(layer, 'clone_columns') and layer.clone_columns > 0)

        # 如果启用了分身，获取所有分身位置并计算整体的边界
        if is_clone_enabled:
            try:
                # 获取所有分身位置
                if hasattr(layer, 'get_clone_positions') and callable(layer.get_clone_positions):
                    # 复制当前图层位置，以便可以恢复如果出错
                    original_x, original_y = layer.x, layer.y

                    clone_positions = layer.get_clone_positions()
                    all_positions = [(layer.x, layer.y)] + clone_positions
                    # 元素填充整体位置
                    fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
                    if fill_enabled:
                        spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                        angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                        mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                        dx = max(1, int(layer.width + spacing))
                        dy = max(1, int(layer.height + spacing))
                        positions = []
                        cx = canvas_width / 2.0
                        cy = canvas_height / 2.0
                        base_x = layer.x
                        base_y = layer.y
                        import math
                        angle = math.radians(angle_deg % 360.0)
                        start_y = -layer.height
                        end_y = canvas_height + layer.height
                        if mode == 'border':
                            seen = set()
                            for x in range(0, max(1, canvas_width - layer.width + 1), dx):
                                px = base_x + x
                                py_top = base_y + 0
                                py_bottom = base_y + (canvas_height - layer.height)
                                seen.add((px, py_top))
                                seen.add((px, py_bottom))
                            for y in range(0, max(1, canvas_height - layer.height + 1), dy):
                                py = base_y + y
                                px_left = base_x + 0
                                px_right = base_x + (canvas_width - layer.width)
                                seen.add((px_left, py))
                                seen.add((px_right, py))
                            positions = list(seen)
                        else:
                            step_y = dy
                            i_row = 0
                            for row_y in range(start_y, end_y + 1, step_y):
                                offset = dx // 2 if (mode == 'staggered' and (i_row % 2 == 1)) else 0
                                for col_x in range(-layer.width, canvas_width + layer.width + 1, dx):
                                    x0 = base_x + col_x + offset
                                    y0 = base_y + row_y
                                    if angle != 0.0:
                                        rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                                        ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                                        x = int(rx)
                                        y = int(ry)
                                    else:
                                        x = x0
                                        y = y0
                                    positions.append((x, y))
                                i_row += 1
                        all_positions = positions if positions else all_positions
                    mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
                    if mirror_mode and mirror_mode != 'none':
                        positions = all_positions[:]
                        min_x = min([x for x, _ in positions])
                        max_x = max([x + layer.width for x, _ in positions])
                        min_y = min([y for _, y in positions])
                        max_y = max([y + layer.height for _, y in positions])
                        group_width = max_x - min_x
                        group_height = max_y - min_y
                        mirrored_positions = []
                        if mirror_mode == 'horizontal':
                            mirrored_left = canvas_width - (min_x + group_width)
                            for cx, cy in positions:
                                offset_x = cx - min_x
                                mirrored_positions.append((mirrored_left + offset_x, cy))
                        elif mirror_mode == 'vertical':
                            mirrored_top = canvas_height - (min_y + group_height)
                            for cx, cy in positions:
                                offset_y = cy - min_y
                                mirrored_positions.append((cx, mirrored_top + offset_y))
                        all_positions = all_positions + mirrored_positions

                    # 计算分身整体的边界（包括原始图层）
                    min_x = min([pos[0] for pos in all_positions])
                    max_x = max([pos[0] + layer.width for pos in all_positions])
                    min_y = min([pos[1] for pos in all_positions])
                    max_y = max([pos[1] + layer.height for pos in all_positions])

                    # 计算整体宽度和高度
                    total_width = max_x - min_x
                    total_height = max_y - min_y

                    # 计算主图层与整体边界的偏移
                    offset_x = layer.x - min_x
                    offset_y = layer.y - min_y

                    # 根据对齐类型执行不同的对齐操作
                    if align_type == "left":
                        # 左对齐到画板
                        layer.x = 0 + offset_x  # 保持分身之间的相对位置
                        need_clear_cache = True

                    elif align_type == "hcenter":
                        # 水平居中于画板
                        layer.x = int((canvas_width - total_width) / 2) + offset_x
                        need_clear_cache = True

                    elif align_type == "right":
                        # 右对齐到画板
                        layer.x = int(canvas_width - total_width) + offset_x
                        need_clear_cache = True

                    elif align_type == "top":
                        # 顶部对齐到画板
                        layer.y = 0 + offset_y
                        need_clear_cache = True

                    elif align_type == "vcenter":
                        # 垂直居中于画板
                        layer.y = int((canvas_height - total_height) / 2) + offset_y
                        need_clear_cache = True

                    elif align_type == "bottom":
                        # 底部对齐到画板
                        layer.y = int(canvas_height - total_height) + offset_y
                        need_clear_cache = True

                    elif align_type == "center":
                        # 完全居中于画板
                        layer.x = int((canvas_width - total_width) / 2) + offset_x
                        layer.y = int((canvas_height - total_height) / 2) + offset_y
                        need_clear_cache = True

                    elif align_type == "same_size":
                        # 对于分身，暂不支持same_size操作
                        if not layer.use_original_size:
                            # 这里可以根据需求实现，例如按比例缩放或提示用户不支持
                            print("分身模式下不支持调整到相同大小")

                            # 暂时采用简单处理：取消分身并调整为画布大小
                            layer.clone_enabled = False
                            layer.width = canvas_width
                            layer.height = canvas_height
                            layer.x = 0
                            layer.y = 0
                            need_clear_cache = True

                    # 如果需要，清除缓存图像以强制重新加载
                    if need_clear_cache:
                        self.clear_layer_cache(layer)

                    # 通知文档已更改
                    self.document.document_changed.emit()

                    # 保存更改后的状态
                    self.document.save_state("对齐分身图层")
                    return

            except Exception as e:
                print(f"分身对齐出错: {e}")
                # 出错时回退到常规对齐

        # 镜像但未启用分身时的整体对齐
        mirror_mode = getattr(layer, 'clone_mirror_mode', 'none')
        if (not is_clone_enabled) and mirror_mode and mirror_mode != 'none':
            try:
                positions = [(layer.x, layer.y)]
                min_x = layer.x
                max_x = layer.x + layer.width
                min_y = layer.y
                max_y = layer.y + layer.height
                group_width = max_x - min_x
                group_height = max_y - min_y
                mirrored_positions = []
                if mirror_mode == 'horizontal':
                    mirrored_left = canvas_width - (min_x + group_width)
                    mirrored_positions.append((mirrored_left, layer.y))
                elif mirror_mode == 'vertical':
                    mirrored_top = canvas_height - (min_y + group_height)
                    mirrored_positions.append((layer.x, mirrored_top))
                all_positions = positions + mirrored_positions
                min_x = min([pos[0] for pos in all_positions])
                max_x = max([pos[0] + layer.width for pos in all_positions])
                min_y = min([pos[1] for pos in all_positions])
                max_y = max([pos[1] + layer.height for pos in all_positions])
                total_width = max_x - min_x
                total_height = max_y - min_y
                offset_x = layer.x - min_x
                offset_y = layer.y - min_y
                if align_type == "left":
                    layer.x = 0 + offset_x
                    need_clear_cache = True
                elif align_type == "hcenter":
                    layer.x = int((canvas_width - total_width) / 2) + offset_x
                    need_clear_cache = True
                elif align_type == "right":
                    layer.x = int(canvas_width - total_width) + offset_x
                    need_clear_cache = True
                elif align_type == "top":
                    layer.y = 0 + offset_y
                    need_clear_cache = True
                elif align_type == "vcenter":
                    layer.y = int((canvas_height - total_height) / 2) + offset_y
                    need_clear_cache = True
                elif align_type == "bottom":
                    layer.y = int(canvas_height - total_height) + offset_y
                    need_clear_cache = True
                elif align_type == "center":
                    layer.x = int((canvas_width - total_width) / 2) + offset_x
                    layer.y = int((canvas_height - total_height) / 2) + offset_y
                    need_clear_cache = True
                if need_clear_cache:
                    self.clear_layer_cache(layer)
                self.document.document_changed.emit()
                self.document.save_state("对齐镜像图层")
                return
            except Exception:
                logger.warning("静默异常已忽略: except in ui/layer_panel_align.py", exc_info=True)
                pass

        fill_enabled = bool(getattr(layer, 'clone_fill_enabled', False))
        if (not is_clone_enabled) and fill_enabled:
            try:
                spacing = int(getattr(layer, 'clone_fill_spacing', 0))
                angle_deg = float(getattr(layer, 'clone_fill_angle', 0.0))
                mode = str(getattr(layer, 'clone_fill_mode', 'grid'))
                dx = max(1, int(layer.width + spacing))
                dy = max(1, int(layer.height + spacing))
                positions = []
                cx = canvas_width / 2.0
                cy = canvas_height / 2.0
                base_x = layer.x
                base_y = layer.y
                import math
                angle = math.radians(angle_deg % 360.0)
                start_y = -layer.height
                end_y = canvas_height + layer.height
                step_y = max(1, int(dy * 0.866)) if mode == 'hex' else dy
                i_row = 0
                for row_y in range(start_y, end_y + 1, step_y):
                    offset = 0
                    if mode == 'staggered' and (i_row % 2 == 1):
                        offset = dx // 2
                    if mode == 'hex' and (i_row % 2 == 1):
                        offset = dx // 2
                    if mode == 'diagonal':
                        offset = (i_row * (dx // 2)) % dx
                    for col_x in range(-layer.width, canvas_width + layer.width + 1, dx):
                        x0 = base_x + col_x + offset
                        y0 = base_y + row_y
                        if angle != 0.0:
                            rx = math.cos(angle) * (x0 - cx) - math.sin(angle) * (y0 - cy) + cx
                            ry = math.sin(angle) * (x0 - cx) + math.cos(angle) * (y0 - cy) + cy
                            x = int(rx)
                            y = int(ry)
                        else:
                            x = x0
                            y = y0
                        positions.append((x, y))
                    i_row += 1
                if positions:
                    min_x = min([pos[0] for pos in positions])
                    max_x = max([pos[0] + layer.width for pos in positions])
                    min_y = min([pos[1] for pos in positions])
                    max_y = max([pos[1] + layer.height for pos in positions])
                    total_width = max_x - min_x
                    total_height = max_y - min_y
                    offset_x = layer.x - min_x
                    offset_y = layer.y - min_y
                    if align_type == "left":
                        layer.x = 0 + offset_x
                        need_clear_cache = True
                    elif align_type == "hcenter":
                        layer.x = int((canvas_width - total_width) / 2) + offset_x
                        need_clear_cache = True
                    elif align_type == "right":
                        layer.x = int(canvas_width - total_width) + offset_x
                        need_clear_cache = True
                    elif align_type == "top":
                        layer.y = 0 + offset_y
                        need_clear_cache = True
                    elif align_type == "vcenter":
                        layer.y = int((canvas_height - total_height) / 2) + offset_y
                        need_clear_cache = True
                    elif align_type == "bottom":
                        layer.y = int(canvas_height - total_height) + offset_y
                        need_clear_cache = True
                    elif align_type == "center":
                        layer.x = int((canvas_width - total_width) / 2) + offset_x
                        layer.y = int((canvas_height - total_height) / 2) + offset_y
                        need_clear_cache = True
                    if need_clear_cache:
                        self.clear_layer_cache(layer)
                    self.document.document_changed.emit()
                    self.document.save_state("对齐填充整体")
                    return
            except Exception:
                logger.warning("静默异常已忽略: except in ui/layer_panel_align.py", exc_info=True)
                pass

        # 常规单图层对齐（无分身或分身/镜像处理失败时）
        # 根据对齐类型执行不同的对齐操作
        if align_type == "left":
            # 左对齐到画板
            layer.x = 0
            need_clear_cache = True

        elif align_type == "hcenter":
            # 水平居中于画板
            layer.x = int((canvas_width - layer.width) / 2)
            need_clear_cache = True

        elif align_type == "right":
            # 右对齐到画板
            layer.x = int(canvas_width - layer.width)
            need_clear_cache = True

        elif align_type == "top":
            # 顶部对齐到画板
            layer.y = 0
            need_clear_cache = True

        elif align_type == "vcenter":
            # 垂直居中于画板
            layer.y = int((canvas_height - layer.height) / 2)
            need_clear_cache = True

        elif align_type == "bottom":
            # 底部对齐到画板
            layer.y = int(canvas_height - layer.height)
            need_clear_cache = True

        elif align_type == "center":
            # 完全居中于画板
            layer.x = int((canvas_width - layer.width) / 2)
            layer.y = int((canvas_height - layer.height) / 2)
            need_clear_cache = True

        elif align_type == "same_size":
            # 适应画板大小 - 完全匹配画板尺寸，不保留原始比例
            if not layer.use_original_size:
                # 直接设置为画板大小
                layer.width = canvas_width
                layer.height = canvas_height

                # 重置位置到左上角
                layer.x = 0
                layer.y = 0

                # 对于same_size操作，总是需要清除缓存
                need_clear_cache = True

        # 如果需要，清除缓存图像以强制重新加载
        if need_clear_cache:
            self.clear_layer_cache(layer)
            # 标记文档需要缓存刷新
            if hasattr(self.document, '_needs_cache_refresh'):
                self.document._needs_cache_refresh = True

        # 通知文档已更改
        self.document.document_changed.emit()

        # 保存更改后的状态
        self.document.save_state("对齐图层")

    def _align_layers_to_reference(self, selected_indices, align_type):
        """多图层对齐：以首选图层为基准对齐其余图层。"""
        valid_indices = []
        for idx in selected_indices:
            if 0 <= idx < len(self.document.layers) and idx not in valid_indices:
                valid_indices.append(idx)
        if len(valid_indices) < 2:
            return

        if align_type in ("distribute_horizontal", "distribute_vertical"):
            self._distribute_layers_evenly(valid_indices, align_type)
            return

        ref_index = valid_indices[0]
        ref_layer = self.document.layers[ref_index]
        ref_left = int(ref_layer.x)
        ref_top = int(ref_layer.y)
        ref_right = int(ref_layer.x + ref_layer.width)
        ref_bottom = int(ref_layer.y + ref_layer.height)
        ref_center_x = ref_layer.x + ref_layer.width / 2.0
        ref_center_y = ref_layer.y + ref_layer.height / 2.0

        changed_layers = []

        for target_index in valid_indices[1:]:
            layer = self.document.layers[target_index]
            if getattr(layer, 'locked', False):
                continue

            changed = False
            if align_type == "left":
                new_x = ref_left
                if int(layer.x) != new_x:
                    layer.x = new_x
                    changed = True
            elif align_type == "hcenter":
                new_x = int(ref_center_x - layer.width / 2.0)
                if int(layer.x) != new_x:
                    layer.x = new_x
                    changed = True
            elif align_type == "right":
                new_x = int(ref_right - layer.width)
                if int(layer.x) != new_x:
                    layer.x = new_x
                    changed = True
            elif align_type == "top":
                new_y = ref_top
                if int(layer.y) != new_y:
                    layer.y = new_y
                    changed = True
            elif align_type == "vcenter":
                new_y = int(ref_center_y - layer.height / 2.0)
                if int(layer.y) != new_y:
                    layer.y = new_y
                    changed = True
            elif align_type == "bottom":
                new_y = int(ref_bottom - layer.height)
                if int(layer.y) != new_y:
                    layer.y = new_y
                    changed = True
            elif align_type == "center":
                new_x = int(ref_center_x - layer.width / 2.0)
                new_y = int(ref_center_y - layer.height / 2.0)
                if int(layer.x) != new_x or int(layer.y) != new_y:
                    layer.x = new_x
                    layer.y = new_y
                    changed = True
            elif align_type == "same_size":
                new_width = int(ref_layer.width)
                new_height = int(ref_layer.height)
                if int(layer.width) != new_width or int(layer.height) != new_height:
                    layer.width = new_width
                    layer.height = new_height
                    changed = True

            if changed:
                changed_layers.append(layer)

        if self._finalize_multi_layer_operation("多图层对齐", changed_layers):
            self._show_status_message(f"已对齐 {len(changed_layers)} 个图层", 2000)

    def _distribute_layers_evenly(self, valid_indices, align_type):
        """按图层边缘间距等距分布，首尾图层固定。"""
        horizontal = align_type == "distribute_horizontal"
        axis_start = "x" if horizontal else "y"
        axis_size = "width" if horizontal else "height"
        sorted_indices = sorted(
            valid_indices,
            key=lambda idx: (
                int(getattr(self.document.layers[idx], axis_start, 0)),
                idx,
            ),
        )
        if len(sorted_indices) < 3:
            self._show_status_message("等距分布需要至少三个图层", 3000)
            return

        layers = [self.document.layers[idx] for idx in sorted_indices]
        first = layers[0]
        last = layers[-1]
        start_pos = float(getattr(first, axis_start, 0))
        end_pos = float(getattr(last, axis_start, 0)) + float(getattr(last, axis_size, 0))
        total_size = sum(float(getattr(layer, axis_size, 0)) for layer in layers)
        gap = (end_pos - start_pos - total_size) / (len(layers) - 1)

        cursor = start_pos
        changed_layers = []
        for i, layer in enumerate(layers):
            target_pos = int(round(cursor))
            if i not in (0, len(layers) - 1) and not getattr(layer, 'locked', False):
                if int(getattr(layer, axis_start, 0)) != target_pos:
                    setattr(layer, axis_start, target_pos)
                    changed_layers.append(layer)
            cursor += float(getattr(layer, axis_size, 0)) + gap

        action_name = "水平等距分布图层" if horizontal else "垂直等距分布图层"
        if self._finalize_multi_layer_operation(action_name, changed_layers):
            direction_text = "水平" if horizontal else "垂直"
            self._show_status_message(f"已{direction_text}等距分布 {len(layers)} 个图层", 2000)

    def _set_controls_enabled(self, enabled):
        """设置控件启用/禁用状态

        Args:
            enabled: 是否启用控件
        """
        # 设置按钮状态
        self.add_btn.setEnabled(enabled)
        self.delete_btn.setEnabled(enabled)
        self.up_btn.setEnabled(enabled and self.document and
                              self.document.selected_layer_index > 0)
        self.down_btn.setEnabled(enabled and self.document and
                               self.document.selected_layer_index < len(self.document.layers) - 1)
        if hasattr(self, 'group_btn'):
            self.group_btn.setEnabled(enabled)
        self.random_btn.setEnabled(enabled)

        print(f"设置控件状态: {'启用' if enabled else '禁用'}")