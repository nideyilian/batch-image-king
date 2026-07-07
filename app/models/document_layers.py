import os
import random
import json
import pickle
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
from PIL.Image import Resampling, Transpose
import numpy as np
from PySide6.QtCore import QObject, Signal
import re
import glob
import gc
from app.models.layer_new import Layer as NewLayer
from app.models.document_blend import BlendMode
from app.models.document_blend import Blender
from typing import List, Tuple
from app.models.binding_manager import BindingGroup
import time
import hashlib
from app.utils.render_diagnostics import log_branch, log_sampling
from app.utils.print_utils import safe_print as _safe_print
from app.models.layer_size_match_manager import LayerSizeMatchManager

# 统一使用编码安全输出，避免GBK控制台因emoji日志中断流程
print = _safe_print


class DocumentLayers:
    """Document 方法拆分 mixin，保持与 Document 完全兼容（通过多重继承组合）。"""

    def add_layer(self, name, x, y, width, height, image_source=None, use_original_size=False, is_folder=True):
        # 保存当前状态
        self.save_state("添加图层前")
        
        # 使用新的Layer模型，支持形状功能
        # 自动判断图像源类型，避免单文件被当作文件夹导致加载失败
        try:
            def _normalize_path(p):
                if not p:
                    return p
                p = p.replace('/', os.sep)
                if p.startswith('\\\\'):
                    return p
                if p.startswith('//'):
                    server_share = p.lstrip('/').replace('/', '\\')
                    return f"\\\\{server_share}"
                return os.path.normpath(p)
            src_norm = _normalize_path(image_source) if image_source else image_source
            if src_norm:
                if os.path.isfile(src_norm):
                    is_folder = False
                elif os.path.isdir(src_norm):
                    is_folder = True
        except Exception:
            pass

        layer = NewLayer(name, x, y, width, height, image_source, use_original_size, is_folder)
        try:
            if hasattr(layer, 'changed') and hasattr(layer.changed, 'connect'):
                layer.changed.connect(self.document_changed.emit)
        except Exception:
            pass
        self.layers.append(layer)
        self.selected_layer_index = len(self.layers) - 1
        self.selected_layer_indices = [self.selected_layer_index]
        self._invalidate_render_cache()
        self.layer_changed.emit()
        
        # 发送图层选中信号，确保UI更新选中状态
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存添加后的状态
        self.save_state("添加图层")
        
        return layer
    


    def add_shaped_layer(self, shaped_layer):
        """添加异形图层"""
        # 保存当前状态
        self.save_state("添加异形图层前")
        
        # 安全地连接异形图层的信号
        try:
            if hasattr(shaped_layer, 'changed') and hasattr(shaped_layer.changed, 'connect'):
                shaped_layer.changed.connect(self.document_changed.emit)
        except Exception as e:
            print(f"警告：无法连接异形图层信号: {e}")
        
        # 将异形图层添加到图层列表
        self.layers.append(shaped_layer)
        self.selected_layer_index = len(self.layers) - 1
        self.selected_layer_indices = [self.selected_layer_index]
        self._invalidate_render_cache()
        self.layer_changed.emit()
        
        # 发送图层选中信号，确保UI更新选中状态
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存添加后的状态
        self.save_state("添加异形图层")
        
        return shaped_layer
    


    def add_text_layer(self, text_layer):
        """添加文字图层"""
        # 保存当前状态
        self.save_state("添加文字图层前")
        
        # 安全地连接文字图层的信号
        try:
            if hasattr(text_layer, 'changed') and hasattr(text_layer.changed, 'connect'):
                text_layer.changed.connect(self.document_changed.emit)
            if hasattr(text_layer, 'text_changed') and hasattr(text_layer.text_changed, 'connect'):
                text_layer.text_changed.connect(self.document_changed.emit)
        except Exception as e:
            print(f"警告：无法连接文字图层信号: {e}")
        
        # 将文字图层添加到图层列表
        self.layers.append(text_layer)
        self.selected_layer_index = len(self.layers) - 1
        self.selected_layer_indices = [self.selected_layer_index]
        self._invalidate_render_cache()
        self.layer_changed.emit()
        
        # 发送图层选中信号，确保UI更新选中状态
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存添加后的状态
        self.save_state("添加文字图层")
        
        return text_layer
    


    def add_existing_layer(self, layer):
        """添加已存在的图层对象（用于复制粘贴功能）"""
        # 保存当前状态
        self.save_state("添加图层前")
        
        # 安全地连接图层的信号（如果存在的话）
        try:
            if hasattr(layer, 'changed') and hasattr(layer.changed, 'connect'):
                layer.changed.connect(self.document_changed.emit)
        except Exception as e:
            print(f"警告：无法连接图层信号: {e}")
        
        # 将图层添加到图层列表
        self.layers.append(layer)
        self.selected_layer_index = len(self.layers) - 1
        self.selected_layer_indices = [self.selected_layer_index]
        self.layer_changed.emit()
        
        # 发送图层选中信号，确保UI更新选中状态
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存添加后的状态
        self.save_state("添加图层")
        
        return layer
        


    def remove_layer(self, index):
        if 0 <= index < len(self.layers):
            # 检查图层是否锁定
            if self.layers[index].locked:
                return
                
            # 保存当前状态
            self.save_state("删除图层前")
            
            # 获取要删除的图层
            layer_to_remove = self.layers[index]
            
            # 从绑定管理器中移除图层
            if hasattr(self, 'binding_manager') and self.binding_manager:
                self.binding_manager.remove_layer_from_group(layer_to_remove)
                print(f"从绑定组中移除图层: {layer_to_remove.name}")
            
            del self.layers[index]
            if index == self.selected_layer_index:
                if len(self.layers) > 0:
                    self.selected_layer_index = min(index, len(self.layers) - 1)
                else:
                    self.selected_layer_index = -1
            elif index < self.selected_layer_index:
                self.selected_layer_index -= 1
            self.selected_layer_indices = [
                (idx - 1 if idx > index else idx)
                for idx in getattr(self, 'selected_layer_indices', [])
                if idx != index and 0 <= idx < len(self.layers) + 1
            ]
            self.selected_layer_indices = [
                idx for idx in self.selected_layer_indices if 0 <= idx < len(self.layers)
            ]
            if self.selected_layer_index >= 0 and self.selected_layer_index not in self.selected_layer_indices:
                self.selected_layer_indices.insert(0, self.selected_layer_index)

            self._invalidate_render_cache()
            self.layer_changed.emit()
            self.layer_selected.emit(self.selected_layer_index)
            self.layers_selection_changed.emit(list(self.selected_layer_indices))
            
            # 保存删除后的状态
            self.save_state("删除图层")
    


    def move_layer_up(self, index):
        if 0 < index < len(self.layers):
            # 检查图层是否锁定
            if self.layers[index].locked or self.layers[index-1].locked:
                return
                
            # 保存当前状态
            self.save_state("移动图层前")
            
            self.layers[index], self.layers[index-1] = self.layers[index-1], self.layers[index]
            if self.selected_layer_index == index:
                self.selected_layer_index -= 1
            elif self.selected_layer_index == index - 1:
                self.selected_layer_index += 1
            self.selected_layer_indices = [
                idx - 1 if idx == index else idx + 1 if idx == index - 1 else idx
                for idx in getattr(self, 'selected_layer_indices', [])
            ]
            self.layer_changed.emit()
            self.layer_selected.emit(self.selected_layer_index)
            self.layers_selection_changed.emit(list(self.selected_layer_indices))
            
            # 保存移动后的状态
            self.save_state("上移图层")
            


    def move_layer_down(self, index):
        if 0 <= index < len(self.layers) - 1:
            # 检查图层是否锁定
            if self.layers[index].locked or self.layers[index+1].locked:
                return
                
            # 保存当前状态
            self.save_state("移动图层前")
            
            self.layers[index], self.layers[index+1] = self.layers[index+1], self.layers[index]
            if self.selected_layer_index == index:
                self.selected_layer_index += 1
            elif self.selected_layer_index == index + 1:
                self.selected_layer_index -= 1
            self.selected_layer_indices = [
                idx + 1 if idx == index else idx - 1 if idx == index + 1 else idx
                for idx in getattr(self, 'selected_layer_indices', [])
            ]
            self.layer_changed.emit()
            self.layer_selected.emit(self.selected_layer_index)
            self.layers_selection_changed.emit(list(self.selected_layer_indices))
            
            # 保存移动后的状态
            self.save_state("下移图层")
    


    def move_layer(self, from_index, to_index):
        """移动图层从一个位置到另一个位置"""
        if not (0 <= from_index < len(self.layers) and 0 <= to_index < len(self.layers)):
            return
            
        if from_index == to_index:
            return
            
        # 检查图层是否锁定
        if self.layers[from_index].locked:
            return
            
        # 保存当前状态
        self.save_state("移动图层前")
        
        # 记住选中的图层
        selected_layer = self.layers[self.selected_layer_index] if self.selected_layer_index >= 0 else None
        selected_layer_objects = [
            self.layers[idx]
            for idx in getattr(self, 'selected_layer_indices', [])
            if 0 <= idx < len(self.layers)
        ]
        
        # 移动图层
        layer = self.layers.pop(from_index)
        self.layers.insert(to_index, layer)
        
        # 更新选中的图层索引
        if selected_layer:
            try:
                self.selected_layer_index = self.layers.index(selected_layer)
            except ValueError:
                self.selected_layer_index = min(self.selected_layer_index, len(self.layers) - 1)
        self.selected_layer_indices = []
        for selected in selected_layer_objects:
            try:
                new_idx = self.layers.index(selected)
            except ValueError:
                continue
            if new_idx not in self.selected_layer_indices:
                self.selected_layer_indices.append(new_idx)
        if self.selected_layer_index >= 0 and self.selected_layer_index not in self.selected_layer_indices:
            self.selected_layer_indices.insert(0, self.selected_layer_index)
        
        # 发送图层变化信号
        self.layer_changed.emit()
        self.layer_selected.emit(self.selected_layer_index)
        self.layers_selection_changed.emit(list(self.selected_layer_indices))
        
        # 保存移动后的状态
        self.save_state("移动图层")
    


    def select_layer(self, index):
        if 0 <= index < len(self.layers):
            self.select_layers([index], primary_index=index)
        else:
            self.select_layers([], primary_index=-1)



    def select_layers(self, indices, primary_index=None):
        """选择一个或多个图层，并保持 selected_layer_index 兼容旧单选逻辑。"""
        valid_indices = []
        for idx in indices or []:
            try:
                idx = int(idx)
            except (TypeError, ValueError):
                continue
            if 0 <= idx < len(self.layers) and idx not in valid_indices:
                valid_indices.append(idx)

        if primary_index is None:
            primary = valid_indices[0] if valid_indices else -1
        else:
            try:
                primary = int(primary_index)
            except (TypeError, ValueError):
                primary = -1
            if primary not in valid_indices:
                primary = valid_indices[0] if valid_indices else -1

        selection_changed = (
            list(getattr(self, 'selected_layer_indices', [])) != valid_indices or
            self.selected_layer_index != primary
        )
        self.selected_layer_indices = valid_indices
        self.selected_layer_index = primary

        if selection_changed:
            self.layer_changed.emit()
            self.layer_selected.emit(primary)
            self.layers_selection_changed.emit(list(valid_indices))
            


    def update_layer(self, layer_index):
        """更新指定图层，避免全局重绘"""
        if 0 <= layer_index < len(self.layers):
            layer = self.layers[layer_index]
            # 清理该图层的缓存
            if hasattr(layer, 'clear_cache'):
                layer.clear_cache()
            # 发送精确的图层更新信号
            self.layer_updated.emit(layer_index)
            print(f"更新图层 {layer_index}: {layer.name}")



    def update_specific_layers(self, layer_indices):
        """更新指定的多个图层"""
        for layer_index in layer_indices:
            if 0 <= layer_index < len(self.layers):
                layer = self.layers[layer_index]
                # 清理该图层的缓存
                if hasattr(layer, 'clear_cache'):
                    layer.clear_cache()
                # 发送精确的图层更新信号
                self.layer_updated.emit(layer_index)
        print(f"更新图层: {layer_indices}")
