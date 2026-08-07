from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_qml_inspector_uses_basic_and_more_parameter_tabs():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert 'model: ["基本参数", "更多参数"]' in source
    for section_id in (
        "basicPropertiesSection",
        "imageSourceSection",
        "advancedSettingsSection",
        "shapeSection",
        "appearanceSection",
        "overlaySection",
        "cornerSection",
        "clonePropertiesSection",
        "layerTransformSection",
        "randomTransformSection",
    ):
        assert f"id: {section_id}" in source

    assert 'title: "内容源"' not in source
    assert 'title: "渐变叠加"' not in source
    assert 'model: ["属性", "效果"]' not in source
