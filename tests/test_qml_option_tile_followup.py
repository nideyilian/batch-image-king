from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MAIN_QML = REPO_ROOT / "app" / "qml" / "Main.qml"


def _source() -> str:
    return MAIN_QML.read_text(encoding="utf-8")


@pytest.mark.unit
def test_canvas_resize_uses_three_exclusive_strategy_tiles():
    source = _source()
    start = source.index('id: canvasAdjustmentOptions')
    end = source.index('text: resizeCanvasDialog.errorMessage', start)
    block = source[start:end]

    assert block.count("OptionTile {") == 3
    assert block.count("exclusive: true") == 3
    assert 'title: "比例缩放"' in block
    assert 'title: "居中保留"' in block
    assert 'title: "左上保留"' in block
    assert "resizeCanvasDialog.adjustmentMode = 0" in block
    assert "resizeCanvasDialog.adjustmentMode = 1" in block
    assert "resizeCanvasDialog.adjustmentMode = 2" in block
    assert "SegmentedControl {" not in block
    assert "AppIcons.info" not in block


@pytest.mark.unit
def test_text_content_mode_uses_explicit_exclusive_tiles():
    source = _source()
    start = source.index('id: textContentModeOptions')
    end = source.index('BodyLabel { text: "文字内容"', start)
    block = source[start:end]

    assert 'property bool bindingEnabled: true' in source
    assert block.count("OptionTile {") == 2
    assert block.count("exclusive: true") == 2
    assert 'title: "按行随机"' in block
    assert 'title: "整段排版"' in block
    assert "textLayerDialog.bindingEnabled = true" in block
    assert "textLayerDialog.bindingEnabled = false" in block
    assert "bindingEnabled: textLayerDialog.bindingEnabled" in source
    assert "textLayerBindingInput" not in source


@pytest.mark.unit
def test_shaped_layer_dialog_uses_five_shape_tiles_and_dialog_state():
    source = _source()
    start = source.index('id: shapedLayerTypeOptions')
    end = source.index('BodyLabel { text: "位置与尺寸"', start)
    block = source[start:end]

    assert 'property string shapeType: "rectangle"' in source
    assert block.count("OptionTile {") == 5
    assert block.count("exclusive: true") == 5
    for value in ("rectangle", "right_trapezoid", "circle", "pentagon", "hexagon"):
        assert f'shapedLayerDialog.shapeType = "{value}"' in block
    assert "shapeType: shapedLayerDialog.shapeType" in source
    assert 'visible: shapedLayerDialog.shapeType === "right_trapezoid"' in source
    assert 'visible: shapedLayerDialog.shapeType === "pentagon" || shapedLayerDialog.shapeType === "hexagon"' in source
    assert "shapedLayerTypeInput" not in source


@pytest.mark.unit
def test_batch_quality_profile_uses_compact_two_by_two_tiles():
    source = _source()
    start = source.index('id: qualityStrategyGrid')
    end = source.index('id: performanceStrategyOptions', start)
    block = source[start:end]

    assert "columns: 2" in block
    assert block.count("OptionTile {") == 4
    assert block.count("compact: true") == 4
    assert block.count("exclusive: true") == 4
    for value in ("quality", "balanced", "speed", "size"):
        assert f'batchExport.qualityProfile = "{value}"' in block
    assert "SelectBox {" not in block
