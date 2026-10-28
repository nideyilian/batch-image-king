"""
控制器模块
包含各种业务逻辑控制器

⚠ 这里**不要**再重导出 DocumentController。

原因：`from app.controllers.layer_controller import LayerController` 会先执行
本文件，于是本文件的任何导入都会变成"隐式依赖"。原先这里写着
`from .document_controller import DocumentController`，而 DocumentController
又导入了经典 Widgets 的 `app.ui.new_canvas_dialog` —— 结果 QML 工作台
仅仅为了拿一个 LayerController，就把整条经典版对话框链拖进了运行链
（实测 `sys.modules` 里多出 new_canvas_dialog / canvas_preset_dialog /
ui_primitives）。这类依赖在静态 import 图里看不见，只能靠运行时取证发现。

需要 DocumentController 的地方请直接写完整路径导入。
"""

from .layer_controller import LayerController

__all__ = ["LayerController"]
