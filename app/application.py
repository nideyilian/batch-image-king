#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import traceback
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QIcon, QFontDatabase
from PySide6.QtCore import QDir, QTranslator, QLocale

# 调整工作目录
if hasattr(sys, "_MEIPASS"):
    # PyInstaller 打包环境
    os.chdir(sys._MEIPASS)

# 添加当前目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

# 导入主窗口
from app.main_window import MainWindow
from app.utils.logger import Logger
from app.utils.print_utils import safe_print


# 全局异常处理
def handle_exception(exc_type, exc_value, exc_traceback):
    """处理未捕获的异常"""
    if issubclass(exc_type, KeyboardInterrupt):
        # 正常退出
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    # 记录异常
    error_msg = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
    safe_print(f"未捕获的异常:\n{error_msg}")
    Logger.critical(f"未捕获的异常:\n{error_msg}")

def main():
    """应用程序主入口"""
    # 设置异常处理器
    sys.excepthook = handle_exception

    # 创建应用程序
    app = QApplication(sys.argv)
    app.setApplicationName("图像批量合成工具")
    app.setOrganizationName("YourCompany")
    app.setOrganizationDomain("example.com")
    
    # 设置应用程序图标
    # app.setWindowIcon(QIcon("path/to/icon.png"))
    
    # 加载本地化翻译
    translator = QTranslator()
    if translator.load(QLocale(), "app", "_", "translations"):
        app.installTranslator(translator)
    
    # 创建主窗口
    main_window = MainWindow()
    main_window.show()
    
    # 运行应用程序
    return app.exec()

if __name__ == "__main__":
    sys.exit(main()) 