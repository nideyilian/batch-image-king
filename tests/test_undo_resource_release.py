"""撤销/重做资源回收回归测试。

对应 2026-11-02 实机问题「操作多几下就卡死」。

根因：``Document._restore_state`` 每次撤销都用 ``deserialize_layer_tree(parent=self)``
重建全部图层，但旧图层从未从 Document 的 C++ 子对象树上摘下。
旧图层在 Python 侧已无人引用，C++ 侧却仍由 Document 持有，永远不析构。

实测（``docs/audit/_probe_undo_leak.py``，5 图层文档连续「改属性 + 撤销」）：
  - Layer 对象       5 → 100（20 轮）→ 200（40 轮）
  - doc.children()   4 → 104（20 轮）
  - 95 个孤儿图层的 parent() 仍是 Document

用户侧表现：每轮撤销常驻一份图层 + 图像缓存（单层可达数 MB），
几十轮后内存与子对象树同步膨胀，主线程遍历/信号分发越来越慢，最终卡死。

同时修掉：撤销恢复出来的图层没有接回 ``changed`` 信号（接收者数为 0），
导致「撤销之后再改该图层属性不触发重绘」，看起来像卡住。
"""
from __future__ import annotations

import gc

import pytest
from PIL import Image

from app.models.document import Document
from app.models.layer_new import Layer


def _document(layer_count: int = 4, canvas=(400, 300)) -> Document:
    document = Document()
    document.create_new(*canvas)
    for index in range(layer_count):
        document.add_layer(
            f"L{index}",
            10 + 5 * index,
            15,
            100,
            80,
            image_source=None,
            is_folder=False,
        )
    return document


def _drain(qapp, ms: int = 6) -> None:
    """让 deleteLater 真正执行。

    ⚠️ 只调用 ``processEvents()`` 不够：``deleteLater`` 投递的是 DeferredDelete 事件，
    它需要**进入事件循环**才会被处理。实测同样的代码，只用 processEvents 时
    124 个图层对象一个都不回收；改用 QEventLoop 跑一小段后立刻降到 3 个。
    这里用 ``QTimer.singleShot(0)`` + 局部 QEventLoop 驱动。
    """
    from PySide6.QtCore import QEventLoop, QTimer

    loop = QEventLoop()
    QTimer.singleShot(ms, loop.quit)
    loop.exec()
    qapp.processEvents()


def _owned_orphans(document: Document) -> list:
    """挂在指定文档名下、但不在 document.layers 里的 Layer 对象。"""
    gc.collect()
    live = [obj for obj in gc.get_objects() if isinstance(obj, Layer)]
    current = {id(layer) for layer in document.layers}
    orphans = []
    for obj in live:
        if id(obj) in current:
            continue
        try:
            if obj.parent() is document:
                orphans.append(obj)
        except RuntimeError:
            # 已被 deleteLater 销毁，属于正常情况
            continue
    return orphans


@pytest.mark.unit
def test_undo_does_not_accumulate_layer_objects(qapp):
    """反复撤销不得累积 Layer 对象（修复前 40 轮会到 200 个）。"""
    document = _document()
    document.save_state("基准")
    _drain(qapp)

    baseline = _owned_orphans(document)
    assert baseline == [], f"起始就有孤儿图层：{len(baseline)}"

    # 全局存活数只能比较「增量」：整个 pytest 进程里还有别的测试留下的 Document，
    # 它们的图层同样计入 gc.get_objects()，拿绝对值断言会在全量跑时误报。
    gc.collect()
    baseline_alive = sum(1 for obj in gc.get_objects() if isinstance(obj, Layer))

    for round_index in range(40):
        document.layers[0].x = 10 + round_index
        document.save_state(f"r{round_index}")
        if document.can_undo():
            document.undo()
        _drain(qapp)

    _drain(qapp)
    orphans = _owned_orphans(document)
    assert orphans == [], f"撤销 40 轮后仍有 {len(orphans)} 个孤儿图层挂在文档上"

    # 增量断言：抓住「没挂在树上但也没被回收」的情况（引用环 / deleteLater 没执行）。
    # 40 轮撤销每轮最多替换 len(document.layers) 个图层，修复前增量会达到 100+。
    gc.collect()
    final_alive = sum(1 for obj in gc.get_objects() if isinstance(obj, Layer))
    growth = final_alive - baseline_alive
    assert growth <= 12, (
        f"撤销 40 轮后 Layer 存活数从 {baseline_alive} 涨到 {final_alive}"
        f"（增量 {growth}），对象在累积"
    )


@pytest.mark.unit
def test_undo_does_not_grow_document_children(qapp):
    """Document 的 C++ 子对象数不随撤销轮次增长。

    修复前：恢复图层时传 ``parent=self``，每轮撤销都往 C++ 树上挂一批新节点，
            旧节点永不摘除 —— 30 轮后 children 4 → 34+（5 图层文档更大）。
    修复后：与 ``add_layer`` 所有权模型对齐（不挂 C++ 树），
            children 恒为「4 个管理器」+「被外部传了 parent 的图层」，
            撤销多少轮都不变。
    """
    document = _document(layer_count=3)
    document.save_state("基准")
    _drain(qapp)
    baseline_children = len(document.children())

    for round_index in range(30):
        document.layers[0].x = 20 + round_index
        document.save_state(f"r{round_index}")
        if document.can_undo():
            document.undo()
        _drain(qapp)
    _drain(qapp)

    after = len(document.children())
    assert after <= baseline_children, (
        f"C++ 子对象从 {baseline_children} 涨到 {after}，撤销仍在往树上挂对象"
    )


@pytest.mark.unit
def test_restored_layers_are_wired_to_document_changed(qapp):
    """撤销恢复出来的图层必须接回 changed 信号，否则改属性不重绘。"""
    document = _document(layer_count=2)
    document.save_state("基准")
    document.layers[0].x = 55
    document.save_state("移动")
    document.undo()
    _drain(qapp)

    restored = document.layers[0]
    receivers = restored.receivers("2changed()")
    assert receivers >= 1, "撤销后的图层没有连接 changed 信号（改属性不会触发重绘）"

    fired = {"count": 0}
    document.document_changed.connect(lambda: fired.__setitem__("count", fired["count"] + 1))
    restored.x = 999
    _drain(qapp)
    assert fired["count"] >= 1, "修改撤销后图层的属性没有触发 document_changed"


@pytest.mark.unit
def test_undo_still_restores_values_and_types(qapp):
    """修泄漏不能弄坏撤销本身：属性值、图层类型都要正确还原。"""
    from app.models.shaped_layer_new import ShapedLayer
    from app.models.text_layer import TextLayer

    document = _document(layer_count=2)
    document.add_text_layer(TextLayer(name="文字", x=20, y=20, width=200, height=60))
    document.add_shaped_layer(ShapedLayer(name="形状", x=50, y=50, width=80, height=80))
    document.save_state("加文字和形状")
    _drain(qapp)

    original_x = document.layers[0].x
    original_count = len(document.layers)
    document.layers[0].x = 123
    document.layers[0].name = "改过"
    document.save_state("改动")
    document.undo()
    _drain(qapp)

    assert document.layers[0].x == original_x
    assert document.layers[0].name != "改过"
    assert len(document.layers) == original_count
    types = [type(layer).__name__ for layer in document.layers]
    assert "TextLayer" in types
    assert "ShapedLayer" in types

    document.redo()
    _drain(qapp)
    assert document.layers[0].x == 123
    assert document.layers[0].name == "改过"


@pytest.mark.unit
def test_repeated_undo_redo_keeps_layer_count_stable(qapp):
    """反复 undo/redo 之后图层数量不应逐轮漂移。"""
    document = _document(layer_count=3)
    document.save_state("基准")

    first_count = None
    for round_index in range(25):
        document.layers[0].x = 30 + round_index
        document.save_state(f"r{round_index}")
        document.undo()
        document.undo()
        if document.can_redo():
            document.redo()
        _drain(qapp)
        if first_count is None:
            first_count = len(document.layers)
        assert len(document.layers) == first_count, (
            f"第 {round_index} 轮后图层数从 {first_count} 变成 {len(document.layers)}"
        )
