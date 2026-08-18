import pytest

from app.ui.components import EmptyState, FileDropZone, Skeleton, Spinner, Table, Toast


@pytest.mark.integration
def test_feedback_components_expose_loading_empty_and_result_states(qapp):
    toast = Toast("导出完成", variant="success")
    spinner = Spinner()
    skeleton = Skeleton(width=180, height=20)
    empty = EmptyState("暂无预设", "保存后会显示在这里", action_text="新建")

    assert toast.property("role") == "toast"
    assert toast.property("variant") == "success"
    assert toast.message() == "导出完成"
    assert spinner.minimum() == 0 and spinner.maximum() == 0
    assert spinner.property("role") == "spinner"
    assert skeleton.property("role") == "skeleton"
    assert skeleton.size().width() == 180
    assert empty.property("role") == "empty-state"
    assert empty.action_button.text() == "新建"


@pytest.mark.integration
def test_table_and_file_drop_zone_keep_data_structured(qapp):
    table = Table(headers=["文件", "状态"])
    table.set_rows([["a.png", "成功"], ["b.png", "失败"]])
    dropped = []
    zone = FileDropZone(extensions=[".png", ".jpg"])
    zone.filesDropped.connect(dropped.append)

    accepted = zone.accept_paths(["A.PNG", "notes.txt", "b.jpg"])

    assert table.rowCount() == 2
    assert table.item(1, 1).text() == "失败"
    assert accepted == ["A.PNG", "b.jpg"]
    assert dropped == [["A.PNG", "b.jpg"]]

