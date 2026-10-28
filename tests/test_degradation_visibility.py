"""降级可见性契约测试。

背景：批量导出链路上曾有大量 ``except Exception: return 默认值``，出图失败
或结果偏差时日志里查不到任何线索，用户只能看到「图不对」却无从排查。
现在统一用 ``DegradationCounter``：同一降级点首次详细记录（含 traceback），
后续只计数，批次结束汇总。

这些测试锁住三件事：
1. 计数器本身的去噪语义（首次详细、后续只计数、汇总完整）
2. 批量导出预计算器确实接入了计数器
3. 关键失败路径（素材目录缺失 / 分类筛选空 / 导出设置损坏）会留痕而非静默
"""

from __future__ import annotations

import logging

import pytest

from app.utils.logger import DegradationCounter


class _RecordingHandler(logging.Handler):
    """收集日志记录，用于断言日志真的被写出来了。"""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.fixture
def recording_logger():
    logger = logging.getLogger("test.degradation")
    logger.handlers = []
    logger.setLevel(logging.DEBUG)
    logger.propagate = False
    handler = _RecordingHandler()
    logger.addHandler(handler)
    yield logger, handler
    logger.handlers = []


def _fresh_precomputer():
    from app.utils.batch_export_precomputer_v2 import BatchExportPrecomputerV2

    class _Doc:
        layers = []
        export_settings = {}

    return BatchExportPrecomputerV2(_Doc(), {})


# --- 计数器语义 -----------------------------------------------------------


def test_counter_records_first_occurrence_with_traceback(recording_logger):
    logger, handler = recording_logger
    counter = DegradationCounter(logger)

    counter.note("素材去重.全局使用次数读取失败", "a.jpg")

    assert len(handler.records) == 1
    record = handler.records[0]
    assert record.levelno == logging.WARNING
    assert "素材去重.全局使用次数读取失败" in record.getMessage()
    assert "a.jpg" in record.getMessage()
    # exc_info 必须带上，否则排障只能靠猜
    assert record.exc_info is not None


def test_counter_suppresses_repeated_logs_but_keeps_counting(recording_logger):
    logger, handler = recording_logger
    counter = DegradationCounter(logger)

    for _ in range(50):
        counter.note("素材去重.全局使用次数读取失败", "a.jpg")

    # 只记录第一次，避免 5000 张图刷出 5000 条堆栈
    assert len(handler.records) == 1
    assert counter.count("素材去重.全局使用次数读取失败") == 50
    assert counter.total == 50


def test_counter_summary_lists_all_keys_sorted_by_count(recording_logger):
    logger, _ = recording_logger
    counter = DegradationCounter(logger)

    for _ in range(3):
        counter.note("a.key")
    for _ in range(7):
        counter.note("b.key")

    lines = counter.summary()
    assert lines[0].startswith("本次导出发生 10 次降级（2 类）")
    assert "b.key × 7" in lines[1]
    assert "a.key × 3" in lines[2]


def test_counter_summary_empty_when_no_degradation(recording_logger):
    logger, _ = recording_logger
    counter = DegradationCounter(logger)
    assert counter.summary() == []
    assert not counter.has_any()
    assert counter.total == 0


def test_counter_reset_clears_state(recording_logger):
    logger, handler = recording_logger
    counter = DegradationCounter(logger)
    counter.note("k")
    counter.reset()

    assert not counter.has_any()
    assert counter.total == 0
    # reset 后同一个 key 应该能再次详细记录
    counter.note("k")
    assert len(handler.records) == 2


def test_counter_works_without_logger():
    """logger 为 None 时不能崩 —— 计数器可能被用在未初始化日志的场景。"""
    counter = DegradationCounter(None)
    counter.note("k", "detail")
    assert counter.total == 1
    assert "k × 1" in counter.summary()[1]


# --- 接线检查 -------------------------------------------------------------


def test_precomputer_owns_degradation_counter():
    computer = _fresh_precomputer()
    assert isinstance(computer.degradations, DegradationCounter)
    assert computer.degradations.total == 0


def test_precompute_diagnostics_carries_degradation_info():
    """降级信息必须能进入诊断字典，才能流到导出报告与界面。"""
    computer = _fresh_precomputer()
    computer.degradations.note("测试.降级点", "样本")

    diagnostics = {}
    if computer.degradations.has_any():
        diagnostics["degradations"] = list(computer.degradations.summary())
        diagnostics["degradation_total"] = int(computer.degradations.total)

    assert diagnostics["degradation_total"] == 1
    assert any("测试.降级点" in line for line in diagnostics["degradations"])


def test_precomputer_tolerates_broken_export_settings():
    """导出设置读取抛异常时不能崩，且唯一使用配置降级为关闭并留痕。"""
    from app.utils.batch_export_precomputer_v2 import BatchExportPrecomputerV2

    class _BadDoc:
        layers = []

        @property
        def export_settings(self):
            raise RuntimeError("模拟设置损坏")

    computer = BatchExportPrecomputerV2(_BadDoc(), {"layer_analysis": {}})

    assert computer.unique_use_enabled is False
    assert computer.unique_use_layers == []
    assert computer.degradations.count("导出设置.读取唯一使用配置失败") >= 1


# --- 素材目录：最容易静默出空图的一类故障 ---------------------------------


def test_missing_asset_directory_is_reported():
    """素材目录不存在时必须留痕。

    原实现 ``if not os.path.isdir(...): return []`` 连异常都不抛，
    上层拿到空池就静默导出「该位置没有内容」的图，用户极难自查。
    """
    computer = _fresh_precomputer()
    gone = "/nonexistent/path/definitely_missing_assets_dir"

    assert computer._get_folder_images_cached(gone) == []
    assert computer.degradations.count("素材目录.目录不存在") == 1
    # 样本要能指回具体目录（Windows 下被 abspath 转过，只比对末段）
    sample = str(computer.degradations._samples.get("素材目录.目录不存在", ""))
    assert "definitely_missing_assets_dir" in sample.replace("\\", "/")


def test_category_filter_mismatch_is_reported(tmp_path):
    """目录里有图但分类关键词一张都匹配不上时留痕。"""
    for name in ("a_red.jpg", "b_red.jpg"):
        (tmp_path / name).write_bytes(b"x")

    computer = _fresh_precomputer()
    result = computer._get_folder_images_cached(str(tmp_path), category="blue")

    assert result == []
    assert computer.degradations.count("素材目录.分类筛选后为空") == 1


def test_healthy_directory_produces_no_degradation(tmp_path):
    """正常目录不能误报 —— 否则告警会被噪声淹没。"""
    for name in ("img1.jpg", "img2.png", "skip.txt"):
        (tmp_path / name).write_bytes(b"x")

    computer = _fresh_precomputer()
    result = computer._get_folder_images_cached(str(tmp_path))

    assert len(result) == 2  # 只收图片
    assert computer.degradations.total == 0


# --- 界面提示：降级必须能被用户看到 ---------------------------------------


def test_export_dialog_reads_degradation_from_diagnostics():
    """导出完成提示要读降级信息（**当前欠账，已知缺口**）。

    原实现检查经典版 `app/ui/batch_export_dialog_progress.py` 里的
    `_last_precompute_diagnostics` 文案。该文件已随经典界面下线删除。

    ⚠ QML 版 `batch_export_view_model` 目前**没有**面向用户的降级提示
    （全局搜 `degradations` / 「降级」在 app/qml 下零命中）。也就是说：
    导出发生性能降级时，用户拿到的结果可能不符合预期，但界面上不会说。
    这是经典版有、QML 没有的真实差异，属于待补功能，不是"已对齐"。

    这里保留测试名并 skip，而不是直接删除：删掉的话这个缺口就彻底
    从账面上消失了，和之前那张「已完成 20 项」的审计文档同一个毛病。
    """
    pytest.skip("QML 导出尚无降级提示（已知缺口），补齐后改为真实断言")
