"""Trusted pickle loading helpers.

Project and preset ``.cmp`` files are pickle payloads for backward
compatibility. Pickle must only be used for files the user trusts.
"""

from __future__ import annotations

import logging
import pickle
from typing import BinaryIO, Any

logger = logging.getLogger(__name__)

TRUSTED_PICKLE_WARNING = (
    "正在读取 pickle 格式的项目/预设文件；仅应打开来自可信来源的 .cmp 文件。"
)


def load_trusted_pickle(file_obj: BinaryIO, source_label: str = ".cmp 文件") -> Any:
    """Load a trusted pickle payload and emit a consistent safety warning."""
    logger.warning("%s 来源: %s", TRUSTED_PICKLE_WARNING, source_label)
    return pickle.load(file_obj)
