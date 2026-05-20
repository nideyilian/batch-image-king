# -*- coding: utf-8 -*-
import sys
import os

class NullWriter:
    """一个什么都不做的写入器，用于替换缺失的 stdout/stderr"""
    def write(self, message):
        pass
        
    def flush(self):
        pass
        
    def isatty(self):
        return False

def setup_streams():
    """
    配置标准输入输出流
    在 PyInstaller --noconsole 模式下，sys.stdout 和 sys.stderr 可能是 None
    这将导致 print() 调用抛出 AttributeError
    """
    # 检查是否在 PyInstaller 环境中
    if getattr(sys, 'frozen', False):
        # 如果是打包环境，且没有控制台（pythonw.exe），强制重定向
        if sys.stdout is None:
            sys.stdout = NullWriter()
        
        if sys.stderr is None:
            sys.stderr = NullWriter()
            
        # 即使它们不是 None，我们也可能想要重定向它们，以防某些库试图写入
        # 但如果我们有控制台（比如调试版本），我们可能想保留输出
        
        # 此外，还要处理 __stdout__ 和 __stderr__
        if sys.__stdout__ is None:
            sys.__stdout__ = NullWriter()
            
        if sys.__stderr__ is None:
            sys.__stderr__ = NullWriter()
            
    else:
        # 开发环境，如果莫名其妙丢失了流
        if sys.stdout is None:
            sys.stdout = NullWriter()
        if sys.stderr is None:
            sys.stderr = NullWriter()
