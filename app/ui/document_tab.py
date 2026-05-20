from PySide6.QtWidgets import QWidget, QVBoxLayout
from app.ui.canvas import CanvasWidget

class DocumentTab(QWidget):
    """文档标签页，包含单个文档的编辑器"""

    def __init__(self, document, parent=None):
        super().__init__(parent)
        self.document = document
        self.setup_ui()

    def setup_ui(self):
        """初始化UI"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 创建画布
        self.canvas = CanvasWidget(self.document)
        layout.addWidget(self.canvas)

    def get_canvas(self):
        """获取画布控件"""
        return self.canvas 