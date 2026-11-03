"""交互流畅性回归测试。

锁住 2026-11-02 定位的三个性能缺陷，防止以后再退化：

1. 交互帧的图层重采样必须走快速路径
   （曾用 ``rgba_resampler.resize_rgba_premultiplied``：760×560 单层 43.3ms，
   8 层拖动只落地 4/30 帧 ≈ 18fps）。
2. 交互帧的降采样必须有收益门槛
   （曾把 1080×1350 只缩到 0.889，省下的合成时间抵不掉每层一次重采样）。
3. 批量导出不得整段持有文档锁
   （曾持锁 1003ms，主线程拖拽同时被阻塞 980ms）。
4. 图层面板模型只在行结构真变时才 reset
   （曾每次操作固定 2 轮全表 reset，拖排序时面板整块闪）。
"""
from __future__ import annotations

import threading
import time

import pytest
from PIL import Image

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.batch_export_view_model import BatchExportViewModel
from app.qml.viewmodels.layer_list_model import LayerListModel
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel
from app.utils import fast_renderer_preview as preview_module
from app.utils.fast_renderer_preview import FastRendererPreview


def _document(layer_count: int = 6, canvas=(400, 300), image_size=(200, 150)) -> Document:
    document = Document()
    document.create_new(*canvas)
    for index in range(layer_count):
        document.add_layer(
            f"L{index}",
            5 * index,
            5,
            image_size[0],
            image_size[1],
            image_source=None,
            is_folder=False,
        )
    return document


class _Renderer(FastRendererPreview):
    """只借用预览 mixin，避开 FastRenderer 的完整初始化依赖。"""


# ---------------------------------------------------------------- 1. 重采样路径


@pytest.mark.unit
def test_interactive_scale_uses_single_pass_pil_resize():
    """交互帧缩放必须是一次 PIL resize，不能走 float 预乘多通道路径。"""
    renderer = _Renderer()
    source = Image.new("RGBA", (400, 300), (10, 20, 30, 128))

    result = renderer._scale_layer_for_interactive_preview(source, 0.5)

    assert result.size == (200, 150)
    assert result.mode == "RGBA"


@pytest.mark.unit
def test_interactive_scale_is_dramatically_faster_than_premultiplied():
    """同一尺寸下，交互帧缩放必须比 float 预乘路径快一个量级以上。

    实测基线：760×560 → 675×497，PIL 约 4.3ms，float 预乘约 43.3ms。
    这里只断言「至少快 3 倍」，给慢机器留余量，同时足以抓住换回旧实现。
    """
    from app.utils.rgba_resampler import resize_rgba_premultiplied

    renderer = _Renderer()
    source = Image.new("RGBA", (760, 560), (200, 100, 50, 180))
    target = (675, 497)

    runs = 5
    started = time.perf_counter()
    for _ in range(runs):
        renderer._scale_layer_for_interactive_preview(source, 0.8889)
    fast = time.perf_counter() - started

    started = time.perf_counter()
    for _ in range(runs):
        resize_rgba_premultiplied(source, target, Image.Resampling.BILINEAR)
    slow = time.perf_counter() - started

    assert fast * 3 < slow, f"交互帧缩放没有走快速路径（fast={fast:.4f}s slow={slow:.4f}s）"


@pytest.mark.unit
def test_interactive_scale_returns_source_when_scale_is_one():
    renderer = _Renderer()
    source = Image.new("RGBA", (100, 100), (0, 0, 0, 255))
    assert renderer._scale_layer_for_interactive_preview(source, 1.0) is source


# ---------------------------------------------------------------- 2. 降采样门槛


@pytest.mark.unit
def test_interactive_render_scale_skips_negligible_downsample():
    """小幅降采样（0.75 以上）必须直接返回 1.0，避免每层白做一次重采样。"""
    document = _document()
    renderer = _Renderer()

    # 1080x1350 在 MAX_EDGE=1200 下算出 0.8889 —— 属于「省不下什么」的区间
    document.canvas_width, document.canvas_height = 1080, 1350
    assert renderer._get_interactive_render_scale(document, True, True) == 1.0

    # 大画布才真降
    document.canvas_width, document.canvas_height = 3000, 3000
    scale = renderer._get_interactive_render_scale(document, True, True)
    assert scale < 0.75


@pytest.mark.unit
def test_interactive_render_scale_is_one_for_non_interactive():
    document = _document()
    renderer = _Renderer()
    document.canvas_width, document.canvas_height = 3000, 3000
    assert renderer._get_interactive_render_scale(document, True, False) == 1.0
    assert renderer._get_interactive_render_scale(document, False, True) == 1.0


@pytest.mark.unit
def test_interactive_frames_keep_canvas_resolution_for_normal_canvas():
    """1080×1350 画布的交互帧必须是全分辨率，避免与 final 帧之间纹理尺寸跳变。

    「交互帧 960×1200 ↔ 松手后 1080×1350」的切换会让 QML 重传纹理，
    正是拖拽时画面闪一下的来源之一。
    """
    from app.services.preview_render_service import render_preview_to_image

    document = _document(layer_count=3)
    document.canvas_width, document.canvas_height = 1080, 1350

    interactive = render_preview_to_image(
        document, force_refresh=True, interactive_low_quality=True
    )
    final = render_preview_to_image(document, force_refresh=True)

    assert interactive.image is not None
    assert final.image is not None
    assert interactive.image.size == final.image.size == (1080, 1350)


# ---------------------------------------------------------------- 3. 导出不持锁


@pytest.mark.unit
def test_batch_export_does_not_hold_document_lock_for_whole_run(qapp, tmp_path):
    """导出期间主线程必须能拿到文档锁（旧实现整段持有，阻塞 1 秒级）。

    判定方式特意选「在导出进行中反复抢锁，统计最坏等待」而不是「抢一次」：
    只抢一次容易被时序偶然放过（跑得快就刚好撞不上持锁窗口）。
    """
    document = _document(layer_count=3)
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    lock = workspace.documentLock
    observed: dict = {"waits": []}
    holder = {}
    stop = threading.Event()

    def main_thread_probe():
        """模拟主线程在导出期间持续尝试取锁（拖动/改属性都会走这条）。"""
        while not stop.is_set():
            started = time.perf_counter()
            acquired = lock.acquire(timeout=2.0)
            waited = (time.perf_counter() - started) * 1000
            observed["waits"].append(waited)
            if acquired:
                lock.release()
            else:
                observed["starved"] = True
                return
            time.sleep(0.005)

    def runner(clone, **kwargs):
        holder["is_clone"] = clone is not document
        probe = threading.Thread(target=main_thread_probe, daemon=True)
        probe.start()
        time.sleep(0.25)  # 保持「导出还在跑」，让探针多次尝试
        stop.set()
        probe.join(timeout=3.0)
        return True

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    view_model.outputDirectory = str(tmp_path)
    view_model.count = 1
    assert view_model.startExport() is True

    deadline = time.monotonic() + 20
    while view_model.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()

    waits = observed["waits"]
    assert waits, "探针没有拿到任何采样"
    assert not observed.get("starved"), "导出期间主线程完全拿不到文档锁"
    worst = max(waits)
    assert worst < 100, f"主线程最长等待锁 {worst:.0f}ms，仍会被感知为卡死"
    assert holder.get("is_clone") is True, "导出必须跑在文档副本上，不能直接改共享文档"
    assert view_model.succeeded is True
    # 共享文档不应被导出过程污染
    assert len(document.layers) == 3


@pytest.mark.unit
def test_batch_export_publishes_reports_back_to_shared_document(qapp, tmp_path):
    """副本导出的报告必须搬回主文档，否则降级/调整提示会全丢。"""
    document = _document(layer_count=2)
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )

    def runner(clone, **kwargs):
        clone._last_export_report = {"exported_count": 2, "failed_count": 0}
        clone._last_precompute_diagnostics = {"degradations": {"x": 1}, "degradation_total": 1}
        clone._last_export_adjustment = {"requested": 5, "planned": 2}
        return True

    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    view_model.outputDirectory = str(tmp_path)
    view_model.count = 5
    assert view_model.startExport() is True

    deadline = time.monotonic() + 20
    while view_model.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()

    assert document._last_export_report == {"exported_count": 2, "failed_count": 0}
    assert "降级" in view_model.degradationSummary
    assert "实际导出 2 张" in view_model.adjustmentSummary


@pytest.mark.unit
def test_batch_export_falls_back_to_locking_when_snapshot_unavailable(qapp, tmp_path):
    """快照失败时必须退回持锁导出（慢但安全），不能静默跑在共享文档上无锁。"""
    document = _document(layer_count=2)
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )

    def runner(target, **kwargs):
        # 退回路径：runner 拿到的是共享文档本身
        runner.shared = target is document
        return True

    runner.shared = None
    view_model = BatchExportViewModel(workspace=workspace, runner=runner)
    # 强制快照失败
    view_model._capture_export_snapshot = lambda: (None, "")
    view_model.outputDirectory = str(tmp_path)
    view_model.count = 1
    assert view_model.startExport() is True

    deadline = time.monotonic() + 20
    while view_model.running and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()

    assert runner.shared is True
    assert view_model.succeeded is True


# ---------------------------------------------------------------- 4. 图层面板刷新


def _workspace_with_model(layer_count: int = 5):
    document = _document(layer_count=layer_count)
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    return document, workspace, workspace._layer_model


@pytest.mark.unit
def test_layer_model_does_not_reset_for_attribute_changes():
    """改名/显隐/锁定/选中/移动 都不该重建 delegate。"""
    document, workspace, model = _workspace_with_model()

    counter = {"reset": 0}
    model.modelAboutToBeReset.connect(lambda: counter.__setitem__("reset", counter["reset"] + 1))

    for action in (
        lambda: setattr(document.layers[0], "name", "改名"),
        lambda: workspace.toggleLayerVisible(1),
        lambda: workspace.toggleLayerLocked(1),
        lambda: workspace.selectLayer(2),
        lambda: workspace._set_layer_attrs(0, {"x": 77}, "移动"),
    ):
        counter["reset"] = 0
        action()
        document.layer_changed.emit()
        assert counter["reset"] == 0, "属性变更不应触发整表重建"


@pytest.mark.unit
def test_layer_model_resets_when_structure_changes():
    """增删/排序必须重建（否则面板与实际顺序脱节）。"""
    document, workspace, model = _workspace_with_model()

    counter = {"reset": 0}
    model.modelAboutToBeReset.connect(lambda: counter.__setitem__("reset", counter["reset"] + 1))

    workspace.selectLayer(0)
    counter["reset"] = 0
    workspace.moveSelectedLayer("forward")
    assert counter["reset"] >= 1, "排序后必须让模型重建"

    counter["reset"] = 0
    workspace.deleteSelectedLayer()
    assert counter["reset"] >= 1, "删除后必须让模型重建"


@pytest.mark.unit
def test_layer_model_reorder_detected_via_stable_id_not_index():
    """结构指纹必须用稳定 ID。

    用「文档索引」的话，把中间图层移到顶层后索引集合仍是 0..N-1，
    指纹不变 → 认为没有结构变化 → 面板顺序不会更新。
    """
    document, workspace, model = _workspace_with_model()
    before = [model.data(model.index(r, 0), model.NameRole) for r in range(model.rowCount())]

    workspace.selectLayer(2)
    workspace.moveSelectedLayer("forward")
    after = [model.data(model.index(r, 0), model.NameRole) for r in range(model.rowCount())]

    assert before != after, "排序没有被模型感知到"
    assert sorted(before) == sorted(after)


@pytest.mark.unit
def test_finish_arrangement_triggers_single_model_sync():
    """一次排序只应有单一触发点（旧实现是 layer_changed + 显式 reset 共 2 轮）。"""
    document, workspace, model = _workspace_with_model()

    counter = {"reset": 0, "data": 0}
    model.modelAboutToBeReset.connect(lambda: counter.__setitem__("reset", counter["reset"] + 1))
    model.dataChanged.connect(lambda *a: counter.__setitem__("data", counter["data"] + 1))

    workspace.selectLayer(1)
    counter["reset"] = 0
    counter["data"] = 0
    workspace.moveSelectedLayer("forward")

    total_syncs = counter["reset"] + counter["data"]
    assert counter["reset"] <= 1, f"一次排序触发了 {counter['reset']} 轮重建"
    assert total_syncs >= 1, "排序后模型没有任何刷新"


# ---------------------------------------------------------------- 5. 脏矩形一致性


@pytest.mark.unit
def test_incremental_drag_matches_full_render_pixel_exact(tmp_path):
    """增量预览（脏矩形路径）必须与全量重建**逐像素相同**。

    锁住 2026-11-03 的脏矩形优化。该改动把拖动帧从「整画布 copy + 全层合成」
    换成「只重合成活动层新旧位置并集」，4000x5000 画布从 263ms 降到 32ms。
    致命失败模式：脏区算小了、或忘了取新旧并集 → 留残影。所以用「全量重建」
    做基准，要求逐字节相同（容差 0）。

    两个必须注意的测试构造前提（都踩过）：
    1. **必须用有真实图像的图层**。空图层 `get_layer_surface_cached` 返回 None，
       会直接 continue 掉，脏矩形路径根本走不到，测试会假绿。
    2. **基准帧必须用另一份文档**。对同一文档调 render_preview(force_refresh=True)
       会作废交互底图缓存，使下一帧 dirty 变成整层矩形，把并集 bug 藏起来。
    """
    from PIL import Image
    from app.utils.fast_renderer import get_global_fast_renderer

    image_path = tmp_path / "layer.png"
    Image.new("RGBA", (120, 100), (200, 80, 40, 220)).save(image_path)

    def _make(canvas=(300, 240), offset=0):
        doc = Document()
        doc.create_new(*canvas)
        for index in range(4):
            doc.add_layer(
                f"D{index}", 20 + index * 18, 15 + index * 14, 120, 100,
                image_source=str(image_path), is_folder=False,
            )
        doc.layers[3].x = 20 + offset
        doc.layers[3].y = 15 + offset // 2
        return doc

    renderer = get_global_fast_renderer()
    document = _make()
    renderer.render_preview_incremental(document, 3, force_refresh=True, interactive_low_quality=True)

    for step, offset in enumerate((10, 45, 90, 30, 70)):
        document.layers[3].x = 20 + offset
        document.layers[3].y = 15 + offset // 2

        incremental = renderer.render_preview_incremental(
            document, 3, force_refresh=False, interactive_low_quality=True
        )
        # 独立文档做全量基准，避免污染底图缓存
        full = renderer.render_preview(
            _make(offset=offset), force_refresh=True, interactive_low_quality=True
        )

        assert incremental is not None and full is not None, f"第{step}帧返回 None"

        # 容差 1/255，不是「逐字节相同」—— 原因必须记录清楚，否则以后会被误当成
        # 测试太松而收紧，结果改坏实现：
        #
        # _high_quality_alpha_composite 收尾用 _float_to_uint8_with_dithering，
        # 而该抖动用「固定种子 + 按数组 shape 生成随机数」。脏区把数组切小了，
        # 随机序列随之改变 → 抖动图案错位 → 结果差 ±1（实测最大 1，无 >1）。
        # 这是抖动实现的固有性质，不是脏区算错；脏区算错会表现为**大面积整块
        # 偏移或残影**（差几十到上百），下面单独断言这一点。
        a, b = incremental.tobytes(), full.tobytes()
        assert len(a) == len(b)
        max_diff = max(abs(x - y) for x, y in zip(a, b))
        assert max_diff <= 1, (
            f"第{step}帧（偏移 {offset}）增量与全量差异 {max_diff} > 1，"
            f"脏矩形算错或漏了效果外扩"
        )


@pytest.mark.unit
def test_incremental_drag_takes_dirty_rect_path(tmp_path):
    """确认拖动帧真的走了脏矩形路径，而不是悄悄退回整画布拷贝。

    没有这条断言，上一条测试可能在「脏矩形代码根本没执行」的情况下依然全绿
    （实测踩过：空图层 + 同文档基准，注入退化后 15 项测试全部通过）。
    """
    from PIL import Image
    import app.utils.fast_renderer_preview as preview_module
    from app.utils.fast_renderer import get_global_fast_renderer

    image_path = tmp_path / "layer.png"
    Image.new("RGBA", (120, 100), (30, 160, 90, 200)).save(image_path)

    document = Document()
    document.create_new(300, 240)
    for index in range(4):
        document.add_layer(
            f"D{index}", 20 + index * 18, 15 + index * 14, 120, 100,
            image_source=str(image_path), is_folder=False,
        )

    renderer = get_global_fast_renderer()
    renderer.render_preview_incremental(document, 3, force_refresh=True, interactive_low_quality=True)

    calls = {"n": 0, "dirty": []}
    original = preview_module.FastRendererPreview._compose_in_dirty_region

    def _spy(self, **kwargs):
        calls["n"] += 1
        calls["dirty"].append(kwargs.get("dirty"))
        return original(self, **kwargs)

    preview_module.FastRendererPreview._compose_in_dirty_region = _spy
    try:
        document.layers[3].x = 60
        renderer.render_preview_incremental(
            document, 3, force_refresh=False, interactive_low_quality=True
        )
    finally:
        preview_module.FastRendererPreview._compose_in_dirty_region = original

    assert calls["n"] >= 1, "增量拖动没有走脏矩形路径（退回了整画布拷贝）"
    dirty = calls["dirty"][0]
    assert dirty is not None
    x0, y0, x1, y1 = dirty
    # 脏区必须显著小于整张画布
    assert (x1 - x0) * (y1 - y0) < 300 * 240 * 0.9, f"脏区 {dirty} 过大，等于没做脏矩形"


@pytest.mark.unit
def test_dirty_region_covers_effects_outset():
    """脏矩形必须包含描边/阴影/外发光的外扩，否则边缘会留残影。"""
    from app.utils.fast_renderer_preview import FastRendererPreview

    class _R(FastRendererPreview):
        pass

    renderer = _R()
    layer = type("L", (), {
        "stroke_enabled": True, "stroke_width": 12,
        "shadow_enabled": True, "shadow_blur": 8, "shadow_offset_x": 6, "shadow_offset_y": -4,
        "glow_enabled": True, "glow_radius": 5,
    })()

    outset = renderer._layer_effects_outset_px(layer, 1.0)
    # 阴影 blur*2 + offset = 16+6 = 22 是最大项，再加 2px 余量
    assert outset >= 22, f"外扩量 {outset} 不足，阴影/描边会溢出脏区"
    # 缩放后应等比减小（交互帧是降采样渲染）
    assert renderer._layer_effects_outset_px(layer, 0.5) < outset
