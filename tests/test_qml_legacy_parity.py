"""新版 QML 界面与旧版（Qt Widgets）功能对齐的契约测试。

背景（2026-10-28）：项目有两套界面，旧版 `app/ui` + 新版 `app/qml`。
杰哥的要求是「新版功能跟旧版完全一致（除 AI 生图）」。

这类「一致」不能靠肉眼审，必须钉成测试 —— 否则下次谁改一版就悄悄丢了。
本文件只覆盖**已确认存在差异并已修复**的几项：

1. 单选图层对齐到画板（旧版对齐工具栏 10 个按钮单选时全部可用）
2. 快速文字图层 T（旧版一键建层，不弹窗）
3. 新建文字层必须 auto_fit_text_box=True（否则大字号被 300x100 的框裁字）
"""

from __future__ import annotations

from typing import Optional

import pytest

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace(document: Optional[Document] = None, *, width: int = 800, height: int = 600):
    if document is None:
        document = Document()
        document.create_new(width, height)
    return WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )


# ═══════════════════════════════════════════════════════════════════════════
# 1. 单选对齐到画板
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_single_layer_aligns_to_canvas_not_to_itself():
    """单选时对齐的参照物是**画板**，不是图层自己。

    旧版 app/ui/layer_panel_align.py::align_layers 在 `len(selected) <= 1` 时
    走「对齐到画板」分支；早期 QML 在 len<2 时直接 return False，
    导致单选时整组对齐按钮点了没反应（工具栏置灰 / 右键菜单 disabled）。
    """
    workspace = _workspace(width=800, height=600)
    workspace.addTextLayer()
    workspace.selectLayer(workspace.selectedLayerIndex)
    layer = workspace.document.layers[workspace.selectedLayerIndex]
    layer.x, layer.y = 123, 456

    assert workspace.alignSelected("left") is True
    assert layer.x == 0, f"左对齐到画板应把 x 归零，实际 {layer.x}"

    layer.x, layer.y = 123, 456
    assert workspace.alignSelected("top") is True
    assert layer.y == 0, f"顶对齐到画板应把 y 归零，实际 {layer.y}"

    assert workspace.alignSelected("right") is True
    assert layer.x == 800 - layer.width

    assert workspace.alignSelected("bottom") is True
    assert layer.y == 600 - layer.height

    assert workspace.alignSelected("hcenter") is True
    assert layer.x == (800 - layer.width) // 2

    assert workspace.alignSelected("vcenter") is True
    assert layer.y == (600 - layer.height) // 2

    assert workspace.alignSelected("center") is True
    assert (layer.x, layer.y) == ((800 - layer.width) // 2, (600 - layer.height) // 2)

    assert workspace.alignSelected("same_size") is True
    assert (layer.x, layer.y) == (0, 0)
    assert (layer.width, layer.height) == (800, 600)


@pytest.mark.unit
def test_single_layer_same_size_respects_original_size_flag():
    """勾了「使用原始尺寸」时不允许匹配画板 —— 与旧版同一判断。"""
    workspace = _workspace()
    workspace.addTextLayer()
    layer = workspace.document.layers[workspace.selectedLayerIndex]
    layer.use_original_size = True
    before = (layer.width, layer.height)

    assert workspace.alignSelected("same_size") is False
    assert (layer.width, layer.height) == before


@pytest.mark.unit
def test_single_layer_align_uses_clone_bounds():
    """开了分身之后，对齐要按整体包围盒算，不能只看主矩形。

    否则会出现「主体贴边、分身出界」——旧版为此专门写了分身分支。
    用图片图层测：分身在 ImageLayer 上，TextLayer 没有分身接口。
    """
    workspace = _workspace(width=800, height=600)
    layer = workspace.document.add_layer("分身测试", 100, 100, 100, 100)
    if layer is None:
        pytest.skip("当前文档模型不能创建图片图层")
    workspace.selectLayer(workspace.document.layers.index(layer))
    layer.clone_enabled = True
    layer.clone_rows = 2
    layer.clone_columns = 2

    getter = getattr(layer, "get_effective_clone_positions", None) or getattr(
        layer, "get_clone_positions", None
    )
    if not callable(getter):
        pytest.skip("当前图层模型没有分身位置接口")
    if not getter():
        pytest.skip("分身位置未生效，跳过包围盒断言")

    assert workspace.alignSelected("left") is True
    min_x, _min_y, _w, _h = workspace._layer_alignment_bounds(layer)
    assert min_x == 0, f"对齐后整体包围盒左边缘应为 0，实际 {min_x}"


@pytest.mark.unit
def test_multi_layer_align_still_references_primary_layer():
    """多选对齐保持旧版语义：以首选图层为基准，而不是画板。

    这条防的是「修单选时顺手把多选也改成对画板」这类回归。
    """
    workspace = _workspace(width=800, height=600)
    document = workspace.document
    document.add_text_layer(_text_layer("参考", x=200, y=150, width=100, height=50))
    document.add_text_layer(_text_layer("跟随", x=500, y=400, width=60, height=30))
    # 图层顺序是「后加的在前」，所以按名字找索引，不要假设 0 是参考层
    ref_index = next(i for i, l in enumerate(document.layers) if l.name == "参考")
    follower_index = next(i for i, l in enumerate(document.layers) if l.name == "跟随")
    workspace.selectLayer(follower_index)
    workspace.selectLayerWithModifiers(ref_index, True, False)
    assert workspace.selectedLayerIndex == ref_index, "主选图层应为「参考」"

    assert workspace.alignSelectedLayers("left") is True
    reference = document.layers[ref_index]
    follower = document.layers[follower_index]
    assert follower.x == reference.x, (
        f"多选左对齐应以主选图层 x={reference.x} 为基准，实际 {follower.x}"
    )
    assert reference.x == 200, "基准图层本身不应被移动"
    assert reference.y == 150, "左对齐不应改动 y"


@pytest.mark.unit
def test_align_selected_layers_returns_false_for_single_selection():
    """`alignSelectedLayers` 只管多选；单选由 alignSelected 负责。

    两个入口分工明确，避免「同一操作两套实现、结果不一样」。
    """
    workspace = _workspace()
    workspace.addTextLayer()
    assert workspace.alignSelectedLayers("left") is False


# ═══════════════════════════════════════════════════════════════════════════
# 2. 快速文字图层
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_quick_text_layer_matches_legacy_defaults():
    """快速建层的默认值必须与旧版 layer_controller.add_quick_text_layer 一致。

    旧版规则：内容「双击编辑文字」、白色、字号=画布高/12（夹 24~160）、
    位置=画布 6% 留白、auto_fit_text_box 开启。
    """
    workspace = _workspace(width=800, height=600)
    assert workspace.addQuickTextLayer() is True

    layer = workspace.document.layers[workspace.selectedLayerIndex]
    assert layer.name == "双击编辑文字"
    assert layer.font_size == 50, f"600 高画布字号应为 600/12=50，实际 {layer.font_size}"
    assert (layer.x, layer.y) == (48, 36), (
        f"位置应为画布 6% 留白 (48,36)，实际 ({layer.x},{layer.y})"
    )
    assert layer.auto_fit_text_box is True, "必须开自动适配，否则大字号被 300x100 的框裁掉"
    assert layer.text_binding_enabled is True


@pytest.mark.unit
def test_quick_text_layer_font_scales_with_canvas():
    """字号跟画布高度走：1080 高应为 90px，而不是固定 48。"""
    workspace = _workspace(width=1920, height=1080)
    assert workspace.addQuickTextLayer() is True
    layer = workspace.document.layers[workspace.selectedLayerIndex]
    assert layer.font_size == 90, f"1080 高画布字号应为 1080/12=90，实际 {layer.font_size}"


@pytest.mark.unit
def test_quick_text_layer_names_are_unique():
    """连按 T 建多层时名字要能区分，否则图层面板里一堆同名。"""
    workspace = _workspace()
    for _ in range(3):
        assert workspace.addQuickTextLayer() is True
    names = [layer.name for layer in workspace.document.layers]
    assert len(names) == len(set(names)), f"图层名重复：{names}"
    assert "双击编辑文字" in names
    assert "双击编辑文字 2" in names


# ═══════════════════════════════════════════════════════════════════════════
# 3. 文字层文本框
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.unit
def test_configured_text_layer_enables_auto_fit():
    """配置化建层也必须开自动适配。

    旧版 add_configured_text_layer 对此有明确注释：关掉时 72px 的
    「限时特惠 5折」只渲染出「限时特惠」，「5折」整段丢失。
    QML 侧曾写成 False —— 同一个坑。
    """
    workspace = _workspace()
    assert (
        workspace.addConfiguredTextLayer(
            {
                "name": "测试层",
                "content": "限时特惠 5折",
                "fontFamily": "Microsoft YaHei",
                "fontSize": 72,
                "alignment": "left",
                "color": "#FFFFFF",
            }
        )
        is True
    )
    layer = workspace.document.layers[workspace.selectedLayerIndex]
    assert layer.auto_fit_text_box is True


def _text_layer(name: str, *, x=0, y=0, width=100, height=50):
    from app.models.text_layer import TextLayer

    layer = TextLayer(name=name, x=x, y=y, width=width, height=height)
    layer.current_text = name
    layer.auto_fit_text_box = False
    return layer
