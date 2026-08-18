"""RenderService 唯一渲染出口的冒烟测试（P2）。

仅验证模块 API 与单例契约，不触发真实渲染（真实渲染需要画布 / 图层 / FastRenderer）。
如需端到端渲染回归，见 ``test_integration_baseline.py``。
"""
import pytest

from app.services.render_service import (
    get_render_service,
    render_document_to_image,
    RenderRequest,
    RenderResult,
    RenderService,
)


@pytest.mark.unit
def test_render_service_singleton():
    """get_render_service 应返回全局唯一实例。"""
    assert get_render_service() is get_render_service()
    assert isinstance(get_render_service(), RenderService)


@pytest.mark.unit
def test_render_request_defaults():
    """RenderRequest 应提供合理的默认值。"""
    req = RenderRequest(document=object(), mode="preview")
    assert req.mode == "preview"
    assert req.quality_profile == "quality"
    assert req.batch_mode is False
    assert req.force_refresh is False
    assert req.cancel_callback is None


@pytest.mark.unit
def test_render_document_to_image_callable():
    """便捷函数应存在且可调用（签名由类型注解保证）。"""
    assert callable(render_document_to_image)


@pytest.mark.unit
def test_render_result_type():
    """RenderResult 构造后默认 image 为空、ok 为 False。"""
    result = RenderResult(image=None)
    assert result.image is None
    assert result.ok is False
    assert result.error == ""
