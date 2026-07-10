"""Preview render cancellation token.

A new background preview request creates a fresh :class:`PreviewRenderToken`.
Any in-flight render that observes ``cancelled == True`` must abort the moment
it checks (typically at the start of each per-layer render).  This stops
overlapping drags from keeping stale renders alive.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class PreviewRenderToken:
    """Lightweight cancel handle.  Cheap to allocate; safe to share by reference."""

    generation: int = 0
    cancelled: bool = False

    def cancel(self) -> None:
        self.cancelled = True


class PreviewRenderTokenSource:
    """Owns the active preview render token for one canvas/document."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._generation = 0
        self._current: PreviewRenderToken = PreviewRenderToken(generation=0)

    def next(self) -> PreviewRenderToken:
        """Cancel the current token and return a fresh one."""
        with self._lock:
            self._current.cancel()
            self._generation += 1
            self._current = PreviewRenderToken(generation=self._generation)
            return self._current

    def peek(self) -> PreviewRenderToken:
        with self._lock:
            return self._current

    def cancel(self) -> None:
        with self._lock:
            self._current.cancel()
