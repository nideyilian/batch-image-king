"""分类（左侧文件夹）新建/重命名/删除入口的界面级回归。

单测能证明「数据变了」，证明不了「用户点得到」：
  · 新建分类后侧栏是否立刻出现（绑定在 vm.categories）；
  · 悬停分类行，铅笔/垃圾桶是否露出来；
  · 点下去是否真的接到信号（整行 MouseArea 曾经盖住这两个按钮）。

所以这里起真实 QML 窗口 + 真实鼠标事件验证。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "helpers" / "preset_category_ui_probe.py"


def _has_interactive_desktop() -> bool:
    if sys.platform != "win32":
        return False
    if os.environ.get("CI", "").lower() in {"true", "1"}:
        return False
    return True


@pytest.mark.integration
def test_category_create_hover_and_row_actions_work():
    """新建即时出现、悬停露出按钮、点击进入重命名/删除确认。"""
    if not _has_interactive_desktop():
        pytest.skip("无交互桌面会话（如 CI 无头 runner），windows 平台起不来")

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "windows"

    result = subprocess.run(
        [sys.executable, str(PROBE)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, f"分类界面探针失败（rc={result.returncode}）：\n{output}"
    assert "OK" in output
