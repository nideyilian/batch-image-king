import pytest
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QProgressBar,
    QPushButton,
    QToolButton,
    QVBoxLayout,
)

from app.ui.theme.polisher import polish_widget_tree


@pytest.mark.integration
def test_polisher_assigns_semantics_without_overwriting_explicit_variant(qapp):
    root = QDialog()
    layout = QVBoxLayout(root)
    default_button = QPushButton("保存")
    default_button.setDefault(True)
    plain_button = QPushButton("刷新")
    explicit_button = QPushButton("预览")
    explicit_button.setProperty("variant", "ghost")
    tool_button = QToolButton()
    tool_button.setText("更多")
    progress = QProgressBar()
    group = QGroupBox("导出设置")
    for widget in (default_button, plain_button, explicit_button, tool_button, progress, group):
        layout.addWidget(widget)

    polish_widget_tree(root)

    assert root.property("role") == "dialog"
    assert default_button.property("variant") == "default"
    assert plain_button.property("variant") == "secondary"
    assert explicit_button.property("variant") == "ghost"
    assert tool_button.property("variant") == "ghost"
    assert progress.property("role") == "progress"
    assert group.property("role") == "section"
    assert default_button.accessibleName() == "保存"


@pytest.mark.integration
def test_polisher_maps_dialog_button_box_roles(qapp):
    box = QDialogButtonBox()
    accept = box.addButton("应用", QDialogButtonBox.AcceptRole)
    reject = box.addButton("取消", QDialogButtonBox.RejectRole)
    destructive = box.addButton("删除", QDialogButtonBox.DestructiveRole)

    polish_widget_tree(box)

    assert accept.property("variant") == "default"
    assert reject.property("variant") == "outline"
    assert destructive.property("variant") == "destructive"


@pytest.mark.integration
def test_polisher_is_idempotent(qapp):
    button = QPushButton("操作")
    polish_widget_tree(button)
    button.setProperty("variant", "link")
    polish_widget_tree(button)
    assert button.property("variant") == "link"

