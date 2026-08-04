import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QGroupBox

from app.ui.design_tokens import Tokens
from app.ui.layer_properties import LayerPropertiesPanel
from app.ui.property_widgets import PropertySection


@pytest.mark.integration
def test_layer_properties_uses_two_flat_sidebar_tabs(qapp):
    panel = LayerPropertiesPanel(None)
    try:
        assert panel.property_tabs.count() == 2
        assert [panel.property_tabs.tabText(i) for i in range(2)] == ["基本参数", "更多参数"]

        basic_sections = [
            panel.basic_group,
            panel.source_group,
            panel.advanced_group,
            panel.shape_group,
            panel.appearance_group,
        ]
        more_sections = [
            panel.ai_generation_group,
            panel.clone_group,
            panel.transform_group,
            panel.random_transform_group,
        ]

        assert all(isinstance(section, PropertySection) for section in basic_sections + more_sections)
        assert all(section.parent() is panel.basic_tab_content for section in basic_sections)
        assert all(section.parent() is panel.more_tab_content for section in more_sections)
        assert all(not hasattr(section, "toggle_button") for section in basic_sections + more_sections)
        assert all(not section.content_container.isHidden() for section in basic_sections + more_sections)
    finally:
        panel.deleteLater()


@pytest.mark.integration
def test_sidebar_reflows_without_nested_transform_cards(qapp):
    panel = LayerPropertiesPanel(None)
    try:
        panel.resize(240, 720)
        panel.show()
        qapp.processEvents()

        assert panel.property_tabs.width() >= Tokens.SIDEBAR_MIN_WIDTH
        assert panel.basic_scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
        assert panel.more_scroll_area.horizontalScrollBarPolicy() == Qt.ScrollBarAlwaysOff
        assert panel.transform_widget.findChildren(QGroupBox) == []
        assert panel.random_transform_widget.findChildren(QGroupBox) == []
        assert panel.property_tabs.tabBar().usesScrollButtons() is False
    finally:
        panel.close()
        panel.deleteLater()


@pytest.mark.unit
def test_sidebar_design_tokens_are_explicit_and_consistent():
    assert Tokens.ACCENT == "#2F9CF4"
    assert Tokens.BG_TERTIARY == "#2A2A2A"
    assert Tokens.BG_PRIMARY == "#181818"
    assert Tokens.TEXT_PRIMARY == "#F4F4F5"
    assert Tokens.SIDEBAR_COLOR_PRIMARY == "#2F9CF4"
    assert Tokens.SIDEBAR_COLOR_SECONDARY == "#2A2A2A"
    assert Tokens.SIDEBAR_COLOR_BACKGROUND == "#181818"
    assert Tokens.SIDEBAR_COLOR_TEXT == "#F4F4F5"
    assert Tokens.SIDEBAR_TITLE_FONT_SIZE == 14
    assert Tokens.SIDEBAR_BODY_FONT_SIZE == 13
    assert Tokens.SIDEBAR_PADDING == 12
    assert Tokens.CONTROL_RADIUS == Tokens.BUTTON_RADIUS == 5
    assert Tokens.SIDEBAR_SECTION_RADIUS == Tokens.SIDEBAR_NAV_RADIUS == 0
