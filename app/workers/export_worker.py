# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import sys
import time
import traceback
from pathlib import Path
from threading import Lock
from typing import Optional


def _replace_with_retry(
    source: Path,
    target: Path,
    *,
    max_attempts: int = 8,
    delay_seconds: float = 0.05,
) -> None:
    attempts = max(1, int(max_attempts))
    for attempt in range(attempts):
        try:
            os.replace(source, target)
            return
        except PermissionError:
            if attempt + 1 >= attempts:
                raise
            time.sleep(max(0.0, float(delay_seconds)))


class ManifestWriter:
    def __init__(self, path: str, request: dict):
        self.path = path
        self.request = dict(request)
        self.lock = Lock()
        self.last_write_error = ""
        self.payload = {
            "version": 1,
            "status": "starting",
            "success": False,
            "error": "",
            "started_at": time.time(),
            "updated_at": time.time(),
            "request": {
                "directory": request.get("directory"),
                "count": int(request.get("count", 0) or 0),
                "filename_template": request.get("filename_template"),
                "file_format": request.get("file_format"),
                "start_index": int(request.get("start_index", 1) or 1),
                "traverse_mode": bool(request.get("traverse_mode", False)),
                "avoid_duplicates": bool(request.get("avoid_duplicates", True)),
            },
            "progress": {
                "current": 0,
                "total": int(request.get("count", 0) or 0),
                "stage": "starting",
                "last_file": "",
            },
            "completed_files": [],
            "worker_pid": os.getpid(),
        }

    def load_resume_state(self) -> int:
        if not bool(self.request.get("resume", True)):
            return 0
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                existing = json.load(f)
            if not isinstance(existing, dict):
                return 0
            if not _same_request(existing.get("request", {}), self.payload.get("request", {})):
                return 0
            completed_files = [
                str(item)
                for item in (existing.get("completed_files", []) or [])
                if item and os.path.exists(str(item))
            ]
            completed = len(completed_files)
            if completed <= 0:
                return 0
            self.payload["completed_files"] = completed_files
            self.payload["resume_from"] = completed
            self.payload["progress"]["current"] = completed
            return completed
        except Exception:
            return 0

    def update(self, *, status: Optional[str] = None, stage: Optional[str] = None, current: Optional[int] = None,
               total: Optional[int] = None, last_file: Optional[str] = None, error: Optional[str] = None) -> None:
        with self.lock:
            if status is not None:
                self.payload["status"] = str(status)
            if error is not None:
                self.payload["error"] = str(error)
            progress = self.payload.setdefault("progress", {})
            if stage is not None:
                progress["stage"] = str(stage)
            if current is not None:
                progress["current"] = max(0, int(current))
            if total is not None:
                progress["total"] = max(0, int(total))
            if last_file is not None:
                progress["last_file"] = str(last_file)
            self.payload["updated_at"] = time.time()
            self._write_locked()

    def add_completed_file(self, file_path: str) -> None:
        with self.lock:
            completed = self.payload.setdefault("completed_files", [])
            if file_path and file_path not in completed:
                completed.append(file_path)
            progress = self.payload.setdefault("progress", {})
            progress["last_file"] = file_path
            self.payload["updated_at"] = time.time()
            self._write_locked()

    def finish(self, success: bool, error: str = "", report: Optional[dict] = None) -> None:
        with self.lock:
            self.payload["status"] = "completed" if success else "failed"
            self.payload["success"] = bool(success)
            self.payload["error"] = str(error or "")
            self.payload["finished_at"] = time.time()
            self.payload["updated_at"] = time.time()
            if report:
                self.payload["export_report"] = _json_safe(report)
            self._write_locked()

    def _write_locked(self) -> bool:
        try:
            target = Path(self.path)
            target.parent.mkdir(parents=True, exist_ok=True)
            temp = target.with_suffix(target.suffix + ".tmp")
            with open(temp, "w", encoding="utf-8") as f:
                json.dump(self.payload, f, ensure_ascii=False, indent=2, default=str)
            _replace_with_retry(temp, target)
            self.last_write_error = ""
            return True
        except Exception as exc:
            self.last_write_error = str(exc)
            print(f"manifest write failed, export continues: {exc}", file=sys.stderr)
            return False


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        print("missing request path", file=sys.stderr)
        return 2
    request_path = argv[0]
    try:
        with open(request_path, "r", encoding="utf-8") as f:
            request = json.load(f)
    except Exception as exc:
        print(f"failed to read request: {exc}", file=sys.stderr)
        return 2

    manifest = ManifestWriter(str(request.get("manifest_path") or ""), request)
    try:
        requested_count = int(request.get("count", 0) or 0)
        resume_completed = manifest.load_resume_state()
        manifest.update(status="loading", stage="加载文档快照")
        document = _load_document(str(request.get("document_snapshot") or ""))
        settings = getattr(document, "export_settings", {}) or {}
        settings["export_external_worker_enabled"] = False
        settings.setdefault("export_backend", "auto")
        document.export_settings = settings

        remaining_count = max(0, requested_count - resume_completed)
        start_index = int(request.get("start_index", 1) or 1) + resume_completed

        manifest.update(
            status="running",
            stage="准备导出",
            current=resume_completed,
            total=requested_count,
        )
        if remaining_count <= 0:
            manifest.finish(True, report={"summary": {"requested_count": requested_count, "exported_count": resume_completed}})
            return 0

        document_analysis = document._analyze_document_for_export()

        # 仅用于测试的故障注入:子进程主动抛错,验证主进程失败时保留临时文件。
        # 默认未启用,生产用户不会触发;测试可设 BTPW_EXPORT_WORKER_TEST_FAIL=1。
        if os.environ.get("BTPW_EXPORT_WORKER_TEST_FAIL", "0") == "1":
            raise RuntimeError("test_injected_failure: BTPW_EXPORT_WORKER_TEST_FAIL=1")

        from app.utils.optimized_batch_executor import export_batch_with_precomputation_v2

        def is_canceled() -> bool:
            cancel_path = str(request.get("cancel_path") or "")
            return bool(cancel_path and os.path.exists(cancel_path))

        def progress_callback(current_count: int) -> None:
            manifest.update(current=resume_completed + int(current_count or 0), total=requested_count)

        def file_completed_callback(message: str) -> None:
            file_path = _resolve_completed_file(str(message or ""), str(request.get("directory") or ""))
            manifest.add_completed_file(file_path)

        def stage_callback(stage_name: str) -> None:
            manifest.update(stage=str(stage_name or ""))

        success = export_batch_with_precomputation_v2(
            document=document,
            document_analysis=document_analysis,
            directory=str(request.get("directory") or ""),
            count=remaining_count,
            filename_template=str(request.get("filename_template") or "image_{number:04d}"),
            file_format=str(request.get("file_format") or "png"),
            start_index=start_index,
            progress_callback=progress_callback,
            file_completed_callback=file_completed_callback,
            stage_callback=stage_callback,
            cancel_callback=is_canceled,
            traverse_mode=bool(request.get("traverse_mode", False)),
            avoid_duplicates=bool(request.get("avoid_duplicates", True)),
        )
        report = getattr(document, "_last_export_report", None)
        error = "" if success else str(getattr(document, "_last_export_error", "") or "导出失败")
        manifest.finish(bool(success), error=error, report=report if isinstance(report, dict) else None)
        return 0 if success else 1
    except Exception as exc:
        tb = traceback.format_exc()
        manifest.finish(False, error=f"{exc}\n{tb}")
        print(tb, file=sys.stderr)
        return 1


def _load_document(snapshot_path: str):
    from app.models.document import Document
    from app.models.document_serializer import DocumentSerializer

    serializer = DocumentSerializer()
    document_data = serializer.deserialize_document(snapshot_path)
    if not document_data:
        raise RuntimeError(f"无法加载文档快照: {snapshot_path}")
    document = Document()
    if not DocumentSerializer.restore_document_data(document, document_data):
        raise RuntimeError(f"无法恢复文档快照: {snapshot_path}")
    document.current_file_path = snapshot_path
    return document


def _same_request(old_request: dict, new_request: dict) -> bool:
    keys = ("directory", "filename_template", "file_format", "start_index", "traverse_mode", "avoid_duplicates")
    return all(str(old_request.get(key)) == str(new_request.get(key)) for key in keys)


def _resolve_completed_file(message: str, directory: str) -> str:
    value = message.strip()
    if value.startswith(":"):
        value = value[1:].strip()
    if not value:
        return ""
    if os.path.isabs(value):
        return value
    return os.path.abspath(os.path.join(directory, value))


def _json_safe(payload: dict) -> dict:
    try:
        return json.loads(json.dumps(payload, ensure_ascii=False, default=str))
    except Exception:
        return {}


if __name__ == "__main__":
    raise SystemExit(main())
