from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys

from PIL import Image
import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_qml_export_sections_and_color_picker_debug_entry_exist():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    launcher_source = (REPO_ROOT / "app/qml/qml_main.py").read_text(encoding="utf-8")

    assert 'objectName: "effectColorDialog"' in qml_source
    assert "header: null" in qml_source
    assert 'text: "颜色区域"' in qml_source
    assert 'text: "HSV"' in qml_source
    assert 'text: "RGB"' in qml_source
    assert "component ExportSettingsSection" in qml_source
    for title in ("导出任务", "文件命名", "输出格式", "组合策略", "高级策略"):
        assert f'title: "{title}"' in qml_source

    assert '"--show-color-picker"' in launcher_source
    assert 'window.findChild(QObject, "effectColorDialog")' in launcher_source


@pytest.mark.unit
def test_batch_export_count_and_start_columns_stay_top_aligned():
    qml_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    start = qml_source.index('BodyLabel { text: "生成数量"')
    end = qml_source.index('title: "文件命名"', start)
    count_and_start_block = qml_source[start - 240 : end]

    assert "Layout.preferredWidth: 116" in count_and_start_block
    assert count_and_start_block.count("Layout.alignment: Qt.AlignTop") == 2


@pytest.mark.integration
def test_qml_color_picker_renders_without_native_white_header(tmp_path: Path):
    screenshot = tmp_path / "qml-color-picker.png"
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    env["QT_QUICK_BACKEND"] = "software"

    result = subprocess.run(
        [
            sys.executable,
            str(REPO_ROOT / "start_qml.py"),
            "--screenshot",
            str(screenshot),
            "--width",
            "1280",
            "--height",
            "760",
            "--show-color-picker",
        ],
        cwd=REPO_ROOT,
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
        red, green, blue = image.convert("RGB").getpixel((image.width // 2, 90))
        assert max(red, green, blue) < 80
