"""预设卡片按钮必须真的能点。

回归背景：卡片底部按钮曾经"看得见、信号也绑好了"，但被整卡热区
（在文件末尾声明的 MouseArea）吞掉点击，表现为点了完全没反应。
用户报「批量等按钮无法点击」，而当时的检查只看视图模型方法返回值，
完全测不出来——所以这条必须用真实鼠标事件验证。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "helpers" / "preset_card_button_probe.py"


def _has_interactive_desktop() -> bool:
    """判断当前是否有可用桌面会话（能起 windows 平台）。

    CI（GitHub Actions Windows runner）是无头会话，`QT_QPA_PLATFORM=windows`
    无法创建窗口，探针进程直接非 0 退出——那不是「按钮点不动」，是环境不具备
    条件。必须跳过，否则 CI 会长期红着，掩盖真正的回归。
    """
    if sys.platform != "win32":
        return False
    # GitHub Actions 等无头环境会注入 CI=true，此时无法创建真实窗口
    if os.environ.get("CI", "").lower() in {"true", "1"}:
        return False
    return True


@pytest.mark.integration
def test_preset_card_buttons_are_clickable():
    """在真实窗口里点「打开」「批量」「收藏」「更多」，都必须有响应。

    用 windows 平台而非 offscreen：offscreen 下 mapToItem 坐标会偏，
    实测偏差 200+ 像素，会得到假失败（踩过一次）。
    """
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
        timeout=120,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, f"按钮点击探针失败（rc={result.returncode}）：\n{output}"
    assert "打开" in output and "OK" in output
    assert "FAIL" not in output, f"存在点不动的按钮：\n{output}"
