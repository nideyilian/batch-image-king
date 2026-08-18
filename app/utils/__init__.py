"""
工具模块包
工具包
包含实用工具和辅助函数

重新组织后的结构：
- core: 核心功能（配置、日志、错误处理等）
- image: 图像处理相关
- ui: UI相关工具
- performance: 性能优化相关

注意：本包不再通配重导出子模块名字（原先的 ``from .core import *`` 等会把
``np``、``Image``、``logger`` 等意外名字污染到 ``app.utils`` 命名空间，并
导致启动时急切加载 cv2 等重型依赖）。使用方请按完整子模块路径导入，
例如 ``from app.utils.preset_manager import PresetManager``。
"""
