#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Safe print helpers.

Normal debug-style output is disabled by default because several preview and
render paths call these helpers at very high frequency. Set BTPW_VERBOSE_LOG=1
to restore verbose console output while diagnosing issues.
"""

import os


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


def safe_print(message: str):
    """Print only important messages by default, with encoding fallback."""
    if not _should_print(message):
        return
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            ascii_message = str(message).encode("ascii", "ignore").decode("ascii")
            print(f"[ENCODING_ISSUE] {ascii_message}")
        except Exception:
            print("[ENCODING_ERROR] Message encoding failed - unable to display content")


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
