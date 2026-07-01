# -*- coding: utf-8 -*-
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
import pickle
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable, Optional


@dataclass
class WorkerExportResult:
    attempted: bool
    success: bool
    fallback_allowed: bool = False
    error: str = ""
    manifest_path: str = ""


def should_use_export_worker(document, count: int) -> bool:
    """Return True when large batch export should run in an isolated process."""
    if os.environ.get("BTPW_EXPORT_WORKER_CHILD", "0") == "1":
        return False
    if os.environ.get("BTPW_DISABLE_EXPORT_WORKER", "0") == "1":
        return False
    if os.environ.get("BTPW_FORCE_EXPORT_WORKER", "0") == "1":
        return True

    settings = getattr(document, "export_settings", {}) or {}
    if not bool(settings.get("export_external_worker_enabled", True)):
        return False

    try:
        configured_threshold = int(settings.get("export_worker_min_count", 200) or 200)
        threshold = max(1, min(configured_threshold, 200))
    except Exception:
        threshold = 200

    try:
        visible_layers = len([layer for layer in getattr(document, "layers", []) if getattr(layer, "visible", True)])
    except Exception:
        visible_layers = 0

    return int(count or 0) >= threshold or (int(count or 0) >= 200 and visible_layers >= 8)


def export_with_worker(
    document,
    *,
    directory: str,
    count: int,
    filename_template: str,
    file_format: str,
    start_index: int = 1,
    traverse_mode: bool = False,
    avoid_duplicates: bool = True,
    progress_callback: Optional[Callable[[int], None]] = None,
    file_completed_callback: Optional[Callable[[str], None]] = None,
    stage_callback: Optional[Callable[[str], None]] = None,
    cancel_callback: Optional[Callable[[], bool]] = None,
) -> WorkerExportResult:
    """Run batch export in a separate process and mirror progress via manifest."""
    try:
        os.makedirs(directory, exist_ok=True)
        work_dir = Path(directory) / ".btpw_export_worker"
        work_dir.mkdir(parents=True, exist_ok=True)

        manifest_path = _manifest_path(
            directory=directory,
            filename_template=filename_template,
            file_format=file_format,
            start_index=start_index,
        )
        snapshot_path = str(work_dir / f"document_snapshot_{int(time.time() * 1000)}.cmp")
        request_path = str(work_dir / f"request_{int(time.time() * 1000)}.json")
        cancel_path = str(work_dir / f"cancel_{int(time.time() * 1000)}.flag")
        stdout_path = str(work_dir / "worker_stdout.log")
        stderr_path = str(work_dir / "worker_stderr.log")

        _write_document_snapshot(document, snapshot_path)
        request = {
            "version": 1,
            "document_snapshot": snapshot_path,
            "manifest_path": manifest_path,
            "cancel_path": cancel_path,
            "directory": directory,
            "count": int(count),
            "filename_template": filename_template or "image_{number:04d}",
            "file_format": file_format or "png",
            "start_index": int(start_index),
            "traverse_mode": bool(traverse_mode),
            "avoid_duplicates": bool(avoid_duplicates),
            "resume": bool((getattr(document, "export_settings", {}) or {}).get("export_worker_resume_enabled", True)),
        }
        _atomic_write_json(request_path, request)
    except Exception as exc:
        return WorkerExportResult(False, False, True, f"无法准备独立导出进程: {exc}")

    cmd = _worker_command(request_path)
    env = os.environ.copy()
    env["BTPW_EXPORT_WORKER_CHILD"] = "1"
    env.setdefault("PYTHONUTF8", "1")

    creationflags = 0
    if os.name == "nt":
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)

    if stage_callback:
        stage_callback("独立导出进程")

    last_progress = -1
    last_file = ""
    last_stage = ""
    proc = None
    try:
        with open(stdout_path, "a", encoding="utf-8", errors="backslashreplace") as stdout, open(
            stderr_path,
            "a",
            encoding="utf-8",
            errors="backslashreplace",
        ) as stderr:
            proc = subprocess.Popen(
                cmd,
                cwd=str(_project_root()),
                env=env,
                stdout=stdout,
                stderr=stderr,
                creationflags=creationflags,
            )

            while proc.poll() is None:
                if cancel_callback and cancel_callback():
                    _touch(cancel_path)
                    if stage_callback:
                        stage_callback("正在取消独立导出进程")
                    try:
                        proc.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        proc.terminate()
                        try:
                            proc.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            proc.kill()
                    break

                manifest = _read_json(manifest_path)
                progress = _manifest_progress(manifest)
                if progress is not None and progress != last_progress:
                    last_progress = progress
                    if progress_callback:
                        progress_callback(progress)
                current_file = _manifest_last_file(manifest)
                if current_file and current_file != last_file:
                    last_file = current_file
                    if file_completed_callback:
                        file_completed_callback(current_file)
                stage = _manifest_stage(manifest)
                if stage and stage != last_stage and stage_callback:
                    last_stage = stage
                    stage_callback(stage)
                time.sleep(0.2)

        return_code = proc.returncode if proc is not None else 1
        manifest = _read_json(manifest_path)
        progress = _manifest_progress(manifest)
        if progress is not None and progress != last_progress and progress_callback:
            progress_callback(progress)

        success = return_code == 0 and bool((manifest or {}).get("success", False))
        if success:
            return WorkerExportResult(True, True, False, "", manifest_path)

        error = str((manifest or {}).get("error") or f"独立导出进程失败，退出码: {return_code}")
        return WorkerExportResult(True, False, False, error, manifest_path)
    except Exception as exc:
        try:
            if proc is not None and proc.poll() is None:
                proc.terminate()
        except Exception:
            pass
        return WorkerExportResult(True, False, False, f"独立导出进程异常: {exc}", manifest_path)


def _write_document_snapshot(document, snapshot_path: str) -> None:
    from app.models.document_serializer import DocumentSerializer

    data = DocumentSerializer.prepare_document_data(document)
    data["version"] = max(5, int(data.get("version", 5) or 5))
    settings = dict(data.get("export_settings", {}) or {})
    settings["export_external_worker_enabled"] = False
    settings.setdefault("export_backend", "auto")
    data["export_settings"] = settings
    with open(snapshot_path, "wb") as f:
        pickle.dump(data, f)


def _worker_command(request_path: str):
    if getattr(sys, "frozen", False):
        return [sys.executable, "--export-worker", request_path]
    return [sys.executable, str(_project_root() / "main.py"), "--export-worker", request_path]


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_path(directory: str, filename_template: str, file_format: str, start_index: int) -> str:
    key = f"{os.path.abspath(directory)}|{filename_template}|{file_format}|{int(start_index)}"
    digest = hashlib.sha1(key.encode("utf-8", "ignore")).hexdigest()[:12]
    return str(Path(directory) / f".btpw_export_manifest_{digest}.json")


def _atomic_write_json(path: str, payload: dict) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp = target.with_suffix(target.suffix + ".tmp")
    with open(temp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    os.replace(temp, target)


def _read_json(path: str) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            payload = json.load(f)
            return payload if isinstance(payload, dict) else {}
    except Exception:
        return {}


def _manifest_progress(manifest: dict) -> Optional[int]:
    try:
        progress = manifest.get("progress", {}) if isinstance(manifest, dict) else {}
        if isinstance(progress, dict):
            return int(progress.get("current", 0) or 0)
    except Exception:
        pass
    return None


def _manifest_last_file(manifest: dict) -> str:
    try:
        progress = manifest.get("progress", {}) if isinstance(manifest, dict) else {}
        if isinstance(progress, dict):
            return str(progress.get("last_file", "") or "")
    except Exception:
        pass
    return ""


def _manifest_stage(manifest: dict) -> str:
    try:
        progress = manifest.get("progress", {}) if isinstance(manifest, dict) else {}
        if isinstance(progress, dict):
            return str(progress.get("stage", "") or "")
    except Exception:
        pass
    return ""


def _touch(path: str) -> None:
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text("cancel", encoding="utf-8")
    except Exception:
        pass
