import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import Qt
from PySide6 import QtTest
from PySide6.QtWidgets import QApplication, QCheckBox, QSizePolicy, QStyle, QStyleOptionButton

from app.models.text_layer import TextLayer
from app.ui.integrated_text_panel import IntegratedTextPanel
from app.ui.property_panel_a2 import PropertyPanelA2

# 紧凑布局几何（v1.1.5「规整图层参数布局」）：卡片正文边距/间距、文字输入框高度
#
# ⚠ 2026-10-28：原来是 (8, 5, 8, 6) —— 垂直 5/6 不在 4px 栅格上，
# 叠上卡片 1px 边框后，嵌套子卡片的字段标签正好比顶层多缩进 7px，
# 串成 88 / 95 / 102 三个右边缘（肉眼看就是"齐了但没齐"）。
# 现在跟随 SUBPANEL_MARGINS（8,4,8,4），不再由测试锁死魔法数字 ——
# 测试锁的应该是「等于令牌」，而不是「等于我上次抄下来的数」。
COMPACT_BODY_MARGINS = PropertyPanelA2.SUBPANEL_MARGINS
COMPACT_BODY_SPACING = 4   # design_spec.Space.XS（原 5，不在 4px 栅格上）
COMPACT_TEXT_AREA_HEIGHT = 72


class IntegratedTextPanelA2UiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = IntegratedTextPanel()

    def tearDown(self):
        self.panel.deleteLater()

    def test_approved_sections_exist(self):
        self.assertEqual(self.panel.content_card_title.text(), "文字内容")
        self.assertEqual(self.panel.font_card_title.text(), "字体")
        self.assertEqual(self.panel.typography_card_title.text(), "排版")
        self.assertEqual(self.panel.appearance_card_title.text(), "外观")
        self.assertEqual(self.panel.background_card_title.text(), "文字背景")
        self.assertEqual(self.panel.effects_group.title_label.text(), "文字阴影与发光")
        self.assertEqual(self.panel.pos_group.title_label.text(), "位置和尺寸")

    def test_text_parameters_are_split_between_basic_and_more_tabs(self):
        self.assertEqual(self.panel.parameter_tabs.count(), 2)
        self.assertEqual(self.panel.parameter_tabs.tabText(0), "基本参数")
        self.assertEqual(self.panel.parameter_tabs.tabText(1), "更多参数")
        self.assertIs(self.panel.appearance_card.parentWidget(), self.panel.basic_tab_content)
        self.assertIs(self.panel.background_card.parentWidget(), self.panel.more_tab_content)
        self.assertIs(self.panel.effects_group.parentWidget(), self.panel.more_tab_content)
        # 紧凑布局：位置和尺寸移至基本参数页（integrated_text_panel.py:97）
        self.assertIs(self.panel.pos_group.parentWidget(), self.panel.basic_tab_content)

    def test_mode_buttons_and_visibility_helpers_exist(self):
        self.assertEqual(
            [button.text() for button in self.panel.text_fill_mode_buttons],
            ["无", "纯色", "渐变"],
        )
        self.assertEqual(
            [button.text() for button in self.panel.background_mode_buttons],
            ["无", "纯色", "渐变"],
        )
        self.assertTrue(hasattr(self.panel, "_sync_appearance_visibility"))
        self.assertTrue(hasattr(self.panel, "_sync_position_summary"))

    def test_position_controls_are_grouped_with_summary(self):
        self.assertTrue(hasattr(self.panel, "position_box"))
        self.assertTrue(hasattr(self.panel, "size_box"))
        self.panel.x_spin.setValue(50)
        self.panel.y_spin.setValue(51)
        self.panel.width_spin.setValue(106)
        self.panel.height_spin.setValue(34)
        self.panel._sync_position_summary()
        self.assertIn("X 50", self.panel.position_summary_label.text())
        self.assertEqual(self.panel.position_summary_label.text(), "X 50 · Y 51 · 106 × 34")

    def test_a_v2_cards_have_header_summaries(self):
        self.assertEqual(self.panel.content_summary_label.text(), "0 条 · 绑定模式开启")
        self.assertIn("24px", self.panel.font_summary_label.text())
        self.assertIn("左对齐", self.panel.typography_summary_label.text())
        self.assertIn("纯色文字", self.panel.appearance_summary_label.text())
        self.assertEqual(self.panel.background_summary_label.text(), "无背景")

    def test_a_v2_uses_compact_full_width_controls(self):
        self.assertTrue(all(
            button.sizePolicy().horizontalPolicy() == QSizePolicy.Expanding
            for button in self.panel.quick_font_buttons
        ))
        for button in (
            self.panel.font_settings_btn,
            self.panel.prev_text_btn,
            self.panel.next_text_btn,
            self.panel.random_text_btn,
        ):
            self.assertTrue(button.property("actionButton"))
            self.assertEqual(button.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
            self.assertEqual(button.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
        # 紧凑布局：描边开关为内联 QCheckBox（integrated_text_panel.py:784）
        self.assertEqual(self.panel.stroke_enable_check.text(), "描边")
        self.assertEqual(self.panel.stroke_enable_check.property("role"), "inlineCheck")
        self.assertTrue(self.panel.background_controls.isHidden())

    def test_a_v2_dimensions_follow_property_panel_spec(self):
        self.assertEqual(self.panel.layout().getContentsMargins(), (0, 0, 0, 0))
        self.assertEqual(self.panel.basic_layout.getContentsMargins(), (
            PropertyPanelA2.PANEL_MARGIN,
            PropertyPanelA2.PANEL_MARGIN,
            PropertyPanelA2.PANEL_MARGIN,
            PropertyPanelA2.PANEL_MARGIN,
        ))
        self.assertEqual(self.panel.more_layout.getContentsMargins(), self.panel.basic_layout.getContentsMargins())
        self.assertEqual(self.panel.basic_layout.spacing(), PropertyPanelA2.CARD_GAP)
        self.assertEqual(self.panel.more_layout.spacing(), PropertyPanelA2.CARD_GAP)

        for card in (
            self.panel.content_card,
            self.panel.font_card,
            self.panel.typography_card,
            self.panel.appearance_card,
            self.panel.background_card,
        ):
            self.assertEqual(card.header_frame.minimumHeight(), PropertyPanelA2.HEADER_HEIGHT)
            self.assertEqual(card.header_frame.maximumHeight(), PropertyPanelA2.HEADER_HEIGHT)
            self.assertEqual(card.body_layout.getContentsMargins(), COMPACT_BODY_MARGINS)
            self.assertEqual(card.body_layout.spacing(), COMPACT_BODY_SPACING)

        self.assertEqual(self.panel.inline_text_edit.minimumHeight(), COMPACT_TEXT_AREA_HEIGHT)
        self.assertEqual(self.panel.inline_text_edit.maximumHeight(), COMPACT_TEXT_AREA_HEIGHT)
        for button in self.panel.text_fill_mode_buttons + self.panel.background_mode_buttons:
            self.assertEqual(button.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
            self.assertEqual(button.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
        # 紧凑布局：描边为固定行高 QCheckBox（宽度自适应，不再使用 A2Switch 的 SWITCH_SIZE）
        self.assertEqual(self.panel.stroke_enable_check.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
        self.assertEqual(self.panel.stroke_enable_check.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)

    def test_typography_module_uses_a2_grid_and_segment_geometry(self):
        self.assertEqual(self.panel.typography_size_row.spacing(), PropertyPanelA2.ROW_GAP)
        self.assertEqual(self.panel.typography_align_row.spacing(), PropertyPanelA2.ROW_GAP)
        self.assertEqual(self.panel.align_group.layout().spacing(), PropertyPanelA2.SEGMENT_GAP)

        for button in (
            self.panel.align_group.left_btn,
            self.panel.align_group.center_btn,
            self.panel.align_group.right_btn,
        ):
            self.assertTrue(button.property("segmentButton"))
            self.assertEqual(button.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
            self.assertEqual(button.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
            self.assertEqual(button.minimumWidth(), PropertyPanelA2.ALIGN_BUTTON_MIN_WIDTH)
            self.assertGreater(button.maximumWidth(), PropertyPanelA2.ALIGN_BUTTON_MIN_WIDTH)
            self.assertEqual(button.sizePolicy().horizontalPolicy(), QSizePolicy.Expanding)

        self.assertEqual(self.panel.vertical_layout_check.property("role"), "inlineCheck")
        self.assertEqual(self.panel.vertical_layout_check.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
        self.assertEqual(self.panel.vertical_layout_check.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)

        for row in (self.panel.spacing_params_row, self.panel.text_box_params_row):
            self.assertEqual(row.property("role"), "parameterGrid")
            self.assertEqual(row.layout().getContentsMargins(), (0, 0, 0, 0))
            self.assertEqual(row.layout().horizontalSpacing(), PropertyPanelA2.ROW_GAP)
            self.assertEqual(row.layout().verticalSpacing(), PropertyPanelA2.ROW_GAP)

    def test_appearance_inner_panels_and_switch_follow_a2_spec(self):
        self.assertEqual(self.panel.text_color_controls.property("role"), "subPanel")
        self.assertEqual(self.panel.stroke_toggle_panel.property("role"), "subPanel")
        self.assertEqual(self.panel.stroke_controls.property("role"), "subPanel")
        self.assertEqual(self.panel.background_advanced_row.property("role"), "subPanel")

        # 紧凑布局：描边开关内联为 QCheckBox，独立开关面板/标题降级为隐藏占位（保持 handlers 兼容）
        self.assertEqual(self.panel.stroke_toggle_panel.minimumHeight(), 0)
        self.assertEqual(self.panel.stroke_title_label.text(), "")
        self.assertIsInstance(self.panel.stroke_enable_check, QCheckBox)
        self.assertEqual(self.panel.stroke_enable_check.property("role"), "inlineCheck")
        self.assertEqual(self.panel.stroke_enable_check.minimumHeight(), PropertyPanelA2.CONTROL_HEIGHT)
        self.assertEqual(self.panel.stroke_enable_check.maximumHeight(), PropertyPanelA2.CONTROL_HEIGHT)

        for swatch in (self.panel.text_color, self.panel.stroke_color, self.panel.bg_color):
            self.assertEqual(swatch.minimumWidth(), PropertyPanelA2.COLOR_SWATCH_SIZE)
            self.assertEqual(swatch.maximumWidth(), PropertyPanelA2.COLOR_SWATCH_SIZE)
            self.assertEqual(swatch.minimumHeight(), PropertyPanelA2.COLOR_SWATCH_SIZE)
            self.assertEqual(swatch.maximumHeight(), PropertyPanelA2.COLOR_SWATCH_SIZE)

    def test_stroke_switch_click_area_enables_stroke(self):
        layer = TextLayer()
        self.panel.set_text_layer(layer)
        switch = self.panel.stroke_enable_check
        # 紧凑布局为 QCheckBox：点击左侧勾选指示器区域切换描边
        option = QStyleOptionButton()
        option.initFrom(switch)
        indicator = switch.style().subElementRect(QStyle.SE_CheckBoxIndicator, option, switch)
        center = indicator.center()

        self.assertTrue(switch.hitButton(center))
        QtTest.QTest.mouseClick(switch, Qt.LeftButton, pos=center)
        QApplication.processEvents()

        self.assertTrue(switch.isChecked())
        self.assertTrue(layer.stroke_enabled)
        self.assertTrue(self.panel.stroke_width_spin.isEnabled())
        self.assertTrue(self.panel.stroke_color_button.isEnabled())


if __name__ == "__main__":
    unittest.main()
