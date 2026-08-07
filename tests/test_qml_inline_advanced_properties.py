from __future__ import annotations

from pathlib import Path

import pytest

from app.models.document import Document
from app.qml.preview_image_provider import PreviewImageProvider
from app.qml.viewmodels.workspace_view_model import WorkspaceViewModel


def _workspace() -> WorkspaceViewModel:
    document = Document()
    document.create_new(640, 480)
    document._history_manager.clear()
    workspace = WorkspaceViewModel(
        document=document,
        preview_provider=PreviewImageProvider(),
        auto_render=False,
    )
    assert workspace.addEmptyImageLayer() is True
    return workspace


@pytest.mark.unit
def test_clone_and_fill_properties_are_editable_from_qml_view_model():
    workspace = _workspace()
    layer = workspace.document.layers[0]

    assert workspace.selectedSupportsClone is True
    assert workspace.setSelectedCloneEnabled(True) is True
    assert (layer.clone_rows, layer.clone_columns) == (2, 2)
    assert workspace.setSelectedCloneRows(3) is True
    assert workspace.setSelectedCloneColumns(4) is True
    assert workspace.setSelectedCloneRowSpacing(18) is True
    assert workspace.setSelectedCloneColumnSpacing(24) is True
    assert workspace.setSelectedCloneMirrorMode("horizontal") is True
    assert workspace.setSelectedCloneCustomSizeEnabled(True) is True
    assert (layer.clone_custom_width, layer.clone_custom_height) == (200, 200)
    assert workspace.setSelectedCloneCustomWidth(96) is True
    assert workspace.setSelectedCloneCustomHeight(72) is True
    assert workspace.selectedCloneLayoutMode == "fixed"
    assert workspace.setSelectedCloneLayoutMode("fill") is True
    assert workspace.setSelectedCloneFillMode("staggered") is True
    assert workspace.setSelectedCloneFillSpacing(12) is True
    assert workspace.setSelectedCloneFillMargin(30) is True
    assert workspace.setSelectedCloneFillAngle(22.5) is True

    assert workspace.selectedCloneEnabled is True
    assert (workspace.selectedCloneRows, workspace.selectedCloneColumns) == (3, 4)
    assert (workspace.selectedCloneRowSpacing, workspace.selectedCloneColumnSpacing) == (18, 24)
    assert workspace.selectedCloneMirrorMode == "horizontal"
    assert workspace.selectedCloneCustomSizeEnabled is True
    assert (workspace.selectedCloneCustomWidth, workspace.selectedCloneCustomHeight) == (96, 72)
    assert workspace.selectedCloneFillEnabled is True
    assert workspace.selectedCloneLayoutMode == "fill"
    assert workspace.selectedCloneFillMode == "staggered"
    assert workspace.selectedCloneFillSpacing == 12
    assert workspace.selectedCloneFillMargin == 30
    assert workspace.selectedCloneFillAngle == pytest.approx(22.5)
    assert workspace.setSelectedCloneFillEnabled(False) is True
    assert workspace.selectedCloneLayoutMode == "fixed"
    assert workspace.setSelectedCloneLayoutMode("unknown") is False


@pytest.mark.unit
def test_vector_corner_and_advanced_stroke_properties_are_editable_inline():
    workspace = _workspace()
    layer = workspace.document.layers[0]

    assert workspace.selectedSupportsAdvancedStroke is True
    assert workspace.setSelectedStrokeType(2) is True
    assert workspace.setSelectedStrokeJoin("round") is True
    assert workspace.setSelectedStrokeCap("square") is True
    assert workspace.setSelectedStrokeDash(16, 7) is True
    assert workspace.selectedCornerMode == "uniform"
    assert workspace.setSelectedCornerMode("independent") is True
    assert workspace.setSelectedVectorCornerRadii(4, 8, 12, 16) is True

    assert workspace.selectedStrokeType == 2
    assert workspace.selectedStrokeJoin == "round"
    assert workspace.selectedStrokeCap == "square"
    assert (workspace.selectedStrokeDashLength, workspace.selectedStrokeDashGap) == (16, 7)
    assert workspace.selectedVectorCornerRadii == [4, 8, 12, 16]
    assert workspace.selectedCornerMode == "independent"
    assert layer.corner_radius == 16

    assert workspace.setSelectedCornerMode("uniform") is True
    assert workspace.selectedCornerMode == "uniform"
    assert workspace.selectedVectorCornerRadii == [0, 0, 0, 0]
    assert workspace.selectedCornerRadius == 16

    assert workspace.setSelectedVectorCornerRadiusAll(20) is True
    assert workspace.selectedVectorCornerRadii == [20, 20, 20, 20]
    assert workspace.selectedCornerMode == "independent"


@pytest.mark.unit
def test_transparent_bounds_trim_remains_compatible_with_legacy_field():
    workspace = _workspace()
    layer = workspace.document.layers[0]

    assert workspace.selectedUseOriginalSize is False
    assert workspace.selectedTrimTransparentBoundsEnabled is False
    assert workspace.setSelectedTrimTransparentBoundsEnabled(True) is True
    assert layer.use_original_size is True
    assert workspace.selectedUseOriginalSize is True
    assert workspace.setSelectedUseOriginalSize(False) is True
    assert workspace.selectedTrimTransparentBoundsEnabled is False


@pytest.mark.unit
def test_qml_advanced_properties_are_inline_and_never_open_legacy_popup():
    repo_root = Path(__file__).resolve().parents[1]
    qml_source = (repo_root / "app" / "qml" / "Main.qml").read_text(encoding="utf-8")
    bridge_source = (repo_root / "app" / "qml" / "legacy_feature_bridge.py").read_text(
        encoding="utf-8"
    )

    assert "legacyTools.openAdvancedLayerProperties()" not in qml_source
    assert "def openAdvancedLayerProperties" not in bridge_source
    assert "function revealAdvancedProperties()" in qml_source
    assert 'objectName: "clonePropertiesSection"' in qml_source
    assert 'objectName: "advancedStrokeSection"' in qml_source
    assert "workspace.setSelectedCloneEnabled" in qml_source
    assert "workspace.setSelectedCloneLayoutMode" in qml_source
    assert "workspace.setSelectedOverlayMode" in qml_source
    assert "workspace.setSelectedTrimTransparentBoundsEnabled" in qml_source
    assert "workspace.setSelectedCornerMode" in qml_source
    assert "workspace.setSelectedVectorCornerRadii" in qml_source
    assert "workspace.setSelectedStrokeDash" in qml_source
