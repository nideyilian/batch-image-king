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
