"""批图王版本单一来源。

发布新版本时只需修改 APP_VERSION，随后运行 python build.py：
- build.py 会据此生成 version_info.txt（PyInstaller 版本信息）。
- build.py 会刷新 update/update.json（自动更新清单）。

更新清单 URL 指向 GitHub 原始文件，推送到仓库后客户端即可发现新版本。
"""

APP_NAME = "批图王"
APP_VERSION = "1.1.5"
