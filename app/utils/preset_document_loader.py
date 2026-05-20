"""Helpers for loading preset data into temporary or visible documents."""

from app.models.document import Document


def create_document_from_preset_data(doc_data, parent=None):
    """Create a Document from serialized preset document data."""
    document = Document(parent=parent)
    document.canvas_width = int(doc_data.get('canvas_width', 800) or 800)
    document.canvas_height = int(doc_data.get('canvas_height', 600) or 600)

    for layer_data in doc_data.get('layers', []) or []:
        layer = document.create_layer_from_data(layer_data)
        if layer is not None:
            document.layers.append(layer)

    document.selected_layer_index = int(doc_data.get('selected_layer_index', -1) or -1)
    document.selected_layer_indices = [document.selected_layer_index] if document.selected_layer_index >= 0 else []

    if 'export_settings' in doc_data and isinstance(doc_data.get('export_settings'), dict):
        settings = document._build_default_export_settings()
        settings.update(doc_data.get('export_settings') or {})
        document.export_settings = settings

    if hasattr(document, 'set_view_settings'):
        document.set_view_settings(doc_data.get('view_settings', {}) or {})

    if 'binding_groups' in doc_data and hasattr(document, 'binding_manager'):
        try:
            document.binding_manager.deserialize(doc_data.get('binding_groups', {}) or {}, document.layers)
        except Exception as exc:
            print(f"加载预设绑定组失败: {exc}")

    if hasattr(document, 'layer_size_match_manager') and document.layer_size_match_manager is not None:
        try:
            document.layer_size_match_manager.deserialize(doc_data.get('layer_size_matches', {}) or {})
        except Exception as exc:
            print(f"加载预设尺寸匹配配置失败: {exc}")

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
