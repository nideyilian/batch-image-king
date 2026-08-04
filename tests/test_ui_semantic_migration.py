from types import SimpleNamespace

import pytest

from app.ui.batch_export_dialog import BatchExportDialog
from app.ui.new_canvas_dialog import NewCanvasDialog
from app.ui.preset_manager_dialog import PresetDetailWidget


class FakeDocument:
    def __init__(self):
        self.layers = [SimpleNamespace(name="图层", current_image_path="", image_source="")]
        self.export_settings = {
            "batch_export_settings_saved": True,
            "use_layer_name": False,
            "use_date": True,
            "traverse_export": False,
            "smart_sampling": True,
        }

    def _calculate_possible_combinations(self):
        return 1


class FakePresetManager:
    pass


@pytest.mark.integration
def test_batch_export_actions_have_explicit_semantics(qapp):
    dialog = BatchExportDialog(FakeDocument())
    try:
        assert dialog.ok_btn.property("variant") == "default"
        assert dialog.browse_btn.property("variant") == "outline"
        assert dialog.save_config_btn.property("variant") == "secondary"
        assert dialog.progress_cancel_btn.property("variant") == "destructive"
        assert dialog.progress_bar.property("role") == "progress"
        assert dialog.calculated_count_label.property("role") == "status-value"
    finally:
        dialog.deleteLater()

@pytest.mark.integration
def test_preset_actions_use_primary_and_destructive_roles(qapp):
    panel = PresetDetailWidget(FakePresetManager())
    try:
        assert panel.edit_button.property("variant") == "secondary"
        assert panel.export_button.property("variant") == "secondary"
        assert panel.delete_button.property("variant") == "destructive"
        assert panel.apply_button.property("variant") == "default"
    finally:
        panel.deleteLater()


@pytest.mark.integration
def test_new_canvas_dialog_uses_dialog_and_button_semantics(qapp):
    dialog = NewCanvasDialog()
    try:
        buttons = {button.text(): button for button in dialog.button_box.buttons()}
        assert dialog.property("role") == "dialog"
        assert buttons["确定"].property("variant") == "default"
        assert buttons["取消"].property("variant") == "outline"
    finally:
        dialog.deleteLater()
