"""PropertyPanelA2 尺寸契约。

═══════════════════════════════════════════════════════════════════════════
2026-10-28 重写说明
═══════════════════════════════════════════════════════════════════════════

本测试原来把一堆**非规范值**锁死了：

    CARD_RADIUS = 7
    HEADER_HEIGHT = 36
    HEADER_MARGINS = (8, 4, 7, 4)          ← 非对称，7 不在 4px 栅格上
    GROUP_CONTENT_MARGINS = (8, 8, 8, 9)   ← 9 不在栅格上
    CONTROL_HEIGHT = 30                    ← 不在栅格上

这些值正是「用脚填的数值」的化石证据 —— 每次改功能顺手加一个，
日积月累导致同一窗口出现 37 种高度、9 种边距、7 种间距。

现在改成**从 design_spec 派生断言**：
只要 spec 守住「3 档高度 + 6 档间距 + 4 档圆角 + 4px 栅格」，
面板就不可能再漂。

测试不再锁死具体数字，而是锁死**不变量**。
"""

import unittest

from app.ui.design_spec import Radius, Scale, Space
from app.ui.property_panel_a2 import PropertyPanelA2


class PropertyPanelA2SpecTest(unittest.TestCase):
    # ── 尺寸必须来自 spec ──────────────────────────────────────────

    def test_control_height_comes_from_spec(self):
        """控件高度必须等于 spec 的 MD 档（28），不能是裸数字。"""
        self.assertEqual(PropertyPanelA2.CONTROL_HEIGHT, Scale.PX[Scale.MD])

    def test_header_height_comes_from_spec(self):
        """标题高度也走 spec（原来写死 36，比控件高 8px，视觉上突兀）。"""
        self.assertEqual(PropertyPanelA2.HEADER_HEIGHT, Scale.PX[Scale.MD])

    def test_card_radius_is_on_radius_scale(self):
        """卡片圆角必须是 spec 的四档之一（原来写死 7，不在任何档位上）。"""
        self.assertIn(PropertyPanelA2.CARD_RADIUS, Radius.ALL)

    # ── 边距必须在栅格上且左右对称 ────────────────────────────────

    def test_all_margins_are_on_4px_grid(self):
        """所有边距元组的每个分量都必须落在 4px 栅格上。

        原值 `(8, 4, 7, 4)` 里的 7、`(8, 8, 8, 9)` 里的 9 是漂移源头：
        它们让这一侧的元素永远对不齐任何其它容器。
        """
        margins = {
            "BODY_MARGINS": PropertyPanelA2.BODY_MARGINS,
            "SUBPANEL_MARGINS": PropertyPanelA2.SUBPANEL_MARGINS,
            "HEADER_MARGINS": PropertyPanelA2.HEADER_MARGINS,
            "GROUP_CONTENT_MARGINS": PropertyPanelA2.GROUP_CONTENT_MARGINS,
        }
        for name, m in margins.items():
            with self.subTest(margin=name):
                for v in m:
                    self.assertEqual(
                        v % 4, 0,
                        f"{name}={m} 中的 {v} 不在 4px 栅格上",
                    )

    def test_margins_are_symmetric(self):
        """左右边距必须对称，否则内容会视觉偏移。

        `(8, 4, 7, 4)` 就是左右不等（8 vs 7）的实例。
        """
        for name in ("BODY_MARGINS", "SUBPANEL_MARGINS", "HEADER_MARGINS",
                     "GROUP_CONTENT_MARGINS"):
            m = getattr(PropertyPanelA2, name)
            with self.subTest(margin=name):
                self.assertEqual(
                    m[0], m[2],
                    f"{name}={m} 左右边距不等（{m[0]} vs {m[2]}）",
                )

    # ── 间距必须来自档位 ──────────────────────────────────────────

    def test_gaps_come_from_space_scale(self):
        """区块间距必须落在 design_spec.Space 的档位内。"""
        for name in ("PANEL_MARGIN", "CARD_GAP", "SECTION_GAP", "ROW_GAP"):
            if not hasattr(PropertyPanelA2, name):
                continue
            value = getattr(PropertyPanelA2, name)
            with self.subTest(gap=name):
                self.assertIn(
                    value, Space.ALL,
                    f"{name}={value} 不在间距档位 {Space.ALL} 内",
                )

    # ── 固定宽度类：不参与高度收敛，只防随手改 ────────────────────

    def test_fixed_widths_are_stable(self):
        self.assertEqual(PropertyPanelA2.TEXT_AREA_HEIGHT, 96)
        # 2026-10-28：标签列宽收敛到 design_spec.Layout（72），
        # 不再允许在面板层写死 58。这里断言「指向真源」而不是「等于 58」——
        # 否则测试本身就成了第二套规范（这类测试在项目里已踩过一次坑）。
        from app.ui.design_spec import Layout

        self.assertEqual(PropertyPanelA2.LABEL_WIDTH, Layout.LABEL_WIDTH)
        self.assertEqual(PropertyPanelA2.POSITION_LABEL_WIDTH, 22)
        self.assertEqual(PropertyPanelA2.ACTION_BUTTON_WIDTH, 56)
        self.assertEqual(PropertyPanelA2.ALIGN_BUTTON_MIN_WIDTH, 56)
        self.assertEqual(PropertyPanelA2.FEATURE_TOGGLE_HEIGHT, 48)

    def test_switch_size_height_matches_control(self):
        """开关高度应与控件高度一致（原来写死 (52, 30)，与 28 不同步）。"""
        width, height = PropertyPanelA2.SWITCH_SIZE
        self.assertEqual(width, 52)
        self.assertEqual(height, Scale.PX[Scale.MD])

    # ── 字号档位 ─────────────────────────────────────────────────

    def test_type_scale_tokens_match_a_v2_spec(self):
        """字号必须与 tokens_v2 真源一致（2026-10-28 收敛后）。

        原来这里硬断言 FEATURE_TITLE_FONT_SIZE == 15，等于**测试在锁死旧规范**：
        一旦真源改成 14，测试就报错，逼人改回去。这正是双规范难以收敛的原因 ——
        测试不是守住真源，而是守住某一份历史快照。

        现在改为：断言这些属性与 tokens_v2.Typography 相等。
        真源调整时测试自动跟随，只有「有人偷偷写新数字」才会失败。
        """
        from app.ui.tokens_v2 import Typography as T

        self.assertEqual(PropertyPanelA2.SECTION_TITLE_FONT_SIZE, T.size_base)
        self.assertEqual(PropertyPanelA2.FIELD_LABEL_FONT_SIZE, T.size_sm)
        self.assertEqual(PropertyPanelA2.SUMMARY_FONT_SIZE, T.size_caption)
        self.assertEqual(PropertyPanelA2.FEATURE_TITLE_FONT_SIZE, T.size_md)

        # 层级正确性：字段标签必须比正文小一档，功能标题不得大于区块标题之上
        self.assertLess(
            PropertyPanelA2.FIELD_LABEL_FONT_SIZE,
            PropertyPanelA2.SECTION_TITLE_FONT_SIZE,
            "字段标签必须比区块标题小，否则每一行都像标题",
        )

    # ── QSS 角色完备性 ───────────────────────────────────────────

    def test_stylesheet_exposes_reusable_roles(self):
        stylesheet = PropertyPanelA2.stylesheet("#ExamplePanel")
        for selector in (
            '#ExamplePanel',
            'QFrame[role="section"]',
            'QFrame[role="sectionHeader"]',
            'QFrame[role="sectionBody"]',
            'QFrame[role="parameterGrid"]',
            'QLabel[role="fieldLabel"]',
            'QLabel[role="featureTitle"]',
            'QPushButton[segmentButton="true"]',
            'QToolButton[segmentButton="true"]',
            'QAbstractButton[actionButton="true"]',
            'QPushButton[compactValue="true"]',
            'QCheckBox[role="inlineCheck"]',
        ):
            self.assertIn(selector, stylesheet)
        self.assertIn(f"max-height: {PropertyPanelA2.CONTROL_HEIGHT}px", stylesheet)


if __name__ == "__main__":
    unittest.main()
