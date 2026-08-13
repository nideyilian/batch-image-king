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
def test_qml_theme_menu_persists_and_applies_the_selected_mode():
    main_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    launcher_source = (REPO_ROOT / "app/qml/qml_main.py").read_text(encoding="utf-8")

    for marker in (
        'id: appearanceSettings',
        'category: "uiAppearance"',
        'property string themeMode: "light"',
        'function setThemeMode(mode)',
        'Theme.darkMode = normalizedMode === "dark"',
        'id: interfaceSettingsButton',
        'id: appearanceMenu',
        'text: (Theme.darkMode ? "    " : "✓  ") + "浅色主题"',
        'text: (Theme.darkMode ? "✓  " : "    ") + "暗色主题"',
        'onTriggered: window.setThemeMode("light")',
        'onTriggered: window.setThemeMode("dark")',
        'palette.window: Theme.bgApp',
        'palette.text: Theme.textPrimary',
        'palette.highlight: Theme.accent',
    ):
        assert marker in main_source

    assert 'parser.add_argument("--theme", choices=("light", "dark")' in launcher_source
    assert 'window, "setThemeMode", Q_ARG("QVariant", args.theme)' in launcher_source
