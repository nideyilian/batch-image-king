import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from app.ui.components import (
    Accordion,
    AlertDialog,
    AspectRatio,
    CommandPalette,
    ContextMenu,
    DropdownMenu,
    Popover,
    Resizable,
    ScrollArea,
    Sidebar,
)


@pytest.mark.integration
def test_layout_components_use_native_qt_layout_behavior(qapp):
    content = QLabel("内容")
    scroll = ScrollArea(content)
    splitter = Resizable(Qt.Horizontal)
    splitter.addWidget(QLabel("左"))
    splitter.addWidget(QLabel("右"))
    sidebar = Sidebar(width=240)
    ratio = AspectRatio(16 / 9)
    accordion = Accordion()
    item = accordion.add_item("导出设置", QLabel("设置内容"), expanded=True)

    assert scroll.widget() is content
    assert scroll.widgetResizable()
    assert splitter.property("role") == "resizable"
    assert sidebar.property("role") == "sidebar"
    assert sidebar.minimumWidth() == 240
    assert ratio.heightForWidth(320) == 180
    assert item.is_expanded()
    item.set_expanded(False)
    assert not item.is_expanded()


@pytest.mark.integration
def test_overlay_components_preserve_native_dialog_and_menu_semantics(qapp):
    dialog = AlertDialog("覆盖文件？", "同名文件将被替换", destructive=True)
    popover = Popover()
    menu = DropdownMenu("导出")
    action = menu.add_item("PNG", value="png")
    context_menu = ContextMenu()

    assert dialog.property("role") == "alert-dialog"
    assert dialog.confirm_button.property("variant") == "destructive"
    assert dialog.cancel_button.property("variant") == "outline"
    assert popover.property("role") == "popover-surface"
    assert action.data() == "png"
    assert context_menu.property("role") == "context-menu"


@pytest.mark.integration
def test_command_palette_filters_and_triggers_commands(qapp):
    calls = []
    palette = CommandPalette()
    palette.add_command("new", "新建画布", lambda: calls.append("new"), keywords="canvas")
    palette.add_command("export", "批量导出", lambda: calls.append("export"), keywords="batch")

    palette.set_query("导出")

    assert palette.visible_commands() == ["export"]
    assert palette.trigger_command("export")
    assert calls == ["export"]

