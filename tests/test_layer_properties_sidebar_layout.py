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
    """侧栏颜色必须与全局令牌一致 —— 这才是本测试真正守护的东西。

    原版把 `#2F9CF4` / `#2A2A2A` 等具体色值写死，等于把「某个历史配色」
    固化成了契约。配色方向变更时（2026-10-27 选定 01 墨黑极简，
    主色 #2F9CF4 → #5E6AD2）这类断言会误报，但它想防的问题其实没发生。

    改为断言「侧栏令牌 == 全局令牌」，意图更准：
    只要有人让侧栏单独用一套色（历史漂移的根源），这条就会红。
    """
    # 侧栏颜色必须与全局令牌同源
    assert Tokens.SIDEBAR_COLOR_PRIMARY == Tokens.ACCENT
    assert Tokens.SIDEBAR_COLOR_SECONDARY == Tokens.BG_TERTIARY
    assert Tokens.SIDEBAR_COLOR_BACKGROUND == Tokens.BG_PRIMARY
    assert Tokens.SIDEBAR_COLOR_TEXT == Tokens.TEXT_PRIMARY

    # 颜色必须来自 tokens_v2（唯一事实来源），不允许是本文件自写的字面量
    from app.ui.tokens_v2 import Color

    assert Tokens.ACCENT == Color.accent
    assert Tokens.BG_PRIMARY == Color.surface_base
    assert Tokens.BG_TERTIARY == Color.surface_2
    assert Tokens.TEXT_PRIMARY == Color.text_primary

    # 排版与结构尺寸保持稳定（这部分与配色无关）
    assert Tokens.SIDEBAR_TITLE_FONT_SIZE == 14
    assert Tokens.SIDEBAR_BODY_FONT_SIZE == 13
    assert Tokens.SIDEBAR_PADDING == 12

    # 2026-10-28：圆角改为「必须在 design_spec.Radius 档位内」，
    # 不再锁死具体数字。原断言 `== 5` 把非档位值 5 固化了下来，
    # 而 design_spec 的档位是 4/6/8/12 —— 5 卡在 4 和 6 之间，
    # 既不对齐小控件也不对齐卡片。
    from app.ui.design_spec import Radius

    assert Tokens.CONTROL_RADIUS == Tokens.BUTTON_RADIUS, (
        "控件圆角与按钮圆角必须一致，否则同排元素视觉错位"
    )
    assert Tokens.CONTROL_RADIUS in Radius.ALL, (
        f"CONTROL_RADIUS={Tokens.CONTROL_RADIUS} 不在档位 {Radius.ALL} 内"
    )
    assert Tokens.SIDEBAR_SECTION_RADIUS == Tokens.SIDEBAR_NAV_RADIUS == 0
