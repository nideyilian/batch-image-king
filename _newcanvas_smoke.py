import sys
from PySide6.QtWidgets import QApplication
app = QApplication(sys.argv)

from app.ui.new_canvas_dialog import NewCanvasDialog, get_canvas_settings

# 构造（无 controller，验证内部 CanvasPresetManager 生效）
dlg = NewCanvasDialog(None)
print("PRESET_ITEMS", dlg.preset_combo.count())
print("WIDTH", dlg.width_spin.value(), "HEIGHT", dlg.height_spin.value())
print("ALIAS_w", dlg.width_spinbox is dlg.width_spin, "ALIAS_h", dlg.height_spinbox is dlg.height_spin)

# 校验：空名称应被拦截且显示行内提示
# 注：headless 下对话框未 show()，父级隐藏使 isVisible() 为假；
# 用 isVisibleTo 验证“若父级可见则该提示可见”
dlg.name_edit.setText("")
dlg.accept()
print("EMPTY_REJECTED", dlg.result_settings is None, "ALERT_SHOWABLE", dlg.alert.isVisibleTo(dlg))
# 输入名称后提示应自动隐藏
dlg.name_edit.setText("abc")
print("ALERT_AUTO_HIDE", not dlg.alert.isVisibleTo(dlg))

# 正常接受
dlg.name_edit.setText("测试文档")
dlg.accept()
print("RESULT", dlg.result_settings)

# 比例按钮
dlg2 = NewCanvasDialog(None)
dlg2._apply_ratio(1920, 1080)
print("RATIO", dlg2.width_spin.value(), dlg2.height_spin.value(), dlg2.preset_combo.currentText())

# 交换
dlg2._swap_dimensions()
print("SWAP", dlg2.width_spin.value(), dlg2.height_spin.value())

# 注：headless 下 exec() 会自动返回，不能代表真实取消行为，跳过该断言
print("ALL_OK")
