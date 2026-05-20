import time
from typing import Any, Dict, Optional


def build_export_report(
    *,
    requested_count: int,
    planned_count: int,
    exported_count: int,
    success: bool,
    canceled: bool,
    error_message: str,
    export_mode: str,
    binding_enabled: bool,
    precompute_time: float,
    render_time: float,
    io_time: float,
    total_time: float,
    throughput: float,
    directory: str,
    file_format: str,
    adjustment_info: Optional[Dict[str, Any]] = None,
    extra: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """构建统一导出报告（迭代1：只做观测聚合，不改变业务行为）。"""
    report = {
        "version": 1,
        "timestamp": int(time.time()),
        "summary": {
            "requested_count": int(max(0, requested_count)),
            "planned_count": int(max(0, planned_count)),
            "exported_count": int(max(0, exported_count)),
            "success": bool(success),
            "canceled": bool(canceled),
            "error_message": str(error_message or ""),
        },
        "context": {
            "export_mode": str(export_mode or "unknown"),
            "binding_enabled": bool(binding_enabled),
            "directory": str(directory or ""),
            "file_format": str(file_format or ""),
        },
        "timing": {
            "precompute_time": float(max(0.0, precompute_time or 0.0)),
            "render_time": float(max(0.0, render_time or 0.0)),
            "io_time": float(max(0.0, io_time or 0.0)),
            "total_time": float(max(0.0, total_time or 0.0)),
            "throughput": float(max(0.0, throughput or 0.0)),
        },
        "adjustment": adjustment_info or {"requested": requested_count, "planned": planned_count, "reasons": []},
    }
    if extra:
        report["extra"] = extra
    return report

