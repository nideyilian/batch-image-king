"""预设删除后卡片必须消失（界面级回归）。

视图模型单测只能证明「信号发出去了」，证明不了「卡片真的没了」——
工作台的卡片网格绑的是 ``visiblePresets``（notify=viewChanged），
漏发信号时数据层一切正常、界面却原地不动。所以这里起真实 QML 窗口，
删一张卡片后检查工作台的 visibleItems 是否减少、选中态是否清空。
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "helpers" / "preset_delete_refresh_probe.py"


def _has_interactive_desktop() -> bool:
    if sys.platform != "win32":
        return False
    if os.environ.get("CI", "").lower() in {"true", "1"}:
        return False
    return True


@pytest.mark.integration
def test_deleting_preset_removes_card_from_workbench():
    """删卡片：卡片数要减 1，选中态要清空。"""
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
    assert result.returncode == 0, f"删除刷新探针失败（rc={result.returncode}）：\n{output}"
    assert "OK" in output


E2E_PROBE = REPO_ROOT / "tests" / "helpers" / "preset_delete_e2e_probe.py"


@pytest.mark.integration
def test_delete_from_card_goes_through_confirm_dialog():
    """走完整入口：卡片删除 → 确认弹窗 → 卡片消失、条目消失。

    这条覆盖 Main.qml 里的删除确认弹窗：只看视图模型或只看工作台组件，
    都发现不了「弹窗按钮绑错 id / 回调没接上」这类问题。
    """
    if not _has_interactive_desktop():
        pytest.skip("无交互桌面会话（如 CI 无头 runner），windows 平台起不来")

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "windows"

    result = subprocess.run(
        [sys.executable, str(E2E_PROBE)],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, f"删除链路探针失败（rc={result.returncode}）：\n{output}"
    assert "OK" in output
