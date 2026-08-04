from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest


@pytest.mark.integration
def test_qml_workbench_can_render_offscreen(tmp_path: Path):
    repo_root = Path(__file__).resolve().parents[1]
    launcher = repo_root / "app" / "qml" / "qml_main.py"
    screenshot = tmp_path / "qml-workbench.png"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"

    result = subprocess.run(
        [
            sys.executable,
            str(launcher),
            "--screenshot",
            str(screenshot),
            "--width",
            "1280",
            "--height",
            "760",
        ],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert screenshot.exists() and screenshot.stat().st_size > 20_000
    with Image.open(screenshot) as image:
        assert image.size == (1280, 760)
        assert image.getbbox() is not None
