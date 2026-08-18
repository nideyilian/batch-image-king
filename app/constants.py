"""
应用程序常量定义模块
"""

# 默认画布尺寸
DEFAULT_CANVAS_WIDTH = 800
DEFAULT_CANVAS_HEIGHT = 600

# 文字图层默认字体家族。文档保存通用别名，运行时按平台解析。
DEFAULT_TEXT_FONT_FAMILY = "sans-serif"

# 应用程序名称
APP_NAME = "模块批量出图工具"
APP_VERSION = "1.0.0"

# 文件类型过滤器
IMAGE_FILTER = "图像文件 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff);;所有文件 (*.*)"
PROJECT_FILTER = "项目文件 (*.cmp);;所有文件 (*.*)"

# 最大历史记录数
MAX_HISTORY_RECORDS = 50

# 缩放限制
MIN_ZOOM = 0.1
MAX_ZOOM = 10.0

# 默认颜色
DEFAULT_BG_COLOR = (60, 60, 60)
GRID_DARK_COLOR = (180, 180, 180)
GRID_LIGHT_COLOR = (220, 220, 220)
