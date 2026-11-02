"""批量导出「文件名清洗 / 模板占位符 / 索引映射」行为测试（2026-11-02）。

覆盖 ``app/utils/batch_export_precomputer_v2.py`` 里可以脱离 Qt 实例验证的纯逻辑。
这一批是导出链路上**唯一直接影响落盘结果**的地方：名字错了，文件就写不出来，
或者写到意想不到的位置。

本文件同时锁住一个 2026-11-02 修掉的真实缺陷：
``_clean_filename`` 原先只处理"非法字符 / 控制字符 / 长度"，
对 **Windows 特有的非法形态**（``..``、``CON``/``NUL`` 等保留设备名、
结尾的点或空格）完全没管，而这些都能由用户自定义的文件名模板触发：

- ``..`` 原样返回 → 拼进输出目录后指向父目录
- ``CON`` / ``NUL`` / ``COM1`` 原样返回 → 写文件失败，或内容被写进控制台
- ``abc.`` 原样返回 → Windows 静默截断成 ``abc``，用户看到的文件名与预期不符
"""

from __future__ import annotations

import pytest

from app.utils.batch_export_precomputer_v2 import (
    BatchExportPrecomputerV2,
    generate_deterministic_hash,
)

# 只借用方法本体，不构造真实预计算器（它需要 document / QObject）。
_RESERVED = BatchExportPrecomputerV2._WINDOWS_RESERVED_NAMES
_clean = BatchExportPrecomputerV2._clean_filename
_extract_main = BatchExportPrecomputerV2._extract_main_filename


class _Host:
    """``_clean_filename`` 只用到 self.degradations.note，这里给个静默实现。"""

    _clean_filename = _clean
    _extract_main_filename = _extract_main
    _WINDOWS_RESERVED_NAMES = _RESERVED

    def __init__(self):
        self.notes: list[tuple] = []
        notes = self.notes

        class _Degradations:
            @staticmethod
            def note(reason, detail=None):
                notes.append((reason, detail))

        self.degradations = _Degradations()


def clean(name: str) -> str:
    return _Host()._clean_filename(name)


def extract_main(name: str) -> str:
    return _Host()._extract_main_filename(name)


# ---------------------------------------------------------------------------
# Windows 非法形态（本次修复重点）
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_dot_only_names_are_replaced():
    """``.`` / ``..`` / ``...`` 在路径里分别指当前目录与父目录，绝不能当文件名。"""
    for name in (".", "..", "...", "...."):
        assert clean(name) == "export", name


@pytest.mark.unit
@pytest.mark.parametrize(
    "name",
    ["CON", "PRN", "AUX", "NUL", "COM1", "COM9", "LPT1", "LPT9",
     "con", "nul", "aux"],
)
def test_windows_reserved_device_names_are_rewritten(name):
    """保留设备名必须改写，大小写不敏感。"""
    out = clean(name)
    assert out.split(".")[0].upper() not in _RESERVED
    assert out.startswith(name)


@pytest.mark.unit
@pytest.mark.parametrize("name,expected", [
    ("con.txt", "con-file.txt"),
    ("NUL.png", "NUL-file.png"),
    ("COM1.jpeg", "COM1-file.jpeg"),
])
def test_reserved_name_suffix_goes_before_extension(name, expected):
    """后缀必须加在**主体名**后面。

    如果只是简单地在末尾拼 ``_file``，``con.txt`` 会变成 ``con.txt_file``，
    主体仍是 ``con``，Windows 依旧拒绝创建。
    """
    assert clean(name) == expected


@pytest.mark.unit
def test_trailing_dot_and_space_are_stripped():
    """Windows 不允许文件名以点或空格结尾（会静默截断）。"""
    assert clean("abc.") == "abc"
    assert clean("abc ") == "abc"
    assert clean("abc. . ") == "abc"
    assert clean("abc.-") == "abc"
    assert clean("  .  ") == "export"


@pytest.mark.unit
def test_output_never_ends_with_dot_or_space_for_any_illegal_input():
    """对一批刁钻输入做统一断言：结果必须可被 Windows 创建。"""
    for name in (".", "..", "...", "CON", "NUL", "a.", "a ", "", "   ",
                 "....", "con.", "..a..", "  .  "):
        out = clean(name)
        assert out, f"{name!r} 输出为空"
        assert not set(out) <= {"."}, f"{name!r} 输出仅含点号: {out!r}"
        assert not out.endswith("."), f"{name!r} 输出以点结尾: {out!r}"
        assert not out.endswith(" "), f"{name!r} 输出以空格结尾: {out!r}"
        assert out.split(".")[0].upper() not in _RESERVED, f"{name!r} 命中保留名: {out!r}"


# ---------------------------------------------------------------------------
# 常规清洗
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_illegal_characters_are_replaced():
    """Windows 九个非法字符全部替换，一个不漏。"""
    for char in '<>:"/\\|?*':
        out = clean(f"a{char}b")
        assert char not in out, (char, out)


@pytest.mark.unit
def test_path_separators_are_flattened_so_no_directory_escape():
    """``/`` 与 ``\\`` 被替换后，结果不可能再带出目录层级。"""
    for name in ("../../etc/passwd", "a/../../b", "C:\\Windows\\x", "..\\..\\x"):
        out = clean(name)
        assert "/" not in out and "\\" not in out, (name, out)


@pytest.mark.unit
def test_control_characters_are_removed():
    # 控制字符被删掉后两侧字符直接相邻（历史行为，不为它做额外分隔）
    assert clean("a\x00b\nc\td") == "abcd"


@pytest.mark.unit
def test_fullwidth_characters_are_normalized():
    """NFKC 会把全角冒号/斜杠转半角，随后按非法字符处理。"""
    out = clean("标题：副标题")
    assert "：" not in out


@pytest.mark.unit
def test_chinese_is_preserved():
    """中文必须保留 —— 用户模板大量使用中文。"""
    assert clean("限量腕表") == "限量腕表"
    assert clean("限量腕表.png") == "限量腕表.png"


@pytest.mark.unit
def test_empty_input_falls_back_to_export():
    for name in ("", "   ", "---", "___"):
        assert clean(name) == "export", name


@pytest.mark.unit
def test_length_is_capped_at_100():
    out = clean("a" * 300)
    assert len(out) <= 100


@pytest.mark.unit
def test_truncation_does_not_leave_trailing_dot():
    """截断后若最后一位是点，仍然不合规，要再修一次。"""
    out = clean("a" * 99 + ".")
    assert not out.endswith(".")


@pytest.mark.unit
def test_non_string_input_is_coerced():
    assert clean(123) == "123"
    assert clean(None) == "None"


@pytest.mark.unit
def test_degradation_is_recorded_when_name_is_rewritten():
    """改写必须留痕 —— 否则用户看到文件名变了却不知道为什么。"""
    host = _Host()
    host._clean_filename("..")
    assert any("点号" in reason for reason, _ in host.notes), host.notes

    host2 = _Host()
    host2._clean_filename("CON")
    assert any("保留设备名" in reason for reason, _ in host2.notes), host2.notes


@pytest.mark.unit
def test_clean_filename_is_idempotent():
    """洗过的名字再洗一次不应再变化（否则模板替换会反复改写）。"""
    for name in ("限量腕表", "a<b>.png", "CON", "abc.", "..", "", "x" * 200, "abc. . "):
        once = clean(name)
        twice = clean(once)
        assert once == twice, f"{name!r}: {once!r} -> {twice!r}"


# ---------------------------------------------------------------------------
# 主文件名提取（去序号后缀）
# ---------------------------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("raw,expected", [
    ("image_001", "image"),
    ("photo (1)", "photo"),
    ("pic-02", "pic"),
    ("a[3]", "a"),
    ("name", "name"),
])
def test_extract_main_filename_strips_sequence_suffix(raw, expected):
    """同一素材的多个副本（``photo (1)``、``image_001``）要归到同一个主名。"""
    assert extract_main(raw) == expected


@pytest.mark.unit
def test_extract_main_filename_keeps_original_when_stripping_empties_it():
    """全是数字的名字不能被剥成空串。"""
    for raw in ("001", "1", "(1)"):
        out = extract_main(raw)
        assert out, raw


@pytest.mark.unit
def test_extract_main_filename_handles_empty():
    assert extract_main("") == ""


# ---------------------------------------------------------------------------
# 确定性哈希
# ---------------------------------------------------------------------------

@pytest.mark.unit
def test_hash_is_order_independent():
    """图层状态是 dict，遍历顺序可能不同，但同一组合必须得到同一哈希。"""
    a = generate_deterministic_hash({0: "a.png", 1: "b.png", 2: "c.png"})
    b = generate_deterministic_hash({2: "c.png", 0: "a.png", 1: "b.png"})
    assert a == b


@pytest.mark.unit
def test_hash_differs_when_any_layer_file_changes():
    base = generate_deterministic_hash({0: "a.png", 1: "b.png"})
    assert base != generate_deterministic_hash({0: "a.png", 1: "c.png"})
    assert base != generate_deterministic_hash({0: "x.png", 1: "b.png"})


@pytest.mark.unit
def test_hash_differs_when_layer_mapping_shifts():
    """同一批文件换到不同图层上必须算不同组合（否则去重会误杀）。"""
    a = generate_deterministic_hash({0: "a.png", 1: "b.png"})
    b = generate_deterministic_hash({0: "b.png", 1: "a.png"})
    assert a != b


@pytest.mark.unit
def test_hash_is_deterministic_across_calls():
    """纯函数，不许掺时间/随机因子（否则跨进程去重失效）。"""
    values = {0: "a.png", 1: "b.png"}
    assert len({generate_deterministic_hash(values) for _ in range(20)}) == 1


@pytest.mark.unit
def test_hash_handles_empty_state():
    out = generate_deterministic_hash({})
    assert isinstance(out, str) and out
