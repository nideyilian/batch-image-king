"""崩溃恢复提示的触发条件。

背景：程序被强制结束（任务管理器 / 脚本 kill / 关机）时，状态文件会停留在
"running"，下次启动就被误判成「上次异常退出」并弹窗。用户实际什么都没遇到，
弹窗只会制造焦虑——杰哥就因为我在调试时反复 kill 进程，连续看到这个假提示。

策略：上个会话存活时间够久（>= 90s）后消失，按"被强制结束"静默处理；
只有短命退出（可能真的刚启动就挂）才提示。
"""

import json
from datetime import datetime, timedelta

import pytest

from app.utils.crash_session import begin_crash_session


def _write_state(tmp_path, started_at: datetime, status="running", consumed=False):
    state = {
        "version": 1,
        "session_id": "old-session",
        "status": status,
        "started_at": started_at.isoformat(timespec="seconds"),
        "crash_log_path": "",
        "app_log_path": "",
        "notice_consumed": consumed,
    }
    (tmp_path / "last_run_state.json").write_text(
        json.dumps(state, ensure_ascii=False), encoding="utf-8"
    )


@pytest.mark.unit
def test_long_running_session_is_silent(tmp_path):
    """跑了两小时的会话被 kill —— 不该弹「异常退出」。"""
    _write_state(tmp_path, datetime.now() - timedelta(hours=2))
    _, notice = begin_crash_session(log_dir=tmp_path)
    assert notice is None


@pytest.mark.unit
def test_short_lived_session_still_warns(tmp_path):
    """刚启动 5 秒就没了的会话 —— 值得提示。"""
    _write_state(tmp_path, datetime.now() - timedelta(seconds=5))
    _, notice = begin_crash_session(log_dir=tmp_path)
    assert notice is not None


@pytest.mark.unit
def test_clean_exit_never_warns(tmp_path):
    """正常退出的上一会话不该提示。"""
    _write_state(tmp_path, datetime.now() - timedelta(seconds=3), status="clean")
    _, notice = begin_crash_session(log_dir=tmp_path)
    assert notice is None


@pytest.mark.unit
def test_consumed_notice_not_repeated(tmp_path):
    """已经提示过一次就不再重复打扰。"""
    _write_state(
        tmp_path, datetime.now() - timedelta(seconds=5), consumed=True
    )
    _, notice = begin_crash_session(log_dir=tmp_path)
    assert notice is None


@pytest.mark.unit
def test_future_timestamp_is_treated_as_suspicious(tmp_path):
    """时钟回拨导致 started_at 在未来 —— 保守地仍然提示。"""
    _write_state(tmp_path, datetime.now() + timedelta(hours=5))
    _, notice = begin_crash_session(log_dir=tmp_path)
    assert notice is not None


@pytest.mark.unit
def test_missing_started_at_is_treated_as_suspicious(tmp_path):
    """没有时间戳就无法判断，保守提示。"""
    (tmp_path / "last_run_state.json").write_text(
        json.dumps({"version": 1, "session_id": "x", "status": "running"}),
        encoding="utf-8",
    )
    _, notice = begin_crash_session(log_dir=tmp_path)
    assert notice is not None
