from __future__ import annotations

from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


def _contrast_ratio(foreground: str, background: str) -> float:
    def luminance(value: str) -> float:
        channels = [int(value[index : index + 2], 16) / 255 for index in (1, 3, 5)]
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    lighter, darker = sorted(
        (luminance(foreground), luminance(background)), reverse=True
    )
    return (lighter + 0.05) / (darker + 0.05)


@pytest.mark.unit
def test_theme_tokens_define_composed_light_and_dark_palettes():
    source = (REPO_ROOT / "app/qml/components/Theme.qml").read_text(encoding="utf-8")

    # 默认深色（2026-10-28 产品定位调整）。浅色主题仍在，靠标题栏按钮切换。
    assert "property bool darkMode: true" in source
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
        'property string themeMode: "dark"',
        'function applyThemeMode(mode)',
        'function setThemeMode(mode)',
        'Theme.darkMode = mode === "dark"',
        'window.applyThemeMode(appearanceSettings.themeMode)',
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
def test_startup_applies_stored_theme_without_freezing_the_default():
    """启动只应用、不落盘，否则「默认值」会被第一次启动永久固化。

    旧实现 onCompleted 直接调 setThemeMode()，它会把解析出的模式写进
    uiAppearance/themeMode。结果是：用户哪怕从未点过主题按钮，第一次启动
    就把当时的默认值钉死了 —— 之后再改 Theme.qml 的默认值对他无效。
    （实测：默认改深色后，之前启动过一次的配置仍回落到浅色。）

    显式切换仍然要落盘，所以按钮和 --theme 继续走 setThemeMode。
    """
    main_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")

    assert "window.applyThemeMode(appearanceSettings.themeMode)" in main_source
    assert "window.setThemeMode(appearanceSettings.themeMode)" not in main_source


@pytest.mark.unit
def test_theme_toggle_uses_lucide_sun_and_moon_icons():
    icon_registry = (REPO_ROOT / "app/qml/components/AppIcons.qml").read_text(encoding="utf-8")

    assert 'readonly property string sun: "sun"' in icon_registry
    assert 'readonly property string moon: "moon"' in icon_registry
    for icon_name in ("sun.svg", "moon.svg"):
        assert (REPO_ROOT / "app/qml/icons" / icon_name).is_file()


@pytest.mark.unit
def test_text_selection_and_disabled_states_stay_readable_in_both_themes():
    theme_source = (REPO_ROOT / "app/qml/components/Theme.qml").read_text(encoding="utf-8")
    text_controls = (
        "AppTextField.qml",
        "AppTextArea.qml",
        "ValueBox.qml",
        "FontSelectBox.qml",
    )

    assert 'readonly property color selectionBackground: accent' in theme_source
    assert 'readonly property color selectionForeground: accentForeground' in theme_source

    for filename in text_controls:
        source = (REPO_ROOT / "app/qml/components" / filename).read_text(encoding="utf-8")
        assert "selectionColor: Theme.selectionBackground" in source
        assert "selectedTextColor: Theme.selectionForeground" in source

    for filename in (
        "AppButton.qml",
        "AppTextField.qml",
        "FontSelectBox.qml",
        "HermesNavItem.qml",
        "IconButton.qml",
        "OptionTile.qml",
        "SegmentedControl.qml",
        "ToggleSwitch.qml",
        "ValueBox.qml",
    ):
        source = (REPO_ROOT / "app/qml/components" / filename).read_text(encoding="utf-8")
        assert "opacity: enabled ? 1 :" not in source

    main_source = (REPO_ROOT / "app/qml/Main.qml").read_text(encoding="utf-8")
    assert "selectionColor: Theme.accentPressed" not in main_source
    assert "selectedTextColor: Theme.textPrimary" not in main_source


@pytest.mark.unit
def test_selection_and_disabled_palette_pairs_meet_text_contrast_floor():
    palette_pairs = (
        ("#ffffff", "#171716"),  # light selected text
        ("#111111", "#f1f1ef"),  # dark selected text
        ("#73736f", "#ffffff"),  # light disabled text on controls
        ("#a1a19d", "#242424"),  # dark disabled text on controls
    )

    for foreground, background in palette_pairs:
        assert _contrast_ratio(foreground, background) >= 4.5
