#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe print helpers.

Normal debug-style output is disabled by default because several preview and
render paths call these helpers at very high frequency. Set BTPW_VERBOSE_LOG=1
to restore verbose console output while diagnosing issues.
"""

import os
import sys


_VERBOSE_LOG = os.environ.get("BTPW_VERBOSE_LOG", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
_ALWAYS_PRINT_PREFIXES = ("[ERROR]", "[CRITICAL]", "[严重错误]")
_ALWAYS_PRINT_KEYWORDS = ("错误", "失败", "Exception", "Traceback")


def _should_print(message: str, debug: bool = False) -> bool:
    if _VERBOSE_LOG:
        return True
    if debug:
        return False
    text = str(message)
    return text.startswith(_ALWAYS_PRINT_PREFIXES) or any(keyword in text for keyword in _ALWAYS_PRINT_KEYWORDS)


def safe_print(*args, file=sys.stdout, sep=" ", end="\n", flush=False, debug=False):
    """Encoding-safe drop-in replacement for builtin ``print``.

    Accepts the same ``*args`` / ``file`` / ``sep`` / ``end`` / ``flush``
    keyword arguments as the builtin, so ``from ... import safe_print as print``
    is a safe, behavior-preserving alias. Only important messages are emitted by
    default (see ``_should_print``); all output goes through an encoding fallback
    so Chinese paths never crash the console.
    """
    if not args:
        text = ""
    else:
        text = sep.join(str(a) for a in args)
    if not _should_print(text, debug=debug):
        return
    try:
        file.write(text + end)
        if flush:
            file.flush()
    except (UnicodeEncodeError, OSError):
        try:
            ascii_text = text.encode("ascii", "ignore").decode("ascii")
            file.write(f"[ENCODING_ISSUE] {ascii_text}{end}")
        except Exception:
            pass
    except Exception:
        pass


def safe_print_debug(message: str):
    """Verbose debug print controlled by BTPW_VERBOSE_LOG."""
    if not _should_print(message, debug=True):
        return
    try:
        print(f"[DEBUG] {message}")
    except (UnicodeEncodeError, OSError):
        try:
            ascii_message = str(message).encode("ascii", "ignore").decode("ascii")
            print(f"[DEBUG] {ascii_message}")
        except Exception:
            print("[DEBUG] Message encoding failed")
