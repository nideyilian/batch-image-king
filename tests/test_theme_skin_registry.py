import pytest

from app.ui.theme.tokens import Theme


@pytest.fixture
def restore_theme():
    original = Theme.skin()
    yield
    Theme.unregister_skin("test-dark", missing_ok=True)
    Theme.set_skin(original)


def _test_skin():
    colors = Theme.colors().copy()
    colors["background"] = "#101010"
    colors["primary"] = "#33AAFF"
    return colors


@pytest.mark.unit
def test_default_skin_and_mode_alias_are_compatible():
    assert Theme.skin() == Theme.mode()
    assert "dark" in Theme.available_skins()


@pytest.mark.unit
def test_register_skin_copies_values_and_can_switch(restore_theme):
    colors = _test_skin()
    Theme.register_skin("test-dark", colors)
    colors["background"] = "#FFFFFF"

    Theme.set_skin("test-dark")

    assert Theme.skin() == "test-dark"
    assert Theme.color("background") == "#101010"


@pytest.mark.unit
def test_register_skin_validates_required_semantic_colors(restore_theme):
    with pytest.raises(ValueError, match="missing semantic colors"):
        Theme.register_skin("test-dark", {"background": "#101010"})


@pytest.mark.unit
def test_set_skin_rejects_unknown_skin(restore_theme):
    with pytest.raises(KeyError, match="unknown skin"):
        Theme.set_skin("does-not-exist")


@pytest.mark.unit
def test_skin_change_callback_can_be_removed(restore_theme):
    calls = []
    Theme.register_skin("test-dark", _test_skin())
    Theme.on_change(calls.append)
    try:
        Theme.set_skin("test-dark")
        assert calls[-1] == "test-dark"
    finally:
        Theme.off_change(calls.append)

