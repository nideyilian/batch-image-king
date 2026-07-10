from pathlib import Path

import pytest


@pytest.mark.unit
def test_render_composition_direct_calls_are_whitelisted():
    """P1：除 RenderService 兜底和底层兼容实现外，不再直接调用 render_composition。"""
    root = Path(__file__).resolve().parents[1]
    allowed = {
        "app/services/render_service.py",
        "app/models/document_render.py",
        "app/utils/gpu_render_integration.py",
    }
    offenders = []
    for path in (root / "app").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        if ".render_composition(" in text and rel not in allowed:
            offenders.append(rel)

    assert offenders == []


@pytest.mark.unit
def test_pickle_loads_go_through_trusted_loader_warning():
    """P4：项目/预设 pickle 读取应统一走可信文件提示辅助函数。"""
    root = Path(__file__).resolve().parents[1]
    allowed = {"app/utils/trusted_pickle.py"}
    offenders = []
    for path in (root / "app").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        if "pickle.load(" in text and rel not in allowed:
            offenders.append(rel)

    assert offenders == []


@pytest.mark.unit
def test_fast_renderer_direct_imports_are_whitelisted():
    """FastRenderer must stay behind service/runtime boundaries."""
    root = Path(__file__).resolve().parents[1]
    allowed = {
        "app/services/render_service.py",
        "app/services/preview_render_service.py",
        "app/models/document_render.py",
        "app/utils/fast_renderer.py",
        "app/utils/fast_renderer_cache.py",
        "app/utils/fast_renderer_composite.py",
        "app/utils/fast_renderer_preview.py",
        "app/utils/fast_renderer_surface.py",
        "app/utils/obe_plan_execution.py",
        "app/utils/obe_runtime_snapshot.py",
    }
    offenders = []
    needles = (
        "from app.utils.fast_renderer import",
        "import app.utils.fast_renderer",
    )
    for path in (root / "app").rglob("*.py"):
        rel = path.relative_to(root).as_posix()
        text = path.read_text(encoding="utf-8", errors="ignore")
        if rel not in allowed and any(needle in text for needle in needles):
            offenders.append(rel)

    assert offenders == []


@pytest.mark.unit
def test_legacy_layer_object_clipboard_is_gated():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app/controllers/layer_controller.py").read_text(encoding="utf-8", errors="ignore")
    assert "BTPW_ENABLE_LEGACY_LAYER_CLIPBOARD" in text
    assert "Legacy layer-object clipboard payload ignored" in text


@pytest.mark.unit
def test_document_serializer_uses_compat_helpers():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app/models/document_serializer.py").read_text(encoding="utf-8", errors="ignore")
    for name in (
        "normalize_layer_data",
        "restore_binding_groups",
        "restore_parent_group_id",
        "serialize_binding_groups",
    ):
        assert name in text
