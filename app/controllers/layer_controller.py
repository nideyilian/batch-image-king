"""
图层控制器
负责管理图层的创建、删除、移动、复制等操作
保持与MainWindow的信号连接兼容性
"""

import copy

from PySide6.QtWidgets import QInputDialog, QMessageBox
from PySide6.QtCore import QObject, Signal

from app.models.layer import Layer
try:
    from app.models.shaped_layer_new import ShapedLayer, ShapeType
except ImportError:
    from app.models.shaped_layer import ShapedLayer, ShapeType
from app.ui.add_text_layer_dialog_simple import AddTextLayerDialog
from app.ui.add_shaped_layer_dialog import AddShapedLayerDialog
from app.utils.layer_tree import (
    child_indices_for_group,
    expand_group_indices,
    is_effectively_locked,
    is_layer_group,
    set_parent_group_id,
)


class LayerController(QObject):
    """图层控制器类"""
    
    # 信号定义 - 保持与MainWindow兼容
    layer_operation_completed = Signal(str, bool)  # 操作名, 是否成功
    status_message = Signal(str, int)  # 状态消息, 显示时间(ms)
    layer_selection_changed = Signal()  # 图层选择改变
    
    def __init__(self, main_window):
        super().__init__()
        self.main_window = main_window
        
        # 图层剪贴板 - 用于复制粘贴功能
        self.layer_clipboard = None
        self.style_clipboard = None

    def _serialize_layer_for_clipboard(self, layer):
        """将图层序列化为可跨文档粘贴的剪贴板数据"""
        if layer is None or not hasattr(layer, 'serialize'):
            return None
        try:
            if is_layer_group(layer):
                from app.models.document_serializer import DocumentSerializer

                layer_data = copy.deepcopy(layer.serialize())
                layer_data['children'] = []
                for child_idx in child_indices_for_group(self.document.layers, getattr(layer, 'group_id', ''), include_hidden=True):
                    child_data = DocumentSerializer.serialize_layer(self.document.layers[child_idx])
                    child_data.pop('parent_group_id', None)
                    child_data.pop('_parent_group_id', None)
                    layer_data['children'].append(child_data)
                return {
                    'format': 'layer_serialized_v1',
                    'layer_data': layer_data,
                    'layer_name': getattr(layer, 'name', '图层组'),
                }
            return {
                'format': 'layer_serialized_v1',
                'layer_data': layer.serialize(),
                'layer_name': getattr(layer, 'name', '未命名图层'),
            }
        except Exception:
            return None

    def _create_layer_from_clipboard_item(self, item):
        """从剪贴板条目创建图层（支持新旧剪贴板格式）"""
        layers = self._create_layers_from_clipboard_item(item)
        return layers[0] if layers else None

    def _create_layers_from_clipboard_item(self, item):
        """从剪贴板条目创建一个或一组图层。"""
        # 新格式：序列化数据（推荐，支持跨文档完整复制）
        if isinstance(item, dict) and item.get('format') == 'layer_serialized_v1':
            layer_data = item.get('layer_data')
            if not isinstance(layer_data, dict):
                return []
            # 深拷贝避免粘贴时污染剪贴板原始数据
            layer_data = copy.deepcopy(layer_data)
            if layer_data.get('type') == 'group':
                child_data_list = list(layer_data.get('children', []) or [])
                layer_data.pop('children', None)
                layer_data.pop('group_id', None)
                group = self.document.create_layer_from_data(layer_data)
                if group is None:
                    return []
                result = [group]
                group_id = getattr(group, 'group_id', None)
                for child_data in child_data_list:
                    if not isinstance(child_data, dict):
                        continue
                    child = self.document.create_layer_from_data(copy.deepcopy(child_data))
                    if child is None:
                        continue
                    set_parent_group_id(child, group_id)
                    result.append(child)
                return result
            layer = self.document.create_layer_from_data(layer_data)
            return [layer] if layer is not None else []

        # 旧格式：直接存图层对象（兼容）
        if item is not None and hasattr(item, 'duplicate'):
            try:
                return [item.duplicate(parent=self.document)]
            except TypeError:
                return [item.duplicate()]
            except Exception:
                return []
        return []
        
    @property
    def document(self):
        """获取当前活动文档"""
        return self.main_window.document
    
    @property 
    def layer_panel(self):
        """获取图层面板"""
        return self.main_window.layer_panel

    def get_selected_indices(self):
        """获取当前有效选中图层索引，优先使用文档级多选状态。"""
        if not self.document:
            return []
        panel_indices = []
        if self.layer_panel and hasattr(self.layer_panel, 'get_selected_indices'):
            panel_indices = list(self.layer_panel.get_selected_indices())
        document_indices = list(getattr(self.document, 'selected_layer_indices', []) or [])
        if len(panel_indices) > 1:
            indices = panel_indices
        elif len(document_indices) > 1:
            indices = document_indices
        else:
            indices = panel_indices or document_indices
        if not indices and getattr(self.document, 'selected_layer_index', -1) >= 0:
            indices = [self.document.selected_layer_index]
        valid = []
        for idx in indices:
            if 0 <= idx < len(self.document.layers) and idx not in valid:
                valid.append(idx)
        return valid

    def get_selected_layers(self):
        """获取当前选中的图层对象。"""
        if not self.document:
            return []
        return [self.document.layers[idx] for idx in self.get_selected_indices()]

    def _clear_layer_cache(self, layer):
        if hasattr(layer, '_cached_image'):
            layer._cached_image = None
        if hasattr(layer, 'cached_image'):
            layer.cached_image = None

    def _refresh_after_batch_operation(self, selected_indices=None):
        if hasattr(self.document, '_invalidate_render_cache'):
            self.document._invalidate_render_cache()
        elif hasattr(self.document, '_needs_cache_refresh'):
            self.document._needs_cache_refresh = True
        if selected_indices is not None and hasattr(self.document, 'select_layers'):
            self.document.select_layers(selected_indices, primary_index=selected_indices[0] if selected_indices else -1)
        if self.layer_panel:
            if hasattr(self.layer_panel, 'update_layers'):
                self.layer_panel.update_layers()
            elif hasattr(self.layer_panel, 'refresh_layers'):
                self.layer_panel.refresh_layers()
        if hasattr(self.main_window, 'update_canvas'):
            self.main_window.update_canvas()
        self.document.document_changed.emit()
        self.document.layer_changed.emit()

    def batch_update_layers(self, indices, updater, action_name, invalidate="auto", allow_locked=False):
        """批量更新图层，一次历史记录、一次刷新。updater返回True表示图层有变化。"""
        if not self.document:
            return 0, 0
        valid_indices = []
        for idx in indices or []:
            if 0 <= idx < len(self.document.layers) and idx not in valid_indices:
                valid_indices.append(idx)
        if not valid_indices:
            return 0, 0

        self.document.save_state(f"{action_name}前")
        changed_layers = []
        skipped_locked = 0
        for idx in valid_indices:
            layer = self.document.layers[idx]
            if getattr(layer, 'locked', False) and not allow_locked:
                skipped_locked += 1
                continue
            try:
                changed = bool(updater(layer, idx))
            except TypeError:
                changed = bool(updater(layer))
            if changed:
                changed_layers.append(layer)
                if invalidate in ("auto", "layer"):
                    self._clear_layer_cache(layer)

        if not changed_layers:
            return 0, skipped_locked

        self._refresh_after_batch_operation(valid_indices)
        self.document.save_state(action_name)
        return len(changed_layers), skipped_locked

    def apply_style_to_selected(self, style_data, source_type_policy="compatible"):
        """将样式剪贴板批量应用到当前选区。"""
        from app.models.text_layer import TextLayer

        common_attrs = [
            'opacity', 'visible', 'locked', 'blend_mode', 'corner_radius',
            'stroke_enabled', 'stroke_width', 'stroke_color', 'stroke_type',
            'rotation', 'flip_horizontal', 'flip_vertical'
        ]
        text_attrs = [
            'text_color', 'font_family', 'font_size', 'font_style', 'text_align',
            'line_spacing', 'gradient_enabled', 'gradient_type', 'gradient_direction',
            'gradient_start_color', 'gradient_end_color', 'gradient_center_x',
            'gradient_center_y', 'background_enabled', 'background_color',
            'background_padding'
        ]

        def updater(layer, _idx):
            attrs = list(common_attrs)
            if isinstance(layer, TextLayer):
                attrs.extend(text_attrs)
            changed = False
            for attr in attrs:
                if attr in style_data and hasattr(layer, attr) and getattr(layer, attr) != style_data[attr]:
                    setattr(layer, attr, copy.deepcopy(style_data[attr]))
                    changed = True
            return changed

        return self.batch_update_layers(
            self.get_selected_indices(),
            updater,
            "批量应用图层样式",
            invalidate="layer",
            allow_locked=False,
        )
        
    def add_layer(self):
        """添加新图层 - 直接添加默认图层，无弹窗"""
        if not self.document:
            self.status_message.emit("请先创建或打开一个文档", 3000)
            return False

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
            self.layer_panel.refresh_layers()
            self.main_window.update_canvas()

            # 发送状态消息
            self.status_message.emit(f"成功添加图层: {layer_name}", 3000)
            self.layer_operation_completed.emit("add_layer", True)
            return True

        except Exception as e:
            self.status_message.emit(f"添加图层时出错: {str(e)}", 5000)
            self.layer_operation_completed.emit("add_layer", False)
            return False
    
    def add_text_layer(self):
        """添加文本图层 - 从MainWindow迁移"""
        if not self.document:
            self.status_message.emit("请先创建或打开一个文档", 3000)
            return False
            
        dialog = AddTextLayerDialog(self.main_window)
        if dialog.exec():
            try:
                # 获取配置好的文字图层对象
                text_layer = dialog.get_text_layer()
                
                # 添加文本图层到文档
                layer = self.document.add_text_layer(text_layer)
                if layer:
                    # 更新UI
                    self.layer_panel.refresh_layers()
                    self.main_window.update_canvas()
                    
                    self.status_message.emit("成功添加文本图层", 3000)
                    self.layer_operation_completed.emit("add_text_layer", True)
                    return True
                else:
                    self.status_message.emit("添加文本图层失败", 3000)
                    self.layer_operation_completed.emit("add_text_layer", False)
                    return False
                    
            except Exception as e:
                self.status_message.emit(f"添加文本图层时出错: {str(e)}", 5000)
                self.layer_operation_completed.emit("add_text_layer", False)
                return False
        
        return False
    
    def delete_layer(self):
        """删除选中的图层，支持多选。"""
        if not self.document:
            return False

        selected_indices = self.get_selected_indices()
        if not selected_indices:
            self.status_message.emit("请先选择要删除的图层", 3000)
            return False

        group_delete_indices = set()
        for idx in selected_indices:
            if not (0 <= idx < len(self.document.layers)):
                continue
            layer = self.document.layers[idx]
            if is_layer_group(layer) and not is_effectively_locked(layer, self.document.layers):
                group_delete_indices.add(idx)
                group_delete_indices.update(
                    child_indices_for_group(self.document.layers, getattr(layer, 'group_id', ''), include_hidden=True)
                )

        unlocked_indices = []
        for idx in selected_indices:
            if not (0 <= idx < len(self.document.layers)):
                continue
            if idx in group_delete_indices:
                continue
            if not is_effectively_locked(self.document.layers[idx], self.document.layers):
                unlocked_indices.append(idx)
        delete_indices = sorted(set(unlocked_indices).union(group_delete_indices))
        skipped_locked = len(selected_indices) - len(unlocked_indices) - len([idx for idx in selected_indices if idx in group_delete_indices])
        if not delete_indices:
            self.status_message.emit("选中的图层都已锁定，无法删除", 3000)
            return False

        if len(delete_indices) == 1:
            message = f"确定要删除图层 '{self.document.layers[delete_indices[0]].name}' 吗？"
        else:
            message = f"确定要删除选中的 {len(delete_indices)} 个图层/组内容吗？"
            if skipped_locked:
                message += f"\n将跳过 {skipped_locked} 个锁定图层。"

        # 确认删除
        reply = QMessageBox.question(
            self.main_window, "确认删除", message,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )

        if reply == QMessageBox.Yes:
            try:
                self.document.save_state("批量删除图层前" if len(delete_indices) > 1 else "删除图层前")
                for idx in sorted(delete_indices, reverse=True):
                    layer_to_remove = self.document.layers[idx]
                    if hasattr(self.document, 'binding_manager') and self.document.binding_manager:
                        self.document.binding_manager.remove_layer_from_group(layer_to_remove)
                    del self.document.layers[idx]
                new_selection = []
                if self.document.layers:
                    fallback = min(min(delete_indices), len(self.document.layers) - 1)
                    new_selection = [fallback]
                if hasattr(self.document, 'select_layers'):
                    self.document.select_layers(new_selection)
                else:
                    self.document.selected_layer_index = new_selection[0] if new_selection else -1
                self._refresh_after_batch_operation(new_selection)
                self.document.save_state("批量删除图层" if len(delete_indices) > 1 else "删除图层")

                suffix = f"，跳过 {skipped_locked} 个锁定图层" if skipped_locked else ""
                self.status_message.emit(f"已删除 {len(delete_indices)} 个图层/组内容{suffix}", 3000)
                self.layer_operation_completed.emit("delete_layer", True)
                return True

            except Exception as e:
                self.status_message.emit(f"删除图层时出错: {str(e)}", 5000)
                self.layer_operation_completed.emit("delete_layer", False)
                return False
        
        return False
    
    def move_layer_up(self):
        """向上移动图层 - 从MainWindow迁移"""
        return self._move_layer(-1)
    
    def move_layer_down(self):
        """向下移动图层 - 从MainWindow迁移"""
        return self._move_layer(1)
    
    def _move_layer(self, direction):
        """移动图层的内部实现，支持多选整体上移/下移。"""
        if not self.document:
            return False

        selected_indices = self.get_selected_indices()
        if not selected_indices:
            self.status_message.emit("请选择图层", 3000)
            return False

        try:
            selected_set = set(selected_indices)
            selected_objects = [self.document.layers[idx] for idx in selected_indices]
            order = sorted(selected_indices) if direction < 0 else sorted(selected_indices, reverse=True)
            moved = False
            skipped_locked = 0

            self.document.save_state("批量移动图层前" if len(selected_indices) > 1 else "移动图层前")
            for idx in order:
                layer = self.document.layers[idx]
                target = idx + direction
                if getattr(layer, 'locked', False):
                    skipped_locked += 1
                    continue
                if target < 0 or target >= len(self.document.layers) or target in selected_set:
                    continue
                if getattr(self.document.layers[target], 'locked', False):
                    continue
                self.document.layers[idx], self.document.layers[target] = self.document.layers[target], self.document.layers[idx]
                selected_set.remove(idx)
                selected_set.add(target)
                moved = True

            if not moved:
                return False

            new_selection = []
            for layer in selected_objects:
                try:
                    new_idx = self.document.layers.index(layer)
                except ValueError:
                    continue
                if new_idx not in new_selection:
                    new_selection.append(new_idx)
            self._refresh_after_batch_operation(new_selection)
            self.document.save_state("批量移动图层" if len(selected_indices) > 1 else "移动图层")

            direction_text = "上" if direction < 0 else "下"
            suffix = f"，跳过 {skipped_locked} 个锁定图层" if skipped_locked else ""
            self.status_message.emit(f"已向{direction_text}移动 {len(new_selection)} 个图层{suffix}", 2000)
            self.layer_operation_completed.emit("move_layer", True)
            return True

        except Exception as e:
            self.status_message.emit(f"移动图层时出错: {str(e)}", 5000)
            self.layer_operation_completed.emit("move_layer", False)
            return False
    
    def copy_layer(self):
        """复制图层，支持多选复制。"""
        if not self.document:
            return False

        selected_indices = self.get_selected_indices()
        if not selected_indices:
            self.status_message.emit("请先选择要复制的图层", 3000)
            return False

        try:
            copied_layers = []
            copied_child_indices = set()
            for idx in selected_indices:
                if 0 <= idx < len(self.document.layers) and is_layer_group(self.document.layers[idx]):
                    copied_child_indices.update(
                        child_indices_for_group(self.document.layers, getattr(self.document.layers[idx], 'group_id', ''), include_hidden=True)
                    )
            for idx in selected_indices:
                if idx in copied_child_indices:
                    continue
                layer = self.document.layers[idx]
                copied_layer = self._serialize_layer_for_clipboard(layer)
                if copied_layer is not None:
                    copied_layers.append(copied_layer)

            if not copied_layers:
                self.status_message.emit("复制图层失败：序列化失败", 5000)
                self.layer_operation_completed.emit("copy_layer", False)
                return False

            # 🔧 修复：同步到主窗口的剪贴板
            self.layer_clipboard = copied_layers
            self.main_window.layer_clipboard = copied_layers

            self.status_message.emit(f"已复制 {len(copied_layers)} 个图层（可跨文档粘贴）", 3000)
            self.layer_operation_completed.emit("copy_layer", True)
            return True
            
        except Exception as e:
            self.status_message.emit(f"复制图层时出错: {str(e)}", 5000)
            self.layer_operation_completed.emit("copy_layer", False)
            return False
    
    def paste_layer(self):
        """粘贴图层 - 修复版"""
        if not self.document:
            return False
            
        # 🔧 修复：检查主窗口的剪贴板
        clipboard = self.main_window.layer_clipboard or self.layer_clipboard
        if not clipboard:
            self.status_message.emit("剪贴板中没有图层", 3000)
            return False
        
        try:
            self.document.save_state("粘贴图层前")
            pasted_count = 0
            pasted_indices = []
            for item in clipboard:
                new_layers = self._create_layers_from_clipboard_item(item)
                if not new_layers:
                    continue
                for new_layer in new_layers:
                    # 稍微偏移位置避免完全重叠；组头没有几何位置，只偏移子图层。
                    if not is_layer_group(new_layer):
                        new_layer.x += 10
                        new_layer.y += 10

                    try:
                        if hasattr(new_layer, 'changed') and hasattr(new_layer.changed, 'connect'):
                            new_layer.changed.connect(self.document.document_changed.emit)
                    except Exception:
                        pass
                    self.document.layers.append(new_layer)
                    pasted_indices.append(len(self.document.layers) - 1)
                    pasted_count += 1

            if pasted_count == 0:
                self.status_message.emit("剪贴板数据无效，无法粘贴图层", 3000)
                self.layer_operation_completed.emit("paste_layer", False)
                return False
            
            self._refresh_after_batch_operation(pasted_indices)
            self.document.save_state("粘贴图层")
            
            self.status_message.emit(f"已粘贴 {pasted_count} 个图层", 3000)
            self.layer_operation_completed.emit("paste_layer", True)
            return True
            
        except Exception as e:
            self.status_message.emit(f"粘贴图层时出错: {str(e)}", 5000)
            self.layer_operation_completed.emit("paste_layer", False)
            return False
    
    def rename_layer(self):
        """重命名图层 - 修复版"""
        if not self.document:
            return False
            
        # 🔧 修复：使用document.selected_layer_index
        if self.document.selected_layer_index < 0:
            self.status_message.emit("请先选择一个图层", 3000)
            return False
        
        layer = self.document.layers[self.document.selected_layer_index]
        
        new_name, ok = QInputDialog.getText(
            self.main_window, "重命名图层", "请输入新名称:", text=layer.name
        )
        
        if ok and new_name.strip():
            try:
                layer.name = new_name.strip()
                
                # 🔧 修复：使用正确的更新方法
                if hasattr(self.layer_panel, 'refresh_layers'):
                    self.layer_panel.refresh_layers()
                else:
                    self.layer_panel.update_layers()
                
                self.status_message.emit(f"图层已重命名为: {new_name.strip()}", 2000)
                self.layer_operation_completed.emit("rename_layer", True)
                return True
                
            except Exception as e:
                self.status_message.emit(f"重命名图层时出错: {str(e)}", 5000)
                self.layer_operation_completed.emit("rename_layer", False)
                return False
        
        return False
    
    def select_all_layers(self):
        """全选图层 - 从MainWindow迁移"""
        if not self.document:
            return False
            
        try:
            self.layer_panel.select_all_layers()
            self.layer_selection_changed.emit()
            
            count = len(self.document.layers)
            self.status_message.emit(f"已选择所有 {count} 个图层", 2000)
            return True
            
        except Exception as e:
            self.status_message.emit(f"选择图层时出错: {str(e)}", 5000)
            return False
    
    def align_layers(self, align_type):
        """对齐图层 - 从MainWindow迁移"""
        if not self.document:
            return False
            
        selected_indices = self.layer_panel.get_selected_indices()
        if len(selected_indices) < 2:
            self.status_message.emit("请选择至少两个图层", 3000)
            return False
        
        try:
            # 获取选中的图层
            selected_layers = [self.document.layers[i] for i in selected_indices]
            
            # 根据对齐类型进行对齐
            if align_type == "left":
                min_x = min(layer.x for layer in selected_layers)
                for layer in selected_layers:
                    layer.x = min_x
            elif align_type == "right":
                max_x = max(layer.x + layer.width for layer in selected_layers)
                for layer in selected_layers:
                    layer.x = max_x - layer.width
            elif align_type == "top":
                min_y = min(layer.y for layer in selected_layers)
                for layer in selected_layers:
                    layer.y = min_y
            elif align_type == "bottom":
                max_y = max(layer.y + layer.height for layer in selected_layers)
                for layer in selected_layers:
                    layer.y = max_y - layer.height
            elif align_type == "center_horizontal":
                avg_x = sum(layer.x + layer.width/2 for layer in selected_layers) / len(selected_layers)
                for layer in selected_layers:
                    layer.x = int(avg_x - layer.width/2)
            elif align_type == "center_vertical":
                avg_y = sum(layer.y + layer.height/2 for layer in selected_layers) / len(selected_layers)
                for layer in selected_layers:
                    layer.y = int(avg_y - layer.height/2)
            
            # 更新UI
            self.layer_panel.refresh_layers()
            self.main_window.update_canvas()
            
            self.status_message.emit(f"图层已按{align_type}对齐", 2000)
            self.layer_operation_completed.emit("align_layers", True)
            return True
            
        except Exception as e:
            self.status_message.emit(f"对齐图层时出错: {str(e)}", 5000)
            self.layer_operation_completed.emit("align_layers", False)
            return False
    
    def copy_layer_style(self):
        """复制图层样式 - 修复版"""
        if not self.document:
            return False
            
        # 🔧 修复：使用document.selected_layer_index
        if self.document.selected_layer_index < 0:
            self.status_message.emit("请先选择一个图层", 3000)
            return False
        
        try:
            layer = self.document.layers[self.document.selected_layer_index]
            
            # 🔧 修复：复制更完整的样式属性
            style_data = {
                'opacity': getattr(layer, 'opacity', 1.0),
                'visible': getattr(layer, 'visible', True),
                'locked': getattr(layer, 'locked', False),
                'blend_mode': getattr(layer, 'blend_mode', 0),
                'corner_radius': getattr(layer, 'corner_radius', 0),
                'stroke_enabled': getattr(layer, 'stroke_enabled', False),
                'stroke_width': getattr(layer, 'stroke_width', 1),
                'stroke_color': getattr(layer, 'stroke_color', (0, 0, 0, 255)),
                'stroke_type': getattr(layer, 'stroke_type', 0),
                'rotation': getattr(layer, 'rotation', 0.0),
                'flip_horizontal': getattr(layer, 'flip_horizontal', False),
                'flip_vertical': getattr(layer, 'flip_vertical', False),
            }
            
            # 🔧 新增：如果是文字图层，复制文字图层专有样式
            from app.models.text_layer import TextLayer
            if isinstance(layer, TextLayer):
                text_style_data = {
                    'text_color': getattr(layer, 'text_color', (0, 0, 0, 255)),
                    'font_family': getattr(layer, 'font_family', 'Arial'),
                    'font_size': getattr(layer, 'font_size', 16),
                    'font_style': getattr(layer, 'font_style', 'NORMAL'),
                    'text_align': getattr(layer, 'text_align', 'LEFT'),
                    'line_spacing': getattr(layer, 'line_spacing', 1.2),
                    'gradient_enabled': getattr(layer, 'gradient_enabled', False),
                    'gradient_type': getattr(layer, 'gradient_type', 'LINEAR'),
                    'gradient_direction': getattr(layer, 'gradient_direction', 'HORIZONTAL'),
                    'gradient_start_color': getattr(layer, 'gradient_start_color', (0, 0, 0, 255)),
                    'gradient_end_color': getattr(layer, 'gradient_end_color', (255, 255, 255, 255)),
                    'gradient_center_x': getattr(layer, 'gradient_center_x', 0.5),
                    'gradient_center_y': getattr(layer, 'gradient_center_y', 0.5),
                    'background_enabled': getattr(layer, 'background_enabled', False),
                    'background_color': getattr(layer, 'background_color', (255, 255, 255, 255)),
                    'background_padding': getattr(layer, 'background_padding', 5),
                }
                style_data.update(text_style_data)
            
            # 🔧 修复：同步到主窗口的剪贴板
            self.style_clipboard = style_data
            self.main_window.layer_style_clipboard = style_data
            
            self.status_message.emit(f"已复制图层 '{layer.name}' 的样式", 2000)
            self.layer_operation_completed.emit("copy_style", True)
            return True
            
        except Exception as e:
            self.status_message.emit(f"复制样式时出错: {str(e)}", 5000)
            self.layer_operation_completed.emit("copy_style", False)
            return False
    
    def paste_layer_style(self):
        """粘贴图层样式，支持应用到多选图层。"""
        if not self.document:
            return False
            
        # 🔧 修复：检查主窗口的样式剪贴板
        style_clipboard = self.main_window.layer_style_clipboard or self.style_clipboard
        if not style_clipboard:
            self.status_message.emit("剪贴板中没有样式", 3000)
            return False
            
        selected_indices = self.get_selected_indices()
        if not selected_indices:
            self.status_message.emit("请先选择要应用样式的图层", 3000)
            return False

        try:
            changed_count, skipped_locked = self.apply_style_to_selected(style_clipboard)
            if changed_count == 0:
                self.status_message.emit("没有可应用样式的未锁定图层", 3000)
                self.layer_operation_completed.emit("paste_style", False)
                return False

            suffix = f"，跳过 {skipped_locked} 个锁定图层" if skipped_locked else ""
            self.status_message.emit(f"已应用样式到 {changed_count} 个图层{suffix}", 2000)
            self.layer_operation_completed.emit("paste_style", True)
            return True
            
        except Exception as e:
            self.status_message.emit(f"应用样式时出错: {str(e)}", 5000)
            self.layer_operation_completed.emit("paste_style", False)
            return False
