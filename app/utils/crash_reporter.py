# -*- coding: utf-8 -*-
import faulthandler
import logging

logger = logging.getLogger(__name__)
import sys
import tempfile
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional


_CRASH_FILE = None
_CRASH_FILE_PATH = ""
_ORIGINAL_THREADING_EXCEPTHOOK = None
_ORIGINAL_UNRAISABLEHOOK = None
_QT_MESSAGE_HANDLER = None


def default_log_dir() -> Path:
    try:
        log_dir = Path.home() / ".config" / "\u6279\u56fe\u738b" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir
    except Exception:
        return Path(tempfile.gettempdir())


def install_crash_reporter(
    logger: Optional[logging.Logger] = None,
    log_dir: Optional[str] = None,
) -> str:
    """Enable process-wide crash diagnostics and return the crash log path."""
    global _CRASH_FILE, _CRASH_FILE_PATH

    if _CRASH_FILE is not None and not _CRASH_FILE.closed:
        return _CRASH_FILE_PATH

    target_dir = Path(log_dir) if log_dir else default_log_dir()
    target_dir.mkdir(parents=True, exist_ok=True)
    _CRASH_FILE_PATH = str(target_dir / f"crash_{datetime.now():%Y%m%d_%H%M%S}.log")
    _CRASH_FILE = open(
        _CRASH_FILE_PATH,
        "a",
        encoding="utf-8",
        errors="backslashreplace",
        buffering=1,
    )

    _write_line("=" * 80)
    _write_line(f"Crash diagnostics started: {datetime.now().isoformat(timespec='seconds')}")
    _write_line(f"Python: {sys.version}")
    _write_line(f"Executable: {sys.executable}")
    _write_line("=" * 80)

    try:
        faulthandler.enable(file=_CRASH_FILE, all_threads=True)
    except Exception as exc:
        _log_warning(logger, f"Failed to enable faulthandler: {exc}")

    _install_threading_hook(logger)
    _install_unraisable_hook(logger)
    _install_qt_message_handler(logger)
    return _CRASH_FILE_PATH


def dump_current_traceback(label: str = "manual dump") -> None:
    if _CRASH_FILE is None or _CRASH_FILE.closed:
        return
    try:
        _write_line("")
        _write_line(f"[traceback dump] {label}")
        faulthandler.dump_traceback(file=_CRASH_FILE, all_threads=True)
    except Exception:
        logger.debug("静默异常已忽略: except in utils/crash_reporter.py")
        pass


def _install_threading_hook(logger: Optional[logging.Logger]) -> None:
    global _ORIGINAL_THREADING_EXCEPTHOOK
    if not hasattr(threading, "excepthook"):
        return
    if _ORIGINAL_THREADING_EXCEPTHOOK is not None:
        return

    _ORIGINAL_THREADING_EXCEPTHOOK = threading.excepthook

    def _threading_hook(args):
        thread_name = getattr(getattr(args, "thread", None), "name", "<unknown>")
        _log_exception(
            logger,
            f"Uncaught exception in thread {thread_name}",
            args.exc_type,
            args.exc_value,
            args.exc_traceback,
        )
        try:
            _ORIGINAL_THREADING_EXCEPTHOOK(args)
        except Exception:
            logger.debug("静默异常已忽略: except in utils/crash_reporter.py")
            pass

    threading.excepthook = _threading_hook


def _install_unraisable_hook(logger: Optional[logging.Logger]) -> None:
    global _ORIGINAL_UNRAISABLEHOOK
    if not hasattr(sys, "unraisablehook"):
        return
    if _ORIGINAL_UNRAISABLEHOOK is not None:
        return

    _ORIGINAL_UNRAISABLEHOOK = sys.unraisablehook

    def _unraisable_hook(unraisable):
        err_msg = getattr(unraisable, "err_msg", None)
        obj = getattr(unraisable, "object", None)
        _write_line("")
        _write_line(f"[unraisable] err_msg={err_msg!r} object={obj!r}")
        _log_exception(
            logger,
            "Unraisable exception",
            unraisable.exc_type,
            unraisable.exc_value,
            unraisable.exc_traceback,
        )
        try:
            _ORIGINAL_UNRAISABLEHOOK(unraisable)
        except Exception:
            logger.debug("静默异常已忽略: except in utils/crash_reporter.py")
            pass

    sys.unraisablehook = _unraisable_hook


def _install_qt_message_handler(logger: Optional[logging.Logger]) -> None:
    global _QT_MESSAGE_HANDLER
    if _QT_MESSAGE_HANDLER is not None:
        return
    try:
        from PySide6.QtCore import QtMsgType, qInstallMessageHandler
    except Exception as exc:
        _log_warning(logger, f"Failed to import Qt message handler: {exc}")
        return

    def _qt_handler(mode, context, message):
        level_name = _qt_level_name(QtMsgType, mode)
        file_name = getattr(context, "file", "") or ""
        line = getattr(context, "line", 0) or 0
        function = getattr(context, "function", "") or ""
        detail = f"[Qt {level_name}] {message}"
        if file_name or function:
            detail += f" ({file_name}:{line} {function})"
        _write_line(detail)
        if logger is not None:
            try:
                level = logging.CRITICAL if level_name == "fatal" else logging.ERROR
                if level_name in ("debug", "info"):
                    level = logging.INFO
                elif level_name == "warning":
                    level = logging.WARNING
                logger.log(level, detail)
            except Exception:
                logger.debug("静默异常已忽略: except in utils/crash_reporter.py")
                pass

    _QT_MESSAGE_HANDLER = _qt_handler
    try:
        qInstallMessageHandler(_QT_MESSAGE_HANDLER)
    except Exception as exc:
        _log_warning(logger, f"Failed to install Qt message handler: {exc}")


def _qt_level_name(qt_msg_type, mode) -> str:
    try:
        if mode == qt_msg_type.QtDebugMsg:
            return "debug"
        if mode == qt_msg_type.QtInfoMsg:
            return "info"
        if mode == qt_msg_type.QtWarningMsg:
            return "warning"
        if mode == qt_msg_type.QtCriticalMsg:
            return "critical"
        if mode == qt_msg_type.QtFatalMsg:
            return "fatal"
    except Exception:
        logger.debug("静默异常已忽略: except in utils/crash_reporter.py")
        pass
    return str(mode)


def _log_exception(logger, title, exc_type, exc_value, exc_traceback) -> None:
    _write_line("")
    _write_line(f"[exception] {title}")
    try:
        _write_line("".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))
    except Exception:
        _write_line(f"{exc_type!r}: {exc_value!r}")
    if logger is not None:
        try:
            logger.error(title, exc_info=(exc_type, exc_value, exc_traceback))
        except Exception:
            logger.debug("静默异常已忽略: except in utils/crash_reporter.py")
            pass


def _log_warning(logger, message: str) -> None:
    _write_line(f"[warning] {message}")
    if logger is not None:
        try:
            logger.warning(message)
        except Exception:
            logger.debug("静默异常已忽略: except in utils/crash_reporter.py")
            pass


def _write_line(message: str) -> None:
    if _CRASH_FILE is None or _CRASH_FILE.closed:
        return
    try:
        _CRASH_FILE.write(str(message) + "\n")
        _CRASH_FILE.flush()
    except Exception:
        logger.debug("静默异常已忽略: except in utils/crash_reporter.py")
        pass
