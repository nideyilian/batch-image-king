import os
from pathlib import Path
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPoint, Qt, Signal
from PySide6.QtGui import QColor
from PySide6 import QtTest
from PySide6.QtWidgets import QApplication, QWidget

from app.ui.color_picker_dialog_a2 import ColorPickerDialogA2
from app.ui.dialog_a2 import DialogA2
from app.ui.font_picker_dialog_a2 import FontPickerDialogA2


class FakeFontSelector(QWidget):
    font_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_font = ""
        self.preview_text = ""

    def set_current_font(self, font_name):
        self.current_font = font_name

    def get_current_font(self):
        return self.current_font


class DialogA2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_dialog_a2_tokens_and_stylesheet_roles(self):
        self.assertEqual(DialogA2.OUTER_MARGIN, 20)
        self.assertEqual(DialogA2.CONTENT_GAP, 12)
        self.assertEqual(DialogA2.CONTROL_HEIGHT, 32)
        self.assertEqual(DialogA2.BUTTON_HEIGHT, 34)
        self.assertEqual(DialogA2.BUTTON_WIDTH, 80)
        self.assertEqual(DialogA2.CARD_RADIUS, 6)

        stylesheet = DialogA2.stylesheet()
        for selector in (
            'QDialog[dialogA2="true"]',
            'QFrame[role="dialogCard"]',
            'QFrame[role="dialogSubPanel"]',
            'QLabel[role="dialogTitle"]',
            'QLabel[role="sectionTitle"]',
            'QLabel[role="hint"]',
            'QPushButton[primaryButton="true"]',
            'QPushButton[secondaryButton="true"]',
        ):
            self.assertIn(selector, stylesheet)

    def test_color_picker_syncs_initial_rgb_alpha_and_hex(self):
        dialog = ColorPickerDialogA2(QColor(12, 34, 56, 128), title="选择文字颜色")

        self.assertEqual(dialog.property("dialogA2"), True)
        self.assertEqual(dialog.title_label.text(), "选择文字颜色")
        self.assertEqual(dialog.red_spin.value(), 12)
        self.assertEqual(dialog.green_spin.value(), 34)
        self.assertEqual(dialog.blue_spin.value(), 56)
        self.assertEqual(dialog.alpha_spin.value(), 128)
        self.assertEqual(dialog.hex_edit.text(), "#0c2238")
        self.assertTrue(hasattr(dialog, "color_field"))
        self.assertTrue(hasattr(dialog, "hue_strip"))
        self.assertEqual(dialog.current_preview._color, QColor(12, 34, 56, 128))
        self.assertEqual(dialog.ok_button.text(), "确定")
        self.assertEqual(dialog.cancel_button.text(), "取消")

    def test_color_picker_swatch_click_updates_selected_color(self):
        dialog = ColorPickerDialogA2(QColor(0, 0, 0, 255))
        swatch = dialog.swatch_buttons[1]
        expected = swatch.property("color")

        QtTest.QTest.mouseClick(swatch, Qt.LeftButton, pos=QPoint(6, 6))
        QApplication.processEvents()

        selected = dialog.selected_color()
        self.assertEqual((selected.red(), selected.green(), selected.blue()), (
            expected.red(), expected.green(), expected.blue()
        ))
        self.assertEqual(dialog.hex_edit.text(), expected.name())

    def test_color_picker_hex_edit_updates_selected_color(self):
        dialog = ColorPickerDialogA2(QColor(0, 0, 0, 255))

        dialog.hex_edit.setText("#336699")
        dialog.apply_hex_color()

        selected = dialog.selected_color()
        self.assertEqual((selected.red(), selected.green(), selected.blue()), (51, 102, 153))

    def test_color_picker_hsv_controls_update_rgb_and_new_preview(self):
        dialog = ColorPickerDialogA2(QColor(0, 0, 0, 255))

        dialog.hue_spin.setValue(120)
        dialog.saturation_spin.setValue(100)
        dialog.value_spin.setValue(100)
        QApplication.processEvents()

        selected = dialog.selected_color()
        self.assertEqual((selected.red(), selected.green(), selected.blue()), (0, 255, 0))
        self.assertEqual(dialog.new_preview._color, selected)

    def test_font_picker_wraps_existing_selector_in_dialog_a2_shell(self):
        dialog = FontPickerDialogA2(
            initial_font="Microsoft YaHei",
            preview_text="示例文字",
            selector_factory=FakeFontSelector,
        )

        self.assertEqual(dialog.property("dialogA2"), True)
        self.assertEqual(dialog.title_label.text(), "选择字体")
        self.assertIsInstance(dialog.selector, FakeFontSelector)
        self.assertEqual(dialog.selected_font(), "Microsoft YaHei")
        self.assertEqual(dialog.ok_button.text(), "确定")
        self.assertEqual(dialog.cancel_button.text(), "取消")

        dialog.selector.font_changed.emit("SimSun")
        self.assertEqual(dialog.selected_font(), "SimSun")

    def test_ui_code_uses_a2_color_picker_instead_of_native_qcolor_dialog(self):
        ui_dir = Path("app/ui")
        offenders = []
        for path in ui_dir.rglob("*.py"):
            if path.name == "color_picker_dialog_a2.py":
                continue
            text = path.read_text(encoding="utf-8")
            if "QColorDialog.getColor" in text:
                offenders.append(str(path))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
