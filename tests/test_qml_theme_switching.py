from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.unit
def test_theme_tokens_define_composed_light_and_dark_palettes():
    source = (REPO_ROOT / "app/qml/components/Theme.qml").read_text(encoding="utf-8")

    assert "property bool darkMode: false" in source
    for token in (
        "bgApp",
        "bgBar",
        "bgPanel",
        "bgRaised",
        "bgControl",
        "bgHover",
        "bgCanvas",
        "bgSelected",
        "border",
        "borderStrong",
        "focusRing",
        "textPrimary",
        "textSecondary",
        "textMuted",
        "textDisabled",
        "accent",
        "accentForeground",
        "success",
        "warning",
        "danger",
    ):
        assert f"property color {token}: darkMode ?" in source

    for marker in (
        'bgApp: darkMode ? "#111111" : "#f4f4f3"',
        'bgPanel: darkMode ? "#181818" : "#ffffff"',
        'bgRaised: darkMode ? "#202020" : "#f7f7f6"',
        'bgControl: darkMode ? "#242424" : "#ffffff"',
        'borderStrong: darkMode ? "#3a3a3a" : "#d5d5d2"',
        'textPrimary: darkMode ? "#f1f1ef" : "#171716"',
        'accent: darkMode ? "#f1f1ef" : "#171716"',
        'accentForeground: darkMode ? "#111111" : "#ffffff"',
    ):
        assert marker in source


@pytest.mark.unit
def test_qml_theme_button_persists_and_toggles_the_selected_mode():
    main_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    launcher_source = (REPO_ROOT / "app/qml/qml_main.py").read_text(encoding="utf-8")

    for marker in (
        'id: appearanceSettings',
        'category: "uiAppearance"',
        'property string themeMode: "light"',
        'function setThemeMode(mode)',
        'Theme.darkMode = normalizedMode === "dark"',
        'id: interfaceSettingsButton',
        'iconName: Theme.darkMode ? AppIcons.sun : AppIcons.moon',
        'tooltip: Theme.darkMode ? "切换为浅色主题" : "切换为暗色主题"',
        'active: Theme.darkMode',
        'onClicked: window.setThemeMode(Theme.darkMode ? "light" : "dark")',
        'palette.window: Theme.bgApp',
        'palette.text: Theme.textPrimary',
        'palette.highlight: Theme.accent',
    ):
        assert marker in main_source

    assert 'parser.add_argument("--theme", choices=("light", "dark")' in launcher_source
    assert 'window, "setThemeMode", Q_ARG("QVariant", args.theme)' in launcher_source

    assert 'id: appearanceMenu' not in main_source
    assert 'text: (Theme.darkMode ? "    " : "✓  ") + "浅色主题"' not in main_source


@pytest.mark.unit
def test_title_bar_only_keeps_real_navigation_actions():
    source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    for marker in (
        'HermesNavItem { index: "01"; text: "画布"',
        'HermesNavItem { index: "02"; text: "预设"',
        'HermesNavItem { index: "03"; text: "导出"',
        'HermesNavItem { index: "04"; text: "命令"',
    ):
        assert marker in source

    for removed_marker in (
        'Hermes-style desktop workspace',
        'text: "工作台"',
        'text: "图层"; iconName: AppIcons.layers; onClicked: showToast',
        'id: commandSearchField',
        'text: "档案  default"',
    ):
        assert removed_marker not in source


@pytest.mark.unit
def test_theme_toggle_uses_lucide_sun_and_moon_icons():
    icon_registry = (REPO_ROOT / "app/qml/components/AppIcons.qml").read_text(encoding="utf-8")

    assert 'readonly property string sun: "sun"' in icon_registry
    assert 'readonly property string moon: "moon"' in icon_registry
    for icon_name in ("sun.svg", "moon.svg"):
        assert (REPO_ROOT / "app/qml/icons" / icon_name).is_file()
