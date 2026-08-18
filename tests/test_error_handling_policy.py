import logging


def test_error_policy_classifies_core_render_failures_as_fallback(caplog):
    from app.utils.error_handling import ErrorCategory, handle_core_exception

    caplog.set_level(logging.WARNING)
    category = handle_core_exception(
        ValueError("boom"),
        context="render primary path",
        category=ErrorCategory.INTERNAL_FALLBACK,
    )

    assert category is ErrorCategory.INTERNAL_FALLBACK
    assert "内部降级" in caplog.text
    assert "render primary path" in caplog.text


def test_error_policy_supports_user_visible_errors(caplog):
    from app.utils.error_handling import ErrorCategory, handle_core_exception

    caplog.set_level(logging.ERROR)
    category = handle_core_exception(
        RuntimeError("bad file"),
        context="load project",
        category=ErrorCategory.USER_VISIBLE,
    )

    assert category is ErrorCategory.USER_VISIBLE
    assert "用户可见错误" in caplog.text
