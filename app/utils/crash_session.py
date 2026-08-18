# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import os
from pathlib import Path
import re
import tempfile
import uuid
from typing import Optional, Tuple


STATE_FILENAME = "last_run_state.json"


@dataclass(frozen=True)
class CrashNotice:
    message: str
    details: str


def default_log_dir() -> Path:
    try:
        path = Path.home() / ".config" / "批图王" / "logs"
        path.mkdir(parents=True, exist_ok=True)
        return path
    except Exception:
        return Path(tempfile.gettempdir())


def begin_crash_session(
    *,
    log_dir=None,
    crash_log_path: str = "",
    app_log_path: str = "",
    session_id: Optional[str] = None,
    started_at: Optional[str] = None,
) -> Tuple[str, Optional[CrashNotice]]:
    directory = Path(log_dir) if log_dir else default_log_dir()
    state_path = directory / STATE_FILENAME
    previous = _read_state(state_path)
    notice = None
    if (
        previous.get("status") == "running"
        and not bool(previous.get("notice_consumed", False))
    ):
        notice = build_crash_notice(previous)

    current_id = str(session_id or uuid.uuid4().hex)
    current = {
        "version": 1,
        "session_id": current_id,
        "status": "running",
        "started_at": str(started_at or datetime.now().isoformat(timespec="seconds")),
        "crash_log_path": str(crash_log_path or ""),
        "app_log_path": str(app_log_path or ""),
        "notice_consumed": False,
    }
    _atomic_write_state(state_path, current)
    return current_id, notice


def mark_clean_exit(session_id: str, *, log_dir=None) -> bool:
    directory = Path(log_dir) if log_dir else default_log_dir()
    state_path = directory / STATE_FILENAME
    state = _read_state(state_path)
    if not state or str(state.get("session_id", "")) != str(session_id or ""):
        return False
    state["status"] = "clean_exit"
    state["finished_at"] = datetime.now().isoformat(timespec="seconds")
    return _atomic_write_state(state_path, state)


def build_crash_notice(state: dict) -> CrashNotice:
    started_at = str(state.get("started_at") or "未知时间")
    crash_path = str(state.get("crash_log_path") or "")
    app_path = str(state.get("app_log_path") or "")
    crash_text = _read_log_tail(crash_path)
    app_text = _read_log_tail(app_path)
    combined = "\n".join(text for text in (crash_text, app_text) if text)
    location = _extract_business_frame(crash_text or app_text)
    location_line = f"\n具体位置：{location}" if location else ""

    lowered = combined.lower()
    if "windows fatal exception: access violation" in lowered:
        reason = (
            "程序访问了无效内存，通常与原生图像处理、界面控件生命周期"
            "或并发操作有关。"
        )
    elif "memoryerror" in lowered or "unable to allocate" in lowered or "内存不足" in combined:
        reason = "处理图片时内存不够，系统没能继续分配所需空间。"
    else:
        python_error = _extract_python_error(combined)
        if python_error:
            reason = f"程序遇到了没有处理的错误：{python_error}"
        else:
            reason = (
                "日志里没有记录到具体错误，可能是程序被强制结束、"
                "电脑断电，或者当时系统资源不足。"
            )

    message = (
        "上次程序在运行时突然退出了。\n\n"
        f"可能原因：{reason}"
        f"{location_line}\n"
        f"上次启动时间：{started_at}"
    )
    technical = _technical_excerpt(combined)
    details = "\n\n".join(
        part for part in (technical, _log_paths_text(state)) if part
    )
    return CrashNotice(message=message, details=details)


def _read_state(path: Path) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _atomic_write_state(path: Path, payload: dict) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temp = path.with_suffix(path.suffix + ".tmp")
        temp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        os.replace(temp, path)
        return True
    except Exception:
        return False


def _log_paths_text(state: dict) -> str:
    paths = [
        str(state.get("crash_log_path") or ""),
        str(state.get("app_log_path") or ""),
    ]
    paths = [path for path in paths if path]
    if not paths:
        return "没有找到上次运行的日志文件。"
    return "相关日志：\n" + "\n".join(paths)


def _read_log_tail(path_value: str, max_bytes: int = 256 * 1024) -> str:
    if not path_value:
        return ""
    try:
        path = Path(path_value)
        with path.open("rb") as handle:
            size = path.stat().st_size
            handle.seek(max(0, size - max_bytes))
            return handle.read(max_bytes).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _extract_business_frame(text: str) -> str:
    if not text:
        return ""
    current_thread_index = text.lower().find("current thread")
    search_text = text[current_thread_index:] if current_thread_index >= 0 else text
    matches = re.findall(
        r'File "([^"]*(?:app|main)[\\/][^"]+)", line (\d+)(?:,? in ([^\r\n]+))?',
        search_text,
        flags=re.IGNORECASE,
    )
    if not matches:
        return ""
    path, line, function = matches[0]
    normalized = path.replace("\\", "/")
    suffix = f"（{function.strip()}）" if function and function.strip() else ""
    return f"{normalized}:{line}{suffix}"


def _extract_python_error(text: str) -> str:
    if not text:
        return ""
    matches = re.findall(
        r"^([A-Za-z_][\w.]*(?:Error|Exception)):\s*(.+)$",
        text,
        flags=re.MULTILINE,
    )
    if not matches:
        return ""
    name, message = matches[-1]
    return f"{name}: {message.strip()}"[:500]


def _technical_excerpt(text: str) -> str:
    if not text:
        return ""
    lines = [line.rstrip() for line in text.splitlines() if line.strip()]
    if not lines:
        return ""
    return "技术信息：\n" + "\n".join(lines[-30:])[:6000]
