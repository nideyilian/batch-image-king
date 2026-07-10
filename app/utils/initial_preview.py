"""Helpers for showing a loaded document preview quickly."""


def prime_initial_preview(document):
    """Mark a loaded document so canvas renders a low-cost first frame first."""
    if document is None:
        return

    try:
        document._needs_cache_refresh = True
        document._quick_first_frame = True
    except Exception:
        return

    signal = getattr(document, "document_changed", None)
    emit = getattr(signal, "emit", None)
    if callable(emit):
        emit()
