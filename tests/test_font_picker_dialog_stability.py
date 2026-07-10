from app.utils.print_utils import safe_print as print  # R7 契约统一：print -> 编码安全的 safe_print
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path


class FontPickerDialogStabilityTest(unittest.TestCase):
    def test_repeated_font_selection_does_not_crash(self):
        repo_root = Path(__file__).resolve().parents[1]
        script = textwrap.dedent(
            """
            import faulthandler
            import sys

            faulthandler.enable()

            from PySide6.QtWidgets import QApplication

            from app.ui.font_picker_dialog_a2 import FontPickerDialogA2

            app = QApplication.instance() or QApplication(sys.argv)
            dialog = FontPickerDialogA2(
                initial_font="Microsoft YaHei",
                preview_text="Font Preview AaBb123",
            )

            for font_name in ("Candara", "Candarab", "Candarai"):
                dialog.selector.set_current_font(font_name)
                app.processEvents()

            print("font-selection-ok")
            """
        )

        with tempfile.TemporaryDirectory() as home_dir:
            env = os.environ.copy()
            env["HOME"] = home_dir
            env["USERPROFILE"] = home_dir
            env["QT_QPA_PLATFORM"] = "offscreen"
            env["PYTHONUNBUFFERED"] = "1"

            result = subprocess.run(
                [sys.executable, "-X", "faulthandler", "-c", script],
                cwd=repo_root,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=30,
            )

        self.assertEqual(
            result.returncode,
            0,
            f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        self.assertIn("font-selection-ok", result.stdout)


if __name__ == "__main__":
    unittest.main()
