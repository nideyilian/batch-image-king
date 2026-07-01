import os
import sys
import threading
import time
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PySide6.QtCore import QObject, Signal
from PySide6.QtWidgets import QApplication

from app.ui.layer_panel import LayerPanel
from app.utils.fast_renderer import FastRenderer, _serialized_preview


class PreviewSerializationTests(unittest.TestCase):
    def test_preview_guard_serializes_threads(self):
        class DummyRenderer:
            def __init__(self):
                self._preview_render_lock = threading.RLock()
                self._counter_lock = threading.Lock()
                self.active = 0
                self.max_active = 0

            @_serialized_preview
            def render(self):
                with self._counter_lock:
                    self.active += 1
                    self.max_active = max(self.max_active, self.active)
                time.sleep(0.03)
                with self._counter_lock:
                    self.active -= 1

        renderer = DummyRenderer()
        threads = [threading.Thread(target=renderer.render) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=1)

        self.assertEqual(renderer.max_active, 1)
        self.assertTrue(all(not thread.is_alive() for thread in threads))

    def test_preview_guard_is_reentrant(self):
        class DummyRenderer:
            def __init__(self):
                self._preview_render_lock = threading.RLock()

            @_serialized_preview
            def inner(self):
                return "ok"

            @_serialized_preview
            def outer(self):
                return self.inner()

        self.assertEqual(DummyRenderer().outer(), "ok")

    def test_only_preview_entry_points_are_serialized(self):
        self.assertTrue(hasattr(FastRenderer.render_preview, "__wrapped__"))
        self.assertTrue(hasattr(FastRenderer.render_preview_incremental, "__wrapped__"))
        self.assertTrue(hasattr(FastRenderer.render_preview_live, "__wrapped__"))
        self.assertFalse(hasattr(FastRenderer.render_batch, "__wrapped__"))


class FakeDocument(QObject):
    layer_changed = Signal()
    document_changed = Signal()
    layers_changed = Signal()
    layer_selected = Signal(int)
    layers_selection_changed = Signal(object)

    def __init__(self):
        super().__init__()
        self.layers = []
        self.selected_layer_index = -1


class LayerPanelLifecycleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_panel_owns_refresh_timers(self):
        panel = LayerPanel(None)
        try:
            self.assertIs(panel._update_timer.parent(), panel)
            self.assertIs(panel._binding_debug_timer.parent(), panel)
        finally:
            panel.deleteLater()

    def test_document_switch_cancels_pending_refresh_and_schedules_once(self):
        panel = LayerPanel(None)
        calls = []

        def record_schedule():
            calls.append(panel._update_timer.isActive())

        panel._schedule_update = record_schedule
        try:
            panel.set_document(FakeDocument())
            calls.clear()
            panel._update_pending = True
            panel._update_timer.start(1000)

            panel.set_document(FakeDocument())

            self.assertEqual(calls, [False])
            self.assertFalse(panel._update_pending)
        finally:
            panel.deleteLater()


if __name__ == "__main__":
    unittest.main()
