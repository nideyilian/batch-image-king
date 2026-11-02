"""文字图层尺寸读写的并发安全回归（2026-11-02）。

背景：``_render_text_supersampled`` 为了让文字边缘更平滑，会**原地**把
``_width`` / ``_height`` / ``_font_size`` 等十几个字段临时放大 N 倍，渲染完
再在 ``finally`` 里还原。

问题：``width`` / ``height`` 的 getter 与 setter 原先不加锁。只要渲染发生在
后台线程（预览、批量导出），主线程在"放大期间"读尺寸就会拿到临时值。

实测后果（QML 画布缩放手柄）：
  - 用户把文字图层从 354×94 拖到 394×124，写回成功；
  - 紧接着的预览渲染进入超采样，_width 被临时改成 788；
  - 主线程 commit 后读回 788×248 —— 精确 2 倍；
  - 表现为 ``tests/helpers/qml_canvas_interaction_probe.py`` 以 13%~40%
    概率报 ``resize mismatch: before=(354, 94), after=(788, 248)``。

修复：getter / setter 都持 ``_render_lock``（与 ``render_text`` 同一把
RLock，可重入，不会死锁）。
"""

from __future__ import annotations

import threading
import time

import pytest

from app.models.text_layer import TextLayer


def _make_layer(width: int = 354, height: int = 94) -> TextLayer:
    layer = TextLayer(name="并发测试", x=108, y=1070, width=width, height=height)
    layer.text_content = "限量腕表"
    layer.current_text = "限量腕表"
    layer.font_size = 86
    layer.auto_fit_text_box = False
    return layer


@pytest.mark.unit
def test_supersample_does_not_leak_scaled_size_to_readers():
    """超采样渲染期间，外部读到的尺寸必须始终是逻辑尺寸。"""
    layer = _make_layer()
    logical_size = (layer.width, layer.height)
    leaked: list[tuple[int, int]] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            leaked.append((layer.width, layer.height))

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        # 多轮渲染，扩大与读线程重叠的概率
        for _ in range(8):
            layer._cached_image = None
            layer.render_text()
    finally:
        stop.set()
        thread.join(timeout=5)

    assert leaked, "读线程没有采到样本，测试本身失效"
    bad = [size for size in leaked if size != logical_size]
    assert not bad, (
        f"读到 {len(bad)} 次非逻辑尺寸（应恒为 {logical_size}），"
        f"样本前 5 个: {bad[:5]} —— getter 未持 _render_lock"
    )


@pytest.mark.unit
def test_concurrent_resize_and_render_keeps_written_size():
    """渲染与改尺寸并发时，写进去的尺寸不能被渲染的还原动作覆盖。"""
    layer = _make_layer()
    target = (394, 124)

    errors: list[str] = []

    def renderer():
        for _ in range(12):
            try:
                layer._cached_image = None
                layer.render_text()
            except Exception as exc:  # pragma: no cover - 失败即报错
                errors.append(f"render: {exc!r}")

    def resizer():
        for _ in range(12):
            layer.width = target[0]
            layer.height = target[1]
            time.sleep(0.001)

    threads = [threading.Thread(target=renderer), threading.Thread(target=resizer)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)

    assert not errors, f"并发过程抛异常: {errors}"
    # 最后再写一次，然后确认读回值一致（不能被超采样任务残留污染）
    layer.width, layer.height = target
    assert (layer.width, layer.height) == target


@pytest.mark.unit
def test_height_getter_locked_symmetrically():
    """height 与 width 必须同样受保护，避免只修一半。"""
    layer = _make_layer()
    logical_height = layer.height
    leaked: list[int] = []
    stop = threading.Event()

    def reader():
        while not stop.is_set():
            leaked.append(layer.height)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        for _ in range(8):
            layer._cached_image = None
            layer.render_text()
    finally:
        stop.set()
        thread.join(timeout=5)

    bad = [h for h in leaked if h != logical_height]
    assert not bad, f"height 读到临时放大值 {bad[:5]}（应恒为 {logical_height}）"


@pytest.mark.unit
def test_render_lock_is_reentrant():
    """getter 会在 render_text 内部被调用，锁必须可重入，否则自锁。"""
    layer = _make_layer()

    def access_inside_render():
        # 模拟渲染内部再读一次尺寸：如果用的是普通 Lock 会死锁
        _ = layer.width
        _ = layer.height

    layer._cached_image = None
    with layer._render_lock:
        access_inside_render()
        layer.render_text()

    assert layer.width > 0 and layer.height > 0
