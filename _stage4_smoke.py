import sys
from PySide6.QtWidgets import QApplication

app = QApplication.instance() or QApplication(sys.argv)

# 1) panel_qss 含新增预览卡角色
from app.ui.design_tokens import Tokens
qss = Tokens.panel_qss("#IntegratedTextPanel")
for role in ("previewCard", "previewTitle", "previewArea"):
    assert f'[role="{role}"]' in qss, f"缺少角色 {role}"
print("PANEL_QSS_OK roles:", "previewCard/previewTitle/previewArea")

# 2) 导入所有改动模块（仅导入，不实例化，避开无关既有 bug）
import app.ui.property_panel_a2 as a2
import app.ui.integrated_text_panel_base as base
import app.ui.integrated_text_panel_content as content
import app.ui.integrated_text_panel as itp
import app.ui.layer_properties_base as lpb
print("IMPORT_OK:", a2.__name__, base.__name__, content.__name__, itp.__name__, lpb.__name__)

# 3) 验证属性面板外观层含 TEXT_INVERTED
assert hasattr(a2.PropertyPanelA2, "TEXT_INVERTED")
print("FACADE_OK TEXT_INVERTED =", a2.PropertyPanelA2.TEXT_INVERTED)

print("ALL_OK")
