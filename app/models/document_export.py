"""``DocumentExport`` 组合 mixin：5 个子 mixin 的聚合。

历史说明
--------

这是 P1 任务 5A 的拆分 shim：原 ``app/models/document_export.py`` 是一个
1814 行的 mixin（21 个方法 + 4 个 dead code 方法），已按职责拆分为 5 个
子 mixin：

- ``DocumentExportAnalysis``    —— 文档状态预分析
- ``DocumentExportBatch``       —— 批量导出主流程
- ``DocumentExportRender``      —— 渲染 + 单图导出
- ``DocumentExportSerialize``   —— 序列化 / 反序列化
- ``DocumentExportFilename``    —— 文件名模板 + 绑定组合 + 组合数估算

本文件保留 ``DocumentExport`` 类名（继承所有 5 个子 mixin），作为
``Document`` 父类链中的挂载点，确保外部代码：

- ``from app.models.document_export import DocumentExport``
- ``class Document(DocumentLayers, DocumentRandomize, DocumentRender, DocumentExport, QObject)``

都不需要修改。

Dead code（无任何调用方）已删除：
- ``_optimized_batch_export`` (1454)
- ``enable_optimized_export`` (1542)
- ``get_export_performance_info`` (1552)
- ``batch_export_enhanced`` (1590)

顺手修复的预存 bug：
- ``_get_binding_common_categories`` 中 ``is_text_layer_virtual_path`` 未 import
- ``_set_binding_category_combination`` 中 ``is_text_layer_virtual_path`` /
  ``parse_text_layer_virtual_path`` 未 import
"""
from __future__ import annotations

import logging

from app.models.document_export_analysis import DocumentExportAnalysis
from app.models.document_export_batch import DocumentExportBatch
from app.models.document_export_filename import DocumentExportFilename
from app.models.document_export_render import DocumentExportRender
from app.models.document_export_serialize import DocumentExportSerialize

logger = logging.getLogger(__name__)


class DocumentExport(
    DocumentExportAnalysis,
    DocumentExportBatch,
    DocumentExportRender,
    DocumentExportSerialize,
    DocumentExportFilename,
):
    """Document 导出相关 mixin 的组合类（5 个子 mixin）。"""


__all__ = ["DocumentExport"]
