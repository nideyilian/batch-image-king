"""输入校验：画布尺寸与非正图层尺寸。

两处曾经缺失的校验：

1. ``create_new(0, 0)`` 能成功 —— ``export_image`` 早有 16~32768 校验，
   但创建入口没有，非法尺寸一路流到导出才报错。校验放错了层。
2. ``add_layer(..., -50, -50)`` 被接受 —— Layer 构造走
   ``set_property(validate=False)``，负宽高直接写入，随后
   ``selectionBounds`` 算出 ``(x, y, -50, -50)``，QML 选中框变成负尺寸，
   命中测试返回 -1，图层静默「消失」。
"""

from __future__ import annotations

import pytest

from app.models.document import Document


@pytest.fixture(scope="module", autouse=True)
def _qt_app():
    from PySide6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    yield app


# ------------------------------------------------------------ 画布尺寸


@pytest.mark.parametrize("width,height", [(0, 0), (1, 1), (10, 10), (15, 15), (15, 600), (600, 15)])
def test_create_new_rejects_too_small(width, height):
    document = Document()
    with pytest.raises(ValueError, match="不能小于 16"):
        document.create_new(width, height)


@pytest.mark.parametrize("width,height", [(40000, 600), (600, 40000), (32769, 32769)])
def test_create_new_rejects_too_large(width, height):
    document = Document()
    with pytest.raises(ValueError, match="不能大于 32768"):
        document.create_new(width, height)


@pytest.mark.parametrize("width,height", [(16, 16), (1080, 1080), (32768, 16), (4000, 3000)])
def test_create_new_accepts_valid_range(width, height):
    document = Document()
    document.create_new(width, height)
    assert (document.canvas_width, document.canvas_height) == (width, height)


def test_create_new_over_limit_reports_limit_not_minimum():
    """超上限时必须报「大于 32768」，不能误报「小于 16」。"""
    document = Document()
    with pytest.raises(ValueError) as info:
        document.create_new(40000, 10)
    assert "大于 32768" in str(info.value)


# ------------------------------------------------------------ 图层尺寸


@pytest.mark.parametrize("width,height", [(-50, -50), (-1, 100), (100, -1), (0, 0)])
def test_add_layer_clamps_non_positive_size(width, height):
    document = Document()
    document.create_new(600, 600)
    document.add_layer("bad", 100, 100, width, height, is_folder=False)
    layer = document.layers[0]
    assert layer.width >= 1, f"宽度应被钳到 >= 1，实际 {layer.width}"
    assert layer.height >= 1, f"高度应被钳到 >= 1，实际 {layer.height}"


def test_selection_bounds_never_negative():
    """选中边界不能出现负宽高 —— 那会让 QML 选中框与手柄全部错位。"""
    from app.qml.preview_image_provider import PreviewImageProvider
    from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

    document = Document()
    document.create_new(600, 600)
    document.add_layer("bad", 100, 100, -50, -50, is_folder=False)
    workspace = WorkspaceViewModel(
        document=document, preview_provider=PreviewImageProvider(), auto_render=False
    )
    # 即使模型里被强改成负值（老项目文件、外部脚本），边界计算也要兜住
    layer = document.layers[0]
    layer._property_manager.set_property("width", -80, validate=False)
    layer._property_manager.set_property("height", -80, validate=False)

    assert workspace.selectionBoundsWidth >= 1
    assert workspace.selectionBoundsHeight >= 1


def test_layer_with_valid_size_is_untouched():
    """正常尺寸不能被改动。"""
    document = Document()
    document.create_new(600, 600)
    document.add_layer("ok", 50, 60, 320, 240, is_folder=False)
    layer = document.layers[0]
    assert (layer.x, layer.y, layer.width, layer.height) == (50, 60, 320, 240)


# ------------------------------------------------------------ 新建文档槽

def test_new_document_slot_rejects_invalid_without_crashing():
    """newDocument 槽必须挡住非法尺寸并给出提示，而不是让异常穿透成崩溃。"""
    from app.qml.preview_image_provider import PreviewImageProvider
    from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

    document = Document()
    document.create_new(500, 500)
    workspace = WorkspaceViewModel(
        document=document, preview_provider=PreviewImageProvider(), auto_render=False
    )

    for width, height in ((0, 0), (1, 1), (15, 15), (40000, 100), (-5, 100)):
        assert workspace.newDocument(width, height) is False, f"({width},{height}) 应被拒绝"
        # 失败时不能改动当前文档
        assert (workspace.canvasWidth, workspace.canvasHeight) == (500, 500)
        assert "16" in workspace.statusMessage or "尺寸" in workspace.statusMessage


def test_new_document_slot_accepts_valid():
    from app.qml.preview_image_provider import PreviewImageProvider
    from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

    document = Document()
    document.create_new(500, 500)
    workspace = WorkspaceViewModel(
        document=document, preview_provider=PreviewImageProvider(), auto_render=False
    )
    assert workspace.newDocument(1080, 1350) is True
    assert (workspace.canvasWidth, workspace.canvasHeight) == (1080, 1350)


def test_new_document_seeds_history_baseline():
    """新建文档应有一条基线快照，这样首个操作就能撤销。"""
    from app.qml.preview_image_provider import PreviewImageProvider
    from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel

    document = Document()
    document.create_new(500, 500)
    workspace = WorkspaceViewModel(
        document=document, preview_provider=PreviewImageProvider(), auto_render=False
    )
    workspace.newDocument(800, 600)
    history = workspace._document._history_manager._history
    assert len(history) == 1, f"新建后应恰好 1 条基线，实际 {len(history)} 条"
    assert not workspace._document.can_undo(), "只有基线时不应能撤销"
