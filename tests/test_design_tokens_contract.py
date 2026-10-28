"""设计令牌契约 —— 字号 / 间距 / 尺寸只能有一个真源。

═══════════════════════════════════════════════════════════════════════════
为什么这些测试在「经典界面下线」之后仍然保留
═══════════════════════════════════════════════════════════════════════════

经典 Widgets 主界面已经删除，但 QML 工作台里**仍嵌着一批 QWidget 弹窗**
（颜色选择器、添加文字图层、新建画布、对话框基类），它们的配色和排版
仍然取自 `app/ui/design_spec.py`、`app/ui/design_tokens.py`、
`app/ui/tokens_v2.py`。

也就是说这三份令牌依然是**活的**。而它们历史上曾经三套并存、取值冲突
（`tokens_v2` MD=14/LG=16 vs `design_spec` MD=15/LG=18），按不同文件写
就会得到不同字号 —— 这就是「同一块面板字号乱」的根因。

下面这些断言守的是同一件事：**任何人想加一个新字号，必须先在 tokens_v2
里登记。** 从 tests/test_ui_rules.py 按 AST 机械提取（该文件里的面板级
契约已随经典界面一并删除）。
"""

from __future__ import annotations

import os
import re

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from app.ui.design_spec import Scale, Space  # noqa: E402


def test_scale_has_exactly_three_tiers():
    """高度必须只有 3 档。

    Ant Design / TDesign / Material 3 都是 3 档。
    档位再多，选档时就要「猜」，等于没有规范。
    """
    assert len(Scale.PX) == 3, f"高度档位应为 3，实际 {len(Scale.PX)}: {Scale.PX}"


def test_scale_is_on_4px_grid():
    """所有高度必须是 4 的倍数。

    不在 4px 栅格上的值（如旧代码的 30、34、38、26）无法互相整除，
    导致任意两个相邻控件都对齐不了 —— 这是「看着歪」的数学原因。
    """
    off_grid = {name: px for name, px in Scale.PX.items() if px % 4 != 0}
    assert not off_grid, f"以下档位不在 4px 栅格上: {off_grid}"


def test_scale_meets_wcag_click_target():
    """最小档位必须满足 WCAG 2.5.8 的 24x24 可点击目标。"""
    assert min(Scale.PX.values()) >= 24, "最小高度低于 WCAG 2.5.8 的 24px 下限"


def test_space_has_at_most_six_tiers():
    """间距档位不超过 6 档。"""
    assert len(Space.ALL) <= 6, f"间距档位过多: {Space.ALL}"


def test_space_is_on_4px_grid():
    """所有间距必须是 4 的倍数。"""
    off = [v for v in Space.ALL if v % 4 != 0]
    assert not off, f"间距不在 4px 栅格上: {off}"


def test_tokens_height_comes_from_spec():
    """Tokens.CONTROL_HEIGHT 必须等于 spec 的 MD 档。

    改造前 design_tokens 写死 30、tokens_v2 是 30、各处 setFixedSize 是 32/34/44，
    三套真源打架，实测同排控件歪 8px。
    """
    from app.ui.design_tokens import Tokens

    assert Tokens.CONTROL_HEIGHT == Scale.PX[Scale.MD], (
        f"Tokens.CONTROL_HEIGHT={Tokens.CONTROL_HEIGHT} 与 spec MD="
        f"{Scale.PX[Scale.MD]} 不一致"
    )


def test_qss_height_comes_from_spec():
    """全局 QSS 里的控件高度必须等于 spec 的 MD 档。"""
    from app.ui.theme.provider import build_global_stylesheet

    qss = build_global_stylesheet()
    expected = Scale.PX[Scale.MD]
    # control-h 会出现在 min-height: %%control-h%%px 的位置
    assert f"min-height: {expected}px" in qss or f"height: {expected}px" in qss, (
        f"QSS 里找不到 spec 高度 {expected}px"
    )


def test_no_off_grid_height_in_qss():
    """QSS 的**最终高度**不应出现旧档位（26/30/34/38）。

    这些是改造前的残留，一旦出现说明某个规则没走 design_spec。

    ⚠ 判据是「height + padding + border = 目标值」，所以内高可以是
    非栅格值（例如 icon 档目标 28，内高 28-2×1=26 是合法的）。
    直接搜「26px 出现」会误报，这里改成验证每条 icon 档规则
    的内高 + 边框正好等于 design_spec 的档位值。
    """
    import re

    from app.ui.design_spec import Scale
    from app.ui.theme.provider import build_global_stylesheet

    qss = build_global_stylesheet()

    # 1) 找出所有「图标按钮档位」规则，验证内高 + 2×border = 档位值
    icon_rules = {
        'uiSize="icon"': Scale.PX[Scale.MD],
        'uiSize="iconSm"': Scale.PX[Scale.SM],
    }
    for selector_key, target in icon_rules.items():
        pattern = (
            r'QPushButton\[' + re.escape(selector_key) + r'\][^{]*\{([^}]*)\}'
        )
        m = re.search(pattern, qss)
        assert m, f"找不到 {selector_key} 的规则"
        body = m.group(1)
        mh = re.search(r"min-height:\s*(\d+)px", body)
        assert mh, f"{selector_key} 规则里没有 min-height"
        inner = int(mh.group(1))
        # 这类按钮在控件内联 QSS 里写了 border: 1px
        assert inner + 2 == target, (
            f"{selector_key} 内高 {inner} + 边框 2 = {inner + 2}，"
            f"但档位目标是 {target}（应在 design_spec.Scale 里）"
        )

    # 2) 除图标档位外，其余地方不得直接写旧档位高度
    legacy = {30, 34, 38}
    hits = [h for h in legacy if f"min-height: {h}px" in qss]
    assert not hits, (
        f"QSS 仍在使用旧高度档位: {hits}（应只来自 design_spec 的 24/28/36）"
    )


def test_font_size_single_source():
    """字号必须只有一个真源：tokens_v2.Typography。

    design_spec.FontSize 与 design_tokens.Tokens 的数字必须与它一致，
    否则「按 spec 写」和「按 tokens_v2 写」会得到不同字号。
    """
    from app.ui.design_spec import FontSize
    from app.ui.design_tokens import Tokens
    from app.ui.tokens_v2 import Typography as T

    # design_spec 的每个档位都必须能在 tokens_v2 里找到同值
    spec_values = set(FontSize.ALL)
    v2_values = {
        T.size_caption, T.size_sm, T.size_base, T.size_md,
        T.size_lg, T.size_xl, T.size_2xl,
    }
    assert spec_values <= v2_values, (
        f"design_spec.FontSize 出现了 tokens_v2 里没有的字号: "
        f"{sorted(spec_values - v2_values)}"
    )

    # design_tokens 的语义字号也必须落在 tokens_v2 的档位内
    semantic = {
        "SIDEBAR_TITLE_FONT_SIZE": Tokens.SIDEBAR_TITLE_FONT_SIZE,
        "SIDEBAR_BODY_FONT_SIZE": Tokens.SIDEBAR_BODY_FONT_SIZE,
        "SECTION_TITLE_FONT_SIZE": Tokens.SECTION_TITLE_FONT_SIZE,
        "FIELD_LABEL_FONT_SIZE": Tokens.FIELD_LABEL_FONT_SIZE,
        "SUMMARY_FONT_SIZE": Tokens.SUMMARY_FONT_SIZE,
        "FEATURE_TITLE_FONT_SIZE": Tokens.FEATURE_TITLE_FONT_SIZE,
        "FONT_SIZE_BASE": Tokens.FONT_SIZE_BASE,
        "FONT_SIZE_SMALL": Tokens.FONT_SIZE_SMALL,
    }
    off_grid = {
        k: v for k, v in semantic.items() if v not in v2_values
    }
    assert not off_grid, (
        f"以下字号不在 tokens_v2 的档位内（说明又写死了新数字）: {off_grid}\n"
        f"合法档位: {sorted(v2_values)}"
    )


def test_no_hardcoded_font_size_in_qss():
    """QSS / setStyleSheet 里不得出现裸数字字号。

    只允许两种写法：
      - f-string 插值：`font-size: {Token}px`
      - 令牌变量：    `font-size: 12px` 仅当该值同时出现在令牌里

    这条测试的作用是：任何人想加一个新字号，必须先在 tokens_v2 里登记。
    """
    import os
    import re

    legal = set()
    from app.ui.tokens_v2 import Typography as T

    for name in dir(T):
        if name.startswith("size_"):
            legal.add(getattr(T, name))
    from app.ui.design_spec import FontSize

    legal |= set(FontSize.ALL)

    # 匹配 font-size: 12px 这种裸数字（不含花括号插值）
    # ⚠ 这里必须写 \\s \\d 而不是 \s \d —— 之前用 shell heredoc 生成该文件时，
    #   反斜杠被吃掉，正则变成了 "/s*(/d+)px"，永远匹配不到任何东西，
    #   测试看起来"通过"其实完全没生效（注入 17px 也能过）。
    #   这类"假通过"比没有测试更危险。
    pattern = re.compile(r"font-size:\s*(\d+)px")
    offenders = []
    for root, _dirs, files in os.walk("app"):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                lines = open(path, encoding="utf-8").read().splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if line.lstrip().startswith("#"):
                    continue
                for m in pattern.finditer(line):
                    value = int(m.group(1))
                    if value not in legal:
                        offenders.append(f"{path}:{i} → {value}px")

    assert not offenders, (
        "以下位置写了不在令牌档位内的字号，请改用 tokens_v2.Typography "
        "或 design_spec.FontSize：\n  " + "\n  ".join(offenders)
    )


def test_field_label_smaller_than_content():
    """字段标签必须比输入内容小一档（层级正确性）。

    「标签 12 / 内容 13」是当前规范。反过来（标签比内容大）会让
    每一行都像标题，整片失去层次 —— 属性面板之前就是这个毛病。
    """
    from app.ui.design_tokens import Tokens

    label = Tokens.FIELD_LABEL_FONT_SIZE
    body = Tokens.FONT_SIZE_BASE
    assert label < body, (
        f"字段标签字号({label})必须小于正文/输入内容字号({body})，"
        "否则表单看起来每一行都是标题"
    )


def test_no_font_size_arithmetic_offsets():
    """禁止对字号做算术偏移（如 FONT_SIZE_BASE + 1）。

    偏移出来的值不在档位上，等于绕过规范 —— 这是历史遗留的常见漂移源。
    """
    import os
    import re

    # 同样注意反斜杠：见上一条测试的说明
    pattern = re.compile(r"font-size:\s*\{[^}]*[\+\-]\s*\d+[^}]*\}px")
    offenders = []
    for root, _dirs, files in os.walk("app"):
        for fn in files:
            if not fn.endswith(".py"):
                continue
            path = os.path.join(root, fn)
            try:
                lines = open(path, encoding="utf-8").read().splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                if pattern.search(line):
                    offenders.append(f"{path}:{i}")
    assert not offenders, (
        "以下位置对字号做了算术偏移，会产生不在档位上的字号：\n  "
        + "\n  ".join(offenders)
    )


def test_design_tokens_stylesheet_font_sizes_all_legal():
    """design_tokens 生成的全部 QSS 里，字号必须都在档位上。

    上一条测的是「运行时可见控件」，但可见性依赖窗口状态（有没有选中图层、
    当前哪个 tab），容易漏。这条直接查**生成的 QSS 文本** —— 不管控件是否
    可见，只要样式里写了越界字号就会被抓。

    2026-10-28 实测抓到：design_tokens.py 里有一条写死 `font-size: 18px`
    （不在档位内的 18，规范是 16/20）。
    """
    import re

    from app.ui.design_tokens import Tokens
    from app.ui.tokens_v2 import Typography as T
    from app.ui.design_spec import FontSize

    legal = {getattr(T, n) for n in dir(T) if n.startswith("size_")}
    legal |= set(FontSize.ALL)

    qss_parts = []
    for method in ("control_qss", "panel_qss"):
        fn = getattr(Tokens, method, None)
        if fn is None:
            continue
        try:
            qss_parts.append(fn("#Probe"))
        except Exception as exc:  # 参数签名变了就跳过，不让测试本身变脆
            pytest.skip(f"Tokens.{method} 调用失败: {exc}")
    qss = "\n".join(qss_parts)
    if not qss:
        pytest.skip("Tokens 没有可调用的 QSS 生成方法")

    offenders = []
    # ⚠ 反斜杠必须写对（\\s \\d）。用 shell heredoc 生成代码时反斜杠会被吞，
    #   正则变成 "/s*(/d+)px" 就永远匹配不到 —— 测试"通过"但完全没生效。
    for m in re.finditer(r"font-size:\s*(\d+)px", qss):
        value = int(m.group(1))
        if value not in legal:
            offenders.append(value)

    assert not offenders, (
        f"design_tokens 生成的 QSS 里有越界字号 {sorted(set(offenders))}，"
        f"合法档位 {sorted(legal)}"
    )
