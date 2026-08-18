"""快捷键契约自动化测试

目标：
1. 验证快捷键契约模块 shortcut_contract 本身可导入、无内部冲突、无核心键位抢占。
2. 抽样断言 Photoshop 核心语义键位未被占用：
   - Ctrl+J   复制选中图层 via copy
   - Ctrl+T   自由变换（而非新建文字层）
   - Ctrl+E   向下合并图层（而非导出）
   - Ctrl+G / Ctrl+Shift+G  图层编组 / 取消编组
   - Ctrl+Shift+Z  重做（与 Ctrl+Y 兼容均可）
   - Ctrl+Alt+Z    后退一步 / Step Backward
   - Ctrl+[ / ]    图层前后移动一层
   - Ctrl+Shift+[ / ]  图层置底 / 置顶
   - Ctrl+D   取消选择 / Deselect（若应用未实现也不能用于复制标签页）
   - Ctrl+R   切换标尺（不能用于改画布尺寸）
   - Ctrl+L   曲线/色阶 — PS 色阶，本应用若不做也不能强占来新建图层
   - Ctrl+P   打印（若未实现，允许为空但不能被预设中心抢占）
3. 验证 QML Main.qml、经典 main_window_ui.py 中，关键冲突键位已按契约迁移。
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
APP_DIR = ROOT / "app"
QML_MAIN = ROOT / "app" / "qml" / "Main.qml"
CLASSIC_UI = ROOT / "app" / "main_window_ui.py"
CANVAS_EVENTS = ROOT / "app" / "ui" / "canvas_events.py"
CONTRACT_PY = APP_DIR / "utils" / "shortcut_contract.py"


# ---------------------------------------------------------------------------
# 1. 契约模块：无语法错误、核心语义表可枚举、detect_core_hijacks 返回空
# ---------------------------------------------------------------------------


def _load_contract_module():
    """动态导入契约模块，避免导入副作用提前失败。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location(
        "shortcut_contract", str(CONTRACT_PY)
    )
    if spec is None or spec.loader is None:
        pytest.skip("shortcut_contract 模块文件缺失")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.mark.unit
def test_contract_module_imports():
    """契约模块能被正常导入，并暴露关键 API。"""
    mod = _load_contract_module()
    required_attrs = (
        "ShortcutEntry",
        "shortcut_table",
        "seq",
        "detect_core_hijacks",
    )
    for attr in required_attrs:
        assert hasattr(mod, attr), f"契约模块缺少 {attr}"
    table = mod.shortcut_table()
    assert isinstance(table, list) and len(table) > 0, "快捷键表不应为空"
    for entry in table:
        assert isinstance(entry, mod.ShortcutEntry), (
            "shortcut_table 返回值必须是 ShortcutEntry 列表"
        )


@pytest.mark.unit
def test_no_duplicate_sequence_in_default_scope():
    """同一 ShortcutScope 下，同一 QKeySequence 文本不能被两个不同 action 占用。"""
    mod = _load_contract_module()
    seen: dict[tuple[str, str], str] = {}
    duplicates: list[str] = []
    for entry in mod.shortcut_table():
        key = (str(entry.scope), str(entry.sequence))
        if key in seen and seen[key] != entry.action_id:
            duplicates.append(
                f"[{entry.scope}] {entry.sequence} 同时被 {seen[key]} "
                f"和 {entry.action_id} 占用"
            )
        else:
            seen[key] = entry.action_id
    assert not duplicates, "快捷键契约内部冲突：\n" + "\n".join(duplicates)


@pytest.mark.unit
def test_no_photoshop_core_hijack_from_app_exclusive():
    """APP_EXCLUSIVE 层绝对不能抢占 Photoshop 核心键位。"""
    mod = _load_contract_module()
    hijacks = mod.detect_core_hijacks()
    assert hijacks == [], (
        "检测到应用专属快捷键抢占了 Photoshop 核心键位：\n"
        + "\n".join(str(h) for h in hijacks)
    )


@pytest.mark.unit
def test_core_semantics_have_expected_ps_sequences():
    """Photoshop 核心语义必须对应标准键位。"""
    mod = _load_contract_module()
    by_action = {e.action_id: e for e in mod.shortcut_table()}

    expected = {
        # action_id -> (期望的 QKeySequence 字符串集合中之一即可)
        "layer.duplicate":                {"Ctrl+J"},
        "layer.free_transform":           {"Ctrl+T"},
        "layer.merge_down":               {"Ctrl+E"},
        "layer.group":                    {"Ctrl+G"},
        "layer.ungroup":                  {"Ctrl+Shift+G"},
        "edit.redo":                      {"Ctrl+Shift+Z", "Ctrl+Y"},
        "edit.step_backward":             {"Ctrl+Alt+Z"},
        "layer.move_backward":            {"Ctrl+["},
        "layer.move_forward":             {"Ctrl+]"},
        "layer.send_to_back":             {"Ctrl+Shift+["},
        "layer.bring_to_front":           {"Ctrl+Shift+]"},
        "view.toggle_rulers":             {"Ctrl+R"},
        # "view.toggle_guides": {"Ctrl+Semicolon", ";"},  参考线键位各实现兼容
        "app.create_empty_image_layer":   {"Shift+Ctrl+N", "Ctrl+Shift+N"},
    }
    missing = []
    wrong = []
    for action_id, allowed in expected.items():
        if action_id not in by_action:
            missing.append(f"缺少核心动作：{action_id}")
            continue
        actual = by_action[action_id].sequence
        if str(actual) not in allowed and actual not in allowed:
            wrong.append(
                f"动作 {action_id} 期望键位 ∈ {allowed}，实际 = {actual!r}"
            )
    assert not missing, "以下 Photoshop 核心语义在契约中缺失：\n" + "\n".join(missing)
    assert not wrong, "以下核心语义键位不符合 Photoshop 习惯：\n" + "\n".join(wrong)


# ---------------------------------------------------------------------------
# 2. 源码回归：验证旧的冲突键位不再出现在文件里；抽样验证新契约已落地
# ---------------------------------------------------------------------------


SET_SHORTCUT_RE = re.compile(r"setShortcut\(\"([^\"]+)\"\)")
SET_SHORTCUTS_RE = re.compile(r"setShortcuts\(\[([^\]]+)\]\)")
QML_SHORTCUT_SEQ_RE = re.compile(r"sequence:\s*\"([^\"]+)\"")
QML_MENU_HINT_RE = re.compile(r"ShapeMenuItem\s*\{[^}]*text:\s*\"[^\"]*\\t([^\"]+)\"")


def _extract_classic_shortcuts(text: str) -> list[str]:
    """从经典界面源码抽出所有 setShortcut / setShortcuts 中的键位字符串。"""
    result: list[str] = []
    for m in SET_SHORTCUT_RE.finditer(text):
        result.append(m.group(1))
    for m in SET_SHORTCUTS_RE.finditer(text):
        # 形如 QKeySequence("Ctrl+Shift+Z"), QKeySequence.Redo
        for inner in re.findall(r"\"([^\"]+)\"", m.group(1)):
            result.append(inner)
    return result


def _extract_qml_shortcut_sequences(text: str) -> list[str]:
    return [m.group(1) for m in QML_SHORTCUT_SEQ_RE.finditer(text)]


@pytest.mark.unit
def test_classic_ui_no_longer_hijacks_ps_core_keys():
    """经典界面 main_window_ui.py 中，冲突源必须已迁出核心键位。"""
    assert CLASSIC_UI.is_file(), f"{CLASSIC_UI} 不存在"
    text = CLASSIC_UI.read_text(encoding="utf-8")
    used = set(_extract_classic_shortcuts(text))

    # 这些是曾经错误占用 PS 核心键位的映射：
    forbidden_now = [
        # (旧占用组合键, 原功能, 说明)
        ("Ctrl+D", "duplicate_tab_action", "Ctrl+D 在 PS 是取消选择/Deslect，禁止用于复制标签"),
        ("Ctrl+E", "export_action", "Ctrl+E 在 PS 是向下合并图层，禁止用于导出"),
        ("Ctrl+P", "preset_store_action", "Ctrl+P 在 PS 是打印，禁止用于预设中心"),
        ("Ctrl+R", "resize_canvas_action", "Ctrl+R 在 PS 是切换标尺，禁止用于改画布尺寸"),
        ("Ctrl+L", "add_layer_action", "Ctrl+L 在 PS 是色阶，禁止用于新建图层"),
        ("Ctrl+T", "add_text_layer_action", "Ctrl+T 在 PS 是自由变换，禁止用于新建文字层"),
    ]

    # 验证每条被释放的键位不再绑定到原 action 上（通过文本匹配）
    bad: list[str] = []
    for seq, old_action_id, reason in forbidden_now:
        # 在源码中，若该 seq 仍存在，必须不在 old_action 的 setShortcut 行；
        # 简单策略：按 seq 查找其上下文行，检查 old_action 是否是此行的左值
        for lineno, line in enumerate(text.splitlines(), start=1):
            if f"setShortcut(\"{seq}\")" in line or f"setShortcut(QKeySequence(\"{seq}\"))" in line:
                if old_action_id in line:
                    bad.append(
                        f"L{lineno}: {old_action_id} 仍然占用 {seq} — {reason}"
                    )
    assert not bad, "经典界面仍有以下冲突未迁移：\n" + "\n".join(bad)


@pytest.mark.unit
def test_classic_ui_core_semantics_present():
    """抽样验证：经典界面已注册 Ctrl+J/T/E/G/Shift+G/Shift+Z/Alt+Z。"""
    text = CLASSIC_UI.read_text(encoding="utf-8")
    used = set(_extract_classic_shortcuts(text))
    required_any = [
        ("Ctrl+J", "复制图层 via copy (PS)"),
        ("Ctrl+T", "自由变换 (PS)"),
        ("Ctrl+E", "向下合并图层 (PS)"),
        ("Ctrl+G", "图层编组 (PS)"),
        ("Ctrl+Shift+G", "取消图层编组 (PS)"),
        ("Ctrl+Shift+Z", "重做 (PS 风格)"),
        ("Ctrl+Alt+Z", "后退一步 (PS 风格)"),
    ]
    missing = [label for seq, label in required_any if seq not in used]
    assert not missing, "经典界面缺少以下 Photoshop 核心快捷键：\n" + "\n".join(
        f"- {label}" for label in missing
    )


@pytest.mark.unit
def test_qml_main_no_longer_hijacks_ps_core_keys():
    """QML Main.qml 中，导出/预设中心/新建图层/新建文字层等必须已离开 PS 核心键位。"""
    assert QML_MAIN.is_file(), f"{QML_MAIN} 不存在"
    text = QML_MAIN.read_text(encoding="utf-8")

    # 错误的旧绑定（动作标识 + 不应再出现的快捷键文本 + 菜单文字提示）
    banned_patterns = [
        # (在 QML 中唯一能定位旧键位的字符串片段, 理由)
        ("导出当前画面\\tCtrl+E\"", "导出菜单不应再使用 Ctrl+E 后缀"),
        ("预设中心\\tCtrl+P\"", "预设中心菜单不应再使用 Ctrl+P 后缀"),
        ("新建空图片图层\\tCtrl+L\"", "新建图层菜单不应再使用 Ctrl+L 后缀"),
        ("添加文字图层\\tCtrl+T\"", "新建文字图层菜单不应再使用 Ctrl+T 后缀"),
        ("复制当前标签\\tCtrl+D\"", "复制标签页菜单不应再使用 Ctrl+D 后缀"),
        ("修改画布尺寸\\tCtrl+R\"", "修改画布尺寸菜单不应再使用 Ctrl+R 后缀"),
        ("sequence: \"Ctrl+E\";.*exportDialog.open", "Ctrl+E 不能再绑定到导出"),
    ]
    bad: list[str] = []
    for idx, line in enumerate(text.splitlines(), start=1):
        for pattern, reason in banned_patterns:
            # 避免 re 转义麻烦：用 substring 检查
            # 去掉尾部的 \" 字面量，直接看关键段
            pattern_clean = pattern.replace("\\t", "\t").rstrip('"')
            if pattern_clean in line:
                bad.append(f"L{idx}: {reason} | line = {line.strip()}")
    assert not bad, "QML 仍存在以下旧冲突快捷键：\n" + "\n".join(bad)


@pytest.mark.unit
def test_qml_main_has_core_semantics_and_focus_gating():
    """验证 QML 已具备核心键位的 Shortcut，且具备焦点门控属性。"""
    text = QML_MAIN.read_text(encoding="utf-8")
    seqs = set(_extract_qml_shortcut_sequences(text))
    missing = []
    for label, seq in [
        ("复制图层 via copy", "Ctrl+J"),
        ("自由变换", "Ctrl+T"),
        ("向下合并", "Ctrl+E"),
        ("图层编组", "Ctrl+G"),
        ("取消编组", "Ctrl+Shift+G"),
        ("重做", "Ctrl+Shift+Z"),
        ("后退一步", "Ctrl+Alt+Z"),
        ("图层下移一层", "Ctrl+["),
        ("图层上移一层", "Ctrl+]"),
        ("置底", "Ctrl+Shift+["),
        ("置顶", "Ctrl+Shift+]"),
        ("标尺切换", "Ctrl+R"),
    ]:
        if seq not in seqs:
            missing.append(f"{label} ({seq})")
    assert not missing, "QML 缺少以下核心快捷键序列：\n" + "\n".join(
        f"- {s}" for s in missing
    )

    # 焦点门控：window 上必须具备 layerShortcutsEnabled / toolShortcutsEnabled 属性，
    # 且用于门控文字编辑态 + 输入框编辑态
    for key_attr in ("layerShortcutsEnabled", "toolShortcutsEnabled", "_editableInputHasFocus"):
        assert key_attr in text, (
            f"QML 缺失焦点门控属性 {key_attr}，无法避免输入框抢快捷键"
        )


@pytest.mark.unit
def test_canvas_events_ctrl_p_no_blind_accept():
    """canvas_events.py 的 Ctrl+P 必须仅在 perf 启用时才 accept。

    修复前：perf 未启用也会无条件 event.accept()，导致 Ctrl+P 永远无法响应菜单。
    """
    text = CANVAS_EVENTS.read_text(encoding="utf-8")
    # 检查修复模式：`if handled: event.accept()` 替代无条件 accept
    # 注意：这里只断言「无条件 accept 在 Key_P 分支中不再存在」
    lines = text.splitlines()
    in_ctrl_p = False
    bad_line = None
    for lineno, line in enumerate(lines, start=1):
        if "Qt.Key_P" in line:
            in_ctrl_p = True
            continue
        if in_ctrl_p:
            # 该分支结束的标志：遇到一个与外层结构同级的 if / for / 缩进减小后再
            # 不再回到 Key_P 分支。为简化判断：只要在「event.accept()」前 15 行
            # 内没看到 perf 保护分支，就记为旧实现。
            if "event.accept()" in line:
                # 往前看 15 行，是否存在 if is_perf_enabled / if handled
                start = max(0, lineno - 15)
                snippet = "\n".join(lines[start:lineno])
                if ("if handled:" not in snippet
                        and "is_perf_enabled()" not in snippet):
                    bad_line = lineno
                break
    assert bad_line is None, (
        f"canvas_events.py L{bad_line} 在 Ctrl+P 分支无条件接受事件；"
        "应只在性能报告实际输出时才 accept"
    )
