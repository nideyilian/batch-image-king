"""跨进程稳定的种子派生。

Python 内置 ``hash()`` 对 ``str`` / ``bytes`` 受 ``PYTHONHASHSEED`` 影响：
同一个字符串在父进程和子进程（或两次启动）里可能得到不同哈希值。
用它做随机种子会出现两种症状：

1. 预计算阶段算出的随机偏移，和导出进程重算的结果对不上；
2. 同一份工程导出两次，随机位置/缩放/旋转不一样。

``stable_seed`` 用 md5 派生，跨进程、跨机器、跨 Python 版本都一致。
"""

from __future__ import annotations

import hashlib
from typing import Any


def stable_seed(*parts: Any) -> int:
    """把若干参数派生为 32 位非负种子（跨进程稳定）。

    参数按位置拼接，使用 0x1f 分隔，避免 ``("ab", "c")`` 与 ``("a", "bc")`` 撞车。
    """
    digest = hashlib.md5()
    for index, part in enumerate(parts):
        if index:
            digest.update(b"\x1f")
        digest.update(str(part).encode("utf-8", "surrogatepass"))
    return int.from_bytes(digest.digest()[:4], "big") & 0x7FFFFFFF
