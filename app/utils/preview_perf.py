"""Lightweight preview performance monitor.

Enabled via the ``BTPW_PREVIEW_PERF`` environment variable. When enabled the
:class:`PreviewPerfMonitor` records rolling statistics for the most expensive
canvas preview hotspots and dumps a summary to the logger on demand (Ctrl+P
bound in the canvas widget).

The monitor is intentionally cheap: it uses a small fixed-size ring buffer of
samples and only aggregates at the end.  No background threads, no allocations
on the hot path beyond appending to a Python list of floats.
"""

from __future__ import annotations

import collections
import logging
import os
import threading
import time
from typing import Deque, Dict, Optional

logger = logging.getLogger(__name__)


def is_perf_enabled() -> bool:
    """Return True when the preview performance monitor is enabled."""

    return os.environ.get("BTPW_PREVIEW_PERF", "0") == "1"


class _MetricRecorder:
    __slots__ = ("samples", "count", "max", "last")

    def __init__(self, capacity: int = 512) -> None:
        self.samples: Deque[float] = collections.deque(maxlen=capacity)
        self.count: int = 0
        self.max: float = 0.0
        self.last: float = 0.0

    def record(self, value_ms: float) -> None:
        if value_ms < 0.0:
            value_ms = 0.0
        self.samples.append(value_ms)
        self.count += 1
        self.last = value_ms
        if value_ms > self.max:
            self.max = value_ms

    def summary(self) -> Dict[str, float]:
        if not self.samples:
            return {"count": 0, "avg_ms": 0.0, "max_ms": 0.0, "last_ms": 0.0, "p95_ms": 0.0}
        ordered = sorted(self.samples)
        avg = sum(ordered) / len(ordered)
        p95_index = max(0, int(len(ordered) * 0.95) - 1)
        return {
            "count": self.count,
            "avg_ms": round(avg, 3),
            "max_ms": round(self.max, 3),
            "last_ms": round(self.last, 3),
            "p95_ms": round(ordered[p95_index], 3),
        }


class PreviewPerfMonitor:
    """Process-wide singleton monitor.  Cheap enough to leave always-on in debug."""

    _instance: Optional["PreviewPerfMonitor"] = None
    _lock = threading.Lock()

    def __init__(self) -> None:
        self.paint = _MetricRecorder()
        self.composition = _MetricRecorder()
        self.background_render = _MetricRecorder()
        self.pil_to_qimage = _MetricRecorder()
        self.hit_test = _MetricRecorder()
        self.dropped_renders = 0
        self.cancelled_renders = 0
        self.document_changed = 0
        self.layer_changed = 0
        self._last_report_ms = 0.0
        self._start = time.time()

    @classmethod
    def instance(cls) -> "PreviewPerfMonitor":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        with cls._lock:
            cls._instance = cls()

    def record_dropped_render(self) -> None:
        self.dropped_renders += 1

    def record_cancelled_render(self) -> None:
        self.cancelled_renders += 1

    def record_document_changed(self) -> None:
        self.document_changed += 1

    def record_layer_changed(self) -> None:
        self.layer_changed += 1

    def report(self, force: bool = False) -> str:
        now_ms = time.time() * 1000.0
        if not force and now_ms - self._last_report_ms < 1000.0:
            return ""
        self._last_report_ms = now_ms
        elapsed = max(0.001, time.time() - self._start)
        body = (
            "[预览性能] elapsed=%.1fs paint=%s composition=%s bg_render=%s "
            "pil2qimg=%s hit_test=%s dropped=%d cancelled=%d doc_chg=%d layer_chg=%d"
        ) % (
            elapsed,
            self.paint.summary(),
            self.composition.summary(),
            self.background_render.summary(),
            self.pil_to_qimage.summary(),
            self.hit_test.summary(),
            self.dropped_renders,
            self.cancelled_renders,
            self.document_changed,
            self.layer_changed,
        )
        try:
            logger.info(body)
        except Exception:
            pass
        return body


def time_block(metric: _MetricRecorder):
    """Return a context manager that times a block in milliseconds and records it."""

    from contextlib import contextmanager

    @contextmanager
    def _ctx():
        if not is_perf_enabled():
            yield
            return
        start = time.perf_counter()
        try:
            yield
        finally:
            metric.record((time.perf_counter() - start) * 1000.0)

    return _ctx()
