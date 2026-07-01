import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.utils.crash_session import (
    begin_crash_session,
    build_crash_notice,
    mark_clean_exit,
)


class CrashSessionStateTests(unittest.TestCase):
    def _write_state(self, directory, **overrides):
        state = {
            "version": 1,
            "session_id": "old-session",
            "status": "running",
            "started_at": "2026-07-01T10:00:00",
            "crash_log_path": "",
            "app_log_path": "",
            "notice_consumed": False,
        }
        state.update(overrides)
        Path(directory, "last_run_state.json").write_text(
            json.dumps(state, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_running_session_returns_notice_once(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write_state(directory)

            session_id, notice = begin_crash_session(
                log_dir=directory,
                session_id="new-session",
                started_at="2026-07-01T11:00:00",
            )

            self.assertEqual(session_id, "new-session")
            self.assertIsNotNone(notice)
            state = json.loads(Path(directory, "last_run_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["session_id"], "new-session")
            self.assertEqual(state["status"], "running")

            self.assertTrue(mark_clean_exit(session_id, log_dir=directory))
            _, second_notice = begin_crash_session(
                log_dir=directory,
                session_id="next-session",
                started_at="2026-07-01T12:00:00",
            )
            self.assertIsNone(second_notice)

    def test_clean_exit_does_not_return_notice(self):
        with tempfile.TemporaryDirectory() as directory:
            self._write_state(directory, status="clean_exit")

            _, notice = begin_crash_session(log_dir=directory, session_id="new-session")

            self.assertIsNone(notice)

    def test_mismatched_session_cannot_mark_current_run_clean(self):
        with tempfile.TemporaryDirectory() as directory:
            begin_crash_session(log_dir=directory, session_id="current-session")

            self.assertFalse(mark_clean_exit("other-session", log_dir=directory))
            state = json.loads(Path(directory, "last_run_state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["status"], "running")


class CrashReasonTests(unittest.TestCase):
    def test_access_violation_has_chinese_reason_and_business_location(self):
        with tempfile.TemporaryDirectory() as directory:
            crash_log = Path(directory, "crash.log")
            crash_log.write_text(
                "Windows fatal exception: access violation\n\n"
                "Thread 0x02 (most recent call first):\n"
                '  File "app\\utils\\rgba_resampler.py", line 75 in resize\n\n'
                "Current thread 0x01 (most recent call first):\n"
                '  File "app\\ui\\layer_panel.py", line 201 in __init__\n',
                encoding="utf-8",
            )

            notice = build_crash_notice(
                {
                    "started_at": "2026-07-01T09:46:25",
                    "crash_log_path": str(crash_log),
                    "app_log_path": "",
                }
            )

            self.assertIn("访问了无效内存", notice.message)
            self.assertIn("app/ui/layer_panel.py:201", notice.message)
            self.assertIn(str(crash_log), notice.details)

    def test_memory_error_has_chinese_reason(self):
        with tempfile.TemporaryDirectory() as directory:
            app_log = Path(directory, "app.log")
            app_log.write_text(
                "Traceback (most recent call last):\n"
                '  File "app\\utils\\fast_renderer.py", line 500, in render_preview\n'
                "MemoryError: Unable to allocate image buffer\n",
                encoding="utf-8",
            )

            notice = build_crash_notice(
                {
                    "started_at": "2026-07-01T09:46:25",
                    "crash_log_path": "",
                    "app_log_path": str(app_log),
                }
            )

            self.assertIn("内存不够", notice.message)
            self.assertIn("MemoryError", notice.details)

    def test_missing_logs_explain_force_close_or_power_loss(self):
        notice = build_crash_notice(
            {
                "started_at": "2026-07-01T09:46:25",
                "crash_log_path": "missing-crash.log",
                "app_log_path": "missing-app.log",
            }
        )

        self.assertIn("强制结束", notice.message)
        self.assertIn("断电", notice.message)
        self.assertIn("系统资源不足", notice.message)


class MainCrashNoticeIntegrationTests(unittest.TestCase):
    def test_export_worker_exits_before_main_session_starts(self):
        source = Path(__file__).resolve().parents[1].joinpath("main.py").read_text(encoding="utf-8")

        self.assertLess(
            source.index("sys.exit(export_worker_main"),
            source.index("begin_crash_session("),
        )

    def test_notice_dialog_uses_chinese_title_and_details(self):
        import main as app_main

        dialog = Mock()
        fake_message_box = Mock(return_value=dialog)
        fake_message_box.Warning = 2
        fake_message_box.AcceptRole = 0
        notice = SimpleNamespace(message="口语说明", details="具体原因")

        with patch.object(app_main, "QMessageBox", fake_message_box):
            app_main.show_previous_crash_notice(None, notice)

        dialog.setWindowTitle.assert_called_once_with("检测到上次异常退出")
        dialog.setText.assert_called_once_with("口语说明")
        dialog.setDetailedText.assert_called_once_with("具体原因")
        dialog.addButton.assert_called_once_with("知道了", 0)
        dialog.exec.assert_called_once()

    def test_controlled_exit_marks_current_session_clean(self):
        import main as app_main

        logger = Mock()
        with patch.object(app_main, "mark_clean_exit", return_value=True) as mark:
            result = app_main.finish_crash_session("session-1", 7, logger)

        self.assertEqual(result, 7)
        mark.assert_called_once_with("session-1")

    def test_logger_file_path_returns_file_handler_target(self):
        import logging
        import main as app_main

        handler = logging.FileHandler(os.devnull)
        try:
            logger = SimpleNamespace(handlers=[logging.StreamHandler(), handler])
            self.assertEqual(app_main.logger_file_path(logger), handler.baseFilename)
        finally:
            handler.close()


if __name__ == "__main__":
    unittest.main()
