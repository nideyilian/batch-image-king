"""项目根 conftest.py。

负责把项目根加入 ``sys.path``，让 ``import app.xxx`` 在 pytest 直接收集时
也能找到包。已有的 unittest 风格测试文件仍然保留各自的
``sys.path.insert(0, ...)`` 兜底，本文件只是更早、更统一的注入点。
"""
from __future__ import annotations

import os
import sys

# 把项目根目录加入 sys.path（兼容 pytest 任意调用方式）
_PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


# 显式暴露给 pytest 使用的 fixtures 集合
# 当前为空；后续若需要共享 fixture（例如临时目录、QApplication），
# 统一在这里实现，避免散落在各测试文件里。
