"""Trusted pickle loading helpers.

Project and preset ``.cmp`` files are pickle payloads for backward
compatibility. Plain ``pickle.load`` can execute arbitrary code during
unpickling, so a malicious ``.cmp`` is an RCE vector. To close that
hole, every load in the app goes through :func:`load_trusted_pickle`,
which uses :class:`RestrictedUnpickler` with a strict allowlist:

- ``builtins``: only pure data/container types. Dangerous callables used
  by classic RCE gadgets (``eval`` / ``exec`` / ``open`` / ``getattr`` /
  ``__import__`` ...) are rejected.
- safe stdlib modules: ``enum``, ``collections``, ``datetime``,
  ``copyreg`` (pickle's own old-style reconstruction helpers).
- the app's own namespaces (``app.*``): document/layer/preset data such
  as the ``ShapeType`` enum member referenced by shaped layers.

Anything else (``os``, ``subprocess``, ``posix``, ``builtins.eval`` ...)
raises ``pickle.UnpicklingError`` and the file is rejected.
"""

from __future__ import annotations

import logging
import pickle
from typing import BinaryIO, Any

logger = logging.getLogger(__name__)

TRUSTED_PICKLE_WARNING = (
    "正在读取 pickle 格式的项目/预设文件；仅应打开来自可信来源的 .cmp 文件。"
)

# builtins 白名单：只允许纯数据/容器类型。
_ALLOWED_BUILTINS = frozenset(
    {
        "NoneType",
        "bool",
        "int",
        "float",
        "str",
        "bytes",
        "complex",
        "object",
        "range",
        "slice",
        "tuple",
        "list",
        "dict",
        "set",
        "frozenset",
    }
)

# 标准库安全模块白名单（这些模块内没有可被 pickle 利用的危险 callable）。
_ALLOWED_STDLIB_MODULES = frozenset(
    {
        "collections",
        "collections.abc",
        "datetime",
        "copyreg",
        "enum",
    }
)

# 应用自身命名空间：.cmp 里的图层/文档/预设数据（如 ShapeType 枚举）都来自 app.*。
_APP_MODULE_PREFIX = "app."


def _is_allowed(module: str, name: str) -> bool:
    if module == "builtins":
        return name in _ALLOWED_BUILTINS
    if module in _ALLOWED_STDLIB_MODULES:
        return True
    if module.startswith(_APP_MODULE_PREFIX):
        return True
    return False


class RestrictedUnpickler(pickle.Unpickler):
    """只允许白名单内模块/类的 Unpickler，阻断 pickle RCE。

    ``find_class`` 是 pickle 反序列化时解析任意类引用的唯一入口；重写它并
    拒绝白名单之外的模块/类，即可阻止恶意载荷导入 ``os.system``、
    ``builtins.eval`` 等危险对象。
    """

    def find_class(self, module: str, name: str):
        if not _is_allowed(module, name):
            raise pickle.UnpicklingError(
                "拒绝反序列化不受信任的类 {}.{}（.cmp 仅应来自可信来源）".format(
                    module, name
                )
            )
        return super().find_class(module, name)


def load_trusted_pickle(file_obj: BinaryIO, source_label: str = ".cmp 文件") -> Any:
    """Load a trusted pickle payload and emit a consistent safety warning.

    Raises:
        pickle.UnpicklingError: 载荷引用了白名单之外的类（可能是恶意文件）。
    """
    logger.warning("%s 来源: %s", TRUSTED_PICKLE_WARNING, source_label)
    return RestrictedUnpickler(file_obj).load()
