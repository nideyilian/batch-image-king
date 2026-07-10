"""
高级图像合成引擎包
包含Photoshop级别的图像处理功能
"""

import logging

logger = logging.getLogger(__name__)


def safe_print(message: str):
    """安全的打印函数，避免编码问题"""
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except Exception:
            logger.warning("静默异常已忽略: except in engines/__init__.py", exc_info=True)
            print("[DEBUG] Message encoding failed")


# 安全的导入机制
ENGINES_AVAILABLE = False
__all__ = []

# 首先检查关键依赖
try:
    import cv2
    import numpy as np
    from PIL import Image
    DEPENDENCIES_OK = True
except ImportError as e:
    safe_print(f"[WARNING] 高级引擎依赖缺失: {e}")
    DEPENDENCIES_OK = False

# 如果依赖OK，尝试导入引擎
if DEPENDENCIES_OK:
    try:
        from .advanced_compositor_manager import AdvancedCompositorManager, CompositeQuality
        __all__ = [
            'AdvancedCompositorManager',
            'CompositeQuality'
        ]

        ENGINES_AVAILABLE = True
        safe_print("[INFO] 高级合成引擎可用")

    except Exception as e:
        safe_print(f"[WARNING] 高级引擎初始化失败: {e}")
        ENGINES_AVAILABLE = False
        __all__ = []

# 提供安全的导入函数
def get_advanced_compositor():
    """安全获取高级合成器"""
    if ENGINES_AVAILABLE:
        try:
            return AdvancedCompositorManager, CompositeQuality
        except Exception:
            logger.warning("静默异常已忽略: except in engines/__init__.py", exc_info=True)
            pass
    return None, None