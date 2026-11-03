"""缩略图取消接口：契约与竞态测试。

覆盖三件容易做错的事：

1. 取消后**不能**让后台任务把旧缩略图写回磁盘
   （清空标签页后卡片还显示旧图，是用户直接可见的"坏了"）。
2. 取消后重新请求必须能正常工作
   （用布尔 cancelled 集合的实现会在这里失败）。
3. 取消一个正在渲染的任务，落盘前必须被拦下。

时序类测试一律**注入延迟/钩子**制造确定窗口，不靠 sleep 猜。
实测纯色图层渲染只要 ~20ms，sleep 0.08s 时前几页早已落盘 —— 靠 sleep
写出来的测试会给出假绿或假红。
"""
from __future__ import annotations

import os
import sys
import threading
import time

import pytest
from PIL import Image

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models.document import Document
from app.utils.preset_manager import PresetManager
from app.utils.preset_thumbnail import (
    PresetThumbnailService,
    render_preset_thumbnails,
    thumb_path_for,
)


def _document(work_dir: str, name: str, color) -> Document:
    document = Document()
    document.create_new(400, 300)
    document.tab_name = name
    document.original_tab_name = name
    image_path = os.path.join(work_dir, f"{name}.png")
    Image.new("RGBA", (240, 180), color).save(image_path)
    document.add_layer("L0", 10, 20, 200, 150, image_source=image_path)
    return document


@pytest.fixture()
def service_env(qapp, tmp_path):
    work_dir = str(tmp_path)
    manager = PresetManager(app_dir=work_dir, copy_initial=False)
    pages = [
        _document(work_dir, f"p{index}", (40 * index, 100, 160, 255))
        for index in range(4)
    ]
    preset_id = manager.save_preset_documents("取消测试", "", pages)
    assert preset_id
    service = PresetThumbnailService(manager.presets_dir)
    yield service, manager.presets_dir, preset_id
    service.stop(timeout=1.0)


@pytest.mark.unit
def test_cancel_returns_false_when_nothing_pending(service_env):
    service, _presets_dir, preset_id = service_env
    assert service.cancel(preset_id) is False


@pytest.mark.unit
def test_cancel_clears_pending_and_is_idempotent(service_env):
    service, _presets_dir, preset_id = service_env
    service.request(preset_id)
    assert service.cancel(preset_id) is True
    assert service.pending_count() == 0
    # 再调一次不该报错，也不该误报"取消了任务"
    assert service.cancel(preset_id) is False


@pytest.mark.unit
def test_cancel_prevents_stale_thumbnail_writeback(service_env):
    """取消后，已排队但没跑的任务不得把缩略图写回磁盘。

    这是本接口存在的全部理由：清空标签页时调用方已经删掉了缩略图，
    若后台任务随后写回，卡片会继续显示**已被清空的内容**。
    """
    service, presets_dir, preset_id = service_env
    thumb = thumb_path_for(presets_dir, preset_id, 0)
    notified: list[str] = []
    service.add_listener(lambda pid, path: notified.append(pid))

    service.request(preset_id)
    service.cancel(preset_id)
    deadline = time.monotonic() + 6.0
    while time.monotonic() < deadline:
        time.sleep(0.05)

    assert not os.path.isfile(thumb), "取消后仍写回了缩略图"
    assert notified == [], "取消后仍回调了 UI"


@pytest.mark.unit
def test_request_after_cancel_keeps_new_pending_state(service_env, monkeypatch):
    """取消后重新请求：新任务的 pending 不能被旧任务的收尾清掉。

    ⚠️ 这是「布尔 cancelled 集合 / 无条件 discard」实现的必失败点：
    旧队列项还没被消费完，新请求入队后旧任务结束时会把它一起清掉，
    UI 侧于是以为任务已结束、而结果永远不来 —— 卡片停在占位图上。

    实现用每 preset 一个**代数**，任务带自己那一代进来，收尾时只清自己那代。

    测法必须确定：注入渲染延迟，让「旧任务已收尾、新任务仍在渲染」这个
    窗口稳定存在 0.45s，再断言 pending 仍为 1。靠 poll 采样会撞上
    「任务刚完成、通知还没到」的正常间隙，产生假红。
    """
    import app.services.render_service as render_service

    original = render_service.render_document_to_image

    def slow_render(*args, **kwargs):
        time.sleep(0.45)
        return original(*args, **kwargs)

    monkeypatch.setattr(render_service, "render_document_to_image", slow_render)

    service, presets_dir, preset_id = service_env
    thumb = thumb_path_for(presets_dir, preset_id, 0)
    done = threading.Event()
    service.add_listener(lambda pid, path: done.set() if pid == preset_id else None)

    service.request(preset_id)   # 旧任务（即将被取消）
    service.cancel(preset_id)    # 代数 +1，旧任务作废
    service.request(preset_id, force=True)  # 新任务，带新代数
    assert service.pending_count() == 1

    # 0.25s 后旧任务一定已被工作线程消费并收尾，而新任务还在渲染中
    time.sleep(0.25)
    assert service.pending_count() == 1, (
        "新任务的 pending 被作废旧任务的收尾清掉了"
    )

    assert done.wait(timeout=30), "取消后重新请求没有出图"
    assert os.path.isfile(thumb)
    assert service.pending_count() == 0


@pytest.mark.unit
def test_cancel_during_render_blocks_writeback(service_env, monkeypatch):
    """渲染进行中取消 → 落盘前被拦下。

    注入 0.45s 延迟制造确定窗口（真实渲染可能只要 20ms，靠 sleep 猜不到）。
    """
    import app.services.render_service as render_service

    original = render_service.render_document_to_image

    def slow_render(*args, **kwargs):
        time.sleep(0.45)
        return original(*args, **kwargs)

    monkeypatch.setattr(render_service, "render_document_to_image", slow_render)

    service, presets_dir, preset_id = service_env
    thumb = thumb_path_for(presets_dir, preset_id, 0)
    if os.path.isfile(thumb):
        os.remove(thumb)

    notified: list[str] = []
    service.add_listener(lambda pid, path: notified.append(path))

    service.request(preset_id, force=True)
    time.sleep(0.15)  # 第一页正在渲染
    service.cancel(preset_id)
    time.sleep(2.5)

    assert not os.path.isfile(thumb), "渲染途中取消后仍落盘"
    assert notified == [], "渲染途中取消后仍回调"


@pytest.mark.unit
def test_render_stops_at_first_cancelled_page(service_env):
    """逐页检查：钩子返回真就停下，且**不返回半批结果**。

    返回半批是危险的——调用方会把这些路径当作"已就绪"缓存起来，
    其中可能包含刚刚被删掉的文件。
    """
    _service, presets_dir, preset_id = service_env
    calls = {"count": 0}

    def cancel_after_first() -> bool:
        calls["count"] += 1
        return calls["count"] > 1

    result = render_preset_thumbnails(
        preset_id,
        presets_dir,
        source_path=os.path.join(presets_dir, f"{preset_id}.cmp"),
        should_cancel=cancel_after_first,
    )
    assert result == {}
    assert calls["count"] >= 2, "只在开头检查了一次，没有逐页检查"


@pytest.mark.unit
def test_cancel_all_clears_everything(service_env):
    service, presets_dir, _preset_id = service_env
    manager = PresetManager(app_dir=os.path.dirname(presets_dir), copy_initial=False)
    ids = [
        manager.save_preset_documents(f"批量{index}", "", [_document(
            os.path.dirname(presets_dir), f"b{index}", (index * 30, 80, 200, 255)
        )])
        for index in range(3)
    ]
    for preset_id in ids:
        service.request(preset_id)
    assert service.pending_count() == len(ids)
    assert service.cancel_all() == len(ids)
    assert service.pending_count() == 0


@pytest.mark.unit
def test_cancelled_task_skips_rendering_entirely(service_env, monkeypatch):
    """已取消的任务不得白跑一遍渲染。

    实测一个 4 页预设渲染约 1.2s，而渲染器与画布预览共享图层 surface 缓存。
    取消后还白跑一遍，用户看到的是「清空完标签页，画布却卡了一下」。

    实现有两道冗余防护，任一存活即通过：
      - `_run` 出队时的 `_is_stale` 直接 continue（最省，一次都不调渲染）
      - `render_preset_thumbnails` 每页开始前的 `should_cancel`（第一页前就拦住）

    所以这条测试锁定的是**组合行为**（取消后零渲染尝试），
    单独删掉任意一道不会失败 —— 这是刻意的冗余，不是测试没写严。
    """
    import app.services.render_service as render_service

    calls = {"count": 0}
    original = render_service.render_document_to_image

    def counting_render(*args, **kwargs):
        calls["count"] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(render_service, "render_document_to_image", counting_render)

    service, presets_dir, preset_id = service_env
    # 确保没有缓存命中，否则连渲染都不会尝试
    for page in range(4):
        path = thumb_path_for(presets_dir, preset_id, page)
        if os.path.isfile(path):
            os.remove(path)

    service.request(preset_id, force=True)
    service.cancel(preset_id)

    deadline = time.monotonic() + 2.0
    while time.monotonic() < deadline:
        time.sleep(0.05)

    assert calls["count"] == 0, f"取消后仍尝试渲染了 {calls['count']} 次"


@pytest.mark.unit
def test_normal_request_unaffected_by_cancel_api(service_env):
    """没调用 cancel 时，行为与改造前完全一致。"""
    service, presets_dir, preset_id = service_env
    thumb = thumb_path_for(presets_dir, preset_id, 0)
    done = threading.Event()
    service.add_listener(lambda pid, path: done.set() if pid == preset_id else None)
    service.request(preset_id, force=True)
    assert done.wait(timeout=30)
    assert os.path.isfile(thumb)
    assert service.pending_count() == 0
