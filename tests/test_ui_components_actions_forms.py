import pytest
from PySide6.QtGui import QColor

from app.ui.components import (
    ButtonGroup,
    ColorSwatch,
    ComboBox,
    Field,
    IconButton,
    Input,
    InputGroup,
    MultiSelect,
    NumberInput,
    RadioGroup,
    SegmentedControl,
    Textarea,
    Toggle,
    ToggleGroup,
)


@pytest.mark.integration
def test_action_components_expose_stable_semantics(qapp):
    icon_button = IconButton("save", tool_tip="保存")
    toggle = Toggle("网格")
    group = ButtonGroup()
    group.add_button(icon_button)
    toggles = ToggleGroup()
    first = toggles.add_item("fit", "适应")
    second = toggles.add_item("fill", "填充")
    segmented = SegmentedControl(items=[("px", "像素"), ("percent", "百分比")])

    assert icon_button.property("uiSize") == "icon"
    assert icon_button.accessibleName() == "保存"
    assert toggle.isCheckable()
    assert group.property("role") == "button-group"
    assert toggles.property("role") == "toggle-group"
    first.click()
    second.click()
    assert toggles.current_value() == "fill"
    assert segmented.property("role") == "segmented-control"


@pytest.mark.integration
def test_form_components_cover_values_and_validation(qapp):
    textarea = Textarea(placeholder="输入文案")
    number = NumberInput(minimum=0, maximum=100, value=25, decimals=0, suffix="%")
    combo = ComboBox(items=["PNG", "JPG"])
    multi = MultiSelect(items=[("png", "PNG"), ("jpg", "JPG")])
    radio = RadioGroup(options=[("single", "单图"), ("batch", "批量")])
    field = Field("输出格式", combo, hint="选择导出格式")
    input_group = InputGroup(Input(placeholder="文件名"), prefix="前缀", suffix=".png")
    swatch = ColorSwatch("#3366FF")

    multi.set_selected_values(["jpg"])
    radio.set_value("batch")
    field.set_error("请选择可用格式")

    assert textarea.placeholderText() == "输入文案"
    assert number.value() == 25
    assert number.suffix() == "%"
    assert combo.isEditable()
    assert multi.selected_values() == ["jpg"]
    assert radio.value() == "batch"
    assert field.error_text() == "请选择可用格式"
    assert combo.property("invalid") is True
    assert input_group.property("role") == "input-group"
    assert swatch.color() == QColor("#3366FF")
