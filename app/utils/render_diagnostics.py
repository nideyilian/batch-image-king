"""
运行时渲染诊断日志工具。

通过环境变量 `BTPW_RENDER_DIAG=1` 启用。
"""

import os
import builtins
import threading
from typing import Any, Dict


_LOCK = threading.Lock()
_SEEN = set()


def _enabled() -> bool:
    value = str(os.environ.get("BTPW_RENDER_DIAG", "0")).strip().lower()
    return value in ("1", "true", "yes", "on")


def _fmt_kv(data: Dict[str, Any]) -> str:
    parts = []
    for k, v in data.items():
        parts.append(f"{k}={v}")
    return ", ".join(parts)


def log_branch(source: str, branch: str, **kwargs):
    """记录渲染分支。默认按参数去重，避免刷屏。"""
    if not _enabled():
        return
    payload = {"branch": branch, **kwargs}
    key = ("branch", source, tuple(sorted(payload.items())))
    with _LOCK:
        if key in _SEEN:
            return
        _SEEN.add(key)
    builtins.print(f"[渲染诊断][{source}] {_fmt_kv(payload)}")


def log_sampling(source: str, width: int, height: int, edge_size: int, scale: int, **kwargs):
    """记录采样倍率。默认按参数去重，避免刷屏。"""
    if not _enabled():
        return
    payload = {
        "width": int(width),
        "height": int(height),
        "edge_size": int(edge_size),
        "scale": int(scale),
        **kwargs,
    }
    key = ("sampling", source, tuple(sorted(payload.items())))
    with _LOCK:
        if key in _SEEN:
            return
        _SEEN.add(key)
    builtins.print(f"[渲染诊断][{source}] {_fmt_kv(payload)}")
