"""P3 硬编码色值清理：候选映射与收益量化。

不直接改文件，只产出「哪一处该映射到哪个令牌」的清单，
让人工确认语义无误后再落地。语义不明的一律标 UNSURE，不猜。

用法：
    python tools/audit_hardcoded_colors.py            # 打印清单
    python tools/audit_hardcoded_colors.py --apply    # 落地 SAFE 项
"""

from __future__ import annotations

import argparse
import os
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

HEX = re.compile(r"#[0-9A-Fa-f]{6}\b|#[0-9A-Fa-f]{3}\b")

# 令牌定义文件本身不参与清理（这里就该写色值）
TOKEN_FILES = {
    "tokens_v2.py",
    "design_tokens.py",
    "dark_theme.py",
    "provider.py",
    "tokens.py",
    "visual_hierarchy.py",
}

# 已确认 0 引用的死代码文件：改它没有用户收益，只统计不清理
DEAD_FILES = {
    "integrated_text_editor_dialog.py",
    "simple_text_editor_dialog.py",
    "preset_panel.py",
    "add_shaped_layer_dialog.py",
    "export_progress_dialog.py",
}

# 语义明确的映射：旧值 -> (令牌名, 说明)
SAFE_MAP: dict[str, tuple[str, str]] = {
    # 旧主色（Ant 蓝系）→ 品牌主色
    "#2f9cf4": ("accent", "旧主色 #2F9CF4"),
    "#55b2ff": ("accent_hover", "旧主色亮档"),
    # 旧灰阶 → 表面层级
    "#1f1f1f": ("surface_3", "旧控件底"),
    "#303033": ("border_strong", "旧描边"),
    "#253244": ("surface_selected", "旧选中底"),
    # 旧文本灰 → 文本层级
    "#8e8e93": ("text_muted", "旧提示文字"),
    "#c7c7c9": ("text_secondary", "旧次要正文"),
    "#f4f4f5": ("text_primary", "旧主文本"),
    # 与令牌完全一致，纯替换
    "#ffffff": ("text_on_accent", "纯白"),
    "#000000": ("canvas", "纯黑底"),
}

# 语义模糊或属于「局部设计」：不自动改，只列出来供人工判断
UNSURE_HINTS = {
    "#4a4a4a": "旧控件 hover 底，可能是 surface_hover 也可能是局部强调",
    "#5a5a5a": "旧禁用/次级描边，需看具体控件",
    "#ccc": "HTML 片段里的表格描边，属于富文本内部样式",
    "#1e1e1e": "编辑器底色，与 surface_base 接近但不等值",
    "#2f2f2f": "编辑器行号栏",
    "#3a3a3a": "编辑器边框",
}

# 色板数据文件：这些色值是「用户可选的颜料」，不是主题样式
PALETTE_FILES = {"color_picker_dialog_a2.py"}

# 语义不同、**不应**令牌化的白色（值为 #FFFFFF 但语义不是「主色上的文字」）：
#   icon_manager      → 图标绘制函数的默认色参数，与主题无关
#   add_text_layer_*  → 画在任意用户选色块上的文字，必须恒定白以保对比度
WHITE_EXEMPT = {"icon_manager.py", "add_text_layer_dialog_simple.py"}

# 算法常量：用于「在任意底色上选深/浅文字」的亮度判断。
# 这两个值是一对配套的极值（近黑 / 近白），换成主题令牌会让配对关系失去语义
# （主题的 text_primary 是 #F7F8F8，不是纯白，判断阈值会漂）。
ALGORITHM_FILES = {"layer_properties_shape.py"}

# 纯默认参数：构造函数缺省色，不是样式声明
DEFAULT_ARG_FILES = {"forms.py"}


def scan() -> tuple[dict[str, list], dict[str, list]]:
    """返回 (live_hits, dead_hits)，key 是色值。"""
    live: dict[str, list] = defaultdict(list)
    dead: dict[str, list] = defaultdict(list)

    for root, dirs, files in os.walk(os.path.join(ROOT, "app", "ui")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if not fn.endswith(".py") or fn in TOKEN_FILES or fn in PALETTE_FILES:
                continue
            path = os.path.join(root, fn)
            try:
                src = open(path, encoding="utf-8").read()
            except Exception:
                continue
            bucket = dead if fn in DEAD_FILES else live
            for lineno, line in enumerate(src.splitlines(), 1):
                # 跳过纯注释行：注释里提到历史色值是说明性文字，不是活样式
                if line.strip().startswith("#"):
                    continue
                for m in HEX.finditer(line):
                    color = m.group(0).lower()
                    if color == "#ffffff" and fn in WHITE_EXEMPT:
                        continue
                    if fn in ALGORITHM_FILES or fn in DEFAULT_ARG_FILES:
                        continue
                    bucket[color].append((fn, lineno, line.strip()))

    return live, dead


def report() -> None:
    live, dead = scan()

    live_total = sum(len(v) for v in live.values())
    dead_total = sum(len(v) for v in dead.values())
    print(f"活代码硬编码: {live_total} 处 / {len(live)} 种")
    print(f"死代码硬编码: {dead_total} 处 / {len(dead)} 种（无用户收益，不清理）")
    print()

    safe_hits = 0
    sure_rows = []
    for color, locs in live.items():
        if color in SAFE_MAP:
            token, why = SAFE_MAP[color]
            safe_hits += len(locs)
            sure_rows.append((len(locs), color, token, why))
    sure_rows.sort(reverse=True)

    print(f"=== 活代码中仍待替换（{safe_hits} 处，占活代码 {safe_hits / max(live_total, 1) * 100:.0f}%）===")
    if not sure_rows:
        print("  （无）")
    for n, color, token, why in sure_rows:
        files = sorted({fn for fn, _, _ in live[color]})
        print(f"  {color:9} ×{n:<3} → {token:16} {', '.join(files)}")
    print()

    unsure = [(c, l) for c, l in live.items() if c not in SAFE_MAP]
    unsure.sort(key=lambda kv: -len(kv[1]))
    print(f"=== 需人工判断 / 保留（{sum(len(v) for _, v in unsure)} 处）===")
    for color, locs in unsure[:18]:
        hint = UNSURE_HINTS.get(color, "")
        print(f"  {color:9} ×{len(locs):<3} {hint}")
    print()

    # 逐文件收益
    per_file = Counter()
    for color, locs in live.items():
        if color in SAFE_MAP:
            for fn, _, _ in locs:
                per_file[fn] += 1
    print("=== 按文件收益（只统计可安全替换）===")
    for fn, n in per_file.most_common():
        print(f"  {fn:34} {n}")


def apply() -> None:
    """把 SAFE_MAP 中『色值与令牌完全一致』的项做纯文本替换。

    只处理值完全相等的（#ffffff → text_on_accent 这类），
    因为这类替换不可能改变视觉。语义映射（如旧灰阶 → surface_3）
    会轻微改色，必须逐文件回归，不在自动脚本里做。
    """
    from app.ui.tokens_v2 import Color as C

    exact = {
        "#ffffff": C.text_on_accent,
        "#000000": C.canvas,
    }
    changed = []
    for root, dirs, files in os.walk(os.path.join(ROOT, "app", "ui")):
        dirs[:] = [d for d in dirs if d != "__pycache__"]
        for fn in files:
            if not fn.endswith(".py") or fn in TOKEN_FILES or fn in PALETTE_FILES:
                continue
            if fn in DEAD_FILES:
                continue
            path = os.path.join(root, fn)
            src = open(path, encoding="utf-8").read()
            new = src
            for old, tok in exact.items():
                # 只替换 QSS/styleSheet 里的字面量，不动数据列表
                new = re.sub(rf"(?i){re.escape(old)}\b", tok, new)
            if new != src:
                open(path, "w", encoding="utf-8").write(new)
                changed.append(fn)
    print(f"已替换值完全一致的项：{changed or '无'}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.apply:
        apply()
    else:
        report()
