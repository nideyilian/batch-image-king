from __future__ import annotations

import re
from pathlib import Path

import pytest


@pytest.mark.unit
def test_repeated_visible_commands_have_one_button_entry() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "app" / "qml" / "Main.qml").read_text(encoding="utf-8")

    # Menus and shortcuts remain available, but each command has one visible button.
    assert source.count("onClicked: workspace.addEmptyImageLayer()") == 1
    assert 'tooltip: "新建空图片图层"' not in source
    assert "onClicked: window.revealAdvancedProperties()" not in source
    assert 'tooltip: "打开更多参数"' not in source
    assert source.count('tooltip: "解散图层组"') == 1
    assert 'label: "组状态"' not in source
    assert 'label: "文字工具 (T)"' not in source
    assert 'label: "形状工具 (U)"' not in source


@pytest.mark.unit
def test_empty_workspace_owns_new_and_open_buttons() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    source = (repo_root / "app" / "qml" / "Main.qml").read_text(encoding="utf-8")

    assert "iconName: AppIcons.fileNew" not in source

    open_command = re.search(
        r"IconButton\s*\{\s*iconName:\s*AppIcons\.folderOpen"
        r"[^}]*visible:\s*window\.hasOpenDocument[^}]*\}",
        source,
    )
    assert open_command is not None

    new_tab_command = re.search(
        r"IconButton\s*\{\s*iconName:\s*AppIcons\.add"
        r"[^}]*tooltip:\s*\"新建文档\""
        r"[^}]*visible:\s*window\.hasOpenDocument[^}]*\}",
        source,
    )
    assert new_tab_command is not None

    assert 'label: "新建画布"' in source
    assert 'label: "打开项目"' in source
