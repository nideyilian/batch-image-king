# -*- coding: utf-8 -*-
"""Optimized batch executor components."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

import os as os_module  # 避免局部变量遮蔽
import time
import threading
import builtins
from collections import Counter, OrderedDict
from contextlib import nullcontext
from dataclasses import dataclass
from typing import List, Dict, Optional, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed, wait, FIRST_COMPLETED
from PIL import Image
import gc
import io
import math

class OptimizedBatchExecutorRuntimeSnapshot(object):
    def _collect_layer_runtime_snapshot(self, layer) -> str:
        """采集图层关键运行时状态，定位任务间状态串扰。"""
        try:
            current_path = str(
                getattr(layer, '_current_image_path', '') or
                getattr(layer, 'current_image_path', '') or
                ''
            )
            return (
                f"path={current_path or 'None'} "
                f"xy=({getattr(layer, 'x', None)},{getattr(layer, 'y', None)}) "
                f"wh=({getattr(layer, 'width', None)},{getattr(layer, 'height', None)}) "
                f"fit={getattr(layer, 'fit_mode', None)} crop={getattr(layer, 'crop_direction', None)} "
                f"rot={getattr(layer, 'rotation', None)} "
                f"rnd=({getattr(layer, '_current_random_offset_x', 0)},"
                f"{getattr(layer, '_current_random_offset_y', 0)},"
                f"{getattr(layer, '_current_random_scale', 1.0)},"
                f"{getattr(layer, '_current_random_rotation', 0.0)}) "
                f"flip=({getattr(layer, 'flip_horizontal', False)},{getattr(layer, 'flip_vertical', False)}) "
                f"clone=({getattr(layer, '_clone_enabled', getattr(layer, 'clone_enabled', False))},"
                f"{getattr(layer, '_clone_rows', getattr(layer, 'clone_rows', 1))},"
                f"{getattr(layer, '_clone_columns', getattr(layer, 'clone_columns', 1))})"
            )
        except Exception as e:
            return f"snapshot_error={str(e)}"

    def _emit_runtime_snapshot_for_indices(self, document, doc_indices, task_name: str, stage: str):
        """输出指定图层索引集合的运行时状态快照。"""
        if not self._export_trace_enabled:
            return
        if not hasattr(document, 'layers'):
            return
        for doc_idx in sorted([int(i) for i in (doc_indices or set())]):
            if doc_idx < 0 or doc_idx >= len(document.layers):
                continue
            layer = document.layers[doc_idx]
            self._emit_export_trace(
                f"任务={task_name} 运行时快照 stage={stage} 文档索引={doc_idx} "
                f"图层={getattr(layer, 'name', '')} {self._collect_layer_runtime_snapshot(layer)}"
            )

    def _capture_document_runtime_fingerprint(self, document, target_doc_indices: Optional[set] = None) -> Dict[int, Dict[str, object]]:
        """采集主文档运行时指纹，用于确认批导没有污染 UI 文档。"""
        snapshot: Dict[int, Dict[str, object]] = {}
        try:
            if not hasattr(document, 'layers'):
                return snapshot
            try:
                from app.models.text_layer import TextLayer
            except Exception:
                TextLayer = None
            target_indices = set(target_doc_indices or [])
            for idx, layer in enumerate(document.layers):
                if target_indices and idx not in target_indices:
                    continue
                item = {
                    'current_image_path': getattr(layer, '_current_image_path', getattr(layer, 'current_image_path', None)),
                    'cached_image_path': getattr(layer, '_cached_image_path', None),
                    'random_offset_x': getattr(layer, '_current_random_offset_x', 0),
                    'random_offset_y': getattr(layer, '_current_random_offset_y', 0),
                    'random_scale': getattr(layer, '_current_random_scale', 1.0),
                    'random_rotation': getattr(layer, '_current_random_rotation', 0.0),
                    'clone_enabled': getattr(layer, '_clone_enabled', getattr(layer, 'clone_enabled', False)),
                    'clone_rows': getattr(layer, '_clone_rows', getattr(layer, 'clone_rows', 1)),
                    'clone_columns': getattr(layer, '_clone_columns', getattr(layer, 'clone_columns', 1)),
                }
                if TextLayer is not None and isinstance(layer, TextLayer):
                    item['current_text'] = getattr(layer, '_current_text', getattr(layer, 'current_text', None))
                snapshot[idx] = item
        except Exception:
            return snapshot
        return snapshot

    def _detect_main_document_runtime_mutation(self, before: Dict[int, Dict[str, object]]) -> List[str]:
        """比较主文档运行时指纹，返回被批导修改过的图层描述。"""
        changes: List[str] = []
        if not before:
            return changes
        try:
            after = self._capture_document_runtime_fingerprint(self.document, set(before.keys()))
            for idx, before_item in before.items():
                after_item = after.get(idx, {})
                if before_item != after_item:
                    layer_name = ""
                    try:
                        layer_name = str(getattr(self.document.layers[idx], 'name', '') or f"图层{idx}")
                    except Exception:
                        layer_name = f"图层{idx}"
                    changes.append(f"{idx}:{layer_name}")
        except Exception:
            return changes
        return changes

    def _prepare_worker_document_seed(self):
        """为线程独立渲染准备文档快照"""
        try:
            from app.models.document_serializer import DocumentSerializer
            self._worker_document_seed = DocumentSerializer.serialize_document_data(self.document)
            self._sanitize_worker_document_seed_runtime_state()
            with self._lock:
                self.stats['worker_document_seed_available'] = 1
        except Exception as e:
            self._worker_document_seed = None
            if self.is_batch_mode:
                print(f"[批处理] 线程文档快照准备失败，将回退共享文档渲染: {e}")

    def _sanitize_worker_document_seed_runtime_state(self):
        """清理快照里的运行期字段，避免 worker 继承 UI 预览临时状态。"""
        try:
            if not isinstance(self._worker_document_seed, dict):
                return
            layers_data = self._worker_document_seed.get('layers', [])
            if not isinstance(layers_data, list):
                return

            runtime_keys = (
                'current_image_path', '_current_image_path',
                'cached_image', '_cached_image', '_cached_image_path',
                '_current_image_cache', '_cache_valid',
                '_current_random_offset_x', '_current_random_offset_y',
                '_current_random_scale', '_current_random_rotation',
            )
            for layer_data in layers_data:
                if not isinstance(layer_data, dict):
                    continue
                for key in runtime_keys:
                    layer_data.pop(key, None)
        except Exception:
            logger.debug("静默异常已忽略: except in utils/obe_runtime_snapshot.py")
            pass

    def _build_visible_doc_indices(self, document) -> List[int]:
        """构建可见图层在 document.layers 中的真实索引列表。"""
        try:
            if not hasattr(document, 'layers'):
                return []
            from app.utils.layer_tree import is_layer_group, is_effectively_visible
            return [
                idx for idx, layer in enumerate(document.layers)
                if not is_layer_group(layer) and is_effectively_visible(layer, document.layers)
            ]
        except Exception:
            return []

    def _should_use_visible_index_mode(self, document, combination, visible_doc_indices: List[int]) -> bool:
        """
        判断组合索引语义：
        - True: 组合使用“可见图层序号”
        - False: 组合使用“文档真实图层索引”
        """
        try:
            if not hasattr(combination, 'layer_states') or not isinstance(combination.layer_states, dict):
                return False
            if not hasattr(document, 'layers'):
                return False
            if len(visible_doc_indices) >= len(document.layers):
                # 无隐藏图层时两种语义等价，默认按文档索引处理
                return False
            keys = [int(k) for k in combination.layer_states.keys() if isinstance(k, int) or str(k).isdigit()]
            if not keys:
                return False
            # 关键判据：若 key 直接命中隐藏图层，说明 key 更可能是“可见层序号”
            hidden_hit = 0
            for k in keys:
                if 0 <= k < len(document.layers) and (not bool(getattr(document.layers[k], 'visible', True))):
                    hidden_hit += 1
            return hidden_hit > 0
        except Exception:
            return False

    def _resolve_combination_layer_index(
        self,
        document,
        combo_layer_idx,
        visible_doc_indices: List[int],
        use_visible_index_mode: bool
    ) -> Optional[int]:
        """把组合里的图层索引解析为 document.layers 的真实索引。"""
        try:
            idx = int(combo_layer_idx)
        except Exception:
            return None

        if use_visible_index_mode:
            if 0 <= idx < len(visible_doc_indices):
                return int(visible_doc_indices[idx])
            return None

        if hasattr(document, 'layers') and 0 <= idx < len(document.layers):
            return idx
        return None

    def _get_target_document_for_render(self):
        """获取当前任务使用的文档对象及是否需要共享锁"""
        if not self.is_batch_mode:
            return self.document, True
        if not self._worker_document_seed:
            with self._lock:
                self.stats['shared_document_render_count'] += 1
            return self.document, True

        cached_doc = getattr(self._thread_local, 'render_document', None)
        if cached_doc is not None:
            return cached_doc, False

        try:
            from app.models.document import Document
            from app.models.document_serializer import DocumentSerializer

            worker_doc = Document(parent=None)
            restored = DocumentSerializer.restore_document_data(worker_doc, self._worker_document_seed)
            if not restored:
                with self._lock:
                    self.stats['worker_document_create_failures'] += 1
                    self.stats['shared_document_render_count'] += 1
                return self.document, True

            worker_doc._is_batch_export_running = True
            worker_doc._export_canceled = False
            self._thread_local.render_document = worker_doc
            return worker_doc, False
        except Exception as e:
            if self.is_batch_mode:
                print(f"[批处理] 创建线程独立文档失败，回退共享文档渲染: {e}")
            with self._lock:
                self.stats['worker_document_create_failures'] += 1
                self.stats['shared_document_render_count'] += 1
            return self.document, True

    def _get_thread_local_fast_renderer(self):
        """获取线程独立 FastRenderer，避免高并发导出时状态串扰。"""
        cached_renderer = getattr(self._thread_local, 'fast_renderer', None)
        if cached_renderer is not None:
            return self._register_worker_renderer(cached_renderer)
        try:
            from app.utils.fast_renderer import FastRenderer
            renderer = FastRenderer()
            self._thread_local.fast_renderer = renderer
            return self._register_worker_renderer(renderer)
        except Exception:
            from app.utils.fast_renderer import get_global_fast_renderer
            return self._register_worker_renderer(get_global_fast_renderer())

    def _collect_plan_mutable_doc_indices(self, plan: PrecomputedExportPlan, document) -> set:
        """收集本次计划里会被动态替换的图层索引。"""
        mutable_indices = set()
        try:
            if not plan or not getattr(plan, 'tasks', None) or not hasattr(document, 'layers'):
                return mutable_indices
            visible_doc_indices = self._build_visible_doc_indices(document)
            for task in plan.tasks:
                combination = getattr(task, 'combination', None)
                if combination is None or not hasattr(combination, 'layer_states'):
                    continue
                use_visible_index_mode = self._should_use_visible_index_mode(document, combination, visible_doc_indices)
                for combo_layer_idx in combination.layer_states.keys():
                    doc_layer_idx = self._resolve_combination_layer_index(
                        document=document,
                        combo_layer_idx=combo_layer_idx,
                        visible_doc_indices=visible_doc_indices,
                        use_visible_index_mode=use_visible_index_mode
                    )
                    if doc_layer_idx is not None:
                        mutable_indices.add(int(doc_layer_idx))
        except Exception:
            return mutable_indices
        return mutable_indices
