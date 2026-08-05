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
            "--show-batch-export",
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

    qml_source = (repo_root / "app" / "qml" / "Main.qml").read_text(encoding="utf-8")
    assert 'objectName: "batchExportDrawer"' in qml_source
    assert 'text: batchExport.running ? "查看进度" : "批量导出"' in qml_source
    assert 'title: "内容源"' in qml_source
    assert 'title: "文字内容"' in qml_source
    assert 'tooltip: "添加素材文件夹"' in qml_source


@pytest.mark.integration
def test_qml_canvas_drag_updates_real_layer_geometry():
    repo_root = Path(__file__).resolve().parents[1]
    probe = repo_root / "tests" / "helpers" / "qml_canvas_interaction_probe.py"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"

    result = subprocess.run(
        [sys.executable, str(probe)],
        cwd=repo_root,
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    assert "dragged layer to" in result.stdout
