"""标签页双击重命名 + 右键基础编辑。

回归背景：`onDoubleClicked` 绑好了不等于双击真的能打开重命名框——
热区可能被兄弟 MouseArea 吃掉、或者双击到的是后台标签。这类问题只看源码
和视图模型返回值都发现不了，必须发真实鼠标事件（见 tests/helpers/tab_rename_probe.py）。

探针实测覆盖：
1. 双击标签 → 重命名框打开（visible=True）
2. 双击前该标签被激活（activeIndex 从别的值切到被双击的那个）
3. 重命名框带出原标题
4. 右键能弹出菜单（「复制标签页」与「复制图层」共存，见静态契约）
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
PROBE = REPO_ROOT / "tests" / "helpers" / "tab_rename_probe.py"


def _has_interactive_desktop() -> bool:
    """无头会话（CI）起不来 windows 平台，跳过而不是让测试长期红着。"""
    if sys.platform != "win32":
        return False
    if os.environ.get("CI", "").lower() in {"true", "1"}:
        return False
    return True


@pytest.mark.integration
def test_tab_double_click_opens_rename_and_activates_tab():
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
        timeout=150,
        check=False,
    )

    output = result.stdout + result.stderr
    assert result.returncode == 0, f"双击重命名探针失败（rc={result.returncode}）：\n{output}"
    assert "[OK] 双击打开重命名框" in output, output
    assert "[OK] 双击前激活该标签" in output, output
    assert "[FAIL]" not in output, f"存在失败项：\n{output}"
