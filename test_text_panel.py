#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试文字图层面板UI
"""

import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QScrollArea
from PySide6.QtCore import Qt

# 添加项目路径
sys.path.insert(0, '.')

from app.ui.integrated_text_panel import IntegratedTextPanel
from app.models.text_layer import TextLayer

class TestWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("文字图层面板测试")
        self.setGeometry(100, 100, 400, 800)
        
        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        
        # 创建文字图层面板
        self.text_panel = IntegratedTextPanel()
        
        # 创建测试文字图层
        test_layer = TextLayer(
            name="测试文字",
            x=50, y=50, width=300, height=100
        )
        test_layer.font_family = "Microsoft YaHei"
        test_layer.font_size = 24
        test_layer.text_color = (0, 0, 0, 255)
        test_layer.stroke_enabled = True
        test_layer.stroke_color = (255, 255, 255, 255)
        test_layer.stroke_width = 2
        
        # 设置图层到面板
        self.text_panel.set_text_layer(test_layer)
        
        scroll.setWidget(self.text_panel)
        self.setCentralWidget(scroll)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    
    # 应用暗色主题
    app.setStyle("Fusion")
    from PySide6.QtGui import QPalette, QColor
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(24, 24, 24))
    palette.setColor(QPalette.WindowText, QColor(244, 244, 245))
    palette.setColor(QPalette.Base, QColor(31, 31, 31))
    palette.setColor(QPalette.AlternateBase, QColor(42, 42, 42))
    palette.setColor(QPalette.ToolTipBase, QColor(244, 244, 245))
    palette.setColor(QPalette.ToolTipText, QColor(244, 244, 245))
    palette.setColor(QPalette.Text, QColor(244, 244, 245))
    palette.setColor(QPalette.Button, QColor(42, 42, 42))
    palette.setColor(QPalette.ButtonText, QColor(244, 244, 245))
    palette.setColor(QPalette.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.Highlight, QColor(47, 156, 244))
    palette.setColor(QPalette.HighlightedText, QColor(255, 255, 255))
    app.setPalette(palette)
    
    window = TestWindow()
    window.show()
    sys.exit(app.exec())
