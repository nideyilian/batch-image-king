"""Helpers for loading preset data into temporary or visible documents."""

from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
from app.models.document import Document
from app.models.document_serializer import DocumentSerializer


def create_document_from_preset_data(doc_data, parent=None):
    """Create a Document from serialized preset document data.

    复用 ``DocumentSerializer.restore_document_data``（与打开 .cmp 完全相同的
    恢复路径）：图层树（含分组 children 递归结构）、导出/视图设置、绑定组、
    尺寸匹配配置都按同一套规范恢复，避免预设路径与文档打开路径字段漂移。
    预设特有的标签页元数据在恢复后补齐。
    """
    document = Document(parent=parent)
    DocumentSerializer.restore_document_data(document, doc_data)

    if document.selected_layer_index >= 0:
        document.selected_layer_indices = [document.selected_layer_index]

    document.tab_name = doc_data.get('tab_name') or doc_data.get('original_tab_name') or doc_data.get('name', '预设标签页')
    document.original_tab_name = doc_data.get('original_tab_name') or document.tab_name
    document.is_modified = False
    return document


def documents_from_preset_data(preset_data, parent=None):
    """Return a list of Documents from single-document or multi-document preset data."""
    if isinstance(preset_data, dict) and isinstance(preset_data.get('documents'), list):
        return [
            create_document_from_preset_data(doc_data, parent=parent)
            for doc_data in preset_data.get('documents', [])
            if isinstance(doc_data, dict)
        ]

    if isinstance(preset_data, dict):
        return [create_document_from_preset_data(preset_data, parent=parent)]

    return []
