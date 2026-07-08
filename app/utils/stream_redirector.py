# -*- coding: utf-8 -*-
import logging

logger = logging.getLogger(__name__)
import sys
import tempfile
from datetime import datetime
from pathlib import Path


_STREAM_HANDLES = []


class NullWriter:
    """Writer used only when file-backed stream logging is unavailable."""

    def write(self, message):
        pass

    def flush(self):
        pass

    def isatty(self):
        return False


class StreamLogWriter:
    """File-backed stream used when packaged apps have no console."""

    def __init__(self, stream_name):
        self._handle = _open_stream_log(stream_name)

    def write(self, message):
        if not message or self._handle is None:
            return
        try:
            self._handle.write(str(message))
            self._handle.flush()
        except Exception:
            logger.debug("静默异常已忽略: except in utils/stream_redirector.py")
            pass

    def flush(self):
        try:
            if self._handle is not None:
                self._handle.flush()
        except Exception:
            logger.debug("静默异常已忽略: except in utils/stream_redirector.py")
            pass

    def isatty(self):
        return False

    def fileno(self):
        if self._handle is None:
            raise OSError("stream log is unavailable")
        return self._handle.fileno()


def _default_log_dir():
    try:
        log_dir = Path.home() / ".config" / "\u6279\u56fe\u738b" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    except Exception:
        return Path(tempfile.gettempdir())


def _open_stream_log(stream_name):
    try:
        log_dir = _default_log_dir()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_path = log_dir / f"{stream_name}_{timestamp}.log"
        handle = open(
            log_path,
            "a",
            encoding="utf-8",
            errors="backslashreplace",
            buffering=1,
        )
        _STREAM_HANDLES.append(handle)
        return handle
    except Exception:
        return None


def _make_writer(stream_name):
    writer = StreamLogWriter(stream_name)
    if writer._handle is None:
        return NullWriter()
    return writer


def setup_streams():
    """
    Configure stdout/stderr early.

    In PyInstaller --noconsole mode, stdout and stderr can be None. Redirecting
    them to local files keeps print() and traceback.print_exc() useful after a
    packaged crash instead of silently discarding diagnostics.
    """
    if sys.stdout is None:
        sys.stdout = _make_writer("stdout")
    if sys.stderr is None:
        sys.stderr = _make_writer("stderr")

    if sys.__stdout__ is None:
        sys.__stdout__ = sys.stdout
    if sys.__stderr__ is None:
        sys.__stderr__ = sys.stderr
