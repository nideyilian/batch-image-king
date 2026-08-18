import pytest


pytestmark = pytest.mark.unit


class DummySignal:
    def __init__(self):
        self.emit_count = 0

    def emit(self):
        self.emit_count += 1


class DummyDocument:
    def __init__(self):
        self._needs_cache_refresh = False
        self._quick_first_frame = False
        self.document_changed = DummySignal()


def test_prime_initial_preview_marks_document_for_quick_first_frame():
    from app.utils.initial_preview import prime_initial_preview

    document = DummyDocument()

    prime_initial_preview(document)

    assert document._needs_cache_refresh is True
    assert document._quick_first_frame is True
    assert document.document_changed.emit_count == 1
