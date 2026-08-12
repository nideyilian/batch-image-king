"""项目根 conftest.py。

职责：
1. 把项目根加入 ``sys.path``，让 ``import app.xxx`` 在 pytest 直接收集时也能找到包。
2. 提供可跑的集成测试基线：
   - 强制 PySide6 使用 ``offscreen`` 平台插件，使 GUI/UI 测试在无显示环境下也能运行。
   - 提供一个 session 级、autouse 的 ``qapp`` fixture，全测试会话共享同一个
     ``QApplication`` 实例（PySide6 不允许同时存在多个 QApplication，统一在此创建，
     各 UI 测试通过 ``QApplication.instance()`` 复用，避免重复创建报错）。
   这样无论是 pytest 函数式测试还是 unittest.TestCase 式 UI 测试，都能稳定拿到 Qt 环境。

集成测试请用 ``@pytest.mark.integration`` 标记；可用 ``pytest -m integration`` 单独运行，
不传 ``-m`` 时默认全部执行（含集成测试）。
"""

from __future__ import annotations

import os
import sys

# 必须在任何 PySide6 导入之前设置，否则会回退到平台默认（无显示环境会失败）
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# 把项目根目录加入 sys.path（兼容 pytest 任意调用方式）
_PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def qapp():
    """全会话共享的 QApplication（offscreen）。

    集成/UI 测试无需各自创建 QApplication；统一在此创建，unittest.TestCase 式的
    测试也会通过 ``QApplication.instance()`` 自动复用同一实例。

    若当前 Python 环境未安装 PySide6（例如只装了 pytest 做纯逻辑契约测试），
    则不创建 QApplication 并 yield None，允许非 UI 用例照常执行；真正依赖
    QApplication 的集成用例会在首次使用 Qt 类时自行失败，错误信息也会更准确。
    """
    try:
        from PySide6.QtWidgets import QApplication
    except ModuleNotFoundError:
        yield None
        return

    app = QApplication.instance() or QApplication([])
    yield app
