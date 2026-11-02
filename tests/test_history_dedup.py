"""历史栈：同一状态不应重复入栈。

背景：12 个图层操作函数都成对保存快照（``xxx前`` + ``xxx``），
而「xxx前」记录的就是上一次操作后的状态 —— 与栈顶内容完全相同。
结果是每次图层操作吃掉 2 条历史，``max_history=20`` 时约 10 次操作
就把更早的编辑挤出撤销栈。

修法放在 ``DocumentHistory.save_state`` 里：与栈顶状态完全一致就跳过。
这样不需要改 12 处调用点，也不会破坏「首次操作仍需一条基线」
（``create_new`` 后栈为空，第一条照常入栈）。
"""

from __future__ import annotations

import pytest

from app.models.document import Document


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


def _history_len(document: Document) -> int:
    return len(document._history_manager._history)


def _new_document(width: int = 600, height: int = 600) -> Document:
    document = Document()
    document.create_new(width, height)
    return document


def test_duplicate_state_is_not_pushed_twice():
    """连续两次保存同一状态，只应占一条历史。"""
    document = _new_document()
    document.save_state("操作")
    first = _history_len(document)
    document.save_state("操作后再存一次")
    assert _history_len(document) == first, "相同状态不应再入栈"


def test_add_layer_costs_only_one_history_entry():
    """加一个图层只应占 1 条历史（旧实现占 2 条）。"""
    document = _new_document()
    document.add_layer("A", 0, 0, 100, 100, is_folder=False)
    after_first = _history_len(document)
    assert after_first <= 2, f"首个图层后历史 {after_first} 条（基线 1 + 操作 1 是上限）"

    document.add_layer("B", 10, 10, 100, 100, is_folder=False)
    after_second = _history_len(document)
    assert after_second - after_first == 1, (
        f"第二个图层应只增加 1 条，实际增加 {after_second - after_first} 条"
    )


def test_many_layer_operations_fit_in_history():
    """12 次图层操作应能全部放进 20 条历史（旧实现需要 24 条，会被挤掉）。"""
    document = _new_document()
    for i in range(12):
        document.add_layer(f"L{i}", i * 5, i * 5, 100, 100, is_folder=False)

    used = _history_len(document)
    limit = document._history_manager._max_history
    assert used <= limit, f"12 次操作用了 {used} 条，超过上限 {limit}"
    # 上限 20 时，12 次操作（+1 基线）应只占 13 条
    assert used == 13, f"预期 13 条（基线 1 + 操作 12），实际 {used}"


def test_undo_still_restores_previous_state():
    """去重不能破坏撤销：一次撤销退一步。"""
    document = _new_document()
    document.add_layer("A", 0, 0, 100, 100, is_folder=False)
    assert len(document.layers) == 1

    document.add_layer("B", 50, 50, 100, 100, is_folder=False)
    assert len(document.layers) == 2

    document.undo()
    assert len(document.layers) == 1, "撤销一次应退回一个图层"

    document.undo()
    assert len(document.layers) == 0, "再撤销一次应退回空文档"


def test_redo_still_works_after_dedup():
    """去重不能破坏重做。"""
    document = _new_document()
    document.add_layer("A", 0, 0, 100, 100, is_folder=False)
    document.add_layer("B", 50, 50, 100, 100, is_folder=False)
    document.undo()
    assert len(document.layers) == 1

    document.redo()
    assert len(document.layers) == 2, "重做应恢复第二个图层"


def test_real_change_still_creates_new_entry():
    """内容确实变化时必须照常入栈，否则会丢历史。"""
    document = _new_document()
    document.add_layer("A", 0, 0, 100, 100, is_folder=False)
    baseline = _history_len(document)

    document.layers[0].x = 42
    document.save_state("移动图层")
    assert _history_len(document) == baseline + 1, "状态变化必须产生新历史"

    document.undo()
    assert document.layers[0].x == 0, "应能撤销回移动前"


def test_coalesce_still_works():
    """合并键逻辑不受去重影响（拖滑块仍然只留一条）。"""
    document = _new_document()
    document.add_layer("A", 0, 0, 100, 100, is_folder=False)
    baseline = _history_len(document)

    for i in range(10):
        document.layers[0].x = i + 1
        document.save_state("拖动", coalesce_key="layer0:x")

    merged = _history_len(document)
    assert merged - baseline == 1, f"连续同键保存应合并成 1 条，实际 {merged - baseline} 条"
