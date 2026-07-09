"""Core exception classification helpers."""

from __future__ import annotations

from enum import Enum
import logging


class ErrorCategory(Enum):
    USER_VISIBLE = "user_visible"
    WARNING = "warning"
    INTERNAL_FALLBACK = "internal_fallback"


def handle_core_exception(
    exc: Exception,
    context: str,
    category: ErrorCategory,
    logger: logging.Logger | None = None,
) -> ErrorCategory:
    """Log a core-path exception with an explicit recovery category."""
    log = logger or logging.getLogger(__name__)
    if category is ErrorCategory.USER_VISIBLE:
        log.error("用户可见错误: %s: %s", context, exc, exc_info=True)
    elif category is ErrorCategory.INTERNAL_FALLBACK:
        log.warning("内部降级: %s: %s", context, exc, exc_info=True)
    else:
        log.warning("警告: %s: %s", context, exc, exc_info=True)
    return category
