"""预览结果被丢弃的判定：拖动时每一帧都必须能上屏。

根因：``_on_preview_rendered`` 原来要求 ``generation == self._preview_generation``。
但 ``requestPreview`` / ``previewLiveGeometry`` 每调一次就推一次 generation，
渲染 3~15ms 期间主线程又推了几次，结果回来时 generation 必然落后 —— **每一帧
都被丢掉**，画面停在旧帧，只有彻底停手、定时器静默后才接受一次。
用户感知就是「拖动时不动、松手才跳」。

修法：判定改成「比已接受的更新」（``>= _accepted_preview_generation``），
而不是「等于当前最新」。
"""

from __future__ import annotations

import pytest

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


@pytest.fixture()
def vm():
    document = Document()
    document.create_new(1200, 800)
    document.add_layer("图层", 200, 200, 500, 400, is_folder=False)
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    workspace.selectLayer(0)
    return workspace


def _make_qimage(width=64, height=64):
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QImage

    image = QImage(width, height, QImage.Format_RGBA8888)
    image.fill(Qt.red)
    return image


def _emit(vm, request_id, generation, image=None):
    """模拟后台线程回调（直接在主线程调用，绕过队列延迟）。"""
    vm._on_preview_rendered(
        request_id,
        generation,
        True,
        image if image is not None else _make_qimage(),
        "",
        0.01,
    )


def test_stale_generation_is_still_accepted(vm):
    """generation 落后于当前值，但比已接受的更新时，仍要上屏。"""
    vm._preview_generation = 10
    vm._render_request_id = 1
    vm._accepted_preview_generation = 2
    revision_before = vm.previewRevision

    _emit(vm, 1, 5)   # 5 < 10，但 5 > 2

    assert vm.previewRevision == revision_before + 1, "更旧但更新的帧必须上屏"
    assert vm._accepted_preview_generation == 5


def test_equal_generation_is_accepted(vm):
    vm._preview_generation = 7
    vm._render_request_id = 3
    vm._accepted_preview_generation = 6
    revision_before = vm.previewRevision

    _emit(vm, 3, 7)

    assert vm.previewRevision == revision_before + 1


def test_older_than_accepted_is_dropped(vm):
    """比已上屏的更旧，必须丢弃，避免画面倒退。"""
    vm._preview_generation = 20
    vm._render_request_id = 4
    vm._accepted_preview_generation = 15
    revision_before = vm.previewRevision

    _emit(vm, 4, 9)

    assert vm.previewRevision == revision_before, "更旧的帧不能覆盖新画面"


def test_wrong_request_id_is_dropped(vm):
    """request_id 不匹配说明是过期请求，必须丢弃。"""
    vm._preview_generation = 10
    vm._render_request_id = 8
    vm._accepted_preview_generation = 1
    revision_before = vm.previewRevision

    _emit(vm, 7, 10)   # id 不匹配

    assert vm.previewRevision == revision_before


def test_consecutive_drag_frames_keep_updating(vm):
    """模拟拖动：连续 8 帧，每一帧都必须让 revision 前进。"""
    vm._render_request_id = 0
    vm._accepted_preview_generation = 0
    revisions = [vm.previewRevision]

    for _ in range(8):
        # 每帧：主线程推进 generation 并「启动渲染」
        vm._preview_generation += 1
        vm._render_request_id += 1
        started_generation = vm._preview_generation
        # 渲染期间又推进了几次（模拟拖动中继续移动）
        vm._preview_generation += 2
        # 渲染回来
        _emit(vm, vm._render_request_id, started_generation)
        revisions.append(vm.previewRevision)

    assert revisions == list(range(revisions[0], revisions[0] + 9)), (
        f"每一帧都应上屏，实际 revision 序列={revisions}"
    )


def test_live_geometry_writes_without_history(vm):
    """拖动中的实时几何：要改坐标，但不能写历史、不能改 modified。"""
    document = vm._document
    layer = document.layers[0]
    history_before = len(document._history_manager._history)
    modified_before = document.is_modified

    vm._auto_render = False   # 只验证几何写入，不触发渲染
    assert vm.previewLiveGeometry(300, 250, 500, 400)

    assert (layer.x, layer.y) == (300, 250)
    assert len(document._history_manager._history) == history_before, "拖动中不写历史"
    assert document.is_modified == modified_before, "拖动中不改 modified"


def test_restore_geometry_reverts_live_writes(vm):
    """取消拖动必须把实时写入的几何还原。"""
    document = vm._document
    layer = document.layers[0]
    original = (layer.x, layer.y, layer.width, layer.height)

    vm._auto_render = False
    vm.previewLiveGeometry(500, 400, 300, 200)
    assert (layer.x, layer.y) != original[:2]

    assert vm.restoreSelectedGeometry(*original)
    assert (layer.x, layer.y, layer.width, layer.height) == original


def test_multi_selection_live_geometry_scales_proportionally(vm):
    """多选缩放：每个图层按同一比例缩放。"""
    document = vm._document
    document.add_layer("图层2", 800, 200, 300, 200, is_folder=False)
    document.select_layers([0, 1], primary_index=0)
    vm._auto_render = False

    before = [(l.x, l.y, l.width, l.height) for l in document.layers]
    bounds_x, bounds_y, bounds_w, bounds_h = vm._selection_bounds()

    vm.previewLiveGeometry(bounds_x, bounds_y, bounds_w * 2, bounds_h * 2)

    for layer, (bx, by, bw, bh) in zip(document.layers, before):
        assert layer.width == pytest.approx(bw * 2, rel=0.05)
        assert layer.height == pytest.approx(bh * 2, rel=0.05)

    vm.restoreSelectedGeometry(bounds_x, bounds_y, bounds_w, bounds_h)
    for layer, (bx, by, bw, bh) in zip(document.layers, before):
        assert abs(layer.x - bx) <= 2
        assert abs(layer.width - bw) <= 2
