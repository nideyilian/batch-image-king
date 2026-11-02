"""日志文件策略回归（2026-11-02）。

锁定两条曾出过问题的行为：

1. **不再每次启动新建文件**：早期 ``Logger.init`` 用 ``app_{timestamp}.log``，
   实测一台机器累积 1627 个文件 / 12MB，且没有任何轮转。
   现在必须是固定 ``app.log`` + ``RotatingFileHandler``。
2. **历史遗留文件会被清理，但保守**：只删「超出最近 N 个」且「超过 30 天」的文件，
   避免误删仍在排查用的日志，也不能碰现行的 ``app.log`` / ``app.log.1``。
"""

from __future__ import annotations

import glob
import logging
import os
import time

import pytest

from app.utils.logger import (
    LEGACY_LOG_GLOB,
    LEGACY_LOG_MAX_AGE_DAYS,
    LOG_BACKUP_COUNT,
    LOG_FILENAME,
    LOG_MAX_BYTES,
    Logger,
    prune_legacy_log_files,
)


@pytest.fixture
def fresh_logger(tmp_path):
    """让 Logger 单例回到未初始化状态，并隔离到临时目录。"""
    Logger._initialized = False
    Logger._logger = None
    yield tmp_path
    # 收尾：把 handler 关掉，避免临时目录被删时 handler 仍持有句柄
    if Logger._logger is not None:
        for handler in list(Logger._logger.handlers):
            handler.close()
            Logger._logger.removeHandler(handler)
    Logger._initialized = False
    Logger._logger = None


@pytest.mark.unit
def test_log_file_name_is_stable_across_initializations(fresh_logger):
    """同一目录连续初始化两次，日志文件名必须一致（证明不再带时间戳）。"""
    Logger.init(log_dir=str(fresh_logger), console_output=False, logger_name="批图王")
    first = sorted(os.path.basename(p) for p in glob.glob(str(fresh_logger / "*.log")))
    assert first == [LOG_FILENAME], f"首次启动应只产出 {LOG_FILENAME}，实际 {first}"

    # 模拟下次启动
    Logger._initialized = False
    Logger.init(log_dir=str(fresh_logger), console_output=False, logger_name="批图王")
    second = sorted(os.path.basename(p) for p in glob.glob(str(fresh_logger / "*.log")))
    assert second == [LOG_FILENAME], f"二次启动不应新建文件，实际 {second}"


@pytest.mark.unit
def test_rotating_handler_is_configured(fresh_logger):
    """必须使用 RotatingFileHandler 且带上限，否则长期使用会无限增长。"""
    Logger.init(log_dir=str(fresh_logger), console_output=False, logger_name="批图王")
    handler = Logger.get_logger().handlers[0]

    assert isinstance(handler, logging.handlers.RotatingFileHandler)
    assert handler.maxBytes == LOG_MAX_BYTES
    assert handler.backupCount == LOG_BACKUP_COUNT
    assert LOG_MAX_BYTES > 0 and LOG_BACKUP_COUNT > 0


@pytest.mark.unit
def test_log_rotates_and_bounded(fresh_logger):
    """写超上限后必须轮转，且产物数量不超过 backupCount + 1。"""
    Logger.init(
        log_dir=str(fresh_logger),
        console_output=False,
        logger_name="批图王",
        max_bytes=2048,
        backup_count=2,
    )
    log = Logger.get_logger()
    for i in range(400):
        log.info("轮转测试行 %04d %s", i, "y" * 60)
    for handler in log.handlers:
        handler.flush()

    produced = sorted(os.path.basename(p) for p in glob.glob(str(fresh_logger / "app.log*")))
    assert "app.log.1" in produced, f"应发生轮转，实际产物 {produced}"
    # backupCount=2 → 最多 app.log + .1 + .2
    assert len(produced) <= 3, f"轮转产物超出上限: {produced}"


@pytest.mark.unit
def test_prune_keeps_recent_and_current_files(fresh_logger):
    """清理只删「旧 + 超量」的历史文件，现行 app.log 与近期日志必须保留。"""
    old_ts = time.time() - (LEGACY_LOG_MAX_AGE_DAYS + 10) * 86400

    # 5 个 40 天前的时间戳日志
    legacy_old = []
    for i in range(5):
        path = fresh_logger / f"app_2025{i + 1:02d}01_120000.log"
        path.write_text("old", encoding="utf-8")
        os.utime(path, (old_ts, old_ts))
        legacy_old.append(path)

    # 2 个近期时间戳日志
    legacy_new = []
    for i in range(2):
        path = fresh_logger / f"app_2026110{i + 1}_090000.log"
        path.write_text("new", encoding="utf-8")
        legacy_new.append(path)

    # 现行文件：必须完全不受影响
    current = fresh_logger / LOG_FILENAME
    current.write_text("current", encoding="utf-8")
    rotated = fresh_logger / f"{LOG_FILENAME}.1"
    rotated.write_text("rotated", encoding="utf-8")

    removed = prune_legacy_log_files(str(fresh_logger), keep=2, max_age_days=LEGACY_LOG_MAX_AGE_DAYS)

    assert removed == 5, f"应删除 5 个过期历史日志，实际 {removed}"
    assert current.exists(), "现行 app.log 不得被删"
    assert rotated.exists(), "轮转副本 app.log.1 不得被删"
    for path in legacy_new:
        assert path.exists(), f"近期日志不得被删: {path.name}"
    for path in legacy_old:
        assert not path.exists(), f"过期日志应被删: {path.name}"


@pytest.mark.unit
def test_prune_never_touches_current_log_when_matching_glob(fresh_logger):
    """即使现行文件名命中 legacy glob，也必须跳过（防御性断言）。"""
    current = fresh_logger / LOG_FILENAME
    current.write_text("keep-me", encoding="utf-8")
    os.utime(current, (time.time() - 400 * 86400,) * 2)

    prune_legacy_log_files(str(fresh_logger), keep=0, max_age_days=1)
    assert current.exists(), "app.log 被误删 —— 清理逻辑必须排除现行文件"


@pytest.mark.unit
def test_prune_is_noop_on_empty_dir(fresh_logger):
    """空目录不应抛异常（启动路径必须绝对稳）。"""
    assert prune_legacy_log_files(str(fresh_logger)) == 0


@pytest.mark.unit
def test_legacy_glob_does_not_match_current_log():
    """glob 模式本身不能匹配现行 app.log，否则清理逻辑的前提就不成立。"""
    import fnmatch

    assert not fnmatch.fnmatch(LOG_FILENAME, LEGACY_LOG_GLOB)
    assert fnmatch.fnmatch("app_20261102_101530.log", LEGACY_LOG_GLOB)
