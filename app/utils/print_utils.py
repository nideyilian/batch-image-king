#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
统一的打印工具模块
提供安全的打印函数，避免编码问题
"""


def safe_print(message: str):
    """
    安全的打印函数，避免编码问题
    
    Args:
        message: 要打印的消息字符串
        
    说明:
        - 首先尝试直接打印
        - 如果遇到编码错误，尝试使用ASCII编码
        - 最后的备选方案是打印简单的错误消息
    """
    try:
        print(message)
    except (UnicodeEncodeError, OSError):
        try:
            # 尝试使用ASCII编码，忽略无法编码的字符
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[ENCODING_ISSUE] {ascii_message}")
        except Exception:
            # 最后的备选方案，确保至少能输出一些信息
            print("[ENCODING_ERROR] Message encoding failed - unable to display content")


def safe_print_debug(message: str):
    """
    安全的调试打印函数
    
    Args:
        message: 要打印的调试消息
    """
    try:
        print(f"[DEBUG] {message}")
    except (UnicodeEncodeError, OSError):
        try:
            ascii_message = message.encode('ascii', 'ignore').decode('ascii')
            print(f"[DEBUG] {ascii_message}")
        except Exception:
            print("[DEBUG] Message encoding failed")

